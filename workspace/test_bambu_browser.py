"""Offline browser acceptance: per-card settings, history and persistent drafts."""
import unittest
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
import server
from unittest.mock import patch
import bambu
import test_action_wizard_browser as fixture
from bambu_contract import DEFAULTS

class BambuBrowserTests(unittest.TestCase):
    def test_studio_printer_setup_independent_selection_and_no_draft_secrets(self):
        template=dict(DEFAULTS,id='bambu-liquid',name='Bambu',kind='bambu',background='#14202b',accent='#86e4c3',_widgetPackage=True,_storePackage='studio.bambu.widget',_storeVersion='2.0.0')
        with sync_playwright() as pw,fixture.ActionWizardTests().workspace(pw) as (page,host,root,program,picker,legacy),patch.object(bambu.Link,'start'):
            page.route('**/api/store/installed',lambda r:r.fulfill(json=dict(installed=[],widgets=[template])))
            page.route('**/api/bambu/probe',lambda r:r.fulfill(json=dict(pin='b'*64)))
            page.evaluate("window.dispatchEvent(new Event('studio-store-changed'))")
            page.locator('#mode-layout').click()
            item=page.locator('#widget-library').get_by_role('button',name='Bambu',exact=True)
            expect(item).to_be_visible();item.drag_to(page.locator('#core-screen'))
            page.locator('#bambu-manage').click()
            expect(page.locator('#bambu-connections')).to_be_visible()
            page.locator('#bambu-connection-name').fill('H2D workshop')
            page.locator('#bambu-connection-host').fill('192.168.1.30')
            page.locator('#bambu-connection-serial').fill('SYNTHETIC123')
            page.locator('#bambu-connection-code').fill('LAN12345')
            page.get_by_role('button',name='Check connection',exact=True).click()
            expect(page.locator('.bambu-fingerprint')).to_have_text('b'*64)
            page.get_by_role('button',name='Trust certificate & save',exact=True).click()
            expect(page.locator('.bambu-printer-row')).to_have_count(1)
            expect(page.locator('#bambu-connection-code')).to_have_value('')
            page.locator('#bambu-connection-name').fill('H3C office')
            page.locator('#bambu-connection-host').fill('192.168.1.31')
            page.locator('#bambu-connection-serial').fill('SYNTHETIC456')
            page.locator('#bambu-connection-code').fill('LAN67890')
            page.get_by_role('button',name='Check connection',exact=True).click()
            page.get_by_role('button',name='Trust certificate & save',exact=True).click()
            expect(page.locator('.bambu-printer-row')).to_have_count(2)
            page.set_viewport_size(dict(width=390,height=1000))
            out=Path(__file__).parent/'data/qa';out.mkdir(exist_ok=True,parents=True)
            page.screenshot(path=str(out/'bambu-connections-mobile.png'),full_page=True)
            self.assertTrue(page.locator('#bambu-connections').evaluate('(d)=>d.scrollWidth<=d.clientWidth+1'))
            page.set_viewport_size(dict(width=1600,height=1000));page.screenshot(path=str(out/'bambu-connections-desktop.png'),full_page=True)
            page.locator('#bambu-connections').get_by_role('button',name='Close',exact=True).click()
            ids=page.locator('#bambu-printerId option').evaluate_all('(items)=>items.map(o=>o.value).filter(Boolean)')
            self.assertEqual(len(ids),2)
            page.locator('#bambu-printerId').select_option(ids[0])
            item.drag_to(page.locator('#core-screen'));page.locator('#bambu-printerId').select_option(ids[1])
            page.locator('#draft-save').click();expect(page.locator('#draft-status')).to_contain_text('Draft saved')
            saved=page.request.get('http://'+host+'/api/editor',headers={'X-Studio-Token':server.SESSION_TOKEN}).json()['draft']
            cards=[w['param']['payload']['params'] for w in saved['profiles'][0]['homeData'] if w.get('param',{}).get('payload',{}).get('params',{}).get('kind')=='bambu']
            self.assertEqual([c['printerId'] for c in cards],ids)
            for secret in ('LAN12345','LAN67890','192.168.1.30','SYNTHETIC123','b'*64):self.assertNotIn(secret,str(saved))
            self.assertFalse(saved['background_apps'])
            page.locator('#bambu-printerId').select_option(ids[0]);page.locator('#widget-undo').click()
            expect(page.locator('#bambu-printerId')).to_have_value(ids[1])

    def test_independent_cards_save_reload_and_undo(self):
        template=dict(DEFAULTS,id='bambu-liquid',name='Bambu',kind='bambu',background='#14202b',accent='#86e4c3',_widgetPackage=True,_storePackage='studio.bambu.panel',_storeVersion='1.0.0',_bundledApp=dict(id='dk.ultrabar.bambu',name='Bambu'))
        with sync_playwright() as pw,fixture.ActionWizardTests().workspace(pw) as (page,host,root,program,picker,legacy):
            page.route('**/api/store/installed',lambda r:r.fulfill(json=dict(installed=[],widgets=[template])))
            page.evaluate("window.dispatchEvent(new Event('studio-store-changed'))")
            page.locator('#mode-layout').click()
            item=page.locator('#widget-library').get_by_role('button',name='Bambu',exact=True)
            expect(item).to_be_visible();item.drag_to(page.locator('#core-screen'))
            expect(page.locator('#background-apps button')).to_have_count(0)
            page.locator('#bambu-primary').select_option('remaining')
            page.locator('#bambu-secondary').select_option('job')
            page.locator('#bambu-expandedSlots').select_option('5')
            page.locator('#bambu-showControls').uncheck();page.locator('#bambu-liquidMotion').uncheck()
            item.drag_to(page.locator('#core-screen'))
            expect(page.locator('#background-apps button')).to_have_count(0)
            expect(page.locator('#bambu-expandedSlots')).to_have_value('3')
            expect(page.locator('#bambu-showControls')).to_be_checked()
            page.locator('#draft-save').click();expect(page.locator('#draft-status')).to_contain_text('Draft saved')
            saved=page.request.get('http://'+host+'/api/editor',headers={'X-Studio-Token':server.SESSION_TOKEN}).json()['draft']
            cards=[w['param']['payload']['params'] for w in saved['profiles'][0]['homeData'] if w.get('param',{}).get('payload',{}).get('params',{}).get('kind')=='bambu']
            self.assertEqual(len(cards),2);self.assertEqual(cards[0]['expandedSlots'],5);self.assertFalse(cards[0]['showControls']);self.assertEqual(cards[0]['primary'],'remaining');self.assertEqual(cards[1]['expandedSlots'],3)
            self.assertFalse(saved['background_apps'])
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
