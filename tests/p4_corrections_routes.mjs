import { registerHooks } from 'node:module'
import { readFileSync, existsSync, writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import ts from '../apps/fluid-web/node_modules/typescript/lib/typescript.js'
registerHooks({
 resolve(specifier, context, next) {
   if(specifier.startsWith('.')) for(const suffix of ['.ts','.tsx','/index.ts']) {
     const url = new URL(specifier+suffix,context.parentURL)
     if(existsSync(fileURLToPath(url))) return {url:url.href,shortCircuit:true}
   }
   return next(specifier,context)
 },
 load(url,context,next) {
   if(url.endsWith('.css')) return {format:'module',source:'',shortCircuit:true}
   if(/\.tsx?$/.test(url)) return {format:'module',shortCircuit:true,source:ts.transpileModule(readFileSync(fileURLToPath(url),'utf8').replaceAll('import.meta.env','({})'),{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText}
   return next(url,context)
 }
})
globalThis.localStorage={getItem:()=>null,setItem:()=>{},removeItem:()=>{}}
const assert = (await import('node:assert/strict')).default
const F=JSON.parse(readFileSync(new URL('../evidence/route-fixture.json',import.meta.url),'utf8'))
const nativeFetch=globalThis.fetch
let requests=[]
globalThis.fetch=(url,init)=>{requests.push({url,init});return nativeFetch(new URL(url,F.base),init)}
const {checkResultOpen,verdict}=await import('../apps/fluid-web/src/work/freshness.ts')
const {mountResults,resetPlacedResults}=await import('../apps/fluid-web/src/quiet2/results/mount.ts')
const {clearLaunches}=await import('../apps/fluid-web/src/quiet2/results/launch.ts')
const {page:binding}=await import('../apps/fluid-web/src/brainBinding.ts')
const {destinationOfRef}=await import('../apps/fluid-web/src/quiet2/results/targets.ts')
const {pressedOf,freshlyOpen}=await import('../apps/fluid-web/src/quiet2/results/refNow.ts')
const results=[]
function observed(name,actual){results.push({name,actual});console.log(name,JSON.stringify(actual))}
const P={expectation:F.work,group:F.group,ref:F.post,opens:'post',brain:F.brain,moves:0}
const now=()=>({brain:P.brain,moved:false,moves:0})
const deps={viewer:null,now}
const good=await checkResultOpen(P,deps)
assert.equal(good.how,'open');assert.equal(good.at.post,F.post)
observed('exact post identity despite identical prose',good.at)
const missing=await checkResultOpen({...P,ref:'ent-ffffffffffff',opens:'record'},deps)
assert.equal(missing.how,'gone'); observed('missing',missing)
const deleted=await checkResultOpen({...P,ref:F.deleted_post},deps)
assert.equal(deleted.how,'gone');observed('deleted',deleted)
const late=await checkResultOpen({...P,ref:F.late,opens:'record'},deps)
assert.equal(late.how,'open');observed('B1 readable continuation item opens',late)
const groupGone=await checkResultOpen({...P,group:'ent-ffffffffffff'},deps)
assert.equal(groupGone.how,'changed');observed('missing group typed refresh',groupGone)
const aliasRow=F.first.result_groups.groups[0].items.find(i=>i.ref===F.work)
const aliasDest=destinationOfRef(aliasRow.inspection,{work:F.work,group:F.group})
assert.equal(aliasDest.target.kind,'post');assert.notEqual(aliasRow.ref,aliasDest.target.post)
const alias=await checkResultOpen(pressedOf(aliasDest,P.brain,0),deps)
assert.equal(alias.how,'open');assert.equal(alias.at.post,aliasDest.target.post);observed('B2 stored request ref resolves to exact post',alias)
// A real refusal from the chosen route remains a refusal in exactly its prose.
globalThis.fetch=(url,init)=>nativeFetch(new URL(url,F.base),{...init,headers:{...init?.headers,[F.capability_header]:'review-invalid-grant'}})
const denied=await checkResultOpen(P,deps)
assert.equal(denied.how,'gone');observed('real route refuses presented worker grant',denied)
for(const status of [401,403,500]){
 globalThis.fetch=async()=>new Response(JSON.stringify({error:'Exact server refusal prose.'}),{status})
 const result=await checkResultOpen(P,deps);assert.equal(result.why,'Exact server refusal prose.')
 observed('HTTP '+status+' same prose',result)
}
globalThis.fetch=async()=>new Response('<malformed server response>',{status:503})
observed('malformed JSON error',await checkResultOpen(P,deps))
globalThis.fetch=(url,init)=>{requests.push({url,init});return nativeFetch(new URL(url,F.base),init)}
for(const [label,detail] of [['unreadable',F.unreadable],['wrong work',{...F.first,expectation:'opr-other'}]]){
 const result=await checkResultOpen(label==='unreadable'?{...P,ref:F.note,opens:'record'}:P,{...deps,read:async()=>detail})
 assert.equal(result.how,'gone');observed(label,result)
}
// Malformed transport bodies: distinguish a truthful refusal from a rejected promise.
for(const [label,detail] of [['null',null],['bad groups',{expectation:F.work,result_groups:{groups:[null]}}],['bad items',{expectation:F.work,result_groups:{groups:[{id:F.group,items:{}}]}}]]){
 const r=await checkResultOpen(P,{...deps,read:async()=>detail});assert.equal(r.how,'gone')
 observed('malformed '+label,r)
}
const template=structuredClone(F.first)
const item=template.result_groups.groups[0].items.find(i=>i.ref===F.post)
item.inspection.state='future-unknown';item.inspection.available=true;item.available=true
assert.equal(verdict(P,{ok:true,detail:template},now()).how,'gone');observed('unknown state refused',verdict(P,{ok:true,detail:template},now()).how)
const badInspection=structuredClone(F.first)
badInspection.result_groups.groups[0].items.find(i=>i.ref===F.post).inspection.post=F.deleted_post
observed('module inconsistent inspection target',verdict(P,{ok:true,detail:badInspection},now()).how)
function harness(over={}){
 clearLaunches();resetPlacedResults()
 const seen={moves:[],said:[],settled:[],draft:'unsaved reviewer draft',guard:null}
 let at=null
 const page={spaceKey:()=>"graph-only",origin:()=>F.base,conversation:()=>F.conversation,
 centreAt:()=>at,enterCentre:x=>{at=x},columns:()=>[],freeColumn:()=>null,choose:()=>{},
 invoker:()=>null,hasControl:()=>false,focus:()=>{},centreGo:()=>{},centreReplace:()=>{},
 backTo:(_,go)=>go(),pickConversation:(k,go,stay)=>{seen.guard={go:()=>{seen.moves.push(k);go?.()},stay};return true},
 openPost:(c,p,done)=>{seen.guard={go:()=>{seen.moves.push([c,p]);done('completed')},stay:()=>done({how:'cancelled'})}},
 record:(r,go,stay)=>{seen.guard={go:()=>{seen.moves.push(r);go()},stay}},goToPost:()=>{},
 heldItem:()=>null,putBack:()=>{},say:w=>seen.said.push(w),...over}
 const m=mountResults(page)
 const launch=m.launchNow({conversation:F.conversation,centre:null},{control:null,fallback:{kind:'conversation'}})
 const d={work:F.work,group:F.group,target:{kind:'post',post:F.post,conversation:F.conversation},source:null,basis:[],verified:true,label:'same prose',availability:'ok',available:true,opens:'post'}
 return {m,launch,d,seen,page}
}
binding.saw(P.brain)
const tick=()=>new Promise(r=>setTimeout(r,120))
for(const action of ['stay','go']){
 const h=harness();h.m.openResult(h.d,h.launch,o=>h.seen.settled.push(o));await tick()
 assert.ok(h.seen.guard);assert.deepEqual(h.seen.moves,[])
 h.seen.guard[action]();assert.equal(h.seen.draft,'unsaved reviewer draft')
 assert.equal(h.seen.settled[0].what,action==='stay'?'cancelled':'opened')
 observed('guard '+action,h.seen)
}
{
 const h=harness({resultNow:async()=>badInspection})
 h.m.openResult(h.d,h.launch,o=>h.seen.settled.push(o));await tick()
 assert.equal(h.seen.guard,null);assert.equal(h.seen.settled[0].what,'refused')
 observed('composed mismatched inspection target refused',h.seen)
 const d={...h.d,source:{kind:'post',conversation:F.conversation,post:F.deleted_post}}
 assert.deepEqual(freshlyOpen(d,good).source,d.source)
 observed('fresh result preserves exact declared source',freshlyOpen(d,good).source)
}
for(const kind of ['post','record','conversation']){
 const h=harness();const d={...h.d,work:null,group:null,opens:kind,target:kind==='post'?h.d.target:{kind:'record',ref:kind==='record'?F.note:F.conversation}}
 const n=requests.length;h.m.openResult(d,h.launch);await tick();assert.equal(requests.length,n+1);assert.ok(h.seen.guard)
 observed('B3 unassociated '+kind+' reads exact ref before navigation guard',{requests:requests.length-n,guard:!!h.seen.guard})
}
{
 let release;const h=harness({resultNow:()=>new Promise(r=>{release=r})})
 h.m.openResult(h.d,h.launch,o=>h.seen.settled.push(o));h.m.applyCentre(null);release(F.first);await tick()
 assert.deepEqual(h.seen.moves,[]);assert.equal(h.seen.guard,null);assert.deepEqual(h.seen.said,[])
 observed('late navigation dropped',h.seen)
}
{
 let release;const h=harness({resultNow:()=>new Promise(r=>{release=r})})
 h.m.openResult(h.d,h.launch);binding.saw(P.brain);binding.move();release(F.first);await tick()
 assert.equal(h.seen.guard,null);assert.deepEqual(h.seen.said,[]);assert.deepEqual(h.seen.settled,[])
 observed('B4 real binding moved drops answer',{bindingMoved:binding.moved(),guard:!!h.seen.guard})
}
observed('HTTP requests emitted by real api.read',requests.map(x=>x.url))
writeFileSync(new URL('../evidence/probe-results.json',import.meta.url),JSON.stringify(results,null,2))
