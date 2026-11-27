"""Connect a taken web-search / RSS collection to a Magnet, and reach its refresh setting.

Second half of the owner's chain: the wizard has already declared and taken the
two endpoint collections (`source_wizard_e2e.py`). This opens the Magnet, goes
to Collection -> Sources, adds each collection as a source, saves, and then
reaches the refresh/cadence setting and saves that too. One PNG per step.
"""
import argparse
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent

p = argparse.ArgumentParser()
p.add_argument('--base', default='http://127.0.0.1:8780')
p.add_argument('--out', default='wizard-shots')
p.add_argument('--magnet-name', default='Space missions and astronomy')
p.add_argument('--magnet', default='mag-265878e92e5c987c')
p.add_argument('--collections', nargs='+', required=True,
               help='names of the collections taken by the wizard')
p.add_argument('--settle', type=int, default=8000)
args = p.parse_args()

OUT = ROOT / args.out
OUT.mkdir(parents=True, exist_ok=True)
log = []


def say(*a):
    line = ' '.join(str(x) for x in a)
    print(line, flush=True)
    log.append(line)


def shot(page, name):
    page.screenshot(path=str(OUT / f'{name}.png'), full_page=True)
    say('  shot', name + '.png')


def main():
    ok = True
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel='msedge', headless=True)
        ctx = browser.new_context(viewport={'width': 1500, 'height': 1000})
        page = ctx.new_page()
        page.on('pageerror', lambda e: say(f'  pageerror: {e}'))
        page.goto(f'{args.base}/quiet2', wait_until='domcontentloaded')
        page.wait_for_timeout(args.settle)

        page.locator('[data-open-magnet]:visible').first.click()
        page.wait_for_timeout(1500)
        row = page.get_by_role('option', name=args.magnet_name, exact=False).first
        row.wait_for(timeout=90000)
        row.click()
        page.wait_for_timeout(1200)
        page.get_by_role('button', name='Open in current workspace', exact=False).first.click()
        page.wait_for_timeout(6000)
        where = f'.q2-magnet-canvas [data-magnet="{args.magnet}"]'
        card = page.locator(f'{where} .q2-magnet-card')
        if card.count() == 0:
            page.locator(f'{where} .q2-magnet-puck').first.click()
            page.wait_for_timeout(2500)
        try:
            page.get_by_role('button', name='Larger panel', exact=False).first.click()
            page.wait_for_timeout(1500)
        except Exception:                                    # noqa: BLE001
            pass
        say('magnet card open; tabs:', card.locator('[role=tab]').all_inner_texts())

        card.get_by_role('tab', name='Collection', exact=False).first.click()
        page.wait_for_timeout(3500)
        shot(page, 'magnet-5-collection')

        panel = page.locator('section[aria-label="Sources"]').first
        if not panel.count():
            link = card.get_by_role('button', name='Sources', exact=False).first
            if link.count():
                say('  opening Sources from the Collection view:', link.inner_text())
                link.click()
                page.wait_for_timeout(2500)
                panel = page.locator('section[aria-label="Sources"]').first
        if not panel.count():
            say('  FAIL: no Sources panel in the Collection view')
            shot(page, 'magnet-5-no-sources-panel')
            return 1
        say('  sources panel found; rows now:',
            panel.locator('.mgd-source b').all_inner_texts())
        shot(page, 'magnet-6-sources')

        panel.get_by_role('button', name='Add source', exact=False).first.click()
        page.wait_for_timeout(600)
        pills = panel.locator('.mgd-pill')
        say('  Add source offers:', pills.all_inner_texts())
        shot(page, 'magnet-7-add-source-kinds')

        if not any('File' in t for t in pills.all_inner_texts()):
            say('  FAIL: no Files kind to attach a collection with')
            return 1
        panel.locator('.mgd-pill', has_text='Files').first.click()
        # `/api/sources` answers this build in 6-8 s, so the choices arrive late
        select = panel.locator('select').first
        for _ in range(40):
            if select.locator('option').count() > 1:
                break
            page.wait_for_timeout(500)
        say('  waited for the file collections to arrive')
        options = select.locator('option').all_inner_texts()
        say('  file collections offered:', len(options))
        for want in args.collections:
            match = [o for o in options if want in o]
            if not match:
                say(f'  FAIL: {want!r} is not offered as a file collection.'
                    f' Offered: {options}')
                shot(page, 'magnet-8-collection-missing')
                return 1
            say('  offering', match[0])
            select.select_option(label=match[0])
            page.wait_for_timeout(900)
            whole = panel.get_by_role('button', name='Attach the whole collection', exact=False).first
            say('  attach enabled:', whole.is_enabled())
            whole.click()
            page.wait_for_timeout(700)
        shot(page, 'magnet-8-attached')
        say('  rows now:', panel.locator('.mgd-source b').all_inner_texts())

        save = panel.get_by_role('button', name='Save collection configuration').first
        if not save.count() or not save.is_enabled():
            say('  FAIL: nothing to save after attaching')
            shot(page, 'magnet-9-save-missing')
            return 1
        save.click()
        page.wait_for_timeout(6000)
        say('  after save:', panel.locator('.mgd-source b').all_inner_texts())
        say('  message:', panel.locator('[role=status]').all_inner_texts(),
            panel.locator('[role=alert]').all_inner_texts())
        shot(page, 'magnet-9-saved')

        # THE REFRESH / CADENCE SETTING
        cad = panel.locator('.mgd-row', has_text='Collect').first
        say('  cadence row:', cad.inner_text().replace('\n', ' | ') if cad.count() else 'ABSENT')
        panel.get_by_role('button', name='Limits and dates', exact=False).first.click()
        page.wait_for_timeout(800)
        shot(page, 'magnet-10-refresh-setting')
        box = panel.locator('input[type=checkbox]').last
        label = panel.locator('label', has=box).first
        say('  refresh switch:', label.inner_text().replace('\n', ' ')[:120] if label.count() else 'ABSENT')
        if not box.count():
            say('  FAIL: no refresh setting reachable')
            return 1
        before = box.is_checked()
        box.click()
        page.wait_for_timeout(600)
        save = panel.get_by_role('button', name='Save collection configuration').first
        say('  refresh toggled', before, '->', box.is_checked(), '; savable:',
            save.count() and save.is_enabled())
        if not (save.count() and save.is_enabled()):
            say('  FAIL: the refresh setting is not savable')
            shot(page, 'magnet-11-refresh-not-savable')
            return 1
        save.click()
        page.wait_for_timeout(6000)
        shot(page, 'magnet-11-refresh-saved')
        say('  after refresh save:', panel.locator('[role=status]').all_inner_texts())
        # put it back the way it was
        box = panel.locator('input[type=checkbox]').last
        if box.count() and box.is_checked() != before:
            box.click()
            page.wait_for_timeout(500)
            s = panel.get_by_role('button', name='Save collection configuration').first
            if s.count() and s.is_enabled():
                s.click(); page.wait_for_timeout(5000)
                say('  restored refresh setting to', before)
        browser.close()
    (OUT / 'connect-log.txt').write_text('\n'.join(log), encoding='utf-8')
    return 0 if ok else 1


sys.exit(main())
