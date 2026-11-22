// THE REVIEWER'S OWN SCENARIO (review/binding-scenario.mjs, independent review
// adm-1cb30e65d05f), with its SAFETY ORACLE UNCHANGED and three instrumentation
// changes, each of which the correction itself forced:
//
//   1. `assert.ok(x.chooser(),'chooser must exist before transition')` was a
//      PRECONDITION of the defect: the press reached a chooser because nothing
//      refused it. A press made with no confirmed identity is now refused
//      before any read, so there is no chooser to answer -- a stronger closed
//      outcome than the one the scenario was written to catch. The precondition
//      is kept for the arms that must still open, and recorded (not asserted)
//      for the arms that must not.
//   2. `await parsed.promise` is the default reader's own parse barrier; with
//      no press there is no fetch, so it never settles and the process exits 13
//      on an unfinished await. It is awaited only where a fetch actually
//      happened; `reads` is in the trace so the evidence says which.
//   3. Two expectations are ADDED, for preservation rather than safety:
//      `navigated` (the record route under a confirmed identity must still
//      navigate) and `initial:'startup-bound'` (the real startup window must
//      refuse and then, once the real confirmation lands, open normally).
//
// Everything else -- the real page binding, the real confirmBrain, the real
// loadBrain, the exact handoff expressions, the store observation through
// page.invoker, the history snapshot comparison -- is the reviewer's, byte for
// byte. The final assertions are unchanged.
import assert from 'node:assert/strict'
import { M,L,V,HELD,A,brain,dest,tick,reset,historyFixture,property,variable,evaluate } from './fixture.mjs'
const {page,confirmBrain,brainKeyOf} = await import('../src/brainBinding.ts')
const S = await import('../src/quiet2/results/serving.ts')
const {spaceBrainKey} = await import('../src/quiet2/space/registry.ts')
const scenario=JSON.parse(process.argv[2])
const k1=brain,k2='fixture-corpus@instance-2',other='other-corpus@instance-1'
const graph=spaceBrainKey({origin:'https://fixture.invalid',proxy:null,corpusId:'fixture-corpus'})
const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve}}
const described={...HELD,ref:A,treatment:{view:'text'}}
let reads=0,g=deferred(),recorded=0,parsed=deferred()
const placements=[],settled=[],requests=[]
const x=historyFixture({unfinished:false})
Object.assign(x.page,{
  serving:undefined,
  spaceKey:evaluate(property('spaceKey'),{brain:{key:graph}}),
  destinationOfTarget:()=>dest(),
  artifactNow:()=>{reads++;return g.promise},
  columns:()=>scenario.phase==='chooser'?['s1','s2']:scenario.where==='max'?[]:['s1','s2'],
  freeColumn:()=>scenario.phase==='chooser'?null:scenario.where==='s1'?'s1':null,
  invoker:()=>{const v=V.maximised()??V.inColumn('s1');placements.push({where:v?.place,ref:v?.content.item.ref});return null},
})
if(scenario.reader==='default'){
  x.page.artifactNow=undefined
  globalThis.fetch=(url,options)=>{reads++;requests.push({url,options});return g.promise.then(()=>{
    const response=new Response(JSON.stringify(described),{status:200,headers:{'Content-Type':'application/json'}})
    const json=response.json.bind(response)
    response.json=async()=>{const body=await json();parsed.resolve();return body}
    return response
  })}
}
x.page.leaveOn=evaluate(property('leaveOn'),{realId:'ent-origin',centre:x.centre,pickConversation:()=>assert.fail('unexpected cross-conversation move')})
x.m=M.mountResults(x.page)
const launchNow=evaluate(variable('launchNow'),{
  beginOpening:L.beginOpening,holdLaunch:L.holdLaunch,servingBrainKey:S.servingBrainKey,
  realId:'ent-origin',centreAt:x.at,entered:null,enteredAt:null,left:{current:null},
  document:{querySelector:()=>null},replyTo:null,mainPlace:'conversation:ent-origin',
})
const bind=async(key)=>{
  // Exercise the real confirmBrain -> singleton.saw path, with synthetic HTTP.
  const [corpus_id,instance]=key.split('@')
  const answer=await confirmBrain(async()=>new Response(JSON.stringify({brain:{corpus_id,instance}}),{status:200,headers:{'Content-Type':'application/json'}}))
  assert.equal(brainKeyOf({corpus_id,instance}),key)
  return answer
}
const move=async(mode)=>{
  if(mode==='instance') await bind(k2)
  else if(mode==='corpus') await bind(other)
  else if(mode==='move') page.move()
  else if(mode==='bind') await bind(k2)
  else if(mode==='bind-move'){await bind(k1);await bind(k2)}
}
if(scenario.initial==='bound') await bind(k1)
if(scenario.initial==='second') await bind(k2)
if(scenario.initial==='moved'){await bind(k1);await bind(k2)}
if(scenario.initial==='unbound') assert.equal(page.bound(),null)
let startupConfirm
if(scenario.initial==='startup'||scenario.initial==='startup-bound'){
  // The actual ready path resolves before confirmBrain does. Keep that
  // confirmation outstanding while the result press runs, then finish it.
  startupConfirm=deferred()
  const artifactFetch=globalThis.fetch
  globalThis.fetch=(url,options)=>url==='/__q2/brain'?Promise.resolve(new Response('',{status:404}))
    :url==='/fluid/api/needs-you/brain'?startupConfirm.promise:artifactFetch(url,options)
  globalThis.location={origin:'https://fixture.invalid'}
  window.fetch=globalThis.fetch
  const {loadBrain}=await import('../src/quiet2/live.ts')
  await loadBrain()
  assert.equal(page.bound(),null,'real loadBrain has completed before its confirmBrain')
  if(scenario.initial==='startup-bound'){
    // AND THEN THE REAL CONFIRMATION LANDS, through the real confirmBrain the
    // real loadBrain already started: the startup window is a window, not a
    // page that can never open a result again.
    startupConfirm.resolve(new Response(JSON.stringify({brain:{corpus_id:'fixture-corpus',instance:'instance-1'}}),{status:200,headers:{'Content-Type':'application/json'}}))
    for(let i=0;i<20&&page.bound()===null;i++) await tick()
    assert.equal(page.bound(),k1,'the real confirmation binds the page before the press')
    startupConfirm=undefined
  }
}
let launch,immediate,chooserOpened=false
const snapshot=()=>JSON.stringify(x.states)
if(scenario.kind==='saved'){
  const key=scenario.saved==='null'?null:k1
  x.centre.go({result:{brainKey:key,opening:91,target:{kind:'artifact',ref:A},place:{conversation:'ent-origin',centre:null}}})
} else {
  launch=launchNow({control:'open:'+A,fallback:{kind:'conversation'}})
  assert.equal(launch.brainKey,S.servingBrainKey())
  if(scenario.kind==='record'){
    const real=evaluate(property('record'),{guarded:go=>go(),setBrainReturn:()=>{},centre:x.centre,CENTRE:'centre'})
    x.page.record=(...args)=>{recorded++;return real(...args)};x.m=M.mountResults(x.page)
    immediate=x.m.openResult({...dest(),target:{kind:'record',ref:'ent-111111111111'},opens:'record'},launch)
  } else immediate=x.m.openResult(dest(),launch,o=>settled.push(o))
}
if(scenario.phase==='chooser'){
  g.resolve({how:'held',file:described})
  if(scenario.reader==='default'&&reads)await parsed.promise
  await tick()
  chooserOpened=!!x.chooser()
  // (1) above: a press that must still open must still reach its chooser.
  if(scenario.expect==='open')assert.ok(chooserOpened,'a press under a confirmed identity must still reach its chooser')
}
const generation=M.centreGeneration(),before=snapshot(),oldPage=x.page
await move(scenario.transition)
// Construct the next render with the exact handoff expression, while OLD
// pending read/chooser closures retain the previous object and graph getter.
const nextGraph=spaceBrainKey({origin:'https://fixture.invalid',proxy:null,corpusId:scenario.transition==='corpus'?'other-corpus':'fixture-corpus'})
x.page={...oldPage,spaceKey:evaluate(property('spaceKey'),{brain:{key:nextGraph}})}
x.m=M.mountResults(x.page)
assert.equal(M.centreGeneration(),generation,'render alone must not fake a centre move')
if(scenario.phase==='chooser'){if(chooserOpened) x.chooser().decide(scenario.where)}
else {g.resolve({how:'held',file:described});if(scenario.reader==='default'&&reads)await parsed.promise;await tick()}
await tick()
if(startupConfirm){startupConfirm.resolve(new Response('',{status:503}));await tick()}
const rows=x.m.results.all()
const trace={scenario,serving:S.servingBrainKey(),state:S.servingNow(),bound:page.bound(),moved:page.moved(),launch:launch?.brainKey,
  graph,graphOtherInstance:spaceBrainKey({origin:'https://fixture.invalid',proxy:null,corpusId:'fixture-corpus',instance:'instance-2'}),
  reads,recorded,chooserOpened,immediate,settled,placements,requests,placed:rows.map(row=>({where:row.where,ref:V.viewerOf(row.viewer)?.content.item.ref,launch:x.m.results.launchOf(row.viewer)?.brainKey})),
  entry:history.state?.q2c?.at,generationBefore:generation,generationAfter:M.centreGeneration(),notices:x.seen.notices}
