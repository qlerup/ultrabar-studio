import copy,json,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
import bundle_contract,store,server
from test_deferred_apps import DeferredAppTests
from test_editor import profiles

def descriptor():return dict(widgetApi=1,runtime='studio-native-v1',widgets=[dict(id='bambu-liquid',name='Bambu',kind='bambu')])

class BundleContractTests(unittest.TestCase):
    def test_strict_types_version_fixed_companion_and_embedded_descriptor(self):
        base=dict(type='corebar-app',android=dict(packageId='dk.ultrabar.bambu'),compatibility=dict(minStudioVersion='0.46.0'),bundledWidgets=descriptor())
        self.assertEqual(bundle_contract.validate(base,store.widget_package)[0]['kind'],'bambu')
        for bad in [dict(base,type='corebar-widget'),dict(base,android=dict(packageId='dk.other.app')),dict(base,compatibility=dict(minStudioVersion='0.45.0'))]:
            with self.assertRaises(ValueError):bundle_contract.validate(bad,store.widget_package)
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'app.apk'
            with zipfile.ZipFile(path,'w') as z:z.writestr('assets/widget.json',json.dumps(descriptor()))
            bundle_contract.inspect_apk(path,base)
            with zipfile.ZipFile(path,'w') as z:z.writestr('assets/widget.json','{}')
            with self.assertRaises(ValueError):bundle_contract.inspect_apk(path,base)

class BundledDeployTests(DeferredAppTests):
    def test_one_install_adds_both_templates_and_widget_only_deploy_installs_companion(self):
        self.package.update(id='studio.bambu.panel',name='Bambu Panel',bundledWidgets=descriptor())
        self.package['compatibility']['minStudioVersion']='0.46.0'
        self.package['android']['packageId']='dk.ultrabar.bambu'
        self.assertEqual(self.stage()['state'],'complete')
        templates=self.service.templates();self.assertEqual(len(templates),2)
        widget=next(t for t in templates if t.get('kind')=='bambu')
        self.assertEqual(widget['_bundledApp']['id'],'dk.ultrabar.bambu')
        rows=profiles();rows[0]['homeData'].append(dict(id='studio_native_'+'a'*32,type='PC_CONTROL',param=dict(payload=dict(action='studioNative',params=dict(kind='bambu',packageId=self.package['id'],widgetKey='bambu-liquid',companionApp='dk.ultrabar.bambu')))))
        with patch.object(self.service,'install_on_core') as install,patch.object(store,'inspect_apk'):
            self.service.deploy_dependencies(rows,'core',lambda _:None)
            install.assert_called_once();self.assertEqual(install.call_args.args[1]['android']['packageId'],'dk.ultrabar.bambu')
