"""Retake the tour images using a fresh disposable Brain.

python -m mentis.bootstrap.capture_welcome --output <directory> [--dist ui/dist]
Requires Playwright and Chromium (or Edge), and a built Mentis UI.
No agent is dispatched. Scratch contains a labelled sample answer. The two
handoffs the tour teaches (Send to on a comment, Address on a recorded post)
are pressed for real; the dispatch they queue is caught here and counted, so
nothing runs. The runtime list is what this machine reports.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import tempfile
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import patch

import mentis.api as api
from mentis.bootstrap.new_brain import setup
from mentis.conversation import text
from mentis import web
from mentis.web import scratch as web_scratch


def capture(output, dist=None):
    from playwright.sync_api import sync_playwright
    output = pathlib.Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    if dist:
        web.STATIC = pathlib.Path(dist).resolve()
    if not (web.STATIC / 'index.html').is_file():
        raise ValueError('Build ui/dist first, or supply --dist <built UI>')
    # No path to an existing corpus is accepted, and no production port is used.
    with tempfile.TemporaryDirectory(prefix='mentis-tour-') as tmp:
        root = pathlib.Path(tmp) / 'brain'
        c = api.create_corpus(str(root))
        result = setup(c, '@NewOwner')
        # Somebody elsewhere in the Brain, for the "bring them in" pictures.
        api.brain(c).conversations.resolve_participant(
            '@Reviewer', about='a sample participant, not in the tour yet')
        c.close()
        queued, checks = [], {}
        guide = '@Caretaker'  # a fresh Brain's carrier
        state = web._State(str(root))
        handler = type('TourHandler', (web._Handler,), {'state': state})
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f'http://127.0.0.1:{server.server_port}'
        try:
            # Use the actual Scratch route, with a fixture answerer. Only this
            # disposable server is addressed; no runtime process is started.
            selection = SimpleNamespace(runtime='sample', model=None,
                                        requested_effort=None, because=['tour sample'])
            answer = SimpleNamespace(
                reported='Scratch is for quick questions about your Brain. It stays '
                         'temporary unless you choose Sidebar or Keep. This is a '
                         'sample answer for the tour.',
                exit_code=0, error=None, actual_model=None, actual_effort=None,
                tool_calls=(), usage={})
            with patch.object(web_scratch, '_choose_runtime',
                              lambda *args: (selection, None)), \
                 patch.object(state.agents, 'agents_answer_once', return_value=answer), \
                 patch.object(web_scratch, 'answer_soon', web_scratch.answer):
                request = urllib.request.Request(base + '/api/scratch',
                    data=json.dumps({
                        'owner': result['baseline']['owner'],
                        'parts': [text('What is Scratch for?')],
                        'context': {'surface': 'brain', 'label': 'Daily Briefing',
                                    'invoked_at': 0, 'timezone': 'UTC',
                                    'incomplete': False, 'refs': []}
                    }).encode(), headers={'Content-Type': 'application/json',
                                             'X-Mentis-Client': '1'},
                    method='POST')
                with urllib.request.urlopen(request) as response:
                    sid = json.load(response)['scratch']
            # A handoff pressed below queues its dispatch here, and nothing runs.
            with patch.object(web, 'dispatch_soon',
                              lambda st, **kw: queued.append(kw['participant'])), \
                 sync_playwright() as p:
                try:
                    browser = p.chromium.launch(channel='msedge')
                except Exception:
                    browser = p.chromium.launch()
                try:
                    pg = browser.new_page(viewport={'width': 1440, 'height': 1000})
                    def shot(name):
                        # Let drawer transitions and lazy thumbnail discovery settle.
                        pg.wait_for_timeout(500)
                        pg.wait_for_function('''() => [...document.images].every(img => {
                            const r = img.getBoundingClientRect();
                            const visible = r.width && r.height && r.top < innerHeight
                                && r.bottom > 0 && r.left < innerWidth && r.right > 0;
                            return !visible || (img.complete && img.naturalWidth > 0);
                        })''')
                        pg.evaluate('document.fonts.ready')
                        pg.screenshot(path=str(output / f'{name}.png'))
                    def tour():
                        pg.goto(base + '/#/c/' + result['tour']['conversation'])
                        pg.locator('article[data-turn]').first.wait_for()
                    pg.goto(base + '/#/brain')
                    pg.get_by_text('Welcome to Mentis', exact=True).first.wait_for()
                    shot('lobby')
                    tour()
                    pg.get_by_role('button', name='Other ways to send').click()
                    pg.get_by_role('menu', name='Ways to send').wait_for()
                    shot('composer-send')
                    pg.keyboard.press('Escape')
                    pg.goto(base + '/#/brain/scratch/' + sid)
                    pg.locator('.scratch-thread').wait_for()
                    pg.locator('.scratch-msg.mentis.done .turn-body').wait_for()
                    shot('scratch')
                    pg.get_by_role('button', name=re.compile('^Sidebar')).first.click()
                    pg.get_by_role('dialog').wait_for()
                    shot('sidebar')
                    tour()
                    pg.get_by_role('button', name=re.compile('^Topics')).first.click()
                    pg.locator('.topic-row').filter(has_text='Passages, reactions').click()
                    article = pg.locator('article[data-turn]').filter(
                        has_text='Try one on this sentence.').first
                    article.scroll_into_view_if_needed()
                    pg.evaluate('''() => {
                        const nodes = document.querySelectorAll('article .turn-body');
                        for (const body of nodes) {
                            const w = document.createTreeWalker(body, NodeFilter.SHOW_TEXT);
                            let n;
                            while ((n = w.nextNode())) {
                                const i = n.data.indexOf('Try one on this sentence.');
                                if (i < 0) continue;
                                const r = document.createRange();
                                r.setStart(n, i); r.setEnd(n, i + 25);
                                const s = getSelection(); s.removeAllRanges(); s.addRange(r);
                                document.dispatchEvent(new Event('selectionchange'));
                                return;
                            }
                        }
                        throw new Error('tour passage missing');
                    }''')
                    # The rendered selection has its own passage controls.
                    pg.wait_for_timeout(300)
                    shot('passage-bar')
                    pg.keyboard.press('Escape')
                    pg.locator('.topic-row').filter(has_text='Topics').click()
                    shot('topics')
                    tour()
                    pg.get_by_role('button', name=re.compile('^Media')).first.click()
                    shot('media')
                    pg.goto(base + '/#/c/' + result['tour']['deep_dives'][0])
                    pg.locator('.conv-lineage').wait_for()
                    pg.locator('.conv-lineage').click()
                    pg.locator('.anc-origin').wait_for()
                    shot('deep-dive')

                    def post(words):
                        a = pg.locator('article[data-turn]').filter(has_text=words).first
                        a.scroll_into_view_if_needed()
                        a.hover()
                        return a
                    # Bringing somebody in: the composer's @ list, by name.
                    tour()
                    box = pg.locator('textarea').last
                    box.click()
                    box.type('@Rev')
                    pg.locator('.pick-group').filter(has_text='elsewhere in this brain').wait_for()
                    shot('picker-names')
                    box.press('ArrowRight')
                    pg.wait_for_function("() => !document.body.innerText.includes("
                                         "'asking this machine what it can run')",
                                         timeout=120000)
                    # Use the existing narrow layout: grouped meters wrap below
                    # runtime names rather than squeezing them into ellipses.
                    pg.set_viewport_size({'width': 540, 'height': 1000})
                    shot('picker-runtimes')
                    checks['runtime_labels_legible'] = pg.locator('.pick-label').evaluate_all(
                        '(labels) => labels.every(x => x.scrollWidth <= x.clientWidth)')
                    assert checks['runtime_labels_legible'], 'runtime name truncated'
                    pg.set_viewport_size({'width': 1440, 'height': 1000})
                    checks['runtimes_listed'] = pg.locator('.pick-row .pick-label').all_inner_texts()
                    box.press('ArrowLeft')
                    # Picking a name from elsewhere joins it; clearing the draft
                    # leaves it joined, and nothing was asked.
                    pg.locator('.pick-row').filter(has_text='@Reviewer').first.dispatch_event('mousedown')
                    pg.get_by_role('button', name='Ask @Reviewer').wait_for()
                    box.fill('')
                    checks['dispatched_by_joining'] = len(queued)
                    # Who somebody is: the card behind a name.
                    tour()
                    post('No. They are four separate things').get_by_text(
                        guide, exact=True).first.click()
                    pg.locator('.who-facts').first.wait_for()
                    shot('who-card')
                    pg.keyboard.press('Escape')
                    # Send to, from the sample comment on a passage.
                    tour()
                    post('Your comment is the instruction.')
                    pg.locator('.anc-mark[aria-label*="Your comment is the instruction."]'
                               ).first.dispatch_event('click')
                    pg.locator('.anc-dots').first.click()
                    pg.locator('.handoff-menu').wait_for()
                    checks['send_to_offers'] = pg.locator('.handoff-row').all_inner_texts()
                    shot('send-to')
                    pg.locator('.handoff-row').filter(has_text=guide).first.click()
                    pg.locator('.anc-sent').first.wait_for()
                    checks['send_to_shows'] = pg.locator('.anc-sent').first.inner_text()
                    # Address, on the sample post that was only recorded.
                    tour()
                    # The sample is a reply: open its thread with "1 reply".
                    post('without copying it into a new message').locator(
                        '.thread-open').first.click()
                    pg.locator('.thread article[data-turn]').filter(
                        has_text='Sample, sent with Record only').first.wait_for()
                    sample = pg.locator('.thread article[data-turn]').filter(
                        has_text='Sample, sent with Record only').first
                    sample.hover()
                    sample.locator('[data-act=address]').click()
                    pg.locator('.pop-why').wait_for()
                    checks['address_offers'] = pg.locator('.pop-row .pop-name').all_inner_texts()
                    pg.locator('.pop-why').fill('Please answer in two sentences.')
                    shot('address')
                    pg.locator('.pop-row').filter(has_text=guide).first.click()
                    pg.get_by_text(f'Request queued for {guide}').first.wait_for()
                    checks['address_note'] = f'Request queued for {guide}'
                    checks['dispatches_caught'] = list(queued)
                    (output / 'capture.json').write_text(json.dumps({
                        'base': base, 'seed': result, 'scratch_answer': 'sample',
                        'dist': str(web.STATIC), 'checks': checks},
                        indent=2, ensure_ascii=False), 'utf-8')
                finally:
                    browser.close()
        finally:
            server.shutdown()
            server.server_close()
            state.corpus.close()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', required=True)
    ap.add_argument('--dist')
    args = ap.parse_args(argv)
    capture(args.output, args.dist)


if __name__ == '__main__':
    main()
