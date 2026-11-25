"""Screenshot the rendered Perspectives states written by tests/partc_shots.mjs."""
from pathlib import Path
from playwright.sync_api import sync_playwright

root = Path(__file__).resolve().parents[1]
shots = sorted(root.glob('partc-shot-*.html'))
with sync_playwright() as p:
    browser = p.chromium.launch(channel='msedge', headless=True)
    page = browser.new_page(viewport={'width': 1400, 'height': 900}, device_scale_factor=1)
    for f in shots:
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.goto(f.as_uri())
        out = f.with_suffix('.png')
        page.screenshot(path=str(out))
        print(out.name, 'errors:', errors, flush=True)
    browser.close()
