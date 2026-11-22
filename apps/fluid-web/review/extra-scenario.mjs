import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {M,L,V,O,brain,dest,launch,make,tick,reset} from './fixture.mjs'
import {extraHost} from './extra-host.mjs'
const {page,confirmBrain}=await import('../src/brainBinding.ts')
const s=JSON.parse(process.argv[2])
const bind=(instance='one',corpus_id='review-corpus')=>confirmBrain(async()=>new Response(JSON.stringify({brain:{corpus_id,instance}}),{status:200}))
const move=async()=>{if(s.transition==='instance')await bind('two');if(s.transition==='corpus')await bind('one','other');if(s.transition==='move')page.move()}
if(s.kind==='duplicate-completion'){
 reset();let finish;const notices=[],settled=[]
 const d={...dest(),target:s.route==='post'?{kind:'post',conversation:'ent-origin',post:'ent-post'}:{kind:'record',ref:'ent-target'},opens:s.route}
 const route=(...args)=>{finish=args.at(-2);if(s.immediate)return {how:'refused',why:'synthetic refusal'};return 'requested'}
 const host={brainKey:brain,say:n=>notices.push(n),[s.route]:route}
 const immediate=O.openResultTarget(d,launch(),host,{settled:s.observed?o=>settled.push(o):undefined})
 assert.equal(immediate.what,s.immediate?'refused':'leaving')
 for(const n of ['requested',{how:'refused',why:'synthetic refusal'},{how:'refused',why:'duplicate'},'completed',{how:'failed',why:'duplicate failure'}])finish(n)
 console.log(JSON.stringify({s,immediate,notices,settled}))
 assert.deepEqual(notices,['synthetic refusal']);assert.equal(settled.length,s.observed&&!s.immediate?1:0)
}else if(s.kind==='imports'){
 const handoff=readFileSync(new URL('../src/quiet2/results/HOST-INTEGRATION.md',import.meta.url),'utf8')
 assert.match(handoff,/import \{ mountResults, type BeginMove, type ResultPage \} from '\.\/results\/mount'/)
 assert.match(handoff,/import type \{ MayMove, Navigation, Opened \} from '\.\/results\/opener'/)
 assert.match(readFileSync(new URL('../src/quiet2/results/mount.ts',import.meta.url),'utf8'),/export type BeginMove/)
 assert.match(readFileSync(new URL('../src/quiet2/results/opener.ts',import.meta.url),'utf8'),/export type MayMove/)
 console.log(JSON.stringify({s,imports:'all named types imported from their exporting module'}))
}else{
 await bind();const x=extraHost({overlay:s.route==='post-overlay'}),settled=[]
 const observed=s.observed!==false, observe=observed?o=>settled.push(o):undefined
 const invoker={isConnected:s.focus==='invoker',name:'opening element'}
 x.page.invoker=()=>invoker;x.page.hasControl=()=>s.focus==='control'
 if(s.kind==='side-same'||s.route==='side-other'){x.page.columns=()=>['s1'];x.page.freeColumn=()=> 's1'}
 x.m=M.mountResults(x.page)
 const launch=x.m.launchNow({conversation:'ent-origin',centre:null},{control:'result-control',fallback:{kind:'conversation'}},null,{scroll:417,offset:12},{root:'ent-launch-thread',at:'ent-launch-at'},'ent-reply','draft-key')
 const snapshot=()=>JSON.stringify({history:x.states,index:x.index(),conversation:x.state.conversation,content:x.state.content,workspace:x.state.workspace,thread:x.state.thread,at:x.state.at,reply:x.state.reply,surfaces:x.state.surfaces,focus:x.seen.focuses})
 if(['close-preservation','side-same','history-inflight'].includes(s.kind)){
  x.m.openResult(dest(),launch);await tick();const viewer=x.m.results.all()[0].viewer
  if(s.route==='side-other'){x.centre.open('ent-other');x.state.conversation='ent-other'}
  x.state.thread='ent-current-thread';x.state.reply='ent-current-reply'
  const row=JSON.stringify(V.viewerOf(viewer)), originalLaunch=JSON.stringify(L.launchOf(launch.opening))
  x.calls.length=0;const before=snapshot()
  if(s.kind==='side-same'){
   await move();x.m.closeResult(viewer);await tick()
  }else if(s.kind==='history-inflight'){
   x.m.closeResult(viewer);assert.ok(x.state.question)
   const saved=globalThis.queueMicrotask,pops=[]
   globalThis.queueMicrotask=f=>pops.push(f)
   try{x.answer('go')}finally{globalThis.queueMicrotask=saved}
   assert.equal(pops.length,1,'actual history back must be waiting for popstate')
   await move();for(const f of pops)f();await tick()
  }else{
   x.m.closeResult(viewer);assert.ok(x.state.question);await move();x.answer(s.answer);await tick()
  }
  const after=snapshot()
  console.log(JSON.stringify({s,before,after,calls:x.calls,notices:x.seen.notices,viewer:!!V.viewerOf(viewer),launch:!!L.launchOf(launch.opening),focus:x.seen.focuses}))
  if(s.answer==='stay'||s.transition){
   // A history walk already launched before identity movement cannot be recalled;
   // assert only that OLD thread/reply restoration and close do not follow it.
   if(s.kind!=='history-inflight')assert.equal(after,before,'refused close/Stay must keep page and focus')
   else {assert.equal(x.state.thread,'ent-current-thread','old thread must not be restored after identity movement before popstate');assert.equal(x.state.reply,'ent-current-reply')}
   assert.equal(JSON.stringify(V.viewerOf(viewer)),row,'viewer retained unchanged');assert.equal(JSON.stringify(L.launchOf(launch.opening)),originalLaunch,'launch retained unchanged')
   assert.equal(x.seen.focuses.length,0,'no focus stolen by refused close')
   assert.equal(x.seen.notices.length,s.answer==='stay'?0:1,'refused close says why once')
  }else{
   assert.equal(V.viewerOf(viewer),undefined);assert.equal(L.launchOf(launch.opening),null)
   assert.equal(x.state.thread,'ent-launch-thread');assert.equal(x.seen.focuses.length,1)
   assert.equal(x.seen.focuses[0].choice.how,s.focus??'fallback');assert.equal(x.seen.notices.length,0)
  }
 }else{
  const c=s.route==='post-other'?'ent-target':'ent-origin'
  if(s.kind==='drawn')x.document.querySelector=()=>({})
  const d={...dest(),target:{kind:'post',conversation:c,post:'ent-post'},opens:'post'}
  const immediate=x.m.openResult(d,launch,observe)
  if(s.route==='post-overlay'){
   if(s.kind==='drawn')await move()
   x.answer('go')
  }else if(s.route==='post-other'){
   x.answer('go');x.now.current.realId=c;x.pendingEffect()
  }
  if(s.kind==='drawn'){
   console.log(JSON.stringify({s,immediate,calls:x.calls,settled,notices:x.seen.notices}))
   // Same-conversation drawn reveal is synchronous: movement happens before
   // the guarded overlay arm only. No pretend async gap on the direct arm.
   const refused=s.route==='post-overlay'&&!!s.transition
   assert.equal(x.calls.filter(c=>c[0]==='reveal').length,refused?0:1)
   assert.equal(x.seen.notices.length,refused?1:0)
   assert.deepEqual(settled.map(o=>o.what),observed&&s.route==='post-overlay'?[refused?'refused':'opened']:[])
  }else{
   const before=snapshot()
   if(s.kind==='read-failure'){
    if(s.stage==='root')x.failRoot();else{x.root('ent-root');await tick();x.failRead()}
   }else{
    if(s.stage==='root')await move()
    x.root('ent-root');await tick()
    if(s.stage==='read')await move()
    x.read()
   }
   await tick()
   console.log(JSON.stringify({s,before,after:snapshot(),calls:x.calls,settled,notices:x.seen.notices}))
   if(s.kind==='read-failure'){
    assert.deepEqual(settled.map(o=>o.what),observed?['unavailable']:[]);assert.equal(x.seen.notices.length,1);assert.equal(snapshot(),before)
   }else if(s.transition){assert.equal(snapshot(),before);assert.deepEqual(settled.map(o=>o.what),observed?['refused']:[]);assert.equal(x.seen.notices.length,1)}
   else{assert.equal(x.state.thread,'ent-root');assert.deepEqual(settled.map(o=>o.what),observed?['opened']:[]);assert.equal(x.seen.notices.length,0)}
  }
 }
}
