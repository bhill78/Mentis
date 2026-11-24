"""Mounted regression for the H1/H4 frame scroll seam (review adm-012e854e39e3, B3).

The three checks the review recorded as failures are here as the behaviour they
asked for: typing and filtering return the rendered list to the top, and Back to
results puts it back where it was left. With them are the two things the fix must
not cost -- the reader's own scrolling is never fought, and no other per-view
state is destroyed.

Runs in Edge, the browser the owner tests in. Focused: it drives one Magnet frame
over an in-memory resource, with no backend, no device storage and no Brain.
"""
import json
import subprocess
import time
import urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

root = Path(__file__).resolve().parents[1]
url = 'http://127.0.0.1:5449/tests/quiet_magnet_frame_scroll.html'
checks = []
def check(ok, words):
    assert ok, words
    checks.append(words)

with (root / 'quiet-magnet-frame-scroll-browser.log').open('w', encoding='utf-8') as log:
    proc = subprocess.Popen(['node', 'node_modules/vite/bin/vite.js', '--config', 'tests/quiet_magnet_frame_scroll_vite.mjs'],
                            cwd=root, stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
    print('owned harness pid', proc.pid, flush=True)
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(url, timeout=1).close()
                break
            except OSError:
                time.sleep(.1)
        assert proc.poll() is None
        with sync_playwright() as p:
            browser = p.chromium.launch(channel='msedge', headless=True)
            page = browser.new_page(viewport={'width': 1440, 'height': 900})
            errors = []
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.goto(url)
            card = page.locator('.q2-magnet-card')
            view = page.locator('.q2-magnet-view')
            expect(card).to_be_visible()
            expect(card.get_by_role('heading', name='Search this Magnet')).to_be_visible()
            saved = lambda: page.evaluate('seam.snapshot().places.search.scroll')
            top = lambda: view.evaluate('e=>e.scrollTop')

            # 1. Typing. The saved list position resets, and the rendering follows it.
            view.evaluate('e=>e.scrollTop=400')
            page.wait_for_timeout(150)
            check(top() == 400 and saved() == 400, 'the reader scrolls the results list and the position is saved')
            page.locator('input[type=search]').fill('Row')
            page.wait_for_timeout(150)
            check(saved() == 0 and top() == 0, 'typing in the search line returns the rendered list to the top')

            # 2. Filtering, from a list the reader has scrolled again.
            page.locator('input[type=search]').fill('match')
            page.wait_for_timeout(150)
            view.evaluate('e=>e.scrollTop=400')
            page.wait_for_timeout(150)
            check(top() == 400, 'the filtered list scrolls')
            page.locator('select').select_option('Posts')
            page.wait_for_timeout(150)
            check(saved() == 0 and top() == 0, 'changing the content type returns the rendered list to the top')

            # 3. Opening a result and coming back to the list.
            page.locator('select').select_option('All')
            page.wait_for_timeout(150)
            view.evaluate('e=>e.scrollTop=400')
            page.wait_for_timeout(150)
            before = top()
            # Clicked where it is: letting the driver scroll the row into view
            # would move the very position under test.
            page.get_by_role('button', name='Summary match', exact=True).evaluate('e=>e.click()')
            page.wait_for_timeout(150)
            expect(page.locator('#result-title')).to_have_text('Summary match')
            check(top() == 0, 'the opened result is read from its own top')
            kept = page.evaluate('seam.snapshot().searchListScroll')
            view.evaluate('e=>e.scrollTop=160')
            page.wait_for_timeout(150)
            check(top() == 160, 'the opened result scrolls on its own')
            page.get_by_role('button', name='Back to results', exact=False).click()
            page.wait_for_timeout(150)
            check(kept == before and saved() == before, 'Back to results restores the saved list position')
            check(abs(top() - before) <= 2, 'Back to results restores the rendered list position')

            # 4. The reader's own scrolling is never fought, including several
            #    events inside one frame, where the saved number trails the DOM.
            view.evaluate('e=>{e.scrollTop=100;e.scrollTop=220;e.scrollTop=330}')
            page.wait_for_timeout(250)
            check(top() == 330, 'rapid scrolling is left where the reader put it, not pulled back')
            check(saved() == 330, 'and the saved position catches up to it')

            # 5. Nothing else per-view is destroyed by following the saved number.
            card.get_by_role('button', name='Return to Summary', exact=False).evaluate('e=>e.click()')
            page.wait_for_timeout(150)
            check(card.get_by_role('tab', name='Summary', exact=True).get_attribute('aria-selected') == 'true',
                  'returning from search comes back to the tab it covered')
            check(page.locator('input[type=search]').input_value() == 'match', 'the query stays in the search line')
            view.evaluate('e=>e.scrollTop=300')
            page.wait_for_timeout(150)
            card.get_by_role('tab', name='Posts', exact=True).click()
            page.wait_for_timeout(150)
            check(top() == 0, 'a view the reader has not scrolled starts at the top')
            view.evaluate('e=>e.scrollTop=180')
            page.wait_for_timeout(150)
            card.get_by_role('tab', name='Summary', exact=True).click()
            page.wait_for_timeout(150)
            check(top() == 300, 'the Summary reading position survived the search and the other tab')
            card.get_by_role('tab', name='Posts', exact=True).click()
            page.wait_for_timeout(150)
            check(top() == 180, 'and Posts keeps its own')
            state = page.evaluate('seam.snapshot()')
            check(state['places']['search']['scroll'] == 330 and state['query'] == 'match' and state['searchType'] == 'All',
                  'the search place, query and filter are left exactly as they were')

            check(not errors, 'zero page errors')
            browser.close()
        print(json.dumps({'passed': len(checks), 'failed': 0, 'skipped': 0, 'errors': 0, 'checks': checks}), flush=True)
    finally:
        subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'], capture_output=True)
        proc.wait(timeout=15)
