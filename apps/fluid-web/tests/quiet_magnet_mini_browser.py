"""Own synthetic fetch fixture only; foreground, headless, no Brain/backend."""
import argparse
import json
from pathlib import Path
import subprocess
import time
import urllib.request
from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--out',type=Path,default=ROOT/'review-evidence')
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
            view=browser.new_page(viewport={'width':1000,'height':900})
            errors=[];view.on('pageerror',lambda e:errors.append(str(e)))
            url='http://127.0.0.1:5481/tests/quiet_magnet_mini.html'
            def reset():
                view.goto(url)
                view.evaluate('localStorage.clear()')
                view.reload()
                expect(view.get_by_text('Synthetic post 1.',exact=True)).to_be_visible()
                view.get_by_label('Action',exact=True).select_option('note')
            reset();expect(view.get_by_text('Synthetic post 1.',exact=True)).to_be_visible()
            check(view.get_by_text('nobody carries it',exact=False).is_visible(),'rendered Work names unassigned request')
            view.locator('textarea').fill('same browser words')
            view.get_by_role('button',name='Record note',exact=True).click()
            view.wait_for_function('window.review.calls.length===1')
            view.locator('#toggle').click();view.locator('#toggle').click()
            expect(view.locator('textarea')).to_have_value('same browser words')
            check(True,'in-flight remount initially restores draft')
            view.evaluate('window.review.resolve()')
            expect(view.locator('textarea')).to_have_value('')
            check(view.get_by_role('button',name='Record note',exact=True).is_disabled(),'F1: late success clears remounted composer and disables Send')
            view.locator('form').evaluate('(form)=>form.requestSubmit()')
            expect(view.locator('textarea')).to_have_value('')
            trace=view.evaluate('({calls:window.review.calls,records:[...window.review.records]})')
            check(len(trace['calls'])==1,'F1: further submit sends no duplicate request')
            check(len(trace['records'])==1,'F1: idempotent synthetic door holds exactly one record')
            (OUT/'f1-trace.json').write_text(json.dumps(trace,indent=2),encoding='utf-8')

            reset();expect(view.get_by_text('Synthetic post 1.',exact=True)).to_be_visible()
            view.locator('textarea').fill('keep for another reply')
            view.get_by_role('button',name='Record note',exact=True).click();view.wait_for_function('window.review.calls.length===1')
            view.get_by_role('button',name='Reply',exact=True).nth(1).click()
            check(view.get_by_text('Replying to @fixture #2',exact=True).is_visible(),'B2: new reply target selected during pending send')
            view.evaluate('window.review.resolve()')
            expect(view.locator('textarea')).to_have_value('keep for another reply')
            check(view.get_by_text('Replying to @fixture #2',exact=True).is_visible(),'F2: completion preserves new reply target and words')
            expect(view.get_by_role('button',name='Record note',exact=True)).to_be_enabled()
            view.get_by_role('button',name='Record note',exact=True).click()
            view.wait_for_function('window.review.calls.length===2')
            trace=view.evaluate('({calls:window.review.calls,records:[...window.review.records]})')
            check(trace['calls'][1]['body']['replies_to']=='ent-reviewpost211' and len(trace['records'])==2,'F2: explicit reply records new target under a distinct key')

            reset();expect(view.get_by_text('Synthetic post 1.',exact=True)).to_be_visible()
            view.locator('textarea').fill('remounted reply intent')
            view.get_by_role('button',name='Record note',exact=True).click();view.wait_for_function('window.review.calls.length===1')
            view.locator('#toggle').click();view.locator('#toggle').click()
            view.get_by_role('button',name='Reply',exact=True).nth(1).click()
            view.evaluate('window.review.resolve()')
            expect(view.locator('textarea')).to_have_value('remounted reply intent')
            check(view.get_by_text('Replying to @fixture #2',exact=True).is_visible(),'F2: remounted retarget survives original success')

            reset();expect(view.get_by_text('Synthetic post 1.',exact=True)).to_be_visible()
            earlier=view.get_by_role('button',name='Earlier posts (30 older)',exact=True)
            earlier.click();view.wait_for_function('typeof window.review.holdOlder==="function"')
            view.get_by_role('button',name='Refresh conversation',exact=True).click()
            expect(view.get_by_role('button',name='Refresh conversation',exact=True)).to_be_enabled()
            view.evaluate('window.review.holdOlder()')
            expect(view.get_by_role('button',name='Earlier posts (30 older)',exact=True)).to_be_enabled()
            check(True,'F3: Refresh releases Earlier posts after old response')
            view.get_by_role('button',name='Earlier posts (30 older)',exact=True).click()
            view.wait_for_function('window.review.olderCalls===2')
            view.evaluate('window.review.holdOlder()')
            expect(view.get_by_role('button',name='Earlier posts (30 older)',exact=True)).to_have_count(0)
            check(True,'F3: another earlier page can be read normally')

            reset();expect(view.get_by_text('Synthetic post 1.',exact=True)).to_be_visible()
            view.get_by_role('button',name='Show 1 reply',exact=True).first.click()
            view.wait_for_function('window.review.threadCalls===1')
            view.get_by_role('button',name='Close thread',exact=True).click()
            view.get_by_role('button',name='Show 1 reply',exact=True).first.click()
            view.wait_for_function('window.review.threadCalls===2')
            view.evaluate('window.review.threadResolvers[1]("New replies")')
            expect(view.get_by_text('New replies',exact=True)).to_be_visible()
            view.evaluate('window.review.threadResolvers[0]("Stale replies")')
            check(view.get_by_text('New replies',exact=True).is_visible() and view.get_by_text('Stale replies',exact=True).count()==0,'F4: same-root reopen rejects late old replies')
            view.get_by_role('button',name='Refresh conversation',exact=True).click()
            view.wait_for_function('window.review.threadCalls===3')
            view.get_by_role('button',name='Refresh conversation',exact=True).click()
            view.wait_for_function('window.review.threadCalls===4')
            view.evaluate('window.review.threadResolvers[3]("Newest refresh replies")')
            expect(view.get_by_text('Newest refresh replies',exact=True)).to_be_visible()
            view.evaluate('window.review.threadResolvers[2]("Stale refresh replies")')
            check(view.get_by_text('Newest refresh replies',exact=True).is_visible() and view.get_by_text('Stale refresh replies',exact=True).count()==0,'F4: overlapping refresh rejects late old replies')
            reset()
            view.get_by_label('Action',exact=True).select_option('ask')
            view.locator('textarea').fill('What was retained?')
            agent=view.get_by_label('Agent',exact=True)
            expect(agent.locator('option')).to_have_count(3)
            check(agent.input_value()=='' and view.get_by_role('button',name='Ask agent',exact=True).is_disabled(),
                  'all-undeclared catalogue offers non-owner recipients without choosing one')
            check('@FixtureAgent (no runtime default; automatic runtime)' in agent.inner_text(),
                  'undeclared recipient option explains automatic runtime honestly')
            agent.select_option('ent-reviewagent1')
            view.get_by_role('button',name='Ask agent',exact=True).click()
            view.wait_for_function('window.review.calls.length===1')
            original=view.evaluate('window.review.calls[0]')
            check(original['path']=='/fluid/api/requests' and original['body']['action']=='ask-participant','grounded ask uses the agent routing door')
            check(original['body']['parts'][1]['type']=='file' and original['body']['parts'][1]['ref']=='adm-reviewbatch1','asking Turn carries the exact retained Admission')
            check(original['body']['dispatch'][0]['runtime'] is None
                  and original['body']['addressed_to']==['ent-reviewagent1'],
                  'explicit recipient uses runtime:null automatic dispatch')
            view.reload()
            expect(view.locator('textarea')).to_have_value('What was retained?')
            view.wait_for_function('typeof window.review === "object"')
            check(view.evaluate('window.review.calls.length')==0,'refresh restores uncertain intent without resending it')
            view.get_by_role('button',name='Send again under the same key',exact=True).click()
            view.wait_for_function('window.review.calls.length===1')
            retried=view.evaluate('window.review.calls[0]')
            check(retried['body']==original['body'],'deliberate retry after refresh sends identical question, artifact, recipient and operation')
            view.evaluate('window.review.resolve()')
            expect(view.locator('textarea')).to_have_value('')
            view.get_by_role('button',name='Inspect retained collection',exact=True).click()
            check(view.evaluate('window.review.evidence')=='adm-reviewbatch1' and not view.evaluate('!!window.review.full'),'evidence callback stays inside the Magnet without Full Conversation navigation')
            check(not errors,f'no browser JS errors: {errors}')
            browser.close()
        print(f'Completed: {checks} correction checks passed; 0 failed, 0 skipped, 0 errors',flush=True)
    finally:
        proc.terminate();proc.wait(timeout=10)
        print(f'own Vite PID {proc.pid} stopped; returncode={proc.returncode}',flush=True)
