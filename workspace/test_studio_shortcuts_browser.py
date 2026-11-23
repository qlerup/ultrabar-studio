"""Studio website/program widgets: drag placement, sidebar settings and pictures."""
import hashlib
from pathlib import Path
import unittest
from unittest.mock import patch
from playwright.sync_api import sync_playwright,expect
import test_action_wizard_browser as wizard_fixture
from test_widget_images import png
import server,widget_images


class StudioShortcutBrowserTests(unittest.TestCase):
    def test_separate_templates_editable_settings_upload_and_program_icon(self):
        with sync_playwright() as pw, wizard_fixture.ActionWizardTests().workspace(pw) as (page,host,root,program,picker,legacy), patch.object(widget_images,'program_png',return_value=png('#78bbdd')):
            page.set_viewport_size(dict(width=1920,height=1100));page.locator('#mode-layout').click()
            studio=page.locator('details[data-group="studio"]')
            website=studio.get_by_role('button',name='Open website',exact=True)
            launch=studio.get_by_role('button',name='Launch PC app',exact=True)
            expect(website).to_have_count(1);expect(launch).to_have_count(1)
            expect(website.locator('img')).to_have_count(1);expect(launch.locator('img')).to_have_count(1)
            expect(page.get_by_role('button',name='+ Website or PC program',exact=True)).to_have_count(0)
            before=page.locator('#core-canvas .canvas-widget').count()
            website.click();launch.click()
            expect(page.locator('#core-canvas .canvas-widget')).to_have_count(before)
            website.drag_to(page.locator('#background-drop'))
            expect(page.locator('#background-apps button:not([data-builtin])')).to_have_count(0)
            expect(page.locator('#core-canvas .canvas-widget')).to_have_count(before)
            website.drag_to(page.locator('#core-screen'))
            expect(page.locator('#pc-widget-target')).to_be_visible()
            expect(page.locator('#core-canvas .canvas-widget')).to_have_count(before+1)
            page.locator('#draft-save').click();expect(page.locator('#draft-status')).to_contain_text('Draft saved')
            saved=page.request.get('http://'+host+'/api/editor',headers={'X-Studio-Token':server.SESSION_TOKEN}).json()['draft']
            self.assertTrue(saved['profiles'][0]['homeData'][1]['_pcPending'])
            response=page.request.post('http://'+host+'/api/editor/deploy',headers={'X-Studio-Token':server.SESSION_TOKEN},data=dict(device_id=saved['device_id'],revision=saved['revision']))
            self.assertEqual(response.status,400);self.assertIn('Apply settings',response.json()['error'])
            page.locator('#pc-widget-target').fill('file:///bad.exe');page.locator('#pc-widget-apply').click()
            expect(page.locator('#pc-widget-error')).to_contain_text('http://')
            page.locator('#pc-widget-target').fill('https://example.com')
            page.locator('#pc-widget-picture').set_input_files(dict(name='bad.svg',mimeType='image/svg+xml',buffer=b'<svg></svg>'))
            expect(page.locator('#pc-widget-error')).to_contain_text('valid static')
            custom=png('#88cc99',size=(240,120))
            page.locator('#pc-widget-picture').set_input_files(dict(name='banner.png',mimeType='image/png',buffer=custom))
            expect(page.locator('.pc-picture-source')).to_have_text('Your uploaded picture')
            expect(page.locator('#pc-widget-target')).to_have_value('https://example.com')
            page.get_by_label('Display name',exact=True).fill('My docs');page.get_by_label('Display name',exact=True).press('Tab')
            page.locator('#pc-widget-apply').click()
            expect(page.locator('#editor-notice')).to_contain_text('Widget settings applied')
            expect(page.locator('#core-canvas [aria-label="My docs"] img')).to_have_count(1)
            launch.drag_to(page.locator('#core-screen'))
            expect(page.locator('#pc-widget-target')).to_have_value('')
            page.locator('#pc-widget-form').get_by_role('button',name='Browse programs',exact=True).click()
            expect(page.locator('#pc-widget-target')).to_have_value('')
            page.locator('#pc-widget-form').get_by_role('button',name='Browse programs',exact=True).click()
            expect(page.locator('#pc-widget-target')).to_have_value(str(program))
            expect(page.locator('.pc-picture-source')).to_have_text('Automatic program icon')
            page.locator('#pc-widget-picture').set_input_files(dict(name='custom.png',mimeType='image/png',buffer=custom))
            expect(page.locator('.pc-picture-source')).to_have_text('Your uploaded picture')
            page.locator('#pc-widget-form').get_by_role('button',name='Use program icon',exact=True).click()
            expect(page.locator('.pc-picture-source')).to_have_text('Automatic program icon')
            page.locator('#pc-widget-apply').click()
            expect(page.locator('#editor-notice')).to_contain_text('Widget settings applied')
            expect(website).to_have_count(1);expect(launch).to_have_count(1)
            page.wait_for_timeout(450)  # The existing drag gesture suppresses canvas clicks for 400 ms.
            page.locator('#core-canvas [aria-label="My docs"]').click()
            expect(page.locator('#pc-widget-target')).to_have_value('https://example.com')
            page.locator('#pc-widget-target').fill('https://example.com/new');page.locator('#pc-widget-apply').click()
            expect(page.locator('#editor-notice')).to_contain_text('Widget settings applied')
            website.drag_to(page.locator('#core-screen'))
            expect(page.locator('#core-canvas .canvas-widget')).to_have_count(before+3)
            page.locator('#widget-undo').click()
            expect(page.locator('#core-canvas .canvas-widget')).to_have_count(before+2)
            page.locator('#draft-save').click();expect(page.locator('#draft-status')).to_contain_text('Draft saved')
            saved=page.request.get('http://'+host+'/api/editor',headers={'X-Studio-Token':server.SESSION_TOKEN}).json()['draft']
            shortcuts=[w for w in saved['profiles'][0]['homeData'] if w['type']=='PC_CONTROL']
            self.assertEqual(len(shortcuts),2);self.assertTrue(all('_pcPending' not in w for w in shortcuts))
            by_kind={w['param']['payload']['params']['kind']:w for w in shortcuts}
            self.assertEqual(by_kind['url']['param']['payload']['params']['imageSource'],'custom')
            self.assertEqual(by_kind['program']['param']['payload']['params']['imageSource'],'program')
            for w in shortcuts:
                digest=widget_images.picture_hash(w['icon']);self.assertTrue(digest)
                self.assertTrue((root/'widget-images'/(digest+'.png')).exists())
            self.assertEqual(saved['profiles'][0]['module'],saved['base_profiles'][0]['module'])
            # Reload from persisted draft and registered actions, then edit in the sidebar.
            page.reload();page.locator('#connection-open').click();page.locator('#manual-connection summary').click()
            page.locator('#target').fill('192.168.1.20:5555');page.locator('#connect').click()
            page.locator('#nav-editor').click()
            page.locator('#core-canvas [aria-label="My docs"]').click()
            expect(page.locator('#pc-widget-target')).to_have_value('https://example.com/new')
            for width in [1920,390]:
                page.set_viewport_size(dict(width=width,height=1100))
                page.locator('#pc-widget-form').scroll_into_view_if_needed()
                page.screenshot(path=str(server.ROOT/f'data/qa/studio-shortcuts-{width}.png'),full_page=True)
                self.assertTrue(page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'))
