import tempfile, threading, unittest
from pathlib import Path
from unittest.mock import patch
from werkzeug.serving import make_server
from playwright.sync_api import sync_playwright, expect
import server

class OnboardingTests(unittest.TestCase):
 def test_first_run_connection_and_reopen(self):
  with tempfile.TemporaryDirectory() as tmp, patch.object(server, 'DATA_DIR', Path(tmp)):
   http=make_server('127.0.0.1',0,server.app,threaded=True)
   host=f'127.0.0.1:{http.server_port}'
   with patch.dict(server.app.config, {'ALLOWED_HOSTS':{host}}):
    threading.Thread(target=http.serve_forever,daemon=True).start()
    try:
     with sync_playwright() as pw:
      browser=pw.chromium.launch(channel="msedge")
      page=browser.new_page(viewport={'width':1440,'height':960})
      errors=[]; page.on('pageerror',lambda e: errors.append(str(e)))
      page.route('**/api/discover',lambda route:route.fulfill(json={'devices':[]}))
      page.goto('http://'+host)
      expect(page.locator('#setup-guide')).to_be_visible()
      page.locator('#guide-find-devices').click()
      expect(page.locator('#connection-dialog')).to_be_visible()
      expect(page.locator('#discover')).to_be_enabled()
      page.locator('#target').fill('192.168.1.148:5555')
      page.route('**/api/connect',lambda route:route.fulfill(status=502,json={'error':'Device is offline'}))
      page.locator('#connect').click()
      expect(page.locator('#connection-notice')).to_have_text('Device is offline')
      page.keyboard.press('Escape')
      expect(page.locator('#connection-dialog')).not_to_be_visible()
      page.reload()
      expect(page.locator('#connection-open')).to_be_visible()
      expect(page.locator('#setup-guide')).not_to_be_visible()
      page.locator('#connection-open').click()
      page.locator('#connection-dialog .setup-guide-trigger').first.click()
      expect(page.locator('#setup-guide')).to_be_visible()
      page.keyboard.press('Escape')
      page.screenshot(path=str(Path(__file__).parent/'data/qa/connection-dialog.png'))
      page.set_viewport_size({'width':390,'height':844})
      assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
      page.screenshot(path=str(Path(__file__).parent/'data/qa/connection-mobile.png'))
      page.keyboard.press('Escape')
      page.route('**/api/updates',lambda r:r.fulfill(json=dict(current_version='0.14.0',latest_version='0.15.0',update_available=True,installer_available=True)))
      page.route('**/api/updates/open',lambda r:r.fulfill(json=dict(ok=True)))
      page.locator('#updates-open').click()
      expect(page.locator('#updates-status')).to_contain_text('0.15.0')
      expect(page.locator('#updates-download')).to_be_visible()
      page.locator('#updates-download').click()
      page.screenshot(path=str(Path(__file__).parent/'data/qa/updates-mobile.png'))
      page.unroute('**/api/updates')
      page.route('**/api/updates',lambda r:r.fulfill(status=502,json=dict(error='Offline. Try again.')))
      page.locator('#updates-check').click()
      expect(page.locator('#updates-status')).to_have_text('Offline. Try again.')
      expect(page.locator('#updates-download')).not_to_be_visible()
      expect(page.locator('#updates-check')).to_be_enabled()
      page.unroute('**/api/updates')
      page.route('**/api/updates',lambda r:r.fulfill(json=dict(current_version='0.14.0',latest_version='0.14.0',update_available=False,installer_available=True)))
      page.locator('#updates-check').click()
      expect(page.locator('#updates-status')).to_contain_text('up to date')
      page.keyboard.press('Escape')
      expect(page.locator('#updates-dialog')).not_to_be_visible()

      assert not errors, errors
      browser.close()
    finally: http.shutdown()

