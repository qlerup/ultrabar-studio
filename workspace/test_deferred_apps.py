"""Screen Sync library staging and deployment with no physical device writes."""
import hashlib
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import editor
import screen_sync
import server
import store
from test_store import fixture
from test_editor import profiles


def app_fixture():
    p, _ = fixture()
    raw = b'verified-test-apk'
    p.update(id='studio.vivo.screensync', name='Vivo Screen Sync', type='corebar-app',
             android=dict(packageId=screen_sync.PACKAGE_ID, versionCode=4, minSdk=26, signerSha256=screen_sync.SIGNER))
    p['artifact'].update(size=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    p['compatibility'].update(models=['CB01'], abis=['armeabi-v7a'])
    return p, raw


class DeferredAppTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for patcher in [patch.object(server, 'DATA_DIR', Path(self.tmp.name)), patch.dict(server.connection, target=None, snapshot=None)]:
            patcher.start(); self.addCleanup(patcher.stop)
        self.service = store.Store(server)
        self.package, self.raw = app_fixture()

    def stage(self):
        def fetch(url, limit, destination):
            destination.write(self.raw); return len(self.raw)
        self.service.job = {'state': 'running'}
        p = self.package
        with patch.object(store, 'catalog', return_value=[p]), patch.object(store, 'fetch', side_effect=fetch), patch.object(store, 'inspect_apk'):
            self.service.install(dict(id=p['id'], version=p['version'], sha256=p['artifact']['sha256']))
        return self.service.status()

    def rows(self):
        rows = profiles()
        rows[0]['homeData'].append(dict(id=screen_sync.PACKAGE_ID, type='APPS', name='Vivo Screen Sync', iconScale=100))
        return rows

    def test_install_without_core_survives_restart_and_library_removal(self):
        with patch.object(server, 'adb') as adb, patch.object(store.subprocess, 'run') as install, patch.object(screen_sync, 'prepare') as setup:
            self.assertEqual(self.stage()['state'], 'complete')
            adb.assert_not_called(); install.assert_not_called(); setup.assert_not_called()
        restarted = store.Store(server)
        template = restarted.templates()[0]
        self.assertEqual((template['type'], template['id']), ('APPS', screen_sync.PACKAGE_ID))
        self.assertIsNone(restarted.records()['studio.vivo.screensync:pc']['device_id'])
        restarted.remove_plugin(self.package['id'])
        self.assertEqual(restarted.templates(), [])
        with patch.object(restarted, 'install_on_core') as install, patch.object(store, 'inspect_apk'):
            restarted.deploy_dependencies(self.rows(), 'core', lambda _: None)
            install.assert_called_once()  # Placed widgets retain their dependency.

    def test_no_widget_means_no_device_or_package_work(self):
        self.stage()
        with patch.object(server, 'adb') as adb, patch.object(self.service, 'install_on_core') as install:
            self.service.deploy_dependencies(profiles(), 'core', lambda _: None)
            adb.assert_not_called(); install.assert_not_called()

    def test_any_core_app_can_be_staged_and_deployed_as_background(self):
        self.package.update(id='publisher.example', name='Example app')
        self.package['android'].update(packageId='dk.example.background', signerSha256='a'*64)
        with patch.object(server, 'adb') as adb:
            self.assertEqual(self.stage()['state'], 'complete')
            adb.assert_not_called()
        app=dict(id='dk.example.background', name='Example app', settings=dict(launch=True))
        with patch.object(self.service, 'install_on_core') as install, patch.object(store, 'inspect_apk'):
            self.service.deploy_dependencies(profiles(), 'core', lambda _:None, [app])
            self.assertEqual(install.call_args.kwargs['background'],app)
        self.assertEqual(self.service.templates()[0]['id'],app['id'])

    def test_hidden_apps_persist_without_entering_core_layout_and_stop_on_removal(self):
        self.stage()
        snapshot=dict(target='192.168.1.20:5555',device_id='core',model='CB01',profiles=profiles(),backup='backup.xml')
        hidden=[dict(id=screen_sync.PACKAGE_ID,name='Vivo Screen Sync',settings=dict(enabled=True,wakeDelayMs=1500))]
        client=server.app.test_client();headers={'Host':'127.0.0.1:8741','X-Studio-Token':server.SESSION_TOKEN}
        with patch.dict(server.connection,target=snapshot['target'],snapshot=snapshot):
            draft=client.get('/api/editor',headers=headers).json['draft']
            draft=client.post('/api/editor/draft',headers=headers,json=dict(device_id='core',revision=draft['revision'],profiles=profiles(),background_apps=hidden)).json['draft']
            self.assertEqual(client.get('/api/editor',headers=headers).json['draft']['background_apps'],hidden)
            with patch.object(server,'read_snapshot',return_value=snapshot),patch.object(editor,'wake_for_deploy'),patch.object(store,'inspect_apk'),patch.object(server.store,'install_on_core') as install,patch.object(server.native_widgets,'prepare'),patch.object(server.native_widgets,'configure'),patch.object(editor.bridge,'request') as send,patch.object(server,'adb',return_value='Status: ok'),patch.object(server,'parse_profiles',return_value={'profiles':profiles()}):
                response=client.post('/api/editor/deploy',headers=headers,json=dict(device_id='core',revision=draft['revision']))
            self.assertEqual(response.status_code,200,response.json)
            self.assertEqual(install.call_args.kwargs['background'],hidden[0])
            self.assertNotIn(screen_sync.PACKAGE_ID,str(send.call_args.args[-1]))
            self.assertEqual(response.json['draft']['background_apps'],hidden)
            self.assertEqual(editor.saved_background(server,'core'),hidden)
            draft=response.json['draft']
            draft=client.post('/api/editor/draft',headers=headers,json=dict(device_id='core',revision=draft['revision'],profiles=profiles(),background_apps=[])).json['draft']
            with patch.object(server,'read_snapshot',return_value=response.json['snapshot']),patch.object(editor,'wake_for_deploy'),patch.object(server.native_widgets,'prepare'),patch.object(server.native_widgets,'configure'),patch.object(editor.bridge,'request'),patch.object(server,'adb',return_value='Status: ok'),patch.object(server,'parse_profiles',return_value={'profiles':profiles()}),patch.object(screen_sync,'start_sync') as stop:
                response=client.post('/api/editor/deploy',headers=headers,json=dict(device_id='core',revision=draft['revision']))
            self.assertEqual(response.status_code,200,response.json)
            stop.assert_called_once_with(server,snapshot['target'],False)
            self.assertEqual(editor.saved_background(server,'core'),[])

    def test_invalid_background_settings_are_rejected(self):
        for app in [dict(id='com.ultrabar.launch',name='Core',settings={}),dict(id=screen_sync.PACKAGE_ID,name='Sync',settings=dict(wakeDelayMs=-1)),dict(id='dk.example.app',name='App',settings=dict(command='bad'))]:
            with self.assertRaises((editor.EditError,store.StoreError)):
                editor.validate_background([app])

    def test_tampered_package_stops_before_device_access(self):
        self.stage()
        (server.DATA_DIR/'store/app-packages'/(self.package['artifact']['sha256']+'.apk')).write_bytes(b'changed')
        with patch.object(server, 'adb') as adb, patch.object(store, 'inspect_apk') as inspect:
            with self.assertRaisesRegex(store.StoreError, 'integrity'):
                self.service.deploy_dependencies(self.rows(), 'core', lambda _: None)
            adb.assert_not_called(); inspect.assert_not_called()

    def test_wrong_signing_identity_never_reaches_device(self):
        self.package['android']['signerSha256'] = 'a'*64
        with patch.object(server, 'adb') as adb:
            self.assertEqual(self.stage()['state'], 'error')
            self.assertEqual(self.service.records(), {})
            adb.assert_not_called()

    def test_deploy_checks_identity_installs_then_configures(self):
        self.stage()
        calls = []
        def adb(*args, **kwargs):
            return {'ro.serialno':'core', 'ro.product.cpu.abi':'armeabi-v7a', 'ro.build.version.sdk':'29'}.get(args[-1], ' versionCode=4')
        with patch.dict(server.connection, target='192.168.1.20:5555', snapshot=dict(device_id='core', model='CB01')), patch.object(server, 'adb', side_effect=adb), patch.object(store, 'inspect_apk'), patch.object(screen_sync, 'prepare', side_effect=lambda *a: calls.append('prepare') or (b'config', b'cert')), patch.object(screen_sync, 'configure', side_effect=lambda *a: calls.append('configure')), patch.object(store.subprocess, 'run', side_effect=lambda *a, **kw: calls.append('install') or SimpleNamespace(returncode=0, stdout=b'Success')):
            self.service.deploy_dependencies(self.rows(), 'core', lambda _: None)
        self.assertEqual(calls, ['prepare', 'install', 'configure'])
        with patch.dict(server.connection, target='192.168.1.20:5555', snapshot=dict(device_id='other', model='CB01')), patch.object(store, 'inspect_apk'), patch.object(store.subprocess, 'run') as install:
            with self.assertRaisesRegex(store.StoreError, 'changed'):
                self.service.deploy_dependencies(self.rows(), 'core', lambda _: None)
            install.assert_not_called()

    def test_deploy_route_prepares_dependency_before_layout_and_aborts_on_failure(self):
        snapshot = dict(target='192.168.1.20:5555', device_id='core', model='CB01', profiles=profiles(), backup='backup.xml')
        client = server.app.test_client()
        headers = {'Host':'127.0.0.1:8741', 'X-Studio-Token':server.SESSION_TOKEN}
        with patch.dict(server.connection, target=snapshot['target'], snapshot=snapshot):
            draft = client.get('/api/editor', headers=headers).json['draft']
            draft = client.post('/api/editor/draft', headers=headers, json=dict(device_id='core', revision=draft['revision'], profiles=self.rows())).json['draft']
            events = []
            def prepare(rows, device, notify, background=None):
                self.assertEqual(rows, self.rows()); events.append('dependency')
            with patch.object(server, 'read_snapshot', return_value=snapshot), patch.object(editor, 'wake_for_deploy'), patch.object(server.store, 'deploy_dependencies', side_effect=prepare), patch.object(server.native_widgets, 'prepare'), patch.object(server.native_widgets, 'configure'), patch.object(editor.bridge, 'request', side_effect=lambda *a:events.append('layout')), patch.object(server, 'adb', return_value='Status: ok'), patch.object(server, 'parse_profiles', return_value={'profiles':self.rows()}):
                response = client.post('/api/editor/deploy', headers=headers, json=dict(device_id='core', revision=draft['revision']))
            self.assertEqual(response.status_code, 200, response.json)
            self.assertEqual(events, ['dependency', 'layout'])
            draft = response.json['draft']
            with patch.object(server, 'read_snapshot', return_value=response.json['snapshot']), patch.object(editor, 'wake_for_deploy'), patch.object(server.store, 'deploy_dependencies', side_effect=store.StoreError('Setup failed')), patch.object(editor.bridge, 'request') as write:
                response = client.post('/api/editor/deploy', headers=headers, json=dict(device_id='core', revision=draft['revision']))
                self.assertEqual(response.status_code, 400)
                write.assert_not_called()
