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
  devices += [dict(serial='0000000000000004',type='SENSE_CUBE',name='SenseCube',online=True),dict(serial='0000000000000005',type='KNOB_KEY',name='KnobKey',online=False)]
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
      expect(page.locator('.screen-panel')).to_have_count(0)
      import base64
      screen_image=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=')
      page.route('**/api/screen',lambda r:r.fulfill(content_type='image/png',body=screen_image))
      page.locator('#preview-refresh').click()
      expect(page.locator('.core-unit .core-screen-image')).to_be_visible()
      self.assertTrue(page.locator('.core-unit .core-screen-image').evaluate('(image)=>image.complete&&image.naturalWidth>0'))
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
      page.locator('#mode-actions').click()
      expect(page.locator('#action-config')).not_to_be_visible()
      expect(page.locator('#action-device-empty')).to_be_visible()
      expect(page.locator('#action-devices .hardware-unit')).to_have_count(6)
      assert page.locator('#action-devices .hardware-unit').evaluate_all('(cards)=>cards.map(c=>c.dataset.layoutKey)')==page.evaluate('visibleLayoutOrder()')
      dot=page.locator('#action-devices .dot_key')
      dot.focus();page.keyboard.press('Enter')
      expect(page.locator('#action-config')).to_be_visible()
      expect(page.locator('#action-input')).to_have_value('2:singleClick')
      page.locator('#action-input').select_option('2:doubleClick')
      page.locator('#action-library .library-item').first.click()
      expect(page.locator('#action-sequence .sequence-item')).to_have_count(1)
      page.locator('#action-devices [data-layout-key="0000000000000003"]').click()
      page.locator('#action-input').select_option('knob:clockwise')
      page.locator('#action-library .library-item').first.click()
      expect(page.locator('#action-sequence .sequence-item')).to_have_count(1)
      page.locator('#action-devices [data-layout-key="0000000000000005"]').click()
      expect(page.locator('#action-devices [data-layout-key="0000000000000005"]')).to_have_class('hardware-unit knob_key is-offline action-device-selected')
      expect(page.locator('#action-sequence .sequence-item')).to_have_count(0)
      page.locator('#action-library .library-item').first.click()
      page.locator('#action-devices .vivo_cube').click()
      page.locator('#action-input').select_option('101:longPress')
      page.locator('#action-library .library-item').first.click()
      page.locator('#action-devices .sense_cube').click()
      page.locator('#action-input').select_option('sense:2')
      page.locator('#action-library .library-item').first.click()
      page.evaluate('renderHardware()')
      expect(page.locator('#action-input')).to_have_value('sense:2')
      expect(page.locator('#action-sequence .sequence-item')).to_have_count(1)
      for width in [1920,390]:
       page.set_viewport_size(dict(width=width,height=960))
       page.screenshot(path=str(server.ROOT/f'data/qa/design-actions-{width}.png'),full_page=True)
       assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),page.evaluate("[...document.querySelectorAll('#actions-editor *')].filter(n=>n.getBoundingClientRect().right>innerWidth+1).map(n=>[n.tagName,n.id,n.className,n.getBoundingClientRect().right]).slice(0,15)")
      page.set_viewport_size(dict(width=1440,height=960))
      page.locator('#action-devices .core-unit').click()
      expect(page.locator('#layout-editor')).to_be_visible()
      expect(page.locator('details[data-group="store"] .library-item')).to_have_count(3)
      expect(page.locator('details[data-group="installed"]').get_by_role('button',name='Original PC widget',exact=True,include_hidden=True)).to_have_count(1)
      expect(page.locator('details[data-group="store"]').get_by_role('button',name='Original PC widget',exact=True,include_hidden=True)).to_have_count(0)
      expect(page.locator('details[data-group="studio"]').get_by_role('button',name='Disk usage',exact=True)).to_have_count(0)
      expect(page.locator('details[data-group="store"]').get_by_role('button',name='Drive usage',exact=True)).to_be_visible()
      expect(page.locator('#widget-library').get_by_role('button',name='Legacy drive',exact=True,include_hidden=True)).to_have_count(0)
      expect(page.locator('#core-canvas').get_by_role('button',name='Legacy drive',exact=True)).to_have_count(1)
      stock=page.locator('details[data-group="ultrabar"]')
      studio=page.locator('details[data-group="store"]')
      expect(stock.get_by_role('button',name='Clock',exact=True)).to_have_count(1)
      expect(stock.get_by_role('button',name='Clock',exact=True)).to_be_visible()
      page.emulate_media(reduced_motion='reduce')
      selected=page.locator('#core-canvas .canvas-widget.selected')
      selected.hover()
      assert selected.evaluate('(node)=>node.matches(":hover")'), 'Selected widget is not hovered'
      expect(selected).to_have_css('border-top-color','rgb(185, 178, 255)')
      page.locator('#library-search').hover()
      expect(selected).to_have_css('border-top-color','rgb(185, 178, 255)')
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
      module_map={m['serialNo']:m for m in saved['profiles'][0]['module']}
      assert module_map['0000019F2B129C2C']['config'][0]['doubleClick']['actions']
      assert module_map['0000000000000003']['config']['clockwise']['actions']
      assert module_map['0000000000000002']['config'][0]['longPress']['actions']
      assert module_map['0000000000000005']['config']['button']['singleClick']['actions']
      assert module_map['0000000000000004']['config'][0]['mode']==2
      assert module_map['0000000000000004']['config'][0]['actions']
      monitors=[w['param']['payload']['params'] for p in saved['profiles'] for w in p['homeData'] if w.get('param',{}).get('payload',{}).get('params',{}).get('packageId')=='studio.system.widget']
      assert sorted(w['kind'] for w in monitors)==['cpu','cpu','cpu','gpu','memory'],monitors
      assert all(w['kindOptions']==['cpu','memory','gpu'] for w in monitors)
      pending=[]
      page.route('**/api/editor/deploy-status',lambda r:r.fulfill(json=dict(request_id=pending[-1].request.post_data_json['request_id'] if pending else 'other',state='running',message='Waiting for widgets to become ready…')))
      page.route('**/api/editor/deploy',lambda r:pending.append(r))
      page.locator('#draft-deploy').click();page.locator('#deploy-confirm').click()
      expect(page.locator('#deploy-progress')).to_be_visible()
      expect(page.locator('#deploy-progress')).to_have_attribute('data-state','running')
      expect(page.locator('#deploy-progress-message')).to_have_text('Waiting for widgets to become ready…')
      expect(page.locator('#deploy-progress-close')).to_be_disabled()
      page.keyboard.press('Escape');expect(page.locator('#deploy-progress')).to_be_visible()
      output=Path(__file__).parent/'data/qa'
      page.set_viewport_size(dict(width=1440,height=960))
      page.screenshot(path=str(output/'deploy-running-desktop.png'))
      page.set_viewport_size(dict(width=390,height=844))
      page.screenshot(path=str(output/'deploy-running-mobile.png'))
      assert page.locator('#deploy-progress').evaluate('(e)=>e.scrollWidth<=e.clientWidth'), 'Deployment dialog overflow'
      pending[-1].fulfill(status=502,json=dict(error='Core did not wake. No settings were sent.'))
      expect(page.locator('#deploy-progress-message')).to_have_text('Core did not wake. No settings were sent.')
      expect(page.locator('#deploy-progress')).to_have_attribute('data-state','error')
      expect(page.locator('#deploy-progress-spinner')).not_to_be_visible()
      expect(page.locator('#deploy-progress-close')).to_be_enabled()
      page.screenshot(path=str(output/'deploy-error-mobile.png'))
      page.locator('#deploy-progress-close').click()
      page.locator('#draft-deploy').click();page.locator('#deploy-confirm').click()
      expect(page.locator('#deploy-progress')).to_have_attribute('data-state','running')
      expect(page.locator('#deploy-progress-message')).to_have_text('Waiting for widgets to become ready…')
      pending[-1].fulfill(json=dict(draft=saved,snapshot=snapshot,message='Settings saved and verified. Core home restarted.'))
      expect(page.locator('#deploy-progress')).to_have_attribute('data-state','success')
      expect(page.locator('#deploy-progress-close')).to_have_text('Done')
      expect(page.locator('#deploy-progress-close')).to_be_focused()
      page.screenshot(path=str(output/'deploy-success-mobile.png'))
      page.locator('#deploy-progress-close').click()
      assert not errors,errors
      browser.close()
    finally:http.shutdown()
