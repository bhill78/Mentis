"""Independent decision-dock challenges. Synthetic fixture Brains only."""
import json,os
from pathlib import Path
import pytest
from mentis.conversation import versions
from tests.conftest import fake_execution,no_machine_source_cache,brains_shaped_before_the_presets
from tests._loop import world
from tests.needs_you_kinds import build
from tests.test_quiet_needs_you_inspect_browser import Quiet,_choose,_held
import weakref,struct,zlib
from functools import lru_cache
_servers=[]
@pytest.fixture(autouse=True)
def retain_fixture_server(monkeypatch):
    from tests import _loop
    bind=_loop.ThreadingHTTPServer
    def record(addr,handler):
        s=bind(addr,handler)
        _servers.append(weakref.ref(s))
        return s
    monkeypatch.setattr(_loop,'ThreadingHTTPServer',record)
@lru_cache(maxsize=150)
def mockup(g,n):
    w,h=640,360
    data=bytearray()
    for y in range(h):
        data.append(0)
        for x in range(w):
            c=(247,246,239)
            if 20<x<620 and 20<y<65:c=(34,43,46)
            if 26<x<214 and 84<y<340:c=(229,231,223)
            if 230<x<610 and 84<y<340:c=(255,255,251)
            if (x-120)**2+(y-155)**2<(36+n*2)**2:c=(246,194+g%30,44)
            if 255<x<570 and any(a<y<a+8 for a in (108,133,158,205,230,255)):c=(112,125,127)
            data.extend(c)
    def chunk(k,b):return struct.pack('!I',len(b))+k+b+struct.pack('!I',zlib.crc32(k+b))
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!IIBBBBB',w,h,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(data))+chunk(b'IEND',b'')


def _crowd(world, cid):
    """A realistic conversation: real result posts with held images, then later chatter."""
    cv, who = world['cv'], world['who']['@brian']
    for g in range(25):
        execution = f'reviewer-magnet-{g}'
        started = cv.record_act(actor=who, act='execution-started', conversation=cid,
                                execution=execution, detail={})
        refs = []
        for n in range(6):
            held = artifacts.hold(cv.corpus, cv, mockup(g % 2, n), act='artifact-returned', actor=who,
                                  source='reviewer fixture', door='worker-return',
                                  claimed_name=f'magnet-generation-{g}-variant-{n}.png',
                                  claimed_media_type='image/png', execution=execution, conversation=cid)
            refs.append(held['admission'])
        reply = cv.say(cid, who, [text(f'Generation {g}: six yellow Magnet comparisons are ready.')])
        cv.record_act(actor=who, act='result-returned', conversation=cid, turn=reply,
                      execution=execution, caused_by=started, detail={'returned_artifacts': refs})
    # the deliverables are now far above the latest reply chain
    return [cv.say(cid, who, [text(f'Routing/status reply {i}; the mockups are in earlier result posts.')])
            for i in range(60)]




OUT=Path(os.environ.get('REVIEW_SHOTS',str(Path(__file__).parent)))
WORDS='Wait for the yellow Magnet comparisons before deciding.'
@pytest.fixture
def chrome():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b=p.chromium.launch(channel='chrome',headless=True)
        yield b
        b.close()
def snap(p,n,extra=None):
    got={'history':p.evaluate('history.state'),'url':p.url,'text':p.locator('body').inner_text(),'focus':p.evaluate('document.activeElement.outerHTML'),'scroll':p.locator('.q2-conv').evaluate('e=>({top:e.scrollTop,height:e.scrollHeight})'),'extra':extra}
    p.screenshot(path=str(OUT/(n+'.png')));(OUT/(n+'.json')).write_text(json.dumps(got,indent=2),encoding='utf-8');return got
def evidence(q,w):
    row=q.answer_here(w['form']);_choose(row.locator(f"[data-question='{w['form_questions'][0]}']"),1,WORDS)
    return row.locator(f"[data-role='referenced'] button[data-ref-id='{w['evidence']}']")
