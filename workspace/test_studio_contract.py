"""Contracts for app-owned settings, safe providers and legacy package support."""
import copy
import json
import hashlib
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import server
import store
from studio_contract import legacy_descriptor, legacy_bambu, resolve, validate
from store import StoreError, require_widget_version, widget_package


class StudioContractTests(unittest.TestCase):
    def test_updated_library_package_drives_existing_card_without_core_app(self):
        from studio_contract import apply_installed_settings
        from widget_presentation import resolve as presentation
        fields = [dict(key='mode',label='Mode',type='choice',default='quiet',
                       options=[dict(value='quiet',label='Quiet'),dict(value='normal',label='Normal')]),
                  dict(key='plate',type='color',label='Plate',default='#ddeeff')]
        panel = dict(api=2,settings=dict(api=1,fields=fields))
        face = dict(api=1,source=dict(scope='setting',key='mode'),
                    presets=[dict(value='quiet',splitFlap=dict(plateColor='#000000',plateColorSetting='plate',durationMs=350))])
        panel['presentation'] = face
        widget=dict(kind='clock',name='Example',id='face',studio=panel)
        raw=json.dumps(dict(widgetApi=1,runtime='studio-native-v1',widgets=[widget])).encode()
        templates=widget_package(raw)
        records={'example:pc':dict(id='example',type='corebar-widget',widgets=templates)}
        specs={'a':dict(kind='clock',packageId='example',widgetKey='face',packageSettings={'plate':'#123456'}),
               'b':dict(kind='clock',packageId='example',widgetKey='face')}
        apply_installed_settings(specs, records)
        self.assertEqual(presentation(face,specs['a'])['splitFlap']['plateColor'],'#123456')
        self.assertEqual(presentation(face,specs['b'])['splitFlap']['plateColor'],'#ddeeff')
        fields.append(dict(key='chime',label='Chime',type='boolean',default=True))
        records['example:pc']['widgets']=[widget]
        apply_installed_settings(specs,records)
        self.assertEqual(specs['a']['packageSettings'],dict(mode='quiet',plate='#123456',chime=True))
        self.assertNotIn('chime', specs['a'])

    def test_widget_size_declarations_and_minimum_version(self):
        def parse(sizes):
            widget = dict(id='clock', name='Clock', kind='clock', sizes=sizes)
            return widget_package(json.dumps(dict(widgetApi=1, runtime='studio-native-v1', widgets=[widget])).encode())
        for sizes in (['small'], ['large'], ['large', 'small']):
            self.assertEqual(parse(sizes)[0]['sizes'], sizes)
        for invalid in ([], ['small', 'small'], ['medium'], 'small', [{}]):
            with self.subTest(invalid=invalid), self.assertRaises(StoreError):
                parse(invalid)
        with self.assertRaisesRegex(StoreError, '0.52.0'):
            require_widget_version(parse(['small']), dict(compatibility=dict(minStudioVersion='0.51.0')))

    def test_model_choices_are_bounded_and_require_compatible_studio(self):
        descriptor=legacy_bambu()
        field=dict(key='model',label='Printer model',type='choice',required=False,options=[dict(value='generic',label='Other'),dict(value='h2d',label='H2D')])
        descriptor['connection']['fields'].append(field)
        validate(descriptor,'bambu')
        widget=dict(kind='bambu',studio=descriptor)
        with self.assertRaises(StoreError):require_widget_version([widget],dict(compatibility=dict(minStudioVersion='0.49.3')))
        require_widget_version([widget],dict(compatibility=dict(minStudioVersion='0.50.0')))
        for options in ([dict(value='not/a/model',label='Wrong')], [dict(value='generic',label='Other')]*2, []):
            field['options']=options
            with self.assertRaises(ValueError):validate(descriptor,'bambu')

    def test_legacy_descriptors_cover_existing_widget_controls(self):
        for kind in ('bambu', 'clock', 'disk', 'cpu', 'memory', 'gpu'):
            widget = dict(kind=kind, kindOptions=['cpu', 'memory', 'gpu'])
            descriptor = legacy_descriptor(widget)
            self.assertEqual(validate(descriptor, kind), descriptor)
            self.assertEqual(resolve(widget), descriptor)
        self.assertIsNone(resolve(dict(kind='cpu')))

    def test_descriptor_roundtrips_with_package_and_version_gate(self):
        widget = dict(id='printer', name='Custom printer panel', kind='bambu', studio=legacy_bambu())
        widget['studio']['connection']['title'] = 'Workshop devices'
        raw = json.dumps(dict(widgetApi=1, runtime='studio-native-v1', widgets=[widget])).encode()
        result = widget_package(raw)
        self.assertEqual(result[0]['studio']['connection']['title'], 'Workshop devices')
        require_widget_version(result, dict(type='corebar-widget', compatibility=dict(minStudioVersion='0.49.0')))
        with self.assertRaises(StoreError):
            require_widget_version(result, dict(type='corebar-widget', compatibility=dict(minStudioVersion='0.48.1')))

    def test_package_cannot_override_identity_or_inject_transport(self):
        for key in ('printerId', 'packageId', 'widgetKey', 'script'):
            value = legacy_bambu()
            value['settings']['fields'][0] = dict(key=key, label='Wrong', type='string', default='', maxLength=100)
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate(value, 'bambu')
        for provider in ('https://example.test', 'shell', []):
            value = legacy_bambu();value['connection']['provider'] = provider
            with self.subTest(provider=provider), self.assertRaises(ValueError):
                validate(value, 'bambu')
        value = legacy_bambu();value['connection']['endpoint'] = '/api/anything'
        with self.assertRaises(ValueError):
            validate(value, 'bambu')

    def test_provider_secret_shape_cannot_be_downgraded(self):
        for mutation in ('plain', 'omit', 'duplicate', 'bad-required'):
            value = legacy_bambu();fields = value['connection']['fields']
            if mutation == 'plain':fields[3]['type'] = 'string'
            elif mutation == 'omit':fields.pop(3)
            elif mutation == 'duplicate':fields[3] = copy.deepcopy(fields[0])
            else:fields[3]['required'] = 'yes'
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                validate(value, 'bambu')

    def test_renderer_types_and_allowed_values_are_preserved(self):
        value = legacy_bambu();value['settings']['fields'][2]['type'] = 'number'
        with self.assertRaises(ValueError):validate(value, 'bambu')
        value = legacy_bambu();value['settings']['fields'][2]['max'] = 7
        with self.assertRaises(ValueError):validate(value, 'bambu')
        value = legacy_bambu();value['settings']['fields'][0]['options'].append(dict(value='camera', label='Camera'))
        with self.assertRaises(ValueError):validate(value, 'bambu')
        value = legacy_descriptor(dict(kind='disk'));value['sources']['drive'] = 'https://example.test'
        with self.assertRaises(ValueError):validate(value, 'disk')
        value = legacy_descriptor(dict(kind='disk'));value['sources'] = {'other': 'pc.drives'}
        with self.assertRaises(ValueError):validate(value, 'disk')
        value = legacy_descriptor(dict(kind='disk'));value['settings']['fields'][0]['default'] = 'anything'
        with self.assertRaises(ValueError):validate(value, 'disk')

    def test_monitor_choices_respect_package_measurement_options(self):
        widget = dict(id='monitor', name='Monitor', kind='cpu', kindOptions=['cpu', 'memory'], studio=legacy_descriptor(dict(kind='cpu', kindOptions=['cpu', 'memory', 'gpu'])))
        raw = json.dumps(dict(widgetApi=1, runtime='studio-native-v1', widgets=[widget])).encode()
        with self.assertRaises(StoreError):widget_package(raw)

    def test_new_descriptor_is_copied_and_never_mutates_package(self):
        widget = dict(kind='bambu', studio=legacy_bambu())
        descriptor = resolve(widget);descriptor['connection']['title'] = 'Changed locally'
        self.assertEqual(widget['studio']['connection']['title'], 'Bambu printers')

    def test_reviewed_package_descriptor_survives_install_and_template_listing(self):
        from test_store import fixture
        package, _ = fixture()
        widget = dict(id='printer', name='Printer', kind='bambu', studio=legacy_bambu())
        widget['studio']['connection']['title'] = 'App-owned workshop connections'
        raw = json.dumps(dict(widgetApi=1, runtime='studio-native-v1', widgets=[widget])).encode()
        package.update(type='corebar-widget')
        package['compatibility']['minStudioVersion'] = '0.49.0'
        package['artifact'].update(size=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        def fetch(url, limit, destination=None):
            destination.write(raw);return len(raw)
        with tempfile.TemporaryDirectory() as tmp, patch.object(server, 'DATA_DIR', Path(tmp)), patch.object(store, 'catalog', return_value=[package]), patch.object(store, 'fetch', side_effect=fetch), patch.object(store.updates, 'VERSION', '0.49.0'):
            service = store.Store(server)
            service.job = dict(state='running')
            service.install(dict(id=package['id'], version=package['version'], sha256=package['artifact']['sha256']))
            self.assertEqual(service.status()['state'], 'complete', service.status())
            installed = service.records()[package['id']+':pc']['widgets'][0]
            self.assertEqual(installed['studio'], widget['studio'])
            template = service.templates()[0]
            self.assertEqual(template['_studio']['connection']['title'], 'App-owned workshop connections')
            self.assertEqual(template['_storePackage'], package['id'])


if __name__ == '__main__':
    unittest.main()
