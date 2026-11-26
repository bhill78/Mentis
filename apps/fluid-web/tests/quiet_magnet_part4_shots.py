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

            # THE ACTUAL VISIBLE BOUND, not a DOM count (correction, review
            # ent-e23af56bb855: a DOM row count says nothing about how many of
            # them a reader can see without scrolling -- a scroll container
            # can hold 80 rows in its DOM while showing 6). This reads the
            # scroll container's own clipped rect and each row's, in the page
            # exactly as rendered, and counts only a row whose whole box sits
            # inside it.
            def complete_rows_visible() -> int:
                return page.evaluate("""
() => {
  const v = document.querySelector('.q2-magnet-view').getBoundingClientRect();
  return [...document.querySelectorAll('.q2-magnet-evidence-row')].filter((r) => {
    const b = r.getBoundingClientRect();
    return b.top >= v.top && b.bottom <= v.bottom;
  }).length;
}
""")

            # 1: the default Everything view -- compact, grouped by day and source.
            rows = view.locator('.q2-magnet-evidence-row')
            count = rows.count()
            at_rest = complete_rows_visible()
            print(f'rows rendered in the Everything view: {count}; complete and visible at rest: {at_rest}', flush=True)
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
            on_hover = complete_rows_visible()
            print(f'complete and visible on hover: {on_hover}', flush=True)
            page.screenshot(path=str(shots / '04-browse-hover.png'))

            assert not errors, f'page errors: {errors}'
            assert at_rest >= 20, f'expected at least 20 complete rows visible in the viewport at rest, got {at_rest}'
            assert on_hover >= 20, f'expected at least 20 complete rows visible in the viewport on hover, got {on_hover}'
            print('PART4 SHOTS: ok', flush=True)
            browser.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
