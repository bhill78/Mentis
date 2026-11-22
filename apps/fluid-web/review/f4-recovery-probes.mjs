import test from 'node:test'
import assert from 'node:assert/strict'
import {spawnSync} from 'node:child_process'
for(const mode of ['startup-503','never-bound']){
  test(mode,()=>{
    const r=spawnSync(process.execPath,['review/f4-recovery-scenario.mjs',mode],{cwd:new URL('..',import.meta.url),encoding:'utf8',windowsHide:true,timeout:30000})
    console.log(r.stdout.trim());if(r.status!==0)console.log(r.stderr.trim())
    assert.equal(r.status,0,'one ask per refused press, recovery on the next press, nothing asked once moved')
  })
}
