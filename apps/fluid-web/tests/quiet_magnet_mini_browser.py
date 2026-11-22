"""Real Composer in headless Edge, synthetic HTTP only, no Brain or agent."""
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
            mini=view.locator('.q2-mini'); box=mini.locator('textarea'); main=view.locator('#main-composer textarea')
            def reset(suffix=''):
                view.goto(url+suffix)
                view.evaluate('localStorage.clear(); sessionStorage.clear()')
                view.reload()
                expect(view.get_by_text('Synthetic post 1.',exact=True)).to_be_visible() if not suffix else None
            def split(scope):
                scope.get_by_role('button',name='Choose what sending does',exact=True).click()
            reset()
            box.focus()
            expect(mini.get_by_role('button',name='Refresh conversation',exact=True)).to_be_visible()
            check(mini.locator('select[aria-label="Action"]').count()==0 and mini.locator('.fw-send-caret').count()==1,'real Composer split control replaces forum Action form')
            check(mini.get_by_text('nobody carries it',exact=False).is_visible(),'actual Work read shown inside Magnet')
            main.fill('shared main draft kept at older reading position')
            box.fill('ordinary mini post')
            split(mini)
            expect(view.get_by_role('menu',name='Ways to send')).to_be_visible()
            check(view.get_by_role('menuitemradio',name='Record only',exact=False).is_visible(),'real split menu offers Record only')
            view.get_by_role('menuitemradio',name='Record only',exact=False).click()
            mini.locator('.fw-send-main').click()
            view.wait_for_function('window.review.calls.length===1')
            expect(box).to_have_value('')
            normal=view.evaluate('window.review.calls[0]')
            check(normal['path']=='/fluid/api/requests' and normal['body']['from']=={'magnet':'mag-review'} and normal['body']['action']=='record-only' and normal['body']['dispatch']==[],'ordinary post is record-only and bound to own Magnet route')
            check(normal['headers']['X-Mentis-Brain']=='review-corpus@review-instance','write carries confirmed full Brain identity')
            expect(main).to_have_value('shared main draft kept at older reading position')
            check(view.url==url and not view.evaluate('!!window.review.full'),'mini send preserves main draft and navigation')
            # Default (non-adapter) Composer keeps its original draft lifecycle.
            view.reload()
            expect(main).to_have_value('shared main draft kept at older reading position')
            expect(box).to_have_value('')
            check(True,'shared Composer without adapter keeps its own session draft on reload')
            # Reply, compact/reopen and full page reload keep the mini intent.
            mini.get_by_role('button',name='Reply',exact=True).nth(1).click()
            box.fill('mini reply draft')
            view.locator('#toggle').click();view.locator('#toggle').click()
            expect(box).to_have_value('mini reply draft')
            expect(mini.get_by_text('Replying to @fixture #2',exact=True)).to_be_visible()
            view.reload()
            expect(box).to_have_value('mini reply draft')
            expect(mini.get_by_text('Replying to @fixture #2',exact=True)).to_be_visible()
            check(True,'reply and draft survive compact/reopen and reload without main collision')
            mini.locator('.fw-send-main').click();view.wait_for_function('window.review.calls.length===1')
            expect(box).to_have_value('')
            check(view.evaluate('window.review.calls[0].body.replies_to')=='ent-reviewpost211','mini post names its exact held reply target')
            # Real @ palette, narrow Float, Operations and actual bodyOf choices.
            reset();view.set_viewport_size({'width':430,'height':950})
            box.fill('What was retained? @Fixture')
            people=view.get_by_role('listbox',name='people')
            expect(people).to_be_visible()
            option=people.get_by_role('option').filter(has_text='@FixtureAgent').first
            expect(option).to_be_visible();option.locator('.fc-pmain').click()
            expect(mini.locator('.fc-pill')).to_have_count(1)
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
            split(mini)
            menu=view.get_by_role('menu',name='Ways to send')
            rect=menu.bounding_box()
            check(rect['x']>=0 and rect['x']+rect['width']<=431,'split send Float fits narrow viewport')
            # Escape restores the split opener; selection already asks participant.
            view.keyboard.press('Escape')
            raw_question=box.input_value()
            view.evaluate('window.review.mode="hold"')
            mini.locator('.fw-send-main').click();view.wait_for_function('window.review.calls.length===1')
            original=view.evaluate('window.review.calls[0]')
            check(original['body']['action']=='ask-participant' and original['body']['addressed_to']==['ent-reviewagent1'],'real palette selection reaches addressed request')
            dispatch=original['body']['dispatch'][0]
            check(dispatch['coordinate'] is True and dispatch['runtime'] is None,'Operations Work permission and automatic runtime preserved from bodyOf')
            check(original['body']['parts'][-1]['ref']=='adm-reviewbatch1' and 'read_artifact' in dispatch['work'],'exact retained Admission appended to asking Turn with bounded grounding')
            view.reload()
            expect(box).to_have_value(raw_question)
            check(view.evaluate('window.review.calls.length')==0,'reload restores frozen unresolved attempt without automatic resend')
            mini.get_by_role('button',name='Send again under the same key',exact=True).click()
            view.wait_for_function('window.review.calls.length===1')
            retried=view.evaluate('window.review.calls[0]')
            check(retried==original,'deliberate reload retry sends identical body, permissions, retained evidence, Brain and op key')
            expect(box).to_have_value('')
            # In-flight success updates a new mount of the real Composer.
            view.evaluate('window.review.mode="hold"')
            box.fill('late success after card remount')
            mini.locator('.fw-send-main').click();view.wait_for_function('window.review.calls.length===2')
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
            # First use and capability/Brain preflight controls.
            reset('?no-own')
            expect(mini.get_by_role('button',name='Create own Conversation',exact=True)).to_be_visible()
            mini.get_by_role('button',name='Create own Conversation',exact=True).click()
            expect(box).to_be_visible()
            check(view.evaluate('window.review.create.body.op')=='magnet-conversation:mag-review','first use creates own Conversation under stable explicit operation')
            view.evaluate('window.review.canWrite=false;window.review.notify()')
            expect(mini.locator('textarea')).to_have_count(0)
            check(True,'withdrawn capability removes writable mini Composer')
            view.evaluate('window.review.canWrite=true;window.review.notify()')
            box.fill('must not cross Brain instance')
            view.evaluate('window.review.brain="another-instance"')
            mini.locator('.fw-send-main').click()
            expect(mini.get_by_text('Nothing was sent:',exact=False).first).to_be_visible()
            check(view.evaluate('window.review.calls.length')==0,'changed Brain refuses before any mini write')
            (OUT/'trace.json').write_text(json.dumps({'ordinary':normal,'original':original,'retry':retried,'checks':checks},indent=2),encoding='utf-8')
            check(not errors,f'no browser JS errors: {errors}')
            browser.close()
        print(f'Completed: {checks} checks passed; 0 failed, 0 skipped, 0 errors',flush=True)
    finally:
        proc.terminate();proc.wait(timeout=10)
        print(f'own Vite PID {proc.pid} stopped; returncode={proc.returncode}',flush=True)
