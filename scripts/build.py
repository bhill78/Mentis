"""Produce bounded static derivatives from the held selected parent bytes only."""
from pathlib import Path
import hashlib, json, re, shutil

ROOT = Path(__file__).resolve().parents[1]
WS = ROOT.parent
for d in ('candidates','references','evidence'):
    (ROOT/d).mkdir(exist_ok=True)
sources = {
 'G2A-c': WS/'.mentis-artifacts/9bee386174596de0.html.txt',
 'G2B-c': WS/'.mentis-artifacts/9bb67c090868c62f.html.txt',
 'C4': WS/'magnet-gen2-independent-review/held/pkg/magnet-ui-gen1/concepts/c4-evidence-inquiry-desk.html',
 'C1': WS/'magnet-gen2-independent-review/held/pkg/magnet-ui-gen1/concepts/c1-contextual-inspector.html',
 'SCENARIO_AND_TASKS': WS/'.mentis-artifacts/a98380ebaa24ee62.md',
 'GEN2_COMPACT_INDEPENDENT_REVIEW': WS/'.mentis-artifacts/a7b621f6a35d32dd.txt',
 'GEN1_INDEPENDENT_REVIEW': WS/'.mentis-artifacts/0a7ca0f1a09d19b3.md',
 'COMPACT_MAGNET_REVIEW': WS/'.mentis-artifacts/36bda64556e69bf0.md',
 'owner-yellow-magnet': WS/'.mentis-artifacts/8f47618463d834de.png',
 'owner-ringed-magnet': WS/'.mentis-artifacts/61ade23a912618b4.png',
 'gen2-reviewed-density': WS/'.mentis-artifacts/1fe5d916d3d90351.txt',
}
manifest={}
for key,p in sources.items():
    suffix='.png' if p.suffix=='.png' else '.json' if key.endswith('density') else '.html' if key in ('C1','C4','G2A-c','G2B-c') else '.md'
    dest=ROOT/'references'/(key+suffix)
    shutil.copyfile(p,dest)
    manifest[key]={'source':str(p),'copy':str(dest.relative_to(ROOT)), 'sha256':hashlib.sha256(p.read_bytes()).hexdigest(), 'bytes':p.stat().st_size}
(ROOT/'source-manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')

