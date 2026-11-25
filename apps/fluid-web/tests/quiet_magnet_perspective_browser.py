"""The rebuilt Perspectives panel, mounted and driven in headless Edge.

Rewritten against the approved round-3 surface (`InquiryPanel.tsx`): the panel's
five states -- ASKING, a question and what is understood of it, SUPPORTING
ITEMS, PAST QUESTIONS, and WITH ROOM -- and the real controls each carries.
Every behavioural and authority assertion the earlier driver made is kept and
translated onto those controls: durable selection across a reload, one revision
draft per Perspective that never reaches another, an uncertain edit retried
exactly once with its original target and key, the Conversation draft that is
protected rather than replaced, no grounded preparation or collection call, no
word anywhere that reads as "inquiry", and zero browser errors.

Synthetic HTTP throughout (`quiet_magnet_perspective_harness.tsx`): no Brain, no
agent, no real-agent acceptance. The fixture's write routes are create,
selection, question, rename, retire and resume, so three controls of the rebuilt
surface are asserted present but not pressed -- `Record challenge` and `Send ↑`
(a follow-up is a `branch` write the fixture has no route for), and `Explore
supporting items ↗` (SupportingItems reads `snapshot().results` and subscribes
to `resource.subscribe`, neither of which the fixture resource carries, so
opening it unmounts the harness). They are reported as skipped, with their
reasons, in this run's summary.
"""
import json
import subprocess
import time
import urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

root = Path(__file__).resolve().parents[1]
URL = 'http://127.0.0.1:5457/tests/quiet_magnet_perspective.html'
# The panel's own words, as its module exports them.
NOTHING_RECORDED_YET = 'Nothing is recorded against this question yet. Discussing it keeps what is said with the question.'
GROUNDED_NOT_YET = 'Answering a question from what this Magnet collected is not available yet.'
DISCUSSION_READS = 'Discussion does not read your collected items.'
TRY_ASKING = 'What might be slowing our releases?'
HELP_TITLE = 'What can I do today?'
HELP_WORDS = 'You can discuss a question now, or browse collected items yourself. Discussion does not read those items to form its answer.'
BLOCK_REASON = 'Grounded Perspective answers are blocked'
QUESTION_IS_KEPT = 'This question is kept. What is understood of it can change as this Magnet collects more, and earlier answers stay readable.'
READ_AGAIN = 'Read this question again'
CHECKED_SAME = 'Read again: no newer answer is recorded against this question.'
SAVED_WORDS = 'Saved. No agent or collection was started.'
# 640 px of panel is where the aside comes up (a container query on the panel's
# own inline size), so the compact surface needs a narrower page than that.
COMPACT, ROOMY = {'width': 460, 'height': 1000}, {'width': 1100, 'height': 1000}

checks, skipped = [], []
def check(words):
    checks.append(words)

