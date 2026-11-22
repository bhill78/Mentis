// Authored for independent 3781421e review. Every case runs a fresh binding process.
import test from 'node:test'
import assert from 'node:assert/strict'
import {spawnSync} from 'node:child_process'
const cases=[]
for(const route of ['post-here','post-overlay','post-other']) for(const transition of [null,'instance','corpus','move']) for(const stage of ['root','read']) for(const observed of [true,false]) cases.push({kind:'late-thread',route,transition,stage,observed})
for(const route of ['max-history','side-other']) for(const transition of [null,'instance','corpus','move']) for(const answer of ['go','stay']) for(const focus of ['invoker','control','fallback']) cases.push({kind:'close-preservation',route,transition,answer,focus})
for(const transition of [null,'instance','corpus','move']) cases.push({kind:'side-same',transition})
for(const transition of [null,'instance','corpus','move']) cases.push({kind:'history-inflight',transition})
for(const route of ['record','conversation','post']) for(const observed of [true,false]) for(const immediate of [true,false]) cases.push({kind:'duplicate-completion',route,observed,immediate})
for(const route of ['post-here','post-overlay']) for(const transition of [null,'instance','corpus','move']) for(const observed of [true,false]) cases.push({kind:'drawn',route,transition,observed})
for(const stage of ['root','read']) for(const observed of [true,false]) cases.push({kind:'read-failure',stage,observed})
cases.push({kind:'imports'})
for(const s of cases.filter(s=>process.env.EXTRA_SCOPE!=='residual'||['side-same','history-inflight'].includes(s.kind)))test(JSON.stringify(s),()=>{
 const r=spawnSync(process.execPath,['review/extra-scenario.mjs',JSON.stringify(s)],{cwd:new URL('..',import.meta.url),encoding:'utf8',windowsHide:true,timeout:30000})
 console.log(r.stdout.trim());if(r.status!==0)console.log(r.stderr.trim());assert.equal(r.status,0,'independent exact-host invariant')
})
