import { useEffect, useRef, useState } from 'react'
import { post, useApi } from '../../../api'
import { Chooser } from '../FilesystemFlow'
import { bytes, runToEnd, type Picker, type RunView, type SourcesAnswer } from '../route'
import { baseName, cleanPath, forget, readRecent, remember } from './recent'
import WaitingForDialog from './WaitingForDialog'

type Picked = void | false | { kind: 'file' | 'folder'; size?: number }
export default function PickSource({ purpose, picker, onPath, onFolderToSearch, autoPick }: {
  purpose: 'database' | 'folder'; picker?: Picker
  onPath: (path: string, viaFile?: string) => Picked | Promise<Picked>
  onFolderToSearch?: (path: string) => void | Promise<void>
  autoPick?: 'file' | 'folder'
}) {
  const all = useApi<SourcesAnswer>(picker ? null : '/api/sources')
  const status = picker ?? all.data?.picker
  const [typed, setTyped] = useState(''), [notice, setNotice] = useState(''), [error, setError] = useState('')
  const [recent, setRecent] = useState(readRecent), [browse, setBrowse] = useState(false)
  const [run, setRun] = useState<RunView | null>(null), [mode, setMode] = useState('')
  const database = purpose === 'database'
  const usePath = async (path: string, kind: 'file' | 'folder', via?: string) => {
    if (!path) return
    setError('')
    try {
      let result: Picked = undefined
      if (database && kind === 'folder') await onFolderToSearch?.(path)
      else result = await onPath(path, via)
      if(result!==false)setRecent(remember({ path, kind:result?.kind??kind, purpose, ...(result?.size!=null?{size:result.size}:{}) }))
    } catch (e) { setError((e as Error).message) }
  }
  const [pickError, setPickError] = useState('')
  const pick = async (m: 'file' | 'folder') => {
    setMode(m); setError(''); setPickError('')
    try {
      const end = await runToEnd(post<RunView>('/api/sources/pick', { mode: m, purpose: database ? 'sqlite' : 'folder' }), setRun)
      if (end.state !== 'done') throw new Error(end.failure ?? end.state)
      const result = end.result as { state: string; path?: string; folder?: string; reason?: string }
      if (result.state === 'chosen' && result.path) await usePath(database ? result.path : result.folder ?? result.path,
        database ? m : 'folder', !database && m === 'file' ? result.path : undefined)
      else if (result.state !== 'cancelled') setPickError(result.reason ?? 'The dialog timed out. Try again or paste a path.')
    } catch (e) { setPickError((e as Error).message) } finally { setRun(null); setMode('') }
  }
  // While the picker is out the path field stays usable for typing, but using a path waits for it:
  // whichever answered second would otherwise replace the first.
  const pending = !!mode
  const submit = async () => {
    if (pending) return
    setPickError('')
    const { path, quoted } = cleanPath(typed)
    setTyped(path); setNotice(quoted ? 'Removed the quotes that Windows adds with “Copy as path”.' : '')
    if (!path) { setError('Type or paste a full path.'); return }
    await usePath(path, database ? 'file' : 'folder')
  }
  const opened=useRef(false)
  useEffect(()=>{
    if(autoPick&&status?.available&&!opened.current){opened.current=true;void pick(autoPick)}
    // Open only once when the caller explicitly requests a native dialog.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  },[autoPick,status?.available])
  return <div className={pending ? 'src-picker pending' : 'src-picker'} aria-busy={pending || undefined}>
    {pending && <div className="src-pick-dim" aria-hidden="true" />}
    {status?.available ? <div className="src-pickbox"><div className="src-actions">
      <button className="btn primary" disabled={pending} onClick={() => void pick(database ? 'file' : 'folder')}>{database ? 'Choose a database file…' : 'Choose a folder…'}</button>
      <button className="btn quiet" disabled={pending} onClick={() => void pick(database ? 'folder' : 'file')}>{database ? 'Look in a folder…' : 'Pick a file inside it…'}</button>
      {pending && <WaitingForDialog runKey={run?.key} />}
    </div>{pickError && <p className="act-refused src-pick-error">{pickError}</p>}<p className="src-faint">{database ? 'Opens the Windows Open dialog on this computer. Look in a folder lets you choose a folder, then shows the databases Mentis finds in it.' : 'Opens the Windows folder dialog on this computer. Pick a file inside it uses the folder that contains the file you pick.'} Only the path you pick reaches Mentis, and it is opened read-only.</p></div>
      : <p className="src-faint">{status?.why_not ?? 'Reading picker availability…'}</p>}
    <label className="src-field"><span className="src-label">Or type or paste a path</span><input value={typed} onChange={e => setTyped(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') void submit() }}
      placeholder={database ? 'C:\\Users\\you\\data.db  (a file, or a folder to search)' : 'C:\\Users\\you\\Documents'} /></label>
    <button className="btn quiet" disabled={pending} title={pending ? 'Finish or cancel the Windows picker first' : undefined} onClick={() => void submit()}>Use this path</button>
    <p className="src-faint">Explorer's “Copy as path” works: Mentis removes the quotes it adds. {notice}</p>
    <h3 className="src-h2">Recent</h3>{recent.filter(x => x.purpose === purpose && (database || x.kind === 'folder')).map(x => <div className="src-recent" key={x.path}>
      <button className="link" disabled={pending} onClick={() => void usePath(x.path, x.kind)}><b>{baseName(x.path)}</b> · {x.path} {x.size != null && bytes(x.size)} {database && x.kind === 'folder' && 'folder: shows the databases in it'} · used {Math.max(0, Math.floor((Date.now()-x.used_at)/60000))} min ago</button>
      <button className="btn quiet" aria-label={`Remove ${x.path} from Recent`} onClick={() => setRecent(forget(x))}>×</button></div>)}
    {!database && <><button className="link" disabled={pending} onClick={() => setBrowse(!browse)}>Browse folders here…</button>{browse && <Chooser onChoose={p => { if (pending) return; setBrowse(false); void usePath(p, 'folder') }} />}</>}
    {error && <p className="act-refused">{error}</p>}
  </div>
}
