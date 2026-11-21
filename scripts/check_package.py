from pathlib import Path
import json,hashlib,datetime
from playwright.sync_api import sync_playwright
R=Path(__file__).resolve().parents[1]
checks=[];details={}
def ck(n,v):checks.append({'check':n,'pass':bool(v)})
with sync_playwright() as pw:
 b=pw.chromium.launch(channel='chrome',headless=True)
 for doc in ['index.html','standalone-comparison.html']:
  p=b.new_page(viewport={'width':1600,'height':1100});errors=[]
  p.on('pageerror',lambda e:errors.append(str(e)))
  p.on('console',lambda e:errors.append(e.text) if e.type=='error' else None)
  p.goto((R/doc).as_uri());details[doc]=[]
  for name in ['G3A','G3B','G2A-c','G2B-c','C4','C1']:
   p.locator('#pick').select_option(name)
   frame=p.locator('iframe').element_handle().content_frame()
   frame.wait_for_function('(n)=>document.title.startsWith(n)',arg=name)
   for width,height,id in [(1440,900,'desktop'),(390,844,'phone')]:
    p.locator('#'+id).click()
    frame.wait_for_function('(wh)=>innerWidth===wh[0]&&innerHeight===wh[1]',arg=[width,height])
    details[doc].append({'candidate':name,'viewport':[width,height],'title':frame.title()})
    ck(f'{doc}/{name}/{width}/frame renders at exact size',frame.locator('body').is_visible())
   if name.startswith('G3'):
    frame.locator('[data-puck-btn]').focus()
    ck(f'{doc}/{name}/own quick card',frame.locator('[data-hover-card]').is_visible())
  ck(doc+'/zero browser errors',not errors);details[doc+'-errors']=errors
  p.locator('#pick').select_option('G3A');p.locator('#desktop').click();p.screenshot(path=str(R/'evidence'/(doc.replace('.html','')+'-comparison.png')))
  p.close()
 b.close()
v=json.loads((R/'evidence/verification.json').read_text(encoding='utf-8'))
for n,path in [('G3A','candidates/g3a.html'),('G3B','candidates/g3b.html')]:
 ck(n+'/same final bytes as scenario verification',hashlib.sha256((R/path).read_bytes()).hexdigest()==v['results'][n]['390']['sha256'])
out={'timeUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'checks':checks,'details':details,
 'counts':{'passed':sum(c['pass'] for c in checks),'failed':sum(not c['pass'] for c in checks),'skipped':0,'errors':0}}
(R/'evidence/package-check.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
print(out['counts'])
for c in checks:
 if not c['pass']:print('FAILED',c)
