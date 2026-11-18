"""Cross-package presets and isolation, without vendor/model logic in Studio."""
import copy
import unittest
import widget_presentation as presentation
from studio_contract import validate


def panel():
    return dict(api=1,settings=dict(api=1,fields=[dict(key='preset',label='Style',type='choice',default='morning',options=[dict(value='morning',label='Morning'),dict(value='night',label='Night')])]),presentation=dict(api=1,source=dict(scope='setting',key='preset'),presets=[dict(value='morning',labels={'title':'Morning clock'},artwork=[dict(type='oval',points=[10,10,90,90],fill='accent')]),dict(value='night',labels={'title':'Night clock'})]))


class PresentationTests(unittest.TestCase):
    def test_unrelated_publisher_can_own_choices_labels_and_artwork(self):
        descriptor=panel();validate(descriptor,'clock')
        specs={'one':dict(kind='clock',packageId='someone.clock',widgetKey='clock',preset='morning',_presentation={'labels':{'title':'untrusted draft'}}),'two':dict(kind='clock',packageId='someone.clock',widgetKey='clock',preset='night')}
        records={'clock':dict(id='someone.clock',widgets=[dict(id='clock',kind='clock',studio=descriptor)])}
        bindings=presentation.bindings(specs,records)
        result=presentation.apply(specs,bindings,{})
        self.assertEqual(result['one']['_presentation']['labels']['title'],'Morning clock')
        self.assertEqual(result['two']['_presentation']['labels']['title'],'Night clock')
        self.assertNotIn('_presentation',presentation.apply(specs,{}, {})['one'])
        self.assertEqual(specs['one']['_presentation']['labels']['title'],'untrusted draft')

    def test_connection_preset_uses_declared_provider_and_opaque_connection_key(self):
        config=panel()['presentation'];config['source']=dict(scope='connection',key='deviceType')
        specs={'one':dict(deviceId='opaque')}
        bindings={'one':(config,'other-protocol','deviceId')}
        resolved=presentation.apply(specs,bindings,{'other-protocol':{'opaque':{'deviceType':'night'}}})
        self.assertEqual(resolved['one']['_presentation']['labels']['title'],'Night clock')
        self.assertEqual(presentation.apply(specs,bindings,{})['one']['_presentation'],{})

    def test_secrets_code_external_images_unbounded_or_invalid_shapes_are_rejected(self):
        for mutate in (
            lambda p:p['presentation']['source'].update(key='secret'),
            lambda p:p['presentation']['presets'][0].update(script='run()'),
            lambda p:p['presentation']['presets'][0].update(artwork='https://example.com/image.svg'),
            lambda p:p['presentation']['presets'][0]['artwork'][0].update(points=[0,0,101,100]),
            lambda p:p['presentation']['presets'][0]['artwork'][0].update(points=[0,0,float('nan'),100]),
            lambda p:p['presentation']['presets'][0]['artwork'][0].update(fill='url(https://example.com)'),
            lambda p:p['presentation']['presets'].append(copy.deepcopy(p['presentation']['presets'][0])),
        ):
            descriptor=panel();mutate(descriptor)
            with self.assertRaises(ValueError):validate(descriptor,'clock')

