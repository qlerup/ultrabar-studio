import json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
import app_settings,server,editor,store
from test_app_settings_contract import schema
from test_editor import profiles

class AppSettingsTests(unittest.TestCase):
    def setUp(self):
        self.schema=schema();self.package='dk.test.settings'
        self.record=dict(type='corebar-app',name='Test settings',android=dict(packageId=self.package),settings=self.schema)
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.context=SimpleNamespace(DATA_DIR=Path(self.temp.name),store=SimpleNamespace(records=lambda:{'app':self.record}),connection=dict(target='192.168.1.20:5555'))
    def adb(self,*args,**kwargs):
        if args[-2:]==('id','-u'):return '10077' if 'su' in args else '0'
        if 'dumpsys' in args:return '  userId=10077\n'
        if 'input_data' in kwargs:self.request=json.loads(kwargs['input_data']);self.raw=kwargs['input_data'];return ''
        if 'exec-out' in args:return self.raw
        if 'if [ -f' in args[-1]:
            response=dict(api=1,revision=self.request['revision'],status='ok',values=app_settings.validate_values(self.schema,{}))
            if self.request['operation']=='apply':response['values']=self.request['values']
            return json.dumps(response).encode()
        return ''
    def test_read_and_apply_confirm_saved_values(self):
        self.context.adb=Mock(side_effect=self.adb)
        actual=app_settings.exchange(self.context,self.package,self.schema)
        actual['delay']=1500
        self.assertEqual(app_settings.exchange(self.context,self.package,self.schema,actual),actual)
        commands=[' '.join(call.args) for call in self.context.adb.call_args_list]
        self.assertTrue(any('.StudioSettingsReceiver' in command for command in commands))
        self.assertTrue(any('exec-in' in command for command in commands))
    def test_invalid_values_fail_before_transfer(self):
        self.context.adb=Mock(side_effect=self.adb)
        with self.assertRaises(ValueError):app_settings.validate_all(self.context,{self.package:dict(delay=1001)})
        self.context.adb.assert_not_called()
    def test_rejected_stale_or_mismatched_confirmation_fails(self):
        for kind in ('error','stale','mismatch'):
            def response(*args,**kwargs):
                value=self.adb(*args,**kwargs)
                if 'if [ -f' in args[-1]:
                    data=json.loads(value)
                    if kind=='error':data['status']='error'
                    if kind=='stale':data['revision']='0'*32
                    if kind=='mismatch':data['values']['delay']=250
                    return json.dumps(data).encode()
                return value
            self.context.adb=Mock(side_effect=response)
            with patch.object(app_settings.time,'sleep'),self.assertRaises(editor.EditError):app_settings.exchange(self.context,self.package,self.schema,dict(delay=1000))
    def test_failed_transfer_never_notifies_app(self):
        def corrupted(*args,**kwargs):return b'tampered' if 'exec-out' in args else self.adb(*args,**kwargs)
        self.context.adb=Mock(side_effect=corrupted)
        with self.assertRaisesRegex(editor.EditError,'transfer'):app_settings.exchange(self.context,self.package,self.schema,{})
        self.assertFalse(any('broadcast' in call.args for call in self.context.adb.call_args_list))
    def test_authenticated_drafts_preserve_settings_and_reject_invalid_values_without_adb(self):
        snapshot=dict(device_id='settings-test',target='192.168.1.20:5555',profiles=profiles(),backup='fixture.xml')
        headers={'Host':'127.0.0.1:8741','X-Studio-Token':server.SESSION_TOKEN}
        client=server.app.test_client()
        with patch.object(server,'DATA_DIR',Path(self.temp.name)),patch.dict(server.connection,snapshot=snapshot,target=snapshot['target']),patch.object(server.store,'records',return_value={'test':self.record}),patch.object(server,'adb') as adb:
            self.assertEqual(client.get('/api/editor/app-settings',headers={'Host':headers['Host']}).status_code,403)
            draft=client.get('/api/editor',headers=headers).json['draft']
            body=dict(device_id=snapshot['device_id'],revision=draft['revision'],profiles=draft['profiles'],app_settings={self.package:dict(delay=1500)})
            response=client.post('/api/editor/draft',headers=headers,json=body)
            self.assertEqual(response.status_code,200)
            saved=client.get('/api/editor',headers=headers).json['draft']
            self.assertEqual(saved['app_settings'][self.package]['delay'],1500)
            body.update(revision=saved['revision'],app_settings={self.package:dict(delay=1001)})
            self.assertEqual(client.post('/api/editor/draft',headers=headers,json=body).status_code,400)
            self.assertEqual(client.post('/api/editor/app-settings/read',headers=headers,json=dict(device_id='other',package=self.package)).status_code,400)
            adb.assert_not_called()
