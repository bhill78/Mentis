"""PREVIEW INTERACTION CHECK (not a pinned test): the three nonblocking
findings of review ent-8e817d3b3dff against commit 7c38fd90 -- N1 (ordinary
pointer movement toward a row's own preview link can hand hover, and the
click, to a different row), N2's bottom clip (the last complete row's
preview had nowhere below it and was cut off, with no upward placement
attempted) and N2's sticky overlap (an open preview could paint over the
lower part of the sticky type-pills). Drives the same real-shape fixture
`quiet_magnet_density_harness.tsx`/`quiet_magnet_density_vite.mjs` already
serve for the density check, at the same default card size, so a count or
geometry change here is directly comparable to that check's own numbers.

This does not re-measure the 20-unobscured-row density finding (B1): the
correction request this answers treats that as the resting-list goal only,
not a reason to compress text or conceal an open preview.
"""
import json
import subprocess
import time
import urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

root = Path(__file__).resolve().parents[1]
shots = root / 'preview-interaction-shots'
shots.mkdir(exist_ok=True)

COMPLETE_ROWS_IN = """
(top) => {
  const v = document.querySelector('.q2-magnet-view').getBoundingClientRect();
  const lo = top == null ? v.top : top;
  return [...document.querySelectorAll('.q2-magnet-evidence-row')].filter((r) => {
    const b = r.getBoundingClientRect();
    return b.top >= lo && b.bottom <= v.bottom;
  });
}
"""

ROW_AT_POINT = """
(pt) => {
  const el = document.elementFromPoint(pt.x, pt.y);
  const item = el && el.closest('.mgd-item');
  const items = [...document.querySelectorAll('.mgd-item')];
  return item ? items.indexOf(item) : -1;
}
"""

