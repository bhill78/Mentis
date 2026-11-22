import test from 'node:test'
import assert from 'node:assert/strict'
import {spawnSync} from 'node:child_process'
const scenarios=[]
for(const route of ['artifact','record','conversation']){
  for(const initial of ['unbound','moved','known'])scenarios.push({route,initial})
  scenarios.push({route,initial:'unbound',before:'bind'})
  for(const before of ['move','instance','corpus'])scenarios.push({route,initial:'known',before})
}
for(const route of ['record','conversation'])for(const after of [null,'move'])for(const answer of ['go','stay'])scenarios.push({route,initial:'known',delay:true,after,answer})
for(const after of [null,'move','instance','corpus'])scenarios.push({route:'artifact',initial:'known',chooser:true,after})
scenarios.push({route:'artifact',initial:'unbound',startup:true})
for(const [n,s]of scenarios.entries())test('extra '+(n+1)+' '+JSON.stringify(s),()=>{
  const r=spawnSync(process.execPath,['review/reviewer-extra-scenario.mjs',JSON.stringify(s)],{encoding:'utf8',windowsHide:true,cwd:new URL('..',import.meta.url),timeout:30000})
  console.log(r.stdout.trim());if(r.status!==0)console.log(r.stderr.trim())
  assert.equal(r.status,0,'independent safety and completion assertions')
})
