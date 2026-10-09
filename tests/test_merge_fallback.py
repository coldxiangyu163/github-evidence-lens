import unittest
from examples.synthetic_demo import SyntheticAPI
from github_evidence_lens.core import Collector, APIError


class MissingMergeTests(unittest.TestCase):
    def test_absent_merge_field_uses_detail(self):
        class API(SyntheticAPI):
            def get(self, endpoint, params=None):
                data = super().get(endpoint, params)
                if endpoint == 'search/issues':
                    for row in data['items']:
                        row['pull_request'] = {}
                return data
        result = Collector(API(), sample_prs=0).collect('demo-user')
        self.assertEqual(result['counts']['external_merged'], 1)
        self.assertEqual(result['counts']['external_closed_unmerged'], 0)
        self.assertEqual(result['counts']['external_open'], 1)
        self.assertFalse(result['errors'])

    def test_unknown_merge_state_not_false(self):
        class API(SyntheticAPI):
            def get(self, endpoint, params=None):
                if endpoint == 'repos/example-org/project/pulls/1':
                    raise APIError('Unavailable')
                data = super().get(endpoint, params)
                if endpoint == 'search/issues':
                    data['items'][0]['pull_request'] = {}
                return data
        result = Collector(API(), sample_prs=0).collect('demo-user')
        self.assertEqual(result['counts']['external_merged'], 0)
        self.assertEqual(result['counts']['external_closed_unmerged'], 0)
        self.assertTrue(result['errors'])
