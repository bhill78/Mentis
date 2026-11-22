// Reviewer additions for 9118db60. Uses the retained reviewer fixture, not Builder tests.
import test from 'node:test'
import assert from 'node:assert/strict'
import { M,L,V,R,HELD,A,B,brain,dest,tick,reset,launch,make,historyFixture,property,evaluate } from './fixture.mjs'
const {createBinding} = await import('../src/brainBinding.ts')
const {spaceBrainKey} = await import('../src/quiet2/space/registry.ts')
const file = id => ({...HELD,ref:id,treatment:{view:'text'}})
const held = id => ({how:'held',file:file(id)})
const saved = (id=A,key=brain,opening=91) => ({result:{brainKey:key,opening,target:{kind:'artifact',ref:id},place:{conversation:'ent-origin',centre:null}}})
const gate = () => {let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b});return {promise,resolve,reject}}
function prepare(over={}) { const x=historyFixture({unfinished:false});Object.assign(x.page,{destinationOfTarget:t=>dest(t.ref)},over.brainKey ? {...over,serving:over.brainKey} : over);x.m=M.mountResults(x.page);return x }
function quiet(x) {assert.equal(V.maximised(),null);assert.equal(x.m.results.all().length,0);assert.deepEqual(x.seen.notices,[])}

for (const outcome of ['held','gone','reject']) test('R1 read '+outcome+' after Back across a fresh mount closure', async()=>{
  const g=gate(),x=prepare({artifactNow:()=>g.promise});x.centre.go(saved());await tick()
  const old=x.m;x.m=M.mountResults({...x.page});assert.notEqual(old,x.m)
  history.go(-1);await tick();const before=JSON.stringify(x.states)
  if(outcome==='reject')g.reject(Error('fixture network loss'))
  else g.resolve(outcome==='held'?held(A):{how:'gone',why:'fixture purged'})
  await tick();quiet(x);assert.equal(JSON.stringify(x.states),before);assert.equal(x.index(),0)
})
for (const order of [[0,1],[1,0]]) test('R1 overlapping Forward reads resolved in order '+order,async()=>{
  const gates=[],x=prepare({artifactNow:()=>{const g=gate();gates.push(g);return g.promise}})
  x.centre.go(saved());history.go(-1);await tick();history.go(1);await tick()
  assert.equal(gates.length,2)
  for(const i of order){gates[i].resolve(held(A));await tick();if(i===0&&order[0]===0)quiet(x)}
  assert.equal(x.index(),1);assert.equal(x.states.length,2);assert.equal(x.m.results.all().length,1)
  assert.equal(V.maximised().content.item.ref,A);assert.equal(history.state.q2c.at.result.opening,L.latestOpening())
})
test('R1 late read cannot replace a newer non-result centre entry',async()=>{
  const g=gate(),x=prepare({artifactNow:()=>g.promise});x.centre.go(saved());await tick()
  const record={brain:{stack:[{page:'record',entry:'ent-synthetic'}],origin:{from:'link'}}}
  x.centre.go(record);const before=JSON.stringify(x.states);g.resolve(held(A));await tick()
  quiet(x);assert.deepEqual(history.state.q2c.at,record);assert.equal(JSON.stringify(x.states),before)
})
for (const where of ['max','s1','s2']) test('R1 late chooser '+where+' after actual Back places nothing',async()=>{
  const x=prepare({columns:()=>['s1','s2']});x.centre.go(saved());await tick();const q=x.chooser();assert.ok(q)
  history.go(-1);await tick();const before=JSON.stringify(x.states);q.decide(where);await tick()
  quiet(x);assert.equal(x.index(),0);assert.equal(JSON.stringify(x.states),before)
})
for (const key of ['fixture-corpus@instance-2','different-corpus@instance-1',null]) {
  test('R1 read drops on live Brain getter change to '+key,async()=>{
    let current=brain;const g=gate(),x=prepare({brainKey:()=>current,artifactNow:()=>g.promise})
    x.centre.go(saved());await tick();const gen=M.centreGeneration(),before=JSON.stringify(x.states)
    current=key;g.resolve(held(A));await tick();quiet(x);assert.equal(M.centreGeneration(),gen);assert.equal(JSON.stringify(x.states),before)
  })
  test('R1 chooser drops on live Brain getter change to '+key,async()=>{
    let current=brain;const x=prepare({brainKey:()=>current,columns:()=>['s1','s2']})
    x.centre.go(saved());await tick();const gen=M.centreGeneration(),before=JSON.stringify(x.states)
    current=key;x.chooser().decide('max');await tick();quiet(x);assert.equal(M.centreGeneration(),gen);assert.equal(JSON.stringify(x.states),before)
  })
}
for (const changed of [saved(A,brain,92),saved(B,brain,91)]) test('R1 exact saved opening/target arm '+JSON.stringify(changed.result.target)+'/'+changed.result.opening,async()=>{
  reset();const g=gate(),x=make({artifactNow:()=>g.promise,destinationOfTarget:()=>dest()})
  x.m.applyCentre(saved());const gen=M.centreGeneration();x.setAt(changed);g.resolve(held(A));await tick()
  quiet(x);assert.equal(M.centreGeneration(),gen);assert.deepEqual(x.page.centreAt(),changed)
})

