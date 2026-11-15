"""Offline acceptance of progressive input/action/settings setup. No device writes."""
from contextlib import contextmanager, ExitStack
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from werkzeug.serving import make_server
from playwright.sync_api import sync_playwright, expect
import server
from test_editor import profiles


class ActionWizardTests(unittest.TestCase):
    @contextmanager
    def workspace(self, pw, empty=False):
        data = profiles()
        legacy = dict(type='PC_VOLUME', name='Volume up', values=[dict(id='1', value='up')])
        data[0]['module'] += [
            dict(serialNo='0000000000000001', productId='KNOB_KEY', config={} if empty else dict(button=dict(keyCode=0, singleClick=dict(actions=[legacy], name='singleClick', type='MANUAL', enabled=False, show=False)))),
            dict(serialNo='0000000000000002', productId='KNOB_KEY', config={})]
        if empty:
            data[0]['module'][0]['config'] = []
        second = deepcopy(data[0]);second.update(id='p2',name='Second',default=False);data.append(second)
        snapshot = dict(device_id='wizard',target='192.168.1.20:5555',model='CB01',read_at='2026-11-15T12:00:00Z',backup='fixture.xml',profiles=data,hardware=dict(devices=[dict(serial=m['serialNo'],type=m['productId'],name=m['productId'],online=True) for m in data[0]['module']]))
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            root=Path(tmp);program=root/'Example Editor.exe';program.write_bytes(b'offline validation fixture')
            stack.enter_context(patch.object(server,'DATA_DIR',root))
            stack.enter_context(patch.dict(server.connection,target=snapshot['target'],snapshot=snapshot))
            adb=stack.enter_context(patch.object(server,'adb'))
            stack.enter_context(patch.object(server.companion,'start'))
            picker=stack.enter_context(patch.object(server,'program_picker',side_effect=[None,[str(program)]],create=True))
            http=make_server('127.0.0.1',0,server.app,threaded=True);host=f'127.0.0.1:{http.server_port}'
            stack.enter_context(patch.dict(server.app.config,ALLOWED_HOSTS={host}))
            threading.Thread(target=http.serve_forever,daemon=True).start()
            browser=pw.chromium.launch(channel='msedge');page=browser.new_page(viewport=dict(width=1600,height=1000))
            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.route('**/api/preferences',lambda r:r.fulfill(json=dict(target='',setup_seen=True)))
            page.route('**/api/updates',lambda r:r.fulfill(json=dict(update_available=False,current_version='0.43.0',latest_version='0.43.0')))
            page.route('**/api/updates/status',lambda r:r.fulfill(json=dict(state='idle')))
            page.route('**/api/connect',lambda r:r.fulfill(json=snapshot))
            page.route('**/api/discover',lambda r:r.fulfill(json=dict(devices=[])))
            page.route('**/api/hardware',lambda r:r.fulfill(json=dict(target=snapshot['target'],hardware=snapshot['hardware'])))
            page.route('**/api/screen*',lambda r:r.fulfill(status=502,json=dict(error='Offline preview')))
            page.route('**/api/editor/icons/**',lambda r:r.fulfill(status=502,json=dict(error='Offline icon')))
            page.route('**/api/cube-previews',lambda r:r.fulfill(json=dict(previews={})))
            page.route('**/api/store/installed',lambda r:r.fulfill(json=dict(widgets=[])))
            page.route('**/api/editor/catalog',lambda r:r.fulfill(json=dict(apps=[] if empty else [dict(id='com.test.calculator',type='APPS',name='Calculator')])) )
            page.route('**/api/pc/connect',lambda r:r.fulfill(json={}))
            page.route('**/api/pc',lambda r:r.fulfill(json=dict(actions=server.companion.actions(),metrics={},status='Offline test')))
            try:
                page.goto('http://'+host)
                page.locator('#connection-open').click();page.locator('#manual-connection summary').click()
                page.locator('#target').fill(snapshot['target']);page.locator('#connect').click()
                expect(page.locator('#workspace')).to_be_visible()
                page.locator('#nav-editor').click();page.locator('#mode-actions').click()
                yield page,host,root,program,picker,legacy
                self.assertFalse(errors,errors);adb.assert_not_called()
            finally:
                browser.close();http.shutdown()

    def test_website_program_core_app_edit_and_saved_action(self):
        with sync_playwright() as pw, self.workspace(pw) as (page,host,root,program,picker,legacy):
            first=page.locator('#action-devices [data-layout-key="0000000000000001"]')
            first.click()
            expect(page.locator('#action-step-type')).not_to_be_visible()
            expect(page.locator('#action-step-settings')).not_to_be_visible()
            page.locator('[data-input-key="0:singleClick"]').click()
            expect(page.locator('#action-step-type')).to_be_visible()
            expect(page.locator('#action-step-settings')).not_to_be_visible()
            expect(page.locator('#action-sequence .sequence-item')).to_have_count(1)
            page.locator('[data-action-type="website"]').click()
            expect(page.locator('#action-target')).to_have_attribute('type','url')
            expect(page.locator('#action-browse-program')).not_to_be_visible()
            page.locator('#action-target').fill('file:///invalid.exe')
            page.locator('#action-setup-submit').click()
            expect(page.locator('#action-setup-error')).to_contain_text('http://')
            expect(page.locator('#action-sequence .sequence-item')).to_have_count(1)
            page.locator('#action-target').fill('https://example.com/docs')
            page.locator('#action-name').fill('Documentation')
            pending=[]
            page.route('**/api/pc/actions',lambda r:pending.append(r))
            page.locator('#action-setup-submit').click()
            expect(page.locator('#draft-save')).to_be_disabled()
            page.locator('#action-devices [data-layout-key="0000000000000002"]').click()
            expect(first).to_have_attribute('aria-pressed','true')
            self.assertEqual(len(pending),1)
            response=page.request.fetch(pending[0].request)
            pending[0].fulfill(response=response)
            page.unroute('**/api/pc/actions')
            expect(page.locator('#action-sequence .sequence-item')).to_have_count(2)
            expect(page.locator('#action-feedback')).to_contain_text('Action added')
            expect(page.locator('#action-step-settings')).not_to_be_visible()
            page.locator('#action-sequence .sequence-item').last.get_by_role('button',name='Edit',exact=True).click()
            expect(page.locator('#action-target')).to_have_value('https://example.com/docs')
            page.locator('#action-target').fill('https://example.com/new')
            page.locator('#action-setup-submit').click()
            expect(page.locator('#action-feedback')).to_contain_text('Action updated')
            expect(page.locator('#action-sequence .sequence-item')).to_have_count(2)
            page.locator('[data-input-key="0:doubleClick"]').click()
            expect(page.locator('#action-step-settings')).not_to_be_visible()
            page.locator('[data-action-type="program"]').click()
            expect(page.locator('#action-target')).to_have_attribute('type','text')
            page.locator('#action-browse-program').click()
            expect(page.locator('#action-target')).to_have_value('')
            page.locator('#action-browse-program').click()
            expect(page.locator('#action-target')).to_have_value(str(program))
            self.assertEqual(picker.call_count,2)
            page.locator('#action-name').fill('Editor')
            page.locator('#action-setup-submit').click()
            expect(page.locator('#action-sequence .sequence-item')).to_have_count(1)
            page.locator('#action-devices [data-layout-key="0000000000000002"]').click()
            page.locator('[data-input-key="0:singleClick"]').click()
            page.locator('[data-action-type="pc-action"]').click()
            page.locator('#action-choice').select_option(label='Editor')
            page.locator('#action-setup-submit').click()
            expect(page.locator('#action-sequence .sequence-item')).to_contain_text('Editor')
            first.click();page.locator('[data-input-key="0:longPress"]').click()
            page.locator('[data-action-type="core-app"]').click()
            page.locator('#action-choice').select_option(label='Launch Calculator')
            page.locator('#action-setup-submit').click()
            expect(page.locator('#action-sequence .sequence-item')).to_contain_text('Launch Calculator')
            page.locator('[data-input-key="0:singleClick"]').click()
            page.locator('#action-sequence .sequence-item').last.get_by_role('button',name='\u2191',exact=True).click()
            expect(page.locator('#action-sequence .sequence-item').first).to_contain_text('Documentation')
            page.locator('#action-sequence .sequence-item').last.get_by_role('button',name='Remove',exact=True).click()
            expect(page.locator('#action-sequence .sequence-item')).to_have_count(1)
            page.locator('#action-undo').click()
            expect(page.locator('#action-sequence .sequence-item')).to_have_count(2)
            page.locator('[data-action-type="website"]').click();page.locator('#action-target').fill('https://cancelled.example')
            page.locator('#action-setup-cancel').click()
            expect(page.locator('#action-step-settings')).not_to_be_visible()
            expect(page.locator('#action-sequence .sequence-item')).to_have_count(2)
            page.locator('#draft-save').click();expect(page.locator('#draft-status')).to_contain_text('Draft saved')
            saved=page.request.get('http://'+host+'/api/editor',headers={'X-Studio-Token':server.SESSION_TOKEN}).json()['draft']
            modules={m['serialNo']:m for m in saved['profiles'][0]['module']}
            knob=modules['0000000000000001']['config']['button']
            self.assertEqual(knob['singleClick']['actions'][1],legacy)
            pcid=knob['doubleClick']['actions'][0]['values'][0]['value']['payload']['params']['id']
            self.assertEqual(modules['0000000000000002']['config']['button']['singleClick']['actions'][0]['values'][0]['value']['payload']['params']['id'],pcid)
            self.assertEqual(knob['longPress']['actions'][0]['values'][0]['value'],'com.test.calculator')
            actions=json.loads((root/'pc-actions.json').read_text())
            self.assertTrue(any(a['target']=='https://example.com/new' for a in actions))
            self.assertFalse(any(a['target']=='https://cancelled.example' for a in actions))
            self.assertEqual(saved['profiles'][1]['module'][1]['config']['button']['singleClick']['actions'],[legacy])
            # A hardware poll must not erase an unfinished form.
            page.locator('[data-action-type="website"]').click();page.locator('#action-target').fill('https://example.com/preview')
            page.evaluate('renderHardware()')
            expect(page.locator('#action-target')).to_have_value('https://example.com/preview')
            for width in [1920,390]:
                page.set_viewport_size(dict(width=width,height=1000))
                page.locator('#action-step-settings').scroll_into_view_if_needed()
                page.screenshot(path=str(server.ROOT/f'data/qa/action-wizard-{width}.png'),full_page=True)
                self.assertTrue(page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'))
            page.locator('#edit-profile').select_option('1')
            expect(page.locator('#action-config')).not_to_be_visible()
            page.locator('#action-devices [data-layout-key="0000000000000001"]').click()
            expect(page.locator('#action-step-type')).not_to_be_visible()

    def test_empty_actions_and_cancel_do_not_change_draft(self):
        with sync_playwright() as pw, self.workspace(pw,empty=True) as (page,host,root,program,picker,legacy):
            before=page.request.get('http://'+host+'/api/editor',headers={'X-Studio-Token':server.SESSION_TOKEN}).json()['draft']['profiles']
            page.locator('#action-devices [data-layout-key="0000000000000001"]').click()
            page.locator('[data-input-key="0:singleClick"]').click()
            for kind in ['pc-action','core-app']:
                page.locator(f'[data-action-type="{kind}"]').click()
                expect(page.locator('#action-choice-empty')).to_be_visible()
                expect(page.locator('#action-setup-submit')).to_be_disabled()
            page.locator('#action-setup-cancel').click()
            after=page.request.get('http://'+host+'/api/editor',headers={'X-Studio-Token':server.SESSION_TOKEN}).json()['draft']['profiles']
            self.assertEqual(before,after)
            self.assertFalse((root/'pc-actions.json').exists())
