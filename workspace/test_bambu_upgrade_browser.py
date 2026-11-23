"""Existing Bambu app shows Update and preserves its placed card after upgrading."""
import copy,unittest
from pathlib import Path
from unittest.mock import patch
from playwright.sync_api import sync_playwright,expect
import editor,server,store
import test_action_wizard_browser as fixture_browser
from test_bambu_upgrade import upgraded,legacy,layout


class BambuUpgradeBrowserTests(unittest.TestCase):
    def test_duplicate_widget_is_shown_as_one_update(self):
        package,raw=upgraded()
        def fetch(url,limit,destination=None):
            if destination is None:return raw
            destination.write(raw);return len(raw)
        with sync_playwright() as pw,fixture_browser.ActionWizardTests().workspace(pw) as (page,host,root,program,picker,unused),patch.object(store,'catalog',return_value=[package]),patch.object(store,'fetch',side_effect=fetch):
            page.unroute('**/api/store/installed');server.store.job=None
            server.store.save({'studio.bambu.widget:pc':legacy(True)})
            page.locator('#nav-store').click();card=page.locator('.store-card');expect(card).to_have_count(1)
            expect(card).to_contain_text('Version 2.0.1 / In library: 2.0.0')
            card.get_by_role('button',name='Update',exact=True).click();page.locator('#store-install-confirm').click()
            expect(page.locator('#store-progress-title')).to_have_text('Update ready to deploy',timeout=15000)
            page.locator('#store-progress-later').click();expect(card).to_have_count(1)
            expect(card).to_contain_text('In library: 2.0.1')
            self.assertEqual(list(server.store.records()),['studio.bambu:pc'])

    def test_original_installation_updates_without_readding_card(self):
        package,raw=upgraded()
        def fetch(url,limit,destination=None):
            if destination is None:return raw
            destination.write(raw);return len(raw)
        with sync_playwright() as pw,fixture_browser.ActionWizardTests().workspace(pw) as (page,host,root,program,picker,unused),patch.object(store,'catalog',return_value=[package]),patch.object(store,'fetch',side_effect=fetch):
            page.unroute('**/api/store/installed');server.store.job=None
            server.store.save({'studio.bambu:pc':legacy()})
            snapshot=server.connection['snapshot'];draft=editor.load_draft(server,snapshot)
            draft['profiles'][0]['homeData'].append(layout()[0]['homeData'][-1])
            draft['background_apps']=[dict(id='dk.ultrabar.bambu',name='Bambu',settings=dict(launch=False))]
            draft['app_settings']={'dk.ultrabar.bambu':dict(allowControls=False)}
            editor.atomic_json(editor.draft_path(server,snapshot['device_id']),draft)
            page.reload();page.locator('#connection-open').click();page.locator('#manual-connection summary').click()
            page.locator('#target').fill(snapshot['target']);page.locator('#connect').click()
            page.locator('#nav-editor').click();page.locator('#mode-layout').click()
            page.locator('#nav-store').click()
            card=page.locator('.store-card');expect(card).to_have_count(1)
            expect(card).to_contain_text('Version 2.0.1 / In library: 1.0.1')
            expect(card.get_by_role('button',name='Update',exact=True)).to_be_enabled()
            card.get_by_role('button',name='Update',exact=True).click();page.locator('#store-install-confirm').click()
            expect(page.locator('#store-progress-title')).to_have_text('Update ready to deploy',timeout=15000)
            page.locator('#store-progress-later').click();expect(card).to_have_count(1)
            expect(card).to_contain_text('In library: 2.0.1')
            page.locator('#nav-editor').click();page.locator('#mode-layout').click()
            placed=page.locator('#core-canvas .canvas-widget').filter(has_text='My workshop printer');expect(placed).to_have_count(1);placed.click()
            expect(page.locator('#widget-setting-primary')).to_have_value('remaining');expect(page.locator('#widget-setting-expandedSlots')).to_have_value('5')
            expect(page.locator('#widget-setting-showControls')).not_to_be_checked()
            expect(page.locator('#background-apps button:not([data-builtin])')).to_have_count(0)
            page.locator('#draft-save').click();expect(page.locator('#draft-status')).to_contain_text('Draft saved')
            saved=page.request.get('http://'+host+'/api/editor',headers={'X-Studio-Token':server.SESSION_TOKEN}).json()['draft']
            spec=saved['profiles'][0]['homeData'][-1]['param']['payload']['params']
            self.assertEqual(spec['packageId'],'studio.bambu');self.assertEqual(spec['packageVersion'],'2.0.1')
            self.assertNotIn('companionApp',spec);self.assertFalse(saved['app_settings'])
            self.assertEqual(saved['profiles'][0]['homeData'][-1]['id'],'studio_native_'+'b'*32)
            out=Path(__file__).parent/'data/qa';out.mkdir(exist_ok=True,parents=True);page.screenshot(path=str(out/'bambu-upgrade-preserved-layout.png'))
