from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import editor
import server
import pc


def profiles():
    return [dict(id='p1', name='Home', default=True, showName=True, iconScale=100,
                 albumId='time_image_10', player='SONOS', homeData=[dict(id='clock', type='TIME', name='Clock', iconScale=100)],
                 module=[dict(serialNo='0000019F2B129C2C', productId='DOT_KEY', config=[dict(keyCode=2, singleClick=dict(actions=[dict(type='ACTIVITY', values=[dict(id='1',value='com.app')])]))])])]


class EditorTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.patch=patch.object(server,'DATA_DIR',Path(self.folder.name));self.patch.start();self.addCleanup(self.patch.stop)
        self.snapshot=dict(target='10.10.0.181:5555',device_id='core1',profiles=profiles(),backup='a'*64+'.xml')
        self.conn=patch.dict(server.connection,dict(target=self.snapshot['target'],snapshot=self.snapshot));self.conn.start();self.addCleanup(self.conn.stop)
        self.client=server.app.test_client();self.headers={'Host':'127.0.0.1:8741','X-Studio-Token':server.SESSION_TOKEN}
        self.draft=self.client.get('/api/editor',headers=self.headers).json['draft']
        self.wake=patch.object(editor,'wake_for_deploy');self.wake_mock=self.wake.start();self.addCleanup(self.wake.stop)
        for method in ('prepare','configure'):
            patcher=patch.object(server.native_widgets,method);patcher.start();self.addCleanup(patcher.stop)

    def post(self,path,body=None):
        return self.client.post(path,headers=self.headers,json=body or dict(device_id='core1',revision=self.draft['revision']))

    def save(self,rows):
        return self.post('/api/editor/draft',dict(device_id='core1',revision=self.draft['revision'],profiles=rows))

    def test_rejected_overlay_cannot_be_saved_or_redeployed(self):
        rows=profiles()
        rows[0]['homeData'].append(dict(id='legacy_gpu', type='PC_CONTROL',
            param=dict(payload=dict(action='studioMetric', params=dict(metric='gpu')))))
        response=self.save(rows)
        self.assertEqual(response.status_code,400)
        self.assertIn('overlay widgets are no longer supported', response.json['error'])
        self.draft['profiles']=rows
        editor.atomic_json(editor.draft_path(server, 'core1'), self.draft)
        with patch.object(server, 'adb') as adb, patch.object(editor.bridge, 'request') as send:
            response=self.post('/api/editor/deploy')
            self.assertEqual(response.status_code,400)
            adb.assert_not_called()
            send.assert_not_called()

    def test_draft_is_persistent_and_does_not_write_device(self):
        rows=profiles();rows[0]['name']='Work'
        with patch.object(server,'adb') as adb:
            response=self.save(rows)
            self.assertEqual(response.status_code,200)
            self.assertEqual(self.client.get('/api/editor',headers=self.headers).json['draft']['profiles'],rows)
            adb.assert_not_called()
        self.assertEqual(self.snapshot['profiles'][0]['name'],'Home')

    def test_widget_sizes_persist_through_draft_deploy_and_reset(self):
        rows = profiles()
        key = 'studio_native_' + 'a' * 32
        rows[0]['homeData'].append(dict(id=key, type='PC_CONTROL', name='Store Clock', param=dict(
            payload=dict(action='studioNative', params=dict(kind='clock', accent='#94d9bb')))))
        sizes = {'p1': dict(small=[key], positions={'clock': [0, 0], key: [6, 1]})}
        saved = self.post('/api/editor/draft', dict(device_id='core1', revision=self.draft['revision'],
                                                  profiles=rows, compact_profiles=sizes))
        self.assertEqual(saved.status_code, 200)
        self.draft = saved.json['draft']
        self.assertEqual(self.draft['compact_profiles'], sizes)
        self.assertEqual(editor.saved_compact_profiles(server, self.snapshot), {})
        with patch.object(server, 'read_snapshot', return_value=self.snapshot), \
                patch.object(editor.bridge, 'request') as send, patch.object(server, 'adb', return_value='Status: ok'), \
                patch.object(server, 'parse_profiles', return_value={'profiles': rows}), \
                patch.object(server.native_widgets.ready, 'wait'):
            deployed = self.post('/api/editor/deploy')
        self.assertEqual(deployed.status_code, 200)
        self.assertEqual(send.call_args.args[-1], editor.to_wire(rows))
        self.assertEqual(editor.saved_compact_profiles(server, deployed.json['snapshot']), sizes)
        server.native_widgets.configure.assert_called_once_with(rows, self.snapshot['target'], sizes)
        self.draft = deployed.json['draft']
        with patch.object(server, 'read_snapshot', return_value=deployed.json['snapshot']):
            self.assertEqual(self.post('/api/editor/reset').json['draft']['compact_profiles'], sizes)

    def test_widget_sizes_respect_store_package_declarations(self):
        rows = profiles()
        key = 'studio_native_' + 'b' * 32
        rows[0]['homeData'].append(dict(id=key, type='PC_CONTROL', name='Store Clock', param=dict(
            payload=dict(action='studioNative', params=dict(kind='clock', accent='#94d9bb', packageId='studio.clock', widgetKey='clock')))))
        records = {'studio.clock:pc': dict(id='studio.clock', widgets=[dict(id='clock', sizes=['small'])])}
        with self.assertRaisesRegex(editor.EditError, 'does not support the large size'):
            editor.validate_compact_profiles({}, rows, records)
        self.assertEqual(editor.validate_compact_profiles({'p1': [key]}, rows, records), {'p1': [key]})
        with self.assertRaisesRegex(editor.EditError, 'does not support the small size'):
            editor.validate_compact_profiles({'p1': ['clock', key]}, rows, records)

    def test_empty_split_slots_survive_save_without_enabling_core_runtime(self):
        splits = {'p1': dict(small=[], positions={}, splits=[4, 8])}
        response = self.post('/api/editor/draft', dict(device_id='core1', revision=self.draft['revision'],
                                                      profiles=profiles(), compact_profiles=splits))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get('/api/editor', headers=self.headers).json['draft']['compact_profiles'], splits)
        editor.atomic_json(editor.compact_profiles_path(server, 'core1'), splits)
        self.assertEqual(editor.saved_compact_profiles(server, self.snapshot), splits)
        self.assertEqual(editor.core_widget_layouts(splits), {})
        invalid = {'p1': dict(small=[], positions={}, splits=[4, 5])}
        with self.assertRaisesRegex(editor.EditError, 'separate positions'):
            editor.validate_compact_profiles(invalid, profiles())

    def test_stale_draft_and_wrong_device_rejected(self):
        self.assertEqual(self.save(profiles()).status_code,200)
        self.assertEqual(self.save(profiles()).status_code,409)
        self.assertEqual(self.post('/api/editor/deploy',dict(device_id='other',revision=self.draft['revision'])).status_code,409)

    def test_validation_preserves_module_slots(self):
        for change in [lambda p:p[0].update(module=[]),lambda p:p[0]['module'][0].update(config=[]),lambda p:p[0].update(default=False),lambda p:p[0]['homeData'].append(p[0]['homeData'][0])]:
            rows=profiles();change(rows)
            self.assertEqual(self.save(rows).status_code,400)
        rows=profiles();rows[0]['module'][0]['config'][0]['singleClick']['actions']=[]
        self.assertEqual(self.save(rows).status_code,200)

    def test_unfinished_shortcut_can_be_saved_but_not_deployed(self):
        rows=profiles();rows[0]['homeData'].append(dict(id='studio_test',type='PC_CONTROL',name='Open website',_pcPending=True,param=dict(payload=dict(action='studioAction',params=dict(id='',kind='url')))))
        response=self.save(rows);self.assertEqual(response.status_code,200);self.draft=response.json['draft']
        with patch.object(server,'read_snapshot') as read,patch.object(editor.bridge,'request') as bridge:
            response=self.post('/api/editor/deploy')
            self.assertEqual(response.status_code,400);self.assertIn('Apply settings',response.json['error'])
            read.assert_not_called();bridge.assert_not_called();self.wake_mock.assert_not_called()
        rows[0]['homeData'][-1]['_pcPending']='invalid'
        self.assertEqual(self.save(rows).status_code,400)

    def test_changed_core_aborts_before_write(self):
        latest=deepcopy(self.snapshot);latest['profiles'][0]['name']='Changed elsewhere'
        with patch.object(server,'read_snapshot',return_value=latest),patch.object(editor.bridge,'request') as bridge:
            self.assertEqual(self.post('/api/editor/deploy').status_code,409)
            bridge.assert_not_called()

    def test_backup_precedes_write_and_readback(self):
        order=[]
        self.wake_mock.side_effect=lambda *_:order.append('wake')
        def send(*args):
            self.assertTrue(editor.draft_path(server,'core1').with_suffix('.rollback.json').exists())
            order.append('write')
        with patch.object(server,'read_snapshot',side_effect=lambda _:order.append('backup') or self.snapshot),patch.object(editor.bridge,'request',side_effect=send),patch.object(server,'adb',return_value=b'x'),patch.object(server,'parse_profiles',return_value={'profiles':profiles()}):
            response=self.post('/api/editor/deploy')
        self.assertEqual(response.status_code,200)
        self.assertEqual(order,['backup','wake','write'])

    def test_progress_can_be_read_while_deploy_holds_device_lock(self):
        def waking(*args):
            status=self.client.get('/api/editor/deploy-status',headers=self.headers)
            self.assertEqual(status.status_code,200)
            self.assertEqual(status.json['request_id'],'test-progress')
            self.assertEqual(status.json['state'],'running')
            self.assertIn('Waking Core',status.json['message'])
        self.wake_mock.side_effect=waking
        with patch.object(server,'read_snapshot',return_value=self.snapshot),patch.object(editor.bridge,'request'),patch.object(server,'adb',return_value=b'x'),patch.object(server,'parse_profiles',return_value={'profiles':profiles()}):
            result=self.post('/api/editor/deploy',dict(device_id='core1',revision=self.draft['revision'],request_id='test-progress'))
        self.assertEqual(result.status_code,200)
        self.assertEqual(self.client.get('/api/editor/deploy-status',headers=self.headers).json['state'],'done')

    def test_wake_failure_aborts_before_prepare_and_write(self):
        self.wake_mock.side_effect=server.DeviceError('Core did not leave standby. No settings were sent.')
        with patch.object(server,'read_snapshot',return_value=self.snapshot),patch.object(editor.bridge,'request') as bridge,patch.object(server.native_widgets,'prepare') as prepare:
            response=self.post('/api/editor/deploy')
        self.assertEqual(response.status_code,502)
        bridge.assert_not_called();prepare.assert_not_called()
        self.assertEqual(self.client.get('/api/editor',headers=self.headers).json['draft']['revision'],self.draft['revision'])

    def test_timeout_reads_back_without_resending(self):
        with patch.object(server,'read_snapshot',return_value=self.snapshot),patch.object(editor.bridge,'request',side_effect=TimeoutError) as bridge,patch.object(server,'adb',return_value=b'x'),patch.object(server,'parse_profiles',return_value={'profiles':profiles()}):
            response=self.post('/api/editor/deploy')
        self.assertEqual(response.status_code,200);self.assertFalse(response.json['acknowledged']);self.assertEqual(bridge.call_count,1)

    def test_mismatch_preserves_draft_and_backup(self):
        with patch.object(server,'read_snapshot',return_value=self.snapshot),patch.object(editor.bridge,'request'),patch.object(server,'adb',return_value=b'x'),patch.object(server,'parse_profiles',return_value={'profiles':[]}),patch.object(editor.time,'sleep'),patch.object(server.store,'mark_deployed') as activated:
            self.assertEqual(self.post('/api/editor/deploy').status_code,502)
            activated.assert_not_called()
        self.assertTrue(editor.draft_path(server,'core1').with_suffix('.rollback.json').exists())
        self.assertEqual(self.client.get('/api/editor',headers=self.headers).json['draft']['revision'],self.draft['revision'])

    def test_wire_strips_type_selectors_and_maps_widgets(self):
        p=profiles();p[0]['homeData'][0]['@type']='not.trusted.Class'
        wire=editor.to_wire(p)
        self.assertNotIn('homeData',wire[0]);self.assertNotIn('@type',wire[0]['widget'][0]);self.assertEqual(wire[0]['module'],p[0]['module'])
        p[0]['player']='SPOTIFY'
        with self.assertRaises(editor.EditError):editor.to_wire(p)

    def test_readback_catches_lost_action_and_tolerates_runtime_defaults(self):
        p=profiles();actual=deepcopy(p);actual[0]['homeData'][0]['last']=True
        self.assertTrue(editor.matches(p,actual))
        actual[0]['module'][0]['config'][0]['singleClick']['actions']=[]
        self.assertFalse(editor.matches(p,actual))

    def test_restore_retains_empty_new_slots(self):
        current=profiles();current[0]['module'][0]['config'].append(dict(keyCode=3,singleClick=dict(actions=[dict(type='ACTIVITY')])) )
        restored=editor.retain_cleared_slots(profiles(),current)
        self.assertEqual(restored[0]['module'][0]['config'][1]['singleClick']['actions'],[])
        editor.validate(restored,current)

    def test_auth_still_required_for_writes(self):
        self.assertEqual(self.client.post('/api/editor/deploy',headers={'Host':'127.0.0.1:8741'},json={}).status_code,403)


