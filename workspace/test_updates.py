import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
import updates
import server

class UpdateTests(unittest.TestCase):
    def check(self, version, **extra):
        release = dict(tag_name=version, draft=False, prerelease=False, assets=[])
        release.update(extra)
        with patch.object(updates, 'urlopen', return_value=io.BytesIO(json.dumps(release).encode())):
            return updates.check_latest()

    def test_numeric_versions_and_no_downgrades(self):
        self.assertTrue(self.check('v0.100.0')['update_available'])
        self.assertFalse(self.check('v'+updates.VERSION)['update_available'])
        self.assertFalse(self.check('v0.9.0')['update_available'])

    def test_installer_and_safe_release_url(self):
        data=self.check('v0.100.0', html_url='https://evil.example', assets=[dict(name='UltraBarStudio-Setup-0.100.0.exe',state='uploaded')])
        self.assertTrue(data['installer_available'])
        self.assertEqual(data['release_url'],updates.RELEASES_URL+'/tag/v0.100.0')
        self.assertFalse(self.check('v0.100.0')['installer_available'])

    def test_bad_or_unstable_release(self):
        for tag in ['v1.2.3-beta',None,'../../evil','1.2']:
            with self.assertRaises(updates.UpdateError):self.check(tag)
        with self.assertRaises(updates.UpdateError):self.check('v1.0.0',prerelease=True)
        with patch.object(updates,'urlopen',return_value=io.BytesIO(b'not json')):
            with self.assertRaises(updates.UpdateError):updates.check_latest()

    def test_release_notes_come_from_latest_release(self):
        notes = 'New features\n\n- Remembers CoreBAR.\n- Start with Windows.'
        self.assertEqual(self.check('v0.100.0', body=notes)['release_notes'], notes)
        for value in [None, {}, 123, '']:
            self.assertEqual(self.check('v0.100.0', body=value)['release_notes'], '')

    def test_network_failures(self):
        for error in [URLError('offline'),TimeoutError(),HTTPError('url',404,'missing',{},None),HTTPError('url',403,'limited',{},None)]:
            with patch.object(updates,'urlopen',side_effect=error):
                with self.assertRaises(updates.UpdateError):updates.check_latest()

    def test_release_asset_feed_avoids_rest_api_and_preserves_verified_metadata(self):
        release=dict(tag_name='v99.0.0',draft=False,prerelease=False,
                     assets=[dict(name='UltraBarStudio-Setup-99.0.0.exe',state='uploaded',size=123,digest='sha256:'+'a'*64)])
        with patch.object(updates,'urlopen',return_value=io.BytesIO(json.dumps(release).encode())) as fetch:
            result=updates.check_latest()
        self.assertTrue(result['download_available'])
        self.assertEqual(result['sha256'],'a'*64)
        self.assertEqual(fetch.call_count,1)
        self.assertEqual(fetch.call_args.args[0].full_url,updates.RELEASE_FEED_URL)

    def test_missing_or_limited_feed_never_falls_back_to_rest_api(self):
        for status in (404,403,429):
            with patch.object(updates,'urlopen',side_effect=HTTPError('url',status,'unavailable',{},None)) as fetch:
                with self.assertRaises(updates.UpdateError):updates.check_latest()
            self.assertEqual(fetch.call_count,1)
            self.assertEqual(fetch.call_args.args[0].full_url,updates.RELEASE_FEED_URL)

    def test_concurrent_checks_share_one_request(self):
        import concurrent.futures,threading
        barrier=threading.Barrier(9);entered=threading.Event();release=threading.Event()
        checker=updates.ReleaseChecker()
        def fetch():
            entered.set()
            if not release.wait(3):raise AssertionError('Test request was not released')
            return dict(latest_version='99.0.0')
        def check():
            barrier.wait(timeout=3);return checker.check()
        with patch.object(updates,'check_latest',side_effect=fetch) as network,concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            pending=[pool.submit(check) for _ in range(8)]
            barrier.wait(timeout=3)
            try:self.assertTrue(entered.wait(3))
            finally:release.set()
            self.assertEqual([f.result(timeout=3)['latest_version'] for f in pending],['99.0.0']*8)
            self.assertEqual(network.call_count,1)

    def test_download_reuses_cached_check_and_verifies_installer(self):
        import tempfile,hashlib
        from pathlib import Path
        raw=b'MZ-verified-installer'
        info=dict(update_available=True,download_available=True,latest_version='99.0.0',download_url='https://github.com/qlerup/ultrabar-studio/releases/download/v99.0.0/UltraBarStudio-Setup-99.0.0.exe',size=len(raw),sha256=hashlib.sha256(raw).hexdigest())
        checker=updates.ReleaseChecker()
        with tempfile.TemporaryDirectory() as tmp,patch.object(updates,'check_latest',return_value=info) as metadata,patch.object(updates,'build_opener') as opener:
            checker.check();checker.check()
            opener.return_value.open.return_value=io.BytesIO(raw)
            downloader=updates.Updater(checker.check);downloader.download(Path(tmp))
            self.assertEqual(downloader.status()['state'],'ready')
            self.assertEqual(metadata.call_count,1)
            self.assertEqual(downloader.path.read_bytes(),raw)

    def test_release_build_generates_matching_feed_and_checksum(self):
        import tempfile,hashlib
        from pathlib import Path
        import make_update_feed
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'release').mkdir()
            installer=root/'release'/f'UltraBarStudio-Setup-{updates.VERSION}.exe';installer.write_bytes(b'MZ-release-test')
            (root/'README.md').write_text('# Studio\n\n## Current update\n\nCurrent notes.\n\n## Previous update\nOld notes.',encoding='utf-8')
            with patch.object(make_update_feed,'__file__',str(root/'make_update_feed.py')):make_update_feed.main()
            feed=json.loads((root/'release/studio-update.json').read_text())
            self.assertEqual(feed['tag_name'],'v'+updates.VERSION)
            self.assertEqual(feed['assets'][0]['digest'],'sha256:'+hashlib.sha256(installer.read_bytes()).hexdigest())
            self.assertEqual(feed['assets'][0]['size'],installer.stat().st_size)
            self.assertIn('Current notes.',feed['body']);self.assertNotIn('Old notes.',feed['body'])

    def test_cached_checks_coalesce_then_expire_and_back_off_on_failure(self):
        checker=updates.ReleaseChecker()
        with patch.object(updates.time,'monotonic',return_value=0) as clock,patch.object(updates,'check_latest',return_value=dict(latest_version='99.0.0')) as fetch:
            self.assertEqual(checker.check()['latest_version'],'99.0.0')
            checker.check()['latest_version']='tampered'
            self.assertEqual(checker.check()['latest_version'],'99.0.0');self.assertEqual(fetch.call_count,1)
            clock.return_value=301;fetch.side_effect=updates.UpdateError('Rate limited')
            for _ in range(3):
                with self.assertRaisesRegex(updates.UpdateError,'Rate limited'):checker.check()
            self.assertEqual(fetch.call_count,2)
            clock.return_value=362;fetch.side_effect=None
            self.assertEqual(checker.check()['latest_version'],'99.0.0');self.assertEqual(fetch.call_count,3)

    def test_protected_api_and_browser_destination(self):
        client=server.app.test_client()
        headers={'Host':'127.0.0.1:8741','X-Studio-Token':server.SESSION_TOKEN}
        self.assertEqual(client.get('/api/updates',headers={'Host':'127.0.0.1:8741'}).status_code,403)
        with patch.object(server,'release_checker',updates.ReleaseChecker()),patch.object(updates,'check_latest',side_effect=updates.UpdateError('Offline')):
            self.assertEqual(client.get('/api/updates',headers=headers).status_code,502)
        with patch.object(server.webbrowser,'open',return_value=True) as browser:
            self.assertEqual(client.post('/api/updates/open',json={'url':'https://evil.example'},headers=headers).status_code,200)
            browser.assert_called_once_with(updates.RELEASES_URL+'/latest')

