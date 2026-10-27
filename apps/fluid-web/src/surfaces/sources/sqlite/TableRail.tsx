import { bytes } from '../route'
import { figure } from './figures'
import { complete, config, type Cfg, type Samples, type Table } from './types'
export default function TableRail({ tables, sel, chosen, cfg, samples, active, onActive, onTables }: {
  tables: Table[]; sel: string[]; chosen: string[]; cfg: Cfg; samples: Samples; active: string; onActive: (s: string)=>void; onTables: ()=>void
}) {
  return <aside className="sql-rail"><h3 className="src-label">Ticked tables</h3>{tables.filter(t=>sel.includes(t.name)).sort((a,b)=>Number(!chosen.includes(a.name))-Number(!chosen.includes(b.name))||a.name.localeCompare(b.name)).map(t=>{
    const c=config(cfg,t.name), f=figure(t,cfg,samples), undecided=t.columns.filter(col=>col.secret&&!c.decisions[col.name]).length
    return <button className={active===t.name?'on':''} key={t.name} onClick={()=>onActive(t.name)}><b>{t.name}</b> {c.rows.some(complete)&&'▽'} {t.columns.some(c=>c.secret)&&'🔒'}
      <small>{!samples[t.name]?'counting on the snapshot…':`${c.rows.some(complete)?`${f.rows ?? '?'} of ${f.base}`:`all ${f.base}`} rows · ${f.bytes==null?'size unknown':bytes(f.bytes)}`}{!chosen.includes(t.name)&&' · suggested'}</small>
      {undecided>0&&<small className="sql-undecided">{undecided} secret column(s) to decide</small>}</button>})}
    <button className="link" onClick={onTables}>Change tables</button></aside>
}
