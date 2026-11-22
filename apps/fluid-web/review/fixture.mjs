// Independent synthetic probes against candidate modules and exact handoff wrappers.
// PROVENANCE: this file is the INDEPENDENT REVIEWER's fixture (review adm-e2d35bd306b8,
// clone result-opener-rereview-3a59d4a6), copied byte-for-byte except for the two
// `make()` adapters marked F4 below, which had to follow the corrected host contract.
// It is shared infrastructure, not this correction's own work.
import { registerHooks } from 'node:module'
import { readFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import test from 'node:test'
import assert from 'node:assert/strict'
import ts from '../node_modules/typescript/lib/typescript.js'
const hookURL = 'data:text/javascript,' + encodeURIComponent('export const useRef = v => ({current:v}); export const useEffect = f => globalThis.reviewEffects.push(f);')
registerHooks({
  resolve(s, c, next) {
    if (s === 'react' && /\/(places|centreHistory)\.ts$/.test(c.parentURL)) return { url: hookURL, shortCircuit: true }
    if (s.startsWith('.')) for (const ext of ['.ts', '.tsx', '/index.ts']) {
      const url = new URL(s + ext, c.parentURL)
      if (existsSync(fileURLToPath(url))) return { url: url.href, shortCircuit: true }
    }
    return next(s, c)
  },
  load(url, c, next) {
    if (url.endsWith('.css')) return { format: 'module', source: '', shortCircuit: true }
    if (/\.tsx?$/.test(url)) return { format: 'module', shortCircuit: true, source: ts.transpileModule(readFileSync(fileURLToPath(url), 'utf8').replaceAll('import.meta.env', '({})'), { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX } }).outputText }
    return next(url, c)
  },
})
globalThis.localStorage = { getItem: () => null, setItem() {}, removeItem() {} }
const M = await import('../src/quiet2/results/mount.ts')
const L = await import('../src/quiet2/results/launch.ts')
const O = await import('../src/quiet2/results/opener.ts')
const V = await import('../src/quiet2/viewer/viewers.ts')
const T = await import('../src/quiet2/results/targets.ts')
const H = await import('../src/quiet2/results/hostOpen.ts')
const R = await import('../src/quiet2/results/refRead.ts')
const { heldItem } = await import('../src/quiet2/brain/logic.ts')
const { usePlaces } = await import('../src/quiet2/places.ts')
const handoff = readFileSync(new URL('../src/quiet2/results/HOST-INTEGRATION.md', import.meta.url), 'utf8')
const baseline = readFileSync(new URL('../src/quiet2/Quiet2.tsx', import.meta.url), 'utf8')
const code = [...handoff.matchAll(/```tsx\r?\n([\s\S]*?)```/g)].map(m => m[1]).join('\n')
function variable(name, input = code) {
  const sf = ts.createSourceFile('snippet.tsx', input, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
  let found
  function visit(n) { if (ts.isVariableDeclaration(n) && n.name.getText(sf) === name) found = n.initializer; ts.forEachChild(n, visit) }
  visit(sf); assert.ok(found, name); return found.getText(sf)
}
function property(name) {
  const sf = ts.createSourceFile('snippet.tsx', 'const p = ' + variable('resultPage'), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
  const obj = sf.statements[0].declarationList.declarations[0].initializer
  const p = obj.properties.find(p => p.name?.getText(sf) === name)
  assert.ok(p, name); return p.initializer.getText(sf)
}
function evaluate(expr, deps) {
  const js = ts.transpileModule('const extracted = ' + expr, { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText
  return new Function(...Object.keys(deps), js + '; return extracted')(...Object.values(deps))
}
const brain = 'fixture-corpus@instance-1', A = 'adm-111111111111', B = 'adm-222222222222', ASK = 'opr-aaaaaaaaaaaa'
const HELD = { state: 'held', name: 'review.txt', size: 20, claimed_media_type: 'text/plain' }
const ref = (id = A, extra = {}) => ({ id, type: 'file', state: 'ok', available: true, opens: 'file', file: HELD, ...extra })
const dest = (id = A, extra = {}) => T.destinationOfRef(ref(id, extra))
const tick = () => new Promise(r => setImmediate(r))
const ids = new Set()
function reset() {
  for (const row of M.placedResults().all()) V.closeViewer(row.viewer)
  for (const id of ids) V.closeViewer(id)
  if (V.maximised()) V.closeViewer(V.maximised().id)
  ids.clear(); L.clearLaunches(); M.resetPlacedResults()
}
function launch({ conversation = 'ent-origin', decision = null } = {}) {
  return L.holdLaunch({ opening: L.beginOpening(), brainKey: brain, place: { conversation, centre: null }, thread: {root:'ent-thread',at:'ent-at'}, reading: {scroll:417,offset:12}, reply:'ent-reply', draft:'thread:ent-origin:ent-thread', focus: {control:'result:'+A,fallback:{kind:'conversation'}}, decision })
}
const stillHeld = async ref => ({how:'held',file:{...HELD,ref}})
const decision = () => ({form:null,question:ASK,item:'fixture',ref:A,role:null})
function make(over = {}) {
  if (over.brainKey) { over = {...over,serving:over.brainKey}; delete over.brainKey }
  let at = null, conversation = 'ent-origin', pending = null, chooser
  const seen = { notices:[], centres:[], restores:[], focuses:[], returns:[], sources:[], revealed:[] }
  const guard = (go, stay = () => {}) => { if (over.asks) pending = {go,stay}; else go() }
  const page = {
    spaceKey:()=> 'https://fixture.invalid||fixture-corpus', serving:()=>brain, origin:()=> 'https://fixture.invalid', conversation:()=>conversation, centreAt:()=>at,
    enterCentre:to=>{at=to},artifactNow:stillHeld,reveal:p=>seen.revealed.push(p),
    columns:()=>[],freeColumn:()=>null,choose:q=>{chooser=q},invoker:()=>null,hasControl:()=>false,
    focus:(choice,invoker)=>seen.focuses.push({choice,invoker}),centreGo:to=>{at=to;seen.centres.push(to)},centreReplace:to=>{at=to},
    backTo:(p,done,stay)=>guard(()=>{conversation=p.conversation;at=p.centre;done()},stay),
    // F4 (adm-e2d35bd306b8): the move asks `begin` inside the guard and takes its
    // reference and its report from that answer; null moves nothing at all.
    pickConversation:(c,begin,stay)=>{guard(()=>{const go=begin();if(!go)return;conversation=go.ref;go.moved()},stay);return true},
    openPost:(c,p,done,begin)=>guard(()=>{const go=begin();if(!go)return;conversation=go.ref;done('completed')},()=>done({how:'cancelled'})),
    record:(begin,stay)=>guard(()=>{const go=begin();if(!go)return;go.moved()},stay),goToPost:(c,p)=>seen.sources.push({conversation:c,post:p}),
    heldItem,putBack:s=>seen.restores.push(s),offerReturn:l=>seen.returns.push(l),say:s=>seen.notices.push(s),...over,
  }
  const m = M.mountResults(page)
  return {page,m,seen,guard, pending:()=>pending, answer:how=>{const q=pending;pending=null;q[how]()}, setAt:x=>{at=x}, chooser:()=>chooser}
}
function historyFixture({unfinished=true}={}) {
  reset();globalThis.reviewEffects=[];const listeners=new Map(),states=[null];let index=0,left=false,centre,x
  globalThis.history={get state(){return states[index]},replaceState:s=>{states[index]=s},pushState:s=>{states.splice(index+1);states.push(s);index++},go:n=>{const next=index+n;if(next<0||next>=states.length){left=true;return};index=next;const state=states[index];queueMicrotask(()=>listeners.get('popstate')?.({state}))}}
  globalThis.window={addEventListener:(k,f)=>listeners.set(k,f),removeEventListener:()=>{},setTimeout:()=>0}
  x=make();const at={current:null};let asks=0,pending=null
  const guarded=evaluate(variable('guarded'),{leaving:()=>({ask:unfinished?{title:'unfinished'}:null}),unfinished:()=>null,setLeave:q=>{asks++;pending=q},setNotice:()=>{},CENTRE:'centre'})
  x.page.centreAt=()=>at.current;x.page.enterCentre=evaluate(property('enterCentre'),{centreAt:at})
  const Rproxy={applyCentre:to=>x.m.applyCentre(to)}
  centre=usePlaces({c:'ent-origin',at:null},{apply:evaluate(variable('applyCentre'),{R:Rproxy,brainLeft:{current:null},document:{querySelector:()=>null},setUnread:()=>{},keepBrainCard:{current:false},setBrainOpen:()=>{},setSourcesOpen:()=>{},setSourcesWanted:()=>{},sourcesRead:{reload:()=>{}},spaceRef:{current:{apply:()=>null}},setBrainMain:()=>{},setSourceMain:()=>{},setSourceLast:()=>{}}),show:()=>{},ask:()=>false,address:()=>null})
  for(const effect of globalThis.reviewEffects)effect()
  x.page.centreGo=evaluate(property('centreGo'),{centre});x.page.centreReplace=evaluate(property('centreReplace'),{centre});x.page.backTo=evaluate(property('backTo'),{centre,guarded,CENTRE:'centre'})
  x.m=M.mountResults(x.page)
  return Object.assign(x,{centre,at,asks:()=>asks,states,index:()=>index,left:()=>left,question:()=>pending,answer:how=>{const q=pending;pending=null;q[how]?.()}})
}

export {M,L,O,V,T,H,R,heldItem,brain,A,B,ASK,HELD,ref,dest,tick,reset,launch,decision,make,historyFixture,stillHeld,property,variable,evaluate}
