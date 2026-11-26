"""READ-ONLY measurement against the live TEST candidate (http://127.0.0.1:8780):
breaks down exactly where the Collection scroll view's vertical budget goes on the
real astronomy Magnet, to find why only 11 of ~624px worth of rows are visible
(ent-e27a43b60927 / ent-e20fb2f91abf). Makes no write, no deploy, no restart --
pure navigation and measurement on the candidate TEST already serves, following
the same open sequence as magnet_refinement_shots.py.
"""
import json
from playwright.sync_api import sync_playwright

MAGNET = 'mag-265878e92e5c987c'
MAGNET_NAME = 'Space missions and astronomy'
URL = 'http://127.0.0.1:8780/quiet2'

with sync_playwright() as pw:
    browser = pw.chromium.launch(channel='msedge', headless=True)
    context = browser.new_context(viewport={'width': 1600, 'height': 1400}, device_scale_factor=1)
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.goto(URL, wait_until='domcontentloaded')
    page.wait_for_timeout(9000)

    page.locator('[data-open-magnet]:visible').first.click()
    page.wait_for_timeout(1500)
    row = page.get_by_role('option', name=MAGNET_NAME, exact=False).first
    row.wait_for(timeout=90000)
    row.click()
    page.wait_for_timeout(1200)
    page.get_by_role('button', name='Open in current workspace', exact=False).first.click()
    page.wait_for_timeout(4000)

    where = f'.q2-magnet-canvas [data-magnet="{MAGNET}"]'
    card = page.locator(f'{where} .q2-magnet-card')
    if card.count() == 0:
        page.locator(f'{where} .q2-magnet-puck').click()
        page.wait_for_timeout(1500)

    try:
        page.get_by_role('button', name='Larger panel', exact=False).first.click()
        page.wait_for_timeout(1500)
    except Exception as exc:
        print('larger panel NOT REACHED', exc)

    card.get_by_role('tab', name='Collection', exact=False).first.click()
    page.wait_for_timeout(1500)

    info = page.evaluate("""
(sel) => {
  const root = document.querySelector(sel);
  const card = root.querySelector('.q2-magnet-card');
  const view = root.querySelector('.q2-magnet-view');
  const head = root.querySelector('.q2-magnet-place-head');
  const pills = root.querySelector('.q2-magnet-type-pills');
  const partial = root.querySelector('.q2-magnet-partial');
  const list = root.querySelector('.q2-magnet-collected-items');
  const dayHeads = [...root.querySelectorAll('.q2-magnet-day-head')];
  const srcHeads = [...root.querySelectorAll('.q2-magnet-source-head')];
  const srcHeadTexts = srcHeads.map((h) => h.textContent);
  const rows = [...root.querySelectorAll('.q2-magnet-evidence-row')];
  const rect = (el) => el ? (({top, bottom, height}) => ({top, bottom, height}))(el.getBoundingClientRect()) : null;
  const vrect = view ? view.getBoundingClientRect() : null;
  const visible = rows.filter((r) => {
    const b = r.getBoundingClientRect();
    return vrect && b.top >= vrect.top && b.bottom <= vrect.bottom;
  });
  const rowHeights = rows.slice(0, 20).map((r) => r.getBoundingClientRect().height);
  const srcHeadHeights = srcHeads.slice(0, 20).map((r) => r.getBoundingClientRect().height);
  return {
    cardRect: rect(card), viewRect: vrect, headRect: rect(head), pillsRect: rect(pills), partialRect: rect(partial),
    totalRows: rows.length, totalDayHeads: dayHeads.length, totalSrcHeads: srcHeads.length,
    srcHeadTextsSample: srcHeadTexts.slice(0, 25),
    visibleCompleteRows: visible.length,
    rowHeightsSample: rowHeights, srcHeadHeightsSample: srcHeadHeights,
    scrollHeight: list ? list.scrollHeight : null,
    listOwnHeight: list ? list.getBoundingClientRect().height : null,
  };
}
""", where)
    print(json.dumps(info, indent=2))
    card.screenshot(path='density-probe.png')
    if errors:
        print('PAGE ERRORS', errors)
    browser.close()
