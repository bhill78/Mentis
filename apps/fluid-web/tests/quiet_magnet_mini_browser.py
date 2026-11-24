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
            def selector(call):
                return call['body'].get('magnet_context')
            reset()
            box.focus()
            expect(mini.get_by_role('button',name='Refresh conversation',exact=True)).to_have_count(0)
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
            # An empty reply aim is visible in the regular Composer, cancellable,
            # and is dropped when the card is put away.
            mini.get_by_role('button',name='Reply',exact=True).nth(1).click()
            expect(bar.locator('.fx-composer [data-destination]')).to_contain_text('Replying to')
            expect(bar.get_by_role('button',name='not a reply',exact=True)).to_be_visible()
            bar.get_by_role('button',name='not a reply',exact=True).click()
            expect(bar.get_by_role('button',name='not a reply',exact=True)).to_have_count(0)
            mini.get_by_role('button',name='Reply',exact=True).nth(1).click()
            view.locator('#toggle').click();view.locator('#toggle').click()
            expect(bar.get_by_role('button',name='not a reply',exact=True)).to_have_count(0)
            box.fill('unrelated after empty reply')
            split(bar);view.get_by_role('menuitemradio',name='Record only',exact=False).click()
            bar.locator('.fw-send-main').click();view.wait_for_function('window.review.calls.length===1')
            check('replies_to' not in view.evaluate('window.review.calls[0].body'),'an empty restored reply target is dropped before an unrelated send')

            # Reply plus an intentional draft survives collapse/reopen and reload.
            reset()
            mini.get_by_role('button',name='Reply',exact=True).nth(1).click()
            box.fill('mini reply draft')
            view.locator('#toggle').click();view.locator('#toggle').click()
            expect(box).to_have_value('mini reply draft')
            expect(bar.locator('.fx-composer [data-destination]')).to_contain_text('Replying to')
            expect(bar.get_by_role('button',name='not a reply',exact=True)).to_be_visible()
            view.reload()
            expect(box).to_have_value('mini reply draft')
            expect(bar.locator('.fx-composer [data-destination]')).to_contain_text('Replying to')
            expect(bar.get_by_role('button',name='not a reply',exact=True)).to_be_visible()
            check(True,'reply and draft survive collapse/reopen and reload without main collision')
            bar.locator('.fw-send-main').click();view.wait_for_function('window.review.calls.length===1')
            expect(box).to_have_value('')
            check(view.evaluate('window.review.calls[0].body.replies_to')=='ent-reviewpost211','mini post names its exact held reply target')
            # NOTHING PROPOSES ANSWERING FROM THE COLLECTION, and no standing
            # administrative line stands above the messages (owner §§2, 6).
            reset()
            check(bar.get_by_role('button',name='What Mentis reads',exact=False).count()==0,'the composer offers no reading choice')
            check(bar.get_by_role('menuitemradio',name='Discuss retained collection',exact=False).count()==0,'and no retained-collection affordance')
            check('Grounded execution off' not in bar.inner_text(),'and no execution-status badge beside the words')
            check('Selected collection evidence is recorded separately' not in mini.inner_text(),'no standing disclosure above the Conversation')
            # EXACTLY THE WORDS THAT WERE TYPED, spaces and all, with no part
            # the owner did not write (owner §5).
            box.fill('  a spaced note  ')
            split(bar)
            view.get_by_role('menuitemradio',name='Record only',exact=False).click()
            bar.locator('.fw-send-main').click();view.wait_for_function('window.review.calls.length===1')
            noted=view.evaluate('window.review.calls[0]')
            check(noted['body']['text']=='  a spaced note  ','the recorded words keep the author\'s own whitespace')
            check(noted['body']['parts']==[{'type':'text','text':'  a spaced note  '}],'and are the whole of the parts: nothing generated is written as the author\'s')
            check(noted['body']['magnet_context']['version']==1 and noted['body']['magnet_context']['perspective'] is None and noted['body']['magnet_context']['references']==[],'record-only passes the actual preparation hook and carries its explicit empty selector')
            # A deliberately attached immutable reference is a selector beside
            # the exact words. This synthetic HTTP check grants no artifact reach.
            reset()
            view.evaluate("window.review.context({ref:'adm-reviewfile11',kind:'file',label:'Setup notes'},[{id:'adm-reviewfile11',kind:'file',value:{digest:'a'.repeat(64)}}])")
            expect(bar.get_by_text('Setup notes',exact=True)).to_be_visible()
            box.fill('  about these notes  ')
            bar.locator('.fw-send-main').click();view.wait_for_function('window.review.calls.length===1')
            chipped=view.evaluate('window.review.calls[0]')
            check(chipped['body']['text']=='  about these notes  ' and chipped['body']['parts']==[{'type':'text','text':'  about these notes  '}],'a visible reference chip contributes neither label nor separator nor file part to authored words')
            check(chipped['body']['magnet_context']['references']==[{'kind':'artifact','ref':'adm-reviewfile11','version':None,'digest':'a'*64}],'the chip carries its exact recorded identity separately')
            # Removing it and reopening the card keeps that deliberate removal.
            reset()
            view.evaluate("window.review.context({ref:'adm-reviewfile11',kind:'file',label:'Setup notes'},[{id:'adm-reviewfile11',kind:'file',value:{digest:'a'.repeat(64)}}])")
            box.fill('  without those notes  ')
            bar.get_by_role('button',name='Remove Setup notes from this message',exact=True).click()
            view.locator('#toggle').click();view.locator('#toggle').click()
            expect(box).to_have_value('  without those notes  ')
            expect(bar.get_by_role('button',name='Remove Setup notes from this message',exact=True)).to_have_count(0)
            bar.locator('.fw-send-main').click();view.wait_for_function('window.review.calls.length===1')
            unchipped=view.evaluate('window.review.calls[0]')
            check(unchipped['body']['magnet_context']['references']==[] and unchipped['body']['magnet_context']['perspective'] is None,'removed context remains absent after card reopen and reaches no selector')
            # Diagnostic only: the external chip is not a Draft part, so D's
            # generic empty-draft gate currently prevents a chip-only button send.
            # Record this unfinished owned seam; do not bless it as a passed check.
            reset()
            view.evaluate("window.review.context({ref:'adm-reviewfile11',kind:'file',label:'Setup notes'},[{id:'adm-reviewfile11',kind:'file',value:{digest:'a'.repeat(64)}}])")
            chip_only_disabled=bar.locator('.fw-send-main').is_disabled()
            print(f'Observed incomplete D seam: external chip-only Send disabled={chip_only_disabled}',flush=True)
            # WHAT THE MESSAGE IS ABOUT travels as the explicit selector, and
            # with nothing attached it says exactly that.
            reset()
            box.fill('What can this Magnet collect?')
            bar.locator('.fw-send-main').click();view.wait_for_function('window.review.calls.length===1')
            ordinary=view.evaluate('window.review.calls[0]')
            chosen=selector(ordinary)
            check(sorted(chosen or {})==['configuration_digest','mode','perspective','references','version'],'the send carries the complete version 1 selector')
            check(chosen['version']==1 and chosen['mode']=='ordinary','its version and mode are the published ones')
            check(chosen['perspective'] is None and chosen['references']==[],'nothing attached is said explicitly, never inferred')
            check(len(chosen['configuration_digest'])==64 and all(c in '0123456789abcdef' for c in chosen['configuration_digest']),'and the configuration it was written against is named by digest')
            check('_magnetAssistance' not in json.dumps(ordinary['body']),'no client-only instruction marker is sent any more')
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
            expect(mini.get_by_text('Fixture agent reply',exact=False)).to_be_visible()
            check(view.evaluate('window.review.reads')>=2,'a durable pulse for this Conversation brings an agent reply in without Refresh')
            # A REFERENCE AN AGENT WROTE IS MENTIS'S OWN REFERENCE now that the
            # card draws Mentis's own post: the shared component, given the
            # card's opener, so the citation is read as evidence in the card.
            ref=mini.locator('.q2-body .ref').first
            expect(ref).to_be_visible()
            ref.click()
            check(view.evaluate('window.review.evidence')=='ent-aaaa1111bbbb' and not view.evaluate('!!window.review.full'),'reply evidence click uses card callback without navigation')
            mini.get_by_role('button',name='1 reply',exact=False).first.click()
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
            check(view.evaluate('window.review.create===undefined'),'the first send uses the atomic request receipt, with no separate creation write')
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
            # -- WHAT THE CARD DOES NOW IT DRAWS MENTIS'S OWN CONVERSATION ----
            # (owner §5 and §6: one conversation experience, the composer back
            # to its minimal state, a reply that says what it answers, and a
            # message found in the search opened where it actually is.)
            view.evaluate('window.review.brain="review-instance";window.review.reply=false;window.review.notify()')
            reset()
            quiet=".q2-magnet-composer .fx-composer"
            check(mini.locator('.q2-post').count()>=2,'a post in the card is Mentis’s own post')
            check(mini.locator('.q2-prose strong').first.inner_text()=='strong','its words are drawn by the shared Prose: Markdown is Markdown')
            check(mini.locator('.q2-byline .avatar').count()>=2 and mini.locator('.q2-toolbar').count()>=2,'with the shared byline and the shared post actions')
            # A reply says which post it answers, in the Magnet's own words.
            mini.get_by_role('button',name='Reply',exact=True).first.click()
            destination=bar.locator('.fx-composer [data-destination]')
            expect(destination).to_contain_text('Replying to')
            check('#1' in destination.inner_text() and 'fixture' in destination.inner_text(),'a reply names the post it answers and who wrote it, not "a post"')
            bar.get_by_role('button',name='not a reply',exact=True).click()
            # The composer is back to its minimal state once the message is away.
            box.fill('a message that is going away')
            check(not view.evaluate(f"document.querySelector('{quiet}').classList.contains('fw-quiet')"),'the composer is expanded while a message is being written')
            bar.locator('.fw-send-main').click()
            view.wait_for_function('window.review.calls.length===1')
            view.wait_for_function(f"document.querySelector('{quiet}').classList.contains('fw-quiet')")
            check(True,'the composer returns to its minimal state once the message is recorded')
            # A message found in the search: a reply inside a thread, in no page
            # the card has read. Its thread is named by the server, read, and
            # mounted here, and the position is kept in the Conversation's place.
            reset()
            expect(mini.get_by_text('Actual fixture thread reply',exact=False)).to_have_count(0)
            view.evaluate("window.review.target('ent-reviewpost311')")
            expect(mini.get_by_text('Actual fixture thread reply',exact=False)).to_be_visible()
            kept=view.evaluate('window.review.snapshot().places.Conversation.scroll')
            check(isinstance(kept,(int,float)),f'the exact message is mounted and its position kept in the place ({kept})')
            # Having arrived, the target is let go (Part C's §2): a later reader
            # is not pulled back to it, and the first Escape has something to do.
            view.wait_for_function('window.review.snapshot().searchTarget===null')
            check(view.evaluate('window.review.snapshot().searchTarget')is None,'the search target is released once the message has been positioned')
            check(view.get_by_text('Actual fixture thread reply',exact=False).count()>0,'and what it asked for stays mounted after it is released')
            (OUT/'trace.json').write_text(json.dumps({'ordinary':normal,'noted':noted,'chipped':chipped,'removed_chip':unchipped,'chip_only_send_disabled':chip_only_disabled,'assistance':ordinary,'original':original,'retry':retried,'first_send':first,'checks':checks},indent=2),encoding='utf-8')
            check(not errors,f'no browser JS errors: {errors}')
            browser.close()
        print(f'Completed: {checks} checks passed; 0 failed, 0 skipped, 0 errors',flush=True)
    finally:
        proc.terminate();proc.wait(timeout=10)
        print(f'own Vite PID {proc.pid} stopped; returncode={proc.returncode}',flush=True)
