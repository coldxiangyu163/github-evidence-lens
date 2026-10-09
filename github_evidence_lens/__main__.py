import argparse
import json
import sys
from pathlib import Path

from .core import Collector, atomic_json, reference, username
from .report import render


def load_json(path):
    path = Path(path)
    if path.stat().st_size > 50_000_000:
        raise ValueError('Local input exceeds 50 MB budget')
    return json.loads(path.read_text(encoding='utf-8'))


def main(argv=None):
    parser = argparse.ArgumentParser(prog='github-evidence-lens', description='Public GitHub evidence inventory; no personal score or embedded LLM.')
    sub = parser.add_subparsers(dest='command', required=True)
    collect = sub.add_parser('collect', help='Collect public profile, repositories and authored PR evidence')
    collect.add_argument('user', type=username)
    collect.add_argument('--max-prs', type=int, default=100)
    collect.add_argument('--sample-prs', type=int, default=6)
    inspect = sub.add_parser('inspect', help='Agent-selected public PR deep inspection')
    inspect.add_argument('target', type=reference)
    for p in (collect, inspect):
        p.add_argument('--out', required=True)
        p.add_argument('--max-pages', type=int, default=10)
    report = sub.add_parser('report', help='Render inventory and optional structurally validated agent findings')
    report.add_argument('bundle')
    report.add_argument('--out', required=True)
    report.add_argument('--findings')
    args = parser.parse_args(argv)
    try:
        if args.command == 'report':
            result = render(load_json(args.bundle), args.out, load_json(args.findings) if args.findings else None)
            print(json.dumps(result))
            return 0
        collector = Collector(max_pages=args.max_pages, max_prs=getattr(args, 'max_prs', 100), sample_prs=getattr(args, 'sample_prs', 0))
        if args.command == 'collect':
            bundle = collector.collect(args.user)
        else:
            repo, pr = args.target
            bundle = collector.inspect(f'{repo}#{pr}')
            bundle['subject'] = f'{repo}#{pr}'
        atomic_json(Path(args.out) / 'bundle.json', bundle)
        print(json.dumps({'evidence_items': len(bundle['evidence']), 'errors': len(bundle['errors']), 'bundle': str(Path(args.out) / 'bundle.json')}))
        return 2 if bundle['errors'] else 0
    except (ValueError, OSError, TypeError, KeyError) as exc:
        print('Error: ' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
