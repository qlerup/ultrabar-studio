"""Startup retry, reconnect and settings without touching devices or login startup."""
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from werkzeug.serving import make_server
from playwright.sync_api import sync_playwright, expect
import server


class SettingsBrowserTests(unittest.TestCase):
    def test_core_connection_distinguishes_module_status_failure(self):
        http = make_server('127.0.0.1', 0, server.app, threaded=True)
        host = f'127.0.0.1:{http.server_port}'
        with patch.dict(server.app.config, ALLOWED_HOSTS={host}):
            threading.Thread(target=http.serve_forever, daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch(channel='msedge')
                    page = browser.new_page()
                    target = '192.168.1.20:5555'
                    module_error = 'Could not read current module status from CoreBridge. Retrying automatically.'
                    hardware = {'devices': [], 'status_error': module_error}
                    snapshot = dict(target=target, model='CB01', device_id='core', profiles=[],
                                    hardware=hardware, read_at='2026-11-15T12:00:00Z')
                    page.route('**/api/**', lambda r: r.fulfill(json={}))
                    page.route('**/api/preferences', lambda r: r.fulfill(json={'target': target, 'setup_seen': True}))
                    page.route('**/api/connect', lambda r: r.fulfill(json=snapshot))
                    page.route('**/api/hardware', lambda r: r.fulfill(json={'target': target, 'hardware': hardware}))
                    page.clock.install()
                    page.goto('http://'+host)
                    badge = page.locator('#connection-badge')
                    module_status = page.locator('#hardware-status')
                    core_status = page.locator('.core-unit .unit-state')
                    expect(badge).to_have_class('badge connected')

                    # Subsequent status polls can read the Core even if CoreBridge fails.
                    with page.expect_response('**/api/hardware'):
                        page.clock.fast_forward(5000)
                    page.wait_for_function('!hardwarePolling')
                    expect(module_status).to_have_text(module_error)
                    expect(badge).to_have_class('badge connected')
                    expect(core_status).to_have_text('Connected via ADB')

                    page.route('**/api/hardware', lambda r: r.fulfill(status=502, json={'error': 'Core is offline.'}))
                    page.clock.fast_forward(5000)
                    expect(badge).to_have_text('Not connected')
                    expect(core_status).to_have_text('Connection unverified')

                    # The ADB connection can return while CoreBridge is still unavailable.
                    page.unroute('**/api/hardware')
                    page.route('**/api/hardware', lambda r: r.fulfill(json={'target': target, 'hardware': hardware}))
                    page.clock.fast_forward(5000)
                    expect(module_status).to_have_text(module_error)
                    expect(badge).to_have_class('badge connected')
                    expect(core_status).to_have_text('Connected via ADB')

                    hardware['status_error'] = None
                    page.clock.fast_forward(5000)
                    expect(module_status).to_contain_text('updates every 5 seconds')
                    expect(badge).to_have_class('badge connected')
                    browser.close()
            finally:
                http.shutdown()

    def test_reconnect_retry_reload_and_settings(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(server, 'DATA_DIR', Path(tmp)):
            http = make_server('127.0.0.1', 0, server.app, threaded=True)
            host = f'127.0.0.1:{http.server_port}'
            with patch.dict(server.app.config, ALLOWED_HOSTS={host}):
                threading.Thread(target=http.serve_forever, daemon=True).start()
                try:
                    with sync_playwright() as pw:
                        browser = pw.chromium.launch(channel='msedge')
                        page = browser.new_page(viewport={'width': 1440, 'height': 960})
                        page.route('**/api/updates',lambda r:r.fulfill(json=dict(update_available=False,current_version=server.updates.VERSION,latest_version=server.updates.VERSION)))
                        errors = []
                        page.on('pageerror', lambda e: errors.append(str(e)))
                        target = '192.168.1.20:5555'
                        connections = []
                        saved = {'start_with_windows': False, 'startup_supported': True}
                        snapshot = dict(target=target, model='CB01', device_id='core', profiles=[], hardware={'devices': []}, read_at='2026-11-15T12:00:00Z')
                        page.route('**/api/**', lambda r: r.fulfill(json={}))
                        page.route('**/api/preferences', lambda r: r.fulfill(json={'target': target, 'setup_seen': True}))
                        def connect(r):
                            connections.append(r.request.post_data_json['target'])
                            if len(connections) == 1:
                                r.fulfill(status=502, json={'error': 'Core is offline.'})
                            else:
                                r.fulfill(json=snapshot)
                        page.route('**/api/connect', connect)
                        def settings(r):
                            if r.request.method == 'POST':
                                saved.update(r.request.post_data_json)
                            r.fulfill(json=saved)
                        page.route('**/api/settings', settings)
                        page.clock.install()
                        page.goto('http://'+host)
                        expect(page.locator('#notice')).to_contain_text('Retrying automatically')
                        page.clock.fast_forward(15000)
                        expect(page.locator('#connection-badge')).to_contain_text('Connected')
                        self.assertEqual(connections, [target, target])
                        expect(page.locator('#connection-dialog')).not_to_be_visible()
                        page.reload()
                        expect(page.locator('#connection-badge')).to_contain_text('Connected')
                        self.assertEqual(len(connections), 3)
                        page.locator('#settings-open').click()
                        expect(page.locator('#start-with-windows')).to_be_enabled()
                        page.locator('#start-with-windows').check()
                        expect(page.locator('#settings-status')).to_have_text('Settings saved.')
                        page.screenshot(path=str(Path(__file__).parent/'data/qa/settings-desktop.png'))
                        page.set_viewport_size({'width':390, 'height':844})
                        page.clock.run_for(100)
                        page.screenshot(path=str(Path(__file__).parent/'data/qa/settings-mobile.png'))
                        self.assertTrue(page.evaluate('document.documentElement.scrollWidth <= innerWidth'), page.evaluate("[...document.querySelectorAll('body *')].filter(e=>e.getBoundingClientRect().right>innerWidth+1&&e.getBoundingClientRect().width).map(e=>[e.tagName,e.id,e.className,e.getBoundingClientRect().right]).slice(0,12)"))
                        page.keyboard.press('Escape')
                        page.locator('#settings-open').click()
                        expect(page.locator('#start-with-windows')).to_be_checked()
                        page.route('**/api/settings', lambda r:r.fulfill(status=502,json={'error':'Could not save settings.'}))
                        page.locator('#start-with-windows').uncheck()
                        expect(page.locator('#settings-status')).to_have_text('Could not save settings.')
                        expect(page.locator('#start-with-windows')).to_be_checked()
                        self.assertFalse(errors, errors)
                        browser.close()
                finally:
                    http.shutdown()
