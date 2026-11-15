import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

import server
import startup


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.client = server.app.test_client()
        self.headers = {'Host': '127.0.0.1:8741', 'X-Studio-Token': server.SESSION_TOKEN}

    def test_last_successful_connection_survives_restart_and_failed_attempt(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(server, 'DATA_DIR', Path(tmp)), patch.dict(server.connection):
            with patch.object(server, 'adb', return_value='connected to device'), patch.object(server, 'read_snapshot', return_value={'device_id': 'core'}):
                self.assertEqual(self.client.post('/api/connect', json={'target': '192.168.1.20'}, headers=self.headers).status_code, 200)
            server.connection.update(target=None, snapshot=None)
            self.assertEqual(self.client.get('/api/preferences', headers=self.headers).json['target'], '192.168.1.20:5555')
            with patch.object(server, 'adb', return_value='connection refused'):
                self.assertEqual(self.client.post('/api/connect', json={'target': '192.168.1.21'}, headers=self.headers).status_code, 502)
            self.assertEqual(json.loads((Path(tmp)/'preferences.json').read_text())['target'], '192.168.1.20:5555')

    def test_settings_validation_and_failure(self):
        with patch.object(startup, 'supported', return_value=True), patch.object(startup, 'set_enabled') as save:
            for body in [{}, {'start_with_windows': 'yes'}, {'start_with_windows': 1}, {'start_with_windows': True, 'extra': 1}]:
                self.assertEqual(self.client.post('/api/settings', json=body, headers=self.headers).status_code, 400)
            save.assert_not_called()
            with patch.object(startup, 'enabled', return_value=True):
                self.assertTrue(self.client.post('/api/settings', json={'start_with_windows': True}, headers=self.headers).json['start_with_windows'])
            save.side_effect = PermissionError()
            self.assertEqual(self.client.post('/api/settings', json={'start_with_windows': False}, headers=self.headers).status_code, 502)
        with patch.object(startup, 'supported', return_value=False), patch.object(startup, 'set_enabled') as save:
            self.assertEqual(self.client.post('/api/settings', json={'start_with_windows': True}, headers=self.headers).status_code, 409)
            save.assert_not_called()
        self.assertEqual(self.client.post('/api/settings', json={'start_with_windows': True}, headers={'Host': '127.0.0.1:8741'}).status_code, 403)

    def test_windows_startup_quotes_executable_and_removes_only_own_value(self):
        registry = MagicMock()
        with patch.object(startup, 'supported', return_value=True), patch.object(startup.sys, 'executable', r'C:\Program Files\Studio\UltraBar Studio.exe'), patch.dict('sys.modules', winreg=registry):
            startup.set_enabled(True)
            self.assertEqual(registry.SetValueEx.call_args.args[-1], '"C:\\Program Files\\Studio\\UltraBar Studio.exe"')
            startup.set_enabled(False)
            self.assertEqual(registry.DeleteValue.call_args.args[-1], 'UltraBar Studio')
            registry.DeleteKey.assert_not_called()
