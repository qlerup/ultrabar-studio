"""Offline responsive acceptance: real UI with saved profile fixture; no device writes."""
import tempfile, threading, unittest
from pathlib import Path
from unittest.mock import patch
from werkzeug.serving import make_server
from playwright.sync_api import sync_playwright, expect
import server
from studio_contract import legacy_descriptor

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
      page.route('**/api/updates',lambda r:r.fulfill(json=dict(update_available=False,current_version=server.updates.VERSION,latest_version=server.updates.VERSION)))
      errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
      page.route('**/api/preferences',lambda r:r.fulfill(json=dict(target='',setup_seen=True)))
      page.route('**/api/connect',lambda r:r.fulfill(json=snapshot))
      page.route('**/api/core/pair',lambda r:r.fulfill(json=dict(ok=True)))
      page.route('**/api/hardware',lambda r:r.fulfill(json=dict(target=snapshot['target'],hardware=snapshot['hardware'])))
      page.route('**/api/screen*',lambda r:r.fulfill(status=502,json=dict(error='Preview unavailable in offline test')))
      page.route('**/api/cube-previews',lambda r:r.fulfill(json=dict(previews={})))
      page.route('**/api/store/installed',lambda r:r.fulfill(json=dict(installed=[dict(id='studio.clock',icon=dict(sha256='a'*64)),dict(id='studio.drive.widget',icon=dict(sha256='b'*64)),dict(id='studio.system.widget',icon=dict(sha256='c'*64))],widgets=[dict(id='clock',name='Store Clock',kind='clock',_widgetPackage=True,_storePackage='studio.clock',_storeVersion='1.0.0',hourFormat='24',showSeconds=True,showDate=True,_studio=legacy_descriptor(dict(kind='clock'))),dict(id='drive-usage',name='Drive usage',kind='disk',_widgetPackage=True,_storePackage='studio.drive.widget',_storeVersion='1.0.0',_studio=legacy_descriptor(dict(kind='disk'))),dict(id='system-monitor',name='System Monitor',kind='cpu',kindOptions=['cpu','memory','gpu'],_widgetPackage=True,_storePackage='studio.system.widget',_storeVersion='1.0.0',_studio=legacy_descriptor(dict(kind='cpu',kindOptions=['cpu','memory','gpu'])))])))
      page.route('**/api/editor/icons/**',lambda r:r.fulfill(content_type='image/png',body=screen_image))
      page.route('**/api/store/icons/*',lambda r:r.fulfill(status=502,json=dict(error='Offline icon')) if r.request.url.endswith('c'*64) else r.fulfill(content_type='image/png',body=screen_image))
      builtins=[('com.ultrabar.calculator','Calculator'),('com.ultrabar.alarmclock','Alarmclock'),('com.aiks.leisuregame','Space Dodger'),('com.aiks.aurorasniper','AuroraSniper'),('com.ultrabar.whitenoise','White Noise'),('com.stellarring.screensaver','StellarRing'),('com.flip.screensaver','ScreensaverFlip')]
      page.route('**/api/editor/catalog',lambda r:r.fulfill(json=dict(apps=[dict(id=ident,name=name,type='APPS') for ident,name in builtins]+[dict(id='com.example.thirdparty',name='Third-party app',type='APPS')])))
      cpu_reading=None
      page.route('**/api/pc',lambda r:r.fulfill(json=dict(actions=[],metrics=dict(cpu=cpu_reading,disks=[dict(name='C:\\',percent=25,used_gb=25,total_gb=100)]),status='Test',native_status='Test')))
      page.route('**/api/pc/connect',lambda r:r.fulfill(json=dict(actions=[],metrics={})))
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
      expect(page.locator('#action-step-type')).not_to_be_visible()
      page.locator('[data-input-key="2:doubleClick"]').click()
      page.locator('[data-action-type="core-app"]').click()
      page.locator('#action-setup-submit').click()
      expect(page.locator('#action-sequence .sequence-item')).to_have_count(1)
      page.locator('#action-devices [data-layout-key="0000000000000003"]').click()
      page.locator('[data-input-key="knob:clockwise"]').click()
      page.locator('[data-action-type="core-app"]').click()
      page.locator('#action-setup-submit').click()
      expect(page.locator('#action-sequence .sequence-item')).to_have_count(1)
      page.locator('#action-devices [data-layout-key="0000000000000005"]').click()
      expect(page.locator('#action-devices [data-layout-key="0000000000000005"]')).to_have_class('hardware-unit knob_key is-offline action-device-selected')
      expect(page.locator('#action-sequence .sequence-item')).to_have_count(0)
      page.locator('[data-input-key="0:singleClick"]').click()
      page.locator('[data-action-type="core-app"]').click()
      page.locator('#action-setup-submit').click()
      page.locator('#action-devices .vivo_cube').click()
      page.locator('[data-input-key="101:longPress"]').click()
      page.locator('[data-action-type="core-app"]').click()
      page.locator('#action-setup-submit').click()
      page.locator('#action-devices .sense_cube').click()
      page.locator('[data-input-key="sense:2"]').click()
      page.locator('[data-action-type="core-app"]').click()
      page.locator('#action-setup-submit').click()
      page.evaluate('renderHardware()')
      expect(page.locator('[data-input-key="sense:2"]')).to_have_attribute('aria-pressed','true')
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
      canvas=page.locator('#core-canvas')
      canvas.get_by_role('button',name='Existing Store Clock',exact=True).click()
      expect(page.get_by_label('Widget size',exact=True)).to_have_count(0)
      page.locator('#core-next').click()
      slider=page.get_by_role('slider',name='Scroll Core preview')
      for width in (1440,390):
       page.set_viewport_size(dict(width=width,height=960))
       slider.scroll_into_view_if_needed()
       slider.press('Home')
       expect(slider).to_have_value('0')
       assert canvas.evaluate('(node)=>node.scrollLeft')==0
       bounds=slider.bounding_box()
       handle_width=min(72,max(34,width*.06))
       x=bounds['x']+handle_width/2;y=bounds['y']+bounds['height']/2
       page.mouse.move(x,y);page.mouse.down();page.mouse.move(bounds['x']+bounds['width']-5,y,steps=12);page.mouse.up()
       expect(slider).to_have_value(slider.get_attribute('max'))
       assert canvas.evaluate('''(node)=>{
         const slots=[...node.querySelectorAll('.core-slot')];
         const right=Math.max(...slots.map(slot=>slot.getBoundingClientRect().right));
         const screen=node.getBoundingClientRect();
         return Math.abs(screen.right-right-20*screen.width/1424)<1;
       }''')
      page.set_viewport_size(dict(width=1440,height=960))
      empty=canvas.locator('[data-slot-column="10"]')
      add=empty.get_by_role('button',name='Choose layout for empty slot')
      expect(add).to_have_css('opacity','0')
      add.hover()
      expect(add).to_have_css('opacity','1')
      add.click()
      dialog=page.get_by_role('dialog',name='Slot layout')
      expect(dialog.get_by_role('button',name='One large slot')).to_have_attribute('aria-pressed','true')
      for width in (1440,390):
       page.set_viewport_size(dict(width=width,height=960))
       for name,count in (('One large slot',1),('2×2 grid',4)):
        preview=dialog.get_by_role('button',name=name).locator('.core-slot-preview-widget')
        expect(preview).to_have_count(count)
        expect(preview.first).to_be_visible()
        size=preview.first.bounding_box()
        assert 1.06<size['width']/size['height']<1.14
       assert dialog.evaluate('(node)=>node.scrollWidth<=node.clientWidth')
      page.set_viewport_size(dict(width=1440,height=960))
      dialog.get_by_role('button',name='2×2 grid').click()
      expect(empty.locator('.core-slot-cell')).to_have_count(4)
      page.locator('#core-screen').screenshot(path=str(server.ROOT/'data/qa/design-empty-split-slot.png'))
      monitor=page.locator('#widget-library').get_by_role('button',name='System Monitor',exact=True)
      slider.press('Home')
      cards=canvas.locator('.canvas-widget')
      second=cards.nth(1)
      monitor.scroll_into_view_if_needed()
      before=second.bounding_box()
      source=monitor.bounding_box()
      page.mouse.move(source['x']+source['width']/2,source['y']+source['height']/2)
      page.mouse.down()
      page.mouse.move(before['x']+10,before['y']+before['height']/2,steps=12)
      line=page.locator('.widget-insert-marker:not(.grid-marker)')
      expect(line).to_be_visible()
      assert 0<before['x']-line.bounding_box()['x']<17
      expect(canvas).to_have_css('background-image','none')
      assert 0<line.bounding_box()['height']<before['height']*.5
      assert line.evaluate("(node)=>getComputedStyle(node,'::after').borderRadius")=='50%'
      page.mouse.up()
      expect(second).to_have_attribute('aria-label','System Monitor')
      assert abs(second.bounding_box()['x']-before['x'])<1
      with page.expect_response(lambda r:r.url.endswith('/api/editor/draft') and r.request.method=='POST') as saved:
       page.locator('#draft-save').click()
      assert saved.value.json()['draft']['compact_profiles']['p1']['splits']==[12]
      page.locator('#widget-undo').click()
      expect(second).to_have_attribute('aria-label','Legacy drive')
      slider.press('End')
      monitor.scroll_into_view_if_needed()
      source=monitor.bounding_box();target=empty.locator('.core-slot-cell').nth(1).bounding_box()
      page.mouse.move(source['x']+source['width']/2,source['y']+source['height']/2)
      page.mouse.down();page.mouse.move(target['x']+target['width']/2,target['y']+target['height']/2,steps=12);page.mouse.up()
      expect(canvas.locator('.small-widget')).to_have_attribute('aria-label','System Monitor')
      expect(empty.locator('.core-slot-cell')).to_have_count(3)
      def drag_card_to(target):
       card=canvas.get_by_role('button',name='System Monitor',exact=True).bounding_box()
       destination=target.bounding_box()
       page.mouse.move(card['x']+card['width']/2,card['y']+card['height']/2)
       page.mouse.down()
       page.mouse.move(destination['x']+destination['width']/2,destination['y']+destination['height']/2,steps=12)
       expect(page.locator('.grid-marker:not(.invalid-grid-marker)')).to_be_visible()
       page.mouse.up()
      drag_card_to(empty.locator('.core-slot-cell').first)
      expect(canvas.locator('.small-widget')).to_have_count(1)
      drag_card_to(canvas.locator('.core-slot[data-slot-column="12"]'))
      expect(canvas.locator('.small-widget')).to_have_count(0)
      expect(empty.locator('.core-slot-cell')).to_have_count(4)
      with page.expect_response(lambda r:r.url.endswith('/api/editor/draft') and r.request.method=='POST') as saved:
       page.locator('#draft-save').click()
      assert saved.value.json()['draft']['compact_profiles']['p1']['small']==[]
      page.locator('#widget-undo').click()
      expect(canvas.locator('.small-widget')).to_have_count(1)
      page.locator('#widget-undo').click()
      expect(canvas.locator('.small-widget')).to_have_count(1)
      page.locator('#widget-undo').click()
      expect(empty.locator('.core-slot-cell')).to_have_count(4)
      empty.get_by_role('button',name='Change empty 2×2 grid').click()
      dialog.get_by_role('button',name='One large slot').click()
      expect(empty.locator('.core-slot-cell')).to_have_count(0)
      page.locator('#core-previous').click()
      stock=page.locator('details[data-group="ultrabar"]')
      studio=page.locator('details[data-group="store"]')
      expect(stock.get_by_role('button',name='Clock',exact=True)).to_have_count(1)
      for ident,name in builtins:
       expect(stock.get_by_role('button',name=name,exact=True)).to_have_count(1)
       expect(page.locator('details[data-group="installed"]').get_by_role('button',name=name,exact=True,include_hidden=True)).to_have_count(0)
      expect(page.locator('details[data-group="installed"]').get_by_role('button',name='Third-party app',exact=True,include_hidden=True)).to_have_count(1)
      expect(stock.get_by_role('button',name='Clock',exact=True)).to_be_visible()
      expect(stock.get_by_role('button',name='Clock',exact=True).locator('.library-icon img')).to_have_count(1)
      expect(studio.get_by_role('button',name='Store Clock',exact=True).locator('.library-icon img')).to_have_count(1)
      expect(studio.get_by_role('button',name='Drive usage',exact=True).locator('.library-icon img')).to_have_count(1)
      expect(studio.get_by_role('button',name='System Monitor',exact=True).locator('.library-icon')).to_have_text('S')
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
      before_background=page.locator('#background-apps button').count()
      for name in ['Clock','Calculator']:
       stock.get_by_role('button',name=name,exact=True).click()
       expect(page.locator('#core-canvas .canvas-widget')).to_have_count(count)
      page.locator('details[data-group="store"]').get_by_role('button',name='System Monitor',exact=True).click()
      expect(page.locator('#core-canvas .canvas-widget')).to_have_count(count)
      expect(page.locator('#background-apps button')).to_have_count(before_background)
      page.locator('details[data-group="store"]').get_by_role('button',name='System Monitor',exact=True).drag_to(page.locator('#core-screen'))
      expect(page.locator('#core-canvas .canvas-widget')).to_have_count(count+1)
      expect(page.locator('#widget-setting-kind')).to_have_value('cpu')
      reading=canvas.locator('.canvas-widget.selected .native-value')
      expect(reading).to_have_text('--')
      cpu_reading=37
      expect(reading).to_have_text('37.0%',timeout=8000)
      page.locator('#widget-setting-kind').select_option('memory')
      expect(page.locator('#widget-setting-kind')).to_have_value('memory')
      page.locator('details[data-group="store"]').get_by_role('button',name='System Monitor',exact=True).drag_to(page.locator('#core-canvas'))
      expect(page.locator('#widget-setting-kind')).to_have_value('cpu')
      page.locator('#widget-setting-kind').select_option('gpu')
      expect(page.locator('#core-canvas .canvas-widget')).to_have_count(count+2)
      page.wait_for_timeout(450)
      page.locator('details[data-group="store"]').get_by_role('button',name='Store Clock',exact=True).drag_to(page.locator('#core-canvas'))
      expect(page.locator('#widget-setting-hourFormat')).to_have_value('24')
      page.locator('#widget-setting-hourFormat').select_option('12')
      page.locator('#widget-setting-showSeconds').uncheck()
      page.locator('#widget-setting-showDate').uncheck()
      expect(page.locator('#widget-setting-hourFormat')).to_have_value('12')
      expect(page.locator('details[data-group="store"]').get_by_role('button',name='System Monitor',exact=True)).to_have_count(1)
      expect(page.locator('details[data-group="store"]').get_by_role('button',name='System Monitor',exact=True)).to_have_count(1)
      page.wait_for_timeout(450)
      gpu=page.locator('details[data-group="store"]').get_by_role('button',name='System Monitor',exact=True)
      for _ in range(3):
       gpu.drag_to(page.locator('#core-screen'))
       expect(gpu).to_have_count(1)
      page.wait_for_timeout(450)  # End the post-drag click suppression window.
      page.locator('details[data-group="store"]').get_by_role('button',name='Drive usage',exact=True).drag_to(page.locator('#core-screen'))
      expect(page.locator('#widget-setting-drive')).to_have_value('all')
      page.locator('#widget-setting-drive').select_option('C:\\')
      expect(page.locator('#widget-setting-drive')).to_have_value('C:\\')
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
      self.assertIsNone(pending[-1].request.post_data_json['overwrite_core_hash'])
      core_hash='a'*64
      pending[-1].fulfill(status=409,json=dict(error='Core settings changed.',core_profile_hash=core_hash))
      expect(page.locator('#deploy-progress')).not_to_be_visible()
      expect(page.locator('#deploy-dialog')).to_be_visible()
      expect(page.locator('#deploy-conflict')).to_contain_text('Studio saves a backup')
      expect(page.locator('#deploy-cancel')).to_be_focused()
      assert page.locator('#deploy-dialog').evaluate('(dialog)=>dialog.scrollWidth<=dialog.clientWidth')
      page.locator('#deploy-cancel').click()
      self.assertEqual(len(pending),2)
      page.locator('#draft-deploy').click()
      expect(page.locator('#deploy-confirm')).to_have_text('Deploy anyway')
      page.locator('#deploy-confirm').click()
      expect(page.locator('#deploy-progress-message')).to_have_text('Waiting for widgets to become ready…')
      self.assertEqual(pending[-1].request.post_data_json['overwrite_core_hash'],core_hash)
      pending[-1].fulfill(json=dict(draft=saved,snapshot=snapshot,activated=True,widgets_ready=True,message='Settings saved and verified. Core home restarted.'))
      expect(page.locator('#deploy-progress')).to_have_attribute('data-state','success')
      expect(page.locator('#deploy-progress-close')).to_have_text('Done')
      expect(page.locator('#deploy-progress-close')).to_be_focused()
      page.screenshot(path=str(output/'deploy-success-mobile.png'))
      page.locator('#deploy-progress-close').click()
      assert not errors,errors
      browser.close()
    finally:http.shutdown()
