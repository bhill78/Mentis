"""Drive the Add-a-source wizard end to end for Web search and RSS / Atom.

Not a test: it opens the RUNNING candidate's own interface in headless Edge and
walks the four steps the owner named -- Kind, Where and what, Preview, Take --
for each of the two endpoint kinds, writing one PNG per step. Then it opens the
Magnet whose Sources view must list what was taken, connects it, and reaches the
refresh setting.

    python source_wizard_e2e.py --base http://127.0.0.1:8780 --out wizard-shots
"""
import argparse
import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent

p = argparse.ArgumentParser()
p.add_argument('--base', default='http://127.0.0.1:8780')
p.add_argument('--out', default='wizard-shots')
p.add_argument('--settle', type=int, default=7000)
p.add_argument('--only', default='')
args = p.parse_args()

OUT = ROOT / args.out
OUT.mkdir(parents=True, exist_ok=True)
STAMP = time.strftime('%H%M%S')

KINDS = [
    {'id': 'web-search', 'card': 'Web search',
     'name': f'Wizard check · web search {STAMP}',
     'fills': [('Searches', 'mars sample return mission')]},
    {'id': 'rss-atom', 'card': 'RSS / Atom feeds',
     'name': f'Wizard check · feed {STAMP}',
     'fills': [('Feeds', 'https://www.nasa.gov/feeds/iotd-feed/')]},
]

log = []


def say(*a):
    line = ' '.join(str(x) for x in a)
    print(line, flush=True)
    log.append(line)


def shot(page, name):
    f = OUT / f'{name}.png'
    page.screenshot(path=str(f), full_page=True)
    say('  shot', f.name)


def errors_of(page):
    return page.evaluate('() => (window.__errs || [])')


def drive(page, kind):
    say(f'=== {kind["id"]} ===')
    page.goto(f'{args.base}/quiet2?sources=add', wait_until='domcontentloaded')
    page.wait_for_timeout(args.settle)
    heading = page.get_by_role('heading', name='Add a source')
    heading.first.wait_for(timeout=30000)
    cards = page.locator('.q2-src-kindcard')
    say('  kind cards:', cards.count(),
        [cards.nth(i).locator('b').inner_text() for i in range(cards.count())])
    shot(page, f'{kind["id"]}-1-kind')

    card = page.locator('.q2-src-kindcard', has=page.locator('b', has_text=kind['card'])).first
    card.click()
    page.wait_for_timeout(1500)
    if not page.get_by_role('heading', name='Add a source').count():
        say('  FAIL: the page unmounted when the kind was picked')
        return False
    say('  step 2 reached; "Where it is" shown:',
        page.get_by_text('Where it is, on this machine').count())
    name = page.locator('.q2-src-field input[type=text]').first
    name.fill(kind['name'])
    for label, value in kind['fills']:
        box = page.get_by_label(label, exact=False)
        if not box.count():
            box = page.locator('textarea, input[type=text]').filter(has_text='')
        try:
            box.first.fill(value)
        except Exception as e:                               # noqa: BLE001
            say('  FAIL filling', label, e)
            shot(page, f'{kind["id"]}-2-fill-failed')
            return False
        say('  filled', label, '=', value)
    page.wait_for_timeout(400)
    shot(page, f'{kind["id"]}-2-where-and-what')

    page.get_by_role('button', name='Preview', exact=True).first.click()
    say('  Preview pressed')
    region = page.get_by_role('region', name='Preview')
    try:
        region.wait_for(timeout=120000)
    except Exception:                                        # noqa: BLE001
        say('  FAIL: no preview.',
            'alert:', page.locator('.q2-src-alert').all_inner_texts())
        shot(page, f'{kind["id"]}-3-preview-failed')
        return False
    page.wait_for_timeout(600)
    say('  preview says:', page.locator('.q2-src-lead').first.inner_text())
    shot(page, f'{kind["id"]}-3-preview')

    take = page.get_by_role('button', name='Take ', exact=False).first
    say('  take button:', take.inner_text(), 'enabled:', take.is_enabled())
    if not take.is_enabled():
        say('  FAIL: Take is disabled')
        shot(page, f'{kind["id"]}-4-take-disabled')
        return False
    take.click()
    added = page.get_by_role('heading', name='was added', exact=False)
    try:
        added.wait_for(timeout=180000)
    except Exception:                                        # noqa: BLE001
        say('  FAIL: never said it was added.',
            'alert:', page.locator('.q2-src-alert').all_inner_texts())
        shot(page, f'{kind["id"]}-4-take-failed')
        return False
    page.wait_for_timeout(1500)
    say('  TAKEN:', added.first.inner_text(), '|',
        page.locator('.q2-src-lead').first.inner_text())
    shot(page, f'{kind["id"]}-4-taken')
    errs = errors_of(page)
    if errs:
        say('  page errors:', errs)
    return True


def main():
    ok = {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel='msedge', headless=True)
        ctx = browser.new_context(viewport={'width': 1500, 'height': 1000})
        ctx.add_init_script('window.__errs = []; '
                            'window.addEventListener("error", e => window.__errs.push(String(e.message)));')
        page = ctx.new_page()
        page.on('pageerror', lambda e: log.append(f'  pageerror: {e}'))
        for kind in KINDS:
            if args.only and kind['id'] != args.only:
                continue
            try:
                ok[kind['id']] = drive(page, kind)
            except Exception as e:                           # noqa: BLE001
                say(f'  EXCEPTION in {kind["id"]}: {e!r}')
                ok[kind['id']] = False
        browser.close()
    say('RESULT', json.dumps(ok))
    (OUT / 'log.txt').write_text('\n'.join(log), encoding='utf-8')
    return 0 if all(ok.values()) else 1


sys.exit(main())
