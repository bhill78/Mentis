"""Bounded presentation interaction check for the hover/focus puck indicators.
No Brain, API target or persistent server. Owns port 5440 (claimed resource)."""
from pathlib import Path
import subprocess
import time
import urllib.request
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
URL = 'http://127.0.0.1:5440/tests/quiet_magnet_indicators.html'
checks = 0

def check(value, message):
    global checks
    assert value, message
    checks += 1

with (ROOT / 'quiet-magnet-indicators-browser.log').open('w', encoding='utf-8') as log:
    proc = subprocess.Popen(['node', 'node_modules/vite/bin/vite.js', '--config', 'tests/quiet_magnet_indicators_vite.mjs'], cwd=ROOT, stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
    print(f'indicators renderer harness pid: {proc.pid}', flush=True)
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(URL, timeout=1).close()
                break
            except OSError:
                time.sleep(.1)
        else:
            raise RuntimeError('indicators renderer harness did not start')
        assert proc.poll() is None, 'this test must own the harness it checks'
        with sync_playwright() as p:
            browser = p.chromium.launch(channel='msedge', headless=True)
            page = browser.new_page(viewport={'width': 1200, 'height': 850})
            errors = []
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.goto(URL)
            puck = page.get_by_role('button', name='Colony Island fixture Magnet', exact=True)
            expect(puck).to_be_visible()
            check(page.get_by_role('group', name='Colony Island fixture quick indicators').count() == 0, 'resting puck has no indicator ring: stays compact')

            puck.hover()
            indicators = page.get_by_role('group', name='Colony Island fixture quick indicators')
            expect(indicators).to_be_visible()
            check(True, 'hovering the puck reveals the indicator ring')

            posts_ind = page.get_by_role('button', name='Posts: 28 posts reported by the source', exact=False)
            expect(posts_ind).to_be_visible()
            check(True, 'Posts indicator names the source-wide total, not the loaded selection')

            files_ind = page.get_by_role('button', name='Files: 1 loaded, page partial', exact=False)
            expect(files_ind).to_be_visible()
            check(True, 'Files indicator is labelled loaded and names the page as partial, never a bare absent count')

            perspectives_ind = page.get_by_role('button', name='Perspectives: Perspectives unavailable', exact=False)
            expect(perspectives_ind).to_be_visible()
            check(True, 'Perspectives indicator is explicit that no supported type/count exists')

            new_ind = page.get_by_role('button', name='New: New-item count unavailable', exact=False)
            expect(new_ind).to_be_visible()
            check(True, 'New-item indicator is explicit that no supported total exists')

            # Click sets the correct existing tab and calls onExpand.
            files_ind.click()
            check(page.locator('#event').inner_text() == 'expand', 'clicking an indicator calls onExpand')
            check(page.get_by_role('tab', name='Files', exact=True).get_attribute('aria-selected') == 'true', 'clicking the Files indicator selects the Files tab')

            page.evaluate("window.indicatorTest.resource.update({expanded:false,pinned:false,tab:'Overview'})")
            page.mouse.move(0, 0)
            page.locator('#outside').focus()

            # Keyboard focus reaches an indicator after the puck, and activating it is functional.
            puck.focus()
            expect(indicators).to_be_visible()
            page.keyboard.press('Tab')
            check(page.evaluate("document.activeElement.className").find('q2-magnet-indicator-posts') != -1, 'Tab from the puck reaches the first indicator (Posts)')
            page.keyboard.press('Enter')
            check(page.get_by_role('tab', name='Posts', exact=True).get_attribute('aria-selected') == 'true', 'activating a focused indicator by keyboard opens the correct tab')

            page.evaluate("window.indicatorTest.resource.update({expanded:false,pinned:false,tab:'Overview'})")
            page.mouse.move(0, 0)
            page.locator('#outside').focus()

            # Touch tap is functional.
            touch = browser.new_context(viewport={'width': 1200, 'height': 850}, is_mobile=True, has_touch=True)
            mobile = touch.new_page()
            mobile.goto(URL)
            mobile.get_by_role('button', name='Colony Island fixture Magnet', exact=True).tap()
            mobile.get_by_role('button', name='Perspectives: Perspectives unavailable', exact=False).tap()
            check(mobile.locator('#event').inner_text() == 'expand', 'tapping an indicator on touch calls onExpand')
            check(mobile.get_by_role('tab', name='Perspectives', exact=True).get_attribute('aria-selected') == 'true', 'tapping the Perspectives indicator opens the Perspectives explanation tab')
            touch.close()

            check(not errors, f'no browser errors: {errors}')
            browser.close()
    finally:
        proc.terminate()
        proc.wait(timeout=10)
print(f'Quiet Magnet indicators browser: {checks} passed, 0 failed, 0 skipped, 0 errors')
