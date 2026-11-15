from pathlib import Path
import unittest
from playwright.sync_api import sync_playwright,expect
import server
import test_action_wizard_browser as fixture
from test_widget_images import png

class VivoBrowserTests(unittest.TestCase):
    def test_action_icon_upload_clear_undo_and_saved_screen(self):
        serial='0000000000ABCDEF'
        with sync_playwright() as pw,fixture.ActionWizardTests().workspace(pw) as (page,host,root,program,picker,legacy):
            page.evaluate('(device)=>{snapshot.hardware.devices.push(device);window.dispatchEvent(new Event("studio-hardware-changed"));}',dict(serial=serial,type='VIVO_CUBE',name='VivoCube',online=True))
            page.locator('#action-devices [data-layout-key="'+serial+'"]').click()
            box=page.locator('#vivo-screen-settings');expect(box).to_be_visible()
            page.get_by_role('button',name='Screen button 101 / Single press',exact=True).click();page.locator('[data-action-type="website"]').click()
            page.locator('#action-target').fill('https://example.com');page.locator('#action-name').fill('Docs');page.locator('#action-setup-submit').click()
            expect(page.locator('#action-sequence .sequence-item')).to_have_count(1);expect(box.locator('img')).to_be_visible()
            page.locator('#draft-save').click();expect(page.locator('#draft-status')).to_contain_text('Draft saved')
            def saved():return page.request.get('http://'+host+'/api/editor',headers={'X-Studio-Token':server.SESSION_TOKEN}).json()['draft']
            initial=saved()['vivo_screens'][serial];self.assertEqual(initial['source'],'action');self.assertEqual(initial['button'],101)
            page.locator('#vivo-picture-upload').set_input_files(dict(name='bad.svg',mimeType='image/svg+xml',buffer=b'<svg/>'))
            expect(page.locator('#editor-notice')).to_contain_text('valid static PNG')
            page.locator('#vivo-picture-upload').set_input_files(dict(name='photo.png',mimeType='image/png',buffer=png('#8dcfaf')))
            expect(page.locator('#action-feedback')).to_contain_text('screen picture saved')
            page.locator('#draft-save').click();expect(page.locator('#draft-status')).to_contain_text('Draft saved')
            custom=saved()['vivo_screens'][serial];self.assertEqual(custom['source'],'custom');self.assertNotEqual(custom['image'],initial['image'])
            out=Path(__file__).parent/'data/qa';out.mkdir(exist_ok=True,parents=True)
            page.set_viewport_size(dict(width=1920,height=1080));page.screenshot(path=str(out/'vivo-picture-desktop.png'),full_page=True)
            page.set_viewport_size(dict(width=390,height=844));page.screenshot(path=str(out/'vivo-picture-mobile.png'),full_page=True)
            self.assertTrue(page.evaluate('document.documentElement.scrollWidth<=innerWidth'));page.set_viewport_size(dict(width=1600,height=1000))
            page.on('dialog',lambda dialog:dialog.accept());box.get_by_role('button',name='Clear screen & actions').click()
            expect(page.locator('#action-sequence .sequence-item')).to_have_count(0)
            page.locator('#action-undo').click();expect(page.locator('#action-sequence .sequence-item')).to_have_count(1)
            box.get_by_role('button',name='Clear screen & actions').click();page.locator('#draft-save').click();expect(page.locator('#draft-status')).to_contain_text('Draft saved')
            state=saved();self.assertTrue(state['vivo_screens'][serial]['clear'])
            module=next(m for m in state['profiles'][0]['module'] if m['serialNo']==serial)
            self.assertEqual(module['config'][0]['singleClick']['actions'],[])
