import { useEffect, useRef } from 'react'
import { kindOf, operators } from './rules'
import type { Rule, Sample } from './types'
export interface Pop { column: string; value: string | number | null; x: number; y: number }
export default function ValuePopover({ pop, sample, onRule, onOmit, onClose }: { pop: Pop; sample: Sample; onRule: (r: Rule)=>void; onOmit?: ()=>void; onClose: ()=>void }) {
  const ref=useRef<HTMLDivElement>(null), kind=kindOf(sample,pop.column)
  useEffect(()=>{const key=(e:KeyboardEvent)=>{if(e.key==='Escape')onClose()};const outside=(e:MouseEvent)=>{if(!ref.current?.contains(e.target as Node))onClose()}
    document.addEventListener('keydown',key);document.addEventListener('mousedown',outside);return()=>{document.removeEventListener('keydown',key);document.removeEventListener('mousedown',outside)}},[onClose])
  const empty=pop.value==null||pop.value==='', ops=empty?operators('date').slice(2):kind==='date'?operators(kind).slice(0,2):operators(kind).slice(0,kind==='text'?2:4)
  return <div ref={ref} className="pop sql-pop" role="dialog" aria-label="Filter by this value" style={{left:Math.max(8,Math.min(pop.x,window.innerWidth-328)),top:Math.min(pop.y,window.innerHeight-240)}}>
    <div className="pop-note"><b>{pop.column} = {empty?'empty':String(pop.value).slice(0,80)}</b></div>{ops.map(([op,label])=><button className="pop-row" key={op} onClick={()=>onRule({column:pop.column,op,value:empty?'':kind==='date'?String(pop.value).slice(0,10):String(pop.value),kind:kind==='integer'||kind==='real'?kind:'text'})}>Only rows where <b>{pop.column}</b> {label} {empty?'':String(pop.value)}</button>)}
    {onOmit&&<button className="pop-row" onClick={onOmit}>Leave out the column <b>{pop.column}</b></button>}
  </div>
}
