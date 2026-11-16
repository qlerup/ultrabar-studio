"""Upgrade installed Bambu identities without replacing placed widgets or Core data."""
import copy,hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import editor,server,store
from test_store import fixture
from test_editor import profiles


SOURCE='https://github.com/qlerup/ultrabar-bambu/blob/'+'a'*40+'/'


def upgraded():
    package,_=fixture()
    raw=json.dumps(dict(widgetApi=1,runtime='studio-native-v1',widgets=[dict(id='bambu-liquid',kind='bambu',name='Bambu')])).encode()
    package.update(id='studio.bambu',name='Bambu',type='corebar-widget',version='2.0.1',source=SOURCE+'widget.json',publisher='qlerup')
    package['compatibility']['minStudioVersion']='0.48.1'
    package['artifact'].update(size=len(raw),sha256=hashlib.sha256(raw).hexdigest())
    return package,raw


def legacy(alias=False):
    package,_=upgraded()
    package.update(version='2.0.0' if alias else '1.0.1',type='corebar-widget' if alias else 'corebar-app',id='studio.bambu.widget' if alias else 'studio.bambu',device_id=None,requiresDeploy=True)
    if not alias:package.update(android=dict(packageId='dk.ultrabar.bambu'),deferred=True)
    return package


def layout(alias=False):
    rows=profiles()
    spec=dict(kind='bambu',packageId='studio.bambu.widget' if alias else 'studio.bambu',packageVersion='2.0.0' if alias else '1.0.1',widgetKey='bambu-liquid',primary='remaining',secondary='job',expandedSlots=5,liquidMotion=False,showControls=False,accent='#86e4c3',printerId='c'*32)
    if not alias:spec['companionApp']='dk.ultrabar.bambu'
    rows[0]['homeData'].append(dict(id='studio_native_'+'b'*32,type='PC_CONTROL',name='My workshop printer',bgColor='#123456',param=dict(payload=dict(action='studioNative',params=spec))))
    return rows


class BambuUpgradeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.service=store.Store(server)
        for context in (patch.object(server,'DATA_DIR',self.root),patch.object(server,'store',self.service)):
            context.start();self.addCleanup(context.stop)
        self.package,self.raw=upgraded()

    def install(self,corrupt=False):
        def fetch(url,limit,destination):
            data=b'invalid' if corrupt else self.raw;destination.write(data);return len(data)
        self.service.job=dict(state='running')
        with patch.object(store,'catalog',return_value=[self.package]),patch.object(store,'fetch',side_effect=fetch),patch.object(server,'adb') as adb:
            self.service.install(dict(id='studio.bambu',version=self.package['version'],sha256=self.package['artifact']['sha256']))
            adb.assert_not_called()

    def test_original_app_is_updated_in_place_and_draft_is_preserved(self):
        self.service.save({'studio.bambu:pc':legacy()})
        rows=layout();snapshot=dict(device_id='upgrade',profiles=copy.deepcopy(rows),backup='before.xml')
        draft=editor.fresh_draft(snapshot);draft['background_apps']=[dict(id='dk.ultrabar.bambu',name='Bambu',settings=dict(launch=False)),dict(id='dk.example.other',name='Keep',settings=dict(launch=True))]
        draft['app_settings']={'dk.ultrabar.bambu':dict(allowControls=True)}
        path=editor.draft_path(server,'upgrade');editor.atomic_json(path,draft);original=path.read_bytes()
        self.install();self.assertEqual(self.service.status()['state'],'complete');self.assertTrue(self.service.status()['is_update'])
        self.assertEqual(list(self.service.records()),['studio.bambu:pc'])
        migrated=editor.load_draft(server,snapshot)
        self.assertEqual(path.read_bytes(),original)  # Saved draft remains recoverable until user saves.
        self.assertEqual(migrated['base_profiles'],rows)
        card=migrated['profiles'][0]['homeData'][-1]
        self.assertEqual(card['id'],rows[0]['homeData'][-1]['id']);self.assertEqual(card['name'],'My workshop printer');self.assertEqual(card['bgColor'],'#123456')
        spec=card['param']['payload']['params'];before=rows[0]['homeData'][-1]['param']['payload']['params']
        for key in ('primary','secondary','expandedSlots','liquidMotion','showControls','printerId'):self.assertEqual(spec[key],before[key])
        self.assertEqual(spec['packageVersion'],'2.0.1');self.assertNotIn('companionApp',spec)
        self.assertEqual([a['id'] for a in migrated['background_apps']],['dk.example.other'])
        self.assertFalse(migrated['app_settings'])

    def test_accidental_widget_registration_is_consolidated_only_after_success(self):
        old=legacy(True);self.service.save({'studio.bambu.widget:pc':old})
        self.install(corrupt=True)
        self.assertEqual(self.service.status()['state'],'error');self.assertEqual(self.service.records(),{'studio.bambu.widget:pc':old})
        self.install();self.assertEqual(self.service.status()['state'],'complete');self.assertTrue(self.service.status()['is_update'])
        self.assertEqual(list(self.service.records()),['studio.bambu:pc'])
        draft=dict(profiles=layout(True),background_apps=[],app_settings={});self.service.migrate_bambu_draft(draft)
        self.assertEqual(draft['profiles'][0]['homeData'][-1]['param']['payload']['params']['packageId'],'studio.bambu')

    def test_unrelated_packages_and_missing_upgrade_do_not_migrate(self):
        draft=dict(profiles=layout(),background_apps=[dict(id='dk.ultrabar.bambu')],app_settings={})
        original=copy.deepcopy(draft);self.assertFalse(self.service.migrate_bambu_draft(draft));self.assertEqual(draft,original)
        wrong=legacy(True);wrong['source']='https://github.com/another/repo/blob/'+'a'*40+'/widget.json'
        self.assertIsNone(self.service.previous_record(self.package,{'studio.bambu.widget:pc':wrong}))
