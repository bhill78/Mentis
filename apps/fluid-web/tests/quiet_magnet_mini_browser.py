"""Real Composer in headless Edge, synthetic HTTP only, no Brain or agent.

The card's composer is its persistent footer bar (ComposerBar), not a control
inside the Conversation view: every locator below is scoped to the bar, which is
where the owner now writes from on every tab.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request
from playwright.sync_api import sync_playwright, expect
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--out',type=Path,required=True)
# 5481 by convention. Another run of this same fixture may hold it (the port is
# claimed exclusively); this run then takes a port of its own and says which.
parser.add_argument('--port',type=int,default=5481)
args=parser.parse_args()
OUT=args.out
PORT=args.port
OUT.mkdir(parents=True,exist_ok=True)
print(f'fixture port {PORT}',flush=True)
checks=0
def check(value,message):
    global checks
    assert value,message
    checks+=1
    print(f'PASS {checks}: {message}',flush=True)
with (OUT/'vite.log').open('w',encoding='utf-8') as log:
    proc=subprocess.Popen(['node','node_modules/vite/bin/vite.js','--config','tests/quiet_magnet_mini_vite.mjs'],cwd=ROOT,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW,
                          env={**os.environ,'MAGNET_MINI_FIXTURE_PORT':str(PORT)})
    print(f'own Vite PID {proc.pid}',flush=True)
    try:
        for _ in range(100):
            if proc.poll() is not None:raise RuntimeError('own Vite exited')
            try:
                urllib.request.urlopen(f'http://127.0.0.1:{PORT}/tests/quiet_magnet_mini.html',timeout=1).close();break
            except OSError:time.sleep(.1)
        else:raise RuntimeError('Vite did not become ready')
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='msedge',headless=True)
            view=browser.new_page(viewport={'width':1000,'height':1000})
            errors=[];view.on('pageerror',lambda e:(errors.append(str(e)),print('BROWSER ERROR',str(e),flush=True)))
            url=f'http://127.0.0.1:{PORT}/tests/quiet_magnet_mini.html'
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
            # NO PERSISTENT WAY OUT OF THE MAGNET (owner §3), on the ordinary
            # opening of a Magnet that has a Conversation of its own.
            check(mini.get_by_role('button',name='Open full Conversation',exact=False).count()==0 and mini.locator('.q2-mini-external').count()==0,'the Conversation view draws no persistent Open full Conversation link')
            check(mini.locator('.q2-mini-head-actions').count()==0,'and leaves no empty actions row where it stood')
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
            check(view.url==url,'mini send preserves main draft and leaves the surrounding page where it was')
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
            # THE SEAM A OBSERVED AS INCOMPLETE IS CLOSED HERE (integration of
            # D's `sendsNothing(draft, asking?.attached)` with A's send path):
            # a record the owner deliberately attached is a message with
            # something in it, so the press is live with nothing typed, and the
            # words stay exactly the owner's -- which here is no words at all.
            reset()
            view.evaluate("window.review.context({ref:'adm-reviewfile11',kind:'file',label:'Setup notes'},[{id:'adm-reviewfile11',kind:'file',value:{digest:'a'.repeat(64)}}])")
            box.focus()
            expect(bar.locator('.fw-send-main')).to_be_visible()
            chip_only_disabled=bar.locator('.fw-send-main').is_disabled()
            check(not chip_only_disabled,'an intentionally attached record can be sent on its own: Send is live with no words typed')
            check(box.input_value()=='','and nothing was written into the words to make it so')
            bar.locator('.fw-send-main').click();view.wait_for_function('window.review.calls.length===1')
            chip_only_external=view.evaluate('window.review.calls[0]')
            check(chip_only_external['body']['magnet_context']['references']==[{'kind':'artifact','ref':'adm-reviewfile11','version':None,'digest':'a'*64}],
                  'and the wordless message carries that record, at the identity the chip stood for')
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
            check(view.evaluate('window.review.evidence')=='ent-aaaa1111bbbb' and view.url==url,'reply evidence click uses card callback without navigation')
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
            # §3 ON THE STATE THE PRODUCT PATH FAILED ON (adm-8850ac2b2bfa): the
            # first send has made the Conversation, so this view is now the one
            # whose header drew a persistent "Open full Conversation →" above the
            # posts. It draws no way out of the card, and the page around it has
            # not moved.
            expect(mini.get_by_text('Synthetic post 1.',exact=True)).to_be_visible()
            check(mini.get_by_role('button',name='Open full Conversation',exact=False).count()==0 and mini.locator('.q2-mini-external').count()==0,'a Magnet that owns its Conversation after the first send draws no persistent Open full Conversation link')
            check(mini.locator('.q2-mini-head-actions').count()==0,'and its header holds no actions row at all with nowhere to go back to')
            check(view.url==url+'?no-own','the first send left the surrounding page exactly where it was')
            # THE WAY BACK IS THE OPPOSITE THING AND STAYS: contextual, drawn in
            # the place the persistent link used to stand, naming where it goes.
            view.evaluate("window.review.wayBack('Perspectives')")
            back=mini.locator('.q2-mini-head-actions')
            expect(back).to_be_visible()
            check(back.get_by_role('button',name='Return to Perspectives',exact=False).count()==1,'the contextual way back is drawn where the persistent link was')
            check(back.get_by_role('button',name='Open full Conversation',exact=False).count()==0,'and it is the only thing in that row')
            view.evaluate("window.review.wayBack('All','search')")
            check(mini.get_by_role('button',name='Return to search results',exact=False).count()==1,'a search result keeps its own way back to the results')
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
            # -- WHAT THIS MESSAGE IS ABOUT, AND WHICH VERSION OF IT ----------
            # (owner §§2 and 5; contract §§3-4.) A durable lens is selected, so
            # the card attaches the saved question the next message is about --
            # at the version it read. The chip is not a part of the draft, so
            # this is also where a wordless message has to be sendable.
            LENS,QUESTION_ONE,DIGEST_ONE='ent-reviewlens11','adm-reviewq11111','1'*64
            reset()
            view.evaluate('window.review.selectLens()')
            expect(bar.locator('.q2-magnet-chip')).to_be_visible()
            chip=view.evaluate('window.review.snapshot().context')
            check(chip['ref']==LENS and chip['version']==QUESTION_ONE and chip['digest']==DIGEST_ONE,
                  'the chip stands for the exact saved question version the card read, not for its identifier alone')
            check(chip.get('text')is None,'and it carries the reference and that version only, never captured content')
            view.locator('#toggle').click();view.locator('#toggle').click()
            expect(bar.locator('.q2-magnet-chip')).to_be_visible()
            check(view.evaluate('window.review.snapshot().context.digest')==DIGEST_ONE,
                  'the version it stands for survives the footer being unmounted and mounted again')
            # A WORDLESS MESSAGE WHOSE WHOLE POINT IS WHAT IT IS ABOUT.
            box.focus()
            send=bar.locator('.fw-send-main')
            expect(send).to_be_visible()
            check(not send.is_disabled(),'Send is live on an intentionally attached question with no words typed')
            check(box.input_value()=='','and nothing was written into the words to make it so')
            send.click()
            view.wait_for_function('!!window.review.carried')
            chip_only=view.evaluate('window.review.carried')
            check(chip_only['context']['digest']==DIGEST_ONE,
                  'the wordless press leaves this part’s composer, carrying that exact version')
            chip_only_said=bar.inner_text()
            # INTEGRATED, THE WORDLESS SEND ACTUALLY COMPLETES, and the
            # reference that went is let go (`retireContext`, A's file). On D's
            # own branch nothing could be sent without words, so the chip stayed
            # where it was and the check read it there. The invariant is the same
            # either way -- no version is substituted and no words are invented --
            # and this is what the owner sees here: the message took its question
            # with it, and the next one starts from no choice rather than from
            # the last one.
            view.wait_for_function('window.review.snapshot().context===null')
            check(box.input_value()=='' and view.evaluate('window.review.snapshot().contextSuppressed')is False,
                  'the recorded wordless message took its question with it, and the composer starts the next one from no choice')
            # A QUESTION REVISED UNDER THE COMPOSER IS NOT THIS MESSAGE'S
            # QUESTION. The record and every fresh read of it move on together;
            # only the chip's own version says what the owner actually read.
            reset()
            view.evaluate('window.review.selectLens()')
            expect(bar.locator('.q2-magnet-chip')).to_be_visible()
            box.fill('What has been collected so far?')
            before=view.evaluate('window.review.calls.length')
            view.evaluate('window.review.revise()')
            bar.locator('.fw-send-main').click()
            expect(bar.get_by_text('The saved question changed',exact=False)).to_be_visible()
            check(view.evaluate('window.review.calls.length')==before,
                  'a question revised since it was attached stops the send: nothing at all is sent')
            expect(box).to_have_value('What has been collected so far?')
            check(view.evaluate('window.review.snapshot().context.digest')==DIGEST_ONE,
                  'the words and the chip are kept, still standing for the version the owner read')
            # AND THE SAME MESSAGE GOES when the chip IS the version the record
            # holds: one request, naming that exact question version.
            reset()
            view.evaluate('window.review.selectLens()')
            expect(bar.locator('.q2-magnet-chip')).to_be_visible()
            box.fill('How do I configure a magnet?')
            bar.locator('.fw-send-main').click()
            view.wait_for_function('window.review.calls.length===1')
            asked=view.evaluate('window.review.calls[0]')
            chosen=selector(asked)
            check(chosen['perspective']=={'id':LENS,'question_ref':QUESTION_ONE,'question_digest':DIGEST_ONE},
                  'an explicit contextual reference travels as that exact version, and is usable')
            check(chosen['references']==[] and chosen['mode']=='ordinary','and nothing else is attached, under no other mode')
            # The words are the owner's. The only prose here that was not typed
            # is `conversation.ts`'s own reference sentence, which is A's file
            # and is removed on A's branch: split on it, and what is left must
            # be exactly what was typed, before and after that lands.
            authored=asked['body']['text'].split('\n\nIn reference to')[0]
            check(authored=='How do I configure a magnet?','the recorded words are the words that were typed')
            # AN INTENTIONAL REMOVAL STAYS REMOVED, through the card being put
            # away and opened again with that lens still selected.
            reset()
            view.evaluate('window.review.selectLens()')
            expect(bar.locator('.q2-magnet-chip')).to_be_visible()
            bar.get_by_role('button',name='Remove',exact=False).click()
            expect(bar.locator('.q2-magnet-chip')).to_have_count(0)
            check(view.evaluate('window.review.snapshot().context')is None and view.evaluate('window.review.snapshot().contextSuppressed')is True,
                  'removing the chip removes what the message carries, and records that it was the owner who did it')
            check(bar.get_by_text('This message carries nothing with it',exact=False).is_visible(),
                  'and the composer says so, where the chip was')
            view.locator('#toggle').click();view.locator('#toggle').click()
            expect(box).to_be_visible()
            check(view.evaluate('window.review.snapshot().context')is None,
                  'reopening the card does not put it back: the active lens does not defeat a removal')
            box.fill('an ordinary question, carrying nothing')
            bar.locator('.fw-send-main').click()
            view.wait_for_function('window.review.calls.length===1')
            removed=selector(view.evaluate('window.review.calls[0]'))
            check(removed['perspective']is None and removed['references']==[],
                  'and the message it then sends reaches nothing, said explicitly')
            (OUT/'trace.json').write_text(json.dumps({'ordinary':normal,'noted':noted,'chipped':chipped,'removed_chip':unchipped,
              'chip_only_send_disabled':chip_only_disabled,'chip_only_external':chip_only_external,
              'assistance':ordinary,'original':original,'retry':retried,'first_send':first,
              'chip_only_carried':chip_only,'chip_only_bar_text':chip_only_said,'attached_question':asked['body'].get('magnet_context'),'checks':checks},indent=2),encoding='utf-8')
            check(not errors,f'no browser JS errors: {errors}')
            browser.close()
        print(f'Completed: {checks} checks passed; 0 failed, 0 skipped, 0 errors',flush=True)
    finally:
        proc.terminate();proc.wait(timeout=10)
        print(f'own Vite PID {proc.pid} stopped; returncode={proc.returncode}',flush=True)
