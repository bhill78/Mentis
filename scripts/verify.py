"""Focused browser evidence, not usability testing. Chrome; static candidate controls only.

Geometry accounts for clipping by every overflow ancestor. The previous review's
viewport-only density is also recorded separately for comparability.
"""
from pathlib import Path
import hashlib, json, re, sys, datetime
from playwright.sync_api import sync_playwright
R=Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding='utf-8')
DRAFT='Before we freeze v4.2, @maya can you confirm whether the Redis warmup patch also covers the cold-start spike seen in SRC-04?'
TARGETS={'G3A':R/'candidates/g3a.html','G3B':R/'candidates/g3b.html',
         'G2A-c':R/'references/G2A-c.html','G2B-c':R/'references/G2B-c.html','C4':R/'references/C4.html','C1':R/'references/C1.html'}
GEOMETRY=r'''() => {
 const box=e=>{const r=e.getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height,r:r.right,b:r.bottom}};
 const clip=e=>{let r=box(e);if(!e.checkVisibility({checkOpacity:true,checkVisibilityCSS:true}))return {area:0,full:false};
  let l=Math.max(0,r.x),t=Math.max(0,r.y),right=Math.min(innerWidth,r.r),bottom=Math.min(innerHeight,r.b);
  for(let p=e.parentElement;p;p=p.parentElement){const s=getComputedStyle(p),q=box(p);
   if(/auto|scroll|hidden|clip/.test(s.overflowX)){l=Math.max(l,q.x);right=Math.min(right,q.r)}
   if(/auto|scroll|hidden|clip/.test(s.overflowY)){t=Math.max(t,q.y);bottom=Math.min(bottom,q.b)} }
  return {area:Math.max(0,right-l)*Math.max(0,bottom-t),full:l<=r.x+.5&&t<=r.y+.5&&right>=r.r-.5&&bottom>=r.b-.5};};
 const pct=e=>e?+(100*clip(e).area/(innerWidth*innerHeight)).toFixed(3):null;
 const visible=e=>clip(e).area>0;
 const card=document.querySelector('[data-hover-card]'),puck=document.querySelector('[data-puck-anchor]');
 const chips=[...document.querySelectorAll('[class*=chip]')].filter(visible).map(e=>e.innerText);
 const tests={interpretation:/Interpretation/i,notEstablished:/Not established/i,behind:/Behind/i,restricted:/Restricted|SRC-09/i,mutual:/Mutual dep/i,edited:/Edited/i,deleted:/Deleted/i,dedup:/de-duplicat|Shared original/i,contradicts:/Contradict/i};
 const flags=Object.fromEntries(Object.entries(tests).map(([k,v])=>[k,chips.some(t=>v.test(t))]));
 let rows=[...document.querySelectorAll('[data-src],.evidence-item')];
 const src=rows.filter(visible).map(e=>({id:e.dataset.src||(e.innerText.match(/SRC-\d\d/)||[])[0],full:clip(e).full,rect:box(e)}));
 const controls=[...document.querySelectorAll('button,a[href],input,select,summary,[role=tab]')].filter(e=>e.checkVisibility({checkOpacity:true,checkVisibilityCSS:true}));
 const collapsed=controls.filter(e=>{const r=box(e);return r.w===0||r.h===0}).map(e=>e.innerText);
 const small=controls.filter(e=>visible(e)&&((box(e).w<24)||(box(e).h<24))).map(e=>({text:e.innerText,rect:box(e)}));
 const tabErrors=[...document.querySelectorAll('[role=tab]')].filter(e=>!e.getAttribute('aria-controls')||!document.getElementById(e.getAttribute('aria-controls'))).map(e=>e.innerText);
 const largest=document.querySelector('[data-level3-surface],.c4-desk,.c1-inspector');
 return {viewport:[innerWidth,innerHeight],restPct:pct(puck),restRect:puck?box(puck):null,
  conversationPct:pct(document.querySelector('.q2-resting-conv')),articleWidth:document.querySelector('#resting-origin-article')?.getBoundingClientRect().width,
  cardPct:card&&visible(card)?pct(card):null,cardRect:card&&visible(card)?box(card):null,
  deepPct:largest?pct(largest):null,src,fullyVisible:src.filter(e=>e.full).length,
  viewportOnlySources:rows.filter(e=>{const r=box(e);return e.checkVisibility()&&r.w>0&&r.h>0&&r.y<innerHeight&&r.b>0&&r.x<innerWidth&&r.r>0}).map(e=>e.dataset.src||(e.innerText.match(/SRC-\d\d/)||[])[0]),
  provenance:flags,provenanceCount:Object.values(flags).filter(Boolean).length,
  tabChrome:[...document.querySelectorAll('[role=tablist]')].filter(visible).reduce((n,e)=>n+box(e).h,0),
  originBandPct:pct(document.querySelector('.g2a-origin-band')),
  cardPreviews:card?[...card.querySelectorAll('[data-card-section]')].map(s=>({kind:s.dataset.cardSection,visible:[...s.querySelectorAll('.g3-preview,.mhc-row')].filter(e=>clip(e).full).length})):[],
  collapsed,small,tabErrors,hOverflow:document.documentElement.scrollWidth-innerWidth};
}'''
checks=[]
def check(name,ok,detail=''):
 checks.append({'check':name,'pass':bool(ok),'detail':detail})
