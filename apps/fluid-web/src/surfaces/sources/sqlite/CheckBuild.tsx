import { useEffect, useRef, useState } from 'react'
import { post } from '../../../api'
import ColumnLanes from './ColumnLanes'
import RowRules from './RowRules'
import SampleGrid from './SampleGrid'
import SqlReveal from './SqlReveal'
import TableRail from './TableRail'
import ValuePopover, { type Pop } from './ValuePopover'
import { wireRules } from './rules'
import { config, type Cfg, type Config, type Inspect, type Sample, type Samples } from './types'
export default function CheckBuild({ file, sel, chosen, cfg, samples, plan, active, onActive, onChange, onSample, onTables, linkWarning, notices }: {
  file: Inspect; sel: string[]; chosen: string[]; cfg: Cfg; samples: Samples; plan: string; active: string
  onActive: (s:string)=>void; onChange: (table:string,c:Config)=>void; onSample: (table:string,s:Sample)=>void; onTables: ()=>void; linkWarning?: React.ReactNode; notices?: React.ReactNode
}) {
  const [pop,setPop]=useState<Pop|null>(null),[open,setOpen]=useState(false),[removed,setRemoved]=useState(''),[error,setError]=useState('')
  const cache=useRef(new Map<string,Sample>()), key=JSON.stringify(sel.map(t=>[t,wireRules(config(cfg,t))]))
  useEffect(()=>{
    let cancelled=false
    const timer=setTimeout(async()=>{
      for(const name of [active,...sel.filter(n=>n!==active)]) {
        if(cancelled) return
        const r=wireRules(config(cfg,name)), id=JSON.stringify([plan,name,r])
        try { let s=cache.current.get(id); if(!s){s=await post<Sample>('/api/sources/sqlite/sample',{plan,table:name,rules:r});cache.current.set(id,s)}
          if(!cancelled) {onSample(name,s);setError('')} }
        catch(e){if(!cancelled)setError((e as Error).message)}
      }
    },Object.keys(samples).length?300:0)
    return()=>{cancelled=true;clearTimeout(timer)}
    // The wire key deliberately ignores incomplete filter drafts. Samples
    // arriving do not restart the sequential background sampling queue.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  },[plan,active,key])
  const table=file.tables.find(t=>t.name===active), c=config(cfg,active), sample=samples[active]
  const move=(name:string)=>{
    const col=table?.columns.find(x=>x.name===name)
    if(!col||col.secret||col.pk||sample?.columns.find(x=>x.name===name)?.key)return
    const omit=c.omit.includes(name)?c.omit.filter(n=>n!==name):[...c.omit,name]
    if(omit.includes(name)&&c.rows.some(r=>r.column===name))setRemoved(name)
    onChange(active,{...c,omit,rows:c.rows.filter(r=>!omit.includes(r.column))});setPop(null)
  }
  return <><div className="sql-ok">Snapshot taken · <code>{plan}</code> · nothing has been recorded yet. Every count and sample below comes from that snapshot.</div>{notices}
    {error&&<p className="act-refused">{error}</p>}<div className="sql-build"><TableRail tables={file.tables} sel={sel} chosen={chosen} cfg={cfg} samples={samples} active={active} onActive={n=>{onActive(n);setPop(null);setRemoved('')}} onTables={onTables}/>
    {table&&<div className="sql-stack"><ColumnLanes table={table} cfg={c} sample={sample} onChange={c=>onChange(active,c)} onMove={move}/>
      <RowRules table={table} cfg={c} sample={sample} onChange={c=>onChange(active,c)} removed={removed}/>{linkWarning}
      <SampleGrid sample={sample} table={table} cfg={c} onValue={setPop}/><SqlReveal sample={sample} file={file.path} table={active} open={open} onOpen={setOpen}/>
    </div>}</div>{pop&&sample&&<ValuePopover pop={pop} sample={sample} onClose={()=>setPop(null)} onRule={r=>{onChange(active,{...c,rows:[...c.rows,r]});setPop(null)}} onOmit={sample.columns.find(x=>x.name===pop.column)?.key?undefined:()=>move(pop.column)}/>}</>
}
