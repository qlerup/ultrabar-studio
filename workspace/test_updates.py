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
