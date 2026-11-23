"""Focused layout/collection interaction regression; not real-product acceptance."""
import json
import subprocess
import time
import urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

root = Path(__file__).resolve().parents[1]
checks = []
def check(ok, words):
    assert ok, words
    checks.append(words)

with (root / 'quiet-magnet-cohesive-browser.log').open('w',encoding='utf-8') as log:
    proc = subprocess.Popen(['node','node_modules/vite/bin/vite.js','--config','tests/quiet_magnet_cohesive_vite.mjs'],cwd=root,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
    print('owned harness pid',proc.pid,flush=True)
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen('http://127.0.0.1:5443/tests/quiet_magnet_cohesive.html',timeout=1).close()
                break
            except OSError: time.sleep(.1)
        assert proc.poll() is None
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='msedge',headless=True)
            page=browser.new_page(viewport={'width':1440,'height':1000})
            errors=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto('http://127.0.0.1:5443/tests/quiet_magnet_cohesive.html')
            card=page.locator('.q2-magnet-card')
            expect(card).to_be_visible()
            row=page.locator('.q2-work-row')
            row.evaluate('e=>e.scrollTop=400')
            before=row.evaluate('e=>({box:e.getBoundingClientRect().toJSON(),scroll:e.scrollTop,padding:getComputedStyle(e).paddingRight})')
            puck_before=page.locator('.q2-magnet-puck').bounding_box()
            card.get_by_role('button',name='All Posts',exact=True).click()
            expect(card.get_by_role('tab',name='Posts',exact=True)).to_have_attribute('aria-selected','true')
            check(True,'All Posts selects Posts')
            check(puck_before==page.locator('.q2-magnet-puck').bounding_box(),'expansion preserves exact puck coordinates and size')
            card.evaluate('e=>e.scrollTop=350')
            page.wait_for_timeout(100)
            position=card.evaluate('e=>e.scrollTop')
            card.locator('.q2-magnet-item').nth(5).click(force=True)
            expect(card.locator('.q2-magnet-post-text')).to_contain_text('captured words')
            card.get_by_role('button',name='Back to Magnet',exact=False).click()
            check(abs(card.evaluate('e=>e.scrollTop')-position)<1,'inspection Back restores collection reading position')
            card.get_by_role('button',name='Compact card',exact=True).click()
            card.get_by_role('button',name='All Files',exact=True).click()
            expect(card.get_by_role('tab',name='Files',exact=True)).to_have_attribute('aria-selected','true')
            check(True,'All Files selects Files')
            card.get_by_role('tab',name='Posts',exact=True).click()
            check(abs(card.evaluate('e=>e.scrollTop')-position)<1,'tab switches retain independent Posts reading position')
            card.get_by_role('tab',name='All',exact=True).click()
            expect(card.get_by_role('tabpanel',name='All retained information')).to_be_visible()
            check(card.locator('.q2-magnet-item').count()==36,'All lists posts and retained attachments together')
            search=card.get_by_role('searchbox',name='Search retained items')
            search.fill('Retained file')
            check(card.locator('.q2-magnet-item').count()==1,'one search finds retained files across All')
            card.get_by_role('tab',name='Posts',exact=True).click()
            expect(card.get_by_text('No retained items match this search and content type.')).to_be_visible()
            check(search.input_value()=='Retained file','content filters retain the shared search query')
            card.get_by_role('tab',name='All',exact=True).click()
            search.fill('')
            after=row.evaluate('e=>({box:e.getBoundingClientRect().toJSON(),scroll:e.scrollTop,padding:getComputedStyle(e).paddingRight})')
            check(before==after,'expansion compaction inspection and Back preserve surrounding geometry and scroll')
            check(page.locator('.q2-magnet-puck').evaluate("e=>{const r=e.getBoundingClientRect();return !!document.elementFromPoint(r.left+r.width*.75,r.top+r.height*.5)?.closest('.q2-magnet-puck')}"),'attached yellow puck remains directly reachable above sticky header')
            check(not errors,'zero page errors')
            browser.close()
        print(json.dumps({'passed':len(checks),'failed':0,'skipped':0,'errors':0,'checks':checks}),flush=True)
    finally:
        subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],capture_output=True)
        proc.wait(timeout=15)
