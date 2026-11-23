"""Focused mounted Perspective UI in headless Edge; synthetic HTTP, no real-agent acceptance."""
import json
import subprocess
import time
import urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

root = Path(__file__).resolve().parents[1]
checks = []
def check(words):
    checks.append(words)

with (root / 'quiet-magnet-perspective-browser.log').open('w', encoding='utf-8') as log:
    proc = subprocess.Popen(['node', 'node_modules/vite/bin/vite.js', '--config', 'tests/quiet_magnet_perspective_vite.mjs'], cwd=root, stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
    print('owned harness pid', proc.pid, flush=True)
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen('http://127.0.0.1:5457/tests/quiet_magnet_perspective.html', timeout=1).close()
                break
            except OSError:
                if proc.poll() is not None: raise RuntimeError('Harness failed; see log')
                time.sleep(.1)
        with sync_playwright() as p:
            browser = p.chromium.launch(channel='msedge', headless=True)
            page = browser.new_page()
            errors = []
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.goto('http://127.0.0.1:5457/tests/quiet_magnet_perspective.html')
            editor = page.get_by_role('textbox', name='Edit saved question', exact=True)
            expect(editor).to_have_value('Latest saved question \u03b1\U0001f642')
            check('current question preloaded independently of old history')
            for words in ['Revised once \u03b1', 'Revised twice \U0001f642']:
                editor.fill(words)
                page.get_by_role('button', name='Save question revision', exact=True).click()
                expect(page.get_by_role('region', name='Selected saved question')).to_contain_text(words)
            check('two durable question edits show latest revision')
            page.get_by_role('textbox', name='Perspective name', exact=True).fill('New hypothesis')
            page.get_by_role('textbox', name='New question or hypothesis', exact=True).fill('A useful hypothesis?')
            page.get_by_role('button', name='Create and select Perspective', exact=True).click()
            expect(page.get_by_label('Active Perspective')).to_have_value('ent-newtopic211')
            expect(editor).to_have_value('A useful hypothesis?')
            check('create hypothesis selects new durable identity and preloads question')
            page.get_by_label('View inquiry history').select_option('ent-fixturetopicA')
            expect(editor).to_have_value('Revised twice \U0001f642')
            editor.fill('Unsaved history editor words')
            page.get_by_role('button', name='Discuss selected question', exact=True).click()
            expect(page.get_by_role('textbox', name='Conversation draft')).to_have_value('A useful hypothesis?')
            check('discussion uses selected saved question, not viewed history or unsaved edits')
            page.get_by_role('textbox', name='Conversation draft').fill('Existing draft kept')
            page.get_by_role('button', name='Open Perspectives', exact=True).click()
            page.get_by_role('button', name='Discuss selected question', exact=True).click()
            expect(page.get_by_role('status').filter(has_text='already has a different draft')).to_be_visible()
            check('discussion protects existing Composer draft')
            page.get_by_label('Active Perspective').select_option('ent-fixturetopicB')
            expect(editor).to_have_value('Alternative hypothesis')
            page.get_by_role('button', name='Retire Perspective', exact=True).click()
            expect(page.get_by_label('Active Perspective')).to_have_value('')
            page.get_by_role('button', name='Resume Perspective', exact=True).click()
            page.get_by_label('Active Perspective').select_option('ent-fixturetopicB')
            expect(editor).to_have_value('Alternative hypothesis')
            check('retire deselects and resume permits selection')
            page.reload()
            expect(page.get_by_label('Active Perspective')).to_have_value('ent-fixturetopicB')
            expect(editor).to_have_value('Alternative hypothesis')
            check('reload keeps durable selection and saved wording')
            page.evaluate('perspectiveTest.loseNext = true')
            editor.fill('Original uncertain edit')
            page.get_by_role('button', name='Save question revision', exact=True).click()
            expect(page.get_by_role('button', name='Retry unchanged inquiry action')).to_be_visible()
            before = page.evaluate('perspectiveTest.edits()')
            page.get_by_label('View inquiry history').select_option('ent-fixturetopicA')
            expect(editor).to_have_value('Revised twice \U0001f642')
            page.reload()
            expect(page.get_by_role('button', name='Retry unchanged inquiry action')).to_be_visible()
            page.get_by_role('button', name='Retry unchanged inquiry action').click()
            expect(page.get_by_role('button', name='Retry unchanged inquiry action')).to_have_count(0)
            expect(editor).to_have_value('Original uncertain edit')
            assert page.evaluate('perspectiveTest.edits()') == before
            check('uncertain edit survives reload and retries original target/key exactly once')
            assert not page.evaluate("perspectiveTest.calls.some(c => /prepare|finalize|reconcile|collection/.test(c.tail))")
            check('no grounded preparation qualification or collection calls')
            assert not errors, errors
            check('zero browser errors')
            browser.close()
        print(json.dumps({'passed': len(checks), 'failed': 0, 'skipped': 0, 'errors': 0, 'checks': checks}), flush=True)
    finally:
        stopped = subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'], capture_output=True)
        if stopped.returncode and proc.poll() is None:
            proc.terminate()
        proc.wait(timeout=15)
