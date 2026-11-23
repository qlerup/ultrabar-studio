import hashlib
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, call, patch

import core_notifications as notifications
import server


class CoreNotificationsTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.target = '192.168.1.10:5555'
        self.context = SimpleNamespace(ROOT=Path(folder.name), DeviceError=server.DeviceError, adb=Mock())
        self.apk = self.context.ROOT / 'assets' / notifications.APK_NAME
        self.apk.parent.mkdir()
        self.apk.write_bytes(b'bundled APK')
        self.digest = hashlib.sha256(self.apk.read_bytes()).hexdigest()
        self.package_path = '/data/app/dk.ultrabarx.notifications-aB_1==/base.apk'
        self.package_list = f'package:{self.package_path}={notifications.PACKAGE}'
        self.hash_line = f'{self.digest}  {self.package_path}'

    def test_installs_and_verifies_the_bundle_before_granting_overlay(self):
        self.context.adb.side_effect = ['', 'Performing Streamed Install\nSuccess',
                                        self.package_list, self.hash_line,
                                        'Result: Bundle[{status=overlay_unavailable}]', '',
                                        'Result: Bundle[{status=ready}]']
        notifications.provision(self.context, self.target)
        self.context.adb.assert_has_calls([
            call('-s', self.target, 'install', '-r', str(self.apk)),
            call('-s', self.target, 'shell', 'pm', 'list', 'packages', '-f', notifications.PACKAGE),
            call('-s', self.target, 'shell', 'sha256sum', self.package_path),
        ])
        self.assertIn(call('-s', self.target, 'shell', 'appops', 'set',
                           notifications.PACKAGE, 'SYSTEM_ALERT_WINDOW', 'allow'),
                      self.context.adb.call_args_list)

    def test_existing_ready_bundle_needs_no_install_or_permission_change(self):
        self.context.adb.side_effect = [self.package_list, self.hash_line,
                                        'Result: Bundle[{status=ready}]']
        notifications.provision(self.context, self.target)
        self.assertEqual(self.context.adb.call_count, 3)

    def test_mismatched_bytes_never_receive_permission_or_test_call(self):
        different = ('a' * 64) + '  ' + self.package_path
        self.context.adb.side_effect = [self.package_list, different, 'Success',
                                        self.package_list, different]
        with self.assertRaisesRegex(server.DeviceError, 'Could not install'):
            notifications.provision(self.context, self.target)
        self.assertEqual(self.context.adb.call_count, 5)
        self.context.adb.reset_mock()
        self.context.adb.side_effect = [self.package_list, different]
        with self.assertRaisesRegex(server.DeviceError, 'Deploy to Core'):
            notifications.test_banner(self.context, self.target)
        self.assertEqual(self.context.adb.call_count, 2)

    def test_test_banner_checks_device_and_reports_status(self):
        path = '/api/editor/core-notifications/test'
        headers = {'Host': '127.0.0.1:8741', 'X-Studio-Token': server.SESSION_TOKEN}
        client = server.app.test_client()
        with patch.dict(server.connection, snapshot={'device_id': 'core'}, target=self.target), \
                patch.object(notifications, 'test_banner') as test:
            self.assertEqual(client.post(path, headers=headers, json={'device_id': 'other'}).status_code, 400)
            test.assert_not_called()
            self.assertEqual(client.post(path, headers=headers, json={'device_id': 'core'}).status_code, 200)
            test.assert_called_once_with(server, self.target, 'silent', None)
            test.reset_mock()
            self.assertEqual(client.post(path, headers=headers, json={'device_id': 'core', 'sound': 'error', 'volume': 50}).status_code, 200)
            test.assert_called_once_with(server, self.target, 'error', 50)
            self.assertEqual(client.post(path, headers=headers, json={'device_id': 'core', 'sound': 'unknown'}).status_code, 400)
            for invalid in (-1, 101, True, '50'):
                self.assertEqual(client.post(path, headers=headers,
                    json={'device_id': 'core', 'volume': invalid}).status_code, 400)
            self.assertEqual(test.call_count, 1)
        self.context.adb.side_effect = [self.package_list, self.hash_line,
                                        'Result: Bundle[{status=screen_off}]']
        with self.assertRaisesRegex(server.DeviceError, 'Wake the Core screen'):
            notifications.test_banner(self.context, self.target)

    def test_selected_sound_is_passed_as_a_test_argument(self):
        self.context.adb.side_effect = [self.package_list, self.hash_line,
                                        'Result: Bundle[{status=accepted}]']
        notifications.test_banner(self.context, self.target, 'complete', 50)
        self.context.adb.assert_called_with('-s', self.target, 'shell', 'content', 'call',
                                            '--uri', notifications.AUTHORITY, '--method', 'test.v1',
                                            '--arg', 'complete:50')