with (root / 'preview-interaction-vite.log').open('w', encoding='utf-8') as log:
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
            view = page.locator('.q2-magnet-view')
            expect(view).to_be_visible()
            items = view.locator('.mgd-item')

            # ---------------------------------------------------------------
            # N1: POINTER TRAVEL FROM A ROW TO ITS OWN LINK NEVER HANDS OFF.
            # The first row (n=1) carries an excerpt, so it is the case the
            # review's own cascade used.
            # ---------------------------------------------------------------
            first_box = items.nth(0).bounding_box()
            start = {'x': first_box['x'] + first_box['width'] / 2, 'y': first_box['y'] + first_box['height'] / 2}
            page.mouse.move(start['x'], start['y'])
            page.wait_for_timeout(100)
            link_box = page.locator('.mgd-item').nth(0).locator('.q2-magnet-row-link').bounding_box()
            assert link_box is not None, 'first row did not reveal its own preview link on hover'
            end = {'x': link_box['x'] + link_box['width'] / 2, 'y': link_box['y'] + link_box['height'] / 2}

            STEPS = 80
            rows_seen = set()
            for i in range(1, STEPS + 1):
                x = start['x'] + (end['x'] - start['x']) * i / STEPS
                y = start['y'] + (end['y'] - start['y']) * i / STEPS
                page.mouse.move(x, y)
                rows_seen.add(page.evaluate(ROW_AT_POINT, {'x': x, 'y': y}))
            print(f'rows under the pointer across {STEPS}-step travel from row 0 to its own link: {sorted(rows_seen)}', flush=True)
            page.screenshot(path=str(shots / 'pointer-travel-end.png'))

            page.evaluate("""
() => {
  window.__clickedHref = null;
  document.addEventListener('click', (e) => {
    const a = e.target.closest('a[href]');
    if (a) { window.__clickedHref = a.href; e.preventDefault(); }
  }, { capture: true, once: true });
}
""")
            page.mouse.click(end['x'], end['y'])
            clicked_href = page.evaluate('() => window.__clickedHref')
            print(f'click at the end of that travel landed on: {clicked_href}', flush=True)

            page.mouse.move(0, 0)
            page.wait_for_timeout(100)

            # ---------------------------------------------------------------
            # N2a: THE LAST COMPLETE ROW'S PREVIEW OPENS UPWARD, NOT CLIPPED.
            # ---------------------------------------------------------------
            complete = page.evaluate(COMPLETE_ROWS_IN, None)
            view_box = view.bounding_box()
            last_complete_index = page.evaluate("""
(viewBottom) => {
  const items = [...document.querySelectorAll('.mgd-item')];
  let last = -1;
  items.forEach((it, i) => {
    const btn = it.querySelector('.q2-magnet-evidence-row');
    const b = btn.getBoundingClientRect();
    if (b.bottom <= viewBottom) last = i;
  });
  return last;
}
""", view_box['y'] + view_box['height'])
            assert last_complete_index >= 0, 'no complete row found inside the view at rest'
            last_box = items.nth(last_complete_index).bounding_box()
            page.mouse.move(last_box['x'] + last_box['width'] / 2, last_box['y'] + last_box['height'] / 2)
            page.wait_for_timeout(100)
            bottom_state = page.evaluate("""
(i) => {
  const item = document.querySelectorAll('.mgd-item')[i];
  const more = item.querySelector('.q2-magnet-row-more');
  const view = document.querySelector('.q2-magnet-view').getBoundingClientRect();
  const r = more.getBoundingClientRect();
  return { opensUp: more.classList.contains('opens-up'), top: r.top, bottom: r.bottom,
           viewTop: view.top, viewBottom: view.bottom,
           within: r.top >= view.top - 0.5 && r.bottom <= view.bottom + 0.5 }
}
""", last_complete_index)
            print(f'last complete row index {last_complete_index} ({complete and len(complete) or 0} complete at rest): '
                  f'preview placement {json.dumps(bottom_state)}', flush=True)
            page.screenshot(path=str(shots / 'bottom-edge.png'))
            page.mouse.move(0, 0)
            page.wait_for_timeout(100)

            # ---------------------------------------------------------------
            # N2b: AN OPEN PREVIEW NEVER PAINTS OVER THE STICKY FILTERS.
            # ---------------------------------------------------------------
            page.evaluate("() => { document.querySelector('.q2-magnet-view').scrollTop = 935; }")
            page.wait_for_timeout(100)
            pills = page.locator('.q2-magnet-type-pills').bounding_box()
            near_pills_index = page.evaluate("""
(pillsBottom) => {
  const items = [...document.querySelectorAll('.mgd-item')];
  let found = -1;
  items.forEach((it, i) => {
    if (found >= 0) return;
    const btn = it.querySelector('.q2-magnet-evidence-row');
    const b = btn.getBoundingClientRect();
    if (b.top >= pillsBottom - 40 && b.top <= pillsBottom + 40) found = i;
  });
  return found;
}
""", pills['y'] + pills['height'])
            if near_pills_index >= 0:
                near_box = items.nth(near_pills_index).bounding_box()
                page.mouse.move(near_box['x'] + near_box['width'] / 2, near_box['y'] + near_box['height'] / 2)
                page.wait_for_timeout(100)
            probe_point = {'x': pills['x'] + pills['width'] / 2, 'y': pills['y'] + pills['height'] - 3}
            pills_on_top = page.evaluate("""
(pt) => {
  const el = document.elementFromPoint(pt.x, pt.y);
  return !!(el && el.closest('.q2-magnet-type-pills'));
}
""", probe_point)
            print(f'row near the sticky pills: index {near_pills_index}; '
                  f'pills still receive the pointer at their own lower edge while a preview is open: {pills_on_top}', flush=True)
            page.screenshot(path=str(shots / 'sticky-edge.png'))

            assert not errors, f'page errors: {errors}'

            ok_travel = rows_seen == {0}
            ok_click = clicked_href and clicked_href.endswith('CBMi1')
            ok_bottom = bottom_state['opensUp'] and bottom_state['within']
            ok_sticky = pills_on_top
            print(f'RESULT pointer_stayed_on_row0={ok_travel} click_hit_row0_link={ok_click} '
                  f'bottom_opened_up_within_view={ok_bottom} pills_on_top_of_open_preview={ok_sticky}', flush=True)
            assert ok_travel, f'pointer travel crossed into other rows: {sorted(rows_seen)}'
            assert ok_click, f'click at the travel endpoint hit {clicked_href!r}, not row 0 link'
            assert ok_bottom, f'bottom row preview not flipped/contained: {bottom_state}'
            assert ok_sticky, 'sticky pills were covered by an open preview'
            browser.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
