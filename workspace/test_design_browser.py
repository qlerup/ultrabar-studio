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
  profiles[0]['homeData'] += [
   dict(id='studio_native_abcdef0123456789abcdef0123456789',type='PC_CONTROL',name='Legacy drive',param=dict(payload=dict(action='studioNative',params=dict(kind='disk',drive='all',accent='#94d9bb')))),
   dict(id='legacy-pc',type='PC_CONTROL',name='Original PC widget',param=dict(payload=dict(action='vendorAction',params={}))),
   dict(id='studio_native_0123456789abcdef0123456789abcdef',type='PC_CONTROL',name='Existing Store Clock',param=dict(payload=dict(action='studioNative',params=dict(kind='clock',packageId='studio.clock',widgetKey='clock',hourFormat='24',accent='#94d9bb'))))]

  profiles[0]['module'] += [dict(serialNo='0000000000000002',productId='VIVO_CUBE',config=[]),dict(serialNo='0000000000000003',productId='KNOB_KEY',config={})]
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
      page.route('**/api/store/installed',lambda r:r.fulfill(json=dict(widgets=[dict(id='clock',name='Store Clock',kind='clock',_widgetPackage=True,_storePackage='studio.clock',_storeVersion='1.0.0',hourFormat='24',showSeconds=True,showDate=True),dict(id='drive-usage',name='Drive usage',kind='disk',_widgetPackage=True,_storePackage='studio.drive.widget',_storeVersion='1.0.0'),dict(id='system-monitor',name='System Monitor',kind='cpu',kindOptions=['cpu','memory','gpu'],_widgetPackage=True,_storePackage='studio.system.widget',_storeVersion='1.0.0')])))
      page.route('**/api/editor/catalog',lambda r:r.fulfill(json=dict(apps=[])))
      page.route('**/api/pc',lambda r:r.fulfill(json=dict(actions=[],metrics=dict(disks=[dict(name='C:\\',percent=25,used_gb=25,total_gb=100)]),status='Test',native_status='Test')))
      page.route('**/api/pc/**',lambda r:r.fulfill(json=dict(actions=[],metrics={})))
      page.route('**/api/discover',lambda r:r.fulfill(json=dict(devices=[])))
      page.goto('http://'+host);page.locator('#connection-open').click();page.locator('#manual-connection summary').click();page.locator('#target').fill(snapshot['target']);page.locator('#connect').click()
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
      page.set_viewport_size(dict(width=1440,height=960))
      page.locator('#nav-editor').click()
      expect(page.locator('details[data-group="store"] .library-item')).to_have_count(3)
      expect(page.locator('details[data-group="installed"]').get_by_role('button',name='Original PC widget',exact=True,include_hidden=True)).to_have_count(1)
      expect(page.locator('details[data-group="store"]').get_by_role('button',name='Original PC widget',exact=True,include_hidden=True)).to_have_count(0)
      expect(page.locator('details[data-group="studio"]').get_by_role('button',name='Disk usage',exact=True)).to_have_count(0)
      expect(page.locator('details[data-group="store"]').get_by_role('button',name='Drive usage',exact=True)).to_be_visible()
      expect(page.locator('#widget-library').get_by_role('button',name='Legacy drive',exact=True,include_hidden=True)).to_have_count(0)
      expect(page.locator('#core-canvas').get_by_role('button',name='Legacy drive',exact=True)).to_have_count(1)
      stock=page.locator('details[data-group="ultrabar"]')
      studio=page.locator('details[data-group="store"]')
      expect(stock.get_by_role('button',name='Clock',exact=True).first).to_be_visible()
      expect(studio.get_by_role('button',name='System Monitor',exact=True)).to_be_visible()
      studio.locator('summary').click()
      expect(studio).not_to_have_attribute('open','')
      page.locator('#library-search').fill('System Monitor')
      expect(page.locator('details[data-group="store"] .library-item')).to_have_count(1)
      expect(page.locator('details[data-group="store"] .library-item')).to_be_visible()
      page.locator('#library-search').fill('no such widget')
      expect(page.locator('#widget-library')).to_have_text('No matching widgets.')
      page.locator('#library-search').fill('')
      expect(page.locator('details[data-group="store"]')).not_to_have_attribute('open','')
      page.locator('details[data-group="store"] summary').click()
      count=page.locator('#core-canvas .canvas-widget').count()
      page.locator('details[data-group="store"]').get_by_role('button',name='System Monitor',exact=True).click()
      expect(page.locator('#core-canvas .canvas-widget')).to_have_count(count+1)
      expect(page.locator('#widget-kind')).to_have_value('cpu')
      page.locator('#widget-kind').select_option('memory')
      expect(page.locator('#widget-kind')).to_have_value('memory')
      page.locator('details[data-group="store"]').get_by_role('button',name='System Monitor',exact=True).drag_to(page.locator('#core-canvas'))
      expect(page.locator('#widget-kind')).to_have_value('cpu')
      page.locator('#widget-kind').select_option('gpu')
      expect(page.locator('#core-canvas .canvas-widget')).to_have_count(count+2)
      page.wait_for_timeout(450)
      page.locator('details[data-group="store"]').get_by_role('button',name='Store Clock',exact=True).drag_to(page.locator('#core-canvas'))
      expect(page.locator('#widget-hour-format')).to_have_value('24')
      page.locator('#widget-hour-format').select_option('12')
      page.locator('#widget-showSeconds').uncheck()
      page.locator('#widget-showDate').uncheck()
      expect(page.locator('#widget-hour-format')).to_have_value('12')
      expect(page.locator('details[data-group="store"]').get_by_role('button',name='System Monitor',exact=True)).to_have_count(1)
      expect(page.locator('details[data-group="store"]').get_by_role('button',name='System Monitor',exact=True)).to_have_count(1)
      page.wait_for_timeout(450)
      gpu=page.locator('details[data-group="store"]').get_by_role('button',name='System Monitor',exact=True)
      for _ in range(3):
       gpu.click()
       expect(gpu).to_have_count(1)
      page.wait_for_timeout(450)  # End the post-drag click suppression window.
      page.locator('details[data-group="store"]').get_by_role('button',name='Drive usage',exact=True).click()
      expect(page.locator('#widget-drive')).to_have_value('all')
      page.locator('#widget-drive').select_option('C:\\')
      expect(page.locator('#widget-drive')).to_have_value('C:\\')
      page.locator('#draft-save').click()
      expect(page.locator('#editor-notice')).to_contain_text('Draft saved')
      saved=page.request.get('http://'+host+'/api/editor',headers={'X-Studio-Token':server.SESSION_TOKEN}).json()['draft']
      monitors=[w['param']['payload']['params'] for p in saved['profiles'] for w in p['homeData'] if w.get('param',{}).get('payload',{}).get('params',{}).get('packageId')=='studio.system.widget']
      assert sorted(w['kind'] for w in monitors)==['cpu','cpu','cpu','gpu','memory'],monitors
      assert all(w['kindOptions']==['cpu','memory','gpu'] for w in monitors)
      page.route('**/api/editor/deploy-status',lambda r:r.fulfill(json=dict(request_id='other',state='running',message='Other request')))
      page.route('**/api/editor/deploy',lambda r:r.fulfill(status=502,json=dict(error='Core did not wake. No settings were sent.')))
      page.locator('#draft-deploy').click();page.locator('#deploy-confirm').click()
      expect(page.locator('#deploy-progress')).to_be_visible()
      expect(page.locator('#deploy-progress-message')).to_have_text('Core did not wake. No settings were sent.')
      expect(page.locator('#deploy-progress-close')).to_be_enabled()
      page.locator('#deploy-progress-close').click()
      assert not errors,errors
      browser.close()
    finally:http.shutdown()
