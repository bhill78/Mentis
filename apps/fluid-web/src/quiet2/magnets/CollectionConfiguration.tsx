/** The configuration panel, inside the Settings overlay.
 *
 *  It opens on what the owner came to change (request §4): the Magnet's name,
 *  then its sources, then what to collect from a Conversation. Everything else
 *  -- which saved location the save is addressed through, the saved collection
 *  modes, the full source model -- is disclosed, not stacked in front.
 *
 *  Its edits are staged (§5-H5-2): a copy is taken when the panel opens, every
 *  change writes to that copy, and only **Save** commits it, through the
 *  existing reconfigure route. The overlay's **Cancel** discards the staged copy
 *  entirely; **Escape** leaves the overlay and keeps it, so reopening the gear
 *  shows the same unsaved edits. Neither touches the message draft or any
 *  inquiry draft -- those are other slots, in `panelDrafts.ts`.
 *
 *  The name is the Magnet's own, kept in its definition (`identity.name`), so it
 *  does not depend on which arrangement happens to draw it. It is committed by
 *  the same Save, in the same reconfigure.
 *
 *  The source model is the honest one (§5-H5-4): Conversation post capture and
 *  exact held text files are supported and actionable here; every other kind the
 *  Magnet schema names is proposed only and is not offered as a choice. NO
 *  SOURCE AT ALL is also an answer: a Magnet may be saved with none, the last
 *  one may be removed, and nothing is read in their place. */
