/* THE RE-REVIEW'S RECOVERY OBSERVATION (adm-e2d35bd306b8, nonblocking),
 * REPRODUCED AGAINST THE CORRECTION.
 *
 * This is the reviewer's own `recovery-scenario.mjs`, with its measurements
 * kept and its oracle turned round: it proved that after the real `loadBrain`
 * startup request fails, three result presses ask the server NOTHING and the
 * page stays unbound for ever. The correction's claim is the narrow opposite --
 * a refused press asks ONCE, so the next press finds a binding -- and these
 * are the same counters, against the real `confirmBrain` over the same
 * synthetic server, with no injected asker.
 *
 *   startup-503   the real `live.ts` `loadBrain` runs and its one request fails
 *   never-bound   nothing ever asked: a host that wires this in without binding
 */
import assert from 'node:assert/strict'
import {M,L,dest,make,tick} from './fixture.mjs'
const {page,confirmBrain}=await import('../src/brainBinding.ts')
let identityReads=0,healthy=false,records=0
globalThis.fetch=async url=>{
  if(url==='/__q2/brain')return new Response('',{status:404})
  assert.equal(url,'/fluid/api/needs-you/brain');identityReads++
  return healthy?new Response(JSON.stringify({brain:{corpus_id:'review',instance:'one'}}),{status:200}):new Response('',{status:503})
}
globalThis.window={fetch:globalThis.fetch};globalThis.location={origin:'https://fixture.invalid'}
const mode=process.argv[2]
if(mode==='startup-503'){
  const {loadBrain}=await import('../src/quiet2/live.ts');await loadBrain();await tick()
  assert.equal(identityReads,1,'the one startup identity request, and it failed')
}
healthy=true // the server has recovered, without any client having observed it
const x=make({serving:undefined,record:begin=>{const go=begin();if(!go)return;records++;go.moved()}})
const result={...dest(),target:{kind:'record',ref:'ent-333333333333'},opens:'record'}
const press=()=>x.m.openResult(result,x.m.launchNow({conversation:'ent-origin',centre:null},{control:null,fallback:{kind:'conversation'}}))
const beforeReads=identityReads

/* THE FIRST PRESS IS STILL REFUSED -- it is not retried and nothing is waited
   for -- but it asks, which is what "try again in a moment" promised. */
const first=press()
assert.equal(first.what,'refused','the press that found no confirmed Brain is refused')
assert.equal(records,0,'and nothing was opened')
assert.equal(identityReads,beforeReads+1,'and it asked the server exactly once')
const whileGoing=press()
assert.equal(whileGoing.what,'refused')
assert.equal(identityReads,beforeReads+1,'a second press while that ask is in flight starts no second ask')
await tick()

/* AND THE NEXT PRESS FINDS THE BINDING. On the reviewed candidate this press
   was the third identical refusal with the identity request count still at one. */
const recovered=press()
assert.equal(page.bound(),'review@one','the page is bound by the ask the press started')
assert.equal(recovered.what,'opened','so pressing again IS the way out, which it was not before')
assert.equal(records,1,'the record route ran once')
const afterRecovery=identityReads
press()
assert.equal(identityReads,afterRecovery,'and a confirmed page asks nobody anything')

/* A MOVED PAGE IS NEVER ASKED: only a reload binds that one. */
page.move()
const movedPress=press()
assert.equal(movedPress.what,'refused','a moved page still refuses')
assert.equal(identityReads,afterRecovery,'and asks nothing, because asking could not help it')
console.log(JSON.stringify({mode,identityReads,bound:page.bound(),moved:page.moved(),records,notices:x.seen.notices.length}))