def click(p,sel):
 loc=p.locator(sel)
 for i in range(loc.count()):
  if loc.nth(i).is_visible():loc.nth(i).click(timeout=3000);return
 raise RuntimeError('No visible control '+sel)
def shot(p,name,state,width):p.screenshot(path=str(R/'evidence'/f'{name}-{width}-{state}.png'))
def main():
 results={}
 with sync_playwright() as pw:
  browser=pw.chromium.launch(channel='chrome',headless=True)
  version=browser.version
  for name,path in TARGETS.items():
   results[name]={}
   modern=name.startswith('G')
   prefix='g2bc' if name in ('G3B','G2B-c') else 'g2ac'
   for width,height in ((1440,900),(390,844)):
    ctx=browser.new_context(viewport={'width':width,'height':height},has_touch=width==390,is_mobile=width==390)
    p=ctx.new_page();p.set_default_timeout(4000);errors=[]
    p.on('pageerror',lambda e:errors.append(str(e)))
    p.on('console',lambda e:errors.append(e.text) if e.type=='error' else None)
    p.goto(path.as_uri());p.wait_for_timeout(80)
    r={'cold':p.evaluate(GEOMETRY),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    if modern:
     check(f'{name}/{width}/deep absent cold',not p.locator('[data-level3-surface]').is_visible())
     if name.startswith('G3'):shot(p,name,'rest',width)
     # Product Tab reachability from a fresh load, excluding no controls by fiat.
     reached=False
     for n in range(25):
      p.keyboard.press('Tab')
      if p.locator('[data-puck-btn]').evaluate('(e)=>e===document.activeElement'): reached=True;break
     r['tabStopsToPuck']=n+1;check(f'{name}/{width}/Tab reaches puck',reached)
     focusText=p.locator('[data-hover-card]').inner_text()
     check(f'{name}/{width}/focus reveals card',p.locator('[data-hover-card]').is_visible())
     p.keyboard.press('Escape');check(f'{name}/{width}/Escape closes and restores focus',not p.locator('[data-hover-card]').is_visible() and p.locator('[data-puck-btn]').evaluate('(e)=>e===document.activeElement'))
     if width==1440:
      p.mouse.move(1,100);p.locator('[data-puck-btn]').hover();p.wait_for_timeout(80)
      check(f'{name}/{width}/hover same card',p.locator('[data-hover-card]').is_visible() and p.locator('[data-hover-card]').inner_text()==focusText)
      p.locator('[data-hover-card]').hover();p.wait_for_timeout(300)
      check(f'{name}/{width}/hover onto card stays open',p.locator('[data-hover-card]').is_visible())
     else:
      p.locator('[data-puck-btn]').tap()
      check(f'{name}/{width}/touch tap reveals card',p.locator('[data-hover-card]').is_visible())
     r['card']=p.evaluate(GEOMETRY)
     if name=='G3B':
      click(p,'[data-kind="files"]');r['filesCard']=p.evaluate(GEOMETRY)
      check(f'{name}/{width}/two file previews',r['filesCard']['cardPreviews'][1]['visible']==2)
      click(p,'[data-kind="posts"]')
     if name.startswith('G3'):
      shot(p,name,'card',width)
      click(p,'#g3-study');r['placements']=[]
      for i in range(3):
       p.locator('[data-xy]').nth(i).click();pos=p.locator('[data-puck-anchor]').bounding_box();r['placements'].append(pos)
       if width==1440:shot(p,name,f'placement-{i+1}',width)
      click(p,'#g3-study-close')
      # Restore sample one for reproducible comparison.
      click(p,'#g3-study');p.locator('[data-xy]').first.click();click(p,'#g3-study-close')
      p.locator('[data-puck-btn]').focus()
     scroll=p.locator('#level1-resting-conv').evaluate('(e)=>e.scrollTop')
     click(p,'[data-hover-card] [data-action="open-deeper"]')
     r['deep']=p.evaluate(GEOMETRY)
     if name.startswith('G3'):shot(p,name,'deep',width)
     check(f'{name}/{width}/explicit deep opens',p.locator('[data-level3-surface]').is_visible())
     if width==390 and name.startswith('G3'):
      check(f'{name}/{width}/W1 card <=40%',r['card']['cardPct']<=40)
      check(f'{name}/{width}/W2 first evidence and audit context',r['deep']['fullyVisible']>=1 and r['deep']['provenanceCount']>=4 and r['deep']['tabChrome']<=72)
     # T1: full ledger, accessible by its own evidence switch.
     if not p.locator('[data-src]').first.is_visible():click(p,f'#{prefix}-toggle-ledger,#{prefix}-narrow-ledger-btn')
     if name=='G3B' and not p.locator('.g3-identity-details').get_attribute('open'):
      # Identity disclosure is deliberately closed on narrow arrival.
      if width==390:click(p,'.g3-identity-details summary')
     ledger=p.locator('[data-src]');seen=[]
     for i in range(ledger.count()):
      ledger.nth(i).scroll_into_view_if_needed();seen.append(ledger.nth(i).get_attribute('data-src'))
     check(f'{name}/{width}/T1 14 evidence reachable',len(set(seen))==14)
     r['ledgerCodes']=seen
     before=p.locator('[data-src]').count()
     # T2-T6: own toggle then actual tabs; no review ribbon or JS activation.
     if width==390 and not p.locator(f'[data-tab-group="{prefix}-r"]').first.is_visible():
      click(p,f'#{prefix}-toggle-ledger,#{prefix}-narrow-ledger-btn')
     tasks={};texts={}
     for target in ('p2','p3','pnew','p1','cont','chat'):
      click(p,f'[data-tab-group="{prefix}-r"][data-tab-target="{target}"]')
      panel=p.locator(f'[data-panel-group="{prefix}-r"][data-panel-id="{target}"]')
      texts[target]=panel.inner_text()
      for el in panel.locator('h3,h4,.q-item,.syn-card,.manifest-table,tr').all():
       if el.is_visible():el.scroll_into_view_if_needed()
      check(f'{name}/{width}/reachable panel {target}',panel.is_visible())
     tasks['T2']=all(t in texts['p3'] for t in ('Earlier filter','Dormant')) and 'New Perspective' in texts['pnew'] and before==p.locator('[data-src]').count()
     tasks['T3']=all(t in texts['p1'] for t in ('Q1.1','Q3','Retired','DNS','S1','S2','S3','Interpretation','Not established'))
     tasks['T4']=all(t in texts['p1'] for t in ('SRC-01','SRC-02','SRC-07','SRC-09')) and bool(re.search('Mutual dep|mutual dep',texts['p1']))
     tasks['T5']=all(t in texts['cont'] for t in ('SRC-13','SRC-14','Atlas','codex','Keep')) and bool(re.search(r'estimat|Est\.',texts['cont'],re.I))
     tasks['T6']=all(t in texts['chat'] for t in ('ent-conv-mag-8841','#6','#9','maya','Atlas','Louie','brian','codex','claude'))
     for task,ok in tasks.items():check(f'{name}/{width}/{task}',ok)
     r['tasks']=tasks
     r['taskPanelText']=texts
     # Draft preview is immutable text in this experiment; this checks fidelity, not editable draft logic.
     check(f'{name}/{width}/separate Magnet composer destination',p.locator('[data-comp-dest="mag"]').get_attribute('aria-selected')=='true')
     click(p,f'#{prefix}-top-return')
     draft=p.locator('[aria-label="Origin unsent draft preview"]').inner_text()
     check(f'{name}/{width}/T7 exact draft and destination',draft==DRAFT and p.locator('[data-comp-dest="orig"]').get_attribute('aria-selected')=='true')
     r['scrollReturn']={'before':scroll,'after':p.locator('#level1-resting-conv').evaluate('(e)=>e.scrollTop')}
     if name.startswith('G3'):check(f'{name}/{width}/T7 exact scroll',r['scrollReturn']['before']==r['scrollReturn']['after'])
    else:
     # Frozen baseline walkthrough uses original controls and retains its limitations.
     r['deep']=r['cold'];texts={}
     if name=='C1':
      click(p,'[data-tab-group="c1-main"][data-tab-target="curated"]');r['ledgerText']=p.locator('[data-panel-group="c1-main"][data-panel-id="curated"]').inner_text()
      click(p,'[data-tab-group="c1-main"][data-tab-target="persp"]')
      for t in ('p2','p3','pnew','p1'):
       click(p,f'[data-tab-group="c1-p"][data-tab-target="{t}"]');texts[t]=p.locator(f'[data-panel-group="c1-p"][data-panel-id="{t}"]').inner_text()
      for t in ('continue','chat'):
       click(p,f'[data-tab-group="c1-main"][data-tab-target="{t}"]');texts[t]=p.locator(f'[data-panel-group="c1-main"][data-panel-id="{t}"]').inner_text()
     else:
      if width==390:click(p,'[data-c4-seg="evidence"]')
      r['ledgerText']=p.locator('.c4-left-evidence').inner_text()
      if width==390:click(p,'[data-c4-seg="inquiry"]')
      for t in ('p2','p3','pnew','p1','cont','chat'):
       click(p,f'[data-tab-group="c4-r"][data-tab-target="{t}"]');texts[t]=p.locator(f'[data-panel-group="c4-r"][data-panel-id="{t}"]').inner_text()
     r['taskPanelText']=texts
     r['representedSources']=sorted(set(re.findall(r'SRC-\d\d',r['ledgerText'])))
     check(f'{name}/{width}/T1-T6 original views reachable',len(texts)==6)
     if name=='C4' or width==390:click(p,'[data-action="return-origin"],[data-action="c1-toggle-origin"]')
     r['returnedOriginVisible']=p.locator('#origin-post-14').is_visible()
     check(f'{name}/{width}/T7 origin reachable',r['returnedOriginVisible'])
    check(f'{name}/{width}/zero page-console errors',not errors,errors)
    r['errors']=errors
    check(f'{name}/{width}/zero document overflow',p.evaluate('document.documentElement.scrollWidth===innerWidth'))
    results[name][str(width)]=r
    (R/'evidence/verification-progress.json').write_text(json.dumps({'results':results,'checks':checks},ensure_ascii=False,indent=2),encoding='utf-8')
    ctx.close()
    print(name,width,'checked',flush=True)
  browser.close()
 manifest=json.loads((R/'source-manifest.json').read_text())
 for name,m in manifest.items():
  check('preserved source '+name,hashlib.sha256(Path(m['source']).read_bytes()).hexdigest()==m['sha256']==hashlib.sha256((R/m['copy']).read_bytes()).hexdigest())
 out={'timeUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'browser':'installed Windows Chrome '+version,'results':results,'checks':checks,
      'counts':{'passed':sum(c['pass'] for c in checks),'failed':sum(not c['pass'] for c in checks),'skipped':0,'errors':0},
      'limits':'Author checks; no human testing, screen reader, physical touch or backend. Two baseline source ledgers are representative subsets. Clipping-aware geometry differs from prior review viewport-only figures.'}
 (R/'evidence/verification.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(out['counts']))
 for c in checks:
  if not c['pass']:print('FAILED',c)
 return out['counts']['failed']
if __name__=='__main__':sys.exit(bool(main()))
