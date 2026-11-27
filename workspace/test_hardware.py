import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from bridge import CLIENT_ID, PairingRequired, Stream, read_token
from hardware import inventory


class HardwareTests(unittest.TestCase):
    def test_reset_reports_corebridge_approval_required(self):
        adb = Mock(return_value=b'cat: /data/user/0/com.ultrabar.hub/shared_prefs/my_prefs.xml: No such file or directory\n')
        result = inventory({}, '10.10.0.181:5555', adb, Path('.'))
        self.assertTrue(result['pairing_required'])
        self.assertEqual(result['devices'], [])

    def test_reads_only_the_approved_studio_client(self):
        adb = Mock(return_value=b'<map><string name="config">{"authorizationCodes":[]}</string></map>')
        with self.assertRaises(PairingRequired):
            read_token('10.10.0.181:5555', adb)
        adb.return_value = f'<map><string name="config">{{"authorizationCodes":[{{"clientId":"{CLIENT_ID}","code":"example"}}]}}</string></map>'.encode()
        self.assertEqual(read_token('10.10.0.181:5555', adb), 'example')

    @patch('bridge.uuid.uuid4', return_value='request')
    def test_pairing_waits_for_final_confirmation(self, _uuid):
        stream = Stream.__new__(Stream)
        stream.send = Mock()
        stream.receive = Mock(side_effect=[
            {'id': 'request', 'code': 200, 'data': {'state': 0}},
            {},
            {'id': 'request', 'code': 200, 'data': {'state': 1}},
        ])
        self.assertEqual(stream.query(101, {}), {'state': 1})
        self.assertEqual(stream.receive.call_count, 3)

    def test_live_membership_is_independent_of_profile_actions(self):
        data = {'profiles': [], 'configuration': {'canGateway': {'endpoints': [
            {'serialNumber': 'cube-a', 'productId': 'VIVO_CUBE'},
            {'serialNumber': 'stale', 'productId': 'KNOB_KEY'}]}}}
        with patch('hardware.read_online', return_value={'cube-a': True, 'new-cube': True, 'cube-off': False}):
            result = inventory(data, '10.10.0.181:5555', None, Path('.'))
        devices = {d['serial']: d for d in result['devices']}
        self.assertEqual(set(devices), {'cube-a', 'new-cube', 'cube-off'})
        self.assertEqual(devices['cube-a']['type'], 'VIVO_CUBE')
        self.assertTrue(devices['new-cube']['online'])
        self.assertFalse(devices['cube-off']['online'])

    def test_error_does_not_misrepresent_stored_inventory_as_live(self):
        data = {'configuration': {'canGateway': {'endpoints': [{'serialNumber': 'old'}]}}}
        with patch('hardware.read_online', side_effect=TimeoutError):
            result = inventory(data, '10.10.0.181:5555', None, Path('.'))
        self.assertEqual(result['devices'], [])
        self.assertIsNotNone(result['status_error'])
