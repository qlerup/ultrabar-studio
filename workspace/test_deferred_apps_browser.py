"""Install Screen Sync offline, then place its library card in a draft."""
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from werkzeug.serving import make_server
from playwright.sync_api import sync_playwright, expect
import server
import store
import screen_sync
from test_deferred_apps import app_fixture
from test_editor import profiles


class DeferredAppBrowserTests(unittest.TestCase):
    def test_install_without_core_then_drag_from_library(self):
        package, raw = app_fixture()
        snapshot = dict(target='192.168.1.20:5555', device_id='core', model='CB01', profiles=profiles(), backup='fixture.xml', read_at='2026-11-15T12:00:00Z', hardware=dict(devices=[]))
        def fetch(url, limit, destination):
            destination.write(raw); return len(raw)
        with tempfile.TemporaryDirectory() as tmp, patch.object(server, 'DATA_DIR', Path(tmp)), patch.dict(server.connection, target=None, snapshot=None), patch.object(server.store, 'job', None), patch.object(store, 'catalog', return_value=[package]), patch.object(store, 'fetch', side_effect=fetch), patch.object(store, 'inspect_apk'), patch.object(server, 'adb') as adb, patch.object(screen_sync, 'configure') as configure:
            http = make_server('127.0.0.1', 0, server.app, threaded=True)
            host = f'127.0.0.1:{http.server_port}'
            with patch.dict(server.app.config, ALLOWED_HOSTS={host}):
                threading.Thread(target=http.serve_forever, daemon=True).start()
                try:
                    with sync_playwright() as pw:
                        browser = pw.chromium.launch(channel='msedge')
                        page = browser.new_page(viewport=dict(width=1440, height=1000))
                        errors = []
                        page.on('pageerror', lambda e:errors.append(str(e)))
                        page.route('**/api/preferences', lambda r:r.fulfill(json=dict(target='', setup_seen=True)))
                        page.route('**/api/store/stats*', lambda r:r.fulfill(json=dict(packages={})))
                        page.route('**/api/discover', lambda r:r.fulfill(json=dict(devices=[])))
                        page.route('**/api/pc/**', lambda r:r.fulfill(json={}))
                        page.route('**/api/pc', lambda r:r.fulfill(json=dict(actions=[], metrics={})))
                        page.route('**/api/hardware', lambda r:r.fulfill(json=dict(target=snapshot['target'], hardware=snapshot['hardware'])))
                        page.route('**/api/screen*', lambda r:r.fulfill(status=502, json=dict(error='Offline preview')))
                        page.route('**/api/cube-previews', lambda r:r.fulfill(json=dict(previews={})))
                        # Already installed apps must not duplicate the Store entry.
                        page.route('**/api/editor/catalog', lambda r:r.fulfill(json=dict(apps=[dict(id=screen_sync.PACKAGE_ID, type='APPS', name='Vivo Screen Sync', iconScale=100)])))
                        page.goto('http://'+host)
                        page.locator('#nav-store').click()
                        install = page.locator('.store-card').get_by_role('button', name='Install', exact=True)
                        expect(install).to_be_enabled()
                        install.click()
                        expect(page.locator('#store-install-summary')).to_contain_text('No CoreBAR connection is needed')
                        page.locator('#store-install-confirm').click()
                        expect(page.locator('#store-status')).to_contain_text('Installed.', timeout=15000)
                        adb.assert_not_called(); configure.assert_not_called()
                        expect(page.locator('.store-card').get_by_role('button', name='Installed', exact=True)).to_be_disabled()
                        def connect(r):
                            server.connection.update(target=snapshot['target'], snapshot=snapshot)
                            r.fulfill(json=snapshot)
                        page.route('**/api/connect', connect)
                        page.locator('#nav-overview').click()
                        page.locator('#connection-open').click()
                        page.locator('#manual-connection summary').click()
                        page.locator('#target').fill(snapshot['target'])
                        page.locator('#connect').click()
                        expect(page.locator('#workspace')).to_be_visible()
                        page.locator('#nav-editor').click()
                        widget = page.locator('#widget-library').get_by_role('button', name='Vivo Screen Sync', exact=True)
                        expect(widget).to_have_count(1)
                        expect(page.locator('details[data-group="store"]')).to_contain_text('Vivo Screen Sync')
                        widget.scroll_into_view_if_needed()
                        source = widget.bounding_box()
                        target = page.locator('#core-screen').bounding_box()
                        page.mouse.move(source['x']+source['width']/2, source['y']+source['height']/2)
                        page.mouse.down()
                        page.mouse.move(target['x']+target['width']/2, target['y']+target['height']/2, steps=18)
                        page.mouse.up()
                        expect(page.locator('#core-canvas [aria-label="Vivo Screen Sync"]')).to_have_count(1)
                        expect(page.get_by_role('button',name='Run in background',exact=True)).to_have_count(0)
                        page.locator('#draft-save').click()
                        expect(page.locator('#editor-notice')).to_contain_text('Draft saved')
                        adb.assert_not_called(); configure.assert_not_called()
                        saved = page.request.get('http://'+host+'/api/editor', headers={'X-Studio-Token':server.SESSION_TOKEN}).json()['draft']
                        self.assertTrue(any(w['id']==screen_sync.PACKAGE_ID and w['type']=='APPS' for w in saved['profiles'][0]['homeData']))
                        page.screenshot(path=str(server.ROOT/'data/qa/screensync-library.png'))
                        page.set_viewport_size(dict(width=1920,height=1080))
                        card=page.locator('#core-canvas [aria-label="Vivo Screen Sync"]')
                        card.scroll_into_view_if_needed()
                        source=card.bounding_box();target=page.locator('#background-drop').bounding_box()
                        page.mouse.move(source['x']+source['width']/2,source['y']+source['height']/2)
                        page.mouse.down();page.mouse.move(target['x']+target['width']/2,target['y']+target['height']/2,steps=18);page.mouse.up()
                        expect(page.locator('#background-apps button')).to_have_count(1)
                        expect(page.locator('#core-canvas [aria-label="Vivo Screen Sync"]')).to_have_count(0)
                        expect(page.locator('#widget-properties')).to_contain_text('Background app settings')
                        page.locator('#background-wake-delay').fill('1750');page.locator('#background-wake-delay').press('Tab')
                        page.locator('#background-sync-mode').select_option('always')
                        page.locator('#draft-save').click()
                        expect(page.locator('#editor-notice')).to_contain_text('Draft saved')
                        saved=page.request.get('http://'+host+'/api/editor',headers={'X-Studio-Token':server.SESSION_TOKEN}).json()['draft']
                        self.assertEqual(saved['background_apps'][0]['settings'],dict(enabled=False,wakeDelayMs=1750))
                        self.assertFalse(any(w['id']==screen_sync.PACKAGE_ID for p in saved['profiles'] for w in p['homeData']))
                        page.screenshot(path=str(server.ROOT/'data/qa/background-apps-desktop.png'))
                        expect(page.get_by_role('button',name='Move onto bar',exact=True)).to_have_count(0)
                        chip=page.locator('#background-apps button')
                        source=chip.bounding_box();target=page.locator('#core-screen').bounding_box()
                        page.mouse.move(source['x']+source['width']/2,source['y']+source['height']/2)
                        page.mouse.down();page.mouse.move(target['x']+target['width']/2,target['y']+target['height']/2,steps=18);page.mouse.up()
                        expect(page.locator('#background-apps button')).to_have_count(0)
                        expect(page.locator('#core-canvas [aria-label="Vivo Screen Sync"]')).to_have_count(1)
                        expect(page.get_by_role('button',name='Run in background',exact=True)).to_have_count(0)
                        page.locator('#widget-undo').click()
                        expect(page.locator('#background-apps button')).to_have_count(1)
                        expect(page.locator('#core-canvas [aria-label="Vivo Screen Sync"]')).to_have_count(0)
                        page.locator('#background-apps button').click()
                        expect(page.locator('#background-wake-delay')).to_have_value('1750')
                        page.locator('#draft-save').click()
                        expect(page.locator('#editor-notice')).to_contain_text('Draft saved')
                        page.set_viewport_size(dict(width=390,height=844))
                        self.assertTrue(page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'))
                        page.locator('#background-drop').scroll_into_view_if_needed()
                        page.screenshot(path=str(server.ROOT/'data/qa/background-apps-mobile.png'))
                        adb.assert_not_called();configure.assert_not_called()
                        self.assertFalse(errors, errors)
                        browser.close()
                finally:
                    http.shutdown()
