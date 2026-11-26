"""Photograph the owner's real Magnet, before and after the link-and-formatting
refinement (owner ent-0b4f3f69b836).

Not a test. It opens the owner's own Magnet -- "Space missions and astronomy --
what launched, what was found", 71 items collected from a web search -- on a
running server in headless Windows Edge, and writes one PNG per surface the
owner reads: the Summary with its evolving answer and its excerpts, the
Collection's rows, and a Perspectives answer. Run it twice against the same
Brain to put the two side by side:

    python magnet_refinement_shots.py --base http://127.0.0.1:8780 --out before-links
    python magnet_refinement_shots.py --base http://127.0.0.1:5173 --out after-links

The second base is this checkout's own dev UI with MENTIS_API pointed at the
first, so both shots are of the SAME collected rows and the only difference is
the interface.
"""
import argparse
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
MAGNET = 'mag-265878e92e5c987c'
MAGNET_NAME = 'Space missions and astronomy'

p = argparse.ArgumentParser()
p.add_argument('--base', default='http://127.0.0.1:8780')
p.add_argument('--out', default='refinement-shots')
p.add_argument('--magnet', default=MAGNET)
p.add_argument('--name', default=MAGNET_NAME)
p.add_argument('--settle', type=int, default=9000)
args = p.parse_args()

OUT = ROOT / args.out
OUT.mkdir(parents=True, exist_ok=True)
URL = f'{args.base}/quiet2'
notes, errors = [], []


def main():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel='msedge', headless=True)
        context = browser.new_context(viewport={'width': 1500, 'height': 1000},
                                      device_scale_factor=1)
        page = context.new_page()
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.goto(URL, wait_until='domcontentloaded')
        page.wait_for_timeout(args.settle)

        page.locator('[data-open-magnet]:visible').first.click()
        page.wait_for_timeout(1500)
        row = page.get_by_role('option', name=args.name, exact=False).first
        row.wait_for(timeout=90000)
        row.click()
        page.wait_for_timeout(1200)
        page.get_by_role('button', name='Open in current workspace', exact=False).first.click()
        page.wait_for_timeout(4000)

        where = f'.q2-magnet-canvas [data-magnet="{args.magnet}"]'
        card = page.locator(f'{where} .q2-magnet-card')
        magnet = page.locator(where)
        if card.count() == 0:
            page.locator(f'{where} .q2-magnet-puck').click()
            page.wait_for_timeout(1500)

        # Room to read: the owner's own panel is wide, and a narrow card would
        # photograph a layout nobody uses.
        try:
            page.get_by_role('button', name='Larger panel', exact=False).first.click()
            page.wait_for_timeout(1500)
        except Exception as exc:                            # noqa: BLE001
            notes.append(f'larger panel: NOT REACHED ({exc})')

        def shot(name, note=''):
            page.wait_for_timeout(900)
            target = card if card.count() else magnet
            try:
                target.screenshot(path=str(OUT / f'{name}.png'))
            except Exception as exc:                        # noqa: BLE001
                page.screenshot(path=str(OUT / f'{name}.png'))
                notes.append(f'{name}: full page ({exc})')
            notes.append(f'{name} {note}'.strip())

        def tab(label):
            try:
                card.get_by_role('tab', name=label, exact=False).first.click()
                page.wait_for_timeout(1500)
                return True
            except Exception as exc:                        # noqa: BLE001
                notes.append(f'tab {label}: NOT REACHED ({exc})')
                return False

        if tab('Summary'):
            shot('summary', 'the evolving answer and the records in their own words')
            # The answer can take a moment to be written against this batch.
            page.wait_for_timeout(4000)
            shot('summary-settled', 'the same surface once the answer has been read')
        if tab('Collection'):
            shot('collection', 'the collected rows: what each row leads with')
            try:
                card.locator('.q2-magnet-evidence-row').first.click()
                page.wait_for_timeout(1500)
                shot('collection-inspected', 'one row opened in the card')
            except Exception as exc:                        # noqa: BLE001
                notes.append(f'inspect a row: NOT REACHED ({exc})')
        if tab('Perspectives'):
            shot('perspectives', 'the question surface and any answer standing')

        page.screenshot(path=str(OUT / 'workspace.png'), full_page=False)
        (OUT / 'shots.json').write_text(json.dumps(
            {'base': args.base, 'url': URL, 'magnet': args.magnet,
             'notes': notes, 'page_errors': errors}, indent=2), 'utf-8')
        print(json.dumps({'out': str(OUT), 'shots': sorted(f.name for f in OUT.glob('*.png')),
                          'notes': notes, 'page_errors': errors}, indent=2), flush=True)
        browser.close()
    return 0


sys.exit(main())
