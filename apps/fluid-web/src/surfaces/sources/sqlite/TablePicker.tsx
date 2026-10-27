import { useState } from 'react'
import { bytes, count } from '../route'
import { alsoDropped, closure, parentsOf, selected, suggested } from './linked'
import type { Inspect, Samples } from './types'
export default function TablePicker({ file, chosen, dismissed, onChange, samples = {} }: {
  file: Inspect; chosen: string[]; dismissed: string[]; onChange: (chosen: string[], dismissed: string[]) => void; samples?: Samples
}) {
  const [search, setSearch] = useState(''), [chip, setChip] = useState('All'), [sort, setSort] = useState('size'), [internal, setInternal] = useState(false)
  const [note, setNote] = useState<{ table: string; added: string[]; dropped: string[] } | null>(null)
  const tables = file.tables, sel = selected(tables, chosen, dismissed), sugg = suggested(tables, chosen, dismissed)
  const paths = closure(tables, chosen, dismissed), hidden = tables.filter(t => t.internal)
  const toggle = (name: string) => {
    let next = chosen, blocked = dismissed
    if (sel.includes(name)) {
      if (chosen.includes(name)) next = chosen.filter(n => n !== name)
      else blocked = [...dismissed, name]
    } else { next = [...chosen, name]; blocked = dismissed.filter(n => n !== name) }
    const after = selected(tables, next, blocked)
    setNote({ table: name, added: after.filter(n => !sel.includes(n) && n !== name), dropped: chosen.includes(name) ? sel.filter(n => !after.includes(n) && n !== name) : [] })
    onChange(next, blocked)
  }
  const visible = tables.filter(t => (internal || !t.internal) && t.name.toLowerCase().includes(search.toLowerCase()) &&
    (chip === 'All' || chip === 'Ticked' && sel.includes(t.name) || chip === 'Linked to ticked' && tables.some(c => sel.includes(c.name) && parentsOf(tables, c.name).includes(t.name)) || chip === 'Large (over 5 MB)' && (t.bytes ?? 0) > 5*1048576))
    .sort((a,b) => sort === 'name' ? a.name.localeCompare(b.name) : sort === 'rows' ? (b.rows ?? -1)-(a.rows ?? -1) : (b.bytes ?? -1)-(a.bytes ?? -1))
  return <><h2 className="src-h2">What to take from {file.path.split(/[\\/]/).pop()}</h2><p className="src-note">Tick the tables you want. Each row shows its size, so you can see what each choice costs. When you tick a table, the tables it <b>points to</b> are ticked too, as suggestions you can untick. Linked tables are taken <b>in full</b>, and you can narrow them in the next step.</p>
    <div className="sql-toolbar"><input placeholder="Find a table…" value={search} onChange={e => setSearch(e.target.value)} />
      {['All','Ticked','Linked to ticked','Large (over 5 MB)'].map(x => <button className={'btn quiet'+(chip===x?' on':'')} aria-pressed={chip===x} key={x} onClick={() => setChip(x)}>{x}{x==='All' ? ` ${tables.length}` : x==='Ticked' ? ` ${sel.length}` : ''}</button>)}
      <label>Sort <select value={sort} onChange={e => setSort(e.target.value)}><option value="name">Name</option><option value="size">Largest first</option><option value="rows">Most rows</option></select></label>
      <button className="link" onClick={() => { onChange(tables.filter(t => !t.virtual).map(t => t.name), []); setNote(null) }}>Select all ({bytes(file.size)})</button>
      <button className="link" onClick={() => { onChange([], []); setNote(null) }}>Clear</button></div>
    <div className="sql-tlist"><div className="sql-thead"><span>Table</span><span>Rows</span><span>Size</span></div>
      {visible.map(t => <div key={t.name} className={sugg.includes(t.name) ? 'sql-table suggested' : 'sql-table'}>
        <div className="sql-trow"><label><input type="checkbox" checked={sel.includes(t.name)} disabled={t.virtual} onChange={() => toggle(t.name)} /> <b>{t.name}</b>
          {t.parents.length > 0 && <small title={`Points to ${parentsOf(tables,t.name).join(', ')}`}> → {parentsOf(tables,t.name).join(', ')}</small>}
          {t.columns.some(c => c.secret) && <small> 🔒 {t.columns.filter(c=>c.secret).length} secret-looking column(s)</small>}
          {t.internal && <small> internal · search index</small>}
          {sugg.includes(t.name) && <small className="sql-why">suggested · {paths[t.name]?.join(' → ')}</small>}</label>
          <span>{samples[t.name]?.total ?? (t.rows == null ? t.rows_state : count(t.rows))}</span><span>{t.bytes == null ? 'size unknown' : bytes(t.bytes)}<meter value={t.bytes ?? 0} max={Math.max(1,...tables.map(t=>t.bytes??0))} /></span></div>
        <details><summary>details</summary>{t.columns.map(c => <p key={c.name}><code>{c.pk ? '🔑 ' : ''}{c.name}</code> {c.type} {t.parents.filter(p=>p.column===c.name).map(p=>`→ ${p.table}.${p.target ?? ''}`).join(', ')} {c.secret && 'looks secret, so it is left out unless you agree'}</p>)}
          <p>{t.children.length ? `Referenced by: ${t.children.join(', ')} (never suggested automatically: tick them yourself if you want them)` : 'Nothing points to this table.'}</p></details>
        {note?.table === t.name && note.added.length > 0 && <div className="sql-rowstrip">Also ticked, because <b>{t.name}</b> points to them: <b>{note.added.join(', ')}</b> (+{bytes(tables.filter(t=>note.added.includes(t.name)).reduce((s,t)=>s+(t.bytes??0),0))}, taken in full).
          <button className="link" onClick={()=>setChip('Ticked')}>Show ticked tables</button> <button className="link" onClick={()=>{onChange(chosen,[...dismissed,...note.added]);setNote(null)}}>Don't take these</button></div>}
        {note?.table === t.name && note.dropped.length > 0 && <div className="sql-rowstrip">Also unticked: {note.dropped.join(', ')}.</div>}
        {dismissed.includes(t.name) && <div className="sql-rowstrip dangling">{tables.filter(c=>sel.includes(c.name)&&parentsOf(tables,c.name).includes(t.name)).map(c=>c.name).join(', ')} points to {t.name}, which you are leaving out. Those links will point to rows Mentis doesn't hold.
          {alsoDropped(tables, chosen, dismissed, t.name).length > 0 && <span> Leaving out {t.name} also unticks <b>{alsoDropped(tables,chosen,dismissed,t.name).join(' and ')}</b>, which was ticked only through {t.name}.</span>}
          <button className="link" onClick={()=>onChange(chosen,dismissed.filter(n=>n!==t.name))}>Tick it again</button></div>}
      </div>)}</div>
    {hidden.length > 0 && <button className="link" onClick={()=>setInternal(!internal)}>{internal ? `Hide the ${hidden.length} internal search-index tables` : `${hidden.length} internal search-index tables (${hidden.map(t=>t.name).join(', ')}) are hidden. Show them`}</button>}
    <p className="src-faint">Counted on the file just now. The preview's counts come from its own snapshot and may differ slightly. {tables.some(t=>t.bytes_basis.includes('approximate')) && 'Sizes are approximate while the file is in use'} {Object.keys(samples).length > 0 && "Tables you have previewed show the snapshot's counts."}</p>
  </>
}
