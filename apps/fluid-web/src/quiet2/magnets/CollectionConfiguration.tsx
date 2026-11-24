/** The Collection configuration panel, inside the Settings overlay.
 *
 *  Its edits are staged (§5-H5-2): a copy is taken when the panel opens, every
 *  change writes to that copy, and only **Save** commits it, through the
 *  existing reconfigure route. The overlay's **Cancel** discards the staged copy
 *  entirely; **Escape** leaves the overlay and keeps it, so reopening the gear
 *  shows the same unsaved edits. Neither touches the message draft or any
 *  inquiry draft -- those are other slots, in `panelDrafts.ts`.
 *
 *  The source model is the honest one (§5-H5-4): Conversation post capture and
 *  exact held text files are supported and actionable here; every other kind the
 *  Magnet schema names is proposed only and is not offered as a choice. */
import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react'
import type { MagnetConfig, MagnetSource } from '../../fluid/surface/magnet/types'
import { conversationChoices, type ConversationChoice } from './managementApi'
import { collectionChange, collectionIssue, configurationRead, exactFileIssue, holdingArrangement, PROPOSED_REASON, PROPOSED_SOURCES, saveCollection, sourceIdentity, SUPPORTED_REASON, SUPPORTED_SOURCES, supportsManualCollection } from './configuration'
import { discardStagedSettings, panelDrafts, requestSettingsReturn, stageSettings, subscribePanelDrafts, type StagedSettings } from './panelDrafts'
import './configuration.css'

type Choice = { id: string; name: string }
type HeldFile = { path: string; label?: string; text?: boolean; state: string; size?: number }

/** What the Brain has actually saved: the baseline a staged copy is taken from. */
export const committedSettings = (config: MagnetConfig): StagedSettings => ({
  sources: config.sources, types: config.selection.informationTypes ?? ['post', 'file', 'image'],
  after: config.selection.dates?.after ?? '', before: config.selection.dates?.before ?? '', manual: false,
})

