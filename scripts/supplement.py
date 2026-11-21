"""Check the seams changed by Gen 3 without repeating the complete task walkthrough."""
from pathlib import Path
import json,hashlib,difflib
from playwright.sync_api import sync_playwright
R=Path(__file__).resolve().parents[1]
out={'checks':[],'details':{}}
def ck(n,v):out['checks'].append({'check':n,'pass':bool(v)})
with sync_playwright() as pw:
 b=pw.chromium.launch(channel='chrome',headless=True)
 for name,parent in [('G3A','G2A-c'),('G3B','G2B-c')]:
  prefix='g2ac' if name=='G3A' else 'g2bc'
  source=b.new_page();source.goto((R/'references'/f'{parent}.html').as_uri())
  original=source.locator('[data-ledger-list]').evaluate('(e)=>e.outerHTML')
  panels=source.locator(f'[data-panel-group="{prefix}-r"]').evaluate_all('(es)=>es.map(e=>e.outerHTML)')
  source.close()
  for w,h in [(1440,900),(390,844)]:
   p=b.new_page(viewport={'width':w,'height':h},has_touch=w==390,is_mobile=w==390);p.goto((R/'candidates'/f'{name.lower()}.html').as_uri())
   detail={};key=f'{name}/{w}'
   detail['restingUnion']=p.locator('[data-puck-anchor]').evaluate('''e=>{let es=[e,...e.querySelectorAll('*')].filter(x=>x.checkVisibility());let rs=es.map(x=>x.getBoundingClientRect());let l=Math.min(...rs.map(r=>r.left)),t=Math.min(...rs.map(r=>r.top)),right=Math.max(...rs.map(r=>r.right)),bottom=Math.max(...rs.map(r=>r.bottom));return {x:l,y:t,w:right-l,h:bottom-t,pct:100*(right-l)*(bottom-t)/(innerWidth*innerHeight)}}''')
   detail['focusStyle']=p.locator('[data-puck-btn]').evaluate('e=>({outline:getComputedStyle(e).outline,shadow:getComputedStyle(e).boxShadow})')
   ck(key+'/ledger bytes inherited',p.locator('[data-ledger-list]').evaluate('(e)=>e.outerHTML')==original)
   ck(key+'/all inquiry panels inherited',p.locator(f'[data-panel-group="{prefix}-r"]').evaluate_all('(es)=>es.map(e=>e.outerHTML)')==panels)
   initial=p.locator('#resting-origin-article').bounding_box()
   p.locator('[data-float-layer]').evaluate('(e)=>e.style.display="none"')
   absent=p.locator('#resting-origin-article').bounding_box()
   ck(key+'/zero article reflow absent vs resting',initial==absent)
   p.locator('[data-float-layer]').evaluate('(e)=>e.style.display=""')
   # Hit testing chooses points away from the actual object; the encompassing layer must be transparent.
   detail['hitTests']=p.evaluate('''()=>[.2,.4,.6,.8].map(f=>{let y=innerHeight*.4,e=document.elementFromPoint(innerWidth*f,y);return {x:innerWidth*f,y,blocked:!!e?.matches('[data-float-layer]')}})''')
   ck(key+'/floating layer passes through unused area',all(not x['blocked'] for x in detail['hitTests']))
   p.locator('[data-puck-btn]').focus()
   # New card controls are at least 24px; presence includes zero-size detection.
   dims=p.locator('[data-hover-card] button').evaluate_all('(es)=>es.map(e=>({text:e.innerText,w:e.getBoundingClientRect().width,h:e.getBoundingClientRect().height}))')
   ck(key+'/card controls >=24px including zero',all(e['w']>=24 and e['h']>=24 for e in dims))
   detail['cardControls']=dims
   p.locator('[data-hover-card] [data-action="open-deeper"]').click()
   for target in ['p1','p2','p3','pnew']:
    if w==390 and not p.locator(f'[data-tab-group="{prefix}-r"]').first.is_visible():p.locator(f'#{prefix}-toggle-ledger,#{prefix}-narrow-ledger-btn').click()
    p.locator(f'[data-tab-group="{prefix}-r"][data-tab-target="{target}"]').click()
    text=p.locator('main').inner_text()
    ck(key+f'/T2 {target} visible constant digest','9f4b8e21' in text)
    ck(key+f'/T2 {target} collection unchanged',p.locator('[data-ledger-list]').evaluate('(e)=>e.outerHTML')==original)
   tabs=p.locator('[role=tab]').evaluate_all('''(es)=>es.map(e=>{let id=e.getAttribute('aria-controls'),panel=document.getElementById(id);return {id:e.id,valid:!!panel&&panel.getAttribute('role')==='tabpanel'&&panel.getAttribute('aria-labelledby')===e.id}})''')
   ck(key+'/every tab references labelled panel',all(t['valid'] for t in tabs))
   detail['tabs']=tabs
   ck(key+'/deep opening focus is visible',p.evaluate('document.activeElement.getBoundingClientRect().width>0'))
   # Check placement remains exact through a product open/return cycle.
   p.locator(f'#{prefix}-top-return').click();p.locator('#g3-study').click();p.locator('[data-xy]').nth(1).click();p.locator('#g3-study-close').click()
   pos=p.locator('[data-puck-anchor]').bounding_box();p.locator('[data-puck-btn]').focus();p.locator('[data-hover-card] [data-action="open-deeper"]').click();p.locator(f'#{prefix}-top-return').click()
   ck(key+'/coordinate illustration survives round trip',pos==p.locator('[data-puck-anchor]').bounding_box())
   # Light mode is a supplementary visual inspection, not a contrast audit.
   p.locator('[data-set-theme="light"]').click();p.locator('[data-puck-btn]').focus()
   p.screenshot(path=str(R/'evidence'/f'{name}-{w}-light-card.png'))
   out['details'][key]=detail;p.close()
 b.close()
out['counts']={'passed':sum(c['pass'] for c in out['checks']),'failed':sum(not c['pass'] for c in out['checks']),'skipped':0,'errors':0}
(R/'evidence/supplement.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
print(out['counts'])
for c in out['checks']:
 if not c['pass']:print('FAILED',c)