with (root / 'quiet-magnet-perspective-browser.log').open('w', encoding='utf-8') as log:
    proc = subprocess.Popen(['node', 'node_modules/vite/bin/vite.js', '--config', 'tests/quiet_magnet_perspective_vite.mjs'], cwd=root, stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
    print('owned harness pid', proc.pid, flush=True)
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(URL, timeout=1).close()
                break
            except OSError:
                if proc.poll() is not None: raise RuntimeError('Harness failed; see log')
                time.sleep(.1)
        with sync_playwright() as p:
            browser = p.chromium.launch(channel='msedge', headless=True)
            page = browser.new_page(viewport=COMPACT)
            errors = []
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.goto(URL)
            panel = page.get_by_role('region', name='Perspectives')
            editor = page.get_by_role('textbox', name='Edit saved question', exact=True)
            lens = page.get_by_label('Active question')
            seen = []                                  # every state's words, scanned at the end

            def to_past():
                if not page.locator('.q2p-past').count():
                    page.locator('.q2p-open-past').click()
                expect(page.locator('.q2p-past h3')).to_have_text('Past questions')

            def manage():
                """`Past questions ▾` is the one route to what administers a question."""
                d = page.locator('details[aria-label="Manage this question"]')
                if not d.evaluate('el => el.open'): d.locator('summary').first.click()
                return d

            def open_editor():
                page.get_by_role('button', name='Edit saved question').click()

            def go_asking():
                """Ordinary Conversation, then the compose box with nothing asked."""
                to_past(); manage()
                lens.select_option('')
                expect(lens).to_have_value('')
                page.get_by_role('button', name='＋ New question', exact=True).click()
                expect(page.locator('.q2p-head h3')).to_have_text('Explore a question')

            # -- a question, and what is understood of it (05 / 10) --------------
            expect(panel).to_be_visible()
            expect(page.locator('.q2p-asked')).to_have_text('Latest saved question α\U0001f642')
            expect(page.locator('.q2p-state')).to_contain_text('CURRENT MODE')
            expect(page.locator('.q2p-state')).to_contain_text('Ordinary discussion')
            expect(page.locator('.mgd-answer')).to_contain_text('Current understanding')
            expect(page.locator('.mgd-answer')).to_contain_text(NOTHING_RECORDED_YET)
            follow = page.get_by_role('textbox', name='Ask a follow-up', exact=True)
            expect(follow).to_have_attribute('placeholder', 'Ask a follow-up or explore an idea…')
            expect(follow).to_have_value('')
            expect(page.locator('.mgd-hint')).to_have_text(GROUNDED_NOT_YET)
            # Pressed below only where the fixture has the route; present here.
            expect(page.get_by_role('button', name='Explore supporting items ↗', exact=True)).to_be_visible()
            seen.append(page.inner_text('body'))
            check('the selected question, what the record holds of it and the follow-up box are the resting surface')

            # -- a kept question, and refreshing what is understood of it --------
            # The question stays and its answer may change under it, so the
            # resting surface says so and offers the manual read. The fixture
            # records no answer against it, so there is no "standing now" answer
            # and no kept earlier ones -- and the read must say that plainly
            # rather than imply something changed.
            expect(page.locator('.q2p-kept')).to_have_text(QUESTION_IS_KEPT)
            expect(page.locator('.mgd-answer')).not_to_contain_text('Answer standing now')
            expect(page.locator('.q2p-answer-history')).to_have_count(0)
            before = len(page.evaluate('window.perspectiveTest.calls'))
            page.get_by_role('button', name=READ_AGAIN, exact=True).click()
            expect(page.get_by_role('status').filter(has_text=CHECKED_SAME)).to_be_visible()
            after = page.evaluate('window.perspectiveTest.calls')
            # Reading again is reading: the detail and its history, no write.
            assert all(c['method'] == 'GET' for c in after[before:]), after[before:]
            assert any('/history' in c['tail'] for c in after[before:]), after[before:]
            expect(page.locator('.q2p-asked')).to_have_text('Latest saved question α\U0001f642')
            seen.append(page.inner_text('body'))
            check('a kept question says its answer may change, and reading it again re-reads the record without writing')

            # -- past questions, and the saved current question ------------------
            to_past()
            expect(page.locator('.q2p-past .mgd-eyebrow')).to_have_text('Perspectives')
            expect(page.get_by_text('Return to a question and continue the conversation.')).to_be_visible()
            expect(page.get_by_role('searchbox', name='Find a question')).to_be_visible()
            expect(page.get_by_role('button', name='＋ New question', exact=True)).to_be_visible()
            expect(page.locator('.q2p-row')).to_have_count(2)
            manage()
            expect(page.locator('details[aria-label="Manage this question"] summary').first).to_contain_text('More about “Original”')
            open_editor()
            expect(editor).to_have_value('Latest saved question α\U0001f642')
            check('current question preloaded independently of old history')
            for words in ['Revised once α', 'Revised twice \U0001f642']:
                editor.fill(words)
                page.get_by_role('button', name='Save question revision', exact=True).click()
                expect(page.locator('.q2p-past')).to_contain_text(f'Saved wording: {words}')
                expect(page.get_by_role('status').filter(has_text=SAVED_WORDS)).to_be_visible()
            check('two durable question edits show the latest revision and say no agent or collection was started')
            expect(page.get_by_role('button', name='Record challenge', exact=True)).to_be_enabled()
            page.get_by_role('button', name='Cancel question edit', exact=True).click()

            # -- asking, with nothing asked (02 / 09) ----------------------------
            go_asking()
            expect(page.locator('.q2p-head .mgd-eyebrow')).to_have_text('Perspectives')
            expect(page.get_by_text('Ask a question or share an idea to discuss.')).to_be_visible()
            ask = page.get_by_role('textbox', name='Question or hypothesis', exact=True)
            expect(ask).to_have_attribute('placeholder', 'What would you like to explore?')
            # Question-first creation: there is no name field anywhere on it.
            expect(page.get_by_role('textbox', name='Perspective name', exact=True)).to_have_count(0)
            expect(page.get_by_role('button', name='Ask →', exact=True)).to_be_disabled()
            expect(page.get_by_text('TRY ASKING')).to_be_visible()
            expect(page.get_by_text('AVAILABLE NOW')).to_be_visible()
            expect(page.get_by_text('Ordinary Conversation', exact=True)).to_be_visible()
            words = page.inner_text('body')
            assert words.count(DISCUSSION_READS) == 1, words
            seen.append(words)
            check('asking offers one invitation, one availability line, and says what discussion reads exactly once')
            page.get_by_role('button', name=f'Ask: {TRY_ASKING}', exact=True).click()
            expect(ask).to_have_value(TRY_ASKING)
            expect(page.locator('.q2p-compose-foot')).to_contain_text(f'It will be listed as “{TRY_ASKING}”, taken from the question.')
            check('the suggested question fills the compose box and the listed name is derived from the question')
            page.get_by_role('button', name='What can I do?', exact=True).click()
            expect(page.get_by_text(HELP_TITLE)).to_be_visible()
            expect(page.get_by_text(HELP_WORDS)).to_be_visible()
            expect(page.get_by_role('button', name='Browse collection →', exact=True)).to_be_visible()
            page.get_by_role('button', name='Continue here', exact=True).click()
            expect(page.get_by_text('TRY ASKING')).to_be_visible()
            check('what can I do today is one panel opened by a link and closed again')

            # -- keeping a question without starting a discussion ----------------
            ask.fill('A useful hypothesis?')
            expect(page.get_by_role('button', name='Save for later', exact=True)).to_be_visible()
            page.get_by_role('button', name='Save for later', exact=True).click()
            expect(page.locator('.q2p-asked')).to_have_text('A useful hypothesis?')
            expect(page.get_by_role('textbox', name='Conversation draft')).to_have_count(0)
            expect(page.get_by_role('textbox', name='Ask a follow-up', exact=True)).to_have_value('')
            expect(page.get_by_role('button', name='Send ↑', exact=True)).to_be_disabled()
            to_past(); manage()
            expect(lens).to_have_value('ent-newtopic211')
            expect(lens).to_contain_text('A useful hypothesis?')
            check('saving a question for later records it, derives its listed name, clears its own draft and starts no discussion')

            # -- asking carries the saved question into Conversation -------------
            go_asking()
            ask.fill('Where does the delay start?')
            page.get_by_role('button', name='Ask →', exact=True).click()
            draft = page.get_by_role('textbox', name='Conversation draft')
            expect(draft).to_have_value('Where does the delay start?')
            check('asking records the question and carries its own saved words into the Conversation')

            # -- the Conversation draft is protected, not replaced ---------------
            draft.fill('Existing draft kept')
            page.get_by_role('button', name='Open Perspectives', exact=True).click()
            go_asking()
            ask.fill('Another question entirely?')
            page.get_by_role('button', name='Ask →', exact=True).click()
            expect(page.get_by_role('status').filter(has_text='already has a different draft')).to_be_visible()
            page.get_by_role('button', name='Open Conversation draft', exact=True).click()
            expect(draft).to_have_value('Existing draft kept')
            page.get_by_role('button', name='Open Perspectives', exact=True).click()
            expect(page.locator('.q2p-asked')).to_have_text('Another question entirely?')
            check('asking protects an existing Conversation draft and says so instead of replacing it')

            # -- the durable rename is a label only ------------------------------
            to_past(); manage()
            page.get_by_role('button', name='Rename this Perspective').click()
            expect(page.get_by_text('A name is a label only.')).to_be_visible()
            page.get_by_role('textbox', name='Perspective name', exact=True).fill('Calibration drift')
            page.get_by_role('button', name='Save name', exact=True).click()
            expect(lens).to_contain_text('Calibration drift')
            open_editor()
            expect(editor).to_have_value('Another question entirely?')
            check('durable rename changes the display name and leaves the saved question')

            # -- one revision draft per Perspective, and no leak ------------------
            editor.fill('Unsaved words for this Perspective')
            # Opening a past question gives the working area straight back to it.
            page.locator('.q2p-row').filter(has_text='Revised twice').click()
            expect(page.locator('.q2p-asked')).to_have_text('Revised twice \U0001f642')
            to_past(); manage(); open_editor()
            expect(editor).to_have_value('Revised twice \U0001f642')
            page.locator('.q2p-row').filter(has_text='Another question entirely?').click()
            expect(page.locator('.q2p-asked')).to_have_text('Another question entirely?')
            to_past(); manage()
            expect(page.get_by_role('button', name='Edit saved question (unsaved edits kept)')).to_be_visible()
            open_editor()
            expect(editor).to_have_value('Unsaved words for this Perspective')
            expect(page.get_by_text('Unsaved edits')).to_be_visible()
            page.get_by_role('button', name='Cancel question edit', exact=True).click()
            check("one Perspective's unsaved revision draft never reaches another")

            # -- retire and resume ------------------------------------------------
            lens.select_option('ent-fixturetopicB')
            open_editor()
            expect(editor).to_have_value('Alternative hypothesis')
            page.get_by_role('button', name='Retire Perspective', exact=True).click()
            expect(lens).to_have_value('')
            page.get_by_role('button', name='Resume Perspective', exact=True).click()
            lens.select_option('ent-fixturetopicB')
            expect(editor).to_have_value('Alternative hypothesis')
            check('retire deselects and resume permits selection, leaving the saved question untouched')

            # -- the selection is durable, not UI state ---------------------------
            page.reload()
            expect(page.locator('.q2p-asked')).to_have_text('Alternative hypothesis')
            to_past(); manage()
            expect(lens).to_have_value('ent-fixturetopicB')
            open_editor()
            expect(editor).to_have_value('Alternative hypothesis')
            check('reload keeps durable selection and saved wording')

            # -- an uncertain edit keeps its original wording, target and key -----
            page.evaluate('perspectiveTest.loseNext = true')
            editor.fill('Original uncertain edit')
            page.get_by_role('button', name='Save question revision', exact=True).click()
            retry = page.get_by_role('button', name='Retry unchanged question action')
            expect(retry).to_be_visible()
            expect(page.get_by_role('status').filter(has_text='Fixture lost acknowledgement')).to_be_visible()
            expect(page.get_by_role('status').filter(has_text='its original wording, target and operation key are kept')).to_be_visible()
            before = page.evaluate('perspectiveTest.edits()')
            page.reload()
            expect(retry).to_be_visible()
            retry.click()
            expect(retry).to_have_count(0)
            to_past(); manage(); open_editor()
            expect(editor).to_have_value('Original uncertain edit')
            assert page.evaluate('perspectiveTest.edits()') == before, {'before': before, 'after': page.evaluate('perspectiveTest.edits()')}
            check('uncertain edit survives reload and retries original target/key exactly once')

            # -- finding a question again -----------------------------------------
            find = page.get_by_role('searchbox', name='Find a question')
            expect(page.locator('.q2p-row')).to_have_count(5)
            find.fill('Calibration drift')
            expect(page.locator('.q2p-row')).to_have_count(1)
            expect(page.locator('.q2p-row')).to_contain_text('Another question entirely?')
            find.fill('no question says this')
            expect(page.locator('.q2p-row')).to_have_count(0)
            expect(page.get_by_text('No saved question matches those words.')).to_be_visible()
            find.fill('')
            expect(page.locator('.q2p-row')).to_have_count(5)
            check('the find box narrows past questions by name and by saved wording, and says when nothing matches')

            # -- history, provenance and the refusal that stays -------------------
            history = page.locator('details[aria-label="Wording history"]')
            history.locator('> summary').click()
            expect(history.locator('> summary')).to_contain_text('Wording history (1)')
            expect(history).to_contain_text('Earlier wording')
            expect(history).to_contain_text('Old first-page wording')
            # The exact earlier version, and where it came from.
            history.locator('li details > summary').first.click()
            expect(history.get_by_role('button', name='View this earlier wording as it was recorded')).to_be_visible()
            expect(history.locator('li details')).to_contain_text('adm-oldrevision')
            expect(history).to_contain_text('All recorded wording for this Perspective is shown.')
            cannot = page.locator('details[aria-label="What this cannot do yet"]')
            cannot.locator('summary').click()
            expect(cannot.get_by_role('button', name='Answer from selected evidence')).to_be_disabled()
            expect(cannot).to_contain_text(BLOCK_REASON)
            seen.append(page.inner_text('body'))
            check('history, provenance and the durable lens live behind Past questions, and grounded answering is still refused in the server’s own words')

            # -- with room: the two columns, and each thing said once -------------
            page.get_by_role('button', name='Back to current →', exact=True).click()
            page.set_viewport_size(ROOMY)
            aside = page.get_by_role('complementary', name='Questions already asked')
            expect(aside).to_be_visible()
            expect(aside.locator('.mgd-h3')).to_have_text('Past questions')
            expect(aside.get_by_role('button', name='All →', exact=True)).to_be_visible()
            expect(aside.get_by_role('button', name='＋ Ask something new', exact=True)).to_be_visible()
            expect(page.locator('.q2p-open-past')).to_be_hidden()
            expect(page.locator('.q2p-main > .mgd-hint')).to_be_hidden()
            words = page.inner_text('body')
            assert words.count(GROUNDED_NOT_YET) == 1, words
            seen.append(words)
            aside.locator('.q2p-aside-row').filter(has_text='Revised twice').click()
            expect(page.locator('.q2p-asked')).to_have_text('Revised twice \U0001f642')
            page.set_viewport_size(COMPACT)
            expect(page.locator('.q2p-open-past')).to_be_visible()
            expect(page.locator('.q2p-main > .mgd-hint')).to_be_visible()
            expect(aside).to_be_hidden()
            check('with room the questions already asked stand beside the work, each thing is said once, and the compact surface restores both')

            # -- nothing grounded was prepared, qualified or collected ------------
            assert not page.evaluate("perspectiveTest.calls.some(c => /prepare|finalize|reconcile|collection/.test(c.tail))")
            check('no grounded preparation qualification or collection calls')
            # The owner's language review (ent-3191baeb33d2 §2) covers every word
            # of the mounted panel, not only the controls this harness drives.
            for shown in seen:
                assert 'inquir' not in shown.lower(), shown
            labels = page.eval_on_selector_all('[aria-label], [title], [placeholder]',
                "els => els.map(e => [e.getAttribute('aria-label'), e.getAttribute('title'), e.getAttribute('placeholder')].filter(Boolean).join(' '))")
            assert labels and not [l for l in labels if 'inquir' in l.lower()], labels
            check('nothing the mounted Perspectives panel shows or announces reads as inquiry')
            assert not errors, errors
            check('zero browser errors')
            skipped.append('SupportingItems (Explore supporting items ↗ / ← Back to answer): asserted present, not opened -- opening it unmounts the harness with "Cannot read properties of undefined (reading \'filter\')", because `retainedItems` reads snapshot().results and the view subscribes to resource.subscribe, neither of which this fixture resource carries')
            skipped.append('Send ↑ follow-up (a branch write) and Record challenge: asserted present and enabled, not pressed -- the fixture has no branch or challenge route')
            browser.close()
        print(json.dumps({'passed': len(checks), 'failed': 0, 'skipped': len(skipped), 'errors': 0, 'checks': checks, 'skipped_detail': skipped}), flush=True)
    finally:
        stopped = subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'], capture_output=True)
        if stopped.returncode and proc.poll() is None:
            proc.terminate()
        proc.wait(timeout=15)
