"""Real Composer in headless Edge, synthetic HTTP only, no Brain or agent.

The card's composer is its persistent footer bar (ComposerBar), not a control
inside the Conversation view: every locator below is scoped to the bar, which is
where the owner now writes from on every tab.
"""
import argparse
import json
from pathlib import Path
import subprocess
import time
import urllib.request
from playwright.sync_api import sync_playwright, expect
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--out',type=Path,required=True)
OUT=parser.parse_args().out
OUT.mkdir(parents=True,exist_ok=True)
checks=0
def check(value,message):
    global checks
    assert value,message
    checks+=1
    print(f'PASS {checks}: {message}',flush=True)
with (OUT/'vite.log').open('w',encoding='utf-8') as log:
    proc=subprocess.Popen(['node','node_modules/vite/bin/vite.js','--config','tests/quiet_magnet_mini_vite.mjs'],cwd=ROOT,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
    print(f'own Vite PID {proc.pid}',flush=True)
    try:
        for _ in range(100):
            if proc.poll() is not None:raise RuntimeError('own Vite exited')
            try:
                urllib.request.urlopen('http://127.0.0.1:5481/tests/quiet_magnet_mini.html',timeout=1).close();break
            except OSError:time.sleep(.1)
        else:raise RuntimeError('Vite did not become ready')
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='msedge',headless=True)
            view=browser.new_page(viewport={'width':1000,'height':1000})
            errors=[];view.on('pageerror',lambda e:(errors.append(str(e)),print('BROWSER ERROR',str(e),flush=True)))
            url='http://127.0.0.1:5481/tests/quiet_magnet_mini.html'
            card=view.locator('.q2-magnet-card')
            mini=view.locator('.q2-mini')          # the Conversation view
            bar=view.locator('.q2-magnet-composer')  # the one persistent composer
            box=bar.locator('textarea'); main=view.locator('#main-composer textarea')
            def reset(suffix=''):
                view.goto(url+suffix)
                view.evaluate('localStorage.clear(); sessionStorage.clear()')
                view.reload()
                expect(view.get_by_text('Synthetic post 1.',exact=True)).to_be_visible() if not suffix else None
            def split(scope):
                scope.get_by_role('button',name='Choose what sending does',exact=True).click()
            def reads():
                bar.get_by_role('button',name='What Mentis reads',exact=False).click()
            reset()
            box.focus()
            expect(mini.get_by_role('button',name='Refresh conversation',exact=True)).to_be_visible()
            # ONE COMPOSER, IN THE FOOTER. The Conversation view has none, and no
            # select is rendered in the composer anywhere.
            check(card.locator('textarea').count()==1 and box.count()==1,'the card has exactly one composer, and it is the footer bar')
            check(mini.locator('textarea').count()==0 and mini.locator('select').count()==0,'the Conversation view holds no composer and no select')
            check(bar.locator('select').count()==0 and bar.locator('.fw-send-caret').count()==1,'no select in the composer; the real split control is its send choice')
            check(mini.get_by_text('nobody carries it',exact=False).is_visible(),'actual Work read shown inside Magnet')
            # The seed is a fallback, not a pin (opr-8274edd84e06): the main
            # button reads Ask Mentis until the owner chooses otherwise.
            box.fill('ordinary mini post')
            check(bar.locator('.fw-send-main').inner_text().strip().startswith('Ask Mentis'),'a fresh Magnet message is Ask Mentis, not pinned to Record only')
            main.fill('shared main draft kept at older reading position')
            split(bar)
            expect(view.get_by_role('menu',name='Ways to send')).to_be_visible()
            check(view.get_by_role('menuitemradio',name='Record only',exact=False).is_visible(),'real split menu offers Record only')
            view.get_by_role('menuitemradio',name='Record only',exact=False).click()
            check(bar.locator('.fw-send-main').inner_text().strip().startswith('Record'),'the per-message choice retargets the button it is about')
            bar.locator('.fw-send-main').click()
            view.wait_for_function('window.review.calls.length===1')
            expect(box).to_have_value('')
            normal=view.evaluate('window.review.calls[0]')
            check(normal['path']=='/fluid/api/requests' and normal['body']['from']=={'magnet':'mag-review'} and normal['body']['action']=='record-only' and normal['body']['dispatch']==[],'ordinary post is record-only and bound to own Magnet route')
            check(normal['headers']['X-Mentis-Brain']=='review-corpus@review-instance','write carries confirmed full Brain identity')
            expect(main).to_have_value('shared main draft kept at older reading position')
            check(view.url==url and not view.evaluate('!!window.review.full'),'mini send preserves main draft and navigation')
            # The next message starts from the fallback again, not from the last
            # message's choice.
            box.fill('a second message')
            check(bar.locator('.fw-send-main').inner_text().strip().startswith('Ask Mentis'),'the send choice is for that message only and resets')
            box.fill('')
            # Default (non-adapter) Composer keeps its original draft lifecycle.
            view.reload()
            expect(main).to_have_value('shared main draft kept at older reading position')
            expect(box).to_have_value('')
            check(True,'shared Composer without adapter keeps its own session draft on reload')
            # Reply, collapse/reopen and full page reload keep the mini intent.
            mini.get_by_role('button',name='Reply',exact=True).nth(1).click()
            box.fill('mini reply draft')
            view.locator('#toggle').click();view.locator('#toggle').click()
            expect(box).to_have_value('mini reply draft')
            expect(bar.get_by_text('Replying to @fixture #2',exact=True)).to_be_visible()
            view.reload()
            expect(box).to_have_value('mini reply draft')
            expect(bar.get_by_text('Replying to @fixture #2',exact=True)).to_be_visible()
            check(True,'reply and draft survive collapse/reopen and reload without main collision')
            bar.locator('.fw-send-main').click();view.wait_for_function('window.review.calls.length===1')
            expect(box).to_have_value('')
            check(view.evaluate('window.review.calls[0].body.replies_to')=='ent-reviewpost211','mini post names its exact held reply target')
            # WHAT MENTIS READS: both items reachable, the choice kept for this
            # Magnet, and each branch of the request produced unchanged.
            reset()
            reads()
            menu=view.get_by_role('menu',name='What Mentis reads')
            expect(menu).to_be_visible()
            check(menu.get_by_role('menuitemradio').count()==2,'the reading choice is two radio items')
            check(menu.get_by_text('This choice is kept for this Magnet',exact=False).is_visible(),'the reading choice says it is kept, not per message')
            box.fill('What is in the retained batch?')
            reads() if not menu.is_visible() else None
            menu.get_by_role('menuitemradio',name='Discuss retained collection',exact=False).click()
            bar.locator('.fw-send-main').click();view.wait_for_function('window.review.calls.length===1')
            retained_call=view.evaluate('window.review.calls[0]')
            # Ask Mentis carries the bounded grounding wording in the asking
            # Turn's own words; a dispatched recipient carries it on its spec.
            retained_words=''.join(q.get('text','') for q in retained_call['body']['parts'])
            check(retained_call['body']['parts'][-1]['ref']=='adm-reviewbatch1','the retained choice attaches the exact retained Admission to the asking Turn')
            check('Read it with read_artifact before answering' in retained_words,'the retained branch keeps its bounded grounding wording unchanged')
            # Kept for this Magnet, not for the message: it survives the card
            # being put away and brought back. Across a reload it is
            # `workingState`'s persisted `assistanceMode` (H1's, asserted by
            # quiet_magnet_read_unit.ts); this harness's resource is synthetic
            # and holds no device storage, so that is not asserted here.
            view.locator('#toggle').click();view.locator('#toggle').click()
            check('Discuss retained collection' in bar.get_by_role('button',name='What Mentis reads',exact=False).inner_text(),'the reading choice is kept for this Magnet, not reset per message')
            reads()
            view.get_by_role('menu',name='What Mentis reads').get_by_role('menuitemradio',name='Ordinary configuration',exact=False).click()
            box.fill('What can this Magnet collect?')
            bar.locator('.fw-send-main').click();view.wait_for_function('window.review.calls.length===2')
            ordinary=view.evaluate('window.review.calls[1]')
            check(not [q for q in ordinary['body']['parts'] if q.get('type')=='file'],'ordinary assistance attaches no collection file')
            check('Ordinary Magnet assistance' in ordinary['body']['parts'][-1]['text'],'the ordinary branch keeps its own wording unchanged')
            # Real @ palette, narrow Float, Operations and actual bodyOf choices.
            reset();view.set_viewport_size({'width':430,'height':950})
            box.fill('What was retained? @Fixture')
            people=view.get_by_role('listbox',name='people')
            expect(people).to_be_visible()
            option=people.get_by_role('option').filter(has_text='@FixtureAgent').first
            expect(option).to_be_visible();option.locator('.fc-pmain').click()
            expect(bar.locator('.fc-pill')).to_have_count(1)
            check(True,'real participant palette adds Operations participant pill')
            # Alt+O opens the established Operations panel for the selected recipient.
            box.press('Alt+o')
            ops=view.get_by_role('dialog',name='Operations for @FixtureAgent',exact=True)
            expect(ops).to_be_visible()
            rect=ops.bounding_box()
            check(rect['x']>=0 and rect['x']+rect['width']<=431,'Operations Float fits narrow viewport outside card clipping')
            ops.locator('[data-row="authority"]').click()
            view.get_by_role('menuitemradio',name='May coordinate this work',exact=False).click()
            view.get_by_role('button',name='Close Operations',exact=True).click()
            split(bar)
            menu=view.get_by_role('menu',name='Ways to send')
            rect=menu.bounding_box()
            check(rect['x']>=0 and rect['x']+rect['width']<=431,'split send Float fits narrow viewport')
            # Escape restores the split opener; selection already asks participant.
            view.keyboard.press('Escape')
            raw_question=box.input_value()
            view.evaluate('window.review.mode="hold"')
            bar.locator('.fw-send-main').click();view.wait_for_function('window.review.calls.length===1')
            original=view.evaluate('window.review.calls[0]')
            check(original['body']['action']=='ask-participant' and original['body']['addressed_to']==['ent-reviewagent1'],'real palette selection reaches addressed request')
            dispatch=original['body']['dispatch'][0]
            check(dispatch['coordinate'] is True and dispatch['runtime'] is None,'Operations Work permission and automatic runtime preserved from bodyOf')
            view.reload()
            expect(box).to_have_value(raw_question)
            check(view.evaluate('window.review.calls.length')==0,'reload restores frozen unresolved attempt without automatic resend')
            bar.get_by_role('button',name='Send again under the same key',exact=True).click()
            view.wait_for_function('window.review.calls.length===1')
            retried=view.evaluate('window.review.calls[0]')
            check(retried==original,'deliberate reload retry sends identical body, permissions, retained evidence, Brain and op key')
            expect(box).to_have_value('')
            # In-flight success updates a new mount of the real Composer.
            view.evaluate('window.review.mode="hold"')
            box.fill('late success after card remount')
            bar.locator('.fw-send-main').click();view.wait_for_function('window.review.calls.length===2')
            view.locator('#toggle').click();view.locator('#toggle').click()
            expect(box).to_have_value('late success after card remount')
            view.evaluate('window.review.resolve()')
            expect(box).to_have_value('')
            check(True,'optional Composer lifecycle receives late success after remount and clears retired draft')
            view.evaluate('window.review.reply=true')
            mini.get_by_role('button',name='Refresh conversation',exact=True).click()
            expect(mini.get_by_text('Fixture agent reply',exact=False)).to_be_visible()
            mini.get_by_role('button',name='Inspect adm-reviewbatch1 inside Magnet',exact=True).click()
            check(view.evaluate('window.review.evidence')=='adm-reviewbatch1' and not view.evaluate('!!window.review.full'),'reply evidence click uses card callback without navigation')
            mini.get_by_role('button',name='Show 1 reply',exact=True).first.click()
            expect(mini.get_by_text('Actual fixture thread reply',exact=False)).to_be_visible()
            check(view.evaluate('window.review.threadReads')==1,'thread controls still read actual thread endpoint')
            # ORDINARY ASSISTANCE ON AN EMPTY COLLECTION: a Magnet with no
            # Conversation of its own still has a composer, and the first send
            # makes the Conversation and records the message in it.
            reset('?no-own')
            view.set_viewport_size({'width':1000,'height':1000})
            expect(box).to_be_visible()
            check(bar.get_by_text('Sending makes one and records the message in it',exact=False).is_visible(),'the bar says what the first send will do')
            box.fill('Ordinary help before anything is collected.')
            bar.locator('.fw-send-main').click()
            view.wait_for_function('window.review.calls.length===1')
            first=view.evaluate('window.review.calls[0]')
            check(view.evaluate('window.review.create.body.op')=='magnet-conversation:mag-review','the first send creates the own Conversation under the stable explicit operation')
            check(first['body']['from']=={'magnet':'mag-review'} and first['body']['text'].startswith('Ordinary help'),'the first send records the owner words in the Conversation it just made')
            expect(box).to_have_value('')
            check(view.evaluate('window.review.canWrite')is True,'nothing dead-ends on conversation-required')
            # The explicit Create control is still there, and capability still rules.
            reset('?no-own')
            expect(mini.get_by_role('button',name='Create own Conversation',exact=True)).to_be_visible()
            mini.get_by_role('button',name='Create own Conversation',exact=True).click()
            expect(box).to_be_visible()
            view.evaluate('window.review.canWrite=false;window.review.notify()')
            expect(bar.locator('textarea')).to_have_count(0)
            check(True,'withdrawn capability removes the writable composer')
            view.evaluate('window.review.canWrite=true;window.review.notify()')
            box.fill('must not cross Brain instance')
            view.evaluate('window.review.brain="another-instance"')
            bar.locator('.fw-send-main').click()
            expect(bar.get_by_text('Nothing was sent:',exact=False).first).to_be_visible()
            check(view.evaluate('window.review.calls.length')==0,'changed Brain refuses before any mini write')
            (OUT/'trace.json').write_text(json.dumps({'ordinary':normal,'retained':retained_call,'assistance':ordinary,'original':original,'retry':retried,'first_send':first,'checks':checks},indent=2),encoding='utf-8')
            check(not errors,f'no browser JS errors: {errors}')
            browser.close()
        print(f'Completed: {checks} checks passed; 0 failed, 0 skipped, 0 errors',flush=True)
    finally:
        proc.terminate();proc.wait(timeout=10)
        print(f'own Vite PID {proc.pid} stopped; returncode={proc.returncode}',flush=True)
