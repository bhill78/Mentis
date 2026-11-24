"""Mounted regression for H1 review blockers B1 and B2, in headless Windows Edge.

B1: an inspection action must not overwrite the saved list position. The review
reproduced the loss with Posts at 350 -> inspect -> Close Magnet -> reopen ->
Back, which came back at 0. This drives the same sequence, and the width toggle
and the search line, against the rendered card and the saved working state.

B2: a Conversation or Perspective citation must render the referenced evidence
inside the Magnet. These are the real MiniConversation and Perspectives panels;
the citation controls are the ones their own words produce. Only HTTP is
synthetic and no Brain is opened.

Scope: this is the B1/B2 correction's own regression check, not acceptance of
the H1 frame. B3 -- restore() changing a place snapshot without the rendered
offset following -- is a separate correction and is deliberately not asserted
here.
"""
import json
import subprocess
import time
import urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

root = Path(__file__).resolve().parents[1]
URL = 'http://127.0.0.1:5447/tests/quiet_magnet_inspect_citations.html'
checks = []


def check(ok, words):
    assert ok, words
    checks.append(words)


def saved(page, key):
    return page.evaluate(f'window.probe.resource.snapshot().places.{key}')


with (root / 'quiet-magnet-inspect-citations-browser.log').open('w', encoding='utf-8') as log:
    proc = subprocess.Popen(
        ['node', 'node_modules/vite/bin/vite.js', '--config', 'tests/quiet_magnet_inspect_citations_vite.mjs'],
        cwd=root, stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
    print('owned harness pid', proc.pid, flush=True)
    try:
        for _ in range(200):
            try:
                urllib.request.urlopen(URL, timeout=1).close()
                break
            except OSError:
                time.sleep(.1)
        assert proc.poll() is None
        with sync_playwright() as p:
            browser = p.chromium.launch(channel='msedge', headless=True)
            page = browser.new_page(viewport={'width': 1440, 'height': 1000})
            errors = []
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.goto(URL)
            card = page.locator('.q2-magnet-card')
            view = page.locator('.q2-magnet-view')
            expect(card).to_be_visible()
            inspection = card.locator('.q2-magnet-inspection')

            # --- B1: inspecting, then closing and reopening the card ---------
            card.get_by_role('tab', name='Posts', exact=True).click()
            view.evaluate('e=>e.scrollTop=350')
            page.wait_for_timeout(150)
            listed = view.evaluate('e=>e.scrollTop')
            check(listed >= 300, f'the Posts list really scrolls (at {listed})')
            view.locator('.q2-magnet-evidence-row').nth(5).click(force=True)
            expect(card.locator('.q2-magnet-post-text')).to_contain_text('captured words')
            entered = saved(page, 'Posts')
            check(entered['scroll'] == listed,
                  'entering an inspection saves the list position it came from')
            check(entered['inspectScroll'] == 0, 'and the inspection starts at its own top')

            card.get_by_role('button', name='Close Magnet', exact=True).click()
            page.locator('.q2-magnet-puck').click()
            page.wait_for_timeout(200)
            closed = saved(page, 'Posts')
            check(closed['scroll'] == listed,
                  'closing the card while inspecting does not overwrite the saved list position')
            check(closed['inspected'] == entered['inspected'], 'and the inspection is still open')
            card.get_by_role('button', name='Close evidence inspection', exact=True).click()
            page.wait_for_timeout(200)
            check(abs(view.evaluate('e=>e.scrollTop') - listed) < 2,
                  'Back after close and reopen returns the rendered list to where the reader was')
            check(saved(page, 'Posts')['scroll'] == listed, 'and the saved list position is unchanged')

            # --- B1: the other actions that remember while inspecting --------
            view.locator('.q2-magnet-evidence-row').nth(5).click(force=True)
            expect(inspection).to_be_visible()
            view.evaluate('e=>e.scrollTop=120')
            page.wait_for_timeout(150)
            card.get_by_role('button', name='Expand Magnet', exact=True).click()
            page.wait_for_timeout(150)
            check(saved(page, 'Posts')['scroll'] == listed,
                  'the width toggle while inspecting leaves the list position alone')
            search = card.get_by_role('searchbox', name='Search all Magnet information')
            search.fill('retained')
            page.wait_for_timeout(150)
            check(saved(page, 'Posts')['scroll'] == listed,
                  'typing in the search line while inspecting leaves the list position alone')
            card.get_by_role('button', name='Clear search', exact=True).click()
            page.wait_for_timeout(150)
            card.get_by_role('button', name='Magnet settings', exact=True).click()
            page.wait_for_timeout(150)
            card.get_by_role('button', name='Magnet settings', exact=True).click()
            page.wait_for_timeout(200)
            check(saved(page, 'Posts')['scroll'] == listed,
                  'the gear and its return leave the list position alone')
            card.get_by_role('button', name='Close evidence inspection', exact=True).click()
            page.wait_for_timeout(200)
            check(abs(view.evaluate('e=>e.scrollTop') - listed) < 2,
                  'Back after all of those still returns the rendered list position')
            card.get_by_role('button', name='Compact Magnet', exact=True).click()
            page.wait_for_timeout(150)

            # --- B2: a Conversation citation --------------------------------
            card.get_by_role('tab', name='Conversation', exact=True).click()
            expect(card.locator('.q2-mini')).to_be_visible()
            cite = card.get_by_role('button', name='Inspect ent-citepost1115 inside Magnet', exact=True)
            expect(cite).to_be_visible()
            check(cite.count() == 1, 'the mini Conversation draws a citation control for a collected reference')
            cite.click()
            page.wait_for_timeout(250)
            expect(inspection).to_be_visible()
            check(saved(page, 'Conversation')['inspected'] == 'ent-citepost1115',
                  'the citation writes the inspection into the Conversation place')
            check(card.locator('.q2-mini').count() == 0,
                  'and the Conversation view gives way to the evidence, as the card did before extraction')
            expect(card.locator('.q2-magnet-post-text')).to_contain_text('Retained item 6')
            check(True, 'the referenced retained post is rendered inside the Magnet')
            card.get_by_role('button', name='Close evidence inspection', exact=True).click()
            page.wait_for_timeout(250)
            expect(card.locator('.q2-mini')).to_be_visible()
            check(saved(page, 'Conversation')['inspected'] is None,
                  'Back returns to the Conversation and clears the inspection')

            # The retained batch cited in the same post is the batch evidence.
            batch = card.get_by_role('button', name='Inspect adm-citebatch111 inside Magnet', exact=True)
            batch.click()
            page.wait_for_timeout(250)
            expect(card.get_by_role('heading', name='Retained collection evidence')).to_be_visible()
            check(True, 'a cited retained batch opens the collection evidence inside the Magnet')
            card.get_by_role('button', name='Close evidence inspection', exact=True).click()
            page.wait_for_timeout(250)

            # --- B2: a Perspective citation ---------------------------------
            card.get_by_role('tab', name='Perspectives', exact=True).click()
            expect(card.get_by_role('heading', name='Perspectives', exact=True)).to_be_visible()
            card.get_by_text('Immutable revision and provenance').first.click()
            raw = card.get_by_role('button', name='Inspect raw historical revision', exact=True)
            expect(raw).to_be_visible()
            raw.click()
            page.wait_for_timeout(300)
            expect(inspection).to_be_visible()
            check(saved(page, 'Perspectives')['inspected'] == 'adm-citerevision1',
                  'an immutable Perspective revision is inspected in the Perspectives place')
            expect(inspection).to_contain_text('Retained artifact')
            check(True, 'the raw historical revision is rendered inside the Magnet, unqualified')
            check(saved(page, 'Conversation')['inspected'] is None,
                  'and it did not leak into another place')
            card.get_by_role('button', name='Close evidence inspection', exact=True).click()
            page.wait_for_timeout(250)
            expect(card.get_by_role('heading', name='Perspectives', exact=True)).to_be_visible()
            check(True, 'Back returns to Perspectives')

            check(not errors, f'zero page errors: {errors}')
            browser.close()
        print(json.dumps({'passed': len(checks), 'failed': 0, 'skipped': 0, 'errors': 0, 'checks': checks}, indent=1), flush=True)
    finally:
        subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'], capture_output=True)
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            print('cleanup error: owned harness pid', proc.pid, 'did not exit', flush=True)
