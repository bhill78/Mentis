import type { Choice } from '../route'
export const secretId = (table: string, column: string) => `secret-${encodeURIComponent(table)}-${encodeURIComponent(column)}`
export function focusSecret(table: string, column: string) {
  const node = document.getElementById(secretId(table,column))
  node?.scrollIntoView({ block:'center', behavior:'smooth' }); node?.classList.remove('flash')
  requestAnimationFrame(()=>{node?.classList.add('flash');node?.querySelector('input')?.focus()})
}
export default function SecretChoice({ table, column, decision, onChoose }: { table: string; column: string; decision?: Choice; onChoose: (c: Choice) => void }) {
  return <div id={secretId(table,column)} className={'sql-secret'+(!decision?' open':'')}><span>🔒 <code>{column}</code> looks like a secret. <b>Choose one to continue.</b></span>
    <label><input type="radio" name={secretId(table,column)} checked={decision==='exclude'} onChange={()=>onChoose('exclude')} /> Leave it out</label>
    <label><input type="radio" name={secretId(table,column)} checked={decision==='include'} onChange={()=>onChoose('include')} /> Take it. I understand its values will be stored in Mentis and shown to anyone who can read this source. (They stay masked in this preview.)</label></div>
}
