"""Gate 1: the plan's early rendered comparison of the real app against the approved preview.

PLAN.md (adm-8ba17c0776c6) section 6: "After H1's full spine and before any of H2-H5
merges: build the real app, open a real Magnet on a fixture Brain, and compare the
rendered chrome against magnet-preview.html at 1440x700, 390x844 and 320x640 -- header
with icon-only gear, six tabs in the approved order, search toolbar, footer composer
slot, puck + attached card geometry, the card staying open when the pointer leaves and
after a reload, and the surrounding workspace's bounding box, scrollTop and draft
unchanged."

This drives the REAL app (Host.tsx -> Magnet.tsx) served from its own build over a
DISPOSABLE fixture Brain, never a live Brain and never TEST. The approved preview is
rendered in the same browser at the same widths, from the byte-identical local copy of
the owner-approved artifact, so the comparison is measured rather than assumed.

What it does NOT claim: the footer composer's CONTENTS are H2's part and are absent at
H1. This check asserts only that the frame reserves the slot and that nothing else
occupies it, and records the absence as a scope limitation.

Usage (the server and the UI build must already be up):
  python tools/quiet_magnet_gate1_browser.py --base http://127.0.0.1:8921 \
      --fixture .preview/quiet-magnet-gate1 --out .preview/gate1
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from pathlib import Path

from playwright.sync_api import sync_playwright, expect

REPO = Path(__file__).resolve().parents[1]
PREVIEW_DIR = REPO.parent / 'magnet-hybrid-preview'
APPROVED_SHA = 'f44929e8ddc243073b50de3b156b25389735dd1c0b00ffc41753e474eb473d60'
WIDTHS = [(1440, 700), (390, 844), (320, 640)]
DRAFT = 'GATE1 workspace draft that must survive the Magnet'

# The frame's six slots, as the approved card orders them and as Magnet.tsx renders them.
PREVIEW = {'card': '#card', 'sub': '#collection-count', 'gear': '#settings-toggle', 'size': '#size',
           'close': '#close', 'tab': '#tabs button', 'toolbar': '#search-toolbar', 'search': '#search',
           'view': '#view', 'composer': '#composer', 'puck': '#puck', 'rest': '#puck-name'}
APP = {'card': '.q2-magnet-card', 'sub': '.q2-magnet-head-sub', 'gear': 'button[aria-label="Magnet settings"]',
       'size': '.q2-magnet-card>header button[aria-label$=" Magnet"]', 'close': 'button[aria-label="Close Magnet"]',
       'tab': '.q2-magnet-tabs button[role=tab]', 'toolbar': '.q2-magnet-toolbar', 'search': '.q2-magnet-toolbar input[type=search]',
       'view': '.q2-magnet-view', 'composer': '.q2-magnet-card>form,.q2-magnet-card>.q2-magnet-composer',
       'puck': '.q2-magnet-puck', 'rest': '.q2-magnet-rest-title'}

# Measured in the page, identically for the preview and the app.
MEASURE = """(sel) => {
  const q = (s) => s ? document.querySelector(s) : null;
  const box = (e) => { if (!e) return null; const r = e.getBoundingClientRect();
    return {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)}; };
  const card = q(sel.card);
  const tabs = Array.from(document.querySelectorAll(sel.tab));
  const selected = tabs.filter((t) => t.getAttribute('aria-selected') === 'true'
      || t.getAttribute('aria-current') === 'page').map((t) => t.textContent.trim());
  const view = q(sel.view);
  // A horizontal tab strip computes overflow-y:auto too (overflow-x:auto makes the
  // other axis auto), and the approved card's own tabs do. The contract's "view is the
  // only scroll container" is about scrolling CONTENT vertically, so measure that.
  const overflow = card ? Array.from(card.querySelectorAll('*')).filter((e) => {
      const s = getComputedStyle(e);
      return ['auto', 'scroll'].includes(s.overflowY) || ['auto', 'scroll'].includes(s.overflowX); }) : [];
  const scrollers = overflow.filter((e) => e.scrollHeight > e.clientHeight + 1);
  return {
    card: box(card),
    cardHidden: card ? !!card.hidden : null,
    header: card ? box(card.querySelector('header,.card-head')) : null,
    headSub: q(sel.sub) ? q(sel.sub).textContent.trim() : null,
    gear: !!q(sel.gear),
    gearTextOnly: q(sel.gear) ? q(sel.gear).textContent.replace(/[\\s\\u2699\\u2600-\\u27bf]/g, '') : null,
    gearExpanded: q(sel.gear) ? q(sel.gear).getAttribute('aria-expanded') : null,
    gearControls: q(sel.gear) ? !!q(sel.gear).getAttribute('aria-controls') : null,
    sizeLabel: q(sel.size) ? q(sel.size).getAttribute('aria-label') : null,
    closeLabel: q(sel.close) ? q(sel.close).getAttribute('aria-label') : null,
    tabs: tabs.map((t) => t.textContent.trim()),
    selected: selected,
    toolbar: !!q(sel.toolbar), toolbarBox: box(q(sel.toolbar)),
    search: !!q(sel.search),
    searchLabel: (() => { const i = q(sel.search); if (!i) return null;
      const l = i.closest('label') || document.querySelector('label[for="' + i.id + '"]');
      return l ? l.textContent.trim() : null; })(),
    view: !!view, viewBox: box(view), viewTabIndex: view ? view.getAttribute('tabindex') : null,
    scrollerCount: scrollers.length,
    scrollersAreView: scrollers.length > 0 && scrollers.every((e) => e === view),
    overflowElements: overflow.map((e) => e.tagName.toLowerCase() + '.' + ((e.className||'').toString().trim() || e.id)),
    composer: !!q(sel.composer),
    textareas: card ? card.querySelectorAll('textarea').length : null,
    details: card ? card.querySelectorAll('details').length : null,
    puck: box(q(sel.puck)),
    puckColour: q(sel.puck) ? getComputedStyle(q(sel.puck)).backgroundColor : null,
    puckExpanded: q(sel.puck) ? q(sel.puck).getAttribute('aria-expanded') : null,
    rest: q(sel.rest) ? {text: q(sel.rest).textContent.trim(), hidden: !!q(sel.rest).hidden, box: box(q(sel.rest))} : null,
    viewport: {w: window.innerWidth, h: window.innerHeight},
  };
}"""


class Report:
    def __init__(self):
        self.rows: list[dict] = []

    def check(self, group: str, width: str, ok: bool, words: str, detail=None):
        self.rows.append({'group': group, 'width': width, 'ok': bool(ok), 'check': words, 'detail': detail})
        return bool(ok)

    def counts(self):
        return {'passed': sum(1 for r in self.rows if r['ok']), 'failed': sum(1 for r in self.rows if not r['ok'])}

    def failures(self):
        return [r for r in self.rows if not r['ok']]


def approved_reference() -> dict:
    """The owner-approved artifact and the constants it actually declares."""
    html = PREVIEW_DIR / 'magnet-preview.html'
    css = (PREVIEW_DIR / 'hybrid.css').read_text('utf-8')
    js = (PREVIEW_DIR / 'hybrid.js').read_text('utf-8')
    tabs = re.search(r"const tabs=\[([^\]]*)\]", js)
    return {
        'path': str(html), 'bytes': html.stat().st_size,
        'sha256': hashlib.sha256(html.read_bytes()).hexdigest(),
        'tabs': [t.strip().strip("'\"") for t in tabs.group(1).split(',')] if tabs else [],
        'width_narrow': int(re.search(r"\.floating\{--width:(\d+)px\}", css).group(1)),
        'width_wide': int(re.search(r"\.floating\.wide\{--width:(\d+)px\}", css).group(1)),
        'breakpoint': int(re.search(r"@media\(max-width:(\d+)px\)", css).group(1)),
        'narrow_rule': re.search(r"\{\.floating,\.floating\.wide\{--width:([^}]+)\}", css).group(1),
    }


def expected_width(viewport_w: int, wide: bool, ref: dict) -> int:
    """What the approved CSS says the card is at this viewport."""
    if viewport_w <= ref['breakpoint']:
        return viewport_w - 24          # calc(100vw - 24px)
    return ref['width_wide'] if wide else ref['width_narrow']


def measure_preview(page, ref, out: Path) -> dict:
    """The approved artifact, rendered in this same browser at each width."""
    page.goto((PREVIEW_DIR / 'magnet-preview.html').as_uri(), wait_until='load')
    page.wait_for_timeout(600)
    seen = {}
    for w, h in WIDTHS:
        page.set_viewport_size({'width': w, 'height': h})
        page.wait_for_timeout(350)
        seen[f'{w}x{h}'] = page.evaluate(MEASURE, PREVIEW)
        page.screenshot(path=str(out / f'approved-{w}x{h}.png'))
    return seen


def open_magnet(page, mid: str):
    """Reach Magnet Management the way this layout offers it: the rail on a wide
    screen, the top bar's Magnets link on a narrow one."""
    rail = page.get_by_role('button', name='Magnet Management', exact=True)
    top = page.locator('button.q2-top-magnets')
    if rail.count() and rail.is_visible():
        rail.click()
    elif top.count():
        top.click()
    else:
        raise RuntimeError('no Magnet Management entry point in this layout')
    dialog = page.get_by_role('dialog', name='Magnet Management')
    expect(dialog).to_be_visible(timeout=20000)
    dialog.get_by_role('option', name='Island observatory', exact=False).click()
    dialog.get_by_role('button', name='Open in current workspace', exact=True).click()
    magnet = page.locator(f'[data-magnet="{mid}"]')
    expect(magnet.locator('.q2-magnet-puck')).to_be_visible(timeout=20000)
    return magnet


