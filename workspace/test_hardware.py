import unittest
from pathlib import Path
from unittest.mock import patch
from hardware import inventory


class HardwareTests(unittest.TestCase):
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
