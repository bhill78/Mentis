/** The Magnet's collection configuration: ONE panel, drawn in three places.
 *
 *  It opens on what the owner came to change: the Magnet's name (in Settings,
 *  which is the only place a Magnet is renamed), then its sources, then what to
 *  collect from a Conversation. Everything else -- the date limits, the saved
 *  collection modes, the limits of this build, which saved location the save is
 *  addressed through -- is disclosed, not stacked in front.
 *
 *  ONE BODY, NOT TWO (owner request: "Simplify collection configuration
 *  substantially. Consolidate duplicated settings"). This file used to hold two
 *  divergent surfaces for the same settings: the approved round-3 Sources
 *  surface for the Collection place, and an older administrative form for the
 *  Settings overlay, each with its own source list, its own "what to collect",
 *  its own date fields and its own commit. They have been consolidated into the
 *  sections below, which are composed once and drawn wherever the panel is. The
 *  approved design (`magnet-design-round3/03-sources.png`) is the one that
 *  survived, because it is the one the owner approved; Settings adds the two
 *  things only it has -- the name, and the saved location the save goes through
 *  -- and takes the rest as it is.
 *
 *  What differs between placements is therefore declared, not duplicated:
 *    `inRail`        a section heading only: the split Collection surface says
 *                    where the reader is and counts what is collected once,
 *                    and the collected items are the column beside this one.
 *    `inCollection`  the approved heading row and its counterpart link; no name.
 *    otherwise       the name (identity) facet, and the saved location.
 *    `resource`      "Collect manually" with Collect now; Settings has no
 *                    resource and so does not offer collection.
 *
 *  Its edits are staged: a copy is taken when the panel opens, every change
 *  writes to that copy, and only **Save** commits it, through the existing
 *  reconfigure route. **Discard** drops the staged copy; Escape leaves the
 *  overlay and keeps it, so reopening the gear shows the same unsaved edits.
 *  Neither touches the message draft or any inquiry draft -- those are other
 *  slots, in `panelDrafts.ts`.
 *
 *  DATES ARE PICKED, NOT TYPED. The two limits used to be free text fields
 *  asking for "a date or ISO time" and refusing afterwards what they could not
 *  read. They are date inputs now, each bounded by the other, so the browser's
 *  own picker prevents the two mistakes the panel used to explain. A saved limit
 *  that carries a time of day is kept exactly as it is while its day is
 *  unchanged (`dayOf`, `withDay` in `configuration.ts`).
 *
 *  The source model is the honest one: Conversation post capture and exact held
 *  text files are supported and actionable here; every other kind the Magnet
 *  schema names is proposed only and is not offered as a choice. That wording
 *  moved behind `Collection limits` rather than standing on the surface -- it is
 *  still indexed in full by `settingsSource`, so it stays findable by search.
 *  NO SOURCE AT ALL is also an answer: a Magnet may be saved with none, the last
 *  one may be removed, and nothing is read in their place. */
import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react'
import type { MagnetConfig, MagnetSource } from '../../fluid/surface/magnet/types'
import type { MagnetResource } from './contract'
import { conversationChoices, type ConversationChoice } from './managementApi'
import { collectionChange, collectionIssue, collectionRhythm, collectsOnlyByHand, configurationRead, dayOf, exactFileIssue, fileChoiceIssue, findConfigurationLocation, identityChange, magnetName, MAGNET_NAME_MOST, MANUAL_COLLECTION, MANUAL_COLLECTION_MEANS, nameIssue, NO_SOURCE_TO_COLLECT, PROPOSED_REASON, PROPOSED_SOURCES, savedPlace, saveCollection, sourceIdentity, sourceRowName, SUPPORTED_REASON, SUPPORTED_SOURCES, supportsManualCollection, UNSUPPORTED_REASON, withDay, type ConfigurationChange } from './configuration'
import { discardStagedSettings, panelDrafts, requestSettingsReturn, stageSettings, subscribePanelDrafts, type StagedSettings } from './panelDrafts'
import { openInSources, type SourcesRoute } from '../../surfaces/sources/route'
import './design.css'
import './configuration.css'
import './collection.css'

type Choice = { id: string; name: string }
type HeldFile = { path: string; label?: string; text?: boolean; state: string; size?: number }

/** The information types, in the reader's words rather than the schema's. The
 *  checkbox used to be labelled `post`; the sentence over it already said
 *  "Posts", so the control says the same thing the sentence does. */
const TYPE_WORDS: Record<string, string> = { post: 'Posts', file: 'Files', image: 'Images', attachment: 'Attachments' }
const COLLECTABLE_TYPES = ['post', 'file', 'image', 'attachment'] as const

/** WHAT IS BEING COLLECTED, AS A SENTENCE (approved mockup round 3,
 *  03-sources.png: "Posts, files, images and attachments"). The selection
 *  itself is unchanged -- this only says it in the reader's words instead of
 *  presenting the checkbox form that sets it.
 *
 *  The limits are said as the DAYS they are, because that is what the pickers
 *  that set them show. A stored limit carrying a time of day is kept exactly as
 *  it is in the definition (`withDay`), but a reader is told the day rather
 *  than being shown `2026-01-01T09:30:00Z` in the middle of a sentence. */
