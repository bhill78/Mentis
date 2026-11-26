"""PART 4 VISUAL CHECK (not a pinned test): screenshots of the compact, grouped
collection list against a fixture shaped like the astronomy Magnet's own batch
(quiet_magnet_part4_harness.tsx) -- many rows across several days and sites --
so the design can be compared with the approved mockup (04-browse.png) without
depending on the live TEST candidate, which still serves the pre-Part-4 build.
"""
import subprocess
import time
import urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

root = Path(__file__).resolve().parents[1]
shots = root / 'part4-shots'
shots.mkdir(exist_ok=True)

with (root / 'part4-shots-vite.log').open('w', encoding='utf-8') as log:
    proc = subprocess.Popen(['node', 'node_modules/vite/bin/vite.js', '--config', 'tests/quiet_magnet_part4_vite.mjs'],
                             cwd=root, stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
    print('owned harness pid', proc.pid, flush=True)
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen('http://127.0.0.1:5444/tests/quiet_magnet_part4.html', timeout=1).close()
                break
            except OSError:
                time.sleep(.1)
        assert proc.poll() is None
        with sync_playwright() as p:
            browser = p.chromium.launch(channel='msedge', headless=True)
            page = browser.new_page(viewport={'width': 1200, 'height': 1400})
            errors = []
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.goto('http://127.0.0.1:5444/tests/quiet_magnet_part4.html')
            card = page.locator('.q2-magnet-card')
            expect(card).to_be_visible()
            view = page.locator('.q2-magnet-view')

            # 1: the default Everything view -- compact, grouped by day and source.
            rows = view.locator('.q2-magnet-evidence-row')
            count = rows.count()
            print(f'rows rendered in the Everything view: {count}', flush=True)
            page.screenshot(path=str(shots / '04-browse-everything.png'))

            # 2: the fourth pill, Images.
            card.get_by_role('button', name='Images', exact=True).click()
            page.wait_for_timeout(100)
            page.screenshot(path=str(shots / '04-browse-images.png'))

            # 3: back to Everything, hover a row to reveal its preview and address.
            card.get_by_role('button', name='Everything', exact=True).click()
            page.wait_for_timeout(100)
            first_row = view.locator('.mgd-item').first
            first_row.hover()
            page.wait_for_timeout(100)
            page.screenshot(path=str(shots / '04-browse-hover.png'))

            assert not errors, f'page errors: {errors}'
            assert count >= 20, f'expected at least 20 rows visible in the DOM, got {count}'
            print('PART4 SHOTS: ok', flush=True)
            browser.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