CSS='''
/* Gen 3 bounded changes; underlying selected-parent panels remain intact. */
.inspect-ribbon { padding:6px 12px; min-height:42px; }
.rb-static-note {font-size:11px!important;}
.g3-static {color:var(--text-dim); font-size:11px;}
.mag-puck-glyph,.mag-puck-sub,.mag-persp-badge,.mag-puck-stat {display:none;}
.mag-puck-caption {border:0;background:transparent;box-shadow:none;}
.mag-puck-anchor {width:98px;transition:none;}
.mag-puck-btn {width:56px;height:56px;min-width:50px;min-height:50px;}
.mag-puck-btn:hover,.mag-puck-btn[aria-expanded=true] {transform:none;}
.mag-puck-count {font-size:20px;}
.mag-hover-card[data-pos] {width:396px;max-width:calc(100% - 16px);max-height:none;padding:10px;overflow:visible;gap:7px;background:var(--surface-raised);}
.g3-title {font-size:14px;font-weight:700;line-height:1.25;}
.g3-sub {font-size:12px;color:var(--text-dim);line-height:1.35;}
.g3-card-head {display:flex;gap:8px;justify-content:space-between;align-items:start;}
.g3-card-status {font-size:12px;line-height:1.4;color:var(--attention);}
.g3-preview-grid {display:grid;grid-template-columns:1fr 1fr;gap:8px;}
.g3-preview-grid section {min-width:0;}
.g3-kind {font-size:12px;font-weight:700;color:var(--text-dim);margin-bottom:3px;}
.g3-preview {font-size:12px;line-height:1.4;border-top:1px solid var(--line);padding:4px 0;}
.g3-preview b {color:var(--accent-ink);font-family:var(--mono);font-size:11px;}
.g3-card-actions {display:flex;gap:6px;align-items:center;}
.g3-card-actions button {min-height:32px;font-size:12px;flex:1;white-space:nowrap;padding:4px 6px;}
.g3-route-index {display:flex;gap:6px;}
.g3-route-index button {flex:1;min-height:32px;font-size:12px;}
.g3-route-index button[aria-pressed=true] {border-color:var(--accent);color:var(--accent-ink);background:var(--accent-soft);}
.g3-kind-panel[hidden] {display:none;}
.g3-provenance {display:none;gap:4px;flex-wrap:wrap;padding:5px 0;}
.g3-provenance .q2-chip {font-size:11px;}
.g3-narrow-label {display:none;}
.g3-fixed-config {display:none;}
.g3-placement {position:fixed;right:12px;top:50px;z-index:100;width:340px;max-width:calc(100vw - 24px);padding:14px;background:var(--surface-raised);border:1px solid var(--line-strong);border-radius:10px;box-shadow:var(--shadow-sheet);font-size:13px;}
.g3-placement[hidden] {display:none;}
.g3-placement p {margin:8px 0;line-height:1.4;}
.g3-placement button {min-height:32px;margin:4px 3px 4px 0;}
.g3-placement code {font-size:12px;}
.g3-identity-details summary {cursor:pointer;min-height:30px;font-size:13px;font-weight:700;padding:4px;}
@media(min-width:721px) {.g3-identity-details summary {display:none;}}
.g2a-origin-band {position:relative;}
.g3-origin-note {font-size:11px;color:var(--text-dim);position:sticky;top:0;background:var(--surface);padding:3px;z-index:1;}
.g2a-origin-inner {overflow:visible;}
body[data-design=G3B] .mag-hover-card[data-pos] {width:348px;gap:3px;padding:8px;}
body[data-design=G3B] .mag-puck-btn {border-radius:14px;}
@media(max-width:720px) {
 .rb-title,.rb-static-note,[data-set-vp],.rb-sep {display:none!important;}
 .inspect-ribbon {min-height:42px;flex-wrap:nowrap;gap:4px;padding:5px 8px;}
 .rb-right {gap:3px!important;}
 .rb-btn {font-size:10px;padding:2px 5px;min-height:28px;}
 .mag-hover-card[data-pos] {left:8px;right:8px;bottom:8px;top:auto;width:auto;max-width:none;padding:9px;}
 body[data-design=G3B] .mag-hover-card[data-pos] {width:auto;}
 .mag-puck-anchor {width:56px;}
 .mag-puck-btn {width:50px;height:50px;}
 .mag-puck-caption {display:none;}
 .g3-title {font-size:13px;}
 .g3-fixed-config {display:block;flex-shrink:0;font:11px/1.4 var(--mono);padding:4px 10px;background:var(--surface-deep);border-bottom:1px solid var(--line);}
 .g3-provenance {display:flex;}
 .g3-card-actions button {min-height:32px;}
 .g3-preview {font-size:12px;}
 .g2a-sheet-head {flex-wrap:nowrap;padding:6px 10px;}
 .g2a-identity-line {display:none;}
 .g3-narrow-label {display:block;font-size:12px;font-weight:700;}
 .g2b-lock-strip {padding:5px 10px;flex-wrap:nowrap;}
 .g2b-lock-strip>div {display:none!important;}
 .g2b-return-strip {display:none!important;}
 .g2b-right-inquiry .wrap-tablist,.g2a-right-inquiry .wrap-tablist {padding:4px;gap:3px;}
 .wrap-tab {min-height:28px;padding:3px 6px;font-size:11px;}
 .g2a-left-ledger,.g2b-left-ledger {padding:6px 10px;}
 .scope-strip {padding:5px;margin-bottom:4px;}
 .filter-row {gap:3px;margin:4px 0;}
 .filter-chip {min-height:28px;padding:3px 6px;}
 .g3-provenance {padding:3px 0;}
}
@media(prefers-reduced-motion:reduce) {* {transition:none!important;scroll-behavior:auto!important;}}
'''