class PcTests(unittest.TestCase):
    def test_url_validation_rejects_commands_and_credentials(self):
        for url in ['file:///C:/x.exe','javascript:alert(1)','https://user:pass@example.com','https://example.com\nfoo']:
            with self.assertRaises(editor.EditError):pc.validate_action(dict(name='Test',kind='url',target=url))
        self.assertEqual(pc.validate_action(dict(name='Test',kind='url',target='https://example.com'))['target'],'https://example.com')

    def test_only_registered_device_actions_execute_once(self):
        companion=pc.Companion(server);companion.device_id='core1'
        action=dict(id='known',name='Website',kind='url',target='https://example.com',device_id='core1')
        frame=dict(id='push1',act=1000000,data=dict(type='PC_CONTROL',payload=dict(action='studioAction',params=dict(id='known'))))
        with patch.object(companion,'actions',return_value=[action]),patch.object(pc.webbrowser,'open',return_value=True) as launch:
            self.assertEqual(companion.handle(frame)['code'],200)
            companion.handle(frame);self.assertEqual(launch.call_count,1)
            companion.device_id='other';self.assertIsNone(companion.handle(frame))
            frame['data']['payload']['action']='startApp';self.assertIsNone(companion.handle(frame))

    def test_metrics_frame_shape_and_missing_sensor(self):
        companion=pc.Companion(server)
        with patch.object(companion.metrics,'sample',return_value={'cpu':37.6,'memory':50,'disks':[]}):
            response=companion.handle(dict(id='p',act=1000000,data=dict(type='CPU')))
            self.assertEqual(response['data'],dict(type='CPU',payload=38))
            self.assertIsNone(companion.handle(dict(id='p2',act=1000000,data=dict(type='STORAGE'))))


