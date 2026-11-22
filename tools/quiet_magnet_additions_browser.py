"""Focused Windows Edge checks on the exact built, gated disposable candidate."""
from pathlib import Path
import json
import os
import time
import urllib.request
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / os.environ.get('QUIET_MAGNET_FIXTURE', '.preview/quiet-magnet-functional')
manifest = json.loads((FIXTURE / 'manifest.json').read_text('utf-8'))
f = manifest['primary']
BASE = os.environ.get('QUIET_MAGNET_PREVIEW', 'http://127.0.0.1:8943')
URL = BASE + '/quiet2?c=' + f['A'] + '&at=1'
checks, traffic, errors = [], [], []


def read(path):
    with urllib.request.urlopen(urllib.request.Request(BASE + path, headers={'X-Mentis-Client': '1'}), timeout=10) as response:
        return json.load(response)


def count(cid):
    return read('/api/conversations/' + cid + '?batch=30')['turns_total']


def check(value, words):
    assert value, words
    checks.append(words)


before = {name: count(f[name]) for name in ('A', 'B', 'C')}
with sync_playwright() as p:
    browser = p.chromium.launch(channel='msedge', headless=True)
    context = browser.new_context(viewport={'width': 1440, 'height': 1000})
    page = context.new_page()
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('request', lambda r: traffic.append({'method': r.method, 'url': r.url}) if '/api/' in r.url else None)
    try:
        page.goto(URL)
        expect(page.get_by_text('ORIGIN A:', exact=False).first).to_be_visible()
        rail = page.get_by_role('button', name='Magnet Management', exact=True)
        expect(rail).to_be_visible()
        check(rail.bounding_box()['y'] > page.locator('.q2-rail-places').bounding_box()['y'] + page.locator('.q2-rail-places').bounding_box()['height'], 'Management is below the Brain group and separator')
        rail.click()
        management = page.get_by_role('dialog', name='Magnet Management')
        expect(management.get_by_text('The main Conversation is read-only.', exact=False)).to_be_visible()
        management.get_by_role('option', name='Island observatory', exact=False).click()
        management.get_by_role('button', name='Open selected Magnet', exact=True).click()
        magnet = page.locator(f'[data-magnet="{f["magnets"]["primary"]}"]')
        puck = magnet.locator('.q2-magnet-puck')
        expect(puck).to_be_visible()
        check(puck.evaluate('e=>getComputedStyle(e).backgroundColor') == 'rgb(237, 191, 80)', 'puck preserves accepted yellow')
        check(round(puck.bounding_box()['width']) == 64, 'resting puck remains compact')
        puck.focus()
        expect(magnet.locator('.q2-magnet-indicators')).to_be_visible()
        check(magnet.locator('.q2-magnet-indicator').count() == 4, 'keyboard focus exposes four actionable indicators')
        check(magnet.locator('.q2-magnet-indicator-new b').count() == 0 and magnet.locator('.q2-magnet-indicator-perspectives b').count() == 0, 'unsupported new-item and Perspective counts have no fabricated badge')
        magnet.locator('.q2-magnet-indicator-perspectives').click()
        card = magnet.locator('.q2-magnet-card')
        expect(card.get_by_text('Perspectives unavailable', exact=True)).to_be_visible()
        check(page.locator('.q2-work-row[inert]').count() == 0, 'expanded card leaves the main work row operable')
        expect(page.get_by_text('ORIGIN A:', exact=False).first).to_be_visible()
        check('c=' + f['A'] in page.url, 'opening card leaves the main Conversation and URL at A')
        magnet.locator('.q2-magnet-indicator-files').click()
        expect(card.get_by_role('tab', name='Files', exact=True)).to_have_attribute('aria-selected', 'true')
        expect(card.get_by_text('Files loaded', exact=False)).to_be_visible()
        magnet.locator('.q2-magnet-indicator-new').click()
        expect(card.get_by_role('tab', name='Overview', exact=True)).to_have_attribute('aria-selected', 'true')
        card.get_by_role('tab', name='Conversation', exact=True).click()
        mini = card.locator('.q2-mini')
        expect(mini.get_by_text('FIXTURE INQUIRY:', exact=False)).to_be_visible()
        check(mini.locator('.q2-mini-work-state').count() > 0, 'mini reads actual nonexecuting Work status')
        inquiry = mini.locator('.q2-mini-post').filter(has_text='FIXTURE INQUIRY:').first
        inquiry.get_by_role('button', name='Show 1 reply', exact=True).click()
        expect(mini.get_by_text('FIXTURE HISTORICAL REPLY:', exact=False)).to_be_visible()
        check(True, 'mini reads the existing C reply thread')
        mini.get_by_role('button', name='Earlier posts', exact=False).click()
        expect(mini.get_by_text('FIXTURE HISTORY 1:', exact=False)).to_be_visible()
        check(True, 'earlier history is paged from the same existing C')
        box = mini.get_by_label('Write in this Conversation', exact=True)
        box.fill('UNSENT fixture draft retained across collapse')
        card.get_by_role('button', name='Back to collection', exact=True).click()
        card.get_by_role('button', name='Open details', exact=False).click()
        card.get_by_role('tab', name='Conversation', exact=True).click()
        expect(box).to_have_value('UNSENT fixture draft retained across collapse')
        check(True, 'mini draft survives collapse and expansion')
        inquiry = mini.locator('.q2-mini-post').filter(has_text='FIXTURE INQUIRY:').first
        inquiry.get_by_role('button', name='Reply', exact=True).click()
        reply_text = 'BROWSER FIXTURE REPLY ' + str(time.time_ns())
        box.fill(reply_text)
        mini.get_by_role('button', name='Send reply', exact=True).click()
        expect(mini.locator('.q2-mini-sent')).to_be_visible(timeout=15000)
        check(count(f['C']) == before['C'] + 1, 'explicit mini reply is recorded once in existing C')
        mini.get_by_role('button', name='Reply to the Conversation instead', exact=True).click() if mini.get_by_role('button', name='Reply to the Conversation instead', exact=True).count() else None
        message = 'BROWSER FIXTURE MESSAGE ' + str(time.time_ns())
        box.fill(message)
        mini.get_by_role('button', name='Send', exact=True).click()
        expect(box).to_have_value('', timeout=15000)
        check(count(f['C']) == before['C'] + 2, 'explicit mini message is recorded once in existing C')
        mini.get_by_role('button', name='Open full Conversation', exact=False).click()
        expect(page.get_by_text(message, exact=False).first).to_be_visible(timeout=15000)
        check('c=' + f['C'] in page.url, 'full Conversation opens the existing C and its newly recorded history')
        check(count(f['A']) == before['A'] and count(f['B']) == before['B'], 'mini sends do not write into main A or source B')
        page.goto(URL)
        rail.click()
        management.get_by_role('button', name='New Magnet', exact=True).click()
        new_name = 'Browser fixture view ' + str(time.time_ns())
        management.get_by_label('Name', exact=True).fill(new_name)
        management.get_by_label('Source Conversation', exact=True).select_option(f['B'])
        management.get_by_role('button', name='Create Magnet', exact=True).click()
        created_puck = page.get_by_role('button', name=new_name + ' Magnet', exact=True)
        expect(created_puck).to_be_visible(timeout=15000)
        arrangement = read('/fluid/api/arrangements/' + f['A'])
        ids = [mid for mid, config in arrangement['layout']['magnets'].items() if mid not in f['magnets'].values() and config['sources'][0].get('conversation') == f['B']]
        check(len(ids) == 1, 'creation persists exactly one supported Magnet definition and placement')
        created = page.locator(f'[data-magnet="{ids[0]}"]')
        created_puck.click()
        created.get_by_role('button', name='Open details', exact=False).click()
        created.get_by_role('tab', name='Conversation', exact=True).click()
        expect(created.get_by_role('heading', name='Magnet conversation unavailable', exact=True)).to_be_visible()
        check(True, 'new Magnet has no invented own Conversation or repair')
        page.set_viewport_size({'width': 600, 'height': 900})
        rect = created.locator('.q2-magnet-card').bounding_box()
        check(rect['x'] >= 0 and rect['x'] + rect['width'] <= 601, 'expanded card stays within narrow viewport')
        check(page.locator('.q2-work-row[inert]').count() == 0, 'narrow expansion also keeps main Conversation operable')
        check(not errors, 'no browser runtime errors')
        writes = [r for r in traffic if r['method'] not in ('GET', 'HEAD', 'OPTIONS')]
        check(len(writes) == 3 and all(r['url'].endswith('/fluid/api/posts') or r['url'].endswith('/fluid/api/arrangements/' + f['A'] + '/magnets') for r in writes), 'browser sends only two C posts and one A Magnet creation')
    finally:
        (FIXTURE / 'browser-additions.json').write_text(json.dumps({'checked_at': time.time(), 'url': URL, 'checks': checks, 'passed': len(checks), 'failed': 0 if not errors else len(errors), 'errors': errors, 'traffic': traffic}, indent=2), 'utf-8')
        browser.close()
print(json.dumps({'passed': len(checks), 'failed': 0, 'skipped': 0, 'errors': 0, 'url': URL}, indent=2))