def tabs_to(p,selector,reverse=False):
    for n in range(700):
        if p.evaluate('(s)=>document.activeElement.matches(s)',selector):return n
        p.keyboard.press('Shift+Tab' if reverse else 'Tab')
    raise AssertionError('native tab never reached '+selector)

@pytest.mark.parametrize('keyboard',[False,True])
def test_long_decision_return_preserves_reading_position(world,chrome,keyboard):
    w=build(world);_crowd(world,w['cid']);q=Quiet(chrome,world,w,width=390 if keyboard else 1440,height=780 if keyboard else 1000);p=q.page
    try:
        button=evidence(q,w)
        if keyboard:
            p.locator('.q2-gdock-close').focus()
            tabs_to(p,f"button[data-ref-id='{w['evidence']}']")
        left=p.locator('.q2-conv').evaluate('e=>{e.scrollTop=1600;return e.scrollTop}')
        assert left>1000
        if keyboard:p.keyboard.press('Enter')
        else:button.click()
        p.wait_for_function('(id)=>history.state.q2c.c===id',arg=w['other'])
        p.locator(f".q2-conv [data-post='{w['evidence']}']").wait_for()
        pill=p.locator('.q2-gdock-return-go');pill.wait_for()
        if keyboard:
            tabs_to(p,'.q2-gdock-return-go');p.keyboard.press('Enter')
        else:pill.click()
        p.wait_for_selector('.q2-gdock-panel [data-needs-item]');p.wait_for_timeout(1000)
        _held(p.locator(f"[data-question='{w['form_questions'][0]}']"),1,WORDS)
        got=snap(p,'long-return-'+str(keyboard),{'leftAt':left,'expectedOrigin':w['cid']})
        assert got['history']['q2c']['c']==w['cid']
        assert p.evaluate('(r)=>document.activeElement.dataset.refId===r',w['evidence'])
        assert abs(got['scroll']['top']-left)<3,'return loses the actual reading position in the long originating conversation'
    finally:q.close()

@pytest.mark.parametrize('kind',['403','missing','wrong-ref','wrong-target','deleted-real'])
def test_evidence_fresh_failure_keeps_decision(world,chrome,kind):
    w=build(world);q=Quiet(chrome,world,w);p=q.page
    try:
        b=evidence(q,w);calls=[]
        def answer(route):
            calls.append(route.request.url)
            if kind=='403':return route.fulfill(status=403,json={'error':'review fixture denies reading evidence'})
            if kind=='missing':return route.fulfill(status=404,json={'error':'review fixture evidence missing'})
            response=route.fetch();body=response.json()
            if kind=='wrong-ref':body['inspection']['id']=w['twin']
            if kind=='wrong-target':body['inspection']['post']=w['asking']
            route.fulfill(response=response,json=body)
        if kind=='deleted-real':versions.delete(world['cv'],w['evidence'],by=w['coach'],because='review fixture removes evidence after drawing')
        else:p.route('**/fluid/api/result-ref?*',answer)
        before=p.evaluate('JSON.stringify(history.state)');b.click();p.wait_for_timeout(700)
        got=snap(p,'fresh-'+kind,{'calls':calls})
        assert p.locator('.q2-gdock-panel').count()==1
        assert not p.locator('.q2-gdock-return-go').count()
        assert p.evaluate('JSON.stringify(history.state)')==before
        _held(p.locator(f"[data-question='{w['form_questions'][0]}']"),1,WORDS)
        assert p.locator('.q2-notice').count()
    finally:q.close()

