import test from 'node:test'
import assert from 'node:assert/strict'
import {spawnSync} from 'node:child_process'
const scenarios=[]
for(const kind of ['saved','explicit']) for(const phase of ['read','chooser']) {
  for(const transition of ['instance','corpus','move']) scenarios.push({kind,phase,initial:'bound',transition,where:'s1',expect:'closed'})
  scenarios.push({kind,phase,initial:'bound',where:'s1',expect:'open'})
}
for(const initial of ['unbound','bound','moved']) scenarios.push({kind:'saved',phase:'read',initial,saved:'null',where:'max',expect:'closed'})
for(const initial of ['unbound','moved','second']) scenarios.push({kind:'saved',phase:'read',initial,where:'max',expect:'closed'})
scenarios.push({kind:'saved',phase:'read',initial:'bound',where:'max',expect:'open'})
for(const initial of ['unbound','moved']) for(const where of ['max','s1']) scenarios.push({kind:'explicit',phase:'read',initial,where,expect:'closed'})
for(const phase of ['read','chooser']) for(const transition of ['bind','bind-move']) scenarios.push({kind:'explicit',phase,initial:'unbound',transition,where:'s1',expect:'closed'})
for(const initial of ['unbound','moved']) scenarios.push({kind:'record',phase:'read',initial,where:'max',expect:'closed'})
// Exercise mount -> artifactNow -> fluidFetch -> synthetic fetch without an
// injected artifact reader, including a newly confirmed instance at completion.
for(const initial of ['unbound','moved']) for(const where of ['max','s1']) scenarios.push({kind:'explicit',phase:'read',initial,where,reader:'default',expect:'closed'})
for(const phase of ['read','chooser']) scenarios.push({kind:'explicit',phase,initial:'unbound',transition:'bind',where:'max',reader:'default',expect:'closed'})
for(const where of ['max','s1']) scenarios.push({kind:'explicit',phase:'read',initial:'startup',where,reader:'default',expect:'closed'})
for(const [i,scenario] of scenarios.entries()) test(String(i+1).padStart(2,'0')+' '+JSON.stringify(scenario),()=>{
  const run=spawnSync(process.execPath,['review/reviewer-binding-scenario.mjs',JSON.stringify(scenario)],{encoding:'utf8',windowsHide:true,cwd:new URL('..',import.meta.url)})
  console.log(run.stdout.trim())
  if(run.status!==0)console.log(run.stderr.trim())
  assert.equal(run.status,0,'scenario safety assertions must hold')
})
