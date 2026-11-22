// New reviewer scenarios. Real binding singleton; synthetic page/history only.
import assert from 'node:assert/strict'
import { M,L,V,A,HELD,dest,tick,historyFixture,property,evaluate } from './fixture.mjs'
const {page,confirmBrain}=await import('../src/brainBinding.ts')
const {servingNow}=await import('../src/quiet2/results/serving.ts')
const s=JSON.parse(process.argv[2]), k='fixture-corpus@instance-1'
const bind=async(instance='instance-1',corpus_id='fixture-corpus')=>confirmBrain(async()=>new Response(JSON.stringify({brain:{corpus_id,instance}}),{status:200}))
const transition=async(t)=>{if(t==='bind')await bind();if(t==='instance')await bind('instance-2');if(t==='corpus')await bind('instance-1','other-corpus');if(t==='move')page.move()}
const x=historyFixture({unfinished:false})
let reads=0,places=0,recordCalls=0,conversationCalls=0,pending,resolveRead
const settled=[],moves=[],notice=x.seen.notices
const graph='https://fixture.invalid||fixture-corpus'
Object.assign(x.page,{serving:undefined,spaceKey:()=>graph,
  columns:()=>s.chooser?['s1','s2']:[],freeColumn:()=>null,
  invoker:()=>{places++;return null},
})
const plainFetch=async()=>{reads++;return new Promise(r=>{resolveRead=()=>r(new Response(JSON.stringify({...HELD,ref:A,treatment:{view:'text'}}),{status:200}))})}
/* THE IDENTITY ROUTE IS NOT A FRESHNESS READ (correction of adm-e2d35bd306b8):
   a press refused for want of a confirmed Brain asks it once. Answered 503, so
   the scenario's unbound state is exactly as unbound as it was, and counted
   apart from `reads`. */
let identityAsks=0
const readFetch=async(url,options)=>url==='/fluid/api/needs-you/brain'
  ?(identityAsks++,new Response('',{status:503}))
  :plainFetch(url,options)
globalThis.fetch=readFetch;x.page.artifactNow=undefined
const guard=(go,_where,stay)=>{if(s.delay)pending={go,stay};else go()}
const record=evaluate(property('record'),{guarded:guard,setBrainReturn:()=>{},centre:x.centre,CENTRE:'centre'})
x.page.record=(...args)=>{recordCalls++;return record(...args)}
/* F4 (adm-e2d35bd306b8): `begin()` is asked inside the guard, where the move is
   made, and the conversation moved to is the reference it answers. */
const pick=(ref,begin,stay)=>{conversationCalls++;guard(()=>{const go=begin();if(!go)return;moves.push(go.ref);x.centre.go({brain:{stack:[{page:'synthetic-conversation',entry:go.ref}]}});go.moved()},'centre',stay);return true}
x.page.pickConversation=evaluate(property('pickConversation'),{pickConversationFor:pick})
x.m=M.mountResults(x.page)
if(s.initial==='known'||s.initial==='moved')await bind()
if(s.initial==='moved')await bind('instance-2')
if(s.startup){
  globalThis.location={origin:'https://fixture.invalid'}
  globalThis.fetch=async(url,options)=>url==='/__q2/brain'?new Response('',{status:404}):readFetch(url,options)
  window.fetch=globalThis.fetch
  const {loadBrain}=await import('../src/quiet2/live.ts')
  await loadBrain();await tick();assert.equal(page.bound(),null)
}
const launch=x.m.launchNow({conversation:'ent-origin',centre:null},{control:'review-open',fallback:{kind:'conversation'}})
await transition(s.before)
const before=JSON.stringify(x.states),draft={text:'unsent review draft'},draftBefore=JSON.stringify(draft)
const destination=s.route==='artifact'?dest():{...dest(),target:{kind:'record',ref:'ent-333333333333'},opens:s.route}
const immediate=x.m.openResult(destination,launch,o=>settled.push(o))
if(s.delay){assert.equal(immediate.what,'leaving');assert.ok(pending);await transition(s.after);pending[s.answer]()}
if(s.route==='artifact'&&immediate.what!=='refused'){
  assert.equal(reads,1);resolveRead();await tick();await tick()
  if(s.chooser){assert.ok(x.chooser());await transition(s.after);x.chooser().decide('s1')}
  else if(s.after){/* read transition scenarios transition before resolving below in separate mode */}
}
if(s.startup){
  /* WAS: "the advised repeated press never re-confirms on its own after startup
     503", which is what the re-review recorded. The correction makes the press
     ask once; this server is still answering 503, so the press is still refused
     and still reads no artifact -- what changed is that the ask now happens at
     all, which is what makes pressing again a recovery when the server is up. */
  await tick()                       // let the first press's own ask settle
  const asksBefore=identityAsks
  const l=x.m.launchNow({conversation:'ent-origin',centre:null},{control:null,fallback:{kind:'conversation'}})
  assert.equal(x.m.openResult(destination,l).what,'refused');assert.equal(reads,0)
  await tick()
  assert.equal(identityAsks,asksBefore+1,'the refused press asks the server once')
  await bind()
  const retry=x.m.openResult(destination,x.m.launchNow({conversation:'ent-origin',centre:null},{control:null,fallback:{kind:'conversation'}}),o=>settled.push(o))
  assert.equal(retry.what,'leaving');resolveRead();await tick();await tick();assert.equal(places,1)
}
console.log(JSON.stringify({scenario:s,serving:servingNow(),launch:launch.brainKey,immediate,settled,reads,identityAsks,places,recordCalls,conversationCalls,moves,before,after:JSON.stringify(x.states),notices:notice,draftPreserved:JSON.stringify(draft)===draftBefore}))
if(s.startup)process.exit(0)
assert.equal(JSON.stringify(draft),draftBefore)
const shouldRefuse=s.initial!=='known'||!!s.before
if(shouldRefuse){
  assert.equal(immediate.what,'refused');assert.equal(reads,0);assert.equal(places,0)
  assert.equal(recordCalls,0);assert.equal(conversationCalls,0);assert.deepEqual(settled,[])
  assert.equal(JSON.stringify(x.states),before);assert.equal(notice.length,1)
  assert.ok(identityAsks<=1,'at most one identity ask per refused press')
}else if(s.delay && (s.answer==='stay'||s.after)){
  assert.equal(JSON.stringify(x.states),before,'a late guard must not navigate after the serving identity changed')
  assert.equal(settled.filter(o=>o.what==='opened').length,0,'a refusal must not report opened')
  assert.deepEqual(moves,[],'and no conversation was moved to at all')
}else if(s.route==='artifact'){
  if(s.after){assert.equal(places,0);assert.equal(settled.filter(o=>o.what==='opened').length,0)}
  else{assert.equal(places,1);assert.equal(settled.filter(o=>o.what==='opened').length,1)}
}else{
  assert.notEqual(JSON.stringify(x.states),before);assert.equal((s.delay?settled[0]:immediate).what,'opened')
}
