import io,json,time,unittest
from unittest.mock import patch
import package_stats,server


def package():
    return dict(id='test.widget',version='1.0.0',source='https://github.com/alice/widget/blob/'+'a'*40+'/widget.json',artifact=dict(url='https://github.com/qlerup/ultrabar-store/releases/download/widget-v1/widget.json'))


def feed():
    return dict(schemaVersion=1,generatedAt=int(time.time()),packages={'test.widget':dict(repository='https://github.com/alice/widget',artifact=package()['artifact']['url'],downloads=17,issues=3,stale=False)})


class StatsTests(unittest.TestCase):
    def setUp(self):
        self.stats=package_stats.PackageStats();self.stats.remember([package()]);self.identity=self.stats.packages['test.widget']

    def test_counts_come_from_one_static_feed_without_api(self):
        with patch.object(package_stats,'urlopen',return_value=io.BytesIO(json.dumps(feed()).encode())) as fetch:self.stats.refresh([self.identity])
        self.assertEqual(fetch.call_count,1);self.assertEqual(fetch.call_args.args[0].full_url,package_stats.STATS_URL)
        self.assertNotIn('api.github.com',fetch.call_args.args[0].full_url)
        row=self.stats.request(['test.widget'])['test.widget']
        self.assertEqual(row['downloads'],17);self.assertEqual(row['issues'],3);self.assertFalse(row['loading'])

    def test_cache_and_single_background_worker(self):
        with patch.object(package_stats.threading,'Thread') as thread:
            self.stats.request(['test.widget']);self.stats.request(['test.widget']);self.assertEqual(thread.call_count,1)
        self.stats.running=False
        with patch.object(package_stats,'published_counts',return_value=feed()) as fetch:
            self.stats.refresh([self.identity]);self.stats.refresh([self.identity]);self.assertEqual(fetch.call_count,1)

    def test_offline_retains_counts_and_caches_failure(self):
        with patch.object(package_stats,'published_counts',return_value=feed()):self.stats.refresh([self.identity])
        self.stats.feed_expires=0
        with patch.object(package_stats,'published_counts',side_effect=OSError('offline')) as fetch:
            self.stats.refresh([self.identity]);self.stats.refresh([self.identity]);self.assertEqual(fetch.call_count,1)
        row=self.stats.request(['test.widget'])['test.widget']
        self.assertEqual(row['downloads'],17);self.assertEqual(row['issues'],3);self.assertTrue(row['stale']);self.assertFalse(row['loading'])

    def test_wrong_artifact_repository_and_invalid_counts_never_become_real_zero(self):
        for changes in ({'artifact':'https://example.com/file'},{'repository':'https://github.com/other/repo'},{'downloads':True,'issues':-1}):
            stats=package_stats.PackageStats();stats.remember([package()]);data=feed();data['packages']['test.widget'].update(changes)
            with patch.object(package_stats,'published_counts',return_value=data):stats.refresh([self.identity])
            row=stats.request(['test.widget'])['test.widget'];self.assertIsNone(row['downloads']);self.assertIsNone(row['issues']);self.assertTrue(row['stale'])

    def test_unknown_local_and_untrusted_packages_cannot_trigger_requests(self):
        self.stats.remember([dict(package(),id='test.local',origin='local'),dict(package(),id='test.bad',source='https://evil.example/repo')])
        with patch.object(package_stats.threading,'Thread') as thread:
            self.assertEqual(self.stats.request(['unknown.package','test.local','test.bad']),{});thread.assert_not_called()

    def test_latest_catalog_identity_is_not_overwritten_by_older_installed_record(self):
        latest=package();latest.update(version='2.0.0');latest['artifact']=dict(url=latest['artifact']['url'].replace('widget-v1','widget-v2'))
        self.stats.remember([latest]);self.stats.remember([package()])
        self.assertEqual(self.stats.packages['test.widget'][1],'widget-v2')

    def test_feed_schema_and_size_are_bounded(self):
        for value in (b'x'*(1024*1024+1),b'{}',b'not json',json.dumps(dict(feed(),schemaVersion=True)).encode()):
            with patch.object(package_stats,'urlopen',return_value=io.BytesIO(value)),self.assertRaises(ValueError):package_stats.published_counts()

    def test_protected_bounded_endpoint(self):
        client=server.app.test_client();headers={'Host':'127.0.0.1:8741','X-Studio-Token':server.SESSION_TOKEN}
        self.assertEqual(client.get('/api/store/stats?ids=test.widget',headers={'Host':headers['Host']}).status_code,403)
        with patch.object(server.store,'stats',self.stats),patch.object(package_stats.threading,'Thread'):
            self.assertEqual(client.get('/api/store/stats?ids=test.widget',headers=headers).status_code,200)
            self.assertEqual(client.get('/api/store/stats?ids='+','.join(['test.widget']*13),headers=headers).status_code,400)
            self.assertEqual(client.get('/api/store/stats?ids=https://evil.example',headers=headers).status_code,400)
