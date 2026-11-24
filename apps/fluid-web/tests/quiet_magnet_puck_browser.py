"""Bounded presentation interaction check. No Brain, API target or persistent server.

The approved hybrid card is CLICKED open and stays open (hybrid.js:99-100, the
persisted `open` in its seed at :6). Hover and focus reveal nothing. These
oracles assert that model, replacing the hover-to-open ones.
"""
from pathlib import Path
import subprocess
import time
import urllib.request
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
URL = 'http://127.0.0.1:5439/tests/quiet_magnet_puck.html'
checks = 0

def check(value, message):
    global checks
    assert value, message
    checks += 1

with (ROOT / 'quiet-magnet-puck-browser.log').open('w', encoding='utf-8') as log:
    proc = subprocess.Popen(['node', 'node_modules/vite/bin/vite.js', '--config', 'tests/quiet_magnet_puck_vite.mjs'], cwd=ROOT, stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
    print(f'renderer harness pid: {proc.pid}', flush=True)
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(URL, timeout=1).close()
                break
            except OSError:
                time.sleep(.1)
        else:
            raise RuntimeError('renderer harness did not start')
        assert proc.poll() is None, 'this test must own the harness it checks'
        with sync_playwright() as p:
            browser = p.chromium.launch(channel='msedge', headless=True)
            page = browser.new_page(viewport={'width': 1200, 'height': 850})
            errors = []
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.goto(URL)
            puck = page.get_by_role('button', name='Open Colony Island fixture Magnet', exact=False)
            expect(puck).to_be_visible()
            check(page.get_by_role('region').count() == 0, 'rest has no card')
            check(page.locator('.q2-magnet-rest-title').inner_text().startswith('Colony Island fixture'), 'a closed puck shows its name')

            # Hover changes nothing.
            puck.hover()
            page.wait_for_timeout(80)
            check(page.get_by_role('region').count() == 0, 'hover opens nothing')
            # Focus changes nothing.
            puck.focus()
            page.wait_for_timeout(80)
            check(page.get_by_role('region').count() == 0, 'focusing the puck opens nothing')

            # The click opens it, and it stays open when the pointer leaves.
            puck.click()
            expect(page.get_by_role('region')).to_be_visible()
            page.mouse.move(1100, 20)
            page.wait_for_timeout(80)
            check(page.get_by_role('region').count() == 1, 'the clicked card stays open when the pointer leaves')
            check(page.evaluate('window.magnetTest.resource.snapshot().open') is True, 'open is the state, not the pointer')
            # The wording the source actually renders, now that the card passes retained: true.
            check(page.get_by_role('button', name='Posts: 28 posts retained in the most recent bounded batch', exact=False).count() == 1, 'the retained posts tally names its batch scope')

            # The six approved tabs, in order, with Summary first and selected.
            tabs = page.get_by_role('tab').all_inner_texts()
            check(tabs == ['Summary', 'All', 'Posts', 'Files', 'Perspectives', 'Conversation'], f'six approved tabs in order: {tabs}')
            check(page.get_by_role('tab', name='Summary', exact=True).get_attribute('aria-selected') == 'true', 'Summary is the default tab')
            check(page.get_by_role('button', name='Magnet settings', exact=True).count() == 1, 'the header gear is icon-only with an accessible name')

            # The composer is in the footer slot on every tab.
            for tab in ['Summary', 'All', 'Posts', 'Files', 'Perspectives', 'Conversation']:
                page.get_by_role('tab', name=tab, exact=True).click()
                check(page.locator('#message').count() == 1, f'one composer textarea on {tab}')

            # An unsent draft survives close and reopen (check_hybrid.py:280,282).
            page.get_by_role('tab', name='Posts', exact=True).click()
            page.locator('#message').fill('words not yet sent')
            page.get_by_role('button', name='Close Magnet', exact=True).click()
            expect(page.get_by_role('region')).to_have_count(0)
            expect(puck).to_be_focused()
            checks += 2
            check(page.locator('.q2-magnet-rest-title').inner_text().startswith('Colony Island fixture'), 'closing the card leaves the puck with its name')
            puck.click()
            expect(page.get_by_role('region')).to_be_visible()
            check(page.locator('#message').input_value() == 'words not yet sent', 'the unsent draft survives close and reopen')
            check(page.get_by_role('tab', name='Posts', exact=True).get_attribute('aria-selected') == 'true', 'reopening returns to the tab it was left on')

            # Escape closes the card and returns focus to the puck.
            page.locator('#message').press('Escape')
            expect(page.get_by_role('region')).to_have_count(0)
            expect(puck).to_be_focused()
            checks += 2

            # Enter on the focused puck is the click.
            page.keyboard.press('Enter')
            expect(page.get_by_role('region')).to_be_visible()
            page.mouse.move(1100, 20)
            check(page.get_by_role('region').count() == 1, 'Enter on the puck opens the same card')

            # The size button is a width only: tabs and composer stay.
            width_before = page.locator('.q2-magnet-card').bounding_box()['width']
            page.get_by_role('button', name='Expand Magnet', exact=True).click()
            page.wait_for_timeout(80)
            width_after = page.locator('.q2-magnet-card').bounding_box()['width']
            check(width_after > width_before, 'the size button widens the card')
            check(page.get_by_role('tab').count() == 6 and page.locator('#message').count() == 1, 'widening changes no content')
            page.get_by_role('button', name='Compact Magnet', exact=True).click()
            page.wait_for_timeout(80)
            check(abs(page.locator('.q2-magnet-card').bounding_box()['width'] - width_before) < 2, 'compacting returns the width')

            # Settings is an overlay place: the composer and search line go, the removal is here.
            page.get_by_role('button', name='Magnet settings', exact=True).click()
            expect(page.get_by_role('button', name='Remove this Magnet from the workspace', exact=True)).to_be_visible()
            checks += 1
            check(page.locator('#message').count() == 0, 'the composer is hidden in settings')
            check(page.locator('input[type=search]').count() == 0, 'the search line is hidden in settings')
            page.get_by_role('button', name='Navigate to source Conversation', exact=False).click()
            check(page.locator('#event').inner_text() == 'source', 'source navigation is emitted from settings')
            page.get_by_role('button', name='Magnet settings', exact=True).click()
            check(page.get_by_role('tab', name='Posts', exact=True).get_attribute('aria-selected') == 'true', 'leaving settings returns where the gear was pressed')

            # Evidence inspection and its return.
            page.get_by_role('tab', name='Files', exact=True).click()
            page.get_by_role('button', name='fixture-notes.md', exact=True).click()
            expect(page.get_by_role('button', name='Back to Magnet', exact=False)).to_be_visible()
            checks += 1
            page.get_by_role('button', name='Back to Magnet', exact=False).click()
            check(page.get_by_role('button', name='fixture-notes.md', exact=True).count() == 1, 'the inspection returns to its list')

            # Keyboard and pointer moves.
            page.locator('.q2-magnet-puck').focus()
            before = page.evaluate('window.magnetTest.resource.snapshot().x')
            page.keyboard.press('ArrowRight')
            check(page.evaluate('window.magnetTest.resource.snapshot().x') == before + 12, 'keyboard move')
            box = page.locator('.q2-magnet-puck').bounding_box()
            open_before = page.evaluate('window.magnetTest.resource.snapshot().open')
            page.mouse.move(box['x'] + 30, box['y'] + 30)
            page.mouse.down()
            page.mouse.move(box['x'] + 180, box['y'] + 110, steps=5)
            page.mouse.up()
            check(page.evaluate('window.magnetTest.resource.snapshot().open') == open_before, 'drag suppresses the click, so it never toggles open')
            check(page.evaluate('window.magnetTest.resource.snapshot().x') > before + 12, 'drag changes presentation position')

            # Narrow screen: full-width card that stays inside the canvas.
            page.set_viewport_size({'width': 390, 'height': 720})
            page.evaluate('window.magnetTest.resource.update({x:310,y:600,open:true})')
            page.wait_for_timeout(120)
            box = page.get_by_role('region').bounding_box()
            check(box['x'] >= 0 and box['x'] + box['width'] <= 390, 'narrow card fits canvas')
            check(box['y'] >= 0 and box['y'] + box['height'] <= 720, 'narrow card scrolls inside height')

            # A cancelled drag never toggles open either.
            page.set_viewport_size({'width': 1200, 'height': 850})
            page.evaluate('window.magnetTest.resource.update({open:false})')
            page.wait_for_timeout(80)
            box = page.locator('.q2-magnet-puck').bounding_box()
            page.mouse.move(box['x'] + 30, box['y'] + 30)
            page.mouse.down()
            page.mouse.move(box['x'] - 30, box['y'] - 30, steps=3)
            page.locator('.q2-magnet-puck').dispatch_event('pointercancel', {'pointerId': 1, 'pointerType': 'mouse', 'bubbles': True})
            page.mouse.up()
            check(page.evaluate('window.magnetTest.resource.snapshot().open') is False, 'a cancelled drag never opens the card')

            # Touch: one tap opens it, and scrolling the card does not drag the puck.
            touch = browser.new_context(viewport={'width': 390, 'height': 720}, is_mobile=True, has_touch=True)
            mobile = touch.new_page()
            mobile.goto(URL)
            mobile.get_by_role('button', name='Open Colony Island fixture Magnet', exact=False).tap()
            expect(mobile.get_by_role('region')).to_be_visible()
            check(mobile.evaluate('window.magnetTest.resource.snapshot().open') is True, 'a single tap opens the card')
            position = mobile.evaluate('({x:window.magnetTest.resource.snapshot().x,y:window.magnetTest.resource.snapshot().y})')
            session = touch.new_cdp_session(mobile)
            session.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [{'x': 210, 'y': 450}]})
            session.send('Input.dispatchTouchEvent', {'type': 'touchMove', 'touchPoints': [{'x': 210, 'y': 270}]})
            session.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []})
            check(mobile.evaluate('({x:window.magnetTest.resource.snapshot().x,y:window.magnetTest.resource.snapshot().y})') == position, 'touch card scrolling does not drag puck')
            check(mobile.get_by_role('region').count() == 1, 'touch scrolling keeps the card open')
            touch.close()

            # The resting title stays readable at the edge.
            page.set_viewport_size({'width': 390, 'height': 720})
            page.mouse.move(0, 0)
            page.locator('#outside').focus()
            page.evaluate('window.magnetTest.resource.update({x:314,y:614,open:false})')
            page.wait_for_timeout(100)
            title_box = page.locator('.q2-magnet-rest-title').bounding_box()
            check(title_box and title_box['x'] >= 0 and title_box['x'] + title_box['width'] <= 390, 'resting title readable at right edge')
            check(title_box['y'] >= 0 and title_box['y'] + title_box['height'] <= 720, 'resting title flips above bottom edge')
            check(not errors, f'no browser errors: {errors}')
            browser.close()
    finally:
        proc.terminate()
        proc.wait(timeout=10)
print(f'Quiet Magnet puck browser: {checks} passed, 0 failed, 0 skipped, 0 errors')
