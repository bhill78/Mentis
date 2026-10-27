import { useState } from 'react'
import SecretChoice, { focusSecret } from './SecretChoice'
import { isTaken, type Config, type Sample, type Table } from './types'
export default function ColumnLanes({ table, cfg, sample, onChange, onMove }: { table: Table; cfg: Config; sample?: Sample; onChange: (c: Config) => void; onMove: (name: string) => void }) {
  const [drag, setDrag] = useState<string | null>(null)
  const keys = sample?.columns.filter(c=>c.key).map(c=>c.name) ?? table.key_candidates[0] ?? []
  const noKey = sample ? !sample.columns.some(c=>c.key) : !keys.length
  return <section className="sql-section"><h2 className="src-h2">1 · Columns</h2><div className="sql-trays">
    {[true,false].map(taking => <div key={String(taking)} className="sql-tray" onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();if(drag && isTaken(table.columns.find(c=>c.name===drag)!,cfg)!==taking) onMove(drag);setDrag(null)}}>
      <h3 className="src-label">{taking?'Taking':'Leaving out'} · {table.columns.filter(c=>isTaken(c,cfg)===taking).length}</h3>
      {table.columns.filter(c=>isTaken(c,cfg)===taking).map(c=><button key={c.name} className={'sql-cchip'+(keys.includes(c.name)?' key':'')+(c.secret?' secret':'')}
        draggable={!c.secret&&!keys.includes(c.name)&&!noKey} onDragStart={()=>setDrag(c.name)} onDragEnd={()=>setDrag(null)}
        title={keys.includes(c.name)?'Key column: always kept so Mentis can recognise each row and links keep working':undefined}
        onClick={()=>c.secret?focusSecret(table.name,c.name):!keys.includes(c.name)&&!noKey&&onMove(c.name)}>
        {keys.includes(c.name)?'🔑 ':c.secret?'🔒 ':table.parents.some(p=>p.column===c.name)?'🔗 ':''}{c.name}
        {c.secret&&<small>{!cfg.decisions[c.name]?'decide below':cfg.decisions[c.name]==='include'?'taken · masked':'left out'}</small>}</button>)}
      {!taking&&!table.columns.some(c=>!isTaken(c,cfg))&&<p>Nothing. Click or drag a column here to leave it out.</p>}</div>)}
    </div><p className="src-faint">Click a column to move it, or drag it across. The key column is always kept, so links keep working.</p>
    {noKey && <p>This table has no key, so it is taken whole; columns and rows can't be narrowed.</p>}
    {table.columns.filter(c=>c.secret).map(c=><SecretChoice key={c.name} table={table.name} column={c.name} decision={cfg.decisions[c.name]} onChoose={decision=>onChange({...cfg,decisions:{...cfg.decisions,[c.name]:decision}})} />)}
  </section>
}
