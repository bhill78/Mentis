"""Focused layout/collection interaction regression; not real-product acceptance.

The approved card has no compact content state: the six tabs, the search line and
the composer slot are present whenever the card is open, so navigation is by tab
rather than by "All Posts" links and a "Compact card" button. `.q2-magnet-view`
is the one scroll container, and per-view reading positions live in `places`.
"""
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
            view=page.locator('.q2-magnet-view')
            expect(card).to_be_visible()
            row=page.locator('.q2-work-row')
            row.evaluate('e=>e.scrollTop=400')
            before=row.evaluate('e=>({box:e.getBoundingClientRect().toJSON(),scroll:e.scrollTop,padding:getComputedStyle(e).paddingRight})')
            puck_before=page.locator('.q2-magnet-puck').bounding_box()
            check(card.locator('.q2-magnet-view').count()==1,'the card has exactly one scroll container')

            card.get_by_role('tab',name='Posts',exact=True).click()
            expect(card.get_by_role('tab',name='Posts',exact=True)).to_have_attribute('aria-selected','true')
            check(True,'the Posts tab selects Posts')
            check(puck_before==page.locator('.q2-magnet-puck').bounding_box(),'changing tab preserves exact puck coordinates and size')

            view.evaluate('e=>e.scrollTop=350')
            page.wait_for_timeout(120)
            position=view.evaluate('e=>e.scrollTop')
            check(position>0,'the view scrolls')
            view.locator('.q2-magnet-item').nth(5).click(force=True)
            expect(card.locator('.q2-magnet-post-text')).to_contain_text('captured words')
            card.get_by_role('button',name='Back to Magnet',exact=False).click()
            page.wait_for_timeout(120)
            check(abs(view.evaluate('e=>e.scrollTop')-position)<2,'inspection Back restores the collection reading position')

            card.get_by_role('tab',name='Files',exact=True).click()
            expect(card.get_by_role('tab',name='Files',exact=True)).to_have_attribute('aria-selected','true')
            check(True,'the Files tab selects Files')
            check(view.evaluate('e=>e.scrollTop')==0,'a view the reader has not scrolled starts at the top')
            card.get_by_role('tab',name='Posts',exact=True).click()
            page.wait_for_timeout(120)
            check(abs(view.evaluate('e=>e.scrollTop')-position)<2,'tab switches retain independent Posts reading position')

            card.get_by_role('tab',name='All',exact=True).click()
            expect(card.get_by_role('tabpanel',name='All')).to_be_visible()
            check(view.locator('.q2-magnet-item').count()==36,'All lists posts and retained attachments together')
            search=card.get_by_role('searchbox',name='Search all Magnet information')
            search.fill('Retained file')
            page.wait_for_timeout(120)
            check(card.get_by_role('heading',name='Search this Magnet').count()==1,'typing in the search line opens the search overlay')
            check(card.get_by_role('tab',name='All',exact=True).get_attribute('aria-selected')=='false','the search overlay covers the tab rather than replacing it')
            card.get_by_role('button',name='Return to All',exact=False).click()
            page.wait_for_timeout(120)
            check(card.get_by_role('tab',name='All',exact=True).get_attribute('aria-selected')=='true','returning from search comes back to the tab it covered')
            check(search.input_value()=='Retained file','returning from search keeps the query in the search line')
            card.get_by_role('button',name='Clear search',exact=True).click()
            page.wait_for_timeout(120)
            check(view.locator('.q2-magnet-item').count()==36,'the covered view is exactly as it was left')

            after=row.evaluate('e=>({box:e.getBoundingClientRect().toJSON(),scroll:e.scrollTop,padding:getComputedStyle(e).paddingRight})')
            check(before==after,'tabs, inspection, Back and search preserve surrounding geometry and scroll')
            check(page.locator('.q2-magnet-puck').evaluate("e=>{const r=e.getBoundingClientRect();return !!document.elementFromPoint(r.left+r.width*.75,r.top+r.height*.5)?.closest('.q2-magnet-puck')}"),'attached yellow puck remains directly reachable above sticky header')
            check(not errors,'zero page errors')
            browser.close()
        print(json.dumps({'passed':len(checks),'failed':0,'skipped':0,'errors':0,'checks':checks}),flush=True)
    finally:
        subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],capture_output=True)
        proc.wait(timeout=15)
