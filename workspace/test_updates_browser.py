"""Update dialog lifecycle with no installer execution or external traffic."""
import threading,unittest
from unittest.mock import patch
from werkzeug.serving import make_server
from playwright.sync_api import sync_playwright,expect
import server

class UpdateUITests(unittest.TestCase):
 def test_download_then_explicit_install(self):
  http=make_server('127.0.0.1',0,server.app,threaded=True);host=f'127.0.0.1:{http.server_port}'
  with patch.dict(server.app.config,ALLOWED_HOSTS={host}):
   threading.Thread(target=http.serve_forever,daemon=True).start()
   try:
    with sync_playwright() as pw:
     browser=pw.chromium.launch(channel='msedge');page=browser.new_page()
     page.route('**/api/preferences',lambda r:r.fulfill(json=dict(setup_seen=True,target='')))
     page.route('**/api/updates',lambda r:r.fulfill(json=dict(update_available=True,download_available=True,latest_version='99.0.0',current_version='0.19.0')))
     job={'state':'idle'};launches=[]
     page.route('**/api/updates/status',lambda r:r.fulfill(json=job))
     def download(r):
      job.update(state='downloading',message='Downloading...',received=50,total=100);r.fulfill(json=job)
     page.route('**/api/updates/download',download)
     page.route('**/api/updates/install',lambda r:(launches.append(True),r.fulfill(json=dict(state='launched',message='Installer opened.'))))
     page.goto('http://'+host)
     page.locator('#updates-open').click();expect(page.locator('#updates-download')).to_be_visible()
     page.locator('#updates-download').click();expect(page.locator('#updates-status')).to_contain_text('50%')
     expect(page.locator('#updates-install')).not_to_be_visible();self.assertFalse(launches)
     job.update(state='ready',message='Download verified.')
     expect(page.locator('#updates-install')).to_be_visible()
     page.once('dialog',lambda d:d.dismiss());page.locator('#updates-install').click();self.assertFalse(launches)
     page.once('dialog',lambda d:d.accept());page.locator('#updates-install').click()
     expect(page.locator('#updates-status')).to_have_text('Installer opened.');self.assertEqual(len(launches),1)
     browser.close()
   finally:http.shutdown()
