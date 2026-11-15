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
     notes='New features\n\n- Remember CoreBAR\n- Start with Windows\n<script>window.notesExecuted=true</script>'
     page.route('**/api/updates',lambda r:r.fulfill(json=dict(update_available=True,download_available=True,latest_version='99.0.0',current_version='0.19.0',release_notes=notes)))
     job={'state':'idle'};launches=[]
     page.route('**/api/updates/status',lambda r:r.fulfill(json=job))
     def download(r):
      job.update(state='downloading',message='Downloading...',received=50,total=100);r.fulfill(json=job)
     page.route('**/api/updates/download',download)
     page.route('**/api/updates/install',lambda r:(launches.append(True),r.fulfill(json=dict(state='launched',message='Installer opened.'))))
     page.goto('http://'+host)
     page.locator('#updates-open').click();expect(page.locator('#updates-download')).to_be_visible()
     expect(page.locator('#updates-notes-body')).to_have_text(notes)
     self.assertFalse(page.evaluate('!!window.notesExecuted'))
     self.assertEqual(page.locator('#updates-notes-body script').count(),0)
     page.set_viewport_size({'width':390,'height':844})
     self.assertTrue(page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
     page.set_viewport_size({'width':1280,'height':800})
     page.locator('#updates-download').click();expect(page.locator('#updates-status')).to_contain_text('50%')
     expect(page.locator('#updates-install')).not_to_be_visible();self.assertFalse(launches)
     job.update(state='ready',message='Download verified.')
     expect(page.locator('#updates-install')).to_be_visible()
     page.once('dialog',lambda d:d.dismiss());page.locator('#updates-install').click();self.assertFalse(launches)
     page.evaluate("()=>{window.studioEditor.saveBeforeUpdate=async()=>{throw new Error('Draft save failed')}}")
     page.once('dialog',lambda d:d.accept());page.locator('#updates-install').click()
     expect(page.locator('#updates-status')).to_have_text('Draft save failed');self.assertFalse(launches)
     page.evaluate("()=>{window.studioEditor.saveBeforeUpdate=async()=>{window.savedForUpdate=true}}")
     page.once('dialog',lambda d:d.accept());page.locator('#updates-install').click()
     self.assertTrue(page.evaluate('window.savedForUpdate'))
     expect(page.locator('#updates-status')).to_have_text('Installer opened.');self.assertEqual(len(launches),1)
     page.keyboard.press('Escape');page.locator('#updates-open').click()
     expect(page.locator('#updates-notes-body')).to_have_text(notes)
     job.update(state='idle')
     page.route('**/api/updates',lambda r:r.fulfill(json=dict(update_available=False,download_available=True,latest_version='99.0.0',current_version='99.0.0',release_notes='Already installed release notes.')))
     page.locator('#updates-check').click()
     expect(page.locator('#updates-status')).to_contain_text('up to date')
     expect(page.locator('#updates-notes-body')).to_have_text('Already installed release notes.')
     page.route('**/api/updates',lambda r:r.fulfill(json=dict(update_available=False,latest_version='99.0.0',current_version='99.0.0')))
     page.locator('#updates-check').click()
     expect(page.locator('#updates-notes-body')).to_contain_text('No release notes')
     browser.close()
   finally:http.shutdown()
