import copy,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import server,store
from test_store import fixture

class StoreActivationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        patcher=patch.object(server,'DATA_DIR',Path(self.temp.name));patcher.start();self.addCleanup(patcher.stop)
        self.service=store.Store(server);self.package,_=fixture()
        self.package.update(requiresDeploy=True,widgets=[])
        self.service.save({self.package['id']+':pc':self.package})
        self.profiles=[dict(homeData=[dict(id='placed',type='PC_CONTROL',param=dict(payload=dict(params=dict(packageId=self.package['id']))))])]
    def test_activation_is_persistent_and_per_device(self):
        self.assertIn(self.package['id'],self.service.pending_deploy('core-a'))
        self.service.mark_deployed('core-a',self.service.deployment_plan(self.profiles,[]))
        self.assertNotIn(self.package['id'],store.Store(server).pending_deploy('core-a'))
        self.assertIn(self.package['id'],self.service.pending_deploy('core-b'))
    def test_later_update_is_not_cleared_by_an_older_deploy(self):
        plan=self.service.deployment_plan(self.profiles,[])
        newer=copy.deepcopy(self.package);newer['version']='1.0.1';self.service.save({newer['id']+':pc':newer})
        self.service.mark_deployed('core-a',plan)
        self.assertIn(newer['id'],self.service.pending_deploy('core-a'))
        self.service.mark_deployed('core-a',self.service.deployment_plan(self.profiles,[]))
        self.assertNotIn(newer['id'],self.service.pending_deploy('core-a'))
    def test_unused_package_is_not_marked_as_deployed(self):
        self.assertEqual(self.service.deployment_plan([dict(homeData=[])],[]),{})
        self.service.mark_deployed('core-a',{})
        self.assertIn(self.package['id'],self.service.pending_deploy('core-a'))
    def test_deploy_updates_widget_version_but_preserves_its_settings(self):
        data=self.profiles[0]['homeData'][0]['param']['payload'];data['action']='studioNative';data['params'].update(accent='#123456',hourFormat='12',packageVersion='0.9.0')
        self.service.update_widget_versions(self.profiles,self.service.deployment_plan(self.profiles,[]))
        self.assertEqual(data['params']['packageVersion'],self.package['version'])
        self.assertEqual(data['params']['accent'],'#123456');self.assertEqual(data['params']['hourFormat'],'12')
    def test_app_on_bar_or_in_background_is_included(self):
        record=copy.deepcopy(self.package);record.update(type='corebar-app',android=dict(packageId='dk.test.app'))
        self.service.save({record['id']+':pc':record})
        for profiles,background in [([dict(homeData=[dict(id='dk.test.app',type='APPS')])],[]),([dict(homeData=[])],[dict(id='dk.test.app')])]:
            self.assertEqual(self.service.deployment_plan(profiles,background),{record['id']:self.service.fingerprint(record)})
