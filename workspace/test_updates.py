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

    def test_network_failures(self):
        for error in [URLError('offline'),TimeoutError(),HTTPError('url',404,'missing',{},None),HTTPError('url',403,'limited',{},None)]:
            with patch.object(updates,'urlopen',side_effect=error):
                with self.assertRaises(updates.UpdateError):updates.check_latest()

    def test_protected_api_and_browser_destination(self):
        client=server.app.test_client()
        headers={'Host':'127.0.0.1:8741','X-Studio-Token':server.SESSION_TOKEN}
        self.assertEqual(client.get('/api/updates',headers={'Host':'127.0.0.1:8741'}).status_code,403)
        with patch.object(updates,'check_latest',side_effect=updates.UpdateError('Offline')):
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
