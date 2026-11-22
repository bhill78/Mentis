import assert from 'node:assert/strict'
import {M,dest,tick,evaluate,property} from './fixture.mjs'
import {extraHost} from './extra-host.mjs'
const {confirmBrain}=await import('../src/brainBinding.ts')
const s=JSON.parse(process.argv[2])
await confirmBrain(async()=>new Response(JSON.stringify({brain:{corpus_id:'review-corpus',instance:'one'}}),{status:200}))
const x=extraHost(),settled=[]
// The proposed page.say is exactly setNotice. Both it and showPost's direct
// setNotice feed this same call log; count setter invocations, not DOM toasts.
x.page.say=evaluate(property('say'),{setNotice:words=>x.calls.push(['notice',words])})
x.m=M.mountResults(x.page)
const l=x.m.launchNow({conversation:'ent-origin',centre:null},{control:null,fallback:{kind:'conversation'}})
x.m.openResult({...dest(),target:{kind:'post',conversation:'ent-origin',post:'ent-post'},opens:'post'},l,s.observed?o=>settled.push(o):undefined)
if(s.stage==='root')x.failRoot();else{x.root('ent-root');await tick();x.failRead()}
await tick()
const notices=x.calls.filter(c=>c[0]==='notice')
console.log(JSON.stringify({s,notices,settled}))
assert.deepEqual(settled.map(o=>o.what),s.observed?['unavailable']:[])
assert.equal(notices.length,1,'one failure notice setter invocation through exact proposed say + showPost')
