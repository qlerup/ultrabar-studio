import copy,json,unittest
from bambu_contract import DEFAULTS,validate
from native_widgets import specifications
from store import widget_package,StoreError,require_widget_version


class BambuContractTests(unittest.TestCase):
    def parse(self,widget):
        return widget_package(json.dumps(dict(widgetApi=1,runtime='studio-native-v1',widgets=[widget])).encode())

    def test_each_widget_retains_its_own_settings(self):
        widgets=[]
        for n in range(2,6):
            spec=dict(DEFAULTS,kind='bambu',expandedSlots=n,accent='#86e4c3')
            widgets.append(dict(id='studio_native_'+str(n)*32,type='PC_CONTROL',bgColor='#14202b',param=dict(payload=dict(action='studioNative',params=spec))))
        specs=specifications([dict(homeData=widgets)])
        self.assertEqual([s['expandedSlots'] for s in specs.values()],[2,3,4,5])

    def test_supported_store_template_roundtrip(self):
        w=dict(DEFAULTS,id='bambu-liquid',name='Bambu Liquid',kind='bambu',background='#14202b')
        self.assertEqual(self.parse(w)[0],dict(w,_widgetPackage=True))

    def test_invalid_display_values_are_rejected(self):
        base=dict(DEFAULTS,id='bambu-liquid',name='Bambu Liquid',kind='bambu')
        for key,value in [('expandedSlots',True),('expandedSlots',1),('expandedSlots',6),('expandedSlots',3.0),('primary','shell'),('secondary','camera'),('liquidMotion','yes'),('showControls',1),('script','bad()')]:
            with self.subTest(key=key,value=value),self.assertRaises(StoreError):self.parse(dict(base,**{key:value}))
        with self.assertRaises(ValueError):validate(dict(kind='clock',expandedSlots=3))

    def test_minimum_version_must_declare_the_supported_renderer(self):
        with self.assertRaises(StoreError):require_widget_version([dict(kind='bambu')],dict(compatibility=dict(minStudioVersion='0.45.0')))
        require_widget_version([dict(kind='bambu')],dict(compatibility=dict(minStudioVersion='0.46.0')))
