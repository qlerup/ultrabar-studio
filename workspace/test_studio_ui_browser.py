"""Packages supply labels/defaults; the common UI preserves per-widget values."""
import copy
import unittest
from playwright.sync_api import sync_playwright, expect
import server
import studio_contract
import test_action_wizard_browser as fixture


class StudioPanelBrowserTests(unittest.TestCase):
    def test_two_packages_own_their_fields_without_studio_specific_ui(self):
        templates=[]
        for package, name, label, default in [('example.first','First clock','First ticking',False),('example.second','Second clock','Second ticking',True)]:
            descriptor=dict(api=1,settings=dict(api=1,fields=[dict(key='showSeconds',label=label,type='boolean',default=default)]),help=name+' help from package')
            templates.append(dict(id='clock',name=name,kind='clock',_widgetPackage=True,_storePackage=package,_storeVersion='1.0.0',_studio=descriptor))
        with sync_playwright() as pw,fixture.ActionWizardTests().workspace(pw) as (page,host,root,program,picker,legacy):
            page.route('**/api/store/installed',lambda r:r.fulfill(json=dict(installed=[],widgets=templates)))
            page.evaluate("window.dispatchEvent(new Event('studio-store-changed'))")
            page.locator('#mode-layout').click()
            first=page.locator('#widget-library').get_by_role('button',name='First clock',exact=True)
            expect(first).to_be_visible();first.drag_to(page.locator('#core-screen'))
            expect(page.get_by_label('First ticking')).not_to_be_checked()
            expect(page.locator('#widget-properties')).to_contain_text('First clock help from package')
            page.get_by_label('First ticking').check()
            page.locator('#widget-library').get_by_role('button',name='Second clock',exact=True).drag_to(page.locator('#core-screen'))
            expect(page.get_by_label('Second ticking')).to_be_checked()
            expect(page.get_by_label('First ticking')).to_have_count(0)
            page.get_by_label('Second ticking').uncheck()
            page.locator('#draft-save').click();expect(page.locator('#draft-status')).to_contain_text('Draft saved')
            saved=page.request.get('http://'+host+'/api/editor',headers={'X-Studio-Token':server.SESSION_TOKEN}).json()['draft']
            specs=[w['param']['payload']['params'] for w in saved['profiles'][0]['homeData'] if w.get('param',{}).get('payload',{}).get('params',{}).get('packageId') in ('example.first','example.second')]
            self.assertEqual([(s['packageId'],s['showSeconds']) for s in specs],[('example.first',True),('example.second',False)])
            for spec in specs:self.assertNotIn('studio',spec);self.assertNotIn('_studio',spec)

    def test_connection_panel_uses_package_labels_and_secret_fields(self):
        descriptor=copy.deepcopy(studio_contract.legacy_bambu())
        descriptor['connection'].update(title='Workshop devices',manageLabel='Configure workshop',label='Device',itemLabel='device')
        descriptor['connection']['fields'][0]['label']='Device nickname'
        descriptor['settings']['fields'][0]['label']='Dashboard reading'
        template=dict(id='device',name='Workshop',kind='bambu',_widgetPackage=True,_storePackage='example.workshop',_storeVersion='1.0.0',_studio=descriptor)
        with sync_playwright() as pw,fixture.ActionWizardTests().workspace(pw) as (page,host,root,program,picker,legacy):
            page.route('**/api/store/installed',lambda r:r.fulfill(json=dict(installed=[],widgets=[template])))
            page.route('**/api/studio/integrations/example.workshop/device/list',lambda r:r.fulfill(json=dict(items=[])))
            page.evaluate("window.dispatchEvent(new Event('studio-store-changed'))")
            page.locator('#mode-layout').click()
            item=page.locator('#widget-library').get_by_role('button',name='Workshop',exact=True)
            expect(item).to_be_visible();item.drag_to(page.locator('#core-screen'))
            expect(page.get_by_label('Dashboard reading')).to_be_visible()
            page.get_by_role('button',name='Configure workshop',exact=True).click()
            expect(page.get_by_role('heading',name='Workshop devices',exact=True)).to_be_visible()
            expect(page.get_by_label('Device nickname')).to_be_visible()
            expect(page.locator('[data-connection-field=code]')).to_have_attribute('type','password')
            expect(page.get_by_role('heading',name='Add device',exact=True)).to_be_visible()
            page.locator('#studio-connections').get_by_role('button',name='Close',exact=True).click()


if __name__=='__main__':unittest.main()
