/* THE INDEPENDENT RE-REVIEW'S EXACT HOST-CONTRACT MATRIX (adm-e2d35bd306b8, F4),
 * REPRODUCED AGAINST THE CORRECTION.
 *
 * This is the reviewer's own `guard-contract-scenario.mjs`, kept case for case
 * and oracle for oracle. What changed is only what the correction changed: the
 * exact proposed `record` expression is extracted from HOST-INTEGRATION.md as
 * before, and the baseline `pickConversation` is transformed by the handoff's
 * OWN documented edits -- asserted to be present in the baseline first, as the
 * reviewer asserted its two edits.
 *
 * Everything else is the reviewer's: the real `brainBinding` singleton and real
 * `confirmBrain`, `ResultPage.serving` omitted so the module reads the binding
 * itself, the real `arrive` from `Quiet2.tsx`, the real usePlaces/centreHistory
 * history, and the oracle that compares the WHOLE history state before and
 * after -- actual entries and actual setters, not calls counted at the adapter
 * boundary.
 *
 * On the reviewed candidate this matrix was 10 pass / 6 fail.
 */
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {M,L,dest,historyFixture,property,variable,evaluate} from './fixture.mjs'
const {page,confirmBrain}=await import('../src/brainBinding.ts')
const s=JSON.parse(process.argv[2])
const bind=async(instance='one',corpus_id='review-corpus')=>confirmBrain(async()=>new Response(JSON.stringify({brain:{corpus_id,instance}}),{status:200}))
await bind()
const x=historyFixture({unfinished:false}),calls=[],settled=[]
let pending
const guarded=(go,_where,stay)=>{pending={go,stay}}
const code=readFileSync(new URL('../src/quiet2/Quiet2.tsx',import.meta.url),'utf8')
const arrive=evaluate(variable('arrive',code),{
  setBrainOpen:v=>calls.push(['brain',v]),setSourcesOpen:v=>calls.push(['sources',v]),setBrainReturn:v=>calls.push(['return',v]),
  realId:'ent-origin',brainLeft:{current:42},centre:x.centre,setRealId:v=>calls.push(['realId',v]),setContent:v=>calls.push(['content',v]),saveWorkspace:v=>calls.push(['saveWorkspace',v]),
})
/* THE HANDOFF'S OWN TWO EDITS TO THE BASELINE, AND ONLY THOSE (patch 2). The
   baseline is asserted unchanged first, exactly as the reviewer asserted the
   old pair, so this is the documented wiring and not a rewrite of it. */
let pickCode=variable('pickConversation',code)
assert.ok(pickCode.includes('(k: string, then?: () => void)'),'baseline pickConversation signature')
assert.ok(pickCode.includes('guarded(() => arrive(k, then))'),'baseline guarded arrive')
pickCode=pickCode
  .replace('(k: string, then?: () => void)','(k, begin, stay)')
  .replace('guarded(() => arrive(k, then))','guarded(() => { const go = begin(); if (!go) return; arrive(go.ref, go.moved) }, CENTRE, stay)')
const pick=evaluate(pickCode,{isReal:true,CONVERSATIONS:[],setNotice:v=>calls.push(['notice',v]),surfacePanes:[],placeOf:()=>null,surfaces:{},setSurfaces:()=>assert.fail('no surfaces here'),guarded,arrive,CENTRE:'centre'})
Object.assign(x.page,{
  serving:undefined,
  record:evaluate(property('record'),{guarded,setBrainReturn:v=>calls.push(['return',v]),centre:x.centre,CENTRE:'centre'}),
  pickConversation:evaluate(property('pickConversation'),{pickConversationFor:pick}),
})
x.m=M.mountResults(x.page)
const launch=x.m.launchNow({conversation:'ent-origin',centre:null},{control:null,fallback:{kind:'conversation'}})
const before=JSON.stringify(x.states)
const immediate=x.m.openResult({...dest(),target:{kind:'record',ref:'ent-333333333333'},opens:s.route},launch,o=>settled.push(o))
assert.equal(immediate.what,'leaving');assert.ok(pending);assert.deepEqual(calls,[])
if(s.transition==='instance')await bind('two')
if(s.transition==='corpus')await bind('one','other-corpus')
if(s.transition==='move')page.move()
pending[s.answer]()
const after=JSON.stringify(x.states)
console.log(JSON.stringify({scenario:s,bound:page.bound(),moved:page.moved(),launch:launch.brainKey,immediate,settled,before,after,calls,notices:x.seen.notices}))
if(s.answer==='stay'||s.transition){
  assert.equal(after,before,'pending navigation must recheck serving identity before it moves')
  assert.equal(settled.filter(o=>o.what==='opened').length,0,'no opened completion on an identity-refused move')
  /* ADDED BY THIS CORRECTION, beyond the reviewer's oracle: nothing of the move
     reached the page either -- no realId, no content, no saved workspace -- and
     a refused Go is told apart from the reader's own Stay. */
  assert.deepEqual(calls.filter(c=>c[0]==='realId'||c[0]==='saveWorkspace'||c[0]==='content'),[],'no page mutation at all')
  if(s.transition&&s.answer==='go'){
    assert.deepEqual(settled.map(o=>o.what),['refused'],'a refused Go is reported as refused, once')
    assert.equal(x.seen.notices.length,1,'and says why exactly once')
  }
  if(!s.transition&&s.answer==='stay')assert.deepEqual(settled.map(o=>o.what),['cancelled'],'Stay is the reader own choice')
}else{
  assert.notEqual(after,before);assert.equal(settled.length,1);assert.equal(settled[0].what,'opened')
  assert.deepEqual(x.seen.notices,[],'an unchanged binding opens with nothing said')
}
