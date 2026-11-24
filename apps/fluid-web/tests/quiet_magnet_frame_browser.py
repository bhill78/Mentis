"""The real frame with the persistent composer in its footer slot, headless Edge.

Two properties, both reported as blocking in the H2 review of 89846b28:

B1  a success received while the footer is NOT mounted (the card closed, or
    settings open) still moves the card to its Conversation, keeps an exact way
    back, lets go of the reference that went with the sent words and of nothing
    the owner has attached since.
B2  the persistent composer and the frame together leave a reading area that can
    actually be read, at 320x640, 390x844 and on the desktop, with the send
    control and the collect control still inside the card.

Synthetic HTTP only: no Brain, no agent, no server of the app's own.
"""
import argparse
import json
from pathlib import Path
import subprocess
import time
import urllib.request
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--out', type=Path, required=True)
OUT = parser.parse_args().out
OUT.mkdir(parents=True, exist_ok=True)
URL = 'http://127.0.0.1:5482/tests/quiet_magnet_frame.html'
# A readable reading area: the approved preview's own floor for the card's view.
FLOOR = 70
checks = 0
notes = []


def check(value, message, evidence=None):
    global checks
    notes.append({'check': message, 'evidence': evidence})
    assert value, f'{message} :: {evidence}'
    checks += 1
    print(f'PASS {checks}: {message}', flush=True)