// Cases 18-20 independently rebuilt in binding-scenario.mjs.
for (const mode of ['invoker','control','fallback']) test('N2 focus recalculated AFTER guarded restore: '+mode,async()=>{
  const x=historyFixture(),focused=[],invoker={isConnected:true,focus:()=>focused.push('invoker')};let connectedControl=false
  x.page.invoker=()=>invoker;x.page.hasControl=()=>connectedControl
  const exact=evaluate(property('focus'),{document:{querySelector:()=>({focus:()=>focused.push('control')})},CSS:{escape:s=>s},focusFallback:f=>focused.push(f.kind)})
  x.page.focus=(choice,el)=>{assert.equal(x.m.results.all().length,0);exact(choice,el)}
  x.page.putBack=s=>{if(s.do==='reading'&&mode!=='invoker'){invoker.isConnected=false;connectedControl=mode==='control'}}
  x.m=M.mountResults(x.page);x.m.openResult(dest(),launch());await tick();x.m.closeResult(V.maximised().id)
  assert.equal(x.asks(),1);assert.deepEqual(focused,[]);assert.ok(V.maximised());x.answer('go');await tick()
  assert.deepEqual(focused,[mode==='fallback'?'conversation':mode]);assert.equal(x.index(),0)
})
test('N2 Stay preserves viewer and invokes no focus',async()=>{
  const x=historyFixture(),invoker={isConnected:true};x.page.invoker=()=>invoker;x.m=M.mountResults(x.page)
  x.m.openResult(dest(),launch());await tick();const id=V.maximised().id;x.m.closeResult(id);x.answer('stay');await tick()
  assert.ok(V.viewerOf(id));assert.equal(x.seen.focuses.length,0);assert.equal(x.m.results.invokerOf(id),invoker)
})
for (const identity of [undefined,null,23,{},[],true,'',B,A+' ']) test('N5 held exact identity rejects '+JSON.stringify(identity),async()=>{
  reset();const body=file(A);if(identity===undefined)delete body.ref;else body.ref=identity
  const seen=[],x=make({artifactNow:id=>R.artifactNow(id,async()=>({ok:true,status:200,json:async()=>body}))})
  x.m.openResult(dest(),launch(),o=>seen.push(o));await tick();quiet({...x,seen:{...x.seen,notices:[]}})
  assert.deepEqual(seen.map(o=>o.what),['unavailable']);assert.equal(x.seen.centres.length,0)
})
test('N5 equal exact identity succeeds using verified bytes treatment',async()=>{
  reset();const seen=[],x=make({artifactNow:id=>R.artifactNow(id,async()=>({ok:true,status:200,json:async()=>file(A)}))})
  x.m.openResult(dest(),launch(),o=>seen.push(o));await tick();assert.deepEqual(seen.map(o=>o.what),['opened']);assert.equal(V.maximised().content.item.ref,A)
})
