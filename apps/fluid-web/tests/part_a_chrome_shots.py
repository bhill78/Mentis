"""Part A: the real panel chrome, rendered, beside the approved round-3 mockups.

Not a check -- a look. It mounts `quiet_magnet_frame_harness.tsx` (the real
`Magnet`, the real stylesheets, the real `ComposerBar`) in headless Edge and
photographs the panel in the states the approved mockups show, so the header,
the tab row, the body padding and the one footer line can be compared against
`magnet-design-round3/02-compact-current.png` and `03-sources.png` rather than
described. It also reports the measurements the design states, read off the
rendered DOM.

Its own Vite, on its own port, stopped by pid when it is done.
"""
import argparse
import json
from pathlib import Path
import subprocess
import time
import urllib.request
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--out', type=Path, required=True)
parser.add_argument('--port', type=int, default=5493)
args = parser.parse_args()
OUT = args.out
OUT.mkdir(parents=True, exist_ok=True)
URL = f'http://127.0.0.1:{args.port}/tests/quiet_magnet_frame.html'

MEASURE = """() => {
  const px = (el, p) => el ? getComputedStyle(el)[p] : null
  const card = document.querySelector('.q2-magnet-card')
  const head = card.querySelector('header')
  const tabs = card.querySelector('.q2-magnet-tabs')
  const tab = [...tabs.querySelectorAll('button')].find(b => b.getAttribute('aria-selected') === 'true')
  const view = card.querySelector('.q2-magnet-view')
  const foot = card.querySelector('.q2-magnet-hint')
  return {
    head: { padding: px(head, 'padding'), borderBottom: px(head, 'borderBottomColor'), gap: px(head, 'gap') },
    title: { size: px(head.querySelector('h2'), 'fontSize'), weight: px(head.querySelector('h2'), 'fontWeight') },
    icon: { size: px(card.querySelector('.q2-magnet-icon'), 'fontSize'), colour: px(card.querySelector('.q2-magnet-icon'), 'color') },
    headControls: [...head.querySelectorAll('button')].map(b => b.textContent.trim()),
    tabs: { gap: px(tabs, 'gap'), padding: px(tabs, 'padding'), borderBottom: px(tabs, 'borderBottomColor') },
    selectedTab: tab ? { text: tab.textContent.trim(), padding: px(tab, 'padding'), weight: px(tab, 'fontWeight'),
                         colour: px(tab, 'color'), underline: px(tab, 'borderBottomWidth') + ' ' + px(tab, 'borderBottomColor') } : null,
    body: { padding: px(view, 'padding') },
    foot: { text: foot.textContent.trim(), padding: px(foot, 'padding'), size: px(foot, 'fontSize'),
            colour: px(foot, 'color'), borderTop: px(foot, 'borderTopColor') },
    drawsFilterRow: !!card.querySelector('.q2-magnet-filters'),
    drawsOwnSearch: !!card.querySelector('.q2-magnet-toolbar'),
    composerPresent: !!card.querySelector('.q2-magnet-composer'),
  }
}"""

with (OUT / 'vite.log').open('w', encoding='utf-8') as log:
    proc = subprocess.Popen(['node', 'node_modules/vite/bin/vite.js', '--config', 'tests/quiet_magnet_frame_vite.mjs',
                             '--port', str(args.port), '--strictPort'],
                            cwd=ROOT, stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
    print(f'own Vite PID {proc.pid} on {args.port}', flush=True)
    report = {}
    try:
        for _ in range(150):
            if proc.poll() is not None:
                raise RuntimeError('own Vite exited')
            try:
                urllib.request.urlopen(URL, timeout=1).close()
                break
            except OSError:
                time.sleep(.1)
        else:
            raise RuntimeError('Vite did not become ready')
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel='msedge', headless=True)
            view = browser.new_page(viewport={'width': 1400, 'height': 900})
            errors = []
            view.on('pageerror', lambda e: errors.append(str(e)))
            view.goto(URL)
            view.locator('.q2-magnet-card').wait_for()
            # The mockups' own places: 02 is Perspectives, 03 is Collection,
            # and Conversation is the one place that keeps a standing composer.
            for name, tab in [('02-perspectives', 'Perspectives'), ('03-collection', 'Collection'),
                              ('summary', 'Summary'), ('conversation', 'Conversation')]:
                view.get_by_role('tab', name=tab, exact=False).click()
                view.wait_for_timeout(150)
                view.screenshot(path=str(OUT / f'part-a-{name}.png'))
                report[name] = view.evaluate(MEASURE)
            view.get_by_role('tab', name='Perspectives', exact=True).click()
            view.wait_for_timeout(100)
            view.locator('.q2-magnet-card').screenshot(path=str(OUT / 'part-a-card-only.png'))
            report['errors'] = errors
            browser.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        print(f'own Vite {proc.pid} stopped', flush=True)

(OUT / 'part-a-chrome.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report, indent=2))
