/* The secret-column gate: a warning at the top of the step, and the short
   reason the bar gives for a held Review button, pointing back up to it. */
const GATE = 'sql-gate'
export type Pending = { table: string; column: string }
export default function SecretGate({ pending, gate, onPick }: { pending: Pending[]; gate: boolean; onPick: (c: Pending) => void }) {
  if(!pending.length)return null
  return <div id={GATE} className="linkwarn sql-gate">{gate&&<b>Decide every secret-looking column first.</b>}<p>🔒 Still to decide: {pending.map(c=><span className="sql-pending" key={c.table+c.column}><button className="link" onClick={()=>onPick(c)}>{c.table}.{c.column}</button></span>)}</p></div>
}
export function GateReason({ count }: { count: number }) {
  if(!count)return null
  const up=()=>document.getElementById(GATE)?.scrollIntoView({ block:'center', behavior:'smooth' })
  return <p className="sql-reason"><button className="link" onClick={up}>Decide {count} secret column{count===1?'':'s'} first ↑</button></p>
}
