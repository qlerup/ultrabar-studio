import json, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import screen_sync, store

class ScreenSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name);(root/'assets').mkdir();(root/'assets/corebridge.crt').write_bytes(b'certificate')
        self.entry=dict(id='studio.vivo.screensync',type='corebar-app',android=dict(packageId=screen_sync.PACKAGE_ID,signerSha256=screen_sync.SIGNER))
        self.server=SimpleNamespace(ROOT=root,adb=Mock(),read_snapshot=Mock(return_value=dict(hardware=dict(devices=[
            dict(type='VIVO_CUBE',serial='cube-one',online=True),dict(type='SENSE_CUBE',serial='not-vivo',online=True),dict(type='VIVO_CUBE',serial='offline',online=False)]))))
    def test_config_uses_only_connected_vivos_and_never_command_arguments(self):
        credential=b'<map><string name="config">{"authorizationCodes":[{"clientId":"ultrabarx-profile-inspection","code":"private-test-credential"}]}</string></map>'
        self.server.adb.side_effect=['0',credential]
        config,cert=screen_sync.prepare(self.server,'core',self.entry)
        self.assertEqual(json.loads(config),dict(token='private-test-credential',serials=['cube-one']))
        self.assertEqual(cert,b'certificate')
        self.assertNotIn('private-test-credential',str(self.server.adb.call_args_list))
    def test_wrong_identity_rejected_before_device_access(self):
        self.entry['android']['signerSha256']='a'*64
        with self.assertRaises(store.StoreError):screen_sync.prepare(self.server,'core',self.entry)
        self.server.adb.assert_not_called()
    def test_missing_root_or_vivos_stops_before_install(self):
        self.server.adb.return_value='2000'
        with self.assertRaisesRegex(store.StoreError,'root'):screen_sync.prepare(self.server,'core',self.entry)
        self.server.adb.return_value='0';self.server.read_snapshot.return_value={}
        with self.assertRaisesRegex(store.StoreError,'VivoCube'):screen_sync.prepare(self.server,'core',self.entry)
    def test_private_setup_verified_and_preferences_untouched(self):
        prepared=(b'private-config',b'certificate');stored={}
        def adb(*args,**kwargs):
            if 'dumpsys' in args:return 'Packages:\n userId=10123\n'
            if kwargs.get('input_data') is not None:stored['config.json' if 'config.json.tmp' in args[-1] else 'server.crt']=kwargs['input_data']
            if 'exec-out' in args:return stored[args[-1].split('/')[-1]]
            return ''
        self.server.adb.side_effect=adb
        screen_sync.configure(self.server,'core',prepared)
        calls=self.server.adb.call_args_list
        self.assertFalse(any('private-config' in str(c.args) or 'shared_prefs' in str(c.args) for c in calls))
        self.assertTrue(any('chmod 600' in str(c.args) for c in calls))
        self.assertIn('start',calls[-1].args)
    def test_incomplete_write_does_not_launch(self):
        self.server.adb.side_effect=lambda *a,**kw:' userId=10123\n' if 'dumpsys' in a else b'wrong' if 'exec-out' in a else ''
        with self.assertRaisesRegex(store.StoreError,'verified'):screen_sync.configure(self.server,'core',(b'config',b'cert'))
        self.assertFalse(any('start' in c.args for c in self.server.adb.call_args_list))
