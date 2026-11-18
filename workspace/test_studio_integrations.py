"""Package ownership and protocol dispatch for generic connection panels."""
import copy
import unittest
from unittest.mock import Mock, patch
import bambu
import server
import studio_contract


class StudioIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.client = server.app.test_client()
        self.headers = {'Host': '127.0.0.1:8741', 'X-Studio-Token': server.SESSION_TOKEN}
        self.widget = dict(id='printer', name='Printer', kind='bambu', studio=studio_contract.legacy_bambu())
        self.records = {'studio.example:pc': dict(id='studio.example', type='corebar-widget', version='1.0.0', widgets=[self.widget])}
        self.patch = patch.object(server.store, 'records', side_effect=lambda: copy.deepcopy(self.records));self.patch.start();self.addCleanup(self.patch.stop)
        self.url = '/api/studio/integrations/studio.example/printer/'

    def test_requires_session_and_installed_package_widget(self):
        self.assertEqual(self.client.get(self.url+'list', headers={'Host': self.headers['Host']}).status_code, 403)
        with patch.object(server.bambu, 'listing', return_value=[]) as listing:
            self.assertEqual(self.client.get(self.url+'list', headers=self.headers).json, dict(items=[]))
            self.assertEqual(listing.call_count, 1)
            self.assertEqual(self.client.get(self.url.replace('studio.example', 'studio.other')+'list', headers=self.headers).status_code, 400)
            self.assertEqual(self.client.get(self.url.replace('/printer/', '/other/')+'list', headers=self.headers).status_code, 400)
            self.records.clear()
            self.assertEqual(self.client.get(self.url+'list', headers=self.headers).status_code, 400)
            self.assertEqual(listing.call_count, 1)

    def test_unknown_actions_and_wrong_http_method_do_not_invoke_adapter(self):
        with patch.object(server.bambu, 'listing') as listing:
            for method, operation in [('get', 'save'), ('post', 'list'), ('post', 'shell'), ('get', 'unknown')]:
                response = getattr(self.client, method)(self.url+operation, headers=self.headers, **({'json': {}} if method == 'post' else {}))
                self.assertEqual(response.status_code, 400)
            listing.assert_not_called()

    def test_adapter_owns_validation_and_returns_redacted_listing(self):
        with patch.object(server.bambu, 'save', return_value='a'*32) as save, patch.object(server.bambu, 'listing', return_value=[dict(id='a'*32, name='Workshop')]):
            body = dict(name='Workshop', host='192.168.1.30', serial='SERIAL123', code='LAN12345', pin='b'*64, controls=False)
            response = self.client.post(self.url+'save', headers=self.headers, json=body)
            self.assertEqual(response.status_code, 200);self.assertEqual(response.json['id'], 'a'*32)
            save.assert_called_once_with(body)
            self.assertNotIn('LAN12345', response.get_data(as_text=True))
        self.assertEqual(self.client.post(self.url+'save', headers=self.headers, json=[]).status_code, 400)

    def test_choice_values_are_owned_by_the_package_not_a_studio_model_list(self):
        self.widget['studio']['connection']['fields'].append(dict(key='model',label='Device edition',type='choice',options=[dict(value='future-device',label='Future device')]))
        with patch.object(server.bambu,'save',return_value='a'*32) as save,patch.object(server.bambu,'listing',return_value=[]):
            response=self.client.post(self.url+'save',headers=self.headers,json=dict(model='future-device'))
            self.assertEqual(response.status_code,200);save.assert_called_once_with(dict(model='future-device'))
            save.reset_mock()
            self.assertEqual(self.client.post(self.url+'save',headers=self.headers,json=dict(model='unlisted-device')).status_code,400)
            save.assert_not_called()

    def test_probe_discovery_and_remove_use_fixed_provider_functions(self):
        stream = Mock()
        with patch.object(bambu, 'tls', return_value=(stream, 'b'*64)) as tls:
            response = self.client.post(self.url+'probe', headers=self.headers, json=dict(host='192.168.1.30'))
            self.assertEqual(response.json, dict(pin='b'*64));tls.assert_called_once_with('192.168.1.30');stream.close.assert_called_once()
            self.assertEqual(self.client.post(self.url+'probe', headers=self.headers, json=dict(host='127.0.0.1')).status_code, 400)
            self.assertEqual(self.client.post(self.url+'probe', headers=self.headers, json=dict(host='192.168.1.30', url='https://example.test')).status_code, 400)
        with patch.object(bambu, 'discover', return_value=[dict(name='Workshop')]) as discover:
            self.assertEqual(self.client.post(self.url+'discover', headers=self.headers, json={}).json, dict(items=[dict(name='Workshop')]))
            self.assertEqual(self.client.post(self.url+'discover', headers=self.headers, json=dict(host='1.2.3.4')).status_code, 400)
            discover.assert_called_once()
        with patch.object(server.bambu, 'remove') as remove, patch.object(server.bambu, 'listing', return_value=[]):
            self.assertEqual(self.client.post(self.url+'remove', headers=self.headers, json=dict(id='a'*32)).json, dict(items=[]))
            remove.assert_called_once_with('a'*32)

    def test_reconnect_preserves_saved_profile_and_controls(self):
        profile = dict(id='a'*32, name='Workshop', host='192.168.1.30', serial='SERIAL123', code='LAN12345', pin='b'*64, controls=False)
        old = Mock()
        with patch.object(server.bambu, 'read', return_value=[profile]), patch.object(server.bambu, 'links', {profile['id']:old}), patch.object(bambu.Link, 'start') as start:
            response = self.client.post(self.url+'reconnect', headers=self.headers, json=dict(id=profile['id']))
            self.assertEqual(response.status_code, 200);old.close.assert_called_once();start.assert_called_once()
            self.assertEqual(server.bambu.links[profile['id']].profile, profile)
            self.assertEqual(self.client.post(self.url+'reconnect', headers=self.headers, json=dict(id='missing')).status_code, 400)

    def test_legacy_packages_use_compatible_provider_descriptor(self):
        del self.widget['studio']
        with patch.object(server.bambu, 'listing', return_value=[]):
            self.assertEqual(self.client.get(self.url+'list', headers=self.headers).json, dict(items=[]))
        self.widget['kind'] = 'clock'
        self.assertEqual(self.client.get(self.url+'list', headers=self.headers).status_code, 400)

    def test_descriptor_is_revalidated_before_invoking_provider(self):
        self.widget['studio']['connection']['provider'] = 'shell'
        with patch.object(server.bambu, 'listing') as listing:
            self.assertEqual(self.client.get(self.url+'list', headers=self.headers).status_code, 400)
            listing.assert_not_called()


if __name__ == '__main__':
    unittest.main()
