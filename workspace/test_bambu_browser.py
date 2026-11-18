"""Offline browser acceptance: per-card settings, history and persistent drafts."""
import unittest
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
import server
from unittest.mock import patch
import bambu
from studio_contract import legacy_descriptor
import test_action_wizard_browser as fixture
from bambu_contract import DEFAULTS

class BambuBrowserTests(unittest.TestCase):
    def test_printer_status_updates_automatically_without_resetting_form(self):
        template=dict(DEFAULTS,id='bambu-liquid',name='Bambu',kind='bambu',_widgetPackage=True,_storePackage='studio.bambu.widget',_storeVersion='2.0.0')
        template['_studio']=legacy_descriptor(template)
        printer=dict(id='test-printer',name='Workshop',host='192.168.1.30',status=dict(connection='Connecting'))
        requests=[]
        with sync_playwright() as pw,fixture.ActionWizardTests().workspace(pw) as (page,host,root,program,picker,legacy):
            def printers(route):
                requests.append(route.request.url)
                route.fulfill(json=dict(items=[printer]))
            page.route('**/api/studio/integrations/*/*/list',printers)
            page.route('**/api/store/installed',lambda r:r.fulfill(json=dict(installed=[],widgets=[template])))
            page.evaluate("window.dispatchEvent(new Event('studio-store-changed'))")
            page.locator('#mode-layout').click()
            item=page.locator('#widget-library').get_by_role('button',name='Bambu',exact=True)
            expect(item).to_be_visible();item.drag_to(page.locator('#core-screen'))
            page.get_by_role('button',name='Manage printers',exact=True).click()
            status=page.locator('.studio-connection-status')
            expect(status).to_contain_text('Connecting')
            name=page.locator('#connection-name');name.fill('Unfinished printer')
            printer['status']['connection']='Connected'
            expect(status).to_contain_text('Connected',timeout=6000)
            expect(name).to_have_value('Unfinished printer');expect(name).to_be_focused()
            printer['status']['connection']='Disconnected'
            expect(status).to_contain_text('Disconnected',timeout=6000)
            page.locator('#studio-connections').get_by_role('button',name='Close',exact=True).click()
            page.wait_for_timeout(300)
            count=len(requests)
            page.wait_for_timeout(2300)
            self.assertEqual(len(requests),count)

    def test_studio_printer_setup_independent_selection_and_no_draft_secrets(self):
        template=dict(DEFAULTS,id='bambu-liquid',name='Bambu',kind='bambu',background='#14202b',accent='#86e4c3',_widgetPackage=True,_storePackage='studio.bambu.widget',_storeVersion='2.0.0')
        template['_studio']=legacy_descriptor(template)
        template['_studio']['connection']['fields'].append(dict(key='model',label='Printer model',type='choice',required=False,options=[dict(value=k,label=k.upper()) for k in ('generic','h2d','h3c')]))
        template['_studio']['presentation']=dict(api=1,source=dict(scope='connection',key='model'),presets=[
            dict(value='h2d',artwork=[dict(type='rect',points=[10,10,90,90],fill='accent')]),
            dict(value='h3c',artwork=[dict(type='oval',points=[10,10,90,90],fill='accent')]),
        ])
        from base64 import b64encode
        from io import BytesIO
        from PIL import Image
        def thumbnail(model):
            buffer=BytesIO(); Image.new('RGB',(30,40),'red' if model=='h2d' else 'blue').save(buffer,format='PNG')
            return b64encode(buffer.getvalue()).decode('ascii')
        with sync_playwright() as pw,fixture.ActionWizardTests().workspace(pw) as (page,host,root,program,picker,legacy),patch.object(bambu.Link,'start'),patch.object(bambu,'thumbnail',side_effect=thumbnail),patch.object(server.store,'records',return_value={'fixture':dict(id=template['_storePackage'],type='corebar-widget',widgets=[template])}):
            page.route('**/api/store/installed',lambda r:r.fulfill(json=dict(installed=[],widgets=[template])))
            page.route('**/api/studio/integrations/*/*/probe',lambda r:r.fulfill(json=dict(pin='b'*64)))
            page.evaluate("window.dispatchEvent(new Event('studio-store-changed'))")
            page.locator('#mode-layout').click()
            item=page.locator('#widget-library').get_by_role('button',name='Bambu',exact=True)
            expect(item).to_be_visible();item.drag_to(page.locator('#core-screen'))
            page.get_by_role('button',name='Manage printers',exact=True).click()
            expect(page.locator('#studio-connections')).to_be_visible()
            page.locator('#connection-name').fill('H2D workshop')
            page.locator('#connection-model').select_option('h2d')
            page.locator('#connection-host').fill('192.168.1.30')
            page.locator('#connection-serial').fill('SYNTHETIC123')
            page.locator('#connection-code').fill('LAN12345')
            page.get_by_role('button',name='Check connection',exact=True).click()
            expect(page.locator('.studio-fingerprint')).to_have_text('b'*64)
            page.get_by_role('button',name='Trust certificate & save',exact=True).click()
            expect(page.locator('.studio-connection-row')).to_have_count(1)
            self.assertEqual(server.bambu.listing()[0]['model'],'h2d')
            page.locator('.studio-connection-row').get_by_role('button',name='Edit',exact=True).click()
            expect(page.locator('#connection-model')).to_have_value('h2d')
            page.get_by_role('button',name='Add printer',exact=True).click()
            expect(page.locator('#connection-code')).to_have_value('')
            page.locator('#connection-name').fill('H3C office')
            page.locator('#connection-model').select_option('h3c')
            page.locator('#connection-host').fill('192.168.1.31')
            page.locator('#connection-serial').fill('SYNTHETIC456')
            page.locator('#connection-code').fill('LAN67890')
            page.get_by_role('button',name='Check connection',exact=True).click()
            page.get_by_role('button',name='Trust certificate & save',exact=True).click()
            expect(page.locator('.studio-connection-row')).to_have_count(2)
            page.set_viewport_size(dict(width=390,height=1000))
            out=Path(__file__).parent/'data/qa';out.mkdir(exist_ok=True,parents=True)
            page.screenshot(path=str(out/'studio-connections-mobile.png'),full_page=True)
            self.assertTrue(page.locator('#studio-connections').evaluate('(d)=>d.scrollWidth<=d.clientWidth+1'))
            page.set_viewport_size(dict(width=1600,height=1000));page.screenshot(path=str(out/'studio-connections-desktop.png'),full_page=True)
            page.locator('#studio-connections').get_by_role('button',name='Close',exact=True).click()
            expect(page.locator('[data-connection-key=printerId] option')).to_have_count(3)
            ids=page.locator('[data-connection-key=printerId] option').evaluate_all('(items)=>items.map(o=>o.value).filter(Boolean)')
            self.assertEqual(len(ids),2)
            page.locator('[data-connection-key=printerId]').select_option(ids[0])
            image=page.locator('#core-canvas .bambu-preview img.package-artwork')
            expect(image).to_have_js_property('naturalWidth',30)
            preview=page.locator('#core-canvas .bambu-preview')
            expect(preview.locator('.native-title')).to_have_text('H2D workshop')
            expect(preview.locator('.native-source')).to_have_text('Printing')
            expect(preview.locator('.bambu-sample')).to_have_text('Sample')
            for width in (1600,390):
                page.set_viewport_size(dict(width=width,height=1000))
                self.assertTrue(preview.evaluate('''card => {
                    const box = selector => card.querySelector(selector).getBoundingClientRect();
                    const image = box('.package-artwork'), value = box('.native-value');
                    const status = box('.native-source'), bar = box('.native-track');
                    return value.right < image.left && status.right < image.left &&
                        value.bottom < status.top && image.bottom < bar.top;
                }'''))
            page.set_viewport_size(dict(width=1600,height=1000))
            first_thumbnail=image.get_attribute('src')
            page.locator('[data-connection-key=printerId]').select_option(ids[1])
            expect(image).to_have_js_property('naturalWidth',30)
            self.assertNotEqual(first_thumbnail,image.get_attribute('src'))
            page.locator('[data-connection-key=printerId]').select_option(ids[0])
            item.drag_to(page.locator('#core-screen'));page.locator('[data-connection-key=printerId]').select_option(ids[1])
            page.locator('#draft-save').click();expect(page.locator('#draft-status')).to_contain_text('Draft saved')
            saved=page.request.get('http://'+host+'/api/editor',headers={'X-Studio-Token':server.SESSION_TOKEN}).json()['draft']
            cards=[w['param']['payload']['params'] for w in saved['profiles'][0]['homeData'] if w.get('param',{}).get('payload',{}).get('params',{}).get('kind')=='bambu']
            self.assertEqual([c['printerId'] for c in cards],ids)
            for secret in ('LAN12345','LAN67890','192.168.1.30','SYNTHETIC123','b'*64):self.assertNotIn(secret,str(saved))
            self.assertFalse(saved['background_apps'])
            page.locator('[data-connection-key=printerId]').select_option(ids[0]);page.locator('#widget-undo').click()
            expect(page.locator('[data-connection-key=printerId]')).to_have_value(ids[1])

    def test_independent_cards_save_reload_and_undo(self):
        template=dict(DEFAULTS,id='bambu-liquid',name='Bambu',kind='bambu',background='#14202b',accent='#86e4c3',_widgetPackage=True,_storePackage='studio.bambu.panel',_storeVersion='1.0.0',_bundledApp=dict(id='dk.ultrabar.bambu',name='Bambu'))
        template['_studio']=legacy_descriptor(template)
        with sync_playwright() as pw,fixture.ActionWizardTests().workspace(pw) as (page,host,root,program,picker,legacy):
            page.route('**/api/store/installed',lambda r:r.fulfill(json=dict(installed=[],widgets=[template])))
            page.evaluate("window.dispatchEvent(new Event('studio-store-changed'))")
            page.locator('#mode-layout').click()
            item=page.locator('#widget-library').get_by_role('button',name='Bambu',exact=True)
            expect(item).to_be_visible();item.drag_to(page.locator('#core-screen'))
            expect(page.locator('#background-apps button')).to_have_count(0)
            page.locator('#widget-setting-primary').select_option('remaining')
            page.locator('#widget-setting-secondary').select_option('job')
            page.locator('#widget-setting-expandedSlots').fill('5');page.locator('#widget-setting-expandedSlots').press('Tab')
            page.locator('#widget-setting-showControls').uncheck();page.locator('#widget-setting-liquidMotion').uncheck()
            item.drag_to(page.locator('#core-screen'))
            expect(page.locator('#background-apps button')).to_have_count(0)
            expect(page.locator('#widget-setting-expandedSlots')).to_have_value('3')
            expect(page.locator('#widget-setting-showControls')).to_be_checked()
            page.locator('#draft-save').click();expect(page.locator('#draft-status')).to_contain_text('Draft saved')
            saved=page.request.get('http://'+host+'/api/editor',headers={'X-Studio-Token':server.SESSION_TOKEN}).json()['draft']
            cards=[w['param']['payload']['params'] for w in saved['profiles'][0]['homeData'] if w.get('param',{}).get('payload',{}).get('params',{}).get('kind')=='bambu']
            self.assertEqual(len(cards),2);self.assertEqual(cards[0]['expandedSlots'],5);self.assertFalse(cards[0]['showControls']);self.assertEqual(cards[0]['primary'],'remaining');self.assertEqual(cards[1]['expandedSlots'],3)
            self.assertFalse(saved['background_apps'])
            page.locator('#widget-setting-expandedSlots').fill('2');page.locator('#widget-setting-expandedSlots').press('Tab');page.locator('#widget-undo').click()
            expect(page.locator('#widget-setting-expandedSlots')).to_have_value('3')
            out=Path(__file__).parent/'data/qa';out.mkdir(exist_ok=True,parents=True)
            page.screenshot(path=str(out/'bambu-settings-desktop.png'),full_page=True)
            page.set_viewport_size(dict(width=390,height=1000));page.screenshot(path=str(out/'bambu-settings-mobile.png'),full_page=True)
            self.assertTrue(page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'))
            page.reload();page.locator('#connection-open').click();page.locator('#manual-connection summary').click()
            page.locator('#target').fill('192.168.1.20:5555');page.locator('#connect').click()
            page.locator('#nav-editor').click();page.locator('#mode-layout').click()
            page.locator('#core-canvas .bambu-preview').first.click()
            expect(page.locator('#widget-setting-expandedSlots')).to_have_value('5')
            expect(page.locator('#widget-setting-primary')).to_have_value('remaining')
