import test from 'node:test'
import assert from 'node:assert/strict'
import {spawnSync} from 'node:child_process'
for(const stage of ['root','read'])for(const observed of [true,false])test(JSON.stringify({stage,observed}),()=>{
 const r=spawnSync(process.execPath,['review/notice-scenario.mjs',JSON.stringify({stage,observed})],{cwd:new URL('..',import.meta.url),encoding:'utf8',windowsHide:true,timeout:30000})
 console.log(r.stdout.trim());if(r.status!==0)console.log(r.stderr.trim());assert.equal(r.status,0)
})
