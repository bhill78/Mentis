import type { Preview, Scope } from '../route'
import { selected } from './linked'
import { wireRules, realNumber } from './rules'
import { config, type Cfg, type Config, type Inspect, type Sample, type Samples } from './types'
export interface State {
  step: number; file: Inspect | null; chosen: string[]; dismissed: string[]; cfg: Cfg; samples: Samples
  snapshot: Preview | null; acquire: Preview | null; active: string; gate: boolean
  patterns: string[]; exclude: string[]
  original?: Scope; baseChosen?: string[]
}
export const initial: State = { step:1,file:null,chosen:[],dismissed:[],cfg:{},samples:{},snapshot:null,acquire:null,active:'',gate:false,patterns:[],exclude:[] }
export const selection = (s: State) => s.file ? selected(s.file.tables,s.chosen,s.dismissed) : []
export const undecided = (s: State) => s.file?.tables.filter(t=>selection(s).includes(t.name)).flatMap(t=>t.columns.filter(c=>c.secret&&!config(s.cfg,t.name).decisions[c.name]).map(c=>({table:t.name,column:c.name}))) ?? []
export const options = (s: State) => ({ tables:Object.fromEntries(Object.entries(s.cfg).map(([t,c])=>[t,wireRules(c)]).filter(([,r])=>{const c=r as ReturnType<typeof wireRules>;return c.omit.length||c.rows.length})) })
export const consent = (s: State) => Object.fromEntries(s.file?.tables.filter(t=>selection(s).includes(t.name)).flatMap(t=>Object.entries(config(s.cfg,t.name).decisions).map(([c,d])=>[t.key+'/'+encodeURIComponent(c).replace(/[!'()*]/g,c=>'%'+c.charCodeAt(0).toString(16).toUpperCase()),d])) ?? [])
export const scopeOf = (s: State): Scope => {
  const sel=selection(s), same=s.original&&JSON.stringify([...sel].sort())===JSON.stringify([...(s.baseChosen??[])].sort())
  return { include:same?s.original!.include:[...s.file?.tables.filter(t=>sel.includes(t.name)).map(t=>t.key)??[],...s.patterns],
    exclude:same?s.original!.exclude:[...s.exclude,...(s.patterns.length?s.file?.tables.filter(t=>!sel.includes(t.name)).map(t=>t.key)??[]:[])],options:options(s) }
}
const stable = (x: unknown): string => {
  if(Array.isArray(x))return JSON.stringify(x.length===2&&x[0]==='real'?['real',realNumber(x[1] as string)]:x.map(v=>stable(v)))
  if(x&&typeof x==='object')return JSON.stringify(Object.entries(x).sort(([a],[b])=>a.localeCompare(b)).map(([k,v])=>[k,stable(v)]))
  return JSON.stringify(x)
}
export const unchanged = (s: State) => !!s.original && stable(scopeOf(s).include)===stable(s.original.include) && stable(scopeOf(s).exclude)===stable(s.original.exclude) &&
  stable(options(s).tables)===stable(s.original.options?.tables??{})
export type Action = {type:'file';file:Inspect;scope?:Scope}|{type:'tables';chosen:string[];dismissed:string[]}|{type:'config';table:string;cfg:Config}|
  {type:'sample';table:string;sample:Sample}|{type:'snapshot';preview:Preview}|{type:'reviewed';preview:Preview}|{type:'active';table:string}|{type:'go';step:number}|{type:'back'}
export function reducer(s: State, a: Action): State {
  switch(a.type) {
    case 'file': {
      const next={...initial,file:a.file}, cfg:Cfg={}
      if(a.scope) {
        const raw=(a.scope.options?.tables??{}) as Record<string,{omit?:string[];rows?:{column:string;op:Config['rows'][number]['op'];value?:[string,string]}[]}>
        for(const [name,r] of Object.entries(raw)) cfg[name]={omit:r.omit??[],decisions:{},rows:(r.rows??[]).map(r=>({column:r.column,op:r.op,value:r.value?.[0]==='real'?String(realNumber(r.value[1])):r.value?.[1]??'',kind:(r.value?.[0]??'text') as 'text'|'integer'|'real'}))}
        // Exact keys are encoded literals. Keep other globs read-only while
        // resolving their current table matches for the editor's ticks.
        const known=new Set(a.file.tables.map(t=>t.key))
        const patterns=a.scope.include.filter(p=>!known.has(p))
        const glob=(p:string,k:string)=>new RegExp('^'+p.replace(/[.+^${}()|\\]/g,'\\$&').replace(/\*/g,'.*').replace(/\?/g,'.')+'$').test(k)
        const chosen=a.file.tables.filter(t=>a.scope!.include.some(p=>glob(p,t.key))&&!a.scope!.exclude.some(p=>glob(p,t.key))).map(t=>t.name)
        return {...next,step:2,cfg,chosen,patterns,exclude:a.scope.exclude,original:a.scope,baseChosen:chosen}
      }
      return next
    }
    case 'tables': return {...s,chosen:a.chosen,dismissed:a.dismissed,snapshot:null,acquire:null,samples:{},gate:false}
    case 'config': {
      const samples={...s.samples}, old=samples[a.table]
      if(old&&JSON.stringify(wireRules(config(s.cfg,a.table)))!==JSON.stringify(wireRules(a.cfg))) {
        samples[a.table]={...old,matching:null,rows:[],bytes_estimate:null,run:{sql:'',params:[]},matching_note:'Updating sample…'}
      }
      return {...s,cfg:{...s.cfg,[a.table]:a.cfg},samples,acquire:null,gate:false}
    }
    case 'sample': return {...s,samples:{...s.samples,[a.table]:a.sample}}
    case 'snapshot': return {...s,snapshot:a.preview,acquire:null,step:3,active:selection(s).includes(s.active)?s.active:selection(s)[0]??''}
    case 'reviewed': return undecided(s).length||a.preview.can_confirm===false ? {...s,step:3,gate:true} : {...s,acquire:a.preview,step:4,gate:false}
    case 'active': return {...s,active:a.table}
    case 'back': return {...s,step:3,acquire:null}
    case 'go':
      if(a.step===4 && (undecided(s).length||!s.acquire||s.acquire.can_confirm===false)) return {...s,step:3,gate:true}
      if(a.step===3 && !s.snapshot) return s
      return {...s,step:a.step,acquire:a.step<4?null:s.acquire}
  }
}
