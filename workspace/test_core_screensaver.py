import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import core_screensaver


class CoreScreensaverTests(unittest.TestCase):
    def test_selects_any_supported_service_and_restores_native_choice(self):
        clock = 'dk.qlerup.flipclock/dk.qlerup.flipclock.CoreScreensaverService'
        weather = 'dk.qlerup.weather/dk.qlerup.weather.CoreScreensaverService'
        other = 'com.example.reader/com.example.reader.ReaderService'
        native = dict(uri='flip', ver=0, lockTime='TIME_5MIN', featureEnabled=True)
        original = dict(native)
        secure = dict(enabled_accessibility_services=other, accessibility_enabled='1')

        def bridge(target, adb, root, value=None):
            if value is not None:
                native.clear()
                native.update(value)
            return dict(native)

        def adb(*args):
            if args[-1] == 'ro.serialno':
                return 'core'
            if args[-2:] == ('id', '-u'):
                return '0'
            if args[3:6] == ('dumpsys', 'activity', 'services'):
                return 'ServiceRecord{test u0 ' + args[-1] + '/.CoreScreensaverService}'
            operation, _, key = args[4:7]
            if operation == 'get':
                return secure.get(key, 'null')
            if operation == 'put':
                secure[key] = args[-1]
            elif operation == 'delete':
                secure.pop(key, None)

        with tempfile.TemporaryDirectory() as data:
            server = SimpleNamespace(DATA_DIR=Path(data), ROOT=Path(data), adb=adb)
            with patch.object(core_screensaver.bridge, 'screensaver', side_effect=bridge):
                core_screensaver.reconcile(server, 'core', 'core', clock)
                core_screensaver.activate(server, 'core', 'core', clock)
                self.assertEqual(secure['enabled_accessibility_services'], other + ':' + clock)
                self.assertEqual(native, dict(original, featureEnabled=False))
                core_screensaver.reconcile(server, 'core', 'core', weather)
                core_screensaver.activate(server, 'core', 'core', weather)
                self.assertEqual(secure['enabled_accessibility_services'], other + ':' + weather)
                core_screensaver.reconcile(server, 'core', 'core', None)
                self.assertEqual(secure['enabled_accessibility_services'], other)
                self.assertEqual(native, original)

    def test_service_component_must_belong_to_its_app(self):
        self.assertIsNotNone(core_screensaver.COMPONENT.fullmatch(
            'dk.qlerup.newclock/dk.qlerup.newclock.CoreScreensaverService'))
        self.assertIsNone(core_screensaver.COMPONENT.fullmatch(
            'dk.qlerup.newclock/com.android.settings.CoreScreensaverService'))
