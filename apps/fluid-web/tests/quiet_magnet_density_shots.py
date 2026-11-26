"""DENSITY CHECK (not a pinned test): measures complete, visible rows in the
Collection list against a fixture shaped like the real astronomy Magnet (75
rows, one host, split 4/71 across two days, a representative quarter of them
carrying a captured excerpt -- quiet_magnet_density_harness.tsx) at the card's
DEFAULT size (no dragged dimensions), the same way quiet_magnet_part4_shots.py
measures the part4 fixture's own shape. Finding: ent-e27a43b60927 /
ent-e20fb2f91abf -- the part4 fixture's 22-row count was measured at a forced
900x1200 panel, not the 740 px default a reader actually gets.

CORRECTION (review ent-f94e543d798e): the prior fixture had no excerpt-bearing
row and no application base styles, so its 20-row hover claim was never
actually measured against either. This adds: hovering/focusing an
excerpt-bearing row (not just a bare headline+link row), a scrolled
measurement that accounts for the sticky type-pills occluding rows under
them (not just the view's own top edge), a keyboard-only reveal check, and a
simulated coarse-pointer tap -- against the real `theme.css`/`app.css`
tokens the harness now loads, not an unstyled DOM.
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

COMPLETE_ROWS_IN = """
(top) => {
  const v = document.querySelector('.q2-magnet-view').getBoundingClientRect();
  const lo = top == null ? v.top : top;
  return [...document.querySelectorAll('.q2-magnet-evidence-row')].filter((r) => {
    const b = r.getBoundingClientRect();
    return b.top >= lo && b.bottom <= v.bottom;
  }).length;
}
"""

GEOMETRY = """
() => {
  const card = document.querySelector('.q2-magnet-card');
  const view = document.querySelector('.q2-magnet-view');
  const li = document.querySelector('li.mgd-item');
  const pills = document.querySelector('.q2-magnet-type-pills');
  return { card: card.getBoundingClientRect().height, view: view.getBoundingClientRect().height,
           rowBox: li ? li.getBoundingClientRect().height : null,
           pillsBottom: pills ? pills.getBoundingClientRect().bottom : null }
}
"""

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
            page = browser.new_page(viewport={'width': 1600, 'height': 1400}, has_touch=True)
            errors = []
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.goto('http://127.0.0.1:5447/tests/quiet_magnet_density.html')
            card = page.locator('.q2-magnet-card')
            expect(card).to_be_visible()
            view = page.locator('.q2-magnet-view')

            def complete_rows_visible(top=None) -> int:
                return page.evaluate(COMPLETE_ROWS_IN, top)

            def geometry():
                return page.evaluate(GEOMETRY)

            rows = view.locator('.q2-magnet-evidence-row')
            count = rows.count()
            at_rest = complete_rows_visible()
            geo = geometry()
            print(f'rows rendered: {count}; complete and visible at rest (DEFAULT card size): {at_rest}', flush=True)
            print(f'geometry: {json.dumps(geo)}', flush=True)
            page.screenshot(path=str(shots / 'density-at-rest.png'))

            # Bounding boxes read up front, before anything is hovered: the
            # excerpt row's floating preview visually overlaps the row below
            # it once open (that is the point -- it covers, it never moves),
            # and `.hover()`'s own actionability check treats an element a
            # later floating block covers as "not yet actionable" and tries
            # to scroll it into view again -- a Playwright side effect of the
            # fix working, not a product behaviour. `page.mouse.move` to a
            # box already read avoids it.
            first_box = view.locator('.mgd-item').first.bounding_box()
            second_box = view.locator('.mgd-item').nth(1).bounding_box()

            def move_to(box):
                page.mouse.move(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)

            # THE FIRST ROW IN THE FIXTURE CARRIES AN EXCERPT (n=1, n % 4 == 1):
            # the case the prior fixture never exercised, and the one the review's
            # own diagnostic found dropped the count from 20 to 19.
            move_to(first_box)
            page.wait_for_timeout(100)
            on_hover_excerpt = complete_rows_visible()
            preview_box = page.evaluate("""
