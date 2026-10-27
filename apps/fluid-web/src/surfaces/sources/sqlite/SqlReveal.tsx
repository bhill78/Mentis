import type { Sample } from './types'
export default function SqlReveal({ sample, file, table, open, onOpen }: { sample?: Sample; file: string; table: string; open: boolean; onOpen: (b:boolean)=>void }) {
  return <details open={open} onToggle={e=>onOpen(e.currentTarget.open)}><summary>What Mentis will run for {table} (read-only)</summary>
    <pre>-- read-only, on the private snapshot of {file}{'\n'}{sample?.run.sql}{'\n'}{sample?.run.params.map(p=>`-- ?${p.n} = ${JSON.stringify(p.value[1])}`).join('\n')}</pre>
    <p>Mentis generates this from your choices above. You can't edit it. Values go in separately as parameters and are never pasted into the SQL. It runs on the private snapshot, never on your file.</p></details>
}
