"""Mounted regression for R2 of the inspection re-review (adm-6a1f95f203bf), in
headless Windows Edge.

R2: the Conversation place holds the reading position the reader left, but the
rendered view came back at the top -- and in the re-review's own control run the
clamp was written back, so the saved number was destroyed too. The frame applied
the position once, into a view whose posts had not arrived.

Driven here against the rendered card: a nonzero Conversation offset across a
tab change, across an inspection and Back, across a close and reopen, and across
content that arrives after the view does (`?slow=`). The unsaved-edit leg is the
Magnet's own isolated Composer draft, which an inspection must not discard --
R1's Perspectives panel draft is H5's durable `panelDrafts` and is verified
against the integrated panels, not here.

Only HTTP is synthetic and no Brain is opened.
"""
import json
import subprocess
import time
import urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

root = Path(__file__).resolve().parents[1]
BASE = 'http://127.0.0.1:5449/tests/quiet_magnet_reading_position.html'
WORDS = 'Unsaved words typed before the reader checked the cited evidence'
checks = []


skips = []


def check(ok, words):
    assert ok, words
    checks.append(words)


# Content that arrives above where the reader is makes the browser's own scroll
# anchoring shift the offset by a line or so, to keep the same words in front of
# them. That is not the defect: coming back at the top, or with the saved number
# destroyed, is. So a restored position is judged to within one reading line.
LINE = 48


def near(a, b):
    return abs(a - b) <= LINE


