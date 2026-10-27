import { Tally } from '../parts'
import { bytes, count, type Preview } from '../route'
import { figure } from './figures'
import { closure, danglingLinks, type Dangling } from './linked'
import LinkWarning from './LinkWarning'
import { sentence } from './rules'
import { complete, config, isTaken, type Cfg, type Inspect, type Samples } from './types'
export default function ReviewSqlite({ file, sel, chosen, cfg, samples, preview, onEdit, onFix, onBack, onAcquire, editing = false }: {
  file: Inspect; sel: string[]; chosen: string[]; cfg: Cfg; samples: Samples; preview: Preview; onEdit: (s:string)=>void
  onFix: (l:Dangling)=>void; onBack: ()=>void; onAcquire: ()=>void; editing?: boolean
}) {
  const paths=closure(file.tables,chosen)
  return <div className="sql-review"><h2 className="src-h2">Ready to acquire</h2><p>Here is everything Mentis will record from <code>{file.path}</code>. Nothing has been recorded yet.</p>
    <Tally cells={[[preview.counts.new,'New rows'],[bytes(preview.bytes_new_to_store),'New to the store'],[file.tables.length-sel.length,'Tables left out'],[bytes(file.size),'Staging copy (temporary)']]}/>
    {editing&&<section className="sql-section"><h2 className="src-h2">What changes</h2><p>{preview.counts.new} rows newly taken · {(preview.counts.kept??0)+(preview.counts.not_examined??0)} rows Mentis keeps but stops updating · {preview.counts.absent} rows gone from the file (recorded as gone) · {preview.counts.widened??0} rows gain columns (widened)</p></section>}
    {file.tables.filter(t=>sel.includes(t.name)).map(t=>{const c=config(cfg,t.name), f=figure(t,cfg,samples), omitted=t.columns.filter(col=>!isTaken(col,c)), filters=c.rows.filter(complete)
      return <div className="src-card" key={t.name}><h3>{t.name} {!chosen.includes(t.name)&&<small>suggested · {paths[t.name]?.join(' → ')}</small>}</h3>
        <p>{omitted.length?`${t.columns.length-omitted.length} of ${t.columns.length} columns. Leaves out ${omitted.map(c=>c.name).join(', ')}`:'All columns'}</p>
        <p>{filters.length?'Only rows where '+filters.map(sentence).join(' and '):'Every row'}</p>
        {!chosen.includes(t.name)&&<p>Taken in full because {paths[t.name]?.[0]} points to it (via {paths[t.name]?.join(' → ')})</p>}
        <span>{f.rows??'?'} rows · {f.bytes==null?'size unknown':'≈ '+bytes(f.bytes)}</span> <button className="link" onClick={()=>onEdit(t.name)}>Edit</button></div>})}
    <LinkWarning links={danglingLinks(file.tables,sel,cfg)} onFix={onFix}/>
    <section className="sql-section"><h2 className="src-h2">🔒 Secret-looking columns</h2>{file.tables.filter(t=>sel.includes(t.name)).flatMap(t=>t.columns.filter(c=>c.secret).map(c=><p key={t.name+c.name}><code>{t.name}.{c.name}</code>: <b>{config(cfg,t.name).decisions[c.name]==='include'?'taken (you agreed; values stored as they are)':'left out (you chose)'}</b></p>))}</section>
    <section className="sql-section"><h2 className="src-h2">On every refresh</h2><p>Mentis takes a fresh snapshot (it copies the whole file again, then deletes the copy) and applies the same tables, columns and filters.</p>
      <p>Rows that newly match are added. If a row stops matching, <b>Mentis keeps the copy it already has, but stops updating it.</b> It is not recorded as deleted.</p>
      <p>A row that is deleted from the file is recorded as gone.</p><p>Linked tables are taken in full on every refresh, unless you give them their own filters.</p>
      <p>Scope saved: include <code>{file.tables.filter(t=>sel.includes(t.name)).map(t=>t.key).join(' · ')}</code> · exclude none · {sel.reduce((n,t)=>n+config(cfg,t).rows.filter(complete).length,0)} row filter(s). The values in these filters are saved in Mentis with the source.</p></section>
    <div className="src-actions"><button className="btn quiet" onClick={onBack}>← Back to preview</button> <button className="btn primary" disabled={preview.can_confirm===false} onClick={onAcquire}>{editing?'Revise and sweep…':`Acquire ${count(preview.counts.new)} rows…`}</button> <span className="src-faint">records this exact snapshot</span></div>
  </div>
}