with (OUT / 'vite.log').open('w', encoding='utf-8') as log:
    proc = subprocess.Popen(['node', 'node_modules/vite/bin/vite.js', '--config', 'tests/quiet_magnet_frame_vite.mjs'],
                            cwd=ROOT, stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
    print(f'own Vite PID {proc.pid}', flush=True)
    try:
        for _ in range(100):
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
            view = browser.new_page(viewport={'width': 1440, 'height': 900})
            errors = []
            view.on('pageerror', lambda e: (errors.append(str(e)), print('BROWSER ERROR', str(e), flush=True)))
            card = view.locator('.q2-magnet-card')
            bar = view.locator('.q2-magnet-composer')
            box = bar.locator('textarea')
            reading = view.locator('.q2-magnet-view')

            def reset(suffix=''):
                view.goto(URL + suffix)
                view.evaluate('localStorage.clear(); sessionStorage.clear()')
                view.reload()
                expect(box).to_be_visible()

            def state():
                return view.evaluate('window.frame.state()')

            def tab(name):
                """Go to a place by name. Posts and Files are the collection's
                type filters now (owner request §1); the places themselves, and
                everything these checks read out of `places`, are unchanged."""
                if name in ('All', 'Posts', 'Files'):
                    view.get_by_role('tab', name='Collection', exact=False).click()
                    view.get_by_role('button', name='Everything' if name == 'All' else name, exact=True).click()
                else:
                    view.get_by_role('tab', name=name, exact=True).click()

            def inspect(ref):
                view.evaluate(f"""window.frame.resource.update({{places: {{...window.frame.state().places,
                  Files: {{...window.frame.state().places.Files, inspected: '{ref}'}}}}}})""")

            # -- B1: the answer lands while the card is closed ----------------
            reset()
            tab('Files')
            inspect('adm-context111')
            view.evaluate("window.frame.mode = 'hold'")
            box.fill('late success while closed')
            expect(bar.locator('.q2-magnet-chip')).to_be_visible()
            check(state()['context']['ref'] == 'adm-context111', 'the first words attach the reference the owner is reading')
            bar.locator('.fw-send-main').click()
            view.wait_for_function('window.frame.calls.length === 1')
            view.get_by_role('button', name='Close Magnet', exact=True).click()
            expect(box).to_have_count(0)
            check(True, 'closing the card unmounts the footer, so no bar is there to receive the answer')
            view.evaluate('window.frame.resolve()')
            view.wait_for_function('!!window.frame.store().sent')
            view.locator('.q2-magnet-puck').click()
            expect(box).to_be_visible()
            view.wait_for_timeout(100)
            after = state()
            check(after['tab'] == 'Conversation', 'the card moves to its Conversation when the footer is next mounted',
                  {'tab': after['tab'], 'sent': view.evaluate('window.frame.store().sent')})
            check(after['context'] is None and after['contextSuppressed'] is False,
                  'the reference that went with the sent words is let go, and suppression with it', after['context'])
            check(after['carried'] is None, 'the note that said an act was owing is consumed')
            check(after['returnRoute']['tab'] == 'Files'
                  and after['returnRoute']['placeSnapshot']['inspected'] == 'adm-context111',
                  'the way back is the view the message was written from, with what was open in it',
                  after['returnRoute'])
            expect(box).to_have_value('')
            view.locator('#return-view').click()
            view.wait_for_timeout(100)
            check(state()['tab'] == 'Files' and state()['places']['Files']['inspected'] == 'adm-context111',
                  'Return goes back to it')
            # and the next message inherits nothing of it
            tab('Summary')
            box.fill('next unrelated message')
            bar.locator('.fw-send-main').click()
            view.wait_for_function('window.frame.calls.length === 2')
            second = view.evaluate('window.frame.calls[1].body')
            check('adm-context111' not in json.dumps(second),
                  'a message sent afterwards carries no part of the sent reference', second.get('text'))

            # -- B1: the reading position of the view it was sent from --------
            # Taken at the press, because by the time the answer lands the card
            # may have been closed and reopened and the view read again from
            # nothing. (No inspection open here: with one, `places.remember`
            # writes the inspected position into the list's -- the frame's own
            # behaviour, unchanged by this work.)
            reset()
            tab('Files')
            reading.evaluate('el => el.scrollTop = 450')
            view.wait_for_timeout(100)
            check(reading.evaluate('el => el.scrollTop') == 450, 'the Files list is read at 450')
            view.evaluate("window.frame.mode = 'hold'")
            box.fill('sent from part way down the list')
            bar.locator('.fw-send-main').click()
            view.wait_for_function('window.frame.calls.length === 1')
            view.get_by_role('button', name='Close Magnet', exact=True).click()
            view.evaluate('window.frame.resolve()')
            view.wait_for_function('!!window.frame.store().sent')
            view.locator('.q2-magnet-puck').click()
            expect(box).to_be_visible()
            view.wait_for_timeout(100)
            check(state()['returnRoute']['placeSnapshot']['scroll'] == 450,
                  'the way back keeps the reading position the message was written from',
                  state()['returnRoute'])
            view.locator('#return-view').click()
            view.wait_for_timeout(150)
            check(state()['tab'] == 'Files' and reading.evaluate('el => el.scrollTop') == 450,
                  'Return puts the owner back at that position', reading.evaluate('el => el.scrollTop'))

            # -- B1: the answer lands while settings is open ------------------
            reset()
            tab('Summary')
            view.evaluate("window.frame.mode = 'hold'")
            box.fill('send while settings is open')
            bar.locator('.fw-send-main').click()
            view.wait_for_function('window.frame.calls.length === 1')
            view.get_by_role('button', name='Magnet settings', exact=True).click()
            expect(box).to_have_count(0)
            view.evaluate('window.frame.resolve()')
            view.wait_for_function('!!window.frame.store().sent')
            view.get_by_role('button', name='Magnet settings', exact=True).click()
            expect(box).to_be_visible()
            view.wait_for_timeout(100)
            check(state()['tab'] == 'Conversation' and state()['overlay'] is None,
                  'a success received with settings open is not lost either', state()['tab'])

            # -- B1: what the owner typed under the unresolved send is theirs --
            reset()
            tab('Files')
            inspect('adm-context111')
            view.evaluate("window.frame.mode = 'hold'")
            box.fill('question about the first reference')
            expect(bar.locator('.q2-magnet-chip')).to_be_visible()
            bar.locator('.fw-send-main').click()
            view.wait_for_function('window.frame.calls.length === 1')
            # While it is unresolved the words are held (the composer is
            # disabled under an unresolved send, which is the app's own
            # behaviour), but a reference can still be attached by name: this is
            # what "Discuss this evidence" writes from an inspected item.
            view.evaluate("window.frame.resource.update({context: {ref: 'adm-context222', kind: 'file', label: 'what I am asking about now'}, contextSuppressed: false})")
            view.evaluate('window.frame.resolve()')
            view.wait_for_function('!!window.frame.store().sent')
            view.wait_for_timeout(100)
            protected = state()
            check(protected['context'] == {'ref': 'adm-context222', 'kind': 'file', 'label': 'what I am asking about now'},
                  'a reference attached under the unresolved send belongs to the next message and stays', protected['context'])
            check(protected['tab'] == 'Conversation', 'and the recorded message still moved the card')
            expect(box).to_have_value('')
            box.fill('a different question, about the reference I attached since')
            expect(bar.locator('.q2-magnet-chip')).to_be_visible()
            bar.locator('.fw-send-main').click()
            view.wait_for_function('window.frame.calls.length === 2')
            kept = view.evaluate('window.frame.calls[1].body')
            check('adm-context222' in json.dumps(kept) and 'adm-context111' not in json.dumps(kept),
                  'that next message carries its own reference and not the sent one', kept.get('text'))

            # -- B2: content dominates the normal collapsed card -------------
            view.set_viewport_size({'width': 2048, 'height': 927})
            reset()
            tab('Posts')
            check('fw-quiet' in (bar.locator('.fx-composer').get_attribute('class') or ''),
                  'the default Magnet composer is the regular composer\'s collapsed single-line state')

            def collapsed_geometry(label):
                fit = view.evaluate("""() => {
                  const card = document.querySelector('.q2-magnet-card')
                  const content = document.querySelector('.q2-magnet-view')
                  const cb = card.getBoundingClientRect()
                  return { card: Math.round(cb.height), view: content.clientHeight,
                    ratio: Math.round(content.clientHeight / cb.height * 1000) / 1000 }
                }""")
                fit['state'] = label
                check(.60 <= fit['ratio'] <= .75,
                      f'collapsed {label} card gives about two-thirds of its height to content at 2048x927', fit)
                return fit

            collapsed = [collapsed_geometry('compact')]
            view.get_by_role('button', name='Expand Magnet', exact=True).click()
            collapsed.append(collapsed_geometry('expanded'))

            # -- B2: a reading area that can be read, at every size -----------
            geometry = []
            for width, height in [(1440, 700), (390, 844), (320, 640)]:
                for fullness in ['typed', 'chip', 'sent']:
                    view.set_viewport_size({'width': width, 'height': height})
                    reset()
                    tab('Summary')
                    if fullness == 'chip':
                        view.evaluate("window.frame.resource.update({context: {ref: 'adm-context111', kind: 'file', label: 'a retained evidence file with a long label'}})")
                    box.fill('ordinary question')
                    expect(box).to_have_value('ordinary question')
                    if fullness == 'sent':
                        bar.locator('.fw-send-main').click()
                        view.wait_for_function('!!window.frame.store().sent')
                        tab('Summary')
                        box.fill('ordinary question')
                    fit = view.evaluate("""() => {
                      const box = (s) => { const e = document.querySelector(s); if (!e) return null
                        const b = e.getBoundingClientRect(); return { top: Math.round(b.top), bottom: Math.round(b.bottom) } }
                      const el = document.querySelector('.q2-magnet-view')
                      return { view: el.clientHeight, scrollable: el.scrollHeight > el.clientHeight,
                        card: box('.q2-magnet-card'), send: box('.q2-magnet-composer .fw-send-main'),
                        collect: box('.q2-magnet-collection .q2-magnet-primary') }
                    }""")
                    fit['viewport'] = f'{width}x{height}'
                    fit['state'] = fullness
                    geometry.append(fit)
                    view.screenshot(path=str(OUT / f'frame-{width}x{height}-{fullness}.png'))
                    check(fit['view'] >= FLOOR and fit['scrollable'],
                          f'the reading area is readable and scrolls at {width}x{height} ({fullness})', fit)
                    check(fit['send']['bottom'] <= fit['card']['bottom'] and fit['send']['top'] >= fit['card']['top'],
                          f'the send control is inside the card at {width}x{height} ({fullness})', fit['send'])
                    check(fit['collect']['bottom'] <= fit['card']['bottom'],
                          f'the collect control is still inside the card at {width}x{height} ({fullness})', fit['collect'])
            view.set_viewport_size({'width': 1440, 'height': 900})
            (OUT / 'frame.json').write_text(json.dumps({'collapsed': collapsed, 'geometry': geometry, 'checks': notes}, indent=2), encoding='utf-8')
            check(not errors, f'no browser JS errors: {errors}')
            browser.close()
        print(f'Completed: {checks} checks passed; 0 failed, 0 skipped, 0 errors', flush=True)
    finally:
        proc.terminate()
        proc.wait(timeout=10)
        print(f'own Vite PID {proc.pid} stopped; returncode={proc.returncode}', flush=True)