with (root / 'quiet-magnet-reading-position-browser.log').open('w', encoding='utf-8') as log:
    proc = subprocess.Popen(
        ['node', 'node_modules/vite/bin/vite.js', '--config', 'tests/quiet_magnet_reading_position_vite.mjs'],
        cwd=root, stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
    print('owned harness pid', proc.pid, flush=True)
    try:
        for _ in range(200):
            try:
                urllib.request.urlopen(BASE, timeout=1).close()
                break
            except OSError:
                time.sleep(.1)
        assert proc.poll() is None
        with sync_playwright() as p:
            browser = p.chromium.launch(channel='msedge', headless=True)
            pg = browser.new_page(viewport={'width': 1440, 'height': 1000})
            errors = []
            pg.on('pageerror', lambda e: errors.append(str(e)))
            pg.goto(BASE)
            pg.evaluate('localStorage.clear()')
            pg.goto(BASE)

            card = pg.locator('.q2-magnet-card')
            view = pg.locator('.q2-magnet-view')
            expect(card).to_be_visible()
            inspection = card.locator('.q2-magnet-inspection')
            cites = card.get_by_role('button', name='Inspect ent-readpost1115 inside Magnet', exact=True)
            cite, far = cites.first, cites.last

            def saved(key='Conversation'):
                return pg.evaluate(f'window.probe.resource.snapshot().places.{key}')

            def rendered():
                return view.evaluate('e=>e.scrollTop')

            # --- the reader's unsaved words, across an inspection -------------
            card.get_by_role('tab', name='Conversation', exact=True).click()
            expect(card.locator('.q2-mini')).to_be_visible()
            expect(cite).to_be_visible()
            # Wherever the card puts the composer -- in the Conversation view
            # here, in the frame's footer slot once H2's bar is integrated -- the
            # words are the Magnet's own isolated draft, and an inspection must
            # not discard them. H2's bar is supplied to the frame by the host, so
            # a fixture without it has no composer to type in: that is said as a
            # skip rather than measured as a loss.
            if card.locator('textarea').count() == 0:
                skips.append('the unsaved-edit leg needs a composer in the card; this fixture renders none '
                             '(supply the integrated footer bar in the harness to drive it)')
            else:
                composer = card.locator('textarea').first
                expect(composer).to_be_visible()
                composer.fill(WORDS)
                pg.wait_for_timeout(250)
                check(composer.input_value() == WORDS, 'the reader has unsaved words in the Magnet composer')
                cite.click()
                pg.wait_for_timeout(300)
                expect(inspection).to_be_visible()
                card.get_by_role('button', name='Close this record', exact=True).click()
                pg.wait_for_timeout(400)
                expect(card.locator('.q2-mini')).to_be_visible()
                check(card.locator('textarea').first.input_value() == WORDS,
                      'inspecting a citation and coming back does not discard those words')

            # --- a nonzero Conversation position, across a tab change --------
            view.evaluate('e=>e.scrollTop=400')
            pg.wait_for_timeout(300)
            left = rendered()
            check(left >= 350, f'the Conversation view really scrolls (at {left})')
            check(saved()['scroll'] == left, 'and the position the reader left is saved')
            # Away to another place and back. Posts is the collection's Posts
            # filter now, and the filter is the same place it always was.
            card.get_by_role('tab', name='Collection', exact=False).click()
            card.get_by_role('button', name='Posts', exact=True).click()
            pg.wait_for_timeout(250)
            card.get_by_role('tab', name='Conversation', exact=True).click()
            pg.wait_for_timeout(1200)
            check(near(saved()['scroll'], left),
                  f'leaving the tab and coming back keeps the saved position ({saved()["scroll"]} of {left})')
            check(near(rendered(), left),
                  f'and renders it: the reader is where they were reading, not at the top (at {rendered()})')
            left = rendered()

            # --- the same position, across an inspection and Back ------------
            # The citation is clicked where it is, without the driver's own
            # scroll-into-view moving the list first: what is being measured is
            # the position the reader left, not the one a harness scrolled to.
            cite.evaluate('el => el.click()')
            pg.wait_for_timeout(300)
            expect(inspection).to_be_visible()
            check(saved()['scroll'] == left,
                  f'entering an inspection saves the position it came from ({saved()["scroll"]} of {left})')
            card.get_by_role('button', name='Close this record', exact=True).click()
            pg.wait_for_timeout(1200)
            expect(card.locator('.q2-mini')).to_be_visible()
            check(near(saved()['scroll'], left),
                  f'Back does not overwrite the saved position with the clamp of a view still reading'
                  f' ({saved()["scroll"]} of {left})')
            check(near(rendered(), left),
                  f'and the rendered Conversation follows it back (at {rendered()})')
            left = rendered()

            # --- the same position, across a close and reopen ----------------
            card.get_by_role('button', name='Close Magnet', exact=True).click()
            pg.wait_for_timeout(250)
            pg.locator('.q2-magnet-puck').click()
            pg.wait_for_timeout(1200)
            check(near(saved()['scroll'], left),
                  f'closing and reopening the card keeps the saved position ({saved()["scroll"]} of {left})')
            check(near(rendered(), left),
                  f'and the reopened card renders it (at {rendered()})')
            left = saved()['scroll']

            # --- content that arrives after the view ------------------------
            pg.goto(BASE + '?slow=1500')
            pg.wait_for_timeout(600)
            card = pg.locator('.q2-magnet-card')
            view = pg.locator('.q2-magnet-view')
            expect(card).to_be_visible()
            check(pg.evaluate('window.probe.resource.snapshot().tab') == 'Conversation',
                  'the restored working state is reading the Conversation')
            check(saved()['scroll'] == left,
                  f'a view whose posts have not arrived does not overwrite the saved position'
                  f' ({saved()["scroll"]} of {left})')
            check(card.locator('.q2-mini-post').count() == 0, 'the posts really have not arrived yet')
            check(rendered() < left - LINE, f'and it cannot yet render it (at {rendered()})')
            pg.wait_for_timeout(2500)
            check(card.locator('.q2-mini-post').count() > 0, 'the posts then arrive')
            check(near(saved()['scroll'], left),
                  f'the saved position is still the one the reader left ({saved()["scroll"]} of {left})')
            check(near(rendered(), left),
                  f'and the content that arrived is rendered at it (at {rendered()})')

            check(not errors, f'zero page errors: {errors}')
            browser.close()
        print(json.dumps({'passed': len(checks), 'failed': 0, 'skipped': len(skips), 'errors': 0,
                          'checks': checks, 'skipped_checks': skips}, indent=1), flush=True)
    finally:
        subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'], capture_output=True)
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            print('cleanup error: owned harness pid', proc.pid, 'did not exit', flush=True)
