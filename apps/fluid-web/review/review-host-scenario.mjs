import assert from 'node:assert/strict'
import {M,L,V,dest,tick} from './fixture.mjs'
import {exactHost} from './exact-host.mjs'
const {page,confirmBrain}=await import('../src/brainBinding.ts')
const s=JSON.parse(process.argv[2])
const bind=(instance='one',corpus_id='review-corpus')=>confirmBrain(async()=>new Response(JSON.stringify({brain:{corpus_id,instance}}),{status:200}))
await bind()
const x=exactHost({overlay:s.route==='post-overlay'}),settled=[]
const observed=s.kind!=='unobserved',observe=observed?o=>settled.push(o):undefined
const launch=x.m.launchNow({conversation:'ent-origin',centre:null},{control:null,fallback:{kind:'conversation'}},null,{scroll:417,offset:12},{root:'ent-launch-thread',at:null},'ent-reply','thread:origin')
const move=async()=>{if(s.transition==='instance')await bind('two');if(s.transition==='corpus')await bind('one','other');if(s.transition==='move')page.move()}
const snapshot=()=>JSON.stringify({history:x.states,index:x.index(),conversation:x.state.conversation,content:x.state.content,workspace:x.state.workspace,thread:x.state.thread,reply:x.state.reply,surfaces:x.state.surfaces})
if(s.kind==='close'){
 x.page.columns=()=>s.route==='side-other'?['s1']:[];x.page.freeColumn=()=>s.route==='side-other'?'s1':null;x.m=M.mountResults(x.page)
 assert.equal(x.m.openResult(dest(),launch).what,'leaving');await tick()
 const viewer=x.m.results.all()[0].viewer
 if(s.route==='side-other'){x.centre.open('ent-other');x.state.conversation='ent-other'}
 x.calls.length=0
 let before=snapshot()
 x.m.closeResult(viewer)
 assert.ok(x.state.question,'close must be pending, not silently finished')
 await move();x.answer(s.answer);await tick()
 const after=snapshot()
 console.log(JSON.stringify({s,before,after,calls:x.calls,notices:x.seen.notices,viewer:!!V.viewerOf(viewer),launch:!!L.launchOf(launch.opening)}))
 if(s.answer==='stay'){assert.equal(after,before);assert.ok(V.viewerOf(viewer));assert.ok(L.launchOf(launch.opening))}
 else if(s.transition){assert.equal(after,before,'close under changed identity must not restore old Brain place');assert.ok(V.viewerOf(viewer))}
 else {assert.notEqual(after,before);assert.equal(V.viewerOf(viewer),undefined)}
}else if(s.kind==='thread'){
 const before=snapshot()
 const immediate=x.m.openResult({...dest(),target:{kind:'post',conversation:'ent-origin',post:'ent-post'},opens:'post'},launch,o=>settled.push(o))
 assert.equal(immediate.what,'leaving')
 if(s.route==='post-overlay'){assert.ok(x.state.question);x.answer('go')}
 x.root('ent-root');await tick();const lateBefore=snapshot();await move();x.read();await tick()
 const after=snapshot()
 console.log(JSON.stringify({s,before,after,calls:x.calls,settled,notices:x.seen.notices}))
 if(s.transition){assert.deepEqual(settled.map(o=>o.what),['refused']);assert.equal(x.seen.notices.length,1);assert.equal(after,lateBefore,'post read must check launch identity before onEnter changes thread/reply/surfaces')}
 else {assert.equal(x.state.thread,'ent-root');assert.deepEqual(settled.map(o=>o.what),['opened']);assert.equal(x.seen.notices.length,0)}
}else{
 const isPost=s.route.startsWith('post')
 const target=isPost?{kind:'post',conversation:s.route==='post-overlay'?'ent-origin':'ent-target',post:'ent-post'}:{kind:'record',ref:'ent-target'}
 const before=snapshot()
 const immediate=x.m.openResult({...dest(),target,opens:isPost?'post':s.route},launch,observe)
 assert.equal(immediate.what,'leaving');assert.ok(x.state.question);assert.deepEqual(x.calls,[])
 await move();x.answer(s.answer)
 if(isPost&&s.answer==='go'&&!s.transition){
  x.now.current.realId=target.conversation
  if(s.route==='post-other')x.pendingEffect()
  x.root('ent-root');await tick();x.read();await tick()
 }
 await tick();const after=snapshot()
 console.log(JSON.stringify({s,before,after,calls:x.calls,settled,notices:x.seen.notices,pending:x.pendingPost.current}))
 if(s.answer==='stay'||s.transition){
  assert.equal(after,before,'identity/Stay gate before all host setters, workspace and history mutation');assert.deepEqual(x.calls,[])
  assert.deepEqual(settled.map(o=>o.what),observed?[s.answer==='stay'?'cancelled':'refused']:[]);assert.equal(x.seen.notices.length,s.answer==='stay'?0:1,'late identity refusal must say why once even without an observer')
 }else{
  assert.notEqual(after,before);assert.deepEqual(settled.map(o=>o.what),observed?['opened']:[]);assert.equal(x.seen.notices.length,0)
 }
}