() => {
  const p = document.querySelector('.mgd-item .q2-magnet-row-more');
  if (!p) return null;
  const r = p.getBoundingClientRect();
  return { display: getComputedStyle(p).display, position: getComputedStyle(p).position, height: r.height };
}
""")
            print(f'first row (excerpt-bearing) more-block: {json.dumps(preview_box)}', flush=True)
            print(f'complete and visible on hover (excerpt row): {on_hover_excerpt}', flush=True)
            page.screenshot(path=str(shots / 'density-hover-excerpt.png'))
            page.mouse.move(0, 0)
            page.wait_for_timeout(100)

            # A HEADLINE-ONLY ROW, FOR COMPARISON: the second row (n=2) has no
            # excerpt, the shape most of the real batch actually has.
            move_to(second_box)
            page.wait_for_timeout(100)
            on_hover_plain = complete_rows_visible()
            print(f'complete and visible on hover (headline-only row): {on_hover_plain}', flush=True)
            page.screenshot(path=str(shots / 'density-hover-plain.png'))
            page.mouse.move(0, 0)
            page.wait_for_timeout(100)
            scroll_after_hovers = page.evaluate("() => document.querySelector('.q2-magnet-view').scrollTop")
            print(f'scrollTop after both hovers (should be 0 -- neither hover should scroll anything): {scroll_after_hovers}', flush=True)

            # KEYBOARD: Tab from the first row's button reaches its revealed
            # link next, and the reveal is the same floating block hover uses,
            # so the complete-row count does not move either.
            first_button = view.locator('.q2-magnet-evidence-row').first
            first_button.focus()
            page.wait_for_timeout(100)
            on_focus = complete_rows_visible()
            focused_is_row = page.evaluate("() => document.activeElement === document.querySelector('.q2-magnet-evidence-row')")
            page.keyboard.press('Tab')
            page.wait_for_timeout(100)
            tab_target = page.evaluate("""
() => {
  const a = document.activeElement;
  return a ? { tag: a.tagName, cls: a.className, text: (a.textContent || '').slice(0, 40) } : null;
}
""")
            print(f'focus landed on the row first: {focused_is_row}; complete and visible on focus: {on_focus}', flush=True)
            print(f'Tab from the row reaches: {json.dumps(tab_target)}', flush=True)
            page.screenshot(path=str(shots / 'density-focus.png'))

            # SCROLLED, UNDER THE STICKY PILLS: the sticky filter row stays on
            # screen while the list scrolls under it, so a row's own top can be
            # inside the view's bounds while the sticky pills still cover it.
            # Scroll the list, then count complete rows below the pills' own
            # bottom edge, not just the view's.
            page.evaluate("""
() => { document.querySelector('.q2-magnet-view').scrollTop = 900; }
""")
            page.wait_for_timeout(100)
            geo_scrolled = geometry()
            under_pills = complete_rows_visible(geo_scrolled['pillsBottom'])
            naive = complete_rows_visible()
            print(f'scrolled: complete rows below the view top (naive): {naive}; below the sticky pills\' own bottom: {under_pills}', flush=True)
            page.screenshot(path=str(shots / 'density-scrolled.png'))
            page.evaluate("() => { document.querySelector('.q2-magnet-view').scrollTop = 0; }")

            # TOUCH: a simulated tap on the excerpt row opens inspection, same
            # as the plain row, rather than requiring the hover reveal first.
            box = first_button.bounding_box()
            page.touchscreen.tap(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
            page.wait_for_timeout(300)
            inspected = page.evaluate("() => !!document.querySelector('.q2-magnet-evidence-row[aria-expanded=\"true\"]')")
            print(f'simulated tap on excerpt row opens inspection: {inspected}', flush=True)
            page.screenshot(path=str(shots / 'density-touch.png'))

            assert not errors, f'page errors: {errors}'
            print(f'RESULT at_rest={at_rest} on_hover_excerpt={on_hover_excerpt} on_hover_plain={on_hover_plain} '
                  f'on_focus={on_focus} under_pills_scrolled={under_pills} card_h={geo["card"]} view_h={geo["view"]} '
                  f'row_h={geo["rowBox"]}', flush=True)
            browser.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
