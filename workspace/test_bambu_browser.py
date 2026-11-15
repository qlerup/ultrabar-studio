"""Offline browser acceptance: per-card settings, history and persistent drafts."""
import unittest
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
import server
import test_action_wizard_browser as fixture
from bambu_contract import DEFAULTS

class BambuBrowserTests(unittest.TestCase):
    def test_independent_cards_save_reload_and_undo(self):
        template=dict(DEFAULTS,id='bambu-liquid',name='Bambu Liquid',kind='bambu',background='#14202b',accent='#86e4c3',_widgetPackage=True,_storePackage='studio.bambu.panel',_storeVersion='1.0.0',_bundledApp=dict(id='dk.ultrabar.bambu',name='Bambu Panel'))
        with sync_playwright() as pw,fixture.ActionWizardTests().workspace(pw) as (page,host,root,program,picker,legacy):
            page.route('**/api/store/installed',lambda r:r.fulfill(json=dict(installed=[],widgets=[template])))
            page.evaluate("window.dispatchEvent(new Event('studio-store-changed'))")
            page.locator('#mode-layout').click()
            item=page.locator('#widget-library').get_by_role('button',name='Bambu Liquid',exact=True)
            expect(item).to_be_visible();item.drag_to(page.locator('#core-screen'))
            expect(page.locator('#background-apps button')).to_have_count(1)
            expect(page.locator('#background-apps')).to_contain_text('Bambu Panel')
            page.locator('#bambu-primary').select_option('remaining')
            page.locator('#bambu-secondary').select_option('job')
            page.locator('#bambu-expandedSlots').select_option('5')
            page.locator('#bambu-showControls').uncheck();page.locator('#bambu-liquidMotion').uncheck()
            item.drag_to(page.locator('#core-screen'))
            expect(page.locator('#background-apps button')).to_have_count(1)
            expect(page.locator('#bambu-expandedSlots')).to_have_value('3')
            expect(page.locator('#bambu-showControls')).to_be_checked()
            page.locator('#draft-save').click();expect(page.locator('#draft-status')).to_contain_text('Draft saved')
            saved=page.request.get('http://'+host+'/api/editor',headers={'X-Studio-Token':server.SESSION_TOKEN}).json()['draft']
            cards=[w['param']['payload']['params'] for w in saved['profiles'][0]['homeData'] if w.get('param',{}).get('payload',{}).get('params',{}).get('kind')=='bambu']
            self.assertEqual(len(cards),2);self.assertEqual(cards[0]['expandedSlots'],5);self.assertFalse(cards[0]['showControls']);self.assertEqual(cards[0]['primary'],'remaining');self.assertEqual(cards[1]['expandedSlots'],3)
            self.assertEqual(saved['background_apps'][0]['id'],'dk.ultrabar.bambu')
            self.assertFalse(saved['background_apps'][0]['settings']['launch'])
            page.locator('#bambu-expandedSlots').select_option('2');page.locator('#widget-undo').click()
            expect(page.locator('#bambu-expandedSlots')).to_have_value('3')
            out=Path(__file__).parent/'data/qa';out.mkdir(exist_ok=True,parents=True)
            page.screenshot(path=str(out/'bambu-settings-desktop.png'),full_page=True)
            page.set_viewport_size(dict(width=390,height=1000));page.screenshot(path=str(out/'bambu-settings-mobile.png'),full_page=True)
            self.assertTrue(page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'))
            page.reload();page.locator('#connection-open').click();page.locator('#manual-connection summary').click()
            page.locator('#target').fill('192.168.1.20:5555');page.locator('#connect').click()
            page.locator('#nav-editor').click();page.locator('#mode-layout').click()
            page.locator('#core-canvas .canvas-widget').filter(has_text='SAMPLE PREVIEW').first.click()
            expect(page.locator('#bambu-expandedSlots')).to_have_value('5')
            expect(page.locator('#bambu-primary')).to_have_value('remaining')
