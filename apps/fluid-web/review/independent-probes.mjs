import test from 'node:test'
import assert from 'node:assert/strict'
import {M,L,V,R,HELD,A,B,brain,dest,ref,tick,reset,launch,make,historyFixture,property,evaluate} from './fixture.mjs'

const response=(body,status=200)=>({ok:status>=200&&status<300,status,json:async()=>body})
const described={...HELD,ref:A,treatment:{view:'text'}}
for(const status of [401,403,404,500]) test('new refusal HTTP '+status+' with plausible held body still opens nothing',async()=>{
  reset();const done=[],x=make({artifactNow:id=>R.artifactNow(id,async()=>response(described,status))})
  assert.equal(x.m.openResult(dest(),launch(),o=>done.push(o)).what,'leaving');await tick()
  assert.deepEqual(done.map(o=>o.what),['unavailable']);assert.equal(V.maximised(),null);assert.equal(x.seen.centres.length,0)
})
for(const state of ['unknown','purged','held-but-missing','held-but-corrupt','not-held']) test('new refusal 200 '+state,async()=>{
  reset();const done=[],x=make({artifactNow:id=>R.artifactNow(id,async()=>response({...described,state}))})
  x.m.openResult(dest(),launch(),o=>done.push(o));await tick();assert.deepEqual(done.map(o=>o.what),['unavailable']);assert.equal(V.maximised(),null)
})
for(const body of [null,{},'held',{...described,ref:B}]) test('new refusal malformed or other description '+JSON.stringify(body),async()=>{
  reset();const done=[],x=make({artifactNow:id=>R.artifactNow(id,async()=>response(body))})
  x.m.openResult(dest(),launch(),o=>done.push(o));await tick();assert.deepEqual(done.map(o=>o.what),['unavailable']);assert.equal(V.maximised(),null)
})
test('new production reader path uses exact GET/no-store and fresh treatment overrides stale item',async()=>{
  reset();let fetched;const saved=globalThis.fetch
  globalThis.fetch=async(url,opts)=>{fetched={url,opts};return response(described)}
  try{
    const x=make({artifactNow:undefined}),done=[];const d=dest(A,{conversation:'ent-src',post:'ent-exact'});d.item={ref:A,view:'image',url:'/stale'}
    const l=launch();assert.equal(x.m.openResult(d,l,o=>done.push(o)).what,'leaving');assert.equal(V.maximised(),null);await tick()
    assert.equal(fetched.url,'/api/artifacts/'+A+'?describe=1');assert.equal(fetched.opts.cache,'no-store');assert.equal(fetched.opts.headers['X-Mentis-Client'],'1')
    assert.equal(V.maximised().content.item.kind,'text');assert.equal(V.maximised().content.item.treatment,'text');assert.equal(V.maximised().content.item.ref,A);assert.equal(V.maximised().content.item.url,'/api/artifacts/'+A)
    assert.deepEqual(V.maximised().source,{kind:'post',conversation:'ent-src',post:'ent-exact'});assert.deepEqual(done.map(o=>o.what),['opened'])
  }finally{globalThis.fetch=saved}
})
test('new async chooser completes without observer',async()=>{
  reset();const x=make({columns:()=>['s1']});x.m.openResult(dest(),launch());await tick();assert.ok(x.chooser());assert.equal(x.m.results.all().length,0)
  x.chooser().decide('s1');assert.equal(x.m.results.all().length,1)
})
for(const go of ['go','stay']) test('new guarded replace return path '+go,async()=>{
  const x=historyFixture(),l=launch({conversation:'ent-not-behind'});x.m.openResult(dest(),l);await tick();const id=V.maximised().id
  x.m.closeResult(id);assert.equal(x.asks(),1);assert.equal(x.index(),1);x.answer(go);await tick()
  if(go==='stay'){assert.ok(V.viewerOf(id));assert.ok(L.launchOf(l.opening));assert.deepEqual(x.seen.restores,[])}
  else{assert.equal(V.viewerOf(id),undefined);assert.equal(x.states.length,2);assert.equal(x.index(),1);assert.equal(history.state.q2c.c,'ent-not-behind');assert.equal(history.state.q2c.at,null);assert.equal(x.asks(),1);assert.deepEqual(x.seen.restores.map(s=>s.do),['thread','reading','reply','draft'])}
})
test('new saved Forward re-resolves in place, Back returns and Forward repeats without added entries',async()=>{
  const x=historyFixture({unfinished:false});x.page.destinationOfTarget=()=>dest();x.m=M.mountResults(x.page)
  const stored={result:{brainKey:brain,opening:91,target:{kind:'artifact',ref:A},place:{conversation:'ent-origin',centre:null}}}
  x.centre.go(stored);await tick();assert.equal(x.states.length,2);assert.equal(x.index(),1);assert.ok(V.maximised())
  for(let i=0;i<2;i++){history.go(-1);await tick();assert.equal(x.index(),0);assert.equal(V.maximised(),null);history.go(1);await tick();assert.equal(x.index(),1);assert.equal(x.states.length,2);assert.ok(V.maximised());assert.equal(V.maximised().content.item.ref,A)}
})
test('new changed-Brain saved Forward is refused',async()=>{
  const x=historyFixture({unfinished:false});let reads=0;x.page.destinationOfTarget=()=>dest();x.page.artifactNow=async()=>{reads++;return {how:'held',file:described}};x.m=M.mountResults(x.page)
  x.centre.go({result:{brainKey:'fixture-corpus@different-instance',opening:91,target:{kind:'artifact',ref:A},place:{conversation:'ent-origin',centre:null}}});await tick()
  assert.equal(reads,0);assert.equal(V.maximised(),null);assert.ok(x.seen.notices.length)
})
test('new N3 no source reveal on ordinary column or Brain viewer',()=>{
  for(const [where,source] of [['s1',{kind:'post',conversation:'ent-source',post:'ent-post'}],['max',{kind:'brain',brainKey:brain}]]){
    reset();const x=make();const id=V.openViewer({kind:'file',item:{ref:A,view:'text',url:'/api/artifacts/'+A}},source,where);x.m.closeResult(id);assert.equal(V.viewerOf(id),undefined);assert.deepEqual(x.seen.revealed,[])
  }
})
test('LIMIT focus invoker survives actual maximised close history leave',async()=>{
  const x=historyFixture({unfinished:false}),invoker={isConnected:true,name:'original'};x.page.invoker=()=>invoker;x.m=M.mountResults(x.page)
  x.m.openResult(dest(),launch());await tick();const id=V.maximised().id;x.m.closeResult(id);await tick()
  assert.equal(x.seen.focuses[0].choice.how,'invoker');assert.equal(x.seen.focuses[0].invoker,invoker)
})
test('LIMIT malformed held answer without identity fails closed',async()=>{
  reset();const body={state:'held',name:'unidentified.txt',treatment:{view:'text'}},done=[]
  const x=make({artifactNow:id=>R.artifactNow(id,async()=>response(body))});x.m.openResult(dest(),launch(),o=>done.push(o));await tick()
  assert.equal(V.maximised(),null);assert.deepEqual(done.map(o=>o.what),['unavailable'])
})
test('BLOCK saved resume read after Back must not replace the previous history entry',async()=>{
  const x=historyFixture({unfinished:false});let give;x.page.destinationOfTarget=()=>dest();x.page.artifactNow=()=>new Promise(r=>{give=r});x.m=M.mountResults(x.page)
  x.centre.go({result:{brainKey:brain,opening:91,target:{kind:'artifact',ref:A},place:{conversation:'ent-origin',centre:null}}})
  assert.equal(V.maximised(),null);history.go(-1);await tick();assert.equal(x.index(),0);assert.equal(x.at.current,null)
  give({how:'held',file:described});await tick();console.log('late-resume-after-Back',JSON.stringify({index:x.index(),entries:x.states.length,at:history.state.q2c.at,viewer:V.maximised()?.id}))
  assert.equal(V.maximised(),null);assert.equal(history.state.q2c.at,null);assert.equal(x.at.current,null)
})
test('LIMIT non-artifact record route has guard outcome but no freshness read',()=>{
  // F4 (adm-e2d35bd306b8): the record adapter takes `begin`, and the record it
  // opens comes from that answer. Only the adapter changes; the oracle does not.
  reset();let reads=0,records=0;const x=make({artifactNow:async()=>{reads++;throw Error('stale')},record:begin=>{const go=begin();if(!go)return;records++;go.moved()}})
  const o=x.m.openResult({...dest(),target:{kind:'record',ref:'ent-111111111111'},opens:'record'},launch())
  assert.equal(o.what,'opened');assert.equal(records,1);assert.equal(reads,0)
})
test('BLOCK actual saved Forward read finishing after Back must stay off the prior Place',async()=>{
  const x=historyFixture({unfinished:false});x.page.destinationOfTarget=()=>dest();x.m=M.mountResults(x.page)
  const stored={result:{brainKey:brain,opening:91,target:{kind:'artifact',ref:A},place:{conversation:'ent-origin',centre:null}}}
  x.centre.go(stored);await tick();history.go(-1);await tick();assert.equal(V.maximised(),null)
  let give;x.page.artifactNow=()=>new Promise(r=>{give=r});x.m=M.mountResults(x.page)
  history.go(1);await tick();assert.equal(x.index(),1);assert.equal(typeof give,'function');assert.equal(V.maximised(),null)
  history.go(-1);await tick();assert.equal(x.index(),0);assert.equal(history.state.q2c.at,null)
  give({how:'held',file:described});await tick()
  console.log('actual-Forward-late',JSON.stringify({index:x.index(),entries:x.states.length,at:history.state.q2c.at,viewer:V.maximised()?.id}))
  assert.equal(history.state.q2c.at,null);assert.equal(V.maximised(),null)
})
