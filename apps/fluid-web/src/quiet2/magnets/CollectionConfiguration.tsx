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
import type { MagnetResource } from './contract'
import { conversationChoices, type ConversationChoice } from './managementApi'
import { collectionChange, collectionIssue, configurationRead, exactFileIssue, findConfigurationLocation, identityChange, magnetName, MAGNET_NAME_MOST, nameIssue, NO_SOURCE_TO_COLLECT, PROPOSED_REASON, PROPOSED_SOURCES, savedPlace, saveCollection, sourceIdentity, SUPPORTED_REASON, SUPPORTED_SOURCES, supportsManualCollection, type ConfigurationChange } from './configuration'
import { discardStagedSettings, panelDrafts, requestSettingsReturn, stageSettings, subscribePanelDrafts, type StagedSettings } from './panelDrafts'
import './design.css'
import './configuration.css'
import './collection.css'

type Choice = { id: string; name: string }
type HeldFile = { path: string; label?: string; text?: boolean; state: string; size?: number }

/** WHAT IS BEING COLLECTED, AS A SENTENCE (approved mockup round 3,
 *  03-sources.png: "Posts, files, images and attachments"). The selection
 *  itself is unchanged -- this only says it in the reader's words instead of
 *  presenting the checkbox form that sets it. */
export function whatIsCollected(types: readonly string[], after: string, before: string): string {
  const words = types.map((t) => `${t}s`)
  const listed = !words.length ? 'Nothing selected'
    : words.length === 1 ? words[0]
      : `${words.slice(0, -1).join(', ')} and ${words[words.length - 1]}`
  const said = listed === 'Nothing selected' ? listed : listed.charAt(0).toUpperCase() + listed.slice(1)
  return after || before ? `${said} · ${after || 'any start'} to ${before || 'any end'}` : said
}

/** The moment a collection was last captured, the way the approved rows say a
 *  moment: "today, 10:42 AM" or "Nov 18" -- never the raw recorded number. */
export function lastCollected(at?: number | null): string {
  if (typeof at !== 'number' || !Number.isFinite(at)) return 'Not collected yet'
  const d = new Date(at * 1000)
  return d.toDateString() === new Date().toDateString()
    ? `Last collected today, ${d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}`
    : `Last collected ${d.toLocaleDateString([], { month: 'short', day: 'numeric' })}`
}

/** What the Brain has actually saved: the baseline a staged copy is taken from. */
export const committedSettings = (config: MagnetConfig): StagedSettings => ({
  sources: config.sources, types: config.selection.informationTypes ?? ['post', 'file', 'image'],
  after: config.selection.dates?.after ?? '', before: config.selection.dates?.before ?? '', manual: false,
})

/** WHETHER THE STAGED COPY DIFFERS FROM WHAT IS SAVED.
 *
 *  A staged copy is taken as soon as the panel opens, so that Cancel has
 *  something definite to discard; its existence is therefore not evidence that
 *  anything was edited. Embedded in the Collection place (the approved mockup's
 *  own Sources view) the panel is somewhere a reader simply looks, and
 *  announcing "Unsaved changes" to someone who has changed nothing is exactly
 *  the administrative noise the redesign removes (owner request
 *  ent-1e82a8786c37). So the unsaved note and Cancel follow the comparison,
 *  not the slot. */
export const settingsEdited = (staged: StagedSettings, config: MagnetConfig): boolean => {
  const saved = committedSettings(config)
  const keys = (v: StagedSettings) => v.sources.map(sourceIdentity).join('\u0000')
  return keys(staged) !== keys(saved) || staged.types.join('\u0000') !== saved.types.join('\u0000')
    || staged.after !== saved.after || staged.before !== saved.before || staged.manual !== saved.manual
}