export function whatIsCollected(types: readonly string[], after: string, before: string): string {
  const words = types.map((t) => `${t}s`)
  const listed = !words.length ? 'Nothing selected'
    : words.length === 1 ? words[0]
      : `${words.slice(0, -1).join(', ')} and ${words[words.length - 1]}`
  const said = listed === 'Nothing selected' ? listed : listed.charAt(0).toUpperCase() + listed.slice(1)
  return after || before ? `${said} · ${dayOf(after) || 'any start'} to ${dayOf(before) || 'any end'}` : said
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

/* -- THE SOURCE CATALOGUE HAS THREE STATES, AND THE PANEL SAYS WHICH ------- *
 *
 * `/api/sources` is read once when the panel opens, and everything about a
 * source that a reader recognises comes out of it: which file collections may
 * be offered, what each configured collection is CALLED, and which kinds of
 * source this Brain can take at all. Before it answers, none of that is
 * known -- and the panel used to present the unknown as an answer: "Where the
 * files are" offered its placeholder and nothing else, a configured row read
 * "Held collection" as though that were the collection's name, and a read
 * that FAILED said nothing whatsoever (the failure went to `setMessage`, which
 * only renders once a save or a discard has been attempted). So a reader met
 * an empty chooser and an unnamed row with no way to tell "still reading"
 * from "there are none" from "the read failed".
 *
 * Reading, read and failed are three different things and are said as three
 * different things, with the failure's own words and a way to ask again.
 * ------------------------------------------------------------------------- */
export type CatalogueState = 'reading' | 'read' | 'failed'
export const CATALOGUE_READING = 'Reading the file collections this Brain holds…'
export const CATALOGUE_FAILED = 'The source catalogue could not be read, so no file collection can be offered and a configured collection is named by what the Magnet carries rather than by its own name.'
export const CATALOGUE_NONE = 'No file collection is available to attach'

/** What the panel says about the catalogue, in each state. Nothing at all once
 *  it is read: the collections themselves are then the answer. */
export function catalogueWords(state: CatalogueState, why?: string | null): string {
  if (state === 'reading') return CATALOGUE_READING
  if (state === 'failed') return why ? `${CATALOGUE_FAILED} ${why}` : CATALOGUE_FAILED
  return ''
}

/** THE CATALOGUE'S STATE, SAID WHERE IT BITES: in the chooser that has nothing
 *  to offer, and on the resting surface when a configured row cannot be named
 *  without it. A failed read is offered a retry, because a read is all it is. */
export function CatalogueNote({ state, why, onRetry }: { state: CatalogueState; why?: string | null; onRetry?: () => void }) {
  const said = catalogueWords(state, why)
  if (!said) return null
  return <p className={`mgd-small mgd-subtle q2-magnet-catalogue${state === 'failed' ? ' q2-magnet-catalogue-failed' : ''}`} role="status" aria-live="polite">
    {said}
    {state === 'failed' && onRetry ? <> <button type="button" className="mgd-link mgd-small" onClick={onRetry}>Try again</button></> : null}
  </p>
}

/** A CONFIGURED COLLECTION'S OWN NAME, from every collection the catalogue
 *  listed -- not only the ones that may be ADDED. The two are different sets:
 *  a collection whose connector is unavailable on this machine is not offered
 *  as a choice, and a Magnet that already reads it still has to say what it
 *  is. Naming the row from the offerable list alone is why a web search
 *  declared in Manage Sources read "Held collection" on a surface that knew
 *  its name perfectly well. */
export function collectionWord(id: string | undefined, names: Record<string, string>): string {
  return (id && names[id]) || 'Held collection'
}

/** THE KINDS OF SOURCE THAT ARE DECLARED, NOT CHOSEN (`binding: 'endpoint'`:
 *  `web-search`, `rss-atom`, `web`). They have no folder and no file to pick,
 *  so there is nothing for this panel to browse: what they read is the
 *  queries or feed addresses given once in Manage Sources, after which they
 *  are a held collection like any other and are attached here as one. Read
 *  from the same `/api/sources` descriptors, so an unavailable kind is never
 *  offered and nothing is hardcoded about which kinds exist. */
export function endpointKinds(descriptors: unknown): Choice[] {
  return (Array.isArray(descriptors) ? descriptors : [])
    .filter((d: any) => d?.available && d?.binding === 'endpoint')
    .map((d: any) => ({ id: String(d.id), name: String(d.label || d.id) }))
}
export const ENDPOINT_FIRST = 'A web search, a feed or a web page is declared once in Manage Sources, with the queries or addresses it reads. It is then a held collection, and this panel attaches it like any other.'

/** WHERE "DECLARE ONE" GOES: Add a source, on that kind, in the one wizard
 *  there is (`quiet2/sources/AddSourcePage.tsx`) -- announced as the Sources
 *  address it is, which the shell already listens for and enters with a
 *  history entry, so Back comes to the Magnet. Nothing here is a second
 *  wizard, and nothing here declares a source. */
export function endpointRoute(connector: string | null): SourcesRoute {
  return connector ? { at: 'flow', connector } : { at: 'add' }
}

/** What the Brain has actually saved: the baseline a staged copy is taken from. */
export const committedSettings = (config: MagnetConfig): StagedSettings => ({
  sources: config.sources, types: config.selection.informationTypes ?? ['post', 'file', 'image'],
  after: config.selection.dates?.after ?? '', before: config.selection.dates?.before ?? '', manual: false,
})

/** WHETHER THE STAGED COPY DIFFERS FROM WHAT IS SAVED.
 *
 *  A staged copy is taken as soon as the panel opens, so that Discard has
 *  something definite to drop; its existence is therefore not evidence that
 *  anything was edited. The panel is somewhere a reader simply looks, and
 *  announcing "Unsaved changes" to someone who has changed nothing is exactly
 *  the administrative noise the redesign removes (owner request
 *  ent-1e82a8786c37). So the unsaved note and the commit follow the comparison,
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
   *  Settings overlay. The identity (name) facet stays Settings' own -- the
   *  Collection place is sources and collection behaviour only, never a second
   *  place to rename the Magnet -- and a save here commits and clears the staged
   *  copy without asking an overlay to return, because there is no overlay to
   *  return from. */
  inCollection?: boolean
  /** IN COLLECTION'S OWN RAIL, BESIDE THE COLLECTED ITEMS (owner request
   *  ent-24beca915507: "sources and filters on one side, readable collected
   *  results on the other"). The split surface already carries the place's
   *  heading block and its count, so this placement contributes a section
   *  heading and nothing that would be said twice: no eyebrow, no second
   *  `view-title`, and no counterpart link to a column that is already on
   *  screen. Everything below the heading is the same body, from the same
   *  staged copy, committed the same way. */
  inRail?: boolean
  /** The Magnet this configures, supplied only by the Collection place: the
   *  approved Sources surface offers "Collect now" on its own "Collect
   *  manually" row (plan seam 3), and that is `resource.collect()` exactly as
   *  the header's button was. Settings' own copy has no such row. */
  resource?: MagnetResource
  /** Back to the collected items, the counterpart link of the approved
   *  heading row. Collection supplies it; Settings has nothing to go back to. */
  onBrowse?(): void
  /** OPENED FROM INSIDE THE CONVERSATION ITSELF (approved mockup round 4,
   *  `03-sources-add.png`/`04-sources-empty.png`): a popover anchored to the
   *  Magnet's own header, never a navigation away from the Conversation place.
   *  Add a source and the existing sources are both on screen at once, in two
   *  columns, so there is nowhere a reader has to remember to come back to --
   *  the editor behind `＋ Add source` is simply always open, and each
   *  existing row carries its one real action (Remove) as a small icon rather
   *  than a text link, matching Summary's own icon-only metadata row. */
  anchored?: boolean
  /** The Magnet's own name, for the panel's heading ("Sources — {title}").
   *  Anchored only: the other placements already say where they are. */
  title?: string }) {
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
  /** Every collection the catalogue listed, by id, for NAMING a configured
   *  row; `collections` above is the narrower set that may be added. */
  const [names, setNames] = useState<Record<string, string>>({})
  const [catalogue, setCatalogue] = useState<CatalogueState>('reading'), [catalogueWhy, setCatalogueWhy] = useState<string | null>(null)
  /** The kinds that are declared rather than picked, as the catalogue reports
   *  them; empty until it answers, and after a failed read. */
  const [declarable, setDeclarable] = useState<Choice[]>([])
  /** A failed read is a read: pressing Try again asks again, and nothing else
   *  about the panel is reset. */
  const [reread, setReread] = useState(0)
  const [collection, setCollection] = useState(''), [fileQuery, setFileQuery] = useState(''), [files, setFiles] = useState<HeldFile[]>([])
  const [prefix, setPrefix] = useState('')
  const [fileNext, setFileNext] = useState<number | null>(null), [fileOffset, setFileOffset] = useState(0)
  const [arrangements, setArrangements] = useState<Choice[]>([{ id: 'home', name: 'Brain Home' }])
  const [arrangement, setArrangement] = useState(''), [sendable, setSendable] = useState(false)
  const [locations, setLocations] = useState(false)
  /** Which source kind is being added, if any. Empty is the resting state: the
   *  two supported kinds are offered and neither one's controls are present. */
  const [adding, setAdding] = useState<'' | 'conversation' | 'file'>('')
  const [message, setMessage] = useState(''), [reading, setReading] = useState(''), [saving, setSaving] = useState(false)
  const [alert, setAlert] = useState('')
  /** The approved Sources surface says each thing once and opens its editors
   *  in place (03-sources.png): `＋ Add source`, `Change` beside what is being
   *  collected, and `Limits and dates ▾`, with the build's own limits one step
   *  further in. Nothing is a standing form, in any placement. */
  const [addOpen, setAddOpen] = useState(false), [changing, setChanging] = useState(false), [limits, setLimits] = useState(false)
  const [bounds, setBounds] = useState(false)
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
  // The staged copy is taken when the panel opens, so Discard has something
  // definite to drop and Escape has something definite to keep.
  useEffect(() => { if (!panelDrafts(at).settings) stageSettings(at, committedSettings(current.current.config)) }, [at])
  // The name field follows a committed rename (its own or another session's),
  // and otherwise keeps what is being typed.
  useEffect(() => { setName(committedName) }, [at, committedName])
  // A refused rule takes focus and stays put; nothing is committed behind it.
  useEffect(() => { if (alert) alerted.current?.focus({ preventScroll: true }) }, [alert])
  useEffect(() => {
    const ctl = new AbortController()
    setCatalogue('reading'); setCatalogueWhy(null)
    void Promise.all([configurationRead('/api/sources', ctl.signal), configurationRead('/fluid/api/workspaces', ctl.signal)]).then(([s, w]) => {
      if (ctl.signal.aborted) return
      // WHICH COLLECTIONS MAY BE NAMED IS THE REGISTRY'S ANSWER, read from the
      // same reply (`descriptors`), not a connector listed here. This was
      // `c.connector === 'filesystem'`, which hid every Git, SQLite, feed, web
      // search and web page collection -- including, after Part W, ones a
      // Magnet reads perfectly well, and the one a Magnet created from a
      // sentence declares for itself. An unavailable connector's collection is
      // still not offered, because the registry still says so.
      const readable = new Set(((s.descriptors ?? []) as any[]).filter((d) => d?.available).map((d) => d.id))
      setCollections((s.collections ?? []).filter((c: any) => readable.has(c.connector)).map((c: any) => ({ id: c.collection, name: c.name || c.collection })))
      // WHAT EVERY LISTED COLLECTION IS CALLED, availability aside: a row for a
      // collection this machine cannot currently read still says which one it is.
      setNames(Object.fromEntries((s.collections ?? []).map((c: any) => [String(c.collection), String(c.name || c.collection)])))
      setDeclarable(endpointKinds(s.descriptors))
      setArrangements([{ id: 'home', name: 'Brain Home' }, ...(w.workspaces ?? []).map((v: any) => ({ id: v.id, name: v.name }))])
      setCatalogue('read')
      setLocations(true)
    }).catch((e) => {
      // A FAILED CATALOGUE READ IS SAID WHERE IT IS FELT, not put in the save's
      // own message slot, which renders only once a save or discard was asked
      // for and so said nothing at all to a reader who had only opened Sources.
      if (!ctl.signal.aborted) { setCatalogue('failed'); setCatalogueWhy((e as Error).message); setLocations(true) }
    })
    return () => ctl.abort()
  }, [p.brainKey, p.magnet, reread])
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
      if (found) { setArrangement(found.arrangement); setSendable(true); setMessage('') }
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
    void savedPlace(arrangement, p.magnet, ctl.signal).then(() => { if (!ctl.signal.aborted) setSendable(true) })
      .catch((e) => { if (!ctl.signal.aborted) { setSendable(false); setMessage(e.message) } })
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
  /** A CONFIGURED SOURCE, SAID AS WHAT IT READS. A `file` source names one
   *  path, everything under a path prefix, or the whole collection (Part C,
   *  `activation.file_choice`), so a path-less one is the collection itself
   *  and not a half-finished choice -- it used to read "Choose one exact
   *  file", which told the owner to finish something that was already done,
   *  and a web search declared at creation is exactly that shape. */
  const collectionName = (id: string | undefined) => collectionWord(id, names)
  /** A PATH THAT IS A STORAGE KEY IS NOT A TITLE (owner ent-24beca915507: ids
   *  and raw collection mechanics stay secondary). A configured file's own
   *  path -- `README.md`, `notes/calibration.txt` -- is what a reader
   *  recognises and is kept. What is not is a held web page or feed entry,
   *  whose path IS the key it was written under: `www-nasa-gov/0033172620276ee1`
   *  was standing as the TITLE of a source row, which is the storage layer
   *  read out as the name of a thing. The same rule the collected rows use
   *  (`EvidenceViews.RAW_STORAGE_KEY`), stated here rather than imported,
   *  because that module imports this one. */
  const storageKey = (path: string) => /^[a-f0-9]{10,}$/i.test((path.split('/').pop() ?? path).replace(/\.[a-z0-9]{1,8}$/i, ''))
  const sourceTitle = (s: MagnetSource) => s.kind === 'conversation' ? conversations.find((c) => c.id === s.conversation)?.name || 'Saved Conversation'
    : s.kind === 'file' ? (s.path === undefined || storageKey(s.path) ? collectionName(s.collection) : s.path) : `${s.kind} (unavailable)`
  const sourceSubtitle = (s: MagnetSource) => s.kind === 'conversation' ? 'Conversation · posts and attachments'
    : s.kind === 'file' ? (s.path === undefined ? 'Everything in this collection'
      : s.path.endsWith('/') ? `Everything under this path · ${collectionName(s.collection)}`
        : storageKey(s.path) ? 'One held item of this collection'
          : `Held file · ${collectionName(s.collection)}`)
      : 'Unavailable in this build'
  const add = (s: MagnetSource) => {
    if (locked) return
    setAlert('')
    if (sources.length >= 20) { setMessage('The Magnet supports at most 20 sources. Remove one before adding another.'); return }
    if (!sources.some((v) => sourceIdentity(v) === sourceIdentity(s))) edit({ sources: [...sources, s] })
  }
  /** A configured file source whose collection the catalogue has not named. */
  const unnamed = sources.some((s) => s.kind === 'file' && !(s.collection && names[s.collection]))
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
  const discard = () => {
    setAlert('')
    // Settings also commits the name, so discarding there puts the field back
    // to what is saved; the Collection place has no name field to put back.
    if (!p.inCollection) setName(committedName)
    setMessage('Staged configuration edits were discarded. Nothing was sent.')
    setAnnounce(true)
    discardStagedSettings(at)
  }

  /* -- the sections, composed once and drawn wherever the panel is ---------- */

  /* THE TWO SUPPORTED KINDS' CONTROLS, defined once and drawn behind
     `＋ Add source`. The same `add()` and the same staged copy in every
     placement -- before a kind is picked there is no Conversation search, no
     file collection chooser and no file list, which is what "do not present
     every option at once" means here. */
  const conversationPicker = <div className="q2-magnet-kind-panel"><label>Find a Conversation<input type="search" value={query} disabled={locked} onChange={(e) => setQuery(e.target.value)} /></label><div className="q2-magnet-config-choices">{conversations.map((c) => <button type="button" key={c.id} disabled={locked || sources.some((s) => s.kind === 'conversation' && s.conversation === c.id)} onClick={() => add({ kind: 'conversation', conversation: c.id })}>Add {c.name}</button>)}</div>{next && <button type="button" className="mgd-link mgd-small" onClick={() => { const key = p.brainKey; void conversationChoices(query, next, new AbortController().signal).then((v) => { if (current.current.brainKey === key) { setConversations((old) => [...old, ...v.rows]); setNext(v.next) } }).catch((e) => setReading(e.message)) }}>More Conversations</button>}</div>
  /** A SOURCE DOES NOT HAVE TO NAME ONE FILE (`fileChoiceIssue`, Part C): the
   *  whole collection, or everything under a path prefix, are both file
   *  sources the schema already carries and the server already validates --
   *  this is the one-file picker's own doc comment, made into controls. Each
   *  sits beside the exact-file list rather than replacing it, since all
   *  three are valid ways to attach the same collection. */
  const wholeAdded = (col: string) => sources.some((s) => s.kind === 'file' && s.collection === col && s.path === undefined)
  const prefixIssue = collection ? fileChoiceIssue(collection, prefix.trim() ? (prefix.trim().endsWith('/') ? prefix.trim() : prefix.trim() + '/') : undefined) : null
  const filePicker = <div className="q2-magnet-kind-panel">
    {/* WHAT THE CHOOSER OFFERS WHILE IT HAS NOTHING TO OFFER. Reading, read
        with none, and a failed read are three different sentences, and the
        chooser itself is disabled while there is nothing in it to choose --
        it used to show "Choose a file collection" over an empty list in all
        three cases. */}
    <label>Where the files are<select value={collection} disabled={locked || !collections.length}
      onChange={(e) => { setCollection(e.target.value); setFileOffset(0); setPrefix('') }}>
      <option value="">{catalogue === 'reading' ? CATALOGUE_READING : collections.length ? 'Choose a file collection' : CATALOGUE_NONE}</option>
      {collections.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
    </select></label>
    <CatalogueNote state={catalogue} why={catalogueWhy} onRetry={() => setReread(reread + 1)} />
    {collection && <div className="q2-magnet-config-choices">
      <div className="mgd-row">
        <button type="button" disabled={locked || wholeAdded(collection)} onClick={() => add({ kind: 'file', collection, path: undefined })}>Attach the whole collection</button>
      </div>
      <div className="mgd-row">
        <input type="text" value={prefix} disabled={locked} placeholder="A path prefix, e.g. notes/" aria-label="Path prefix"
          onChange={(e) => { setAlert(''); setPrefix(e.target.value) }} />
        <button type="button" disabled={locked || !prefix.trim()}
          onClick={() => {
            const p = prefix.trim().endsWith('/') ? prefix.trim() : prefix.trim() + '/'
            const issue = fileChoiceIssue(collection, p)
            if (issue) { setAlert(issue); return }
            add({ kind: 'file', collection, path: p }); setPrefix('')
          }}>Attach everything under this prefix</button>
      </div>
      {prefix.trim() && prefixIssue && <small>{prefixIssue}</small>}
    </div>}
    <label>Find a file<input type="search" value={fileQuery} disabled={locked} onChange={(e) => { setFileQuery(e.target.value); setFileOffset(0) }} /></label>
    <div className="q2-magnet-config-choices">{files.map((f) => { const issue = exactFileIssue(collection, f.path) || (f.text !== true ? 'Only plain text files are supported.' : null); return <div key={f.path}><button type="button" disabled={locked || !!issue || sources.some((s) => s.kind === 'file' && s.collection === collection && s.path === f.path)} title={issue ?? undefined} onClick={() => add({ kind: 'file', collection, path: f.path })}>{f.path}</button>{issue && <small>{issue}</small>}{typeof f.size === 'number' && f.size > 65536 && <small>Only the first 64 KiB will be captured, ending on a UTF-8 character boundary.</small>}</div> })}</div><div>{fileOffset > 0 && <button type="button" className="mgd-link mgd-small" onClick={() => setFileOffset(Math.max(0, fileOffset - 40))}>Previous files</button>}{fileNext !== null && <button type="button" className="mgd-link mgd-small" onClick={() => setFileOffset(fileNext)}>More files</button>}</div></div>

  const refusedRule = alert && <p className="q2-magnet-alert" role="alert" tabIndex={-1} ref={alerted}>{alert}</p>

  /** The configured sources, each a ruled row with its own Remove, then the one
   *  way to add another. The count out of twenty is gone: the rows are the
   *  count, and the bound is stated where it actually bites (at the press to
   *  add the twenty-first). */
  /** EACH EXISTING ROW'S OWN ACTION. Anchored, it is the small icon-only
   *  button Summary's own metadata row uses (`q2-magnet-icon`) rather than a
   *  text link, since the popover has no room to spare and Remove is the only
   *  action a configured row actually has. Every other placement keeps the
   *  text link exactly as it was. */
  const existingRows = sources.map((s, i) => <div className="mgd-row mgd-spread mgd-source" key={sourceIdentity(s)}>
    <div className="mgd-grow">
      <b>{sourceTitle(s)}</b>
      <div className="mgd-subtle">{sourceSubtitle(s)}</div>
    </div>
    {p.anchored
      ? <button type="button" className="q2-magnet-icon" aria-label={`Remove ${sourceTitle(s)}`} title={`Remove ${sourceTitle(s)}`}
          disabled={locked} onClick={() => { setAlert(''); edit({ sources: sources.filter((_, j) => i !== j) }) }}><span aria-hidden="true">🗑</span></button>
      : <button type="button" className="mgd-link mgd-small" disabled={locked}
          onClick={() => { setAlert(''); edit({ sources: sources.filter((_, j) => i !== j) }) }}>Remove</button>}
  </div>)

  /** THE EDITOR'S OWN BODY, the same in every placement: the two kind pills,
   *  whichever picker is open, declaring an endpoint source and a failed
   *  read's own words. Anchored draws it without the `＋ Add source` toggle
   *  around it -- the column is already titled "Add a source", so the editor
   *  is simply always there. */
  const addEditorBody = <>
    <div className="mgd-row">
      <button type="button" className={`mgd-pill${adding === 'conversation' ? ' mgd-active' : ''}`} aria-pressed={adding === 'conversation'}
        disabled={locked} onClick={() => { setAlert(''); setAdding(adding === 'conversation' ? '' : 'conversation') }}>Conversations</button>
      {/* "Held files", not "Files": in the split Collection surface this pill
          and the `Files` TYPE FILTER are in the same column, and two controls
          reading `Files` a hand's width apart mean two different things. It
          is also the truer name -- what this attaches is a held collection,
          a path under one, or one held file. */}
      <button type="button" className={`mgd-pill${adding === 'file' ? ' mgd-active' : ''}`} aria-pressed={adding === 'file'}
        disabled={locked} onClick={() => { setAlert(''); setAdding(adding === 'file' ? '' : 'file') }}>Held files</button>
    </div>
    {adding === 'conversation' && conversationPicker}
    {adding === 'file' && filePicker}
    {/* A SOURCE THAT HAS TO BE DECLARED BEFORE IT CAN BE CHOSEN. The two
        pills above are the two kinds this panel can pick from what already
        exists; a web search, a feed or a web page exists only once somebody
        has said what it reads. Until this was here, a Magnet offered
        "Conversations" and "Held files" and a reader had no way to learn
        that the web search they wanted was one wizard away -- it simply was
        not among the files, because nothing had declared it. The route is
        the one wizard there is, on the kind pressed. */}
    <div className="q2-magnet-declare">
      <p className="mgd-small mgd-muted">{ENDPOINT_FIRST}</p>
      <div className="mgd-row">
        {(declarable.length ? declarable : [{ id: '', name: 'a new source' }]).map((k) => <button type="button" key={k.id || 'any'}
          className="mgd-link mgd-small" onClick={() => openInSources(endpointRoute(k.id || null))}>Declare {k.name} in Manage Sources →</button>)}
      </div>
    </div>
    {/* A failed read of the choices is feedback about adding a source, and is
        said where adding happens -- not on a surface somebody is only
        looking at. */}
    {reading && <p className="mgd-subtle" role="status">{reading}</p>}
  </>

  const sourceSection = <>
    {existingRows}
    {!sources.length && <p className="mgd-subtle" role="status" aria-live="polite">{NO_SOURCE_TO_COLLECT}</p>}
    {/* THE ROWS' OWN NAMES COME OUT OF THE CATALOGUE, so where a row above is
        standing unnamed because the catalogue is still being read or could
        not be read, that is said here -- once, beside the rows it is about,
        and not at all when every row is named. */}
    {catalogue !== 'read' && unnamed && <CatalogueNote state={catalogue} why={catalogueWhy} onRetry={() => setReread(reread + 1)} />}
    <div className="mgd-source">
      <button type="button" className="mgd-button mgd-secondary" aria-expanded={addOpen} disabled={locked}
        onClick={() => { setAlert(''); setAddOpen(!addOpen); if (addOpen) setAdding('') }}>＋ Add source</button>
    </div>
    {addOpen && <div className="q2-magnet-editor">{addEditorBody}</div>}
  </>

  /** What is collected, said as a sentence, with the form that sets it one
   *  press away. The sentence is the live region: it is what follows the
   *  staged selection, so it is what an assistive reader is told about. */
  const whatSection = <>
    <div className="mgd-row mgd-spread">
      <div className="mgd-grow">
        <b>What to collect</b>
        <div className="mgd-subtle" role="status" aria-live="polite">{whatIsCollected(types, after, before)}</div>
      </div>
      <button type="button" className="mgd-link mgd-small" aria-expanded={changing} disabled={locked}
        onClick={() => { setAlert(''); setChanging(!changing) }}>Change</button>
    </div>
    {changing && <div className="q2-magnet-editor q2-magnet-config-types">
      {COLLECTABLE_TYPES.map((t) => <label key={t}>
        <input type="checkbox" checked={types.includes(t)} disabled={locked}
          onChange={(e) => { setAlert(''); edit({ types: e.target.checked ? [...types, t] : types.filter((v) => v !== t) }) }} />{TYPE_WORDS[t]}
      </label>)}
    </div>}
  </>

  const collectable = supportsManualCollection(p.config)
  const byHandOnly = collectsOnlyByHand(p.config)
  const collecting = !!live?.collecting
  const mayCollect = p.canWrite('home') && collectable && !collecting && !!p.resource?.collect
  /** Collecting, where the Magnet itself was supplied. Settings has no resource
   *  and so does not offer it; the frame disables it while Settings is open. */
  const collectSection = !!p.resource && <>
    <div className="mgd-divider" />
    <div className="mgd-row mgd-spread">
      <div className="mgd-grow">
        {/* HOW OFTEN IT LOOKS, AND ASKING FOR IT NOW: BOTH, SINCE PART D2.
            A Magnet made from a sentence carries a cadence, and this build
            now collects a scheduled Magnet at a press as well as when it is
            due (`activation.COLLECTABLE_MODES`, widened at `04853f40`). So
            the heading says what the cadence is -- never a saved mode word --
            and the press is offered beside it, because an owner who can see
            information arriving must be able to ask for it sooner. Only a
            paused or continuous Magnet has no press to offer. */}
        <b>{byHandOnly ? 'Collect manually' : 'Collects on its own'}</b>
        <div className="mgd-subtle">{byHandOnly ? lastCollected(live?.activation?.at)
          : `${collectionRhythm(p.config)} · ${lastCollected(live?.activation?.at).toLowerCase()}`}</div>
      </div>
      {collectable && <button type="button" className="mgd-button" disabled={!mayCollect}
        onClick={() => void p.resource?.collect?.()}>{collecting ? 'Collecting…' : 'Collect now'}</button>}
    </div>
  </>

  const mayCommit = !saving && !!arrangement && p.canWrite(arrangement) && sendable
  /** The commit, where an edit actually leaves something unsaved -- never a
   *  standing form, in any placement. Same path, same request shape, same gate
   *  as the two it replaces. In Settings a rename is also something unsaved,
   *  because the same Save commits it. */
  const commitSection = (edited || renaming) && <div className="mgd-row mgd-spread q2-magnet-commit">
    <span className="mgd-subtle">Unsaved changes</span>
    <span className="mgd-row">
      <button type="button" className="mgd-link mgd-small" disabled={saving} onClick={discard}>Discard</button>
      <button type="button" className="mgd-button" aria-label="Save collection configuration" disabled={!mayCommit}
        onClick={() => void save()}>{saving ? 'Saving…' : attempt.current ? 'Retry' : 'Save'}</button>
    </span>
  </div>

  /** THE ADVANCED OPTIONS, PROGRESSIVELY (owner request: "progressively disclose
   *  advanced options"). One step in: the date limits, which are the ones
   *  actually reached for, now as date pickers bounded by each other. One step
   *  further: what this build can and cannot collect, which is reference
   *  material rather than a setting. The three near-identical paragraphs that
   *  used to stand here are one sentence (`UNSUPPORTED_REASON`), and the empty
   *  "Collection limits" heading that labelled nothing now labels this. */
  const limitsSection = <>
    <div className="mgd-space" />
    <button type="button" className="mgd-link mgd-small" aria-expanded={limits}
      onClick={() => setLimits(!limits)}>Limits and dates ▾</button>
    {limits && <div className="q2-magnet-editor">
      <p className="mgd-small mgd-muted">Dates apply to Conversation content. Files are chosen one by one, by their exact path.</p>
      <div className="mgd-row q2-magnet-dates">
        <label className="mgd-small">From<input type="date" value={dayOf(after)} max={dayOf(before) || undefined} disabled={locked}
          onChange={(e) => { setAlert(''); edit({ after: withDay(after, e.target.value) }) }} /></label>
        <label className="mgd-small">To<input type="date" value={dayOf(before)} min={dayOf(after) || undefined} disabled={locked}
          onChange={(e) => { setAlert(''); edit({ before: withDay(before, e.target.value) }) }} /></label>
      </div>
      {/* The switch that makes collection manual ONLY, so it is offered
          wherever that is not already the case -- a scheduled Magnet
          included, which can be collected by hand and still looks on its own
          until this is chosen. */}
      {!byHandOnly && <label className="mgd-small"><input type="checkbox" checked={manual} disabled={locked}
        onChange={(e) => edit({ manual: e.target.checked })} />{MANUAL_COLLECTION}
        <span className="mgd-subtle"> {MANUAL_COLLECTION_MEANS}</span></label>}
      <button type="button" className="mgd-link mgd-small" aria-expanded={bounds}
        onClick={() => setBounds(!bounds)}>Collection limits ▾</button>
      {bounds && <div className="q2-magnet-bounds">
        <h5>Supported here, and actionable</h5>
        <ul className="q2-magnet-items">{SUPPORTED_SOURCES.map((s) => <li key={sourceRowName(s)}>{s.words}</li>)}</ul>
        <h5>Proposed only, and not offered as a choice</h5>
        <ul className="q2-magnet-items">{PROPOSED_SOURCES.map((s) => <li key={s.words}>{s.words}</li>)}</ul>
        <p className="mgd-small mgd-muted">{PROPOSED_REASON}</p>
        <p className="mgd-small mgd-muted">{SUPPORTED_REASON}</p>
        <p className="mgd-small mgd-muted">{UNSUPPORTED_REASON}</p>
        {/* DELETED (#802, amendment §4): a `JSON.stringify` of every selection
            key this build does not apply stood here -- the wire format of a
            setting nobody chose, read out to the owner. A filter that is saved
            and not applied is said as that, by name, in `configurationFacts`,
            which is also what the index carries. The value is in the record for
            anyone who needs it; it is not interface. */}
      </div>}
    </div>}
  </>

  /** The messages: said where the save was asked for, and only once a save or a
   *  discard has actually been attempted. */
  const messageSection = message && (edited || renaming || saving || announce) && <p className="mgd-subtle" role="status">{message}</p>

  /* THE BODY BOTH COLLECTION PLACEMENTS DRAW, in the approved order (round 3,
     03-sources.png) and nothing else on it: one sentence, the configured
     sources with their own Remove, `＋ Add source`, then what to collect and
     collecting manually, each one line with one control at the far edge, and
     `Limits and dates ▾` as the single way to the rest. */
  const collectionBody = <>
    <p className="mgd-p mgd-muted">Choose where to look. Collect when you’re ready.</p>
    {refusedRule}
    {sourceSection}
    <div className="mgd-divider" />
    {whatSection}
    {collectSection}
    {commitSection}
    {messageSection}
    {limitsSection}
  </>

  if (p.anchored) {
    /* THE INLINE SOURCES PANEL (approved mockup round 4, `03-sources-add.png`
     * / `04-sources-empty.png`): add a source and the existing ones in two
     * columns at once, anchored to the Conversation rather than a place of
     * its own. The empty state keeps both columns -- the add column never
     * depends on there being anything to list beside it. */
    return <section className="q2-magnet-config q2-magnet-sources-anchored" aria-label="Sources">
      <div className="q2-magnet-sources-anchored-head">
        <h2 className="mgd-h2" tabIndex={-1}>Sources — {p.title ?? ''}</h2>
        <div className="mgd-subtle">{sources.length
          ? (byHandOnly ? lastCollected(live?.activation?.at) : `${collectionRhythm(p.config)} · ${lastCollected(live?.activation?.at).toLowerCase()}`)
          : 'No sources yet · add one to start collecting'}</div>
      </div>
      <div className="mgd-divider" />
      {refusedRule}
      <div className="q2-magnet-sources-anchored-cols">
        <div className="q2-magnet-sources-anchored-add">
          <div className="mgd-eyebrow">Add a source</div>
          {addEditorBody}
        </div>
        <div className="q2-magnet-sources-anchored-existing">
          <div className="mgd-eyebrow">Existing sources ({sources.length})</div>
          {existingRows}
          {!sources.length && <p className="mgd-subtle" role="status" aria-live="polite">{NO_SOURCE_TO_COLLECT}</p>}
          {catalogue !== 'read' && unnamed && <CatalogueNote state={catalogue} why={catalogueWhy} onRetry={() => setReread(reread + 1)} />}
        </div>
      </div>
      {whatSection}
      {collectSection}
      {commitSection}
      {messageSection}
    </section>
  }
  if (p.inRail) {
    /* THE SOURCES RAIL of the split Collection surface (owner request
       ent-24beca915507). A section heading, then the same body: the split
       surface's own heading block already says where the reader is and counts
       what is collected, and the collected items are the other column rather
       than somewhere to link to. */
    return <section className="q2-magnet-config q2-magnet-sources q2-magnet-sources-rail" aria-label="Sources">
      <h3 id="q2-magnet-sources-head" className="mgd-h3" tabIndex={-1}>Sources</h3>
      {collectionBody}
    </section>
  }
  if (p.inCollection) {
    /* COLLECTION -> SOURCES, THE APPROVED SURFACE (round 3, 03-sources.png),
     * as its own whole surface -- the heading block with its counterpart link
     * over the same body. */
    return <section className="q2-magnet-config q2-magnet-sources" aria-label="Sources">
      <div className="mgd-row mgd-spread q2-magnet-place-head">
        <div className="mgd-grow">
          <div className="mgd-eyebrow">Collection</div>
          <h2 id="view-title" className="mgd-h2" tabIndex={-1}>Sources</h2>
        </div>
        {p.onBrowse && <button type="button" className="mgd-link mgd-small q2-magnet-place-link" onClick={p.onBrowse}>Collected items →</button>}
      </div>
      {collectionBody}
    </section>
  }
  /* SETTINGS' OWN COPY, reached from the header gear. The same body, in the
     same order, with the two things only Settings has: the Magnet's name, which
     the same Save commits in the same reconfigure, and the saved location the
     save is addressed through, which is disclosed rather than demanded. */
  return <section className="q2-magnet-config" aria-label="Magnet configuration">
    {refusedRule}

    <label className="q2-magnet-config-name">Name
      <input value={name} maxLength={MAGNET_NAME_MOST} disabled={locked} aria-describedby="q2-magnet-name-note"
        onChange={(e) => { setAlert(''); setName(e.target.value) }} />
    </label>
    <p id="q2-magnet-name-note" className="mgd-small mgd-muted">This name is the Magnet’s own and does not change where it is shown.{committedName ? '' : ' It has none of its own yet, so it is currently named after where it is shown.'}</p>

    <div className="mgd-divider" />
    <h3 className="mgd-h3">Sources</h3>
    {sourceSection}
    <div className="mgd-divider" />
    {whatSection}
    {collectSection}
    {commitSection}
    {messageSection}
    {limitsSection}

    {/* DELETED (#802, amendment §4): a "Saved location" select over every saved
        arrangement AND every Conversation stood here, asking the owner to pick
        the door a configuration travels through. It was never a choice about
        the Magnet: the definition belongs to no arrangement, a location only
        keeps the operation key, and the right one is already FOUND read-only
        above (`findConfigurationLocation`). The one case the owner can act on
        -- that there is no saved location at all -- is said by `messageSection`,
        which is where the save's own feedback already is. */}
  </section>
}
