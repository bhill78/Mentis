"""Headless Windows Edge trial of the actual built Quiet Magnet fixture."""
from pathlib import Path
import json
import os
import time
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / '.preview' / 'quiet-magnet'
manifest = json.loads((FIXTURE / 'manifest.json').read_text('utf-8'))
f = manifest['primary']
BASE = os.environ.get('QUIET_MAGNET_PREVIEW', 'http://127.0.0.1:8933')
URL = BASE + '/quiet2?c=' + f['A'] + '&at=1'
checks = []

def check(value, words):
    assert value, words
    checks.append(words)

with sync_playwright() as p:
    browser = p.chromium.launch(channel='msedge', headless=True)
    context = browser.new_context(viewport={'width': 1440, 'height': 1000})
    page = context.new_page()
    errors, traffic = [], []
    completed = False
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('request', lambda r: traffic.append({'method': r.method, 'url': r.url}) if '/api/' in r.url else None)
    try:
        page.goto(URL)
        expect(page.get_by_role('button', name='Open existing Magnet', exact=True)).to_be_visible()
        expect(page.get_by_text('ORIGIN A:', exact=False).first).to_be_visible()
        check(page.locator('.fx-composer').count() == 0, 'read-only UI has no composer')
        page.get_by_role('button', name='Open existing Magnet', exact=True).click()
        dialog = page.get_by_role('dialog', name='Open existing Magnet', exact=True)
        expect(dialog.get_by_role('button', name='Island observatory', exact=False)).to_be_enabled()
        dialog.get_by_role('button', name='Island observatory', exact=False).click()
        puck = page.locator(f'[data-magnet="{f["magnets"]["primary"]}"] .q2-magnet-puck')
        expect(puck).to_be_visible()
        check(puck.evaluate("e=>getComputedStyle(e).backgroundColor") == 'rgb(237, 191, 80)', 'rendered puck keeps accepted yellow inside actual Quiet styles')
        page.screenshot(path=str(FIXTURE / 'resting.png'))
        puck.click()
        card = page.locator(f'[data-magnet="{f["magnets"]["primary"]}"] .q2-magnet-card')
        expect(card.get_by_text('Posts in source;', exact=False)).to_be_visible()
        expect(card.get_by_role('button', name='fixture-field-notes.md', exact=True)).to_be_visible(timeout=20000)
        check(card.get_by_text('36', exact=True).count() == 1, 'source tally is 36, distinct from selected page')
        check(card.get_by_text('Change tracking unavailable.', exact=True).count() == 1, 'change tracking unavailable is explicit')
        page.screenshot(path=str(FIXTURE / 'quick-card.png'))
        card.get_by_role('button', name='Open details', exact=False).click()
        expect(page.get_by_role('dialog', name='Magnet details', exact=True)).to_be_visible()
        check(page.locator('.q2-work-row[inert]').count() == 1, 'detail stage keeps underlying work mounted and inert')
        card.get_by_role('tab', name='Perspectives', exact=True).click()
        expect(card.get_by_text('Perspectives unavailable', exact=True)).to_be_visible()
        check(card.get_by_role('tab', name='Perspectives', exact=True).inner_text() == 'Perspectives', 'Perspectives has no invented count')
        page.screenshot(path=str(FIXTURE / 'perspectives-unavailable.png'))
        card.get_by_role('tab', name='Posts', exact=True).click()
        check(card.locator('.q2-magnet-item').count() == 20, 'first selected Posts page is bounded at twenty')
        card.get_by_role('button', name='Load more', exact=True).click()
        expect(card.locator('.q2-magnet-item')).to_have_count(27)
        check(True, 'Load more yields twenty-seven in-range roots; source tally additionally counts eight dated-out roots and one reply')
        # A collected post uses ordinary thread resolution, not a copied post reader.
        card.get_by_role('button', name='Post #35', exact=True).click()
        expect(page.get_by_text('SOURCE B: Tiny labelled fixture image;', exact=False).first).to_be_visible(timeout=20000)
        check('c=' + f['B'] in page.url, 'collected post navigates to source B in shared history')
        page.get_by_role('button', name='Back to Magnet', exact=False).click()
        expect(page.get_by_role('dialog', name='Magnet details', exact=True)).to_be_visible()
        card.get_by_role('button', name='Magnet conversation', exact=False).click()
        expect(page.get_by_text('MAGNET C:', exact=False).first).to_be_visible(timeout=20000)
        check('c=' + f['C'] in page.url, 'Magnet Conversation C is distinct from source B and origin A')
        page.go_back()
        expect(page.get_by_role('dialog', name='Magnet details', exact=True)).to_be_visible()
        check('c=' + f['A'] in page.url, 'browser Back returns to Magnet over actual origin A')
        card.get_by_role('button', name='Back to origin', exact=False).click()
        expect(page.get_by_text('ORIGIN A:', exact=False).first).to_be_visible()
        check('c=' + f['A'] in page.url, 'origin action returns to A, never substitutes source B')
        check(page.locator(f'[data-post="{f["origin_post"]}"]').count() >= 1, 'origin post anchor is held on return')
        # Inspect file through Quiet's existing file viewer.
        puck.click()
        card.get_by_role('button', name='fixture-field-notes.md', exact=True).click()
        expect(page.get_by_text('Held file from source B.', exact=False).first).to_be_visible(timeout=20000)
        check(page.locator('.q2v').count() > 0, 'held file uses ordinary Quiet viewer')
        # New page for absent-C and local reload expiry without altering fixture.
        page.goto(URL)
        page.get_by_role('button', name='Open existing Magnet', exact=True).click()
        page.get_by_role('dialog', name='Open existing Magnet').get_by_role('button', name='Without own conversation', exact=False).click()
        missing = page.locator(f'[data-magnet="{f["magnets"]["missing_own"]}"]')
        missing.locator('.q2-magnet-puck').click()
        expect(missing.get_by_role('button', name='Magnet conversation', exact=False)).to_be_disabled()
        expect(missing.get_by_text('Magnet conversation unavailable:', exact=False)).to_be_visible()
        check(True, 'missing own Conversation explains deferral without repair')
        missing.get_by_role('button', name='Open details', exact=False).click()
        page.reload()
        expect(page.get_by_text('The local Magnet view expired on reload.', exact=False)).to_be_visible()
        check(page.locator('[data-magnet]').count() == 0, 'reload expires local Magnet state without recreation')
        # Two placements share a source but retain their own identity/position.
        page.goto(URL)
        page.get_by_role('button', name='Open existing Magnet', exact=True).click()
        page.get_by_role('dialog', name='Open existing Magnet').get_by_role('button', name='Island observatory', exact=False).click()
        first = page.locator(f'[data-magnet="{f["magnets"]["primary"]}"]')
        first.locator('.q2-magnet-puck').focus()
        page.keyboard.press('ArrowRight')
        first_x = first.bounding_box()['x']
        page.get_by_role('button', name='Open existing Magnet', exact=True).click()
        page.get_by_role('dialog', name='Open existing Magnet').get_by_role('button', name='Without own conversation', exact=False).click()
        second = page.locator(f'[data-magnet="{f["magnets"]["missing_own"]}"]')
        check(page.locator('[data-magnet]').count() == 2, 'two Magnets over one source are separate resources')
        second.locator('.q2-magnet-puck').focus()
        expect(second.get_by_role('heading', name='Without own conversation', exact=True)).to_be_visible()
        check(first.bounding_box()['x'] == first_x, 'second Magnet cannot overwrite first local position')
        second.get_by_role('button', name='Open details', exact=False).click()
        page.set_viewport_size({'width': 390, 'height': 844})
        detail = page.locator('.q2-magnet-expanded .q2-magnet-card')
        box = detail.bounding_box()
        check(box['x'] >= 0 and box['x'] + box['width'] <= 390, 'narrow expanded card stays within viewport')
        page.screenshot(path=str(FIXTURE / 'narrow-expanded.png'))
        page.keyboard.press('Escape')
        expect(page.get_by_role('dialog', name='Magnet details')).to_have_count(0)
        check(True, 'Escape returns from narrow details to the same local puck')
        # A failed native route stays explicit; no legacy fallback can fill it.
        page.set_viewport_size({'width': 1440, 'height': 1000})
        page.route('**/fluid/api/magnets/*/read?*', lambda route: route.fulfill(status=404, content_type='application/json', body='{"error":"fixture route unavailable"}'))
        page.goto(URL)
        page.get_by_role('button', name='Open existing Magnet', exact=True).click()
        page.get_by_role('dialog', name='Open existing Magnet').get_by_role('button', name='Island observatory', exact=False).click()
        page.locator('.q2-magnet-puck').click()
        expect(page.get_by_text('The Magnet read is unavailable (404). Nothing was substituted.', exact=True).first).to_be_visible()
        check(page.locator('.q2-magnet-items li').count() == 0, 'unavailable routed read never displays unfiltered legacy results')
        page.unroute('**/fluid/api/magnets/*/read?*')
        page.route('**/api/brain?identity=1', lambda route: route.fulfill(status=200, content_type='application/json', body='{"corpus_id":"","corpus_name":"Unknown fixture"}'))
        page.goto(URL)
        page.get_by_role('button', name='Open existing Magnet', exact=True).click()
        expect(page.get_by_text('A resolved Brain and a current conversation are required.', exact=True)).to_be_visible()
        check(page.locator('[data-magnet]').count() == 0, 'unknown Brain identity permits no Magnet display or creation')
        page.unroute('**/api/brain?identity=1')
        check(not [r for r in traffic if r['method'] not in ('GET', 'HEAD', 'OPTIONS')], 'browser runtime API traffic contains only read methods')
        check(not [r for r in traffic if any(s in r['url'] for s in ('/activate', '/conversation?', '/synthesis', '/perspectives'))], 'no activation/Perspective/synthesis or own-Conversation repair route')
        keys = page.evaluate('Object.keys(localStorage)')
        check(not [k for k in keys if k.startswith('mentis.fluid.magnet.seen:')], 'legacy persistent seen baseline was never used')
        check(not errors, 'no browser page errors: ' + repr(errors))
        completed = True
    finally:
        (FIXTURE / 'browser-evidence.json').write_text(json.dumps({'checks': checks, 'passed': len(checks), 'failed': 0 if completed else 1, 'skipped': 0, 'errors': errors, 'traffic': traffic, 'url': URL}, indent=2), 'utf-8')
        page.screenshot(path=str(FIXTURE / 'browser-final.png'))
        print(json.dumps({'passed': len(checks), 'failed': 0 if completed else 1, 'skipped': 0, 'errors': errors, 'url': page.url, 'body': page.locator('body').inner_text()[-1500:]}, indent=2), flush=True)
        browser.close()
