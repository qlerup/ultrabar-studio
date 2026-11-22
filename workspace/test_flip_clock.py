import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import flip_clock


class FlipClockTests(unittest.TestCase):
    def test_deploy_selects_clock_and_removal_restores_previous_selection(self):
        original = dict(uri='flip', featureEnabled=False, lockTime='TIME_5MIN', ver=0)
        state = dict(original)

        def bridge(target, adb, root, value=None):
            if value is not None:
                state.clear()
                state.update(value)
            return dict(state)

        with tempfile.TemporaryDirectory() as data:
            adb = Mock(side_effect=lambda *args: 'core' if 'ro.serialno' in args
                       else 'dk.qlerup.flipclock/.ClockActivity')
            server = SimpleNamespace(DATA_DIR=Path(data), ROOT=Path(data), adb=adb)
            with patch.object(flip_clock.bridge, 'screensaver', side_effect=bridge):
                flip_clock.reconcile(server, 'core:5555', 'core', True, '20')
                self.assertEqual(state, dict(original, uri=flip_clock.HOST, featureEnabled=True, lockTime='TIME_30S'))
                flip_clock.reconcile(server, 'core:5555', 'core', True, '20')
                state['lockTime'] = 'TIME_3MIN'
                flip_clock.reconcile(server, 'core:5555', 'core', False)
                self.assertEqual(state, dict(original, lockTime='TIME_3MIN'))

    def test_removal_preserves_a_manually_selected_screensaver(self):
        current = dict(uri='other', featureEnabled=True, lockTime='TIME_5MIN')
        previous = dict(uri='flip', featureEnabled=True)
        self.assertEqual(flip_clock.changed_settings(current, False, None, dict(previous=previous, appliedLockTime='TIME_30S')), current)

    def test_dismissal_rearms_lineos_once_on_the_same_core(self):
        clock = 'mResumedActivity: dk.qlerup.flipclock/.ClockActivity'
        home = 'mResumedActivity: com.ultrabar.launch/.HomeActivity'
        adb = Mock(side_effect=[clock, home, 'core', 'Broadcast completed', home])
        runtime = flip_clock.Runtime(SimpleNamespace(adb=adb))
        state = runtime.observe('core:5555', 'core', None)
        self.assertTrue(state)
        state = runtime.observe('core:5555', 'core', state)
        self.assertFalse(state)
        self.assertFalse(runtime.observe('core:5555', 'core', state))
        calls = [call for call in adb.call_args_list if 'broadcast' in call.args]
        self.assertEqual(len(calls), 1)
        self.assertIn('com.ultrabar.EXIT_SCREENSAVER', calls[0].args)
