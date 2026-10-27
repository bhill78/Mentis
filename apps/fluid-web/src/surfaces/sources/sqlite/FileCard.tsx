import { bytes, count } from '../route'
import { baseName } from '../pick/recent'
import type { Inspect } from './types'
export default function FileCard({ file, onChange, onFolder }: { file: Inspect; onChange: () => void; onFolder: () => void }) {
  return <div className="src-card"><b className="sql-name">{baseName(file.path)}</b><p className="src-mono">{file.path}</p>
    <p className="src-m">{bytes(file.size)} · modified {new Date(file.modified*1000).toLocaleString()}</p>
    <div className="src-actions"><button className="btn quiet" onClick={onChange}>Change file…</button> <button className="btn quiet" onClick={onFolder}>Look in a folder…</button></div>
    <p>This is a SQLite database (format 3): <b>{file.totals.tables} tables · {count(file.totals.rows)} rows</b></p>
    <p>It will be opened read-only. Mentis never writes to this file.</p>
    {file.wal.size > 0 && <p>It is in use: a write-ahead log ({baseName(file.path)}-wal, {bytes(file.wal.size)}) is next to it. The snapshot includes everything committed so far.</p>}
  </div>
}
