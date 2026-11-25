"""Focused pointer, persistence and viewport checks against the real Magnet frame."""
import subprocess
import time
import tempfile
import urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

root = Path(__file__).resolve().parents[1]
url = 'http://127.0.0.1:5482/tests/quiet_magnet_frame.html'
checks = 0

def check(condition, description):
    global checks
    assert condition, description
    checks += 1
    print(f'PASS {checks}: {description}', flush=True)

with open(Path(tempfile.gettempdir()) / 'quiet-magnet-resize-vite.log', 'w') as log:
    proc = subprocess.Popen(['node', 'node_modules/vite/bin/vite.js', '--config', 'tests/quiet_magnet_frame_vite.mjs'],
                            cwd=root, stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        for _ in range(100):
            if proc.poll() is not None:
                raise RuntimeError('Vite exited')
            try:
                urllib.request.urlopen(url, timeout=1).close()
                break
            except OSError:
                time.sleep(.1)
        else:
            raise RuntimeError('Vite did not become ready')
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel='msedge', headless=True)
            page = browser.new_page(viewport={'width': 1440, 'height': 900})
            page.goto(url)
            page.evaluate('localStorage.clear(); sessionStorage.clear()')
            page.reload()
            card = page.locator('.q2-magnet-card')
            expect(card).to_be_visible()
            def drag(edge, dx, dy):
                box = card.locator('.q2-magnet-resize-' + edge).bounding_box()
                x, y = box['x'] + box['width'] / 2, box['y'] + box['height'] / 2
                page.mouse.move(x, y); page.mouse.down(); page.mouse.move(x + dx, y + dy, steps=5); page.mouse.up()
            def dimensions():
                return page.evaluate('window.frame.state().dimensions')
            drag('e', 140, 0); drag('s', 0, -100); drag('nw', 50, 40)
            chosen = dimensions()
            check(chosen == {'width': 740, 'height': 510}, f'edge and corner pointer resize: {chosen}')
            page.get_by_role('button', name='Close Magnet', exact=True).click()
            page.locator('.q2-magnet-puck').click()
            check(dimensions() == chosen, 'close and reopen retains dimensions')
            page.reload(); expect(card).to_be_visible()
            check(dimensions() == chosen, 'reload retains dimensions')
            page.set_viewport_size({'width': 390, 'height': 500}); page.wait_for_timeout(100)
            box = card.bounding_box()
            check(box['x'] >= 0 and box['y'] >= 0 and box['x'] + box['width'] <= 390 and box['y'] + box['height'] <= 500, f'clamped to small viewport: {box}')
            check(dimensions() == chosen, 'viewport clamp does not overwrite preference')
            reading = page.locator('.q2-magnet-view')
            check(reading.evaluate('(el) => el.scrollHeight > el.clientHeight'), 'content remains scrollable')
            page.set_viewport_size({'width': 1440, 'height': 900}); page.wait_for_timeout(100)
            box = card.bounding_box()
            check(round(box['width']) == chosen['width'] and round(box['height']) == chosen['height'], 'dimensions return when viewport grows')
            browser.close()
        print(f'Completed: {checks} passed, 0 failed, 0 skipped, 0 errors', flush=True)
    finally:
        proc.terminate(); proc.wait(timeout=10)