def card(kind,prefix):
    head='''<div class="g3-card-head"><div><div class="g3-title">Checkout Latency &amp; Cache Watch</div><div class="g3-sub">14 bounded items · 1 new since you looked</div></div><button class="mhc-close-btn" data-action="close-card" aria-label="Close compact Magnet card">×</button></div>'''
    status='<div class="g3-card-status">P1·S3 behind: 2 new · SRC-09 restricted</div>'
    posts='''<div class="g3-preview"><b>SRC-13</b> Replica lag 420ms</div><div class="g3-preview"><b>SRC-04</b> Warm-cache spike 610ms</div>'''
    files='''<div class="g3-preview"><b>SRC-14</b> Bimodal jitter trace</div><div class="g3-preview"><b>SRC-02</b> 14,200 checkout spans</div>'''
    actions='''<div class="g3-card-actions"><button class="mhc-primary-open" data-action="open-deeper">Open evidence →</button><button class="pill-btn" data-action="open-deeper-target" data-deep-target="chat">Magnet Chat · 9</button></div>'''
    if kind=='A':
        content=head+status+f'''<div class="g3-preview-grid"><section data-card-section="posts"><div class="g3-kind">Posts &amp; changes · 8</div>{posts}</section><section data-card-section="files"><div class="g3-kind">Files &amp; traces · 6</div>{files}</section></div><div class="g3-sub">3 Perspectives · syntheses are interpretations</div>'''+actions
    else:
        content=head+'''<div class="g3-sub">Collects p99 traces, incidents &amp; replication lag.</div>'''+status+f'''<div class="g3-route-index" role="group" aria-label="Quick collection kind"><button class="pill-btn" data-kind="posts" aria-pressed="true" aria-controls="g3-posts">Posts &amp; changes · 8</button><button class="pill-btn" data-kind="files" aria-pressed="false" aria-controls="g3-files">Files &amp; traces · 6</button></div><section class="g3-kind-panel" id="g3-posts" data-card-section="posts">{posts}</section><section class="g3-kind-panel" id="g3-files" data-card-section="files" hidden>{files}</section>'''+actions
    return f'''<section class="mag-hover-card" id="{prefix}-hover-card" data-hover-card="true" data-pos="mid-right" role="dialog" aria-modal="false" aria-label="Quick collection — Checkout Latency and Cache Watch" hidden>{content}</section>'''

