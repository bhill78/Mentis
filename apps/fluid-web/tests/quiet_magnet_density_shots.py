"""DENSITY CHECK (not a pinned test): measures complete, visible rows in the
Collection list against a fixture shaped like the real astronomy Magnet (75
rows, one host, split 4/71 across two days -- quiet_magnet_density_harness.tsx)
at the card's DEFAULT size (no dragged dimensions), the same way
quiet_magnet_part4_shots.py measures the part4 fixture's own shape. Finding:
ent-e27a43b60927 / ent-e20fb2f91abf -- the part4 fixture's 22-row count was
measured at a forced 900x1200 panel, not the 740 px default a reader actually
gets.
"""
import json
import subprocess
import time
import urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

root = Path(__file__).resolve().parents[1]
shots = root / 'density-shots'
shots.mkdir(exist_ok=True)

with (root / 'density-shots-vite.log').open('w', encoding='utf-8') as log:
    proc = subprocess.Popen(['node', 'node_modules/vite/bin/vite.js', '--config', 'tests/quiet_magnet_density_vite.mjs'],
                             cwd=root, stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
    print('owned harness pid', proc.pid, flush=True)
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen('http://127.0.0.1:5447/tests/quiet_magnet_density.html', timeout=1).close()
                break
            except OSError:
                time.sleep(.1)
        assert proc.poll() is None
        with sync_playwright() as p:
            browser = p.chromium.launch(channel='msedge', headless=True)
            page = browser.new_page(viewport={'width': 1600, 'height': 1400})
            errors = []
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.goto('http://127.0.0.1:5447/tests/quiet_magnet_density.html')
            card = page.locator('.q2-magnet-card')
            expect(card).to_be_visible()
            view = page.locator('.q2-magnet-view')

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

            def geometry():
                return page.evaluate("""
() => {
  const card = document.querySelector('.q2-magnet-card');
  const view = document.querySelector('.q2-magnet-view');
  const li = document.querySelector('li.mgd-item');
  return { card: card.getBoundingClientRect().height, view: view.getBoundingClientRect().height,
           rowBox: li ? li.getBoundingClientRect().height : null };
}
""")

            rows = view.locator('.q2-magnet-evidence-row')
            count = rows.count()
            at_rest = complete_rows_visible()
            geo = geometry()
            print(f'rows rendered: {count}; complete and visible at rest (DEFAULT card size): {at_rest}', flush=True)
            print(f'geometry: {json.dumps(geo)}', flush=True)
            page.screenshot(path=str(shots / 'density-at-rest.png'))

            first_row = view.locator('.mgd-item').first
            first_row.hover()
            page.wait_for_timeout(100)
            on_hover = complete_rows_visible()
            print(f'complete and visible on hover: {on_hover}', flush=True)
            page.screenshot(path=str(shots / 'density-hover.png'))

            assert not errors, f'page errors: {errors}'
            print(f'RESULT at_rest={at_rest} on_hover={on_hover} card_h={geo["card"]} view_h={geo["view"]} row_h={geo["rowBox"]}', flush=True)
            browser.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
