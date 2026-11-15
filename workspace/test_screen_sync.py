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
        prepared=(b'private-config',b'certificate\r\nsecond line\r\n');stored={}
        def adb(*args,**kwargs):
            if 'dumpsys' in args:return 'Packages:\n userId=10123\n'
            if kwargs.get('input_data') is not None:
                raw=kwargs['input_data']
                stored['config.json' if 'config.json.tmp' in args[-1] else 'server.crt']=raw.replace(b'\r',b'') if 'shell' in args else raw
            if 'exec-out' in args:return stored[args[-1].split('/')[-1]]
            return ''
        self.server.adb.side_effect=adb
        screen_sync.configure(self.server,'core',prepared)
        calls=self.server.adb.call_args_list
        self.assertFalse(any('private-config' in str(c.args) or 'shared_prefs' in str(c.args) for c in calls))
        self.assertTrue(any('chmod 600' in str(c.args) for c in calls))
        self.assertTrue(all('exec-in' in c.args for c in calls if c.kwargs.get('input_data') is not None))
        self.assertIn('start',calls[-1].args)
    def test_binary_transfer_finishes_metadata_after_stdin_closed(self):
        files={}
        path='/data/user/0/'+screen_sync.PACKAGE_ID+'/files/server.crt'
        raw=b'certificate\r\nsecond line\r\n'
        def adb(*args,**kwargs):
            if kwargs.get('input_data') is not None:
                # Raw exec-in writes bytes but cannot finish a trailing shell chain.
                self.assertIn('exec-in',args)
                self.assertNotIn('&&',args[-1])
                files[path+'.tmp']=kwargs['input_data']
            elif 'shell' in args:
                self.assertIn('chmod 600',args[-1])
                self.assertIn('restorecon',args[-1])
                files[path]=files.pop(path+'.tmp')
            elif 'exec-out' in args:return files.get(path,b'')
            return ''
        self.server.adb.side_effect=adb
        self.assertTrue(screen_sync.write_private_file(self.server,'core',path,'10123',raw))
        self.assertEqual(files,{path:raw})

    def test_incomplete_write_does_not_launch(self):
        self.server.adb.side_effect=lambda *a,**kw:' userId=10123\n' if 'dumpsys' in a else b'wrong' if 'exec-out' in a else ''
        with self.assertRaisesRegex(store.StoreError,'verified'):screen_sync.configure(self.server,'core',(b'config',b'cert'))
        self.assertFalse(any('start' in c.args for c in self.server.adb.call_args_list))

    def test_background_settings_preserve_other_preferences_and_start_service(self):
        import re
        import xml.etree.ElementTree as ET
        stored={}
        def adb(*args,**kwargs):
            if 'dumpsys' in args:return ' userId=10123\n'
            if kwargs.get('input_data') is not None:
                path=re.search(r'cat > (\S+)\.tmp',args[-1]).group(1)
                stored[path]=kwargs['input_data']
            if 'exec-out' in args:return stored[args[-1]]
            if args[-1].startswith('if [ -f '):return '<map><string name="keep">existing value</string></map>'
            return 'Starting service'
        self.server.adb.side_effect=adb
        screen_sync.configure(self.server,'core',(b'private-config',b'cert'),settings=dict(enabled=True,wakeDelayMs=1750),background=True)
        prefs=ET.fromstring(stored['/data/user/0/'+screen_sync.PACKAGE_ID+'/shared_prefs/sync.xml'])
        self.assertEqual(prefs.find("./string[@name='keep']").text,'existing value')
        self.assertEqual(prefs.find("./boolean[@name='enabled']").get('value'),'true')
        self.assertEqual(prefs.find("./int[@name='wakeDelayMs']").get('value'),'1750')
        calls=self.server.adb.call_args_list
        self.assertTrue(all('exec-in' in c.args for c in calls if c.kwargs.get('input_data') is not None))
        self.assertIn('start-foreground-service',calls[-1].args)
        self.assertEqual(calls[-1].args[-1],'enable')
        self.assertFalse(any('.MainActivity' in str(c.args) for c in calls))
