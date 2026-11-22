import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import type { MagnetConfig } from '../../fluid/surface/magnet/types'
import type { SavedMagnet } from './contract'
import { conversationChoices, listMagnets, makeMagnet, type ConversationChoice } from './managementApi'
import '../brain/brain.css'
import './management.css'

export type MagnetFilter = 'all' | 'available' | 'unavailable'

export function listedMagnets(rows: SavedMagnet[], query: string, filter: MagnetFilter): SavedMagnet[] {
  const words = query.trim().toLocaleLowerCase()
  return rows.filter((row) => {
    if (filter === 'available' && (row.reason || !row.config)) return false
    if (filter === 'unavailable' && !row.reason && row.config) return false
    return !words || `${row.name} ${row.id}`.toLocaleLowerCase().includes(words)
  })
}

export const openableMagnet = (row: SavedMagnet | undefined): row is SavedMagnet & { config: MagnetConfig } =>
  !!row?.config && !row.reason

const TABS: { id: MagnetFilter; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'available', label: 'Available' },
  { id: 'unavailable', label: 'Needs attention' },
]

export default function Management(p: {
  open: boolean; brainKey: string | null; conversation: string | null;
  canCreate(id: string): boolean; fixture: boolean;
  onOpen(saved: SavedMagnet): void; onClose(): void;
}) {
  const [rows, setRows] = useState<SavedMagnet[] | null>(null)
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<MagnetFilter>('all')
  const [selected, setSelected] = useState('')
  const [view, setView] = useState<'list' | 'detail' | 'create'>('list')
  const [error, setError] = useState<string | null>(null)
  const [revision, setRevision] = useState(0)
  const [sourceQuery, setSourceQuery] = useState('')
  const [choices, setChoices] = useState<ConversationChoice[]>([])
  const [sourceWords, setSourceWords] = useState('')
  const [source, setSource] = useState('')
  const [name, setName] = useState('')
  const [creating, setCreating] = useState(false)
  const [createWords, setCreateWords] = useState('')
  const operation = useRef<string | null>(null)
  const box = useRef<HTMLDivElement>(null)
  const input = useRef<HTMLInputElement>(null)
  const opener = useRef<HTMLElement | null>(null)
  const identity = useRef(p.brainKey); identity.current = p.brainKey
  const current = useRef(p); current.current = p

  useEffect(() => {
    if (!p.open || !p.brainKey) return
    const ctl = new AbortController(), key = p.brainKey
    setError(null)
    void listMagnets(ctl.signal).then((found) => {
      if (ctl.signal.aborted || identity.current !== key) return
      setRows(found)
      setSelected((old) => found.some((row) => row.id === old) ? old : '')
    }, (e: unknown) => {
      if (!ctl.signal.aborted && identity.current === key) { setRows([]); setError(e instanceof Error ? e.message : String(e)) }
    })
    return () => ctl.abort()
  }, [p.open, p.brainKey, revision])

  useEffect(() => {
    if (!p.open || view !== 'create' || !p.brainKey) return
    const ctl = new AbortController(), key = p.brainKey
    const timer = window.setTimeout(() => {
      setSourceWords('Reading Conversations…')
      void conversationChoices(sourceQuery, null, ctl.signal).then((got) => {
        if (ctl.signal.aborted || identity.current !== key) return
        setChoices(got.rows)
        setSourceWords(got.next ? 'Showing the first 40 matches. Narrow the search to find another.' : `${got.rows.length} ${got.rows.length === 1 ? 'Conversation' : 'Conversations'}.`)
      }, (e: unknown) => { if (!ctl.signal.aborted && identity.current === key) setSourceWords(e instanceof Error ? e.message : String(e)) })
    }, sourceQuery.trim() ? 180 : 0)
    return () => { clearTimeout(timer); ctl.abort() }
  }, [p.open, p.brainKey, view, sourceQuery])

  useLayoutEffect(() => {
    if (p.open) {
      opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null
      requestAnimationFrame(() => input.current?.focus({ preventScroll: true }))
    } else {
      const to = opener.current; opener.current = null
      if (to && document.contains(to)) to.focus({ preventScroll: true })
    }
  }, [p.open])

  useEffect(() => {
    setView('list'); setSelected(''); setName(''); setSource(''); setSourceQuery(''); setCreateWords(''); operation.current = null
  }, [p.brainKey])

  useEffect(() => {
    if (!name.trim() && !creating) return
    const warn = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = '' }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [name, creating])

  if (!p.open) return null
  const shown = listedMagnets(rows ?? [], query, filter)
  const chosen = rows?.find((row) => row.id === selected)
  const leave = () => p.onClose()
  const trap = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      e.preventDefault()
      if (view !== 'list') { setView('list'); requestAnimationFrame(() => input.current?.focus()) } else leave()
      return
    }
    if (e.key !== 'Tab' || !box.current) return
    const stops = [...box.current.querySelectorAll<HTMLElement>('button:not([disabled]), input:not([disabled]), select:not([disabled]), [href]')].filter((el) => el.offsetParent !== null)
    if (!stops.length) return
    const first = stops[0], last = stops[stops.length - 1]
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus() }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus() }
  }
  const back = () => { setView('list'); requestAnimationFrame(() => input.current?.focus({ preventScroll: true })) }
  const changeCreate = (f: () => void) => { operation.current = null; setCreateWords(''); f() }
  const create = async () => {
    if (creating || !p.brainKey || !p.canCreate('home')) return
    const key = p.brainKey
    const op = operation.current ?? (operation.current = `quiet-magnet-${crypto.randomUUID()}`)
    setCreating(true); setCreateWords('Creating the Magnet in this Brain…')
    try {
      const made = await makeMagnet({ key, arrangement: 'home', source, name, op, manual: !p.fixture })
      if (identity.current !== key) return
      setName(''); setSource(''); operation.current = null; setRevision((n) => n + 1)
      current.current.onOpen(made)
    } catch (e) {
      if (identity.current === key) setCreateWords(`${(e as Error).message} Your choices and operation key are kept; retrying unchanged choices uses the same operation.`)
    } finally { if (identity.current === key) setCreating(false) }
  }

  return <div className="q2-brain-veil q2-magnet-veil" onPointerDown={(e) => { if (e.target === e.currentTarget) leave() }}>
    <div ref={box} className="q2-brain-card q2-magnet-management" role="dialog" aria-modal="true" aria-label="Magnet Management" onKeyDown={trap}>
      <div className="q2-cl">
        <header className="q2-cl-head">
          {view !== 'list' && <button type="button" className="q2-magnet-back" aria-label="Back to Magnets" onClick={back}>←</button>}
          <h2>{view === 'detail' ? chosen?.name ?? 'Magnet' : view === 'create' ? 'New Magnet' : 'Magnets'}</h2>
          <span className="q2-brain-tools">
            {view === 'list' && <button type="button" className="q2-brain-more" aria-label="New Magnet" title="New Magnet" onClick={() => setView('create')}>+</button>}
            <button type="button" className="q2-cl-close" aria-label="Close" title="Close" onClick={leave}>×</button>
          </span>
        </header>

        {view === 'list' && <>
          <input ref={input} type="search" className="q2-cl-filter" value={query} placeholder="Find a Magnet" autoComplete="off" spellCheck={false}
            aria-label="Find a Magnet" onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Escape' && query) { e.preventDefault(); e.stopPropagation(); setQuery('') } }} />
          <div className="q2-cl-tabs" role="tablist" aria-label="Which Magnets">
            {TABS.map((tab) => <button key={tab.id} type="button" role="tab" aria-selected={filter === tab.id} tabIndex={filter === tab.id ? 0 : -1} onClick={() => setFilter(tab.id)}>{tab.label}</button>)}
          </div>
          <ul className="q2-brain-rows q2-magnet-rows" role="listbox" aria-label="Magnets">
            {!rows && !error && <li className="q2-cl-note" role="status">Reading Magnets…</li>}
            {error && <li className="q2-cl-note" role="alert">Could not read Magnets: {error}</li>}
            {rows && !shown.length && !error && <li className="q2-cl-note">{query.trim() || filter !== 'all' ? 'Nothing matches.' : 'No Magnets in this Brain yet.'}</li>}
            {shown.map((row) => <li key={row.id}>
              <button type="button" className="q2-brain-row" role="option" aria-selected={selected === row.id} data-magnet={row.id}
                onClick={() => { setSelected(row.id); setView('detail') }}>
                <span className="q2-brain-text"><span className="q2-brain-name">{row.name}</span>
                  <span className={'q2-brain-meta' + (row.reason ? ' q2-brain-off' : '')}>{row.reason ? 'Needs attention · definition unavailable here' : sourceSummary(row.config)}</span>
                </span>
              </button>
            </li>)}
          </ul>
          {rows && <p className="q2-brain-foot"><span>{shown.length} of {rows.length} {rows.length === 1 ? 'Magnet' : 'Magnets'}</span><button type="button" className="q2-link" onClick={() => setRevision((n) => n + 1)}>Refresh</button></p>}
        </>}

        {view === 'detail' && chosen && <div className="q2-magnet-detail">
          {chosen.reason && <p className="q2-magnet-alert" role="alert">{chosen.reason}</p>}
          <dl>
            <div><dt>Identity</dt><dd>{chosen.id}</dd></div>
            <div><dt>Sources</dt><dd>{sourceSummary(chosen.config)}</dd></div>
            <div><dt>Collection</dt><dd>{chosen.config?.collection?.mode ?? 'Not configured'}</dd></div>
            <div><dt>Synthesis</dt><dd>{chosen.config?.synthesis?.mode ?? 'Not configured'}</dd></div>
            <div><dt>Own Conversation</dt><dd>{chosen.config?.conversation ?? 'Not opened yet'}</dd></div>
          </dl>
          {!!chosen.config?.sources?.length && <section><h3>Configured sources</h3><ul>{chosen.config.sources.map((item, i) => <li key={i}>{sourceItemWords(item)}</li>)}</ul></section>}
          <p className="q2-magnet-help">Configuration belongs to this Magnet. This view reports what is saved; editing configuration is not supported by this Quiet management surface yet.</p>
          <div className="q2-magnet-actions"><button type="button" className="q2-magnet-primary" disabled={!openableMagnet(chosen)} onClick={() => { if (openableMagnet(chosen)) p.onOpen(chosen) }}>Open in current workspace</button></div>
        </div>}

        {view === 'create' && <form className="q2-magnet-create" onSubmit={(e) => { e.preventDefault(); void create() }}>
          <p>A Magnet is created in this Brain and placed in Brain Home. Its source is configuration, not its owner or container.</p>
          {!p.canCreate('home') && <p className="q2-magnet-alert">{p.fixture ? 'Independent creation is disabled in this disposable fixture because it permits writes only to its test Conversation arrangement.' : 'Magnet creation is unavailable while this page cannot write to Brain Home.'}</p>}
          <label><span>Name</span><input value={name} maxLength={80} disabled={creating} onChange={(e) => changeCreate(() => setName(e.target.value))} /></label>
          <label><span>Find a source Conversation</span><input type="search" value={sourceQuery} disabled={creating} onChange={(e) => { setSourceQuery(e.target.value); setSource(''); operation.current = null }} /></label>
          <p className="q2-magnet-help" role="status">{sourceWords}</p>
          <div className="q2-magnet-source-list" role="listbox" aria-label="Source Conversation">
            {choices.map((choice) => <button type="button" role="option" aria-selected={source === choice.id} key={choice.id} onClick={() => changeCreate(() => setSource(choice.id))}><strong>{choice.name || choice.id}</strong><small>{choice.id}</small></button>)}
          </div>
          <p className="q2-magnet-help">One Conversation source. Collect manually to retain a bounded batch with provenance, inspect it here, and discuss it in the Magnet’s own Conversation. Scheduled collection, Perspectives and change tracking remain unavailable.</p>
          {createWords && <p className="q2-magnet-help" role="status">{createWords}</p>}
          <div className="q2-magnet-actions"><button type="submit" className="q2-magnet-primary" disabled={creating || !name.trim() || !source || !p.canCreate('home')}>{creating ? 'Creating…' : operation.current ? 'Retry same creation' : 'Create Magnet'}</button></div>
        </form>}
      </div>
    </div>
  </div>
}

function sourceSummary(config: SavedMagnet['config']): string {
  const sources = config?.sources ?? []
  if (!sources.length) return 'No configured source'
  return `${sources.length} configured ${sources.length === 1 ? 'source' : 'sources'} · ${sources.map((source) => source.kind).join(', ')}`
}

function sourceItemWords(source: MagnetConfig['sources'][number]): string {
  if (source.kind === 'conversation') return `Conversation · ${source.conversation}`
  const ref = 'ref' in source && typeof source.ref === 'string' ? ` · ${source.ref}` : ''
  return `${source.kind}${ref}`
}
