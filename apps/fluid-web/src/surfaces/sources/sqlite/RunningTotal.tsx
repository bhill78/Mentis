import { bytes, count } from '../route'
import { totals } from './figures'
import type { Cfg, Inspect, Samples } from './types'
export default function RunningTotal({ file, sel, chosen, cfg, samples, preview = false, onBack, onNext, disabled, children }: {
  file: Inspect; sel: string[]; chosen: string[]; cfg: Cfg; samples: Samples; preview?: boolean
  onBack: () => void; onNext: () => void; disabled?: boolean; children?: React.ReactNode
}) {
  const f = totals(file.tables, sel, cfg, samples)
  const secrets = file.tables.filter(t => sel.includes(t.name)).flatMap(t => t.columns.filter(c => c.secret)).length
  return <div className="sql-totals"><div><b>{f.tables} tables · {f.rows == null ? 'count unknown' : count(f.rows)} rows · {f.bytes == null ? 'size unknown' : '≈ '+bytes(f.bytes)}</b> of {bytes(file.size)} · includes {sel.filter(n => !chosen.includes(n)).length} suggested
    <meter value={f.bytes ?? 0} max={file.size || 1} /><p className="src-faint">{preview ? 'Counts are taken on the snapshot and update as you change columns and filters.' : sel.length ? `Whole tables, with ${secrets} secret-looking columns left out until you decide. You can narrow columns and rows in the next step.` : 'Nothing ticked yet.'}</p></div>
    <div>{!preview && <><p>Next, Mentis takes a private snapshot. It copies the <b>whole {bytes(file.size)} file</b>, read-only, so the data can't change under you. Only the ticked tables are kept.</p>{file.disk.ok && <p>{file.disk.message}</p>}</>}{children}
      <div className="src-actions"><button className="btn quiet" onClick={onBack}>{preview ? '← Tables' : '← Back'}</button> <button className="btn primary" disabled={preview ? disabled : !sel.length || !file.disk.ok} onClick={onNext}>{preview ? 'Review & acquire →' : 'Preview & check data →'}</button></div>
    </div></div>
}
