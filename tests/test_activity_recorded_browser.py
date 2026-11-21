"""C2 fixture browser checks, headless installed Chrome only, 390px.
No live Brain, API, runtime, screenshots or persistent server.
Build with node tests/build_activity_fixture.mjs before running.
"""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import os
from threading import Thread

import pytest
from playwright.sync_api import sync_playwright, expect


PORT = int(os.environ.get('ACTIVITY_FIXTURE_PORT', '8947'))
BASE = f'http://127.0.0.1:{PORT}'


@pytest.fixture(scope='module')
def browser_fixture():
    root = Path(__file__).parents[1] / 'apps/fluid-web/dist-activity-fixture'
    assert (root / 'fixture.js').is_file(), 'build_activity_fixture.mjs must finish first'
    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_GET(self):
            if self.path.startswith('/fixture'):
                return super().do_GET()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(b'<html><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/fixture.css"><body style="margin:8px"><div id="root"></div><script type="module" src="/fixture.js"></script></body></html>')
    server = ThreadingHTTPServer(('127.0.0.1', PORT), partial(Handler, directory=str(root)))
    thread = Thread(target=server.serve_forever)
    thread.start()
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel='chrome', headless=True)
            yield browser
            browser.close()
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


@pytest.mark.parametrize('held', [1, 0])
def test_full_retained_output_keyboard_and_exact_host_references(browser_fixture, held):
    page = browser_fixture.new_page(viewport={'width': 390, 'height': 844})
    try:
        page.goto(f'{BASE}/?held={held}')
        activity = page.get_by_role('button', name='Activity', exact=True)
        activity.focus()
        page.keyboard.press('Enter')
        expect(page.get_by_text('Recorded session end: failed', exact=True)).to_be_visible()
        expect(page.get_by_text('FULL ERROR', exact=False)).to_contain_text('ERROR TAIL')
        summary = page.locator('summary')
        summary.focus()
        page.keyboard.press('Enter')
        output = page.locator('pre')
        expect(output).to_be_visible()
        text = output.inner_text()
        assert text.startswith('BEGIN\n') and '\nMIDDLE\n' in text and text.endswith('\nTAIL\n') and len(text) > 22000
        # Select everything the reader can copy; no clipboard permission needed.
        selected = output.evaluate('(el) => { const r = document.createRange(); r.selectNodeContents(el); const s = getSelection(); s.removeAllRanges(); s.addRange(r); return s.toString() }')
        assert selected == text.rstrip('\n')  # Chrome selection omits the terminal line break.
        assert output.text_content() == text  # The collector's characters remain intact in the DOM.
        expect(page.get_by_text('FULL NOTE', exact=False)).to_contain_text('NOTE TAIL')
        for words, identity in [('Open the answer', 'ent-answer'), ('Open returned artifact', 'adm-exact')]:
            button = page.get_by_role('button', name=words, exact=True)
            button.focus()
            page.keyboard.press('Enter')
            expect(page.get_by_role('dialog')).to_contain_text(identity)
            page.get_by_role('button', name='Close reference').click()
            expect(button).to_be_focused()
        if held:
            expect(page.get_by_text('Live activity summary', exact=False)).to_be_visible()
            expect(page.get_by_text('live summary sentinel', exact=True)).to_be_visible()
            assert page.get_by_text('no longer holds', exact=False).count() == 0
        else:
            expect(page.get_by_text('no longer holds', exact=False)).to_be_visible()
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'no horizontal overflow at 390px'
        activity.focus()
        page.keyboard.press('Enter')
        expect(summary).to_have_count(0)
    finally:
        page.close()


@pytest.mark.parametrize('retrieve', ['reread', 'reopen'])
def test_pending_manual_reread_and_reopen_without_polling(browser_fixture, retrieve):
    page = browser_fixture.new_page(viewport={'width': 390, 'height': 844})
    try:
        page.goto(BASE + '/?pending=1')
        activity = page.get_by_role('button', name='Activity', exact=True)
        activity.click()
        expect(page.get_by_text('may still be publishing', exact=False)).to_be_visible()
        page.get_by_role('button', name='Count reads').click()
        before = page.locator('#reads').inner_text()
        page.wait_for_timeout(1200)  # More than one live-feed interval; terminal absence must not poll.
        page.get_by_role('button', name='Count reads').click()
        assert page.locator('#reads').inner_text() == before
        page.get_by_role('button', name='Publish terminal', exact=True).click()
        if retrieve == 'reread':
            page.get_by_role('button', name='Reread recorded end', exact=True).click()
        else:
            activity.click()
            activity.click()
        expect(page.get_by_text('Recorded session end: failed', exact=True)).to_be_visible()
        expect(page.get_by_text('live summary sentinel', exact=True)).to_be_visible()
        activity.click()
        activity.click()
        expect(page.get_by_text('Recorded session end: failed', exact=True)).to_be_visible()
        page.get_by_role('button', name='Count reads').click()
        assert int(page.locator('#reads').inner_text()) > int(before)
    finally:
        page.close()


def test_read_refusal_and_late_response_after_brain_switch(browser_fixture):
    page = browser_fixture.new_page(viewport={'width': 390, 'height': 844})
    try:
        page.goto(BASE + '/?pending=1')
        page.get_by_role('button', name='Activity', exact=True).click()
        expect(page.get_by_text('may still be publishing', exact=False)).to_be_visible()
        page.get_by_role('button', name='Toggle read failure').click()
        page.get_by_role('button', name='Reread recorded end', exact=True).click()
        expect(page.get_by_text('Could not read its activity:', exact=False)).to_contain_text('fixture read refused')
        assert page.get_by_text('may still be publishing', exact=False).count() == 0
        page.get_by_role('button', name='Toggle read failure').click()
        page.get_by_role('button', name='Publish terminal', exact=True).click()
        page.get_by_role('button', name='Delay next read').click()
        page.get_by_role('button', name='Reread recorded end', exact=True).click()
        expect(page.get_by_role('button', name='Reading retained output', exact=False)).to_be_disabled()
        page.get_by_role('button', name='Switch Brain and finish read').click()
        expect(page.get_by_text('This page belongs to another Brain.', exact=False)).to_be_visible()
        assert page.locator('pre, summary, [data-ref]').count() == 0
    finally:
        page.close()