export default function CollectionConfiguration(p: { magnet: string; config: MagnetConfig; brainKey: string; canWrite(key: string): boolean; onSaved(config: MagnetConfig): void }) {
  const at = useMemo(() => ({ brainKey: p.brainKey, magnet: p.magnet }), [p.brainKey, p.magnet])
  const drafts = useSyncExternalStore((fn) => subscribePanelDrafts(at, fn), () => panelDrafts(at), () => panelDrafts(at))
  const staged = drafts.settings ?? committedSettings(p.config)
  const edit = (change: Partial<StagedSettings>) => stageSettings(at, { ...staged, ...change })
  const { sources, types, after, before, manual } = staged
  const [query, setQuery] = useState(''), [conversations, setConversations] = useState<ConversationChoice[]>([])
  const [next, setNext] = useState<string | null>(null), [collections, setCollections] = useState<Choice[]>([])
  const [collection, setCollection] = useState(''), [fileQuery, setFileQuery] = useState(''), [files, setFiles] = useState<HeldFile[]>([])
  const [fileNext, setFileNext] = useState<number | null>(null), [fileOffset, setFileOffset] = useState(0)
  const [arrangements, setArrangements] = useState<Choice[]>([{ id: 'home', name: 'Brain Home' }])
  const [arrangement, setArrangement] = useState('home'), [held, setHeld] = useState(false)
  const [message, setMessage] = useState(''), [reading, setReading] = useState(''), [saving, setSaving] = useState(false)
  const [alert, setAlert] = useState('')
  const alerted = useRef<HTMLParagraphElement>(null)
  const attempt = useRef<{ op: string; arrangement: string; change: ReturnType<typeof collectionChange> } | null>(null)
  const current = useRef(p); current.current = p
  const locked = saving || !!attempt.current
  // The staged copy is taken when the panel opens, so Cancel has something
  // definite to discard and Escape has something definite to keep.
  useEffect(() => { if (!panelDrafts(at).settings) stageSettings(at, committedSettings(current.current.config)) }, [at])
  // A refused rule takes focus and stays put; nothing is committed behind it.
  useEffect(() => { if (alert) alerted.current?.focus({ preventScroll: true }) }, [alert])
  useEffect(() => {
    const ctl = new AbortController()
    void Promise.all([configurationRead('/api/sources', ctl.signal), configurationRead('/fluid/api/workspaces', ctl.signal)]).then(([s, w]) => {
      if (ctl.signal.aborted) return
      setCollections((s.collections ?? []).filter((c: any) => c.connector === 'filesystem').map((c: any) => ({ id: c.collection, name: c.name || c.collection })))
      setArrangements([{ id: 'home', name: 'Brain Home' }, ...(w.workspaces ?? []).map((v: any) => ({ id: v.id, name: v.name }))])
    }).catch((e) => { if (!ctl.signal.aborted) setMessage(e.message) })
    return () => ctl.abort()
  }, [p.brainKey, p.magnet])
  useEffect(() => {
    const ctl = new AbortController()
    void conversationChoices(query, null, ctl.signal).then((v) => { if (!ctl.signal.aborted) { setConversations(v.rows); setNext(v.next) } }).catch((e) => { if (!ctl.signal.aborted) setReading(e.message) })
    return () => ctl.abort()
  }, [query, p.brainKey])
  useEffect(() => {
    setHeld(false)
    if (!arrangement) return
    const ctl = new AbortController()
    void holdingArrangement(arrangement, p.magnet, ctl.signal).then(() => { if (!ctl.signal.aborted) { setHeld(true); setMessage('This saved arrangement holds the Magnet.') } }).catch((e) => { if (!ctl.signal.aborted) setMessage(e.message) })
    return () => ctl.abort()
  }, [arrangement, p.magnet, p.brainKey])
  useEffect(() => {
    if (!collection) { setFiles([]); return }
    const ctl = new AbortController(), params = new URLSearchParams({ state: 'present', limit: '40', offset: String(fileOffset) })
    if (fileQuery) params.set('q', fileQuery)
    void configurationRead(`/api/sources/${encodeURIComponent(collection)}/objects?${params}`, ctl.signal).then((v) => {
      if (!ctl.signal.aborted) { setFiles(v.objects ?? []); setFileNext(v.next_offset ?? null) }
    }).catch((e) => { if (!ctl.signal.aborted) setReading(e.message) })
    return () => ctl.abort()
  }, [collection, fileQuery, fileOffset, p.brainKey])
  const name = (s: MagnetSource) => s.kind === 'conversation' ? conversations.find((c) => c.id === s.conversation)?.name || 'Saved Conversation'
    : s.kind === 'file' ? `${collections.find((c) => c.id === s.collection)?.name ?? 'Held collection'} / ${s.path || 'Choose one exact file'}` : `${s.kind} (unavailable)`
  const add = (s: MagnetSource) => {
    if (locked) return
    setAlert('')
    if (sources.length >= 20) { setMessage('The Magnet supports at most 20 sources. Remove one before adding another.'); return }
    if (!sources.some((v) => sourceIdentity(v) === sourceIdentity(s))) edit({ sources: [...sources, s] })
  }
  const save = async () => {
    if (saving || !p.canWrite(arrangement) || !held) return
    const brainKey = p.brainKey, magnet = p.magnet
    // The approved rules first, in order, in their own wording. Nothing is
    // committed and the panel stays open while one of them fails.
    if (!attempt.current) {
      const issue = collectionIssue(staged)
      if (issue) { setAlert(issue); return }
      let change: ReturnType<typeof collectionChange>
      try { change = collectionChange(p.config, sources, types, after, before, manual) }
      catch (e) { setAlert((e as Error).message); return }
      attempt.current = { op: `magnet-config-${crypto.randomUUID()}`, arrangement, change }
    }
    setAlert('')
    try {
      setSaving(true); setMessage('Saving configuration. Collection runs only when you press Collect now.')
      const config = await saveCollection({ brainKey, magnet, ...attempt.current })
      if (current.current.brainKey !== brainKey || current.current.magnet !== magnet) return
      attempt.current = null
      p.onSaved(config)
      setMessage('Configuration saved. Earlier batches and the Magnet Conversation are preserved. Press Collect now to capture the new selection.')
      // Committed: the staged copy is no longer unsaved, and the overlay returns
      // to wherever the gear was pressed from.
      requestSettingsReturn(at)
    } catch (e) {
      if (current.current.brainKey !== brainKey || current.current.magnet !== magnet) return
      if ((e as Error & { refused?: boolean }).refused) attempt.current = null
      setMessage(`${(e as Error).message}${attempt.current ? ' The unchanged save and its operation key are kept; retry it before making further changes.' : ''}`)
    } finally { if (current.current.brainKey === brainKey && current.current.magnet === magnet) setSaving(false) }
  }
  return <section className="q2-magnet-config" aria-label="Collection configuration">
    <h3>Collection configuration</h3>
    <p>{SUPPORTED_REASON}</p>
    {alert && <p className="q2-magnet-alert" role="alert" tabIndex={-1} ref={alerted}>{alert}</p>}
    {drafts.settings && <p className="q2-magnet-muted">Unsaved staged edits. Save commits them; Cancel discards them; leaving with Escape keeps them for when you reopen this panel.</p>}
    <label>Location containing this Magnet<select value={arrangement} disabled={locked} onChange={(e) => setArrangement(e.target.value)}><option value="">Choose a saved location</option>{arrangements.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}{conversations.map((c) => <option key={c.id} value={c.id}>Conversation: {c.name}</option>)}</select></label>
    <p className="q2-magnet-muted">If no saved arrangement holds this Magnet, attach it to an arrangement first. The current workspace is not changed by this editor.</p>
    <ul className="q2-magnet-items">{sources.map((s, i) => <li key={sourceIdentity(s)}><span>{name(s)}</span><button type="button" className="q2-magnet-link" disabled={locked} onClick={() => { setAlert(''); edit({ sources: sources.filter((_, j) => i !== j) }) }}>Remove source</button></li>)}</ul>
    <p role="status" aria-live="polite">{sources.length} of 20 sources chosen. Choose Conversations, exact held text files, or both.</p>
    {!supportsManualCollection(p.config) && <label><input type="checkbox" checked={manual} disabled={locked} onChange={(e) => edit({ manual: e.target.checked })} />Use supported manual collection: one extraction when I press Collect now, manual synthesis, no automatic notifications or agent processing. This replaces the saved collection and processing modes.</label>}
    <details><summary>Add Conversations</summary><label>Find a Conversation<input type="search" value={query} disabled={locked} onChange={(e) => setQuery(e.target.value)} /></label><div className="q2-magnet-config-choices">{conversations.map((c) => <button type="button" key={c.id} disabled={locked || sources.some((s) => s.kind === 'conversation' && s.conversation === c.id)} onClick={() => add({ kind: 'conversation', conversation: c.id })}>Add {c.name}</button>)}</div>{next && <button type="button" className="q2-magnet-link" onClick={() => { const key = p.brainKey; void conversationChoices(query, next, new AbortController().signal).then((v) => { if (current.current.brainKey === key) { setConversations((old) => [...old, ...v.rows]); setNext(v.next) } }).catch((e) => setReading(e.message)) }}>More Conversations</button>}</details>
    <details><summary>Add held text files</summary><label>Acquired filesystem collection<select value={collection} disabled={locked} onChange={(e) => { setCollection(e.target.value); setFileOffset(0) }}><option value="">Choose a held collection</option>{collections.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label><label>Find a held file<input type="search" value={fileQuery} disabled={locked} onChange={(e) => { setFileQuery(e.target.value); setFileOffset(0) }} /></label><div className="q2-magnet-config-choices">{files.map((f) => { const issue = exactFileIssue(collection, f.path) || (f.text !== true ? 'Only held UTF-8 text files are supported.' : null); return <div key={f.path}><button type="button" disabled={locked || !!issue || sources.some((s) => s.kind === 'file' && s.collection === collection && s.path === f.path)} title={issue ?? undefined} onClick={() => add({ kind: 'file', collection, path: f.path })}>{f.path}</button>{issue && <small>{issue}</small>}{typeof f.size === 'number' && f.size > 65536 && <small>Only the first 64 KiB will be captured, ending on a UTF-8 character boundary.</small>}</div> })}</div><div>{fileOffset > 0 && <button type="button" className="q2-magnet-link" onClick={() => setFileOffset(Math.max(0, fileOffset - 40))}>Previous files</button>}{fileNext !== null && <button type="button" className="q2-magnet-link" onClick={() => setFileOffset(fileNext)}>More files</button>}</div></details>
    <details><summary>Conversation filters</summary><p>Types and dates apply to Conversation content. Held files are selected by exact path only.</p><div className="q2-magnet-config-types">{['post', 'file', 'image', 'attachment'].map((t) => <label key={t}><input type="checkbox" checked={types.includes(t)} disabled={locked} onChange={(e) => { setAlert(''); edit({ types: e.target.checked ? [...types, t] : types.filter((v) => v !== t) }) }} />{t}</label>)}</div><label>After (date or ISO time)<input type="text" placeholder="2026-01-01 or 2026-01-01T12:00:00Z" value={after} disabled={locked} onChange={(e) => { setAlert(''); edit({ after: e.target.value }) }} /></label><label>Before (date or ISO time)<input type="text" placeholder="2026-01-31 or 2026-01-31T12:00:00Z" value={before} disabled={locked} onChange={(e) => { setAlert(''); edit({ before: e.target.value }) }} /></label></details>
    <details><summary>Available sources and collection modes</summary>
      <h4>Supported here, and actionable</h4>
      <ul className="q2-magnet-items">{SUPPORTED_SOURCES.map((s) => <li key={s.kind}>{s.words}</li>)}</ul>
      <h4>Proposed only, and not offered as a choice</h4>
      <ul className="q2-magnet-items">{PROPOSED_SOURCES.map((s) => <li key={s.words}>{s.words}</li>)}</ul>
      <p>{PROPOSED_REASON}</p>
      <p>Individual post selection, schedules and automatic collection are also unsupported.</p>
      <p>Saved collection: {p.config.collection.mode}; synthesis: {p.config.synthesis.mode}; activation: {p.config.activation?.mode ?? 'not configured'}. Saved modes are kept unless you explicitly choose supported manual collection. Relevance and semantic filters are not applied.</p>
      {Object.entries(p.config.selection).filter(([k]) => !['informationTypes', 'dates'].includes(k)).map(([k, v]) => <p key={k}>{k}: {JSON.stringify(v)} (not applied)</p>)}
    </details>
    {reading && <p role="status">{reading}</p>}{message && <p role="status">{message}</p>}
    <div className="q2-magnet-settings-actions">
      <button type="button" className="q2-magnet-primary" disabled={saving || !p.canWrite(arrangement) || !held} onClick={() => void save()}>{saving ? 'Saving…' : attempt.current ? 'Retry unchanged save' : 'Save collection configuration'}</button>
      <button type="button" disabled={saving || !drafts.settings} onClick={() => { setAlert(''); setMessage('Staged configuration edits were discarded. Nothing was sent.'); discardStagedSettings(at) }}>Cancel configuration edits</button>
    </div>
  </section>
}
