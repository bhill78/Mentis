from pathlib import Path
import json
from playwright.sync_api import sync_playwright
R=Path(__file__).resolve().parents[1]
with sync_playwright() as pw:
 b=pw.chromium.launch(channel='chrome',headless=True)
 out={}
 for name in ('g3a','g3b'):
  out[name]={}
  for w,h in ((1440,900),(390,844)):
   p=b.new_page(viewport={'width':w,'height':h},has_touch=w==390)
   p.goto((R/'candidates'/f'{name}.html').as_uri())
   p.locator('[data-puck-btn]').focus()
   p.screenshot(path=str(R/'evidence'/f'{name}-{w}-card.png'))
   out[name][w]={'card':p.locator('[data-hover-card]').bounding_box()}
   p.locator('[data-hover-card] [data-action="open-deeper"]').click()
   p.screenshot(path=str(R/'evidence'/f'{name}-{w}-deep.png'))
   out[name][w]['deep']=p.locator('[data-level3-surface]').bounding_box()
   out[name][w]['elements']=p.evaluate('''()=>[...document.querySelectorAll('[data-level3-surface] [data-src], [role=tablist], .g3-provenance')].map(e=>{let r=e.getBoundingClientRect();return [e.getAttribute('data-src')||e.className,r.x,r.y,r.width,r.height]})''')
   p.close()
 print(json.dumps(out,indent=1))
 b.close()
