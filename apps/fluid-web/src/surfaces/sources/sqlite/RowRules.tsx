import { eligible, kindOf, newRule, operators } from './rules'
import { complete, type Config, type Rule, type Sample, type Table } from './types'
export default function RowRules({ table, cfg, sample, onChange, removed }: { table: Table; cfg: Config; sample?: Sample; onChange: (c: Config) => void; removed?: string }) {
  const change = (i: number, r: Rule) => onChange({...cfg,rows:cfg.rows.map((x,j)=>i===j?r:x)})
  const cols = eligible(table,cfg,sample), keyed = sample?.columns.some(c=>c.key)
  return <section className="sql-section"><h2 className="src-h2">2 · Rows</h2>
    {cfg.rows.length ? <p>Keep only rows where (<b>all</b> of these are true):</p> : <p>Taking <b>every row</b>. Want fewer? Add a filter, or click a value in the sample below.</p>}
    {cfg.rows.map((r,i)=>{const k=kindOf(sample,r.column), ix=sample?.columns.findIndex(c=>c.name===r.column)??-1
      const values=[...new Set(sample?.rows.map(row=>row[ix]).filter(v=>typeof v==='string')??[])] as string[]
      return <div className="frow" key={i}><span>{i?'and':''}</span><select aria-label={`Filter ${i+1} column`} value={r.column} onChange={e=>{const k=kindOf(sample,e.target.value);change(i,{column:e.target.value,op:operators(k)[0][0],value:'',kind:k==='integer'||k==='real'?k:'text'})}}>
        {cols.map(c=><option key={c.name}>{c.name}</option>)}</select>
        <select aria-label={`Filter ${i+1} operator`} value={r.op} onChange={e=>change(i,{...r,op:e.target.value as Rule['op'],value:['is_empty','not_empty'].includes(e.target.value)?'':r.value})}>{operators(k).map(([op,label])=><option value={op} key={op}>{label}</option>)}</select>
        {!['is_empty','not_empty'].includes(r.op)&&<input aria-label={`Filter ${i+1} value`} type={k==='date'?'date':k==='integer'||k==='real'?'number':'text'} value={r.value} list={k==='text'&&values.length<=16?`values-${table.key}-${i}`:undefined} onChange={e=>change(i,{...r,value:e.target.value})} />}
        {k==='text'&&values.length<=16&&<datalist id={`values-${table.key}-${i}`}>{values.map(v=><option value={v} key={v}/>)}</datalist>}
        <button className="btn quiet" aria-label={`Remove filter ${i+1}`} onClick={()=>onChange({...cfg,rows:cfg.rows.filter((_,j)=>j!==i)})}>×</button>{!complete(r)&&<span className="warn">needs a value</span>}</div>})}
    <button className="link" disabled={!keyed||!cols.length} onClick={()=>{const r=newRule(table,cfg,sample);if(r)onChange({...cfg,rows:[...cfg.rows,r]})}}>+ Add a filter</button>
    {removed&&<p>Removed the filter on <code>{removed}</code>, because <code>{removed}</code> is left out.</p>}
    <p><b>Filters are part of what you take.</b> Every refresh runs them again and brings in only matching rows. If a row stops matching, <b>Mentis keeps the copy it already has, but stops updating it.</b> It is not recorded as deleted.</p>
    {cfg.rows.some(complete)&&<p>The values in these filters are saved in Mentis with the source, and show in its history.</p>}
  </section>
}
