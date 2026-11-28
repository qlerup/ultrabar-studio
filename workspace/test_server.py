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

    def test_core_pairing_uses_only_the_current_connection(self):
        target = '10.10.0.181:5555'
        with patch.dict(server.connection, {'target': target}), patch('bridge.pair') as pair:
            stale = self.client.post('/api/core/pair', json={'target': '10.10.0.180:5555'}, headers=self.headers)
            self.assertEqual(stale.status_code, 409)
            pair.assert_not_called()
            self.assertEqual(self.client.post('/api/core/pair', json={'target': target}, headers=self.headers).status_code, 200)
            pair.assert_called_once_with(target, server.adb, server.ROOT)

    def test_core_pairing_timeout_keeps_connection_available_for_retry(self):
        target = '10.10.0.181:5555'
        with patch.dict(server.connection, {'target': target}), patch('bridge.pair', side_effect=[TimeoutError, None]):
            self.assertEqual(self.client.post('/api/core/pair', json={'target': target}, headers=self.headers).status_code, 409)
            self.assertEqual(self.client.post('/api/core/pair', json={'target': target}, headers=self.headers).status_code, 200)

    def test_module_registration_writes_only_selected_live_modules_and_reads_back(self):
        target, device_id = '10.10.0.181:5555', 'core-id'
        serial = '0000000000000001'
        snapshot = {'device_id': device_id}
        module = dict(serial=serial, name='VivoCube', type='VIVO_CUBE', interface='can', net_id=98, work_mode=1, online=True)
        configuration = {'meshGateway': {'endpoints': []}}
        raw = b'<map><string name="app_data">{"profiles":[],"configuration":{"meshGateway":{"endpoints":[]}}}</string></map>'
        state = dict(profiles=[], configuration=configuration)

        def write(_target, _adb, _root, command, updated):
            self.assertEqual(command, 30300)
            self.assertEqual(updated['meshGateway'], configuration['meshGateway'])
            self.assertEqual(next(server.DATA_DIR.glob('backups/*.xml')).read_bytes(), raw)
            state['configuration'] = updated

        with tempfile.TemporaryDirectory() as folder, patch.object(server, 'DATA_DIR', Path(folder)), \
                patch.dict(server.connection, target=target, snapshot=snapshot), \
                patch.object(server, 'adb', side_effect=lambda *args, **kwargs: raw if kwargs.get('binary') else device_id), \
                patch.object(server, 'parse_profiles', side_effect=lambda _:state), \
                patch.object(server.module_discovery, 'recent', return_value=[module]), \
                patch('hardware.read_online', return_value={}), patch('bridge.request', side_effect=write) as bridge:
            response = self.client.post('/api/modules/register', headers=self.headers,
                                        json=dict(device_id=device_id, serials=[serial]))
            self.assertEqual(response.status_code, 200, response.json)
            self.assertEqual(response.json['hardware']['devices'][0]['serial'], serial)
            self.assertIsNone(response.json['hardware']['devices'][0]['online'])
            self.assertEqual(response.json['hardware']['available'], [])
            repeated = self.client.post('/api/modules/register', headers=self.headers,
                                        json=dict(device_id=device_id, serials=[serial]))
            self.assertEqual(repeated.status_code, 200)
            bridge.assert_called_once()

    def test_hardware_poll_never_starts_discovery_until_requested(self):
        target, device_id = '10.10.0.181:5555', 'core-id'
        raw = b'<map><string name="app_data">{"profiles":[]}</string></map>'
        with patch.dict(server.connection, target=target, snapshot={'device_id': device_id}), \
                patch.object(server, 'adb', side_effect=lambda *args, **kwargs: raw if kwargs.get('binary') else ''), \
                patch('hardware.read_online', return_value={}), patch('bridge.read_token'), \
                patch.object(server.module_discovery, 'start') as start:
            self.assertEqual(self.client.get('/api/hardware', headers=self.headers).status_code, 200)
            start.assert_not_called()
            self.assertEqual(self.client.post('/api/modules/scan', headers=self.headers).status_code, 200)
            start.assert_called_once_with((device_id, target), target, server.adb, server.ROOT)

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
