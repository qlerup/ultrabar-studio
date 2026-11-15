import tempfile,threading,time,unittest,json
from pathlib import Path
from unittest.mock import patch
from werkzeug.serving import make_server
from playwright.sync_api import sync_playwright,expect
import server,store
from test_store import fixture,icon_fixture

class StoreBrowserTests(unittest.TestCase):
 def test_catalog_approval_install_remove_and_offline(self):
  p,raw=fixture();approved=[];icon,icon_raw=icon_fixture();p["icon"]=icon;p['publisher']='qlerup';p['source']='https://github.com/qlerup/studio-system-monitor/blob/'+'a'*40+'/widget.json'
  def download(url,limit,destination=None):
   if destination is None:return icon_raw
   destination.write(raw);return len(raw)
  with tempfile.TemporaryDirectory() as tmp,patch.object(server,'DATA_DIR',Path(tmp)),patch.object(store,'catalog',side_effect=lambda:list(approved)),patch.object(store,'fetch',side_effect=download),patch.object(store.webbrowser,'open',return_value=True) as browser_open:
   server.store.job=None
   http=make_server('127.0.0.1',0,server.app,threaded=True);host=f'127.0.0.1:{http.server_port}'
   with patch.dict(server.app.config,ALLOWED_HOSTS={host}):
    threading.Thread(target=http.serve_forever,daemon=True).start()
    try:
     with sync_playwright() as pw:
      browser=pw.chromium.launch(channel='msedge');page=browser.new_page(viewport=dict(width=1440,height=960));errors=[]
      page.on('pageerror',lambda e:errors.append(str(e)))
      page.route('**/api/preferences',lambda r:r.fulfill(json=dict(setup_seen=True,target='')))
      page.route('**/api/discover',lambda r:r.fulfill(json=dict(devices=[])))
      page.goto('http://'+host);page.locator('#nav-store').click()
      expect(page.locator('#store-packages')).to_contain_text('No approved packages yet')
      approved.append(p);page.locator('#store-refresh').click()
      expect(page.locator('.store-card')).to_contain_text('Test presets')
      expect(page.locator('.store-publisher')).to_have_text('Uploaded by @qlerup')
      expect(page.locator('.brand-mark img')).to_be_visible()
      for name,suffix in [('Repository',''),('Issues','/issues'),('Pull requests','/pulls')]:
       link=page.locator('.store-links').get_by_role('link',name=name,exact=True)
       expect(link).to_have_attribute('href','https://github.com/qlerup/studio-system-monitor'+suffix)
       link.click();page.wait_for_timeout(100)
       browser_open.assert_called_with('https://github.com/qlerup/studio-system-monitor'+suffix)
      expect(page.locator('.store-card-icon img')).to_be_visible()
      page.wait_for_function("document.querySelector('.store-card-icon img')?.naturalWidth===256")
      page.locator('.store-card').get_by_role('button',name='Install',exact=True).click()
      expect(page.locator('#store-install-dialog')).to_be_visible()
      page.locator('#store-install-cancel').click()
      self.assertEqual(server.store.records(),{})
      page.locator('.store-card').get_by_role('button',name='Install',exact=True).click()
      page.locator('#store-install-confirm').click()
      expect(page.locator('#store-status')).to_contain_text('Installed.',timeout=15000)
      self.assertEqual(server.store.templates()[0]['name'],'Test clock')
      expect(page.locator('.store-card').get_by_role('button',name='Installed',exact=True)).to_be_disabled()
      page.screenshot(path=str(server.ROOT/'data/qa/store-desktop.png'))
      page.set_viewport_size(dict(width=390,height=844));assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
      page.screenshot(path=str(server.ROOT/'data/qa/store-mobile.png'))
      page.route('**/api/store',lambda r:r.fulfill(status=502,json=dict(error='Offline test')))
      page.locator('#store-refresh').click();expect(page.locator('#store-status')).to_contain_text('Offline test')
      expect(page.locator('.store-card')).to_contain_text('Test presets')
      page.on('dialog',lambda d:d.accept())
      page.locator('.store-card').get_by_role('button',name='Remove from library').click()
      expect(page.locator('#store-status')).to_have_text('Package removed from library.')
      self.assertEqual(server.store.templates(),[])
      folder=Path(tmp)/'local-package';folder.mkdir()
      (folder/'plugin.json').write_bytes(raw);(folder/'icon.png').write_bytes(icon_raw)
      (folder/'manifest.json').write_text(json.dumps(p))
      with patch.object(server,'package_folder_picker',return_value=[str(folder)],create=True):
       page.locator('#store-local-folder').click()
       expect(page.locator('#store-install-summary')).to_contain_text('Local development package')
       page.locator('#store-install-cancel').click();self.assertEqual(server.store.templates(),[])
       page.locator('#store-local-folder').click();page.locator('#store-install-confirm').click()
       expect(page.locator('#store-status')).to_contain_text('Installed.',timeout=15000)
      expect(page.locator('.store-publisher').filter(has_text='LOCAL DEVELOPMENT')).to_be_visible()
      self.assertEqual(server.store.templates()[0]['_storePackage'],'local.studio.test')
      page.screenshot(path=str(server.ROOT/'data/qa/store-local-mobile.png'))
      page.set_viewport_size(dict(width=1440,height=960));page.screenshot(path=str(server.ROOT/'data/qa/store-local-desktop.png'))
      page.locator('.store-card').filter(has_text='LOCAL DEVELOPMENT').get_by_role('button',name='Remove from library').click()
      expect(page.locator('#store-status')).to_have_text('Package removed from library.')
      page.locator('#nav-overview').click();expect(page.locator('#store-content')).not_to_be_visible()
      assert not errors,errors
      browser.close()
    finally:http.shutdown()
