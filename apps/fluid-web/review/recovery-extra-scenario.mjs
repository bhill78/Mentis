import assert from 'node:assert/strict'
import {M,dest,make,tick} from './fixture.mjs'
const {page,confirmBrain}=await import('../src/brainBinding.ts')
const mode=process.argv[2],answers=[];let asks=0,moves=0
globalThis.fetch=url=>{assert.equal(url,'/fluid/api/needs-you/brain');asks++;return new Promise(r=>answers.push(r))}
const x=make({serving:undefined,record:begin=>{const go=begin();if(!go)return;moves++;go.moved()}})
const result={...dest(),target:{kind:'record',ref:'ent-target'},opens:'record'}
const press=(m=x.m,l=m.launchNow({conversation:'ent-origin',centre:null},{control:null,fallback:{kind:'conversation'}}))=>m.openResult(result,l)
const reply=(i,status=200)=>answers[i](status===200?new Response(JSON.stringify({brain:{corpus_id:'review',instance:'one'}}),{status}):new Response('',{status}))
if(mode==='moved'){
 await confirmBrain(async()=>new Response(JSON.stringify({brain:{corpus_id:'review',instance:'one'}}),{status:200}));page.move()
 for(let i=0;i<3;i++)assert.equal(press().what,'refused')
 assert.equal(asks,0);assert.equal(moves,0)
}else{
 const old=x.m.launchNow({conversation:'ent-origin',centre:null},{control:null,fallback:{kind:'conversation'}})
 assert.equal(press(x.m,old).what,'refused');assert.equal(asks,1)
 if(mode==='remount'){
  const again=M.mountResults(x.page)
  assert.equal(press(again).what,'refused')
  console.log(JSON.stringify({mode,asks,inflight:answers.length,moves}))
  // Finish both asks even if the bound below fails. No pending test work.
  for(let i=0;i<answers.length;i++)reply(i,503);await tick()
  assert.equal(asks,1,'one identity ask per page while pending, including after render/remount')
 }else if(mode==='reject-retry'){
  reply(0,503);await tick();assert.equal(page.bound(),null);assert.equal(press().what,'refused');assert.equal(asks,2)
  reply(1);await tick();assert.equal(press().what,'opened');assert.equal(moves,1)
 }else{
  for(let i=0;i<4;i++)assert.equal(press().what,'refused')
  assert.equal(asks,1);reply(0);await tick()
  assert.equal(press(x.m,old).what,'refused','unknown launch cannot acquire recovered identity')
  assert.equal(asks,1);assert.equal(moves,0)
  assert.equal(press().what,'opened');assert.equal(moves,1)
 }
}
console.log(JSON.stringify({mode,asks,moves,bound:page.bound(),moved:page.moved(),notices:x.seen.notices}))
