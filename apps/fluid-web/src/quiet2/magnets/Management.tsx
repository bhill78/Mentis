import { useEffect, useRef, useState } from 'react'
import { CLIENT_HEADERS } from '../../api'
import type { SavedMagnet } from './contract'
import { discoverMagnets } from './read'
import { conversationChoices, makeMagnet, type ConversationChoice } from './managementApi'
import './management.css'

export default function Management(p: {
  open: boolean; brainKey: string | null; conversation: string | null;
  canCreate(id: string): boolean; fixture: boolean;
  onOpen(saved: SavedMagnet): void; onClose(): void;
}) {
  const [scope, setScope] = useState(p.conversation ?? '')
  const [source, setSource] = useState(p.conversation ?? '')
  const [query, setQuery] = useState(''), [filter, setFilter] = useState('')
  const [choices, setChoices] = useState<ConversationChoice[]>([]), [next, setNext] = useState<string | null>(null)
  const [cursor, setCursor] = useState<string | null>(null)
  const [rows, setRows] = useState<SavedMagnet[]>([]), [selected, setSelected] = useState('')
  const [words, setWords] = useState(''), [listWords, setListWords] = useState('')
  const [revision, setRevision] = useState(0), [name, setName] = useState('')
  const [creating, setCreating] = useState(false), [form, setForm] = useState(false)
  const operation = useRef<string | null>(null)
  const identity = useRef(p.brainKey); identity.current = p.brainKey
  const current = useRef(p); current.current = p
  const panel = useRef<HTMLDivElement>(null)
  useEffect(() => {
    setScope(p.conversation ?? ''); setSource(p.conversation ?? ''); setRows([]); setSelected(''); setName(''); setCreating(false); setForm(false); operation.current = null
  }, [p.brainKey]) // A Conversation change leaves this panel's explicit scope alone.
  useEffect(() => {
    if (!p.open) return
    requestAnimationFrame(() => panel.current?.querySelector<HTMLInputElement>('input')?.focus())
  }, [p.open])
  useEffect(() => {
    if (!p.open || !p.brainKey) return
    const abort = new AbortController(), key = p.brainKey
    setListWords('Reading Conversations…')
    void conversationChoices(query, cursor, abort.signal).then((got) => {
      if (abort.signal.aborted || identity.current !== key) return
      setChoices((old) => cursor ? [...new Map([...old, ...got.rows].map((c) => [c.id, c])).values()] : got.rows)
      setNext(got.next); setListWords(got.next ? 'More Conversations are available.' : 'Active Conversations read.')
    }).catch((e: Error) => { if (!abort.signal.aborted && identity.current === key) setListWords(e.message) })
    return () => abort.abort()
  }, [p.open, p.brainKey, query, cursor])
  useEffect(() => {
    if (!p.open || !p.brainKey || !scope) return
    const abort = new AbortController(), key = p.brainKey
    setRows([]); setSelected(''); setWords('Reading saved Magnets…')
    void discoverMagnets(scope, async (path, signal) => {
      const r = await fetch(path, { headers: CLIENT_HEADERS, signal, cache: 'no-store' })
      return { status: r.status, body: await r.json().catch(() => null) }
    }, abort.signal).then((found) => {
      if (abort.signal.aborted || identity.current !== key) return
      setRows(found); setWords(found.length ? 'Saved placements in this Conversation. Opening is local to this tab.' : 'No saved Magnet placements here.')
    }).catch((e: Error) => { if (!abort.signal.aborted && identity.current === key) setWords(e.message) })
    return () => abort.abort()
  }, [p.open, p.brainKey, scope, revision])
  useEffect(() => {
    if (!name.trim() && !creating) return
    const warn = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = '' }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [name, creating])
  const change = (f: () => void) => { operation.current = null; f() }
  const create = async () => {
    if (creating || !p.brainKey || !p.canCreate(scope)) return
    const key = p.brainKey, at = scope
    const op = operation.current ?? (operation.current = `quiet-magnet-${crypto.randomUUID()}`)
    setCreating(true); setWords('Creating and placing the Magnet…')
    try {
      const made = await makeMagnet({ key, arrangement: at, source, name, op })
      if (identity.current !== key) return
      setName(''); operation.current = null; setForm(false)
      setRevision((n) => n + 1); setWords('Magnet created. Its own Conversation is unavailable until configured through supported mechanisms.')
      current.current.onOpen(made)
    } catch (e) { if (identity.current === key) setWords(`${(e as Error).message} Your choices and operation key are kept; refresh to check the result. Retrying unchanged choices uses the same operation.`) }
    finally { if (identity.current === key) setCreating(false) }
  }
  if (!p.open) return null
  const selectedRow = rows.find((r) => r.id === selected)
  const opts = (value: string) => <>{value && !choices.some((c) => c.id === value) && <option value={value}>{value}</option>}{choices.map((c) => <option key={c.id} value={c.id}>{c.name || c.id}</option>)}</>
  return <div ref={panel} className="q2-magnet-management" role="dialog" aria-label="Magnet Management" aria-modal="false"
    onKeyDown={(e) => { if (e.key === 'Escape') { e.stopPropagation(); p.onClose() } }}>
    <header><h2>Magnets</h2><button type="button" aria-label="Close Magnet Management" onClick={p.onClose}>×</button></header>
    <p>Find saved Magnets in a Conversation, or create a view of one supported source.</p>
    {p.fixture && <p className="q2-magnet-fixture-note">Disposable fixture: mini Conversation sends and Magnet creation only. The main Conversation is read-only.</p>}
    <label>Find a Conversation<input type="search" value={query} onChange={(e) => { setCursor(null); setQuery(e.target.value) }} /></label>
    <p role="status">{listWords}</p>{next && <button type="button" onClick={() => setCursor(next)}>More Conversations</button>}
    <label>Saved in<select value={scope} disabled={creating} onChange={(e) => change(() => setScope(e.target.value))}><option value="">Choose a Conversation</option>{opts(scope)}</select></label>
    <label>Find a Magnet<input type="search" value={filter} onChange={(e) => setFilter(e.target.value)} /></label>
    <p role="status">{words}</p>
    <div className="q2-magnet-management-rows" role="listbox" aria-label="Saved Magnets">
      {rows.filter((r) => `${r.name} ${r.id}`.toLowerCase().includes(filter.toLowerCase())).map((r) => <button type="button" key={r.id} role="option" aria-selected={selected === r.id} onClick={() => setSelected(r.id)}>
        <strong>{r.name}</strong><small>{r.reason ? `Unavailable: ${r.reason}` : r.id}</small>
      </button>)}
    </div>
    <div className="q2-magnet-management-actions"><button type="button" disabled={!selectedRow || !!selectedRow.reason || !selectedRow.config} onClick={() => { if (selectedRow) p.onOpen(selectedRow) }}>Open selected Magnet</button>
      <button type="button" disabled={creating} onClick={() => setRevision((n) => n + 1)}>Refresh saved Magnets</button></div>
    <button type="button" aria-expanded={form} onClick={() => setForm(!form)}>New Magnet</button>
    {form && <form onSubmit={(e) => { e.preventDefault(); void create() }}>
      <label>Name<input value={name} maxLength={200} disabled={creating} onChange={(e) => change(() => setName(e.target.value))} /></label>
      <label>Source Conversation<select value={source} disabled={creating} onChange={(e) => change(() => setSource(e.target.value))}><option value="">Choose a source</option>{opts(source)}</select></label>
      <p>Posts, Files, Images and Attachments. Reads on request; collection automation and Perspectives unavailable. A new Magnet has no own Conversation.</p>
      {!p.canCreate(scope) && <p>Creation unavailable in this scope or read-only preview.</p>}
      <button type="submit" disabled={creating || !name.trim() || !source || !scope || !p.canCreate(scope)}>{creating ? 'Creating…' : operation.current ? 'Retry same creation' : 'Create Magnet'}</button>
    </form>}
  </div>
}
