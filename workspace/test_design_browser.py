"""Offline responsive acceptance: real UI with saved profile fixture; no device writes."""
import tempfile, threading, unittest
from pathlib import Path
from unittest.mock import patch
from werkzeug.serving import make_server
from playwright.sync_api import sync_playwright, expect
import server

class DesignTests(unittest.TestCase):
 def test_workspace_at_window_sizes(self):
  from test_editor import profiles as fixture_profiles
  profiles=fixture_profiles()
  profiles[0]['module'] += [dict(serialNo='0000000000000002',productId='VIVO_CUBE',config=[]),dict(serialNo='0000000000000003',productId='KNOB_KEY',config=[])]
  devices=[dict(serial=m['serialNo'],type=m['productId'],name=m['productId'],online=True) for m in profiles[0]['module']]
  snapshot=dict(target='192.168.1.148:5555',model='CB01',device_id='preview',read_at='2026-11-14T20:00:00Z',profiles=profiles,backup='fixture.xml',hardware=dict(devices=devices),layout_order=[])
  with tempfile.TemporaryDirectory() as tmp, patch.object(server,'DATA_DIR',Path(tmp)), patch.dict(server.connection,target=snapshot['target'],snapshot=snapshot):
   http=make_server('127.0.0.1',0,server.app,threaded=True);host=f'127.0.0.1:{http.server_port}'
   with patch.dict(server.app.config,ALLOWED_HOSTS={host}):
    threading.Thread(target=http.serve_forever,daemon=True).start()
    try:
     with sync_playwright() as pw:
      browser=pw.chromium.launch(channel='msedge');page=browser.new_page()
      errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
      page.route('**/api/preferences',lambda r:r.fulfill(json=dict(target=snapshot['target'],setup_seen=True)))
      page.route('**/api/connect',lambda r:r.fulfill(json=snapshot))
      page.route('**/api/hardware',lambda r:r.fulfill(json=dict(target=snapshot['target'],hardware=snapshot['hardware'])))
      page.route('**/api/screen*',lambda r:r.fulfill(status=502,json=dict(error='Preview unavailable in offline test')))
      page.route('**/api/cube-previews',lambda r:r.fulfill(json=dict(previews={})))
      page.route('**/api/editor/catalog',lambda r:r.fulfill(json=dict(apps=[])))
      page.route('**/api/pc/**',lambda r:r.fulfill(json=dict(actions=[],metrics={})))
      page.route('**/api/discover',lambda r:r.fulfill(json=dict(devices=[])))
      page.goto('http://'+host);page.locator('#connection-open').click();page.locator('#target').fill(snapshot['target']);page.locator('#connect').click()
      expect(page.locator('#workspace')).to_be_visible();expect(page.locator('#connection-dialog')).not_to_be_visible()
      page.route('**/api/layout',lambda r:r.fulfill(json=dict(ok=True)))
      page.set_viewport_size(dict(width=1920,height=960))
      # Both asymmetric and reordered layouts keep Core at the viewport midpoint.
      for order in [['core']+[d['serial'] for d in devices], [devices[0]['serial'],'core']+[d['serial'] for d in devices[1:]]]:
       page.evaluate('(order)=>{snapshot.layout_order=order;renderHardware();}',order)
       assert page.evaluate("""()=>{const s=document.querySelector('#hardware-preview').getBoundingClientRect(),c=document.querySelector('.core-unit').getBoundingClientRect();return Math.abs((s.left+s.right-c.left-c.right)/2)<1;}""")
      page.locator('.core-unit').focus();page.keyboard.press('Alt+ArrowRight')
      expect(page.locator('#layout-feedback')).to_have_text('Layout saved')
      assert page.evaluate('visibleLayoutOrder()[2]')=='core'
      for width in [1920,1440,1024,850,640,390]:
       page.set_viewport_size(dict(width=width,height=960))
       expect(page.locator('#draft-save')).to_be_enabled() if page.locator('#editor-content').is_visible() else None
       page.locator('#nav-overview').click()
       expect(page.locator('#overview-content')).to_be_visible()
       assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),('overview',width)
       page.screenshot(path=str(server.ROOT/f'data/qa/design-overview-{width}.png'),full_page=True)
       page.locator('#nav-editor').click();expect(page.locator('#core-canvas .canvas-widget').first).to_be_visible()
       page.wait_for_timeout(100)
       assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),('editor',width)
       page.screenshot(path=str(server.ROOT/f'data/qa/design-editor-{width}.png'),full_page=True)
       page.locator('#connection-open').click();expect(page.locator('#discover')).to_be_visible();page.keyboard.press('Escape')
      assert not errors,errors
      browser.close()
    finally:http.shutdown()