import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react'
import type { MagnetConfig, MagnetSource } from '../../fluid/surface/magnet/types'
import { conversationChoices, type ConversationChoice } from './managementApi'
import { collectionChange, collectionIssue, configurationRead, exactFileIssue, findConfigurationLocation, identityChange, magnetName, MAGNET_NAME_MOST, nameIssue, NO_SOURCE_TO_COLLECT, PROPOSED_REASON, PROPOSED_SOURCES, savedPlace, saveCollection, sourceIdentity, SUPPORTED_REASON, SUPPORTED_SOURCES, supportsManualCollection, type ConfigurationChange } from './configuration'
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
  const committedName = magnetName(p.config, '')
  const [name, setName] = useState(committedName)
  const [query, setQuery] = useState(''), [conversations, setConversations] = useState<ConversationChoice[]>([])
  const [next, setNext] = useState<string | null>(null), [collections, setCollections] = useState<Choice[]>([])
  const [collection, setCollection] = useState(''), [fileQuery, setFileQuery] = useState(''), [files, setFiles] = useState<HeldFile[]>([])
  const [fileNext, setFileNext] = useState<number | null>(null), [fileOffset, setFileOffset] = useState(0)
  const [arrangements, setArrangements] = useState<Choice[]>([{ id: 'home', name: 'Brain Home' }])
  const [arrangement, setArrangement] = useState(''), [sendable, setSendable] = useState(false), [holds, setHolds] = useState(false)
  const [locations, setLocations] = useState(false)
  const [message, setMessage] = useState(''), [reading, setReading] = useState(''), [saving, setSaving] = useState(false)
  const [alert, setAlert] = useState('')
  const alerted = useRef<HTMLParagraphElement>(null)
  const attempt = useRef<{ op: string; arrangement: string; change: ConfigurationChange } | null>(null)
  const current = useRef(p); current.current = p
  const locked = saving || !!attempt.current
  // The staged copy is taken when the panel opens, so Cancel has something
  // definite to discard and Escape has something definite to keep.
  useEffect(() => { if (!panelDrafts(at).settings) stageSettings(at, committedSettings(current.current.config)) }, [at])
  // The name field follows a committed rename (its own or another session's),
  // and otherwise keeps what is being typed.
  useEffect(() => { setName(committedName) }, [at, committedName])
  // A refused rule takes focus and stays put; nothing is committed behind it.
  useEffect(() => { if (alert) alerted.current?.focus({ preventScroll: true }) }, [alert])
  useEffect(() => {
    const ctl = new AbortController()
    void Promise.all([configurationRead('/api/sources', ctl.signal), configurationRead('/fluid/api/workspaces', ctl.signal)]).then(([s, w]) => {
      if (ctl.signal.aborted) return
      setCollections((s.collections ?? []).filter((c: any) => c.connector === 'filesystem').map((c: any) => ({ id: c.collection, name: c.name || c.collection })))
      setArrangements([{ id: 'home', name: 'Brain Home' }, ...(w.workspaces ?? []).map((v: any) => ({ id: v.id, name: v.name }))])
      setLocations(true)
    }).catch((e) => { if (!ctl.signal.aborted) { setMessage(e.message); setLocations(true) } })
    return () => ctl.abort()
  }, [p.brainKey, p.magnet])
  // WHICH SAVED LOCATION THE SAVE IS ADDRESSED THROUGH IS FOUND, NOT ASKED.
  // The definition belongs to no arrangement and its name and configuration do
  // not depend on where it is displayed (request §4); only the door is addressed
  // through a saved location, which keeps the operation key. Brain Home first,
  // then each saved workspace, read-only: one that holds this Magnet is
  // preferred, and otherwise any saved location carries the save and attaches
  // nothing. A Magnet nothing holds is configured and renamed just the same.
  useEffect(() => {
    if (arrangement || !locations) return
    const ctl = new AbortController()
    void findConfigurationLocation(p.magnet, arrangements.map((a) => a.id), ctl.signal).then((found) => {
      if (ctl.signal.aborted) return
      if (found) { setArrangement(found.arrangement); setSendable(true); setHolds(found.holds); setMessage('') }
      else setMessage('There is no saved location to address this configuration through yet. Save a workspace or Brain Home once, then reopen Settings; the Magnet itself does not have to be placed in it.')
    })
    return () => ctl.abort()
  }, [p.magnet, p.brainKey, arrangement, arrangements, locations])
  useEffect(() => {
    const ctl = new AbortController()
    void conversationChoices(query, null, ctl.signal).then((v) => { if (!ctl.signal.aborted) { setConversations(v.rows); setNext(v.next) } }).catch((e) => { if (!ctl.signal.aborted) setReading(e.message) })
    return () => ctl.abort()
  }, [query, p.brainKey])
  // A location chosen by hand is checked the same way the found one was.
  useEffect(() => {
    if (!arrangement) return
    const ctl = new AbortController()
    void savedPlace(arrangement, p.magnet, ctl.signal).then((place) => { if (!ctl.signal.aborted) { setSendable(true); setHolds(place.holds) } })
      .catch((e) => { if (!ctl.signal.aborted) { setSendable(false); setHolds(false); setMessage(e.message) } })
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
  const sourceWords = (s: MagnetSource) => s.kind === 'conversation' ? conversations.find((c) => c.id === s.conversation)?.name || 'Saved Conversation'
    : s.kind === 'file' ? `${collections.find((c) => c.id === s.collection)?.name ?? 'Held collection'} / ${s.path || 'Choose one exact file'}` : `${s.kind} (unavailable)`
  const add = (s: MagnetSource) => {
    if (locked) return
    setAlert('')
    if (sources.length >= 20) { setMessage('The Magnet supports at most 20 sources. Remove one before adding another.'); return }
    if (!sources.some((v) => sourceIdentity(v) === sourceIdentity(s))) edit({ sources: [...sources, s] })
  }
  const renaming = name.trim() !== committedName
  const save = async () => {
    if (saving || !arrangement || !p.canWrite(arrangement) || !sendable) return
    const brainKey = p.brainKey, magnet = p.magnet
    // The approved rules first, in order, in their own wording. Nothing is
    // committed and the panel stays open while one of them fails.
    if (!attempt.current) {
      if (renaming) { const issue = nameIssue(name); if (issue) { setAlert(issue); return } }
      const issue = collectionIssue(staged)
      if (issue) { setAlert(issue); return }
      let change: ConfigurationChange
      try { change = collectionChange(p.config, sources, types, after, before, manual) }
      catch (e) { setAlert((e as Error).message); return }
      if (renaming) change = { ...change, ...identityChange(name) }
      attempt.current = { op: `magnet-config-${crypto.randomUUID()}`, arrangement, change }
    }
    setAlert('')
    try {
      setSaving(true); setMessage('Saving configuration. Collection runs only when you press Collect now.')
      const config = await saveCollection({ brainKey, magnet, ...attempt.current })
      if (current.current.brainKey !== brainKey || current.current.magnet !== magnet) return
      attempt.current = null
      p.onSaved(config)
      setMessage('Saved. The collection history and the Magnet Conversation are kept. Press Collect now to capture the new selection.')
      // Committed: the staged copy is no longer unsaved, and the overlay returns
      // to wherever the gear was pressed from.
      requestSettingsReturn(at)
    } catch (e) {
      if (current.current.brainKey !== brainKey || current.current.magnet !== magnet) return
      if ((e as Error & { refused?: boolean }).refused) attempt.current = null
      setMessage(`${(e as Error).message}${attempt.current ? ' The unchanged save and its operation key are kept; retry it before making further changes.' : ''}`)
    } finally { if (current.current.brainKey === brainKey && current.current.magnet === magnet) setSaving(false) }
  }
  return <section className="q2-magnet-config" aria-label="Magnet configuration">
    {alert && <p className="q2-magnet-alert" role="alert" tabIndex={-1} ref={alerted}>{alert}</p>}

    <label className="q2-magnet-config-name">Name
      <input value={name} maxLength={MAGNET_NAME_MOST} disabled={locked} aria-describedby="q2-magnet-name-note"
        onChange={(e) => { setAlert(''); setName(e.target.value) }} />
    </label>
    <p id="q2-magnet-name-note" className="q2-magnet-muted">This name is the Magnet’s own and does not change where it is shown.{committedName ? '' : ' It has none of its own yet, so it is currently named after where it is shown.'}</p>

    <h4>Sources</h4>
    <ul className="q2-magnet-items">{sources.map((s, i) => <li key={sourceIdentity(s)}><span>{sourceWords(s)}</span><button type="button" className="q2-magnet-link" disabled={locked} onClick={() => { setAlert(''); edit({ sources: sources.filter((_, j) => i !== j) }) }}>Remove</button></li>)}</ul>
    <p role="status" aria-live="polite">{sources.length ? `${sources.length} of 20 sources chosen. Choose Conversations, files, or both.` : NO_SOURCE_TO_COLLECT}</p>
    <details><summary>Add Conversations</summary><label>Find a Conversation<input type="search" value={query} disabled={locked} onChange={(e) => setQuery(e.target.value)} /></label><div className="q2-magnet-config-choices">{conversations.map((c) => <button type="button" key={c.id} disabled={locked || sources.some((s) => s.kind === 'conversation' && s.conversation === c.id)} onClick={() => add({ kind: 'conversation', conversation: c.id })}>Add {c.name}</button>)}</div>{next && <button type="button" className="q2-magnet-link" onClick={() => { const key = p.brainKey; void conversationChoices(query, next, new AbortController().signal).then((v) => { if (current.current.brainKey === key) { setConversations((old) => [...old, ...v.rows]); setNext(v.next) } }).catch((e) => setReading(e.message)) }}>More Conversations</button>}</details>
    <details><summary>Add files</summary><label>Where the files are<select value={collection} disabled={locked} onChange={(e) => { setCollection(e.target.value); setFileOffset(0) }}><option value="">Choose a file collection</option>{collections.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label><label>Find a file<input type="search" value={fileQuery} disabled={locked} onChange={(e) => { setFileQuery(e.target.value); setFileOffset(0) }} /></label><div className="q2-magnet-config-choices">{files.map((f) => { const issue = exactFileIssue(collection, f.path) || (f.text !== true ? 'Only plain text files are supported.' : null); return <div key={f.path}><button type="button" disabled={locked || !!issue || sources.some((s) => s.kind === 'file' && s.collection === collection && s.path === f.path)} title={issue ?? undefined} onClick={() => add({ kind: 'file', collection, path: f.path })}>{f.path}</button>{issue && <small>{issue}</small>}{typeof f.size === 'number' && f.size > 65536 && <small>Only the first 64 KiB will be captured, ending on a UTF-8 character boundary.</small>}</div> })}</div><div>{fileOffset > 0 && <button type="button" className="q2-magnet-link" onClick={() => setFileOffset(Math.max(0, fileOffset - 40))}>Previous files</button>}{fileNext !== null && <button type="button" className="q2-magnet-link" onClick={() => setFileOffset(fileNext)}>More files</button>}</div></details>

    <h4>What to collect</h4>
    <details><summary>Supported collection</summary><p className="q2-magnet-muted">{SUPPORTED_REASON}</p></details>
    <div className="q2-magnet-config-types">{['post', 'file', 'image', 'attachment'].map((t) => <label key={t}><input type="checkbox" checked={types.includes(t)} disabled={locked} onChange={(e) => { setAlert(''); edit({ types: e.target.checked ? [...types, t] : types.filter((v) => v !== t) }) }} />{t}</label>)}</div>
    <details><summary>Date limits</summary><p>Types and dates apply to Conversation content. Files are chosen one by one, by their exact path.</p><label>After (date or ISO time)<input type="text" placeholder="2026-01-01 or 2026-01-01T12:00:00Z" value={after} disabled={locked} onChange={(e) => { setAlert(''); edit({ after: e.target.value }) }} /></label><label>Before (date or ISO time)<input type="text" placeholder="2026-01-31 or 2026-01-31T12:00:00Z" value={before} disabled={locked} onChange={(e) => { setAlert(''); edit({ before: e.target.value }) }} /></label></details>

    {!supportsManualCollection(p.config) && <label><input type="checkbox" checked={manual} disabled={locked} onChange={(e) => edit({ manual: e.target.checked })} />Use supported manual collection: one extraction when I press Collect now, manual synthesis, no automatic notifications or agent processing. This replaces the saved collection and processing modes.</label>}

    <details><summary>Collection limits</summary>
      <h5>Supported here, and actionable</h5>
      <ul className="q2-magnet-items">{SUPPORTED_SOURCES.map((s) => <li key={s.kind}>{s.words}</li>)}</ul>
      <h5>Proposed only, and not offered as a choice</h5>
      <ul className="q2-magnet-items">{PROPOSED_SOURCES.map((s) => <li key={s.words}>{s.words}</li>)}</ul>
      <p>{PROPOSED_REASON}</p>
      <p>Individual post selection, schedules and automatic collection are unsupported.</p>
      <p>Saved modes are kept unless you choose manual collection. Relevance and semantic filters are not applied.</p>
    {Object.entries(p.config.selection).filter(([k]) => !['informationTypes', 'dates'].includes(k)).map(([k, v]) => <p key={k}>{k}: {JSON.stringify(v)} (not applied)</p>)}
    </details>
    <details><summary>Where this configuration is saved through</summary>
      <p className="q2-magnet-muted">{arrangement ? `Saving through ${arrangements.find((a) => a.id === arrangement)?.name ?? arrangement}.` : locations ? 'No saved location found.' : 'Looking for a saved location…'}{arrangement && !holds ? ' This location does not hold the Magnet; saving will not add it there.' : ''}</p>
      <label>Saved location<select value={arrangement} disabled={locked} onChange={(e) => { setMessage(''); setArrangement(e.target.value) }}><option value="">Choose a saved location</option>{arrangements.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}{conversations.map((c) => <option key={c.id} value={c.id}>Conversation: {c.name}</option>)}</select></label>
    </details>

    {drafts.settings && <p className="q2-magnet-muted">Unsaved changes. Save or cancel.</p>}
    {reading && <p role="status">{reading}</p>}{message && <p role="status">{message}</p>}
    <div className="q2-magnet-settings-actions">
      <button type="button" className="q2-magnet-primary" disabled={saving || !arrangement || !p.canWrite(arrangement) || !sendable} onClick={() => void save()}>{saving ? 'Saving…' : attempt.current ? 'Retry unchanged save' : 'Save collection configuration'}</button>
      <button type="button" disabled={saving || (!drafts.settings && !renaming)} onClick={() => { setAlert(''); setName(committedName); setMessage('Staged configuration edits were discarded. Nothing was sent.'); discardStagedSettings(at) }}>Cancel configuration edits</button>
    </div>
  </section>
}