export default function CollectionConfiguration(p: { magnet: string; config: MagnetConfig; brainKey: string; canWrite(key: string): boolean; onSaved(config: MagnetConfig): void
  /** Embedded directly in the Collection place (approved mockup round 3,
   *  03-sources.png), beside `EvidenceViews`'s own toggle, rather than in the
   *  Settings overlay this panel was built for. The identity (name) facet stays
   *  Settings' own -- the Collection place is sources and collection behaviour
   *  only, never a second place to rename the Magnet -- and a save here commits
   *  and clears the staged copy without asking an overlay to return, because
   *  there is no overlay to return from. */
  inCollection?: boolean
  /** The Magnet this configures, supplied only by the Collection place: the
   *  approved Sources surface offers "Collect now" on its own "Collect
   *  manually" row (plan seam 3), and that is `resource.collect()` exactly as
   *  the header's button was. Settings' own copy has no such row. */
  resource?: MagnetResource
  /** Back to the collected items, the counterpart link of the approved
   *  heading row. Collection supplies it; Settings has nothing to go back to. */
  onBrowse?(): void }) {
  const at = useMemo(() => ({ brainKey: p.brainKey, magnet: p.magnet }), [p.brainKey, p.magnet])
  const drafts = useSyncExternalStore((fn) => subscribePanelDrafts(at, fn), () => panelDrafts(at), () => panelDrafts(at))
  const staged = drafts.settings ?? committedSettings(p.config)
  const edited = settingsEdited(staged, p.config)
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
  /** Which source kind is being added, if any. Empty is the resting state: the
   *  two supported kinds are offered and neither one's controls are present. */
  const [adding, setAdding] = useState<'' | 'conversation' | 'file'>('')
  const [message, setMessage] = useState(''), [reading, setReading] = useState(''), [saving, setSaving] = useState(false)
  const [alert, setAlert] = useState('')
  /** The approved Sources surface says each thing once and opens its editors
   *  in place (03-sources.png): `＋ Add source`, `Change` beside what is being
   *  collected, and `Limits and dates ▾`. Nothing is a standing form. */
  const [addOpen, setAddOpen] = useState(false), [changing, setChanging] = useState(false), [limits, setLimits] = useState(false)
  /** Whether a save has actually been attempted here. The found-location note
   *  is feedback about a save, not something to say to a reader who is only
   *  looking at where this Magnet collects from. */
  const [announce, setAnnounce] = useState(false)
  const live = useSyncExternalStore(
    (fn) => p.resource?.subscribe(fn) ?? (() => {}),
    () => p.resource?.snapshot(),
    () => p.resource?.snapshot())
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
  // THE CLEAN ROW (approved mockup round 3, 03-sources.png): a title a reader
  // recognises, and what kind it is underneath -- never the source's raw
  // identity (a Conversation entry id, a collection key) on the row itself.
  const sourceTitle = (s: MagnetSource) => s.kind === 'conversation' ? conversations.find((c) => c.id === s.conversation)?.name || 'Saved Conversation'
    : s.kind === 'file' ? s.path || 'Choose one exact file' : `${s.kind} (unavailable)`
  const sourceSubtitle = (s: MagnetSource) => s.kind === 'conversation' ? 'Conversation · posts and attachments'
    : s.kind === 'file' ? `Held file · ${collections.find((c) => c.id === s.collection)?.name ?? 'Held collection'}` : 'Unavailable in this build'
  const add = (s: MagnetSource) => {
    if (locked) return
    setAlert('')
    if (sources.length >= 20) { setMessage('The Magnet supports at most 20 sources. Remove one before adding another.'); return }
    if (!sources.some((v) => sourceIdentity(v) === sourceIdentity(s))) edit({ sources: [...sources, s] })
  }
  const renaming = !p.inCollection && name.trim() !== committedName
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
    setAlert(''); setAnnounce(true)
    try {
      setSaving(true); setMessage('Saving configuration. Collection runs only when you press Collect now.')
      const config = await saveCollection({ brainKey, magnet, ...attempt.current })
      if (current.current.brainKey !== brainKey || current.current.magnet !== magnet) return
      attempt.current = null
      p.onSaved(config)
      setMessage('Saved. The collection history and the Magnet Conversation are kept. Press Collect now to capture the new selection.')
      // Committed: the staged copy is no longer unsaved. Settings' own copy
      // asks its overlay to return to wherever the gear was pressed from;
      // embedded in Collection there is no overlay to return to, so the
      // staged copy is simply cleared.
      if (p.inCollection) discardStagedSettings(at); else requestSettingsReturn(at)
    } catch (e) {
      if (current.current.brainKey !== brainKey || current.current.magnet !== magnet) return
      if ((e as Error & { refused?: boolean }).refused) attempt.current = null
      setMessage(`${(e as Error).message}${attempt.current ? ' The unchanged save and its operation key are kept; retry it before making further changes.' : ''}`)
    } finally { if (current.current.brainKey === brainKey && current.current.magnet === magnet) setSaving(false) }
  }
  /* THE TWO SUPPORTED KINDS' CONTROLS, defined once and drawn wherever adding
     is offered: Settings' own progressive add, and the approved Sources
     surface's `＋ Add source` editor. The same `add()` and the same staged
     copy -- only where they are drawn differs. */
  const conversationPicker = <div className="q2-magnet-kind-panel"><label>Find a Conversation<input type="search" value={query} disabled={locked} onChange={(e) => setQuery(e.target.value)} /></label><div className="q2-magnet-config-choices">{conversations.map((c) => <button type="button" key={c.id} disabled={locked || sources.some((s) => s.kind === 'conversation' && s.conversation === c.id)} onClick={() => add({ kind: 'conversation', conversation: c.id })}>Add {c.name}</button>)}</div>{next && <button type="button" className="q2-magnet-link" onClick={() => { const key = p.brainKey; void conversationChoices(query, next, new AbortController().signal).then((v) => { if (current.current.brainKey === key) { setConversations((old) => [...old, ...v.rows]); setNext(v.next) } }).catch((e) => setReading(e.message)) }}>More Conversations</button>}<button type="button" className="q2-magnet-link" onClick={() => setAdding('')}>Done adding Conversations</button></div>
  const filePicker = <div className="q2-magnet-kind-panel"><label>Where the files are<select value={collection} disabled={locked} onChange={(e) => { setCollection(e.target.value); setFileOffset(0) }}><option value="">Choose a file collection</option>{collections.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label><label>Find a file<input type="search" value={fileQuery} disabled={locked} onChange={(e) => { setFileQuery(e.target.value); setFileOffset(0) }} /></label><div className="q2-magnet-config-choices">{files.map((f) => { const issue = exactFileIssue(collection, f.path) || (f.text !== true ? 'Only plain text files are supported.' : null); return <div key={f.path}><button type="button" disabled={locked || !!issue || sources.some((s) => s.kind === 'file' && s.collection === collection && s.path === f.path)} title={issue ?? undefined} onClick={() => add({ kind: 'file', collection, path: f.path })}>{f.path}</button>{issue && <small>{issue}</small>}{typeof f.size === 'number' && f.size > 65536 && <small>Only the first 64 KiB will be captured, ending on a UTF-8 character boundary.</small>}</div> })}</div><div>{fileOffset > 0 && <button type="button" className="q2-magnet-link" onClick={() => setFileOffset(Math.max(0, fileOffset - 40))}>Previous files</button>}{fileNext !== null && <button type="button" className="q2-magnet-link" onClick={() => setFileOffset(fileNext)}>More files</button>}</div><button type="button" className="q2-magnet-link" onClick={() => setAdding('')}>Done adding files</button></div>

  if (p.inCollection) {
    /* COLLECTION -> SOURCES, THE APPROVED SURFACE (round 3, 03-sources.png).
     *
     * The order is the mockup's and nothing else stands on it: the heading
     * block with its counterpart link, one sentence, the configured sources
     * with their own Remove, `＋ Add source`, then what to collect and
     * collecting manually, each one line with one control at the far edge,
     * and `Limits and dates ▾` as the single way to the rest.
     *
     * NOTHING ABOUT THE SAVE CHANGED. The staged copy, `collectionIssue`,
     * `collectionChange` and `saveCollection` are the ones Settings uses, and
     * the commit is gated by exactly the `canWrite` handed in -- the affordance
     * is never offered for an arrangement that gate refuses, and the server
     * authorises again regardless. What moved is where the editors are: behind
     * `Change`, behind `＋ Add source`, behind `Limits and dates ▾`, and the
     * commit appears only once something is actually unsaved rather than
     * standing on the surface as a form. */
    const mayCommit = !saving && !!arrangement && p.canWrite(arrangement) && sendable
    const collectable = supportsManualCollection(p.config)
    const collecting = !!live?.collecting
    const mayCollect = p.canWrite('home') && collectable && !collecting && !!p.resource?.collect
    return <section className="q2-magnet-config q2-magnet-sources" aria-label="Sources">
      <div className="mgd-row mgd-spread q2-magnet-place-head">
        <div className="mgd-grow">
          <div className="mgd-eyebrow">Collection</div>
          <h2 id="view-title" className="mgd-h2" tabIndex={-1}>Sources</h2>
        </div>
        {p.onBrowse && <button type="button" className="mgd-link mgd-small q2-magnet-place-link" onClick={p.onBrowse}>Collected items →</button>}
      </div>
      <p className="mgd-p mgd-muted">Choose where to look. Collect when you’re ready.</p>
      {alert && <p className="q2-magnet-alert" role="alert" tabIndex={-1} ref={alerted}>{alert}</p>}

      {sources.map((s, i) => <div className="mgd-row mgd-spread mgd-source" key={sourceIdentity(s)}>
        <div className="mgd-grow">
          <b>{sourceTitle(s)}</b>
          <div className="mgd-subtle">{sourceSubtitle(s)}</div>
        </div>
        <button type="button" className="mgd-link mgd-small" disabled={locked}
          onClick={() => { setAlert(''); edit({ sources: sources.filter((_, j) => i !== j) }) }}>Remove</button>
      </div>)}
      {!sources.length && <p className="mgd-subtle" role="status" aria-live="polite">{NO_SOURCE_TO_COLLECT}</p>}
      <div className="mgd-source">
        <button type="button" className="mgd-button mgd-secondary" aria-expanded={addOpen} disabled={locked}
          onClick={() => { setAlert(''); setAddOpen(!addOpen); if (addOpen) setAdding('') }}>＋ Add source</button>
      </div>
      {addOpen && <div className="q2-magnet-editor">
        <div className="mgd-row">
          <button type="button" className={`mgd-pill${adding === 'conversation' ? ' mgd-active' : ''}`} aria-pressed={adding === 'conversation'}
            disabled={locked} onClick={() => { setAlert(''); setAdding(adding === 'conversation' ? '' : 'conversation') }}>Conversations</button>
          <button type="button" className={`mgd-pill${adding === 'file' ? ' mgd-active' : ''}`} aria-pressed={adding === 'file'}
            disabled={locked} onClick={() => { setAlert(''); setAdding(adding === 'file' ? '' : 'file') }}>Files</button>
        </div>
        {adding === 'conversation' && conversationPicker}
        {adding === 'file' && filePicker}
      </div>}

      <div className="mgd-divider" />
      <div className="mgd-row mgd-spread">
        <div className="mgd-grow">
          <b>What to collect</b>
          <div className="mgd-subtle">{whatIsCollected(types, after, before)}</div>
        </div>
        <button type="button" className="mgd-link mgd-small" aria-expanded={changing} disabled={locked}
          onClick={() => { setAlert(''); setChanging(!changing) }}>Change</button>
      </div>
      {changing && <div className="q2-magnet-editor q2-magnet-config-types">
        {['post', 'file', 'image', 'attachment'].map((t) => <label key={t}>
          <input type="checkbox" checked={types.includes(t)} disabled={locked}
            onChange={(e) => { setAlert(''); edit({ types: e.target.checked ? [...types, t] : types.filter((v) => v !== t) }) }} />{t}
        </label>)}
      </div>}

      <div className="mgd-divider" />
      <div className="mgd-row mgd-spread">
        <div className="mgd-grow">
          <b>Collect manually</b>
          <div className="mgd-subtle">{collectable ? lastCollected(live?.activation?.at) : 'Manual collection is not configured'}</div>
        </div>
        <button type="button" className="mgd-button" disabled={!mayCollect}
          onClick={() => void p.resource?.collect?.()}>{collecting ? 'Collecting…' : 'Collect now'}</button>
      </div>

      {/* The commit, where an edit actually leaves something unsaved -- never a
          standing form. Same path, same request shape, same gate. */}
      {edited && <div className="mgd-row mgd-spread q2-magnet-commit">
        <span className="mgd-subtle">Unsaved changes</span>
        <span className="mgd-row">
          <button type="button" className="mgd-link mgd-small" disabled={saving}
            onClick={() => { setAlert(''); setMessage('Staged configuration edits were discarded. Nothing was sent.'); setAnnounce(true); discardStagedSettings(at) }}>Discard</button>
          <button type="button" className="mgd-button" aria-label="Save collection configuration" disabled={!mayCommit}
            onClick={() => void save()}>{saving ? 'Saving…' : attempt.current ? 'Retry' : 'Save'}</button>
        </span>
      </div>}
      {/* A failed read of the choices is feedback about adding a source, and is
          said where adding happens -- not on a surface somebody is only
          looking at. The same for the saved location a save goes through. */}
      {reading && addOpen && <p className="mgd-subtle" role="status">{reading}</p>}
      {message && (edited || saving || announce) && <p className="mgd-subtle" role="status">{message}</p>}

      <div className="mgd-space" />
      <button type="button" className="mgd-link mgd-small" aria-expanded={limits}
        onClick={() => setLimits(!limits)}>Limits and dates ▾</button>
      {limits && <div className="q2-magnet-editor">
        <p className="mgd-small mgd-muted">Types and dates apply to Conversation content. Files are chosen one by one, by their exact path.</p>
        <label>After (date or ISO time)<input type="text" placeholder="2026-01-01 or 2026-01-01T12:00:00Z" value={after} disabled={locked} onChange={(e) => { setAlert(''); edit({ after: e.target.value }) }} /></label>
        <label>Before (date or ISO time)<input type="text" placeholder="2026-01-31 or 2026-01-31T12:00:00Z" value={before} disabled={locked} onChange={(e) => { setAlert(''); edit({ before: e.target.value }) }} /></label>
        {!collectable && <label><input type="checkbox" checked={manual} disabled={locked} onChange={(e) => edit({ manual: e.target.checked })} />Use supported manual collection: one extraction when I press Collect now, manual synthesis, no automatic notifications or agent processing. This replaces the saved collection and processing modes.</label>}
        <h5>Collection limits</h5>
        <h5>Supported here, and actionable</h5>
        <ul className="q2-magnet-items">{SUPPORTED_SOURCES.map((s) => <li key={s.kind}>{s.words}</li>)}</ul>
        <h5>Proposed only, and not offered as a choice</h5>
        <ul className="q2-magnet-items">{PROPOSED_SOURCES.map((s) => <li key={s.words}>{s.words}</li>)}</ul>
        <p className="mgd-small mgd-muted">{PROPOSED_REASON}</p>
        <p className="mgd-small mgd-muted">Individual post selection, schedules and automatic collection are unsupported.</p>
        <p className="mgd-small mgd-muted">Saved modes are kept unless you choose manual collection. Relevance and semantic filters are not applied.</p>
        {Object.entries(p.config.selection).filter(([k]) => !['informationTypes', 'dates'].includes(k)).map(([k, v]) => <p className="mgd-small mgd-muted" key={k}>{k}: {JSON.stringify(v)} (not applied)</p>)}
      </div>}
    </section>
  }
  /* SETTINGS' OWN COPY, reached from the header gear. No round-3 mockup covers
     it: it is the administrative surface, and the only place a Magnet is
     renamed or removed (plan seam 3), so its form stands as it was. */
  return <section className="q2-magnet-config" aria-label="Magnet configuration">
    {alert && <p className="q2-magnet-alert" role="alert" tabIndex={-1} ref={alerted}>{alert}</p>}

    {!p.inCollection && <label className="q2-magnet-config-name">Name
      <input value={name} maxLength={MAGNET_NAME_MOST} disabled={locked} aria-describedby="q2-magnet-name-note"
        onChange={(e) => { setAlert(''); setName(e.target.value) }} />
    </label>}
    {!p.inCollection && <p id="q2-magnet-name-note" className="q2-magnet-muted">This name is the Magnet’s own and does not change where it is shown.{committedName ? '' : ' It has none of its own yet, so it is currently named after where it is shown.'}</p>}

    {/* SOURCES ARE WHAT THIS PANEL IS FOR, so the configured ones are a plain
        list with their own Remove, and adding one is PROGRESSIVE (owner request
        ent-068c167fa7e6 §2, §4): the two supported kinds are offered, and only
        the chosen kind's controls appear. Before a kind is picked there is no
        Conversation search, no file collection chooser and no file list --
        which is what "not all controls for all kinds at once" means here. */}
    <h4>Sources</h4>
    <ul className="q2-magnet-items q2-magnet-source-rows">{sources.map((s, i) => <li key={sourceIdentity(s)}>
      <span><strong>{sourceTitle(s)}</strong><small className="q2-magnet-muted">{sourceSubtitle(s)}</small></span>
      <button type="button" className="q2-magnet-link" disabled={locked} onClick={() => { setAlert(''); edit({ sources: sources.filter((_, j) => i !== j) }) }}>Remove</button>
    </li>)}</ul>
    <p role="status" aria-live="polite">{sources.length ? `${sources.length} of 20 sources chosen. Choose Conversations, files, or both.` : NO_SOURCE_TO_COLLECT}</p>
    <div className="q2-magnet-add-source" role="group" aria-label="Add a source">
      <span className="q2-magnet-add-label">Add a source</span>
      <button type="button" className="q2-magnet-kind" aria-expanded={adding === 'conversation'} disabled={locked}
        onClick={() => { setAlert(''); setAdding(adding === 'conversation' ? '' : 'conversation') }}>Add Conversations</button>
      <button type="button" className="q2-magnet-kind" aria-expanded={adding === 'file'} disabled={locked}
        onClick={() => { setAlert(''); setAdding(adding === 'file' ? '' : 'file') }}>Add files</button>
    </div>
    {adding === 'conversation' && conversationPicker}
    {adding === 'file' && filePicker}

    {/* WHAT IS COLLECTED, said before it is offered to be changed. The reader
        sees the current selection as a sentence; the controls that change it,
        the date limits and the limits of this build are one press away each
        (§4: do not present every option at once). */}
    <h4>What to collect</h4>
    <p className="q2-magnet-muted">{types.length ? types.join(', ') : 'Nothing selected'}{after || before ? ` · ${after || 'any start'} to ${before || 'any end'}` : ''}</p>
    <details><summary>Change what to collect</summary>
      <div className="q2-magnet-config-types">{['post', 'file', 'image', 'attachment'].map((t) => <label key={t}><input type="checkbox" checked={types.includes(t)} disabled={locked} onChange={(e) => { setAlert(''); edit({ types: e.target.checked ? [...types, t] : types.filter((v) => v !== t) }) }} />{t}</label>)}</div>
      <p className="q2-magnet-muted">{SUPPORTED_REASON}</p>
    </details>

    {!supportsManualCollection(p.config) && <label><input type="checkbox" checked={manual} disabled={locked} onChange={(e) => edit({ manual: e.target.checked })} />Use supported manual collection: one extraction when I press Collect now, manual synthesis, no automatic notifications or agent processing. This replaces the saved collection and processing modes.</label>}

    <details><summary>Limits and dates</summary>
      <p>Types and dates apply to Conversation content. Files are chosen one by one, by their exact path.</p>
      <label>After (date or ISO time)<input type="text" placeholder="2026-01-01 or 2026-01-01T12:00:00Z" value={after} disabled={locked} onChange={(e) => { setAlert(''); edit({ after: e.target.value }) }} /></label>
      <label>Before (date or ISO time)<input type="text" placeholder="2026-01-31 or 2026-01-31T12:00:00Z" value={before} disabled={locked} onChange={(e) => { setAlert(''); edit({ before: e.target.value }) }} /></label>
      <h5>Collection limits</h5>
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

    {edited && <p className="q2-magnet-muted">Unsaved changes. Save or cancel.</p>}
    {reading && <p role="status">{reading}</p>}{message && <p role="status">{message}</p>}
    <div className="q2-magnet-settings-actions">
      <button type="button" className="q2-magnet-primary" disabled={saving || !arrangement || !p.canWrite(arrangement) || !sendable} onClick={() => void save()}>{saving ? 'Saving…' : attempt.current ? 'Retry unchanged save' : 'Save collection configuration'}</button>
      <button type="button" disabled={saving || (!edited && !renaming)} onClick={() => { setAlert(''); setName(committedName); setMessage('Staged configuration edits were discarded. Nothing was sent.'); discardStagedSettings(at) }}>Cancel configuration edits</button>
    </div>
  </section>
}
