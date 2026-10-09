"""SYNTHETIC offline API fixture. These are NOT real account observations."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from github_evidence_lens.core import APIError, Collector, atomic_json
from github_evidence_lens.report import render


class SyntheticAPI:
    def __init__(self):
        self.calls = []

    def get(self, endpoint, params=None):
        self.calls.append((endpoint, params))
        if endpoint == 'users/demo-user':
            return {'login': 'demo-user', 'public_repos': 1, 'type': 'User', 'email': 'not-real@example.invalid'}
        if endpoint == 'users/demo-user/repos':
            return [{'full_name': 'demo-user/sample', 'private': False}]
        if endpoint in ('repos/demo-user/sample', 'repos/example-org/project'):
            return {'full_name': endpoint[6:], 'private': False, 'visibility': 'public', 'fork': False}
        if endpoint == 'search/issues':
            return {'total_count': 3, 'incomplete_results': False, 'items': [
                {'html_url': 'https://github.com/example-org/project/pull/1', 'title': 'Synthetic merged change', 'state': 'closed', 'pull_request': {'merged_at': '2026-01-01T00:00:00Z'}},
                {'html_url': 'https://github.com/example-org/project/pull/2', 'title': 'Synthetic open change', 'state': 'open', 'pull_request': {}},
                {'html_url': 'https://github.com/demo-user/sample/pull/3', 'title': 'Synthetic self merge', 'state': 'closed', 'pull_request': {'merged_at': '2026-01-01T00:00:00Z'}},
            ]}
        if endpoint.endswith('/files'):
            return [{'filename': 'example.py', 'status': 'modified', 'patch': '@@ -1 +1 @@\n-old\n+new', 'additions': 1, 'deletions': 1}]
        if endpoint.endswith('/reviews'):
            return [{'id': 123, 'state': 'COMMENTED', 'body': 'SYNTHETIC: please add boundary tests.'}]
        if endpoint.endswith('/comments'):
            return []
        if endpoint.endswith('/check-runs'):
            return {'total_count': 1, 'check_runs': [{'id': 456, 'name': 'synthetic-test', 'status': 'completed', 'conclusion': 'success'}]}
        if '/pulls/' in endpoint:
            repo = endpoint.split('/pulls/')[0][6:]
            number = int(endpoint.rsplit('/', 1)[1])
            return {'number': number, 'title': 'SYNTHETIC PR', 'body': 'Synthetic fixture; not a real contribution.', 'state': 'open' if number == 2 else 'closed', 'merged': number != 2, 'changed_files': 1, 'head': {'sha': 'a' * 40}, 'base': {'repo': {'private': False, 'full_name': repo}}}
        raise APIError('Unknown synthetic endpoint')


def demo(out):
    bundle = Collector(SyntheticAPI(), sample_prs=3).collect('demo-user')
    bundle['source'] = 'SYNTHETIC OFFLINE FIXTURE — NOT A LIVE ACCOUNT REPORT'
    bundle['subject'] = 'SYNTHETIC demo-user'
    evidence = next(e for e in bundle['evidence'] if e['kind'] == 'checks')
    findings = {'schema_version': '0.1', 'findings': [{'claim': 'Synthetic selected check run reports success', 'status': 'supported', 'rationale': 'The fixture check run explicitly has status completed and conclusion success.', 'evidence_ids': [evidence['id']], 'counterevidence': ['Fixture review asks for boundary tests; green CI does not prove test adequacy.'], 'counterevidence_ids': [next(e['id'] for e in bundle['evidence'] if e['kind'] == 'reviews')], 'limitations': ['Synthetic demonstration only; not a finding about a real person.', 'One sampled check run does not establish overall quality.']}]}
    atomic_json(Path(out) / 'bundle.json', bundle)
    atomic_json(Path(out) / 'findings.json', findings)
    result = render(bundle, Path(out) / 'report', findings)
    print(result)
    return bundle, findings


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', default='artifacts/demo')
    demo(parser.parse_args().out)