class DownloadTests(unittest.TestCase):
    def test_download_verify_launch_and_keep_data(self):
        import tempfile,hashlib
        from pathlib import Path
        data=b'MZ-test-installer'
        release=dict(update_available=True,download_available=True,latest_version='99.0.0',download_url='https://github.com/qlerup/ultrabar-studio/releases/download/v99.0.0/UltraBarStudio-Setup-99.0.0.exe',size=len(data),sha256=hashlib.sha256(data).hexdigest())
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);saved=root/'draft.json';saved.write_text('keep me')
            updater=updates.Updater()
            with patch.object(updates,'check_latest',return_value=release),patch.object(updates,'build_opener') as opener:
                opener.return_value.open.return_value=io.BytesIO(data)
                updater.download(root/'updates')
            self.assertEqual(updater.status()['state'],'ready')
            with patch.object(updates.subprocess,'Popen') as launch:
                updater.launch();launch.assert_called_once()
                self.assertEqual(launch.call_args.args[0],[str(updater.path)])
            self.assertEqual(saved.read_text(),'keep me')
            updater.job['state']='ready';updater.path.write_bytes(b'tampered')
            with patch.object(updates.subprocess,'Popen') as launch:
                with self.assertRaises(updates.UpdateError):updater.launch()
                launch.assert_not_called()
    def test_corrupt_download_never_ready(self):
        import tempfile
        from pathlib import Path
        release=dict(update_available=True,download_available=True,latest_version='99.0.0',download_url='https://github.com/x',size=3,sha256='0'*64)
        with tempfile.TemporaryDirectory() as tmp,patch.object(updates,'check_latest',return_value=release),patch.object(updates,'build_opener') as opener:
            opener.return_value.open.return_value=io.BytesIO(b'bad')
            updater=updates.Updater();updater.download(Path(tmp))
            self.assertEqual(updater.status()['state'],'error')
            self.assertFalse(list(Path(tmp).iterdir()))
    def test_update_routes_require_token(self):
        client=server.app.test_client()
        for route in ['download','install']:
            self.assertEqual(client.post('/api/updates/'+route,headers={'Host':'127.0.0.1:8741'}).status_code,403)
    def test_redirect_rejects_untrusted_host(self):
        with self.assertRaises(updates.UpdateError):
            updates.ReleaseRedirect().redirect_request(None,None,302,'',{},'https://evil.example/installer.exe')


class UpdateHandoffTests(unittest.TestCase):
    def test_verified_installer_is_queued_before_any_process_launch(self):
        import tempfile,hashlib
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'setup.exe';path.write_bytes(b'test')
            u=updates.Updater();u.path=path;u.digest=hashlib.sha256(b'test').hexdigest();u.job={'state':'ready'}
            queued=[]
            with patch.object(updates.subprocess,'Popen') as launch:
                u.launch(queued.append)
                self.assertEqual(queued,[path]);launch.assert_not_called()
                self.assertEqual(u.status()['state'],'launched')
    def test_store_install_blocks_app_shutdown(self):
        client=server.app.test_client();headers={'Host':'127.0.0.1:8741','X-Studio-Token':server.SESSION_TOKEN}
        with patch.object(server.store,'status',return_value={'state':'running'}),patch.object(server.updater,'launch') as launch:
            self.assertEqual(client.post('/api/updates/install',headers=headers).status_code,409)
            launch.assert_not_called()
