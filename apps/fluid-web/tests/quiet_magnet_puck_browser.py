"""Bounded presentation interaction check. No Brain, API target or persistent server."""
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
            puck = page.get_by_role('button', name='Colony Island fixture Magnet', exact=True)
            expect(puck).to_be_visible()
            check(page.get_by_role('region').count() == 0, 'rest has no card')
            puck.hover()
            expect(page.get_by_role('region')).to_be_visible()
            check(page.get_by_text('Posts in source;').count() == 1, 'source-wide tally qualified')
            page.mouse.move(1100, 20)
            expect(page.get_by_role('region')).to_have_count(0)
            checks += 1
            puck.focus()
            expect(page.get_by_role('region')).to_be_visible()
            checks += 1
            page.keyboard.press('Escape')
            expect(page.get_by_role('region')).to_have_count(0)
            expect(puck).to_be_focused()
            checks += 2
            page.keyboard.press('Enter')
            expect(page.get_by_role('region')).to_be_visible()
            page.mouse.move(1100, 20)
            check(page.get_by_role('region').count() == 1, 'Enter pins same quick card')
            page.get_by_role('button', name='Open details').click()
            expect(page.get_by_role('tab', name='Perspectives', exact=True)).to_be_visible()
            checks += 1
            page.get_by_role('tab', name='Perspectives', exact=True).click()
            check(page.get_by_text('Perspectives unavailable', exact=True).count() == 1, 'Perspectives unavailable explanation')
            check(page.locator('textarea,[contenteditable=true]').count() == 0, 'read-only rendering')
            page.get_by_role('tab', name='Files', exact=True).click()
            page.get_by_role('button', name='fixture-notes.md', exact=True).click()
            check(page.locator('#event').inner_text() == 'file', 'file viewer action emitted')
            page.get_by_role('button', name='Open source post', exact=False).click()
            check(page.locator('#event').inner_text() == 'post', 'file source post action emitted')
            page.evaluate("window.magnetTest.resource.update({status:'partial',reason:'Objects still being read'})")
            page.get_by_role('button', name='Retry this page', exact=True).click()
            check(page.evaluate('window.magnetTest.calls.at(-1)') == 'read', 'partial page retry retains current page')
            page.get_by_role('button', name='Load more', exact=True).click()
            check(page.evaluate('window.magnetTest.calls.at(-1)') == 'more', 'load more demand separate from retry')
            page.get_by_role('button', name='Back to collection', exact=True).click()
            page.keyboard.press('Escape')
            expect(page.get_by_role('region')).to_have_count(0)
            expect(puck).to_be_focused()
            checks += 1
            before = page.evaluate('window.magnetTest.resource.snapshot().x')
            page.keyboard.press('ArrowRight')
            check(page.evaluate('window.magnetTest.resource.snapshot().x') == before + 12, 'keyboard move')
            box = puck.bounding_box()
            page.mouse.move(box['x'] + 30, box['y'] + 30)
            page.mouse.down()
            page.mouse.move(box['x'] + 180, box['y'] + 110, steps=5)
            page.mouse.up()
            check(page.evaluate('window.magnetTest.resource.snapshot().pinned') is False, 'drag suppresses click')
            check(page.evaluate('window.magnetTest.resource.snapshot().x') > before + 12, 'drag changes presentation position')
            page.set_viewport_size({'width': 390, 'height': 720})
            page.evaluate('window.magnetTest.resource.update({x:310,y:600,pinned:true})')
            page.wait_for_timeout(100)
            box = page.get_by_role('region').bounding_box()
            check(box['x'] >= 0 and box['x'] + box['width'] <= 390, 'narrow card fits canvas')
            check(box['y'] >= 0 and box['y'] + box['height'] <= 720, 'narrow card scrolls inside height')
            page.get_by_role('button', name='Magnet conversation', exact=False).click()
            check(page.locator('#event').inner_text() == 'own', 'own conversation action emitted')
            page.get_by_role('button', name='Source conversation', exact=False).click()
            check(page.locator('#event').inner_text() == 'source', 'source action emitted separately')
            page.get_by_role('button', name='Back to origin', exact=False).click()
            check(page.locator('#event').inner_text() == 'origin', 'origin action emitted separately')
            page.evaluate('window.magnetTest.resource.update({pinned:false})')
            page.locator('#outside').focus()
            puck.focus()
            page.keyboard.press('Escape')
            expect(puck).to_be_focused()
            box = puck.bounding_box()
            page.mouse.move(box['x'] + 30, box['y'] + 30)
            page.mouse.down()
            page.mouse.move(box['x'] - 30, box['y'] - 30, steps=3)
            puck.dispatch_event('pointercancel', {'pointerId': 1, 'pointerType': 'mouse', 'bubbles': True})
            page.mouse.up()
            check(page.evaluate('window.magnetTest.resource.snapshot().pinned') is False, 'cancelled drag never pins')
            page.locator('#outside').focus()
            touch = browser.new_context(viewport={'width':390,'height':720}, is_mobile=True, has_touch=True)
            mobile = touch.new_page()
            mobile.goto(URL)
            mobile.get_by_role('button', name='Colony Island fixture Magnet', exact=True).tap()
            expect(mobile.get_by_role('region')).to_be_visible()
            check(mobile.evaluate('window.magnetTest.resource.snapshot().pinned') is True, 'single touch pins quick card')
            position = mobile.evaluate('({x:window.magnetTest.resource.snapshot().x,y:window.magnetTest.resource.snapshot().y})')
            session = touch.new_cdp_session(mobile)
            session.send('Input.dispatchTouchEvent', {'type':'touchStart','touchPoints':[{'x':210,'y':450}]})
            session.send('Input.dispatchTouchEvent', {'type':'touchMove','touchPoints':[{'x':210,'y':270}]})
            session.send('Input.dispatchTouchEvent', {'type':'touchEnd','touchPoints':[]})
            check(mobile.evaluate('({x:window.magnetTest.resource.snapshot().x,y:window.magnetTest.resource.snapshot().y})') == position, 'touch card scrolling does not drag puck')
            check(mobile.get_by_role('region').count() == 1, 'touch scrolling keeps card pinned')
            touch.close()
            page.mouse.move(0, 0)
            page.locator('#outside').focus()
            page.evaluate('window.magnetTest.resource.update({x:314,y:614,pinned:false})')
            page.wait_for_timeout(80)
            title_box = page.locator('.q2-magnet-rest-title').bounding_box()
            check(title_box and title_box['x'] >= 0 and title_box['x'] + title_box['width'] <= 390, 'resting title readable at right edge')
            check(title_box['y'] >= 0 and title_box['y'] + title_box['height'] <= 720, 'resting title flips above bottom edge')
            check(not errors, f'no browser errors: {errors}')
            browser.close()
    finally:
        proc.terminate()
        proc.wait(timeout=10)
print(f'Quiet Magnet puck browser: {checks} passed, 0 failed, 0 skipped, 0 errors')
