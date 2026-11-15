import copy,json,tempfile,unittest,zipfile
from pathlib import Path
from app_settings_contract import validate_schema,validate_values,inspect_apk,validate_receiver

def schema():
    return dict(api=1,fields=[dict(key='enabled',label='Enabled',type='boolean',default=True),dict(key='delay',label='Delay',type='integer',default=1000,min=0,max=3000,step=250),dict(key='volume',label='Volume',type='number',default=.5,min=0,max=1,step=.1),dict(key='title',label='Title',type='string',default='My app',maxLength=100),dict(key='website',label='Website',type='url',default='https://example.com',maxLength=2048),dict(key='mode',label='Mode',type='choice',default='normal',options=[dict(value='normal',label='Normal'),dict(value='quiet',label='Quiet')])])

class SettingsContractTests(unittest.TestCase):
    def test_all_types_defaults_and_exact_values(self):
        value=schema();self.assertEqual(validate_schema(value),value)
        result=validate_values(value,{})
        self.assertEqual(result['delay'],1000);self.assertEqual(validate_values(value,result,False),result)
    def test_invalid_types_ranges_steps_keys_and_urls(self):
        for key,value in [('enabled',1),('delay',True),('delay',1001),('delay',4000),('delay',1.0),('volume',float('nan')),('title','x'*101),('website','file:///test'),('website','https://u:p@example.com'),('mode','other'),('unknown',True)]:
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):validate_values(schema(),{key:value})
        with self.assertRaises(ValueError):validate_values(schema(),{},False)
    def test_invalid_schema_and_defaults(self):
        for update in [dict(api=True),dict(api=2),dict(fields=[]),dict(command='shell')]:
            with self.assertRaises(ValueError):validate_schema(dict(schema(),**update))
        for update in [dict(default=1001),dict(step=0),dict(min=4000),dict(type='secret'),dict(maxLength=100)]:
            value=schema();value['fields'][1].update(update)
            with self.assertRaises(ValueError):validate_schema(value)
        value=schema();value['fields'].append(copy.deepcopy(value['fields'][0]))
        with self.assertRaises(ValueError):validate_schema(value)
    def test_embedded_descriptor_must_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'app.apk'
            with zipfile.ZipFile(path,'w') as archive:archive.writestr('assets/studio-settings.json',json.dumps(schema()))
            inspect_apk(path,schema())
            other=schema();other['fields'][0]['default']=False
            with self.assertRaises(ValueError):inspect_apk(path,other)
    def test_receiver_must_have_fixed_name_and_sender_permission(self):
        xml='''E: manifest
  E: application
    E: receiver
      A: android:name(0x01010003)=".StudioSettingsReceiver"
      A: android:exported(0x01010010)=(type 0x12)0xffffffff
      A: android:permission(0x01010006)="android.permission.DUMP"
'''
        validate_receiver(xml,'dk.test.app')
        for bad in [xml.replace('0xffffffff','0x0'),xml.replace('android.permission.DUMP','normal'),xml.replace('.StudioSettingsReceiver','.Other')]:
            with self.assertRaises(ValueError):validate_receiver(bad,'dk.test.app')
