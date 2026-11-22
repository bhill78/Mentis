/* The re-review's own 16-case matrix (adm-e2d35bd306b8): two routes, four
 * transitions (none, another instance, another corpus, the binding's own
 * `move()`), each answered Go and Stay. One fresh Node process per case, with
 * the actual brainBinding singleton. */
import test from 'node:test'
import assert from 'node:assert/strict'
import {spawnSync} from 'node:child_process'
for(const route of ['record','conversation'])for(const transition of [null,'instance','corpus','move'])for(const answer of ['go','stay']){
  const s={route,transition,answer}
  test(JSON.stringify(s),()=>{
    const r=spawnSync(process.execPath,['review/f4-guard-contract-scenario.mjs',JSON.stringify(s)],{cwd:new URL('..',import.meta.url),encoding:'utf8',windowsHide:true,timeout:30000})
    console.log(r.stdout.trim());if(r.status!==0)console.log(r.stderr.trim())
    assert.equal(r.status,0,'guard identity, history and completion oracle')
  })
}