def test_decision_return_refuses_changed_brain_and_retains_offer(world,chrome):
    w=build(world);q=Quiet(chrome,world,w);p=q.page
    try:
        evidence(q,w).click();p.locator(f".q2-conv [data-post='{w['evidence']}']").wait_for()
        p.locator('.q2-gdock-return-go').wait_for()
        p.route('**/api/review-change',lambda r:r.fulfill(status=409,json={'kind':'BrainChanged','error':'review fixture instance changed'}))
        p.evaluate("fetch('/api/review-change',{method:'POST',headers:{'X-Mentis-Client':'1'}})");p.wait_for_timeout(100)
        before=p.evaluate('JSON.stringify(history.state)');p.locator('.q2-gdock-return-go').click();p.wait_for_timeout(300)
        snap(p,'decision-return-brain-refusal')
        assert p.locator('.q2-gdock-return-go').count()==1
        assert not p.locator('.q2-gdock-panel').count()
        assert p.evaluate('JSON.stringify(history.state)')==before
        assert p.locator('.q2-notice').count()
    finally:q.close()

@pytest.mark.parametrize('kind',['deleted-post','denied-read'])
def test_asking_block_freshness_after_display(world,chrome,kind):
    w=build(world);q=Quiet(chrome,world,w);p=q.page
    try:
        b=q.item(w['input']).locator(f"button[data-ref-id='{w['set']}']");b.wait_for()
        calls=[]
        p.on('request',lambda r:calls.append(r.url) if '/api/' in r.url else None)
        if kind=='deleted-post':
            versions.delete(world['cv'],w['input_post'],by=w['coach'],because='review fixture removes the form after the panel drew it')
        else:
            p.route('**/fluid/api/result-ref?*',lambda r:r.fulfill(status=403,json={'error':'review fixture input access denied'}))
            p.route('**/api/turns/*',lambda r:r.fulfill(status=403,json={'error':'review fixture input access denied'}))
            p.route('**/fluid/api/needs-you/about*',lambda r:r.fulfill(status=403,json={'error':'review fixture input access denied'}))
            p.route('**/api/conversations/*',lambda r:r.fulfill(status=403,json={'error':'review fixture conversation access denied'}))
        b.click();p.wait_for_timeout(500)
        got=snap(p,'asking-'+kind,{'apiCallsSincePress':calls,'post':w['input_post'],'set':w['set']})
        assert not p.locator('[data-landed]').count(),'asking-block route must revalidate before presenting a now unavailable or denied form as the target'
        assert p.locator('.q2-gdock-panel').count()==1
    finally:q.close()

def test_history_after_decision_return(world,chrome):
    w=build(world);q=Quiet(chrome,world,w);p=q.page
    try:
        evidence(q,w).click();p.locator(f".q2-conv [data-post='{w['evidence']}']").wait_for();q.back_to_decision()
        p.locator('.q2-gdock-close').click();p.go_back();p.wait_for_function('(id)=>history.state.q2c.c===id',arg=w['other'])
        snap(p,'decision-history-back')
        assert not p.locator('.q2-gdock-panel').count()
        p.go_forward();p.wait_for_function('(id)=>history.state.q2c.c===id',arg=w['cid'])
        q.open_needs();_held(q.answer_here(w['form']).locator(f"[data-question='{w['form_questions'][0]}']"),1,WORDS)
        snap(p,'decision-history-forward')
    finally:q.close()

