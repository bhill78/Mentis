// Independent synthetic probes against candidate modules and exact handoff wrappers.
import { registerHooks } from 'node:module'
import { readFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import test from 'node:test'
import assert from 'node:assert/strict'
import ts from '../node_modules/typescript/lib/typescript.js'
const hookURL = 'data:text/javascript,' + encodeURIComponent('export const useRef = v => ({current:v}); export const useEffect = f => globalThis.reviewEffects.push(f);')
registerHooks({
  resolve(s, c, next) {
    if (s === 'react' && /\/(places|centreHistory)\.ts$/.test(c.parentURL)) return { url: hookURL, shortCircuit: true }
    if (s.startsWith('.')) for (const ext of ['.ts', '.tsx', '/index.ts']) {
      const url = new URL(s + ext, c.parentURL)
      if (existsSync(fileURLToPath(url))) return { url: url.href, shortCircuit: true }
    }
    return next(s, c)
  },
  load(url, c, next) {
    if (url.endsWith('.css')) return { format: 'module', source: '', shortCircuit: true }
    if (/\.tsx?$/.test(url)) return { format: 'module', shortCircuit: true, source: ts.transpileModule(readFileSync(fileURLToPath(url), 'utf8').replaceAll('import.meta.env', '({})'), { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX } }).outputText }
    return next(url, c)
  },
})
globalThis.localStorage = { getItem: () => null, setItem() {}, removeItem() {} }
const M = await import('../src/quiet2/results/mount.ts')
const L = await import('../src/quiet2/results/launch.ts')
const O = await import('../src/quiet2/results/opener.ts')
const V = await import('../src/quiet2/viewer/viewers.ts')
const T = await import('../src/quiet2/results/targets.ts')
const H = await import('../src/quiet2/results/hostOpen.ts')
const R = await import('../src/quiet2/results/refRead.ts')
const { heldItem } = await import('../src/quiet2/brain/logic.ts')
const { usePlaces } = await import('../src/quiet2/places.ts')
const handoff = readFileSync(new URL('../src/quiet2/results/HOST-INTEGRATION.md', import.meta.url), 'utf8')
const baseline = readFileSync(new URL('../src/quiet2/Quiet2.tsx', import.meta.url), 'utf8')
const code = [...handoff.matchAll(/```tsx\r?\n([\s\S]*?)```/g)].map(m => m[1]).join('\n')
function variable(name, input = code) {
  const sf = ts.createSourceFile('snippet.tsx', input, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
  let found
  function visit(n) { if (ts.isVariableDeclaration(n) && n.name.getText(sf) === name) found = n.initializer; ts.forEachChild(n, visit) }
  visit(sf); assert.ok(found, name); return found.getText(sf)
}
function property(name) {
  const sf = ts.createSourceFile('snippet.tsx', 'const p = ' + variable('resultPage'), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
  const obj = sf.statements[0].declarationList.declarations[0].initializer
  const p = obj.properties.find(p => p.name?.getText(sf) === name)
  assert.ok(p, name); return p.initializer.getText(sf)
}
function evaluate(expr, deps) {
  const js = ts.transpileModule('const extracted = ' + expr, { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText
  return new Function(...Object.keys(deps), js + '; return extracted')(...Object.values(deps))
}
const brain = 'fixture-corpus@instance-1', A = 'adm-111111111111', B = 'adm-222222222222', ASK = 'opr-aaaaaaaaaaaa'
const HELD = { state: 'held', name: 'review.txt', size: 20, claimed_media_type: 'text/plain' }
const ref = (id = A, extra = {}) => ({ id, type: 'file', state: 'ok', available: true, opens: 'file', file: HELD, ...extra })
const dest = (id = A, extra = {}) => T.destinationOfRef(ref(id, extra))
const tick = () => new Promise(r => setImmediate(r))
const ids = new Set()
function reset() {
  for (const row of M.placedResults().all()) V.closeViewer(row.viewer)
  for (const id of ids) V.closeViewer(id)
  if (V.maximised()) V.closeViewer(V.maximised().id)
  ids.clear(); L.clearLaunches(); M.resetPlacedResults()
}
function launch({ conversation = 'ent-origin', decision = null } = {}) {
  return L.holdLaunch({ opening: L.beginOpening(), brainKey: brain, place: { conversation, centre: null }, thread: {root:'ent-thread',at:'ent-at'}, reading: {scroll:417,offset:12}, reply:'ent-reply', draft:'thread:ent-origin:ent-thread', focus: {control:'result:'+A,fallback:{kind:'conversation'}}, decision })
}
const stillHeld = async ref => ({how:'held',file:{...HELD,ref}})
const decision = () => ({form:null,question:ASK,item:'fixture',ref:A,role:null})
function make(over = {}) {
  let at = null, conversation = 'ent-origin', pending = null, chooser
  const seen = { notices:[], centres:[], restores:[], focuses:[], returns:[], sources:[], revealed:[] }
  const guard = (go, stay = () => {}) => { if (over.asks) pending = {go,stay}; else go() }
  const page = {
    spaceKey:()=> 'https://fixture.invalid||fixture-corpus', serving:()=>brain, origin:()=> 'https://fixture.invalid', conversation:()=>conversation, centreAt:()=>at,
    enterCentre:to=>{at=to},artifactNow:stillHeld,reveal:p=>seen.revealed.push(p),
    columns:()=>[],freeColumn:()=>null,choose:q=>{chooser=q},invoker:()=>null,hasControl:()=>false,
    focus:(choice,invoker)=>seen.focuses.push({choice,invoker}),centreGo:to=>{at=to;seen.centres.push(to)},centreReplace:to=>{at=to},
    backTo:(p,done,stay)=>guard(()=>{conversation=p.conversation;at=p.centre;done()},stay),
    // F4 (adm-e2d35bd306b8): the corrected contract -- `begin()` inside the guard,
    // the reference and the report from its answer. Only these three adapters change.
    pickConversation:(c,begin,stay)=>{guard(()=>{const go=begin();if(!go)return;conversation=go.ref;go.moved()},stay);return true},
    openPost:(c,p,done,begin)=>guard(()=>{const go=begin();if(!go)return;conversation=go.ref;done('completed')},()=>done({how:'cancelled'})),
    record:(begin,stay)=>guard(()=>{const go=begin();if(!go)return;go.moved()},stay),goToPost:(c,p)=>seen.sources.push({conversation:c,post:p}),
    heldItem,putBack:s=>seen.restores.push(s),offerReturn:l=>seen.returns.push(l),say:s=>seen.notices.push(s),...over,
  }
  const m = M.mountResults(page)
  return {page,m,seen,guard, pending:()=>pending, answer:how=>{const q=pending;pending=null;q[how]()}, setAt:x=>{at=x}, chooser:()=>chooser}
}
for (const delayed of [false,true]) test('F04 exact identity mismatch refused '+(delayed?'delayed':'immediate'), async()=> {
  reset(); let answer, opened=0; const done=[]; const l=launch()
  const result=O.openResultTarget(dest(),l,{brainKey:brain,file:()=>{opened++;return 'max'},read:(_r,cb)=>{answer=cb;return delayed?{how:'reading'}:{how:'fresh',destination:dest(B)}}},{settled:o=>done.push(o)})
  if(delayed){answer({how:'fresh',destination:dest(B)});assert.equal(done[0].what,'refused')}else assert.equal(result.what,'refused')
  assert.equal(opened,0)
})
test('F01 F02 exact file source target URL and missing post compose',async()=>{
  reset();let asked=0; const x=make({postOf:()=>null,pictures:()=>{asked++;throw Error('missing post')}})
  const d=dest(A,{conversation:'ent-source',post:'ent-post'}),l=launch(); const done=[];const o=x.m.openResult(d,l,r=>done.push(r));assert.equal(o.what,'leaving');assert.equal(V.maximised(),null);await tick();const v=V.maximised()
  assert.equal(done[0].what,'opened');assert.equal(v.content.item.ref,A);assert.equal(v.content.item.url,'/api/artifacts/'+A)
  assert.deepEqual(v.source,{kind:'post',conversation:'ent-source',post:'ent-post'});assert.equal(asked,0)
  assert.deepEqual(x.seen.centres[0].result.target,{kind:'artifact',ref:A});assert.equal(x.m.results.launchOf(v.id),l)
})
test('F05 obsolete delayed read opens no viewer',async()=>{
  reset();let resolve;const done=[];const x=make({artifactNow:()=>new Promise(r=>{resolve=r})})
  x.m.openResult(dest(),launch({decision:decision()}),o=>done.push(o));launch();resolve({how:'held',file:{...HELD,ref:A}});await tick()
  assert.equal(V.maximised(),null);assert.equal(done[0].what,'refused')
})
for(const answer of ['go','stay']) test('F09 real handoff record guard '+answer,()=>{
  reset();const x=make({asks:true});let moved=false
  const record=evaluate(property('record'),{guarded:evaluate(variable('guarded'),{leaving:()=>({ask:'unsaved'}),unfinished:()=>null,setLeave:q=>{x.recordQuestion=q},setNotice:()=>{},CENTRE:'centre'}),setBrainReturn:()=>{},centre:{go:(_at,go)=>{moved=true;go()}},CENTRE:'centre'})
  const m=M.mountResults({...x.page,record}),done=[]
  const o=m.openResult({...dest(),target:{kind:'record',ref:'ent-111111111111'},opens:'record'},launch(),r=>done.push(r))
  assert.equal(o.what,'leaving');assert.equal(H.dockStep(o),'wait');assert.equal(moved,false)
  x.recordQuestion[answer]();assert.equal(done[0].what,answer==='go'?'opened':'cancelled');assert.equal(moved,answer==='go')
})
test('F09 record immediate success reports completed',()=>{
  reset();const x=make();assert.equal(x.m.openResult({...dest(),target:{kind:'record',ref:'ent-111111111111'},opens:'record'},launch()).what,'opened')
})
for(const outcome of ['completed','cancelled','failed']) test('post delayed outcome '+outcome,()=>{
  reset();let give;const done=[];const x=make({openPost:(_c,_p,cb,begin)=>{const go=begin();assert.ok(go);give=cb}})
  assert.equal(x.m.openResult({...dest(),target:{kind:'post',conversation:'ent-source',post:'ent-post'},opens:'post'},launch(),o=>done.push(o)).what,'leaving')
  give(outcome);assert.equal(done[0].what,{completed:'opened',cancelled:'cancelled',failed:'unavailable'}[outcome])
})
test('F10 source parking and live history resume use real viewer',async()=>{
  reset();const x=make(),l=launch();x.m.openResult(dest(A,{conversation:'ent-source',post:'ent-post'}),l);await tick()
  const id=V.maximised().id,intent=x.seen.centres[0];x.m.goToSource(id,{conversation:'ent-source',post:'ent-post'})
  assert.equal(V.viewerOf(id).place,'parked');assert.equal(V.maximised(),null);assert.deepEqual(x.seen.sources,[{conversation:'ent-source',post:'ent-post'}])
  x.m.applyCentre(intent);assert.equal(V.maximised().id,id);assert.equal(x.m.results.all().length,1)
})
test('F13 saved Place survives reload resolution',async()=>{
  reset();const x=make({destinationOfTarget:()=>dest()}),l=launch({conversation:'ent-saved'})
  const intent={result:{brainKey:brain,opening:l.opening,target:{kind:'artifact',ref:A},place:l.place}};L.clearLaunches()
  x.m.applyCentre(intent);await tick();const v=V.maximised();assert.ok(v);assert.deepEqual(x.m.results.launchOf(v.id).place,l.place)
})
test('F14 frame only close leaves current Place and offers return',async()=>{
  reset();const x=make(),l=launch({conversation:'ent-saved'});x.m.openResult(dest(),l);await tick();const id=V.maximised().id;x.setAt({sources:true})
  x.m.closeResult(id);assert.equal(V.viewerOf(id),undefined);assert.equal(x.seen.restores.length,0);assert.equal(x.seen.returns[0],l)
})
for(const answer of ['go','stay']) test('F15 side close '+answer,async()=>{
  reset();const x=make({asks:true,columns:()=>['s1'],freeColumn:()=> 's1'}),l=launch({conversation:'ent-saved'});x.m.openResult(dest(),l);await tick();const id=x.m.results.all()[0].viewer
  x.m.closeResult(id);assert.ok(x.pending());assert.ok(V.viewerOf(id));assert.ok(L.launchOf(l.opening));x.answer(answer)
  assert.equal(!!V.viewerOf(id),answer==='stay');assert.equal(!!L.launchOf(l.opening),answer==='stay')
})
test('F16 departing result removes no-column overlay',async()=>{
  reset();const x=make(),l=launch();x.m.openResult(dest(),l);await tick();const id=V.maximised().id
  assert.equal(x.m.applyCentre(null),false);assert.equal(V.viewerOf(id),undefined);assert.equal(L.launchOf(l.opening),null)
})
test('N2 two viewer close uses own invoker',async()=>{
  reset();let invoker={isConnected:true,name:'first'};const x=make({columns:()=>['s1','s2'],freeColumn:()=> 's1',invoker:()=>invoker})
  x.m.openResult(dest(),launch());await tick();const first=x.m.results.all()[0].viewer;invoker={isConnected:true,name:'second'};x.m.openResult(dest(B),launch());await tick();x.m.closeResult(first)
  assert.equal(x.seen.focuses[0].invoker.name,'first')
})
for(const how of ['cancelled','s2']) test('chooser settles '+how,async()=>{
  reset();const x=make({columns:()=>['s1','s2']}),done=[];assert.equal(x.m.openResult(dest(),launch(),o=>done.push(o)).what,'leaving');assert.equal(done.length,0);await tick();assert.equal(done.length,0)
  x.chooser().decide(how);assert.equal(done[0].what,how==='cancelled'?'cancelled':'opened')
})
// Same original refusals, now asserting after the real asynchronous read settles.
for(const surface of ['chooser','Brain','Latest']) test('B4.1 fresh availability required for '+surface,async()=>{
  reset();let reads=0;const done=[];const x=make({artifactNow:async()=>{reads++;return {how:'gone',availability:'purged',why:'Purged'}}})
  assert.equal(x.m.openResult(dest(),launch(),o=>done.push(o)).what,'leaving');assert.equal(done.length,0);assert.equal(V.maximised(),null);await tick()
  assert.equal(reads,1);assert.equal(done[0].what,'unavailable');assert.equal(done.length,1);assert.equal(V.maximised(),null);assert.equal(x.seen.centres.length,0)
})
for(const failure of ['401','missing-ref','network']) test('B4.1 fresh read '+failure+' must not reopen stale descriptor',async()=>{
  reset();const done=[]
  const fetch_=async()=>{if(failure==='network')throw Error('offline');return {ok:failure!=='401',status:failure==='401'?401:200,json:async()=>({about:[{id:ASK,subject:[]}]})}}
  const x=make({artifactNow:id=>R.artifactNow(id,fetch_)});assert.equal(x.m.openResult(dest(),launch({decision:decision()}),o=>done.push(o)).what,'leaving');await tick()
  assert.equal(done[0].what,'unavailable');assert.equal(done.length,1);assert.equal(V.maximised(),null);assert.equal(x.seen.centres.length,0)
})
test('F19 positive fresh explicit unavailable prevents opening',async()=>{
  reset();const done=[],x=make({artifactNow:async()=>({how:'gone',availability:'purged',why:'Purged'})})
  x.m.openResult(dest(),launch({decision:decision()}),o=>done.push(o));await tick();assert.equal(done[0].what,'unavailable');assert.equal(V.maximised(),null)
})
test('B4.1 delayed fresh success must open without optional notification callback',async()=>{
  reset();let answer;const x=make({artifactNow:()=>new Promise(r=>{answer=r})})
  assert.equal(x.m.openResult(dest(),launch({decision:decision()})).what,'leaving');assert.equal(V.maximised(),null);answer({how:'held',file:{...HELD,ref:A}});await tick()
  assert.ok(V.maximised());assert.equal(x.seen.centres.length,1)
})
function historyFixture({unfinished=true}={}) {
  reset();globalThis.reviewEffects=[];const listeners=new Map(),states=[null];let index=0,left=false,centre,x
  globalThis.history={get state(){return states[index]},replaceState:s=>{states[index]=s},pushState:s=>{states.splice(index+1);states.push(s);index++},go:n=>{const next=index+n;if(next<0||next>=states.length){left=true;return};index=next;const state=states[index];queueMicrotask(()=>listeners.get('popstate')?.({state}))}}
  globalThis.window={addEventListener:(k,f)=>listeners.set(k,f),removeEventListener:()=>{},setTimeout:()=>0}
  x=make();const at={current:null};let asks=0,pending=null
  const guarded=evaluate(variable('guarded'),{leaving:()=>({ask:unfinished?{title:'unfinished'}:null}),unfinished:()=>null,setLeave:q=>{asks++;pending=q},setNotice:()=>{},CENTRE:'centre'})
  x.page.centreAt=()=>at.current;x.page.enterCentre=evaluate(property('enterCentre'),{centreAt:at})
  const Rproxy={applyCentre:to=>x.m.applyCentre(to)}
  centre=usePlaces({c:'ent-origin',at:null},{apply:evaluate(variable('applyCentre'),{R:Rproxy,brainLeft:{current:null},document:{querySelector:()=>null},setUnread:()=>{},keepBrainCard:{current:false},setBrainOpen:()=>{},setSourcesOpen:()=>{},setSourcesWanted:()=>{},sourcesRead:{reload:()=>{}},spaceRef:{current:{apply:()=>null}},setBrainMain:()=>{},setSourceMain:()=>{},setSourceLast:()=>{}}),show:()=>{},ask:()=>false,address:()=>null})
  for(const effect of globalThis.reviewEffects)effect()
  x.page.centreGo=evaluate(property('centreGo'),{centre});x.page.centreReplace=evaluate(property('centreReplace'),{centre});x.page.backTo=evaluate(property('backTo'),{centre,guarded,CENTRE:'centre'})
  x.m=M.mountResults(x.page)
  return {...x,centre,at,asks:()=>asks,states,index:()=>index,left:()=>left,question:()=>pending,answer:how=>{const q=pending;pending=null;q[how]?.()}}
}
test('B4.2 documented apply preserves centreAt identity',async()=>{
  const x=historyFixture(),l=launch();x.m.openResult(dest(),l);await tick()
  assert.equal(x.at.current?.result?.opening,l.opening);assert.equal(history.state.q2c.at.result.opening,l.opening)
})
test('B4.3 maximised close asks before actual history back and Stay retains all',async()=>{
  const x=historyFixture(),l=launch();x.m.openResult(dest(),l);await tick();const id=V.maximised().id
  x.m.closeResult(id);await tick();assert.equal(x.asks(),1);assert.ok(x.question());assert.ok(V.viewerOf(id));assert.ok(L.launchOf(l.opening));assert.equal(x.index(),1);assert.deepEqual(x.seen.restores,[])
  x.answer('stay');await tick();assert.ok(V.viewerOf(id));assert.ok(L.launchOf(l.opening));assert.equal(x.index(),1);assert.deepEqual(x.seen.restores,[])
})
test('B4.4 saved re-resolution replaces; Back leaves',async()=>{
  const x=historyFixture({unfinished:false});x.page.destinationOfTarget=()=>dest();x.m=M.mountResults(x.page)
  const stored={result:{brainKey:brain,opening:91,target:{kind:'artifact',ref:A},place:{conversation:'ent-saved',centre:null}}}
  x.centre.replace(stored);assert.equal(V.maximised(),null);await tick()
  assert.equal(x.states.length,1);assert.equal(x.index(),0);assert.ok(V.maximised());assert.deepEqual(history.state.q2c.at.result.place,stored.result.place)
  const opening=L.latestOpening();history.go(-1);await tick();assert.equal(x.left(),true);assert.equal(L.latestOpening(),opening)
})
test('N3 ordinary maximised close retains baseline reveal-source convenience',()=>{
  reset();const x=make(),id=V.openViewer({kind:'file',item:heldItem(A,HELD)},{kind:'post',conversation:'ent-source',post:'ent-post'},'max');ids.add(id)
  const sf=ts.createSourceFile('baseline.tsx',baseline,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);let expr
  function visit(n){if(ts.isPropertyAssignment(n)&&n.name.getText(sf)==='close'&&n.initializer.getText(sf).includes('revealPost(post.post)'))expr=n.initializer.getText(sf);ts.forEachChild(n,visit)}visit(sf);assert.ok(expr)
  const revealed=[];evaluate(expr,{v:V.viewerOf(id),post:{post:'ent-post'},closeViewer:()=>{},requestAnimationFrame:f=>f(),revealPost:p=>revealed.push(p)})();assert.deepEqual(revealed,['ent-post']);revealed.length=0
  x.m.closeResult(id);assert.equal(V.viewerOf(id),undefined);assert.deepEqual(x.seen.revealed,['ent-post'])
})
test('bounded existing artifact describe route exists and is used already',()=>{
  const web=readFileSync(new URL('../../../mentis/web/__init__.py',import.meta.url),'utf8')
  const composer=readFileSync(new URL('../src/fluid/Composer.tsx',import.meta.url),'utf8')
  assert.match(web,/describe="describe=1"/);assert.match(web,/_artifacts.public\(_artifacts.describe/)
  assert.match(composer,/describe=1/)
})
