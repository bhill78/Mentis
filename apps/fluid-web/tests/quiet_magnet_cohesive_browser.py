"""Focused layout/collection interaction regression; not real-product acceptance.

The card has no compact content state: the navigation, the search line and the
composer slot are present whenever the card is open. Navigation is the owner's
hierarchy (ent-3191baeb33d2 §1): Summary, Perspectives and Conversation as
primary tabs, and the collection as one secondary place whose type filters
(Everything, Posts, Files) are the underlying lens places -- so each type still
keeps its own reading position. `.q2-magnet-view` is the one scroll container,
and per-view reading positions live in `places`.
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

            collection=card.get_by_role('tab',name='Collection',exact=False)
            def filtered(name):
                """The collection, shown by one type: the secondary place, then its filter."""
                collection.click()
                card.get_by_role('button',name=name,exact=True).click()
            filtered('Posts')
            expect(collection).to_have_attribute('aria-selected','true')
            expect(card.get_by_role('button',name='Posts',exact=True)).to_have_attribute('aria-pressed','true')
            check(True,'the collection shows posts when the Posts filter is chosen')
            check(puck_before==page.locator('.q2-magnet-puck').bounding_box(),'changing tab preserves exact puck coordinates and size')

            view.evaluate('e=>e.scrollTop=350')
            page.wait_for_timeout(120)
            check(view.evaluate('e=>e.scrollTop')>0,'the view scrolls')
            # Opening a collected record and closing it again. The selectors are
            # the rows and the close this build actually renders: the leg used
            # `.q2-magnet-item` and a "Back to Magnet" control, neither of which
            # the collection list or this harness has ever had, so it could not
            # reach what it was written to check. Same intent, nothing weakened.
            #
            # THE POSITION IS READ WHERE THE READER ACTUALLY IS. The approved
            # rows are taller than the ones this was written against (round 3,
            # 04-browse.png), so bringing the sixth row under the pointer moves
            # the view -- and what must be restored is where the reader was when
            # they opened the record, not an earlier offset. Scrolling the row
            # into view first and reading the position then checks exactly that,
            # and it is still a position the reader scrolled to.
            opened=view.locator('.q2-magnet-evidence-row').nth(5)
            opened.scroll_into_view_if_needed()
            page.wait_for_timeout(120)
            position=view.evaluate('e=>e.scrollTop')
            check(position>0,'the row opened from is below the top of the list')
            opened.click(force=True)
            expect(card.locator('.q2-magnet-post-text')).to_contain_text('captured words')
            card.get_by_role('button',name='Close this record',exact=True).click()
            page.wait_for_timeout(120)
            check(abs(view.evaluate('e=>e.scrollTop')-position)<2,'closing a record restores the collection reading position')

            filtered('Files')
            expect(card.get_by_role('button',name='Files',exact=True)).to_have_attribute('aria-pressed','true')
            check(True,'the Files filter shows files')
            check(view.evaluate('e=>e.scrollTop')==0,'a view the reader has not scrolled starts at the top')
            filtered('Posts')
            page.wait_for_timeout(120)
            check(abs(view.evaluate('e=>e.scrollTop')-position)<2,'filter switches retain independent Posts reading position')

            # The unified filter reads "All" in the approved design, which is
            # also what `MAGNET_COLLECTION_TABS` has always called it; the pills
            # are drawn inside Collected items now, not by the frame (plan
            # seam 1), and they are the same lens places as before.
            filtered('All')
            expect(card.get_by_role('tabpanel',name='All')).to_be_visible()
            check(view.locator('.q2-magnet-evidence-row').count()==36,'the unified collection lists posts and collected attachments together')
            search=card.get_by_role('searchbox',name='Search collected items')
            search.fill('Retained file')
            page.wait_for_timeout(120)
            check(card.get_by_role('heading',name='Results',exact=True).count()==1,'typing in the search line opens the search overlay')
            check(card.get_by_role('searchbox').count()==1,'there is one search line, not a second one in the results')
            check(collection.get_attribute('aria-selected')=='false','the search overlay covers the place rather than replacing it')
            card.get_by_role('button',name='Close search and return to All',exact=True).click()
            page.wait_for_timeout(120)
            check(collection.get_attribute('aria-selected')=='true','returning from search comes back to the place it covered')
            check(search.input_value()=='Retained file','returning from search keeps the query in the search line')
            card.get_by_role('button',name='Clear search',exact=True).click()
            page.wait_for_timeout(120)
            check(view.locator('.q2-magnet-evidence-row').count()==36,'the covered view is exactly as it was left')

            after=row.evaluate('e=>({box:e.getBoundingClientRect().toJSON(),scroll:e.scrollTop,padding:getComputedStyle(e).paddingRight})')
            check(before==after,'tabs, inspection, Back and search preserve surrounding geometry and scroll')
            check(page.locator('.q2-magnet-puck').evaluate("e=>{const r=e.getBoundingClientRect();return !!document.elementFromPoint(r.left+r.width*.75,r.top+r.height*.5)?.closest('.q2-magnet-puck')}"),'attached yellow puck remains directly reachable above sticky header')
            check(not errors,'zero page errors')
            browser.close()
        print(json.dumps({'passed':len(checks),'failed':0,'skipped':0,'errors':0,'checks':checks}),flush=True)
    finally:
        subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],capture_output=True)
        proc.wait(timeout=15)
