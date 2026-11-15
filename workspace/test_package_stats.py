import unittest
from urllib.parse import unquote
from unittest.mock import patch
import package_stats,server


def package():
    return dict(id='test.widget',source='https://github.com/alice/widget/blob/'+'a'*40+'/widget.json',artifact=dict(url='https://github.com/qlerup/ultrabar-store/releases/download/widget-v1/widget.json'))


class StatsTests(unittest.TestCase):
    def setUp(self):
        self.stats=package_stats.PackageStats();self.stats.remember([package()]);self.identity=self.stats.packages['test.widget']
    def data(self,path):
        if path.startswith('repos/'):return dict(assets=[dict(name='icon.png',download_count=900),dict(name='widget.json',download_count=17)])
        self.assertIn('repo:alice/widget is:issue is:open',unquote(path))
        return dict(total_count=3,incomplete_results=False)
    def test_counts_exact_artifact_and_issues_without_pull_requests(self):
        with patch.object(package_stats,'github_json',side_effect=self.data):self.stats.refresh([self.identity])
        row=self.stats.request(['test.widget'])['test.widget']
        self.assertEqual(row['downloads'],17);self.assertEqual(row['issues'],3);self.assertFalse(row['loading'])
    def test_cache_and_single_background_worker(self):
        with patch.object(package_stats.threading,'Thread') as thread:
            self.stats.request(['test.widget']);self.stats.request(['test.widget'])
            self.assertEqual(thread.call_count,1)
        self.stats.running=False
        with patch.object(package_stats,'github_json',side_effect=self.data) as fetch:
            self.stats.refresh([self.identity]);self.stats.refresh([self.identity]);self.assertEqual(fetch.call_count,2)
    def test_offline_retains_last_known_counts_and_caches_failure(self):
        with patch.object(package_stats,'github_json',side_effect=self.data):self.stats.refresh([self.identity])
        self.stats.responses.clear()
        with patch.object(package_stats,'github_json',side_effect=OSError('offline')) as fetch:
            self.stats.refresh([self.identity]);self.stats.refresh([self.identity]);self.assertEqual(fetch.call_count,2)
        row=self.stats.request(['test.widget'])['test.widget']
        self.assertEqual(row['downloads'],17);self.assertEqual(row['issues'],3);self.assertTrue(row['stale']);self.assertFalse(row['loading'])
    def test_unknown_local_and_untrusted_sources_cannot_trigger_requests(self):
        self.stats.remember([dict(package(),id='test.local',origin='local'),dict(package(),id='test.bad',source='https://evil.example/repo')])
        with patch.object(package_stats.threading,'Thread') as thread:
            self.assertEqual(self.stats.request(['unknown.package','test.local','test.bad']),{});thread.assert_not_called()
    def test_new_asset_uses_separate_stats_identity(self):
        with patch.object(package_stats,'github_json',side_effect=self.data):self.stats.refresh([self.identity])
        p=package();p['artifact']['url']=p['artifact']['url'].replace('widget-v1','widget-v2');self.stats.remember([p])
        with patch.object(package_stats.threading,'Thread'):
            row=self.stats.request(['test.widget'])['test.widget'];self.assertIsNone(row['downloads']);self.assertTrue(row['loading'])
    def test_rate_limit_stops_remaining_requests_and_never_fakes_zero(self):
        with patch.object(package_stats,'github_json',side_effect=package_stats.GitHubCooldown(1800)) as fetch:
            self.stats.refresh([self.identity]);self.assertEqual(fetch.call_count,1)
        row=self.stats.request(['test.widget'])['test.widget'];self.assertIsNone(row['downloads']);self.assertIsNone(row['issues']);self.assertTrue(row['stale'])
    def test_protected_bounded_endpoint(self):
        client=server.app.test_client();headers={'Host':'127.0.0.1:8741','X-Studio-Token':server.SESSION_TOKEN}
        self.assertEqual(client.get('/api/store/stats?ids=test.widget',headers={'Host':'127.0.0.1:8741'}).status_code,403)
        with patch.object(server.store,'stats',self.stats),patch.object(package_stats.threading,'Thread'):
            self.assertEqual(client.get('/api/store/stats?ids=test.widget',headers=headers).status_code,200)
            self.assertEqual(client.get('/api/store/stats?ids='+','.join(['test.widget']*13),headers=headers).status_code,400)
            self.assertEqual(client.get('/api/store/stats?ids=https://evil.example',headers=headers).status_code,400)
