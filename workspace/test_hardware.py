import unittest
import threading
from pathlib import Path
from unittest.mock import Mock, patch
from bridge import CLIENT_ID, PairingRequired, Stream, read_token
from hardware import EXPIRED_SIGHTING, RECENT_SIGHTING, ModuleDiscovery, decode_can_modules, discover_attached, inventory, register_can_modules


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
            {'serialNumber': 'stale', 'productId': 'KNOB_KEY'},
            {'serialNumber': 'cube-off', 'productId': 'VIVO_CUBE'}]}}}
        with patch('hardware.read_online', return_value={'cube-a': True, 'new-cube': True, 'cube-off': False}):
            result = inventory(data, '10.10.0.181:5555', None, Path('.'))
        devices = {d['serial']: d for d in result['devices']}
        self.assertEqual(set(devices), {'cube-a', 'stale', 'cube-off'})
        self.assertEqual(devices['cube-a']['type'], 'VIVO_CUBE')
        self.assertIsNone(devices['stale']['online'])
        self.assertFalse(devices['cube-off']['online'])

    def test_error_does_not_misrepresent_stored_inventory_as_live(self):
        data = {'configuration': {'canGateway': {'endpoints': [{'serialNumber': 'old'}]}}}
        with patch('hardware.read_online', side_effect=TimeoutError):
            result = inventory(data, '10.10.0.181:5555', None, Path('.'))
        self.assertIsNone(result['devices'][0]['online'])
        self.assertIsNotNone(result['status_error'])

    @patch('hardware.Stream')
    def test_attached_can_module_is_detected_without_a_profile(self, stream_type):
        stream = stream_type.return_value.__enter__.return_value
        serial = '0000000000000001'
        frame = {'act': 30102, 'data': {'serialNumber': serial, 'productId': 268435459, 'interfaceType': 'can', 'netId': 98, 'workMode': 1}}
        cancelled = threading.Event()
        observed = {}

        def query(action, data, *, timeout, on_event):
            if action == 30100:
                on_event(frame)

        stream.query.side_effect = query
        def receive(_timeout):
            cancelled.set()
            return frame

        stream.receive.side_effect = receive
        discover_attached('10.10.0.181:5555', None, Path('.'),
                          lambda device: observed.update({device['serial']: dict(device, online=True)}), cancelled)
        with patch('hardware.read_online', return_value={}):
            result = inventory({'profiles': []}, '10.10.0.181:5555', None, Path('.'), discovered=observed.values())
        self.assertEqual(result['devices'], [])
        self.assertEqual(result['available'], [dict(serial=serial, type='VIVO_CUBE', name='VivoCube', online=True)])
        self.assertEqual([call.args[0] for call in stream.query.call_args_list], [30100, 30101])

    def test_discovery_keeps_late_and_missed_modules_by_core_until_they_expire(self):
        scanner = ModuleDiscovery()
        scanner.device = ('core-id', '10.10.0.181:5555')
        times = iter((100, 122))
        with patch('hardware.time.monotonic', side_effect=lambda: next(times)), patch('hardware.observe_can'), patch('hardware.discover_attached') as scan:
            def discover(_target, _adb, _root, observe, _cancelled):
                observe(dict(serial='cube', type='VIVO_CUBE'))
                observe(dict(serial='sense', type='SENSE_CUBE'))
            scan.side_effect = discover
            scanner.scan(scanner.device[1], None, Path('.'), scanner.cancelled)
        with patch('hardware.time.monotonic', return_value=123):
            self.assertEqual([device['serial'] for device in scanner.recent(scanner.device)], ['cube', 'sense'])
            self.assertEqual(scanner.recent(('different-core', scanner.device[1])), [])
        with patch('hardware.time.monotonic', return_value=100 + RECENT_SIGHTING):
            self.assertEqual([device['online'] for device in scanner.recent(scanner.device)], [None, True])
        with patch('hardware.time.monotonic', return_value=100 + EXPIRED_SIGHTING):
            self.assertEqual([device['serial'] for device in scanner.recent(scanner.device)], ['sense'])

    def test_passive_discovery_validates_headers_and_payloads_and_handles_reordered_frames(self):
        header = '<0x47c> [8] f0 7c 00 08 42 10 a0 5b'
        product = '<0x47c> [8] 10 00 00 01 00 00 00 7c'
        serial = '<0x47c> [8] 10 20 30 40 50 60 70 80'
        other_module = '<0x462> [8] 10 00 00 03 00 00 00 62'
        capture = '\n'.join((header, product, other_module, serial))
        self.assertEqual(list(decode_can_modules(capture)), [
            dict(serial='1020304050607080', type='DOT_KEY', name='DotKey', interface='can', net_id=124, work_mode=1),
        ])
        self.assertEqual(list(decode_can_modules(capture.replace('a0 5b', 'a0 5a'))), [])
        self.assertEqual(list(decode_can_modules(capture.replace('70 80', '70 81'))), [])
        self.assertEqual(list(decode_can_modules('\n'.join((header, serial)))), [])

    def test_manual_registration_preserves_both_gateways_and_rejects_address_conflicts(self):
        serial = '0000000000000002'
        configuration = dict(canGateway=dict(endpoints=[dict(serialNumber='0000000000000001', netId=124, uid='1')]),
                             meshGateway=dict(endpoints=[dict(serialNumber='0000000000000003', netId=98, uid='2')]))
        found = dict(serial=serial, name='VivoCube', type='VIVO_CUBE', interface='can', net_id=98, work_mode=1, online=True)
        updated = register_can_modules(configuration, [found], [serial])
        self.assertEqual(updated['canGateway']['endpoints'][-1], dict(serialNumber=serial, name='VivoCube',
                         productId='VIVO_CUBE', interfaceType='can', netId=98, workMode=1, uid='3'))
        self.assertEqual(updated['canGateway']['endpoints'][:-1], configuration['canGateway']['endpoints'])
        self.assertEqual(updated['meshGateway'], configuration['meshGateway'])
        self.assertEqual(register_can_modules(updated, [], [serial]), updated)
        with self.assertRaisesRegex(ValueError, 'same address'):
            register_can_modules(configuration, [dict(found, net_id=124)], [serial])
        with self.assertRaisesRegex(ValueError, 'Search again'):
            register_can_modules(configuration, [dict(found, online=None)], [serial])