@pytest.mark.parametrize('route_kind',['evidence','asking-block'])
@pytest.mark.parametrize('outcome',['stay','changed-brain-go'])
def test_guard_does_not_arm_or_move_before_arrival(world,chrome,route_kind,outcome):
    from tests.test_quiet_brain_author_browser import _revise
    w=build(world);q=Quiet(chrome,world,w);p=q.page
    try:
        q.item(w['adoption']['ask']).locator(f"[data-role='subject'] button[data-ref-id='{w['rule']}']").click()
        p.locator(f"[data-record='{w['rule']}']").wait_for()
        ed=_revise(p,w['rule']);ed.locator('textarea').first.fill('Unrecorded revision retained through the guard.')
        # Start the next inspection with no older offer to confuse the result.
        old=p.locator('.q2-gdock-return button').last
        if p.locator('.q2-gdock-return').count():old.click()
        q.open_needs()
        b=evidence(q,w) if route_kind=='evidence' else q.item(w['input']).locator(f"button[data-ref-id='{w['set']}']")
        before=p.evaluate('JSON.stringify(history.state)');b.click();p.locator('.q2-leave').wait_for()
        snap(p,'guard-pending-'+route_kind+'-'+outcome)
        if outcome=='stay':
            assert p.locator('.q2-gdock-panel').count()==1,'a pending inspection must keep its panel until an actual arrival'
            assert not p.locator('.q2-gdock-return-go').count(),'a pending inspection has not earned a way back'
            p.locator('.q2-leave').get_by_role('button',name='Stay',exact=True).click();p.wait_for_timeout(200)
            got=snap(p,'guard-stay-'+route_kind)
            assert p.evaluate('JSON.stringify(history.state)')==before
            assert ed.locator('textarea').first.input_value()=='Unrecorded revision retained through the guard.'
            assert not p.locator('.q2-gdock-return-go').count(),'no return is owed for an inspection that never happened'
            # A pointer press outside the dock dismisses that panel, including
            # Stay's press. Reopening must retain its stored decision draft.
            if route_kind=='evidence':
                q.open_needs();_held(q.answer_here(w['form']).locator(f"[data-question='{w['form_questions'][0]}']"),1,WORDS)
        else:
            p.route('**/api/review-change',lambda r:r.fulfill(status=409,json={'kind':'BrainChanged','error':'review fixture instance changed while guard waited'}))
            p.evaluate("fetch('/api/review-change',{method:'POST',headers:{'X-Mentis-Client':'1'}})");p.wait_for_timeout(100)
            p.locator('[data-leave-go]').click();p.wait_for_timeout(500)
            got=snap(p,'guard-changed-brain-'+route_kind)
            assert p.evaluate('JSON.stringify(history.state)')==before,'guard continuation must refuse an old Brain launch before navigation'
    finally:q.close()

@pytest.mark.parametrize('route_kind',['evidence','asking-block'])
def test_actual_disposable_brain_swap_while_guard_waits(world,chrome,route_kind,tmp_path):
    from tests.test_quiet_brain_author_browser import _revise
    from mentis.web import _State,fixture
    w=build(world);q=Quiet(chrome,world,w);p=q.page
    server=_servers[-1]();old=server.RequestHandlerClass.state
    try:
        q.item(w['adoption']['ask']).locator(f"[data-role='subject'] button[data-ref-id='{w['rule']}']").click()
        p.locator(f"[data-record='{w['rule']}']").wait_for()
        ed=_revise(p,w['rule']);ed.locator('textarea').first.fill('Keep this unrecorded revision tied to its Brain.')
        if p.locator('.q2-gdock-return').count():p.locator('.q2-gdock-return button').last.click()
        q.open_needs()
        b=evidence(q,w) if route_kind=='evidence' else q.item(w['input']).locator(f"button[data-ref-id='{w['set']}']")
        before=p.evaluate('JSON.stringify(history.state)');b.click();p.locator('.q2-leave').wait_for()
        root=tmp_path/'other-brain';fixture.build(str(root));other=_State(str(root))
        server.RequestHandlerClass.state=other
        # The real server, now serving a second synthetic Brain at the same
        # address, must refuse a write bound to the first Brain before writing.
        refusal=p.evaluate("""async () => {const r=await fetch('/api/conversations',{method:'POST',headers:{'X-Mentis-Client':'1','Content-Type':'application/json'},body:JSON.stringify({name:'MUST NOT BE CREATED BY OLD BRAIN PAGE'})});return {status:r.status,body:await r.json()}}""")
        assert refusal['status']==409 and refusal['body']['kind']=='BrainChanged',refusal
        p.locator('[data-leave-go]').click();p.wait_for_timeout(700)
        got=snap(p,'actual-brain-swap-'+route_kind,{'refusal':refusal,'oldRoot':world['root'],'newRoot':str(root),'before':json.loads(before)})
        assert p.evaluate('JSON.stringify(history.state)')==before,'a real changed-Brain refusal must prevent the old opening from changing the centre'
    finally:
        server.RequestHandlerClass.state=old
        q.close()