def workspace_state(page) -> dict:
    return page.evaluate("""() => {
      const c = document.querySelector('.q2-conv');
      const t = document.querySelector('textarea[aria-label="write a post"]');
      const r = c ? c.getBoundingClientRect() : null;
      return {conv: r ? {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)} : null,
              scrollTop: c ? Math.round(c.scrollTop) : null,
              windowScroll: Math.round(window.scrollY),
              draft: t ? t.value : null, inert: document.querySelectorAll('.q2-work-row[inert]').length};
    }""")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--base', default='http://127.0.0.1:8921')
    ap.add_argument('--fixture', default='.preview/quiet-magnet-gate1')
    ap.add_argument('--out', default='.preview/gate1')
    args = ap.parse_args()

    fixture = (REPO / args.fixture).resolve()
    out = (REPO / args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((fixture / 'manifest.json').read_text('utf-8'))['primary']
    mid = manifest['magnets']['primary']
    url = f"{args.base}/quiet2?c={manifest['A']}&at=1"

    ref = approved_reference()
    r = Report()
    errors: list[str] = []
    receipt: dict = {'checked_at': time.time(), 'app_url': url, 'fixture': str(fixture),
                     'approved_reference': ref, 'widths': {}}

    r.check('reference', '-', ref['sha256'] == APPROVED_SHA,
            'the compared preview is byte-identical to the owner-approved artifact', ref['sha256'])
    r.check('reference', '-', ref['tabs'] == ['Summary', 'All', 'Posts', 'Files', 'Perspectives', 'Conversation'],
            'the approved preview declares the six tabs in the approved order', ref['tabs'])
    r.check('reference', '-', (ref['width_narrow'], ref['width_wide'], ref['breakpoint']) == (650, 900, 700),
            'the approved preview declares 650/900 px and a 700 px full-width breakpoint',
            [ref['width_narrow'], ref['width_wide'], ref['breakpoint'], ref['narrow_rule']])

    with sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge', headless=True)
        try:
            ctx = browser.new_context(viewport={'width': 1440, 'height': 700})
            page = ctx.new_page()
            approved = measure_preview(page, ref, out)
            receipt['approved_measured'] = approved
            ctx.close()

            for w, h in WIDTHS:
                key = f'{w}x{h}'
                a = approved[key]
                ctx = browser.new_context(viewport={'width': w, 'height': h})
                page = ctx.new_page()
                page.on('pageerror', lambda e, k=key: errors.append(f'{k}: {e}'))
                page.goto(url, wait_until='domcontentloaded')
                page.wait_for_timeout(5000)

                # The surrounding workspace, before this Magnet exists on screen.
                draft_box = page.locator('textarea[aria-label="write a post"]')
                if draft_box.count():
                    draft_box.fill(DRAFT)
                before = workspace_state(page)

                magnet = open_magnet(page, mid)
                puck = magnet.locator('.q2-magnet-puck')

                # --- open: the approved model is clicked, and it stays open.
                rest_before = magnet.locator('.q2-magnet-rest-title')
                r.check('puck_card', key, rest_before.count() == 1 and 'collected items' not in rest_before.inner_text(),
                        'a closed puck shows its name and no fabricated count',
                        rest_before.inner_text() if rest_before.count() else None)
                puck.hover(); page.wait_for_timeout(150)
                r.check('open', key, magnet.locator('.q2-magnet-card').count() == 0, 'hover opens nothing')
                puck.focus(); page.wait_for_timeout(150)
                r.check('open', key, magnet.locator('.q2-magnet-card').count() == 0, 'focusing the puck opens nothing')
                puck.click()
                expect(magnet.locator('.q2-magnet-card')).to_be_visible(timeout=15000)
                page.wait_for_timeout(400)
                r.check('open', key, True, 'clicking the puck opens the card')
                page.mouse.move(w - 5, 5); page.wait_for_timeout(250)
                r.check('open', key, magnet.locator('.q2-magnet-card').count() == 1,
                        'the card stays open when the pointer leaves')

                m = page.evaluate(MEASURE, APP)
                receipt['widths'][key] = {'approved': a, 'app': m, 'workspace_before': before}
                # The open card itself, which is what the approved screenshots show.
                page.screenshot(path=str(out / f'app-open-{w}x{h}.png'))
                m['cardInk'] = page.evaluate("""() => { const c = document.querySelector('.q2-magnet-card');
                    const s = getComputedStyle(c); return {background: s.backgroundColor, color: s.color}; }""")

                # --- hierarchy: the frame's slots, in the approved order.
                order = page.evaluate("""() => { const c = document.querySelector('.q2-magnet-card');
                    return c ? Array.from(c.children).map((e) => e.tagName.toLowerCase() + '.' + (e.className||'')) : []; }""")
                receipt['widths'][key]['card_children'] = order
                r.check('hierarchy', key, order[:1] == [o for o in order[:1] if o.startswith('header')],
                        'the card opens with its header, as the approved card does', order[:1])
                r.check('hierarchy', key, [o.split('.')[0] for o in order[:4]] == ['header', 'nav', 'div', 'div'],
                        'header, tabs, search toolbar then view, in the approved order', order[:4])
                r.check('hierarchy', key, order and order[-1].startswith('footer'),
                        'the foot closes the card', order[-1] if order else None)
                r.check('hierarchy', key, m['details'] == 0,
                        'no <details> disclosure is left in the card (the approved frame has none)', m['details'])
                r.check('hierarchy', key, m['view'] and m['viewTabIndex'] == a['viewTabIndex'] == '-1'
                        and m['scrollersAreView'] and m['scrollerCount'] == 1,
                        'the view is the only vertically scrolling container, and is focusable as the approved #view is',
                        [m['scrollerCount'], m['scrollersAreView'], m['viewTabIndex']])
                r.check('hierarchy', key,
                        set(m['overflowElements']) <= {'nav.q2-magnet-tabs', 'div.q2-magnet-view'},
                        "the card's only overflow elements are the approved tab strip and view",
                        [m['overflowElements'], a['overflowElements']])

                # --- header chrome, compared field by field with the approved header.
                r.check('hierarchy', key, m['gear'] and not m['gearTextOnly'],
                        'the header gear is icon-only, as the approved #settings-toggle is', m['gearTextOnly'])
                r.check('hierarchy', key, m['gearExpanded'] is not None and m['gearControls'],
                        'the gear carries aria-expanded and aria-controls, as the approved one does',
                        [m['gearExpanded'], m['gearControls']])
                r.check('hierarchy', key, m['sizeLabel'] == a['sizeLabel'] == 'Expand Magnet',
                        'the size control is labelled exactly as the approved #size', [m['sizeLabel'], a['sizeLabel']])
                r.check('hierarchy', key, m['closeLabel'] == a['closeLabel'] == 'Close Magnet',
                        'the close control is labelled exactly as the approved #close', [m['closeLabel'], a['closeLabel']])
                r.check('hierarchy', key, m['headSub'] is not None and 'collected items' in m['headSub']
                        and 'collected items' in (a['headSub'] or ''),
                        'the header subline is the collected count, as the approved #collection-count is',
                        [m['headSub'], a['headSub']])

                # --- tabs.
                r.check('tabs', key, m['tabs'] == a['tabs'] == ref['tabs'],
                        'six tabs in the approved order, matching the rendered approved preview',
                        [m['tabs'], a['tabs']])
                r.check('tabs', key, m['selected'] == ['Summary'],
                        'Summary is first and selected by default', m['selected'])
                magnet.get_by_role('tab', name='Files', exact=True).click()
                page.wait_for_timeout(250)
                r.check('tabs', key, page.evaluate(MEASURE, APP)['selected'] == ['Files'],
                        'selecting a tab moves the selection')
                magnet.get_by_role('tab', name='Summary', exact=True).click()
                page.wait_for_timeout(200)

                # --- search toolbar and the footer composer slot.
                r.check('hierarchy', key, m['toolbar'] and m['search'] and a['toolbar'] and a['search'],
                        'the search toolbar is present, as it is in the approved card')
                r.check('hierarchy', key, (m['searchLabel'] or '').startswith('Search all Magnet information'),
                        'the search line keeps the approved accessible name', m['searchLabel'])
                r.check('hierarchy', key, m['textareas'] == 0 and not m['composer'],
                        'the footer composer slot is empty and unoccupied at H1 (H2 supplies its contents)',
                        [m['textareas'], m['composer']])

                # --- puck and attached card geometry.
                r.check('puck_card', key, m['puck'] and m['puck']['w'] == 64,
                        'the resting puck keeps its 64 px geometry', m['puck'])
                r.check('puck_card', key, m['puckColour'] == 'rgb(237, 191, 80)',
                        'the puck keeps the accepted yellow', m['puckColour'])
                c = m['card']
                r.check('puck_card', key, c['x'] >= 0 and c['x'] + c['w'] <= w + 1,
                        'the card stays inside the canvas width', [c, w])
                r.check('puck_card', key, c['y'] >= 0 and c['y'] + c['h'] <= h + 1,
                        'the card stays inside the canvas height', [c, h])
                r.check('puck_card', key,
                        not (c['x'] + c['w'] < m['puck']['x'] - 1 or c['x'] > m['puck']['x'] + m['puck']['w'] + 33),
                        'the card stays joined to its puck rather than detaching', [c, m['puck']])

                # --- width behaviour: a width only, matching the approved CSS.
                want = expected_width(w, False, ref)
                r.check('width', key, abs(c['w'] - want) <= 2,
                        f'the card is the approved width at this viewport ({want} px)', [c['w'], want])
                r.check('width', key, abs(c['w'] - a['card']['w']) <= 2,
                        'the card width matches the rendered approved preview at this viewport',
                        [c['w'], a['card']['w']])
                magnet.get_by_role('button', name='Expand Magnet', exact=True).click()
                page.wait_for_timeout(350)
                wm = page.evaluate(MEASURE, APP)
                want_wide = expected_width(w, True, ref)
                r.check('width', key, abs(wm['card']['w'] - want_wide) <= 2,
                        f'expanding gives the approved wide width at this viewport ({want_wide} px)',
                        [wm['card']['w'], want_wide])
                r.check('width', key, wm['tabs'] == m['tabs'] and wm['toolbar'] and wm['view']
                        and wm['textareas'] == m['textareas'],
                        'wide is a width only: tabs, toolbar, view and composer slot are unchanged')
                r.check('width', key, wm['sizeLabel'] == 'Compact Magnet',
                        'the size control relabels to Compact Magnet', wm['sizeLabel'])
                magnet.get_by_role('button', name='Compact Magnet', exact=True).click()
                page.wait_for_timeout(350)
                r.check('width', key, abs(page.evaluate(MEASURE, APP)['card']['w'] - want) <= 2,
                        'compacting returns the approved width')

                # --- the card stays open after a reload (persisted working state).
                page.reload(wait_until='domcontentloaded')
                page.wait_for_timeout(6000)
                after_reload = page.evaluate("""(mid) => { const n = document.querySelector('[data-magnet="'+mid+'"]');
                    return {present: !!n, card: n ? n.querySelectorAll('.q2-magnet-card').length : 0,
                            puck: n ? n.querySelectorAll('.q2-magnet-puck').length : 0}; }""", mid)
                receipt['widths'][key]['after_reload'] = after_reload
                stored = page.evaluate("""() => Object.fromEntries(Object.entries(localStorage)
                    .filter(([k]) => k.startsWith('mentis.magnet.working')))""")
                receipt['widths'][key]['persisted'] = stored
                r.check('open', key, any(json.loads(v).get('open') is True for v in stored.values()),
                        'open is persisted as true in the working state across a reload', list(stored))
                r.check('open', key, after_reload['present'] and after_reload['card'] == 1,
                        'the card is still open after a reload', after_reload)

                # --- close, and the surrounding workspace.
                if after_reload['present'] and after_reload['card'] == 1:
                    page.locator(f'[data-magnet="{mid}"]').get_by_role('button', name='Close Magnet', exact=True).click()
                    page.wait_for_timeout(400)
                    r.check('open', key, page.locator(f'[data-magnet="{mid}"] .q2-magnet-card').count() == 0,
                            'Close Magnet shuts the card')
                after = workspace_state(page)
                receipt['widths'][key]['workspace_after'] = after
                r.check('workspace', key, after['conv'] == before['conv'],
                        "the surrounding workspace's bounding box is unchanged", [before['conv'], after['conv']])
                r.check('workspace', key, after['scrollTop'] == before['scrollTop']
                        and after['windowScroll'] == before['windowScroll'],
                        "the surrounding workspace's scrollTop is unchanged",
                        [before['scrollTop'], after['scrollTop'], before['windowScroll'], after['windowScroll']])
                r.check('workspace', key, before['draft'] is None or after['draft'] == DRAFT,
                        'the surrounding workspace draft is unchanged', [before['draft'], after['draft']])
                r.check('workspace', key, after['inert'] == 0,
                        'the main work row is never made inert by the Magnet', after['inert'])

                page.screenshot(path=str(out / f'app-{w}x{h}.png'))
                ctx.close()
        finally:
            browser.close()

    r.check('errors', '-', not errors, 'no page errors in the real app', errors[:5])
    counts = r.counts()
    receipt.update(checks=r.rows, **counts, skipped=0, errors=len(errors), page_errors=errors)
    (out / 'gate1-receipt.json').write_text(json.dumps(receipt, indent=2), 'utf-8')
    for row in r.failures():
        print(f"FAIL [{row['group']}/{row['width']}] {row['check']} :: {row['detail']}")
    print(json.dumps({**counts, 'skipped': 0, 'errors': len(errors),
                      'receipt': str(out / 'gate1-receipt.json')}, indent=2))
    print(f"Quiet Magnet Gate 1 rendered comparison: {counts['passed']} passed, "
          f"{counts['failed']} failed, 0 skipped, {len(errors)} errors")
    return 1 if counts['failed'] or errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