if __name__=='__main__':unittest.main()


class WakeDeployTests(unittest.TestCase):
    def test_wakes_sleeping_core_and_waits_for_display(self):
        states=['mWakefulness=Dozing\nDisplay Power: state=OFF','mWakefulness=Awake\nDisplay Power: state=OFF','mWakefulness=Awake\nDisplay Power: state=ON']
        with patch.object(server,'adb',side_effect=['']+states) as adb,patch.object(editor.time,'sleep') as sleep:
            editor.wake_for_deploy(server,'core')
        self.assertEqual(adb.call_args_list[0].args,('-s','core','shell','input','keyevent','224'))
        self.assertEqual(sleep.call_count,2)
    def test_already_awake_is_not_toggled_off(self):
        with patch.object(server,'adb',side_effect=['','mWakefulness=Awake\nDisplay Power: state=ON']) as adb,patch.object(editor.time,'sleep') as sleep:
            editor.wake_for_deploy(server,'core')
        self.assertEqual(adb.call_args_list[0].args[-1],'224');sleep.assert_not_called()
    def test_standby_timeout_and_adb_failure_are_explicit(self):
        with patch.object(server,'adb',return_value='mWakefulness=Dozing\nDisplay Power: state=OFF'),patch.object(editor.time,'sleep'):
            with self.assertRaisesRegex(server.DeviceError,'No settings were sent'):editor.wake_for_deploy(server,'core')
        with patch.object(server,'adb',side_effect=server.DeviceError('offline')):
            with self.assertRaisesRegex(server.DeviceError,'No settings were sent'):editor.wake_for_deploy(server,'core')