SCRIPT=r'''
(() => {
 const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
 const design=document.body.dataset.design, prefix=design==='G3A'?'g2ac':'g2bc';
 const origin=$('#level1-resting-conv');let originScroll=0;
 document.addEventListener('click',e=>{if(e.target.closest('[data-action="open-deeper"],[data-action="open-deeper-target"],[data-set-level="L3"]'))originScroll=origin.scrollTop;},true);
 const desk=$('#'+prefix+(design==='G3A'?'-desk-body':'-desk'));
 const ledgerButton=$('#'+prefix+(design==='G3A'?'-toggle-ledger':'-narrow-ledger-btn'));
 const anchor=$('[data-puck-anchor]'), card=$('[data-hover-card]'), stage=$('.q2-work-stage');
 // Coordinate samples are arbitrary values, not a product placement enum or drag implementation.
 let coordinate=[.89,.29];
 function place(){
   const r=stage.getBoundingClientRect(), narrow=r.width<=720;
   const w=anchor.offsetWidth||56, h=anchor.offsetHeight||56;
   anchor.style.cssText=`left:${Math.round(Math.max(8,Math.min(r.width-w-12,coordinate[0]*r.width)))}px;top:${Math.round(Math.max(12,Math.min(r.height-h-12,coordinate[1]*r.height)))}px;right:auto;bottom:auto;`;
   // Card stays on screen and inside the working area above the composer.
   if(!narrow){const x=parseFloat(anchor.style.left), y=parseFloat(anchor.style.top);
     card.style.left=Math.max(8,Math.min(r.width-card.offsetWidth-8,x-card.offsetWidth-16))+'px';
     card.style.top=Math.max(8,Math.min(r.height-card.offsetHeight-8,y-20))+'px';
     card.style.right='auto';card.style.bottom='auto';
   } else {card.style.cssText='';}
 }
 const obs=new MutationObserver(place);obs.observe(card,{attributes:true,attributeFilter:['hidden']});
 window.addEventListener('resize',place);place();
 $$('#g3-placement [data-xy]').forEach(b=>b.addEventListener('click',()=>{
   coordinate=b.dataset.xy.split(',').map(Number);place();
   $('#g3-coordinates').textContent=`Illustrated normalized x=${coordinate[0]}, y=${coordinate[1]} (this page only)`;
 }));
 $('#g3-study').addEventListener('click',()=>{$('#g3-placement').hidden=!$('#g3-placement').hidden;});
 $('#g3-study-close').addEventListener('click',()=>{$('#g3-placement').hidden=true;$('#g3-study').focus();});
 $$('[data-kind]').forEach(b=>b.addEventListener('click',()=>{
   $$('[data-kind]').forEach(k=>{const on=k===b;k.setAttribute('aria-pressed',on);$('#g3-'+k.dataset.kind).hidden=!on;});place();
 }));
 const ledger=$('.'+(design==='G3A'?'g2a':'g2b')+'-left-ledger');
 const provenance=document.createElement('div');provenance.className='g3-provenance';
 provenance.setAttribute('aria-label','Current P1 S3 audit context');
 provenance.innerHTML='<span class="q2-chip">P1·S3 Interpretation</span><span class="q2-chip">Not established</span><span class="q2-chip warn">Behind · 2 new</span><span class="q2-chip warn">SRC-09 restricted · gate pending</span>';
 ledger.querySelector('[data-ledger-list]').before(provenance);
 if(design==='G3B'){
   const identity=ledger.querySelector('[data-criterion="1-magnet-identity"]');
   const participants=ledger.querySelector('[data-criterion="8-participants"]');
   const details=document.createElement('details');details.className='g3-identity-details';details.open=window.innerWidth>720;
   details.innerHTML='<summary>Magnet purpose, scope &amp; participants</summary>';
   identity.before(details);details.append(identity,participants);
 }
 if(design==='G3A'){
   const band=$('.g2a-origin-inner'), note=document.createElement('div');note.className='g3-origin-note';
   note.textContent='Origin #14 · scrollable reading context; full draft remains in the composer';band.prepend(note);
 }
 document.addEventListener('magnet:levelchange',ev=>{
   if(ev.detail.level==='L3'){
     const target=ev.detail.target||'p1';
     if(target==='p1'){
       desk.classList.remove('n-inquiry');desk.classList.add('n-evidence');
       ledgerButton.textContent='Inquiry & Chat';ledgerButton.setAttribute('aria-pressed','true');
       ledger.scrollTop=0;
     }
     const returnBtn=$$('[data-level3-surface] [data-action="return-resting"]').find(e=>e.getBoundingClientRect().width>0)||$('#'+prefix+'-top-return');
     returnBtn.focus();
     if(design==='G3A') $('#origin-post-14').scrollIntoView({block:'nearest'});
   } else if(ev.detail.level==='L1') {place();origin.scrollTop=originScroll;const post=$('#resting-origin-post-14');post.tabIndex=-1;post.focus({preventScroll:true});}
 });
 // Preserve return-button focus on a visible control without re-opening the quick card.
 document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!$('#g3-placement').hidden){$('#g3-placement').hidden=true;$('#g3-study').focus();}});
})();
'''

