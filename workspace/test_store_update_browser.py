import copy,threading,unittest
from pathlib import Path
from unittest.mock import patch
from playwright.sync_api import sync_playwright,expect
import server,store
import test_action_wizard_browser as fixture_browser
from test_store import fixture

class StoreUpdateBrowserTests(unittest.TestCase):
    def test_early_version_rejection_stops_spinner_and_allows_close(self):
        package,raw=fixture();latest=copy.deepcopy(package);latest['version']='1.0.1'
        entered=threading.Event();release=threading.Event()
        def catalog():
            if threading.current_thread().name=='StudioStoreInstall':
                entered.set()
                if not release.wait(8):raise store.StoreError('Version test gate expired')
                blocked=copy.deepcopy(latest);blocked['compatibility']['minStudioVersion']='99.0.0';return [blocked]
            return [latest]
        with sync_playwright() as pw,fixture_browser.ActionWizardTests().workspace(pw) as (page,host,root,program,picker,legacy),patch.object(store,'catalog',side_effect=catalog),patch.object(store,'fetch') as fetch:
            try:
                page.unroute('**/api/store/installed');server.store.job=None
                server.store.save({package['id']+':pc':dict(package,widgets=store.plugin_templates(raw))})
                page.locator('#nav-store').click();page.locator('.store-card').get_by_role('button',name='Update',exact=True).click();page.locator('#store-install-confirm').click()
                expect(page.locator('#store-progress')).to_be_visible();self.assertTrue(entered.wait(3));release.set()
                expect(page.locator('#store-progress-title')).to_have_text('Update interrupted',timeout=15000)
                expect(page.locator('#store-progress-message')).to_contain_text('requires Studio 99.0.0')
                expect(page.locator('#store-progress-package')).to_contain_text('1.0.1')
                expect(page.locator('#store-progress-spinner')).not_to_be_visible()
                expect(page.locator('#store-progress-deploy')).not_to_be_visible()
                expect(page.locator('#store-progress-later')).to_be_enabled()
                out=Path(__file__).parent/'data/qa';out.mkdir(exist_ok=True,parents=True);page.screenshot(path=str(out/'store-early-version-error.png'))
                page.locator('#store-progress-later').click();expect(page.locator('#store-progress')).not_to_be_visible();fetch.assert_not_called()
            finally:release.set()

    def test_close_during_download_does_not_reopen_or_abort_update(self):
        package,raw=fixture();latest=dict(package,version='1.0.1');gate=threading.Event()
        def fetch(url,limit,destination):
            if not gate.wait(8):raise store.StoreError('Close test gate expired')
            destination.write(raw);return len(raw)
        with sync_playwright() as pw,fixture_browser.ActionWizardTests().workspace(pw) as (page,host,root,program,picker,legacy),patch.object(store,'catalog',return_value=[latest]),patch.object(store,'fetch',side_effect=fetch):
            try:
                page.unroute('**/api/store/installed');server.store.job=None
                server.store.save({package['id']+':pc':dict(package,widgets=store.plugin_templates(raw))})
                page.locator('#nav-store').click();card=page.locator('.store-card');card.get_by_role('button',name='Update',exact=True).click();page.locator('#store-install-confirm').click()
                expect(page.locator('#store-progress')).to_be_visible();expect(page.locator('#store-progress-later')).to_be_enabled()
                page.keyboard.press('Escape');expect(page.locator('#store-progress')).not_to_be_visible()
                gate.set();expect(card.locator('.store-deploy-notice')).to_be_visible(timeout=15000)
                expect(page.locator('#store-progress')).not_to_be_visible()
                self.assertEqual(server.store.records()[package['id']+':pc']['version'],'1.0.1')
            finally:gate.set()

    def test_cancel_download_preserves_library_and_allows_retry(self):
        package,raw=fixture();latest=dict(package,version='1.0.1');gate=threading.Event()
        def fetch(url,limit,destination):
            if not gate.wait(8):raise store.StoreError('Cancel test gate expired')
            destination.write(raw);return len(raw)
        with sync_playwright() as pw,fixture_browser.ActionWizardTests().workspace(pw) as (page,host,root,program,picker,legacy),patch.object(store,'catalog',return_value=[latest]),patch.object(store,'fetch',side_effect=fetch):
            try:
                page.unroute('**/api/store/installed');server.store.job=None
                original=dict(package,widgets=store.plugin_templates(raw));server.store.save({package['id']+':pc':original})
                page.locator('#nav-store').click();card=page.locator('.store-card');card.get_by_role('button',name='Update',exact=True).click();page.locator('#store-install-confirm').click()
                expect(page.locator('#store-progress-cancel')).to_be_enabled();page.locator('#store-progress-cancel').click()
                expect(page.locator('#store-progress-message')).to_contain_text('Cancelling update')
                gate.set();expect(page.locator('#store-progress-title')).to_have_text('Update cancelled',timeout=15000)
                expect(page.locator('#store-progress-deploy')).not_to_be_visible()
                self.assertEqual(server.store.records(),{package['id']+':pc':original})
                page.locator('#store-progress-later').click();card.get_by_role('button',name='Update',exact=True).click();page.locator('#store-install-confirm').click()
                expect(page.locator('#store-progress-title')).to_have_text('Update ready to deploy',timeout=15000)
                self.assertEqual(server.store.records()[package['id']+':pc']['version'],'1.0.1')
                page.locator('#store-progress-later').click()
            finally:gate.set()

    def test_progress_later_offline_deploy_review_and_failed_update(self):
        package,raw=fixture();latest=copy.deepcopy(package);latest['version']='1.0.1'
        gate=threading.Event();corrupt=[False]
        def fetch(url,limit,destination=None):
            if not gate.wait(15):raise store.StoreError('Offline test gate expired.')
            data=b'bad bytes' if corrupt[0] else raw
            destination.write(data);return len(data)
        with sync_playwright() as pw,fixture_browser.ActionWizardTests().workspace(pw) as (page,host,root,program,picker,legacy),patch.object(store,'catalog',side_effect=lambda:[latest]),patch.object(store,'fetch',side_effect=fetch):
            try:
                page.unroute('**/api/store/installed');server.store.job=None
                record=copy.deepcopy(package);record['widgets']=store.plugin_templates(raw);server.store.save({package['id']+':pc':record})
                page.locator('#mode-layout').click();page.get_by_role('textbox',name='Display name',exact=True).fill('Keep my draft');page.get_by_role('textbox',name='Display name',exact=True).press('Tab')
                page.locator('#nav-store').click();card=page.locator('.store-card');expect(card.get_by_role('button',name='Update',exact=True)).to_be_enabled()
                card.get_by_role('button',name='Update',exact=True).click();page.locator('#store-install-confirm').click()
                dialog=page.locator('#store-progress');expect(dialog).to_be_visible();expect(page.locator('#store-progress-title')).to_have_text('Updating package')
                expect(page.locator('#store-progress-later')).to_be_enabled();expect(page.locator('#store-progress-spinner')).to_be_visible()
                gate.set();expect(page.locator('#store-progress-title')).to_have_text('Update ready to deploy',timeout=15000)
                expect(page.locator('#store-progress-help')).to_contain_text('after Deploy');expect(page.locator('#store-progress-deploy')).to_be_visible()
                out=Path(__file__).parent/'data/qa';out.mkdir(exist_ok=True,parents=True)
                page.screenshot(path=str(out/'store-update-desktop.png'));page.set_viewport_size(dict(width=390,height=844));page.screenshot(path=str(out/'store-update-mobile.png'))
                self.assertTrue(page.evaluate('document.documentElement.scrollWidth<=innerWidth'));page.set_viewport_size(dict(width=1600,height=1000))
                page.evaluate('window.__updateTestSnapshot=snapshot;snapshot=null')
                page.locator('#store-progress-deploy').click();expect(dialog).to_be_visible();expect(page.locator('#store-progress-message')).to_contain_text('Connect Core first')
                page.evaluate('snapshot=window.__updateTestSnapshot;delete window.__updateTestSnapshot')
                page.locator('#store-progress-later').click();expect(dialog).not_to_be_visible()
                expect(card.locator('.store-deploy-notice')).to_contain_text('Deploy required')
                page.locator('#store-refresh').click();expect(card.locator('.store-deploy-notice')).to_be_visible();expect(dialog).not_to_be_visible()
                card.get_by_role('button',name='Review & deploy').click();expect(page.locator('#deploy-dialog')).to_be_visible()
                expect(page.get_by_role('textbox',name='Display name',exact=True)).to_have_value('Keep my draft')
                page.locator('#deploy-cancel').click();page.locator('#nav-store').click()
                latest['version']='1.0.2';corrupt[0]=True
                page.locator('#store-refresh').click();expect(card.get_by_role('button',name='Update',exact=True)).to_be_enabled()
                card.get_by_role('button',name='Update',exact=True).click();page.locator('#store-install-confirm').click()
                expect(page.locator('#store-progress-title')).to_have_text('Update interrupted',timeout=15000)
                expect(page.locator('#store-progress-deploy')).not_to_be_visible();expect(page.locator('#store-progress-message')).to_contain_text('integrity')
                self.assertEqual(server.store.records()[package['id']+':pc']['version'],'1.0.1')
                page.locator('#store-progress-later').click()
            finally:gate.set()
