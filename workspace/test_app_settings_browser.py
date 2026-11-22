import json,unittest
from pathlib import Path
from unittest.mock import patch
from playwright.sync_api import sync_playwright,expect
import server
import test_action_wizard_browser as fixture
from test_app_settings_contract import schema

class AppSettingsBrowserTests(unittest.TestCase):
    def test_generated_fields_read_edit_save_undo_and_reload(self):
        package='dk.example.studiosettings';definition=schema()
        record=dict(id='example.settings',name='Settings example',type='corebar-app',version='1.0.0',android=dict(packageId=package),settings=definition,deferred=True)
        with sync_playwright() as pw,fixture.ActionWizardTests().workspace(pw) as (page,host,root,program,picker,legacy),patch.object(server.store,'records',return_value={'example':record}):
            page.route('**/api/store/installed',lambda r:r.fulfill(json=dict(installed=[record],widgets=[dict(id=package,name='Settings example',type='APPS',_storePackage='example.settings',_storeVersion='1.0.0')])) )
            page.evaluate("window.dispatchEvent(new Event('studio-store-changed'))")
            page.locator('#mode-layout').click()
            item=page.locator('#widget-library').get_by_role('button',name='Settings example',exact=True)
            expect(item).to_be_visible();item.drag_to(page.locator('#background-drop'))
            panel=page.locator('.app-settings-form');expect(panel).to_be_visible();expect(panel.locator('[data-app-setting]')).to_have_count(6)
            expect(panel).to_contain_text('Defaults are shown')
            actual={f['key']:f['default'] for f in definition['fields']};actual.update(delay=1750,title='From Core')
            page.route('**/api/editor/app-settings/read',lambda r:r.fulfill(json=dict(values=actual)))
            panel.get_by_role('button',name='Read settings from Core').click()
            expect(panel.locator('[data-app-setting="delay"]')).to_have_value('1750');expect(panel.locator('[data-app-setting="title"]')).to_have_value('From Core')
            panel.locator('[data-app-setting="mode"]').select_option('quiet')
            panel.locator('[data-app-setting="delay"]').fill('2000');panel.locator('[data-app-setting="delay"]').press('Tab')
            panel.locator('[data-app-setting="enabled"]').uncheck()
            page.locator('#draft-save').click();expect(page.locator('#draft-status')).to_contain_text('Draft saved')
            saved=page.request.get('http://'+host+'/api/editor',headers={'X-Studio-Token':server.SESSION_TOKEN}).json()['draft']
            self.assertEqual(saved['app_settings'][package],dict(actual,delay=2000,mode='quiet',enabled=False))
            panel.locator('[data-app-setting="delay"]').fill('2500');panel.locator('[data-app-setting="delay"]').press('Tab')
            page.locator('#widget-undo').click();page.locator('#background-apps button').click();expect(panel.locator('[data-app-setting="delay"]')).to_have_value('2000')
            page.set_viewport_size(dict(width=1920,height=1100));out=Path(__file__).parent/'data/qa';out.mkdir(exist_ok=True,parents=True)
            page.screenshot(path=str(out/'app-settings-1920.png'),full_page=True)
            page.set_viewport_size(dict(width=390,height=900));page.screenshot(path=str(out/'app-settings-390.png'),full_page=True)
            self.assertEqual(saved['profiles'],saved['base_profiles'])

    def test_installed_widget_updates_open_panel_and_preserves_instances(self):
        import store
        panel = dict(api=2,settings=dict(api=1,fields=[dict(key='faceColor',label='Face color',type='color',default='#123456')]))
        panel['layout']={size:[dict(op='rect',box=[0,0,24,24],color='$faceColor')] for size in ('large','small')}
        panel['layout']['expanded']=[dict(op='rect',box=[0,0,1000,1000],color='$faceColor')]
        widget = dict(id='face',name='Package clock',kind='scene',studio=panel)
        record = dict(id='test.clock',name='Test Clock',type='corebar-widget',version='1.0.0')
        def install():
            record['widgets']=store.widget_package(json.dumps(dict(widgetApi=1,runtime='studio-native-v1',widgets=[widget])).encode())
        install()
        with sync_playwright() as pw,fixture.ActionWizardTests().workspace(pw) as (page,host,root,program,picker,legacy),patch.object(server.store,'records',return_value={'test.clock:pc':record}):
            page.route('**/api/store/installed',lambda route:route.fulfill(json=dict(installed=[record], widgets=server.store.templates())))
            page.evaluate("window.dispatchEvent(new Event('studio-store-changed'))")
            page.locator('#mode-layout').click()
            item=page.locator('#widget-library').get_by_role('button',name='Package clock',exact=True)
            item.drag_to(page.locator('#core-screen'))
            color=page.locator('#widget-setting-faceColor')
            expect(color).to_have_value('#123456')
            pixel="""() => {const c=document.querySelector('#core-screen canvas.package-scene');return c && Array.from(c.getContext('2d').getImageData(6,6,1,1).data).slice(0,3).join(',')} """
            page.wait_for_function("()=>("+pixel+")()==='18,52,86'")
            def expanded_pixel(rgb):
                page.get_by_role('button',name='Preview unfolded widget').click()
                page.wait_for_function("()=>("+pixel.replace('#core-screen canvas', 'dialog canvas')+")()==='"+rgb+"'")
                page.get_by_role('dialog').get_by_role('button',name='Close').click()
            expanded_pixel('18,52,86')
            color.fill('#654321')
            color.dispatch_event('change')
            page.locator('#draft-save').click()
            expect(page.locator('#draft-status')).to_contain_text('Draft saved')
            panel['settings']['fields'].append(dict(key='chimes',label='Enable chimes',type='boolean',default=True))
            for layers in panel['layout'].values():layers[0]['color']='#f09923'
            record['version']='1.1.0'
            install()
            page.evaluate("window.dispatchEvent(new Event('studio-store-changed'))")
            expect(page.get_by_label('Enable chimes')).to_be_checked()
            page.wait_for_function("()=>("+pixel+")()==='240,153,35'")
            expanded_pixel('240,153,35')
            expect(color).to_have_value('#654321')
            expect(page.locator('#background-apps button')).to_have_count(0)
            page.get_by_label('Enable chimes').uncheck()
            page.locator('#draft-save').click()
            expect(page.locator('#draft-status')).to_contain_text('Draft saved')
            saved=page.request.get('http://'+host+'/api/editor',headers={'X-Studio-Token':server.SESSION_TOKEN}).json()['draft']
            cards=[w for profile in saved['profiles'] for w in profile['homeData'] if w.get('name')=='Package clock']
            self.assertEqual(cards[0]['param']['payload']['params']['packageSettings'],{'chimes':False,'faceColor':'#654321'})
