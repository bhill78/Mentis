import test from 'node:test'
import assert from 'node:assert/strict'
import {spawnSync} from 'node:child_process'
const kind=process.env.REVIEW_KIND??'guard'
const routes=kind==='close'?['max-history','side-other']:kind==='thread'?['post-here','post-overlay']:['record','conversation','post-other','post-overlay']
for(const route of routes)for(const transition of [null,'instance','corpus','move'])for(const answer of kind==='thread'?['go']:['go','stay']){
 const s={kind,route,transition,answer}
 test(JSON.stringify(s),()=>{
  const r=spawnSync(process.execPath,['review/review-host-scenario.mjs',JSON.stringify(s)],{cwd:new URL('..',import.meta.url),encoding:'utf8',windowsHide:true,timeout:30000})
  console.log(r.stdout.trim());if(r.status!==0)console.log(r.stderr.trim());assert.equal(r.status,0,'exact host contract safety oracle')
 })
}
