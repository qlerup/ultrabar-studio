import hashlib
import hmac
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
from urllib.error import HTTPError
from urllib.request import urlopen

import editor
import pc_standby
import server


class StandbyTests(unittest.TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.target = '192.168.1.10:5555'
        self.context = SimpleNamespace(DATA_DIR=Path(folder.name), validate_target=server.validate_target,
                                       connection={}, DeviceError=server.DeviceError, adb=Mock())
        self.standby = pc_standby.Standby(self.context)
        self.addCleanup(self.standby.close)
        self.key = bytes(range(32))
        self.pair = dict(target=self.target, key=self.key.hex())

    def test_loopback_api_signs_only_challenges_for_a_paired_core(self):
        editor.atomic_json(self.standby.path, {'core': self.pair})
        self.standby.start()
        pairing = hashlib.sha256(self.key).hexdigest()[:32]
        nonce = b'1' * 32
        base = f'http://127.0.0.1:{self.standby.http.server_port}'
        with urlopen(f'{base}/pc-standby/{pairing}/{nonce.hex()}', timeout=2) as reply:
            self.assertEqual(reply.read(), hmac.digest(self.key, nonce, 'sha256'))
        for route in ('/', f'/pc-standby/{"a" * 32}/{nonce.hex()}', f'/pc-standby/{pairing}/short'):
            with self.assertRaises(HTTPError) as response:
                urlopen(base + route, timeout=2)
            self.assertEqual(response.exception.code, 404)
            response.exception.close()

    def test_a_different_pc_pairing_cannot_be_replaced_or_disabled(self):
        editor.atomic_json(self.standby.path, {'core': self.pair})
        self.context.adb.side_effect = ['core', 'f' * 64, 'core', '0', 'f' * 64]
        self.standby.restore_route(self.target, 'core', self.pair['key'])
        self.standby.reconcile(self.target, 'core', False)
        self.assertEqual(self.standby.pairs(), {})
        self.assertEqual(self.context.adb.call_count, 5)
        self.assertFalse(any('broadcast' in call.args or 'reverse' in call.args
                             for call in self.context.adb.call_args_list))

    def test_background_or_visible_placement_enables_monitoring(self):
        app = {'id': pc_standby.PACKAGE_ID, 'type': 'APPS'}
        self.assertTrue(pc_standby.placed([{'homeData': [app]}], []))
        self.assertTrue(pc_standby.placed([], [app]))
        self.assertFalse(pc_standby.placed([{'homeData': [dict(app, type='PC_CONTROL')]}], []))
