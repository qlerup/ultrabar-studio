"""Opt-in live acceptance test; reads the connected device without changing it."""
from pathlib import Path
from playwright.sync_api import sync_playwright, expect


def main():
    output = Path(__file__).parent / 'data' / 'qa'
    output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={'width': 1440, 'height': 1100})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto('http://127.0.0.1:8741')
        assert page.locator('#empty').is_visible()
        page.wait_for_function("document.querySelector('#target').value !== '' || document.querySelector('#setup-guide').open")
        if page.locator('#setup-guide').is_visible():
            page.locator('#guide-find-devices').click()
        else:
            page.locator('#connection-open').click()
            page.locator('#discover').click()
        expect(page.locator('.discovered-device').first).to_be_visible(timeout=20000)
        page.locator('.discovered-device').first.click()
        page.locator('#discovery-connect').click()
        expect(page.locator('#connection-badge')).to_have_class('badge connected', timeout=65000)
        assert page.locator('.module-card').count() >= 1
        assert page.locator('.widget').count() >= 1
        assert page.locator('.hardware-unit:not(.core-unit)').count() == 6
        assert page.locator('.hardware-unit.sense_cube').count() == 1
        assert page.locator('.hardware-unit.vivo_cube').count() == 2
        assert page.locator('html').get_attribute('lang') == 'en'
        initial = page.evaluate('visibleLayoutOrder()')
        first,second=page.locator('#hardware-preview > .hardware-unit').nth(0),page.locator('#hardware-preview > .hardware-unit').nth(1)
        first.scroll_into_view_if_needed()
        a,b=first.bounding_box(),second.bounding_box()
        page.mouse.move(a['x']+a['width']/2,a['y']+a['height']/2)
        page.mouse.down()
        page.mouse.move(b['x']+b['width']-4,b['y']+b['height']/2,steps=14)
        # A poll arriving during the gesture must not destroy the dragged element.
        page.evaluate('renderHardware()')
        assert page.locator('.drag-ghost').count()==1
        page.mouse.up()
        expect(page.locator('#layout-feedback')).to_have_text('Layout saved')
        reordered=page.evaluate('visibleLayoutOrder()')
        assert reordered!=initial and set(reordered)==set(initial)
        page.evaluate('renderHardware()')
        assert page.evaluate('visibleLayoutOrder()')==reordered
        page.reload()
        page.locator('#connect').click()
        expect(page.locator('#workspace')).to_be_visible(timeout=65000)
        assert page.evaluate('visibleLayoutOrder()')==reordered
        # Keyboard alternative and server failure restore the last saved order.
        page.route('**/api/layout',lambda route:route.fulfill(status=500,json={'error':'Disk unavailable'}))
        page.locator('#hardware-preview > .hardware-unit').first.focus()
        page.keyboard.press('Alt+ArrowRight')
        expect(page.locator('#layout-feedback')).to_contain_text('not saved')
        assert page.evaluate('visibleLayoutOrder()')==reordered
        page.unroute('**/api/layout')
        # Polling must update cards and selected detail without manual refresh.
        hardware = page.evaluate('structuredClone(snapshot.hardware)')
        target = page.evaluate('snapshot.target')
        knob = next(device for device in hardware['devices'] if device['type'] == 'KNOB_KEY')
        knob['online'] = False
        page.route('**/api/hardware', lambda route: route.fulfill(json={'target': target, 'hardware': hardware}))
        card = page.locator('.hardware-unit.knob_key').filter(has=page.locator('.unit-state'))
        chosen = page.locator(f'.hardware-unit[title$="{knob["serial"]}"]')
        expect(chosen.locator('.unit-state')).to_have_text('Offline', timeout=12000)
        chosen.click()
        knob['online'] = True
        expect(chosen.locator('.unit-state')).to_have_text('Online', timeout=12000)
        expect(page.locator('#hardware-detail')).to_contain_text('CoreBAR reports online')
        page.unroute('**/api/hardware')
        page.route('**/api/hardware', lambda route: route.fulfill(status=502, json={'error': 'Connection lost'}))
        expect(chosen.locator('.unit-state')).to_have_text('Unknown', timeout=12000)
        assert page.locator('.hardware-unit:not(.is-unknown)').count() == 0
        page.unroute('**/api/hardware')
        expect(page.locator('#hardware-status')).to_contain_text('updates every 5 seconds', timeout=12000)
        page.locator('#modules').get_by_role('button', name='KnobKey', exact=False).click()
        assert page.locator('#detail-title').inner_text() == 'KnobKey'
        assert page.locator('#events .event').count() >= 1
        page.locator('#screen-button').click()
        expect(page.locator('#screen')).to_be_visible(timeout=65000)
        assert page.locator('#screen').evaluate('(image) => image.complete && image.naturalWidth > 0')
        page.screenshot(path=str(output / 'desktop.png'), full_page=True)
        with page.expect_download() as download:
            page.locator('#backup').click()
        assert download.value.suggested_filename == 'ultrabar-profil-backup.xml'
        page.locator('#refresh').click()
        expect(page.locator('#refresh')).to_be_enabled(timeout=65000)
        for width in [390, 768, 1440]:
            page.set_viewport_size({'width': width, 'height': 950})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'Overflow at {width}'
            if width == 390:
                page.screenshot(path=str(output / 'mobile.png'), full_page=True)
        # Force an offline response without changing the real device/network.
        page.route('**/api/refresh', lambda route: route.fulfill(status=502, json={'error': 'Enheden svarer ikke.'}))
        page.locator('#refresh').click()
        expect(page.locator('#notice')).to_have_class('error')
        assert page.locator('#workspace').is_visible(), 'Last good snapshot must remain available'
        assert not page.locator('#refresh').is_disabled()
        assert not errors, errors
        print('PASS: live connection, six runtime modules, automatic status updates and recovery, English UI, profiles, actions, screenshot, backup, responsive layout; no browser errors.')
        browser.close()


if __name__ == '__main__':
    main()