for k,parent,title in [('A','G2A-c','Grouped Preview Workbench'),('B','G2B-c','Indexed Preview Split Desk')]:
    text=(ROOT/'references'/(parent+'.html')).read_text(encoding='utf-8')
    prefix='g2ac' if k=='A' else 'g2bc'
    # Remove the uninstantiated shared stylesheet branch for rejected G2C-c's orbital cue.
    text=re.sub(r'/\* Subtle orbital ring variant.*?\n}\n','',text,flags=re.S)
    start=text.index('      <section\n        class="mag-hover-card"')
    end=text.index('      <!-- Level 3:',start)
    text=text[:start]+card(k,prefix)+'\n    </div>\n\n'+text[end:]
    text=text.replace('<body data-magnet-level="L1">',f'<body data-magnet-level="L1" data-design="G3{k}">')
    text=text.replace(f'<div class="level3-surface hidden" id="{prefix}-level3" data-level3-surface="true">',f'<div class="level3-surface hidden" id="{prefix}-level3" data-level3-surface="true"><div class="g3-fixed-config">mag-checkout-latency · sha256:9f4b8e21…c218</div>')
    text=text.replace('<span class="rb-tag">'+parent+'</span>',f'<span class="rb-tag">G3{k}</span>')
    text=re.sub(r'<span class="rb-title">.*?</span>',f'<span class="rb-title">{title}</span>',text,count=1)
    text=re.sub(r'<span class="rb-static-note">.*?</span>',f'<span class="rb-static-note">Parent: {parent} only · Static: no drag, saving or backend actions</span>',text,count=1)
    text=re.sub(r'<title>.*?</title>',f'<title>G3{k} — {title} · Final static Quiet Magnet derivative</title>',text,count=1)
    text=text.replace('<div class="rb-right">','<div class="rb-right"><button class="rb-btn" id="g3-study" title="Static placement examples; no real dragging or persistence">Static study</button>',1)
    text=re.sub(r'<button[^>]*data-set-vp="[^"]+".*?</button>', '', text)
    for old,new in [('L1 Resting','Rest'),('L2 Card','Card'),('L3 Open','Deep'),('Quiet Dark','Dark'),('Quiet Light','Light')]:
        text=text.replace('>'+old+'</button>', '>'+new+'</button>')
    text=text.replace('</head>','<style>'+CSS+'</style></head>')
    text=text.replace('<div class="g2a-identity-line"', '<span class="g3-narrow-label">Magnet · 14 items</span><div class="g2a-identity-line"',1)
    text=text.replace('<div class="g2b-lock-strip" aria-label="Pinned Constant Magnet Collection Strip (Narrow)">','<div class="g2b-lock-strip" aria-label="Constant Magnet Collection"><span class="g3-narrow-label">Magnet · 14 items</span>')
    if k=='B':text=re.sub(r'<button[^>]*data-action="return-resting"[^>]*>Close to Resting Magnet</button>','',text)
    # No stale claims that Gen 2 itself was authored here. Its CSS/ID prefixes remain traceable.
    text=text.replace('<!-- Level 3: Preserved','<!-- Gen 3 derived from selected parent; Level 3: Preserved')
    panel='''<aside id="g3-placement" class="g3-placement" aria-label="Static placement study" hidden><strong>Static placement study</strong><p>Design intent: a small movable object anywhere in the working area. No real dragging, saved coordinates, persistence or backend enforcement exists here.</p><button data-xy="0.89,0.29">x .89 / y .29</button><button data-xy="0.08,0.47">x .08 / y .47</button><button data-xy="0.71,0.73">x .71 / y .73</button><p id="g3-coordinates">Three arbitrary coordinate illustrations; clamped within the working area.</p><p>Intended future model: normalized coordinates per person, workspace and Magnet ID; retain identity independently of placement; clamp on resize. This is a design hypothesis, not implemented storage.</p><button id="g3-study-close">Close study</button></aside>'''
    text=text.replace('</body>',panel+'<script>'+SCRIPT+'</script></body>')
    (ROOT/'candidates'/f'g3{k.lower()}.html').write_text(text,encoding='utf-8')
print('Created two derivatives and frozen reference copies')
