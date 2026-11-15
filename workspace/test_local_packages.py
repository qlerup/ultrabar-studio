import copy,json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import Mock,patch
import server,store
from local_packages import read_folder
from test_store import fixture,icon_fixture


class LocalPackagesTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.folder=self.root/'test-package';self.folder.mkdir()
        self.p,self.raw=fixture();icon,self.icon_raw=icon_fixture()
        (self.folder/'plugin.json').write_bytes(self.raw);(self.folder/'icon.png').write_bytes(self.icon_raw)
        self.data=patch.object(server,'DATA_DIR',self.root/'data');self.data.start();self.addCleanup(self.data.stop)
        self.service=store.Store(server)
    def test_folder_without_manifest_can_be_previewed(self):
        p,raw,icon=read_folder(server,self.folder)
        self.assertTrue(p['id'].startswith('local.'));self.assertEqual(p['origin'],'local')
        self.assertEqual(raw,self.raw);self.assertEqual(icon,self.icon_raw)
        self.assertNotIn('publisher',p)
    def test_same_named_folders_have_distinct_stable_ids(self):
        other=self.root/'another-project'/self.folder.name;other.mkdir(parents=True)
        for name in ('plugin.json','icon.png'):(other/name).write_bytes((self.folder/name).read_bytes())
        first=read_folder(server,self.folder)[0]['id'];second=read_folder(server,other)[0]['id']
        self.assertNotEqual(first,second);self.assertEqual(first,read_folder(server,self.folder)[0]['id'])
    def test_offline_install_has_separate_identity_and_preserves_store_install(self):
        (self.folder/'manifest.json').write_text(json.dumps(self.p))
        p,raw,_=read_folder(server,self.folder)
        approved=dict(id=self.p['id'],version='1.0.0',type='studio-plugin',widgets=[dict(name='Approved',kind='clock')])
        self.service.save({self.p['id']+':pc':approved});self.service.job=dict(state='running')
        with patch.object(store,'catalog',side_effect=AssertionError('No catalog needed')),patch.object(store,'fetch',side_effect=AssertionError('No download needed')),patch.object(server,'adb') as adb:
            self.service.install({},local=(p,raw));adb.assert_not_called()
        self.assertEqual(self.service.status()['state'],'complete')
        records=self.service.records();self.assertEqual(records[self.p['id']+':pc'],approved)
        self.assertEqual(records['local.'+self.p['id']+':pc']['origin'],'local')
        self.assertEqual(len(self.service.templates()),2)
    def test_preview_cancel_expiry_and_token_binding(self):
        with patch.object(server,'package_folder_picker',Mock(return_value=None),create=True):self.assertTrue(self.service.preview_local()['cancelled'])
        with patch.object(server,'package_folder_picker',Mock(return_value=[str(self.folder)]),create=True):preview=self.service.preview_local()
        self.assertNotIn('path',preview)
        with self.assertRaisesRegex(store.StoreError,'expired'):self.service.start_local(dict(token='wrong'))
        token,expiry,p,raw=self.service.local_pending;self.service.local_pending=(token,time.monotonic()-1,p,raw)
        with self.assertRaisesRegex(store.StoreError,'expired'):self.service.start_local(dict(token=token))
    def test_preview_snapshots_content_and_requires_explicit_install(self):
        with patch.object(server,'package_folder_picker',Mock(return_value=[str(self.folder)]),create=True):preview=self.service.preview_local()
        self.assertEqual(self.service.records(),{})
        (self.folder/'plugin.json').write_bytes(b'changed after preview')
        with patch.object(store.threading,'Thread') as thread:
            self.service.start_local(dict(token=preview['token']))
            args=thread.call_args.kwargs['args'];self.assertEqual(args[1][1],self.raw)
        with self.assertRaises(store.StoreError):self.service.start_local(dict(token=preview['token']))
    def test_manifest_hash_mismatch_scripts_and_invalid_icon_rejected(self):
        p=copy.deepcopy(self.p);p['artifact']['sha256']='a'*64
        (self.folder/'manifest.json').write_text(json.dumps(p))
        with self.assertRaisesRegex(store.StoreError,'checksum'):read_folder(server,self.folder)
        (self.folder/'manifest.json').unlink();(self.folder/'plugin.json').write_text('{"pluginApi":1,"widgets":[{"name":"x","kind":"clock","script":"bad"}]}')
        with self.assertRaises(store.StoreError):read_folder(server,self.folder)
        (self.folder/'plugin.json').write_bytes(self.raw);(self.folder/'icon.png').write_bytes(b'not png')
        with self.assertRaises(store.StoreError):read_folder(server,self.folder)
    def test_apk_requires_manifest_and_inspection_before_install(self):
        (self.folder/'plugin.json').unlink();(self.folder/'app.apk').write_bytes(b'not apk')
        with self.assertRaisesRegex(store.StoreError,'manifest'):read_folder(server,self.folder)
    def test_protected_local_endpoints_and_no_picker_in_browser_mode(self):
        client=server.app.test_client()
        for path in ('/api/store/local/preview','/api/store/local/install'):
            self.assertEqual(client.post(path,headers={'Host':'127.0.0.1:8741'}).status_code,403)
        with patch.object(server,'package_folder_picker',None,create=True):
            with self.assertRaisesRegex(store.StoreError,'desktop'):self.service.preview_local()