console.log(JSON.stringify(trace))
// AND IT IS SAID, ONCE, IN THE RIGHT WORDS. Added to the reviewer's oracle
// rather than replacing any of it: a press made with no confirmed identity
// must be refused ON THE PRESS and the reader told which state the page is in
// -- not left with a control that silently does nothing.
if(scenario.kind!=='saved'&&['unbound','moved','startup'].includes(scenario.initial)){
  assert.equal(immediate.what,'refused','a press with no confirmed identity is refused on the press itself')
  assert.deepEqual(x.seen.notices,[scenario.initial==='moved'?L.BRAIN_MOVED:L.BRAIN_UNCONFIRMED],
    'and the reader is told which, once, in the words for that state')
}
if(scenario.expect==='open'){
  assert.equal(rows.length,1,'same known binding must retain normal opening')
  assert.equal(V.viewerOf(rows[0].viewer).content.item.ref,A)
  assert.equal(page.moved(),false)
  if(scenario.kind==='saved') assert.equal(x.states.length,2,'resume replaces in place')
}else if(scenario.expect==='navigated'){
  // (3) above: PRESERVATION. The record route under a confirmed identity still
  // navigates and still reports the arrival its guard actually made.
  assert.equal(recorded,1,'a known launch must still navigate to the record')
  assert.equal(immediate.what,'opened')
  assert.equal(rows.length,0,'and a record navigation places no viewer')
}else if(scenario.kind==='record'){
  assert.equal(recorded,0,'unknown or moved launch must not navigate to Brain content')
  assert.notEqual(immediate.what,'opened')
}else{
  assert.equal(rows.length,0,'unknown, moved or changed binding must place no content')
  assert.equal(placements.length,0,'even an immediately discarded maximised viewer is a placement, not a closed gate')
  assert.equal(settled.filter(o=>o.what==='opened').length,0,'a refused placement must not report opened')
  if(scenario.transition) assert.equal(snapshot(),before,'late completion must not relabel history')
}
assert.equal(graph,trace.graphOtherInstance,'graph instance omission is preserved, serving identity must do the comparing')
