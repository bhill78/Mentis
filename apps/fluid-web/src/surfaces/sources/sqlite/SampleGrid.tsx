import { useEffect, useRef } from 'react'
import { bytes } from '../route'
import { isTaken, type Config, type Sample, type Table } from './types'
import type { Pop } from './ValuePopover'
// The sample carries no truncation flag; the backend cuts text at 200 characters and appends '…',
// so a value of exactly 201 code points ending in '…' is the backend's cut, and the title says so.
const CAP=200
const cut=(v: unknown)=>typeof v==='string'&&v.endsWith('…')&&[...v].length===CAP+1
export const valueTitle=(v: unknown)=>v==null?'':cut(v)?`${v}

(The preview holds only the first ${CAP} characters of this value.)`:String(v)
const blobSize=(v: unknown)=>{const m=/^blob · (\d+) bytes$/.exec(String(v));return m?`blob · ${bytes(Number(m[1]))}`:String(v)}
export default function SampleGrid({ sample, table, cfg, onValue }: { sample?: Sample; table: Table; cfg: Config; onValue: (p: Pop)=>void }) {
  const cols=table.columns.filter(c=>isTaken(c,cfg)), scroll=useRef<HTMLDivElement>(null)
  // which edges have more beyond them, and how thick the scrollbars are, so the fades sit inside them
  const measure=()=>{const e=scroll.current,f=e?.parentElement;if(!e||!f)return
    f.dataset.more=[e.scrollTop>0&&'top',e.scrollLeft>0&&'left',e.scrollLeft+e.clientWidth<e.scrollWidth-2&&'right',e.scrollTop+e.clientHeight<e.scrollHeight-2&&'bottom'].filter(Boolean).join(' ')
    f.style.setProperty('--sb-x',`${e.offsetHeight-e.clientHeight-(e.clientTop*2)}px`);f.style.setProperty('--sb-y',`${e.offsetWidth-e.clientWidth-(e.clientLeft*2)}px`)}
  useEffect(()=>{measure();const e=scroll.current;if(!e||typeof ResizeObserver==='undefined')return;const o=new ResizeObserver(measure);o.observe(e);if(e.firstElementChild)o.observe(e.firstElementChild);return()=>o.disconnect()},[sample,cols.length])
  return <section className="sql-section"><h2 className="src-h2">3 · Check the data</h2>{!sample?<p>Counting on the snapshot…</p>:<>
    <div className="sql-grid-cap"><p><span><b>{sample.matching??'unknown'}</b> {sample.matching===sample.total?'rows, all of them':`of ${sample.total??'?'} rows match`} · about {sample.bytes_estimate==null?'size unknown':bytes(sample.bytes_estimate)} · {cols.length} of {table.columns.length} columns</span>
      <span>Showing the first 20. <b>Click any value</b> to filter by it.</span></p>{sample.matching_note&&<p>{sample.matching_note}</p>}</div>
    {sample.matching===0?<p>No rows match. Loosen or remove a filter.</p>:<div className="sql-grid"><div className="sql-grid-scroll" ref={scroll} onScroll={measure}><table><thead><tr>{cols.map(c=>{const links=table.parents.filter(p=>p.column===c.name).map(p=>`→ ${p.table}`).join(', '), meta=sample.columns.find(x=>x.name===c.name)
        return <th key={c.name} className={meta?.typeof==='integer'||meta?.typeof==='real'?'num':undefined} title={`${c.name} · ${c.type}${links?' '+links:''}`}><span className="sql-col">{meta?.key&&<span className="sql-key">🔑</span>}{c.name}</span><small>{c.type}{links&&<span>{links}</span>}</small></th>})}<th className="sql-fill" aria-hidden="true"/></tr></thead>
      <tbody>{sample.rows.map((row,i)=><tr key={i}>{cols.map(c=>{const ix=sample.columns.findIndex(x=>x.name===c.name), v=row[ix], meta=sample.columns[ix], blob=meta?.typeof==='blob', keyless=!sample.columns.some(c=>c.key), empty=v==null||v===''
        return <td key={c.name} className={meta?.typeof==='integer'||meta?.typeof==='real'?'num':undefined}>{c.secret?<span>••••••••</span>:blob?<span title={String(v)}><span className="sql-blob">{blobSize(v)}</span></span>:<button disabled={keyless} className={empty?'empty':undefined} title={valueTitle(v)} onClick={e=>onValue({column:c.name,value:v,x:e.clientX+6,y:e.clientY+6})}>{empty?<i>empty</i>:String(v)}</button>}</td>})}<td className="sql-fill" aria-hidden="true"/></tr>)}</tbody></table></div></div>}</>}
  </section>
}
