// Independently authored safety probes. Each invocation has a fresh REAL page
// binding. The retained reviewer fixture supplies only synthetic React/history
// infrastructure. No serving override is supplied to mountResults.
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
/* THE IDENTITY ROUTE IS NOT THE ARTIFACT READ (correction of adm-e2d35bd306b8).
   A press refused for want of a confirmed Brain now asks `/fluid/api/needs-you/brain`
   once, which this stub would otherwise have counted as a freshness read of the
   artifact. It is answered 503, so the page stays exactly as unbound as the
   scenario intends, and it is counted separately instead. */
const BRAIN_ROUTE='/fluid/api/needs-you/brain'
let identityAsks=0
if(scenario.reader==='default'){
  x.page.artifactNow=undefined
  globalThis.fetch=(url,options)=>{
    if(url===BRAIN_ROUTE&&scenario.initial!=='startup'){identityAsks++;return Promise.resolve(new Response('',{status:503}))}
    reads++;requests.push({url,options});return g.promise.then(()=>{
    const response=new Response(JSON.stringify(described),{status:200,headers:{'Content-Type':'application/json'}})
    const json=response.json.bind(response)
    response.json=async()=>{const body=await json();parsed.resolve();return body}
    return response
  })}
}
/* and for a scenario whose reader is injected, the recovery ask has no stub at
   all unless one is given: answer it the same way, so nothing reaches a server */
if(scenario.reader!=='default'&&scenario.initial!=='startup'){
  globalThis.fetch=(url)=>{
    if(url===BRAIN_ROUTE){identityAsks++;return Promise.resolve(new Response('',{status:503}))}
    return Promise.reject(Error('no fetch in this scenario: '+url))
  }
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
if(scenario.initial==='startup'){
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
}
let launch,immediate
const initialHistory=JSON.stringify(x.states)
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
if(scenario.phase==='chooser'){g.resolve({how:'held',file:described});if(scenario.reader==='default' && immediate?.what!=='refused')await parsed.promise;await tick();if(immediate?.what!=='refused')assert.ok(x.chooser(),'known press must still create chooser before transition');else assert.equal(x.chooser(),undefined,'refused press creates no chooser')}
const generation=M.centreGeneration(),before=snapshot(),oldPage=x.page
await move(scenario.transition)
// Construct the next render with the exact handoff expression, while OLD
// pending read/chooser closures retain the previous object and graph getter.
const nextGraph=spaceBrainKey({origin:'https://fixture.invalid',proxy:null,corpusId:scenario.transition==='corpus'?'other-corpus':'fixture-corpus'})
x.page={...oldPage,spaceKey:evaluate(property('spaceKey'),{brain:{key:nextGraph}})}
x.m=M.mountResults(x.page)
assert.equal(M.centreGeneration(),generation,'render alone must not fake a centre move')
if(scenario.phase==='chooser'){if(immediate?.what!=='refused')x.chooser().decide(scenario.where)}
else {g.resolve({how:'held',file:described});if(scenario.reader==='default' && immediate?.what!=='refused')await parsed.promise;await tick()}
await tick()
if(startupConfirm){startupConfirm.resolve(new Response('',{status:503}));await tick()}
const rows=x.m.results.all()
const trace={scenario,serving:S.servingBrainKey(),bound:page.bound(),moved:page.moved(),launch:launch?.brainKey,
  graph,graphOtherInstance:spaceBrainKey({origin:'https://fixture.invalid',proxy:null,corpusId:'fixture-corpus',instance:'instance-2'}),
  reads,identityAsks,recorded,immediate,settled,placements,requests,placed:rows.map(row=>({where:row.where,ref:V.viewerOf(row.viewer)?.content.item.ref,launch:x.m.results.launchOf(row.viewer)?.brainKey})),
  entry:history.state?.q2c?.at,generationBefore:generation,generationAfter:M.centreGeneration(),notices:x.seen.notices}
console.log(JSON.stringify(trace))
if(scenario.kind!=='saved' && ['unbound','moved','startup'].includes(scenario.initial)){
  assert.equal(immediate.what,'refused','unidentified press must refuse synchronously')
  assert.equal(reads,0,'refused press sends no artifact read')
  assert.deepEqual(x.seen.notices,[scenario.initial==='moved'?L.BRAIN_MOVED:L.BRAIN_UNCONFIRMED])
  assert.equal(JSON.stringify(x.states),initialHistory,'refused press must preserve complete history')
  assert.equal(recorded,0)
  assert.deepEqual(settled,[],'synchronous refusal emits no later completion')
  /* ADDED: and the recovery ask is exactly one, or none where asking could not
     help -- a moved page is never asked, because only a reload binds it. */
  assert.ok(identityAsks<=1,'at most one identity ask per refused press')
  if(scenario.initial==='moved') assert.equal(identityAsks,0,'a moved page is never asked again')
}
if(scenario.expect==='open'){
  assert.equal(rows.length,1,'same known binding must retain normal opening')
  assert.equal(V.viewerOf(rows[0].viewer).content.item.ref,A)
  assert.equal(page.moved(),false)
  if(scenario.kind==='saved') assert.equal(x.states.length,2,'resume replaces in place')
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
