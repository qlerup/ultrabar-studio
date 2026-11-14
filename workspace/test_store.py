import copy, hashlib, json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import server,store

def fixture():
    payload=json.dumps({'pluginApi':1,'widgets':[{'name':'Test clock','kind':'clock'}]}).encode()
    p=dict(schemaVersion=1,id='studio.test',name='Test presets',description='Test plugin',version='1.0.0',type='studio-plugin',license='Test',source='https://github.com/qlerup/ultrabar-store',compatibility=dict(minStudioVersion='0.18.0',hostApi=1),permissions=[],artifact=dict(url=store.ASSET_PREFIX+'test/test.json',size=len(payload),sha256=hashlib.sha256(payload).hexdigest()))
    return p,payload

class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.data=patch.object(server,'DATA_DIR',Path(self.tmp.name));self.data.start();self.addCleanup(self.data.stop)
        self.service=store.Store(server)
    def install(self,p,payload,**overrides):
        def fetch(url,limit,destination=None):
            destination.write(payload);return len(payload)
        self.service.job={'state':'running'}
        body=dict(id=p['id'],version=p['version'],sha256=p['artifact']['sha256']);body.update(overrides)
        with patch.object(store,'catalog',return_value=[p]),patch.object(store,'fetch',side_effect=fetch):self.service.install(body)
        return self.service.status()
    def test_install_and_remove_declarative_plugin(self):
        p,raw=fixture();self.assertEqual(self.install(p,raw)['state'],'complete')
        self.assertEqual(self.service.templates()[0]['name'],'Test clock')
        self.service.remove_plugin(p['id']);self.assertEqual(self.service.templates(),[])
    def test_integrity_failure_leaves_previous_installation(self):
        p,raw=fixture();self.install(p,raw);before=self.service.records()
        self.assertEqual(self.install(p,b'wrong bytes')['state'],'error')
        self.assertEqual(self.service.records(),before)
    def test_catalog_change_requires_review_again(self):
        p,raw=fixture();self.assertEqual(self.install(p,raw,version='9.0.0')['state'],'error');self.assertEqual(self.service.records(),{})
    def test_future_host_api_and_no_downgrade(self):
        p,raw=fixture();p['compatibility']['hostApi']=2;self.assertEqual(self.install(p,raw)['state'],'error')
        p['compatibility']['hostApi']=1;p['version']='2.0.0';self.install(p,raw)
        p['version']='1.0.0';self.assertEqual(self.install(p,raw)['state'],'error')
    def test_untrusted_artifacts_and_corrupt_catalog(self):
        p,_=fixture()
        for url in ['http://github.com/qlerup/ultrabar-store/releases/download/a/a.apk','https://evil.example/a.apk',store.ASSET_PREFIX+'../a.apk',store.ASSET_PREFIX+'a/a.apk?x=1']:
            q=copy.deepcopy(p);q['artifact']['url']=url
            with self.assertRaises(store.StoreError):store.validate_entry(q)
        with patch.object(store,'fetch',return_value=b'{"schemaVersion":2,"packages":[]}'):
            with self.assertRaises(store.StoreError):store.catalog()
    def test_presets_cannot_execute_code(self):
        for widget in [{'name':'x','kind':'clock','script':'evil()'},{'name':'x','kind':'shell'},{'name':'x','kind':'clock','background':'url(evil)'}]:
            with self.assertRaises(store.StoreError):store.plugin_templates(json.dumps(dict(pluginApi=1,widgets=[widget])).encode())
    def test_protected_endpoints(self):
        client=server.app.test_client()
        for method,path in [('get','/api/store'),('post','/api/store/install')]:
            self.assertEqual(getattr(client,method)(path,headers={'Host':'127.0.0.1:8741'}).status_code,403)
    def test_core_identity_is_checked_before_adb_install(self):
        from types import SimpleNamespace
        p,raw=fixture();p.update(type='corebar-app',android=dict(packageId='dk.test.clock',versionCode=1,minSdk=26,signerSha256='a'*64))
        p['compatibility'].update(models=['CB01'],abis=['armeabi-v7a'])
        def adb(*args,**kw):
            if args[-1]=='ro.serialno':return 'actual-core'
            if args[-1]=='ro.product.cpu.abi':return 'armeabi-v7a'
            if args[-1]=='ro.build.version.sdk':return '29'
            return 'Packages:\n versionCode=1'
        with patch.dict(server.connection,target='10.0.0.2:5555',snapshot=dict(device_id='expected-core',model='CB01')),patch.object(server,'adb',side_effect=adb),patch.object(store,'inspect_apk'),patch.object(store.subprocess,'run') as install:
            self.assertEqual(self.install(p,raw,device_id='expected-core')['state'],'error')
            install.assert_not_called()
        with patch.dict(server.connection,target='10.0.0.2:5555',snapshot=dict(device_id='actual-core',model='CB01')),patch.object(server,'adb',side_effect=adb),patch.object(store,'inspect_apk'),patch.object(store.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout=b'Success')) as install:
            self.assertEqual(self.install(p,raw,device_id='actual-core')['state'],'complete')
            self.assertIn('dk.test.clock',[x['android']['packageId'] for x in self.service.records().values()])
            args=install.call_args.args[0];self.assertIn('-r',args);self.assertNotIn('-d',args)

    def test_apk_signature_parser_rejects_invalid_input(self):
        p=Path(self.tmp.name)/'bad.apk';p.write_bytes(b'not an APK')
        with self.assertRaises(store.StoreError):store.v2_signers(p)
