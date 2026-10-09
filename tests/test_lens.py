import copy
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree

from examples.synthetic_demo import SyntheticAPI, demo
from github_evidence_lens.core import APIError, Collector, GhAPI, atomic_json, reference, sanitize, username
from github_evidence_lens.report import render, validate_bundle, validate_findings
from github_evidence_lens.__main__ import main


class Tests(unittest.TestCase):
    def test_exact_validation(self):
        for bad in (' demo', 'demo ', '@demo', 'demo/name', '-demo', 'a--b', 'a' * 40, 'a\n'):
            with self.assertRaises(ValueError):
                username(bad)
        for bad in ('o/r#0', 'o/r#01', 'o/../r#1', 'o/..#1', 'https://github.com/o/r#1', 'o/r#1\n'):
            with self.assertRaises(ValueError):
                reference(bad)
        self.assertEqual(reference('demo-user/re.po#12'), ('demo-user/re.po', 12))

    def test_endpoint_allowlist(self):
        for bad in ('https://evil.invalid', 'user/repos', 'repos/o/r/../../user', 'repos/o/r/actions/secrets', 'repos/o/r?x=1'):
            with self.assertRaises(APIError):
                GhAPI().get(bad)

    def test_pagination(self):
        class API:
            def get(self, endpoint, params):
                return list(range(100)) if params['page'] == 1 else [100]
        collector = Collector(API())
        rows, flags = collector.pages('anything')
        self.assertEqual(len(rows), 101)
        self.assertEqual(flags['pages'], 2)
        self.assertFalse(flags['truncated'])

    def test_page_budget(self):
        class API:
            def get(self, endpoint, params):
                return list(range(100))
        rows, flags = Collector(API(), max_pages=1).pages('anything')
        self.assertTrue(flags['truncated'])
        self.assertEqual(len(rows), 100)

    def test_search_ceiling_and_incomplete(self):
        class API:
            def get(self, endpoint, params):
                return {'items': list(range(100)), 'total_count': 5000, 'incomplete_results': True}
        rows, flags = Collector(API()).pages('search/issues', 'items', 101)
        self.assertEqual(len(rows), 101)
        self.assertTrue(flags['truncated'])
        self.assertTrue(flags['incomplete_results'])
        self.assertEqual(flags['total'], 5000)

    def test_private_fail_closed(self):
        for meta in ({'private': True, 'visibility': 'private', 'full_name': 'o/r'}, {'private': False, 'visibility': 'internal', 'full_name': 'o/r'}, {'private': False, 'full_name': 'o/r'}, {'private': False, 'visibility': 'public', 'full_name': 'other/r'}):
            class API:
                def __init__(self): self.calls = []
                def get(self, endpoint, params=None):
                    self.calls.append(endpoint)
                    return meta
            api = API()
            bundle = Collector(api).inspect('o/r#1')
            self.assertEqual(api.calls, ['repos/o/r'])
            self.assertEqual(bundle['evidence'], [])
            self.assertTrue(bundle['errors'])

    def test_error_not_empty_success(self):
        class API:
            def get(self, endpoint, params=None): raise APIError('rate limit; status=403')
        collector = Collector(API())
        rows, flags = collector.pages('search/issues', 'items')
        self.assertEqual(rows, [])
        self.assertTrue(flags['errors'])
        self.assertTrue(flags['truncated'])
        self.assertIn('rate limit', collector.bundle['errors'][0]['error'])

    def test_partial_failure(self):
        class API:
            def get(self, endpoint, params=None):
                if params['page'] == 2: raise APIError('HTTP/API error; status=500')
                return [1] * 100
        rows, flags = Collector(API()).pages('items')
        self.assertEqual(len(rows), 100)
        self.assertTrue(flags['errors'])
        self.assertTrue(flags['truncated'])

    def test_visibility_before_detail_and_grouping(self):
        api = SyntheticAPI()
        bundle = Collector(api, sample_prs=3).collect('demo-user')
        self.assertEqual(bundle['counts']['external_merged'], 1)
        self.assertEqual(bundle['counts']['self_merged'], 1)
        self.assertEqual(bundle['counts']['external_open'], 1)
        self.assertEqual(bundle['counts']['external_closed_unmerged'], 0)
        calls = [c[0] for c in api.calls]
        self.assertLess(calls.index('repos/example-org/project'), calls.index('repos/example-org/project/pulls/1'))
        self.assertIn('is:public', next(p['q'] for e, p in api.calls if e == 'search/issues'))
        self.assertEqual(len(bundle['selection']['selected']), 3)
        self.assertNotIn('email', json.dumps(bundle))

    def test_deduplicate_and_stable_ids(self):
        class API(SyntheticAPI):
            def get(self, endpoint, params=None):
                value = super().get(endpoint, params)
                if endpoint == 'search/issues': value['items'].append(value['items'][0])
                return value
        one = Collector(API(), sample_prs=0).collect('demo-user')
        two = Collector(API(), sample_prs=0).collect('demo-user')
        self.assertEqual(sum(one['counts'].values()), 3)
        self.assertEqual([e['id'] for e in one['evidence']], [e['id'] for e in two['evidence']])

    def test_missing_patch_and_actors(self):
        class API(SyntheticAPI):
            def get(self, endpoint, params=None):
                value = super().get(endpoint, params)
                if endpoint.endswith('/files'): value[0].pop('patch')
                if endpoint.endswith('/reviews'):
                    value[0].update({'user': {'login': 'maintainer', 'type': 'User', 'email': 'secret@example.invalid'}, 'author_association': 'MEMBER', 'html_url': 'https://github.com/example-org/project/pull/1#pullrequestreview-123'})
                return value
        bundle = Collector(API()).inspect('example-org/project#1')
        self.assertTrue(next(e for e in bundle['evidence'] if e['kind'] == 'files')['completeness']['patch_missing'])
        review = next(e for e in bundle['evidence'] if e['kind'] == 'reviews')['content'][0]
        self.assertEqual(review['user'], {'login': 'maintainer', 'type': 'User'})
        self.assertEqual(review['author_association'], 'MEMBER')

    def test_base_private_rejected(self):
        class API(SyntheticAPI):
            def get(self, endpoint, params=None):
                value = super().get(endpoint, params)
                if endpoint.endswith('/pulls/1'): value['base']['repo']['visibility'] = 'internal'
                return value
        api = API()
        bundle = Collector(api).inspect('example-org/project#1')
        self.assertFalse(any(e['kind'] == 'pr_detail' for e in bundle['evidence']))
        self.assertFalse(any(e.endswith('/files') for e, p in api.calls))
        self.assertTrue(bundle['errors'])

    def test_redaction(self):
        text = sanitize({'email': 'private', 'body': 'mail me a@example.invalid ghp_abcdef123456 contact: abcde'})
        self.assertNotIn('email', text)
        self.assertNotIn('a@example.invalid', text['body'])
        self.assertNotIn('ghp_', text['body'])
        self.assertNotIn('abcde', text['body'])

    def test_citations(self):
        with tempfile.TemporaryDirectory() as out:
            bundle, findings = demo(out)
        ids = validate_bundle(bundle)
        self.assertEqual(len(validate_findings(findings, ids)), 1)
        for key, bad in [('evidence_ids', ['ev_not_real']), ('counterevidence_ids', ['unknown']), ('status', 'excellent'), ('rationale', ''), ('limitations', []), ('counterevidence', 'none')]:
            invalid = copy.deepcopy(findings)
            invalid['findings'][0][key] = bad
            with self.assertRaises(ValueError): validate_findings(invalid, ids)

    def test_injection_escaping(self):
        bundle = Collector(SyntheticAPI(), sample_prs=0).collect('demo-user')
        bundle['subject'] = '<script>alert(1)</script> [click](javascript:evil) ![x](https://evil.invalid/x)'
        with tempfile.TemporaryDirectory() as out:
            render(bundle, out)
            html = Path(out, 'report.html').read_text()
            markdown = Path(out, 'report.md').read_text()
            svg = Path(out, 'card.svg').read_text()
            self.assertNotIn('<script>', html)
            self.assertNotIn('<script>', markdown)
            self.assertNotIn('[click](javascript:', markdown)
            self.assertNotIn('<script>', svg)
            self.assertIn('&lt;script&gt;', html)
            ElementTree.fromstring(svg)
        bundle['evidence'][0]['url'] = 'javascript:alert(1)'
        with self.assertRaises(ValueError): validate_bundle(bundle)

    def test_duplicate_ids_rejected(self):
        bundle = Collector(SyntheticAPI(), sample_prs=0).collect('demo-user')
        bundle['evidence'].append(bundle['evidence'][0])
        with self.assertRaises(ValueError): validate_bundle(bundle)

    def test_atomic_and_cli_report(self):
        with tempfile.TemporaryDirectory() as out:
            bundle, findings = demo(out)
            self.assertEqual(json.loads(Path(out, 'bundle.json').read_text()), bundle)
            self.assertEqual(main(['report', str(Path(out, 'bundle.json')), '--out', str(Path(out, 'cli'))]), 0)
            self.assertIn('Not AI-reviewed', Path(out, 'cli', 'report.html').read_text())
            self.assertFalse(list(Path(out).glob('.evidence-*')))

    def test_cli_collect_and_inspect(self):
        with tempfile.TemporaryDirectory() as out, patch('github_evidence_lens.core.GhAPI', SyntheticAPI):
            self.assertEqual(main(['collect', 'demo-user', '--out', out, '--sample-prs', '1']), 0)
            self.assertTrue(Path(out, 'bundle.json').exists())
            self.assertEqual(main(['inspect', 'example-org/project#1', '--out', out]), 0)

    def test_cli_failure_exit(self):
        class API:
            def get(self, endpoint, params=None): raise APIError('HTTP/API error; status=403')
        with tempfile.TemporaryDirectory() as out, patch('github_evidence_lens.core.GhAPI', API):
            self.assertEqual(main(['collect', 'demo-user', '--out', out]), 2)
            self.assertTrue(json.loads(Path(out, 'bundle.json').read_text())['errors'])

    def test_cli_invalid(self):
        result = subprocess.run([sys.executable, '-m', 'github_evidence_lens', 'collect', '@bad', '--out', 'unused'], capture_output=True)
        self.assertEqual(result.returncode, 2)


if __name__ == '__main__':
    unittest.main()
