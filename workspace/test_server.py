import unittest
import tempfile
import json
from pathlib import Path
from unittest.mock import patch

import server


class StudioTests(unittest.TestCase):
    def setUp(self):
        self.client = server.app.test_client()
        self.headers = {'Host': '127.0.0.1:8741', 'X-Studio-Token': server.SESSION_TOKEN}

    def test_target_rejects_shell_injection_and_public_addresses(self):
        for value in ['8.8.8.8', '127.0.0.1', '0.0.0.0', '10.10.0.181;reboot', '-s', '10.10.0.181:0', '10.10.0.181:65536', None]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                server.validate_target(value)
        self.assertEqual(server.validate_target('10.10.0.181'), '10.10.0.181:5555')

    def test_corrupt_profile_never_becomes_empty_valid_profile(self):
        for raw in [b'<map/>', b'not xml', b'<map><string name="app_data">{"profiles":null}</string></map>']:
            with self.assertRaises(server.DeviceError):
                server.parse_profiles(raw)

    def test_read_preserves_unknown_fields(self):
        data = server.parse_profiles(b'<map><string name="app_data">{"profiles":[{"module":[],"future":{"keep":true}}]}</string></map>')
        self.assertEqual(data['profiles'][0]['future'], {'keep': True})

    def test_api_requires_token_and_trusted_host(self):
        self.assertEqual(self.client.post('/api/connect', headers={'Host': '127.0.0.1:8741'}).status_code, 403)
        self.assertEqual(self.client.get('/', headers={'Host': 'attacker.example'}).status_code, 403)

    def test_invalid_target_does_not_invoke_adb(self):
        with patch.object(server, 'adb') as adb:
            response = self.client.post('/api/connect', json={'target': 'public.example'}, headers=self.headers)
            self.assertEqual(response.status_code, 400)
            adb.assert_not_called()

    def test_failed_connect_keeps_previous_snapshot(self):
        old = dict(server.connection)
        try:
            server.connection.update(target='10.10.0.180:5555', snapshot={'profiles': []})
            with patch.object(server, 'adb', return_value='cannot connect: refused'):
                response = self.client.post('/api/connect', json={'target': '10.10.0.181'}, headers=self.headers)
            self.assertEqual(response.status_code, 502)
            self.assertEqual(server.connection['target'], '10.10.0.180:5555')
        finally:
            server.connection.update(old)

    def test_layout_is_local_persistent_and_independent_of_ip(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(server, 'DATA_DIR', Path(folder)), patch.dict(server.connection, {'snapshot': {'device_id': 'core-serial'}, 'target': '10.10.0.181:5555'}), patch.object(server, 'adb') as adb:
            order = ['0000019F2F1D2913', 'core', '0000019FD6D46D08']
            response = self.client.post('/api/layout', json={'device_id': 'core-serial', 'order': order}, headers=self.headers)
            self.assertEqual(response.status_code, 200)
            server.connection['target'] = '10.10.0.190:5555'
            self.assertEqual(server.read_layouts()['core-serial'], order)
            self.assertEqual(json.loads((Path(folder)/'layouts.json').read_text())['core-serial'], order)
            adb.assert_not_called()

    def test_layout_rejects_duplicates_and_wrong_device(self):
        with patch.dict(server.connection, {'snapshot': {'device_id': 'core-serial'}}):
            for order in [['core', 'core'], ['not-a-serial', 'core'], [], ['0000019F2F1D2913']]:
                response = self.client.post('/api/layout', json={'device_id': 'core-serial', 'order': order}, headers=self.headers)
                self.assertEqual(response.status_code, 400)
            response = self.client.post('/api/layout', json={'device_id': 'other', 'order': ['core']}, headers=self.headers)
            self.assertEqual(response.status_code, 409)


    def test_screen_reports_off_without_waking_device(self):
        png = b'\x89PNG\r\n\x1a\nexample'
        with patch.dict(server.connection, {'target': '10.10.0.181:5555'}), patch.object(server, 'adb', side_effect=[png, 'Display Power: state=OFF']) as adb:
            response = self.client.get('/api/screen', headers=self.headers)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data, png)
            self.assertEqual(response.headers['X-Core-Screen-State'], 'OFF')
            self.assertEqual(adb.call_count, 2)
            self.assertEqual(adb.call_args.args[2:], ('shell', 'dumpsys', 'power'))

    def test_screen_rejects_non_image_and_tolerates_unknown_power(self):
        with patch.dict(server.connection, {'target': '10.10.0.181:5555'}), patch.object(server, 'adb', side_effect=[b'error', '']):
            self.assertEqual(self.client.get('/api/screen', headers=self.headers).status_code, 502)
        with patch.dict(server.connection, {'target': '10.10.0.181:5555'}), patch.object(server, 'adb', side_effect=[b'\x89PNG\r\n\x1a\nexample', server.DeviceError('Unavailable')]):
            response = self.client.get('/api/screen', headers=self.headers)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers['X-Core-Screen-State'], 'UNKNOWN')


if __name__ == '__main__':
    unittest.main()
