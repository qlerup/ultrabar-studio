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
