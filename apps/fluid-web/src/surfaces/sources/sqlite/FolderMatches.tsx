import { bytes } from '../route'
export interface Matches { folder: string; matches: { path: string; name: string; size: number; sqlite?: boolean; modified: number }[]; capped?: boolean }
export default function FolderMatches({ scan, onPick, onClose, onFolder }: { scan: Matches; onPick: (p: string) => void; onClose: () => void; onFolder: () => void }) {
  return <div className="src-card scan"><h2 className="src-label">Databases in {scan.folder} (and one level of subfolders)</h2>
    {scan.matches.map(m => <button className="scan-file" key={m.path} disabled={m.sqlite === false} onClick={() => onPick(m.path)}>
      <b>{m.name}</b><span>{m.path.slice(scan.folder.length).replace(/^[\\/]/, '') || 'this folder'}</span><span>{bytes(m.size)}</span>
      <span>{m.sqlite === false ? '✗ not a SQLite database' : '✓ SQLite database'}</span></button>)}
    {scan.capped && <p>The scan cap was hit; there may be more files.</p>}
    <div className="src-actions"><button className="link" onClick={onFolder}>Look in a different folder</button> <button className="btn quiet" onClick={onClose}>Close</button></div>
  </div>
}
