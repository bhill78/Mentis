/* THE UNIVERSAL MAGNET, PURE (plan adm-b848fa881c8d §3.10; part P7).
 *
 * One Magnet capability; a conversation is one possible source value, never
 * its identity (the `mag-` id is). Everything here is browser-free:
 *
 *   - the source-adapter registry, which every read and search goes through;
 *   - the compact pane's tabs: the ordered intersection of the selected
 *     information types and what the configured adapters can do, with Search
 *     only where an adapter searches, and an unsupported selected type kept
 *     visible, disabled, with its reason;
 *   - the same capability ids for every Magnet, whose Availability alone
 *     varies with sources, permissions, connectors and runtime;
 *   - what a config asks for that this build does not run (connectors, web,
 *     scheduled or continuous collection, synthesis, notifications), each
 *     with its reason -- kept, shown, never executed;
 *   - finding the Magnet a workspace already has for a conversation;
 *   - the rectangle a Magnet window is drawn at, by its level. */

import type { Arr } from '../../workspace/place'
import type { Zone } from '../../workspace/tree'
import { allPageViews } from '../../focus/page'
import type { ActionId } from '../actions/types'
import type { Availability, CapabilityUnavailable, Level, Rect } from '../types'
import { MAGNET_CHOICES } from './choices'
import { DEFAULT_APPEARANCE, readAppearance, type Appearance } from '../../present/types'
import { magnetLook as themedLook, readMagnetTheme } from './presentation'
import {
  INFORMATION_TYPES, MAGNET_BOUNDS, MAGNET_SOURCE_KINDS,
  type MagnetCapability, type MagnetConfig, type MagnetConfigChange, type MagnetEnv, type MagnetId, type MagnetResult,
  type MagnetSeed, type MagnetSource, type MagnetSourceAdapter, type MagnetZone,
} from './types'

export const MAGNET_SHOW = 'magnet'

const AVAILABLE: Availability = { state: 'available' }
const ABSENT: Availability = { state: 'absent' }
const no = (code: CapabilityUnavailable['code'], message: string, retryable = false, more: Partial<CapabilityUnavailable> = {}): Availability =>
  ({ state: 'disabled', reason: { code, message, retryable, ...more } })

/* -- the source-adapter registry --------------------------------------------- */

export interface AdapterRegistry {
  register(a: MagnetSourceAdapter): void
  of(src: MagnetSource): MagnetSourceAdapter | undefined
  kinds(): string[]
}
export function createAdapters(): AdapterRegistry {
  const by = new Map<string, MagnetSourceAdapter>()
  return {
    register(a) { by.set(a.kind, a) },
    of: (src) => by.get(src.kind),
    kinds: () => [...by.keys()],
  }
}

/** The env this build runs in: reads are allowed; no connector is present;
 *  the only collection the runtime does is one-time. */
export const BUILD_ENV: MagnetEnv = { permissions: new Set(['read']), connectors: new Set(), runtime: new Set(['one-time']) }

/** A source's key: the same source in two Magnets has the same key; two
 *  sources of one Magnet never share one, which the server refuses and
 *  draftProblems says (so results, statuses and cursors are never merged). */
export const sourceKey = (s: MagnetSource): string => {
  switch (s.kind) {
    case 'brain': return 'brain:' + s.brain
    case 'conversation': return 'conversation:' + s.conversation
    case 'connector': return `connector:${s.connector}:${s.location ?? ''}`
    case 'web': return `web:${s.url ?? ''}:${s.domain ?? ''}`
    case 'other': return `other:${s.type}:${s.ref}`
    case 'agent-results': return `agent-results:${s.conversation ?? ''}:${s.runtime ?? ''}`
    case 'file': return `file:${s.collection}:${s.path ?? ''}`
    case 'database': return `database:${s.collection}:${s.table ?? ''}`
  }
}

/** Why a source cannot be read here, or null when it can. */
export function sourceReason(s: MagnetSource, env: MagnetEnv, adapters: AdapterRegistry): CapabilityUnavailable | null {
  if (s.kind === 'connector' && !env.connectors.has(s.connector))
    return { code: 'connector', message: `The connector “${s.connector}” is not connected here.`, connectorId: s.connector, sourceId: sourceKey(s), retryable: true }
  if (s.kind === 'web') return { code: 'source', message: 'Reading the web is not in this build.', sourceId: sourceKey(s), retryable: false }
  if (!adapters.of(s)) return { code: 'source', message: `Nothing in this build reads a ${s.kind} source yet.`, sourceId: sourceKey(s), retryable: false }
  if (!env.permissions.has('read')) return { code: 'permission', message: 'You may not read this source.', permission: 'read', sourceId: sourceKey(s), retryable: false }
  return null
}

/** What the configured, readable sources can do together. */
export function capabilitiesOfConfig(c: MagnetConfig, env: MagnetEnv, adapters: AdapterRegistry): Set<MagnetCapability> {
  const out = new Set<MagnetCapability>()
  for (const s of c.sources) {
    const a = adapters.of(s)
    if (!a || sourceReason(s, env, adapters)) continue
    for (const k of a.capabilities(s, env)) out.add(k)
  }
  return out
}

/* -- tabs ------------------------------------------------------------------- */

export type TabId = (typeof INFORMATION_TYPES)[number] | 'search'
export interface Tab { id: TabId; label: string; availability: Availability }
export const TAB_LABEL: Record<TabId, string> = {
  post: 'Posts', file: 'Files', image: 'Images', attachment: 'Attachments', link: 'Links', form: 'Forms', other: 'Other', search: 'Search',
}

/** The compact pane's tabs (§3.10.1). */
export function tabsOf(c: MagnetConfig, env: MagnetEnv, adapters: AdapterRegistry): Tab[] {
  const can = capabilitiesOfConfig(c, env, adapters)
  const chosen = c.selection.informationTypes
  const types = chosen?.length ? INFORMATION_TYPES.filter((t) => chosen.includes(t)) : INFORMATION_TYPES.filter((t) => can.has(t))
  const tabs: Tab[] = types.map((t) => ({
    id: t, label: TAB_LABEL[t],
    availability: can.has(t) ? AVAILABLE : no('source', `None of this Magnet’s sources can show ${TAB_LABEL[t].toLowerCase()} in this build.`),
  }))
  if (can.has('search')) tabs.push({ id: 'search', label: TAB_LABEL.search, availability: AVAILABLE })
  return tabs
}

/** What a tab with nothing to show says, and whether reading on can find more.
 *  It says it is empty only when its source has nothing left to read and every
 *  source answered; otherwise it says what was read. */
const TAB_WORD: Partial<Record<TabId, string>> = { file: 'files', image: 'images or media', attachment: 'attachments', link: 'links', form: 'forms', other: 'other items' }
export function tabEmpty(tab: TabId, l: { loading: boolean; more?: boolean; statuses?: ReadonlyArray<{ status: string; reason?: string }>; results: readonly MagnetResult[]; postsInAll?: number }): { words: string; more: boolean } {
  if (l.loading) return { words: 'Reading…', more: false }
  const what = tab === 'post' ? 'posts' : TAB_WORD[tab] ?? 'items'
  const more = !!l.more
  const stuck = l.statuses?.find((s) => s.status !== 'ok')
  if (stuck) return { words: `No ${what} in what could be read; there may be more. ${stuck.reason ?? ''}`.trim(), more }
  if (!more) return { words: tab === 'post' ? 'No posts yet.' : `No ${what} here.`, more }
  const read = l.results.filter((r) => r.kind === 'post').length
  return { words: read && l.postsInAll ? `No ${what} in the newest ${read} of ${l.postsInAll} posts, all that has been read so far.` : `No ${what} in what has been read so far; there is more to read.`, more }
}

/* -- one capability set for every Magnet --------------------------------------- */

/** Every Magnet reports exactly these; only their Availability differs. */
export const MAGNET_ACTIONS = ['magnet.tab', 'search', 'peek', 'openAsWorkspace', 'magnet.configure', 'magnet.reconfigure', 'magnet.activate', 'magnet.setUpActivation', 'magnet.conversation'] as const satisfies readonly ActionId[]

export const MAGNET_CONFIG_GONE = 'This workspace refers to a Magnet configuration that is missing.'

/** The one conversation a Magnet reads, when that is all it reads. */
export function conversationOf(c: MagnetConfig | undefined): string | null {
  const s = c?.sources
  return s && s.length === 1 && s[0].kind === 'conversation' ? s[0].conversation : null
}

export function magnetAvailability(c: MagnetConfig, env: MagnetEnv, adapters: AdapterRegistry = noAdapters): ReadonlyMap<ActionId, Availability> {
  const can = capabilitiesOfConfig(c, env, adapters)
  const tabs = tabsOf(c, env, adapters)
  const blocked = c.sources.map((s) => sourceReason(s, env, adapters)).find((r) => r)
  const out = new Map<ActionId, Availability>()
  out.set('magnet.tab', tabs.some((t) => t.availability.state === 'available') ? AVAILABLE
    : blocked ? { state: 'disabled', reason: blocked } : no('source', 'Nothing this Magnet selects can be shown here.'))
  out.set('search', can.has('search') ? AVAILABLE
    : blocked ? { state: 'disabled', reason: blocked } : no('source', 'None of this Magnet’s sources can be searched.'))
  /* its summary card is what it holds now: there whether or not it can read */
  out.set('peek', AVAILABLE)
  out.set('openAsWorkspace', conversationOf(c) ? AVAILABLE
    : no('scope', 'Only a Magnet of one conversation has a source conversation to open. Put in a workspace is the way to a workspace.'))
  /* the same Magnet changes what it collects: every facet is editable; what a
     value asks that this build does not run is said beside it (notRunning) */
  out.set('magnet.configure', env.permissions.has('read') ? AVAILABLE : no('permission', 'You may not change what this Magnet reads.', false, { permission: 'read' }))
  out.set('magnet.reconfigure', env.permissions.has('read') ? AVAILABLE : no('permission', 'You may not change what this Magnet reads.', false, { permission: 'read' }))
  /* judged from the definition alone: why not is what the server's door would say */
  const refusal = activationRefusal(c)
  out.set('magnet.activate', refusal ? no('state', refusal.message) : AVAILABLE)
  out.set('magnet.setUpActivation', env.permissions.has('read') && setUpChange(c) ? AVAILABLE : ABSENT)
  /* its own, distinct from any source: asked for, and made only on that press */
  out.set('magnet.conversation', AVAILABLE)
  return out
}
const noAdapters = createAdapters()

/** What selection asks beyond information types: kept with the Magnet, said,
 *  and not applied by any source in this build. */
export const SELECTION_KEPT = 'Kept with the Magnet; the conversation source does not filter by it in this build. Search finds words within what it collects.'
const selectionExtras = (c: MagnetConfig): string[] => {
  const s = c.selection
  return [
    s.criteria?.trim() ? 'criteria' : '', s.phrases?.length ? 'phrases' : '', s.topics?.length ? 'topics' : '',
    s.filters && Object.keys(s.filters).length ? 'filters' : '',
  ].filter(Boolean)
}
export const DATES_KEPT = 'Its dates apply where this server reads Magnets itself. On a server that does not, they are kept with the Magnet and not applied.'

/** The server's words for each line of "What can run", by its code: `_CANNOT_RUN` in
 *  mentis/magnet/activation.py, held to refusals.json. */
export const ACTIVATION_REFUSALS = {
  'schema-version-not-supported': 'this Magnet definition is from a later schema than this build reads, so it is not run',
  'activation-not-supported': 'this build activates a Magnet only by hand: its activation must be manual',
  'collection-not-supported': 'this build collects only once per activation: its collection must be one-time',
  'synthesis-not-supported': 'this build synthesizes nothing by itself: its synthesis must be manual',
  'notifications-not-supported': 'this build sends no notifications: every notification must be off',
  'pipeline-not-supported': 'this build runs one operation, extract, and nothing else',
  'extract-mode-not-supported': 'this build\'s extract materializes one M1 page: its options may say only that mode',
  'ai-not-supported': 'this build\'s extract uses no AI: its ai mode must be none',
  'output-not-supported': 'this build\'s extract records the page: its outputs may say only records',
  'destination-not-supported': 'this build\'s extract goes to the Magnet\'s own Conversation and nowhere else',
  'no-readable-source': 'no source produced a useful result: none could be read, or what could be read gave no results. Nothing was recorded',
} as const
export type ActivationRefusalCode = keyof typeof ACTIVATION_REFUSALS

/** The first line of "What can run" this definition fails, or null: `_cannot_run_code` in
 *  mentis/magnet/activation.py, in its order and held to the same rows
 *  (tests/fixtures/magnet-conformance/activation/definitions.json). This is the definition's half
 *  only: nothing a server sends says whether it has the processor, and without the front's rule its
 *  door answers ProcessorUnavailable to a definition this takes. */
export function activationRefusal(c: MagnetConfig): { code: ActivationRefusalCode; message: string } | null {
  const { schema_version: version } = c as { schema_version?: unknown }
  const operations = c.processing?.operations ?? []
  const code: ActivationRefusalCode | null =
    version != null && version !== 1 ? 'schema-version-not-supported'
    : c.activation?.mode !== 'manual' ? 'activation-not-supported'
    : c.collection.mode !== 'one-time' ? 'collection-not-supported'
    : c.synthesis.mode !== 'manual' ? 'synthesis-not-supported'
    : c.notifications.newItems || c.notifications.changes || c.notifications.failures ? 'notifications-not-supported'
    : operations.length !== 1 || operations[0].op !== 'extract' ? 'pipeline-not-supported'
    : !['{}', '{"mode":"m1-page"}'].includes(JSON.stringify(operations[0].options ?? {})) ? 'extract-mode-not-supported'
    : c.ai != null && JSON.stringify(c.ai) !== '{"mode":"none"}' ? 'ai-not-supported'
    : c.outputs != null && JSON.stringify(c.outputs) !== '["records"]' ? 'output-not-supported'
    : c.destinations != null && JSON.stringify(c.destinations) !== '[{"kind":"magnet-conversation"}]' ? 'destination-not-supported'
    : !c.sources.some((s) => s.kind === 'conversation') ? 'no-readable-source'
    : null
  return code && { code, message: ACTIVATION_REFUSALS[code] }
}

/** Whether a manual activation takes this definition. */
export const activationRuns = (c: MagnetConfig): boolean => activationRefusal(c) === null

/** What "Set up manual activation" would send: what a definition lacks of manual activation with
 *  one extract step, or null where it lacks neither or has asked for something else, which is its
 *  own to change in the editor and is never overwritten here. */
export function setUpChange(c: MagnetConfig): Pick<MagnetConfigChange, 'activation' | 'processing'> | null {
  const operations = c.processing?.operations ?? []
  const asksElse = (c.activation && c.activation.mode !== 'manual') || operations.length > 1 || (operations.length === 1 && operations[0].op !== 'extract')
  if (asksElse) return null
  const change: Pick<MagnetConfigChange, 'activation' | 'processing'> = {
    ...(c.activation ? {} : { activation: { mode: 'manual' as const } }),
    ...(operations.length ? {} : { processing: { operations: [{ op: 'extract' as const }] } }),
  }
  return Object.keys(change).length ? change : null
}

/** Whether a value of these facets is one a manual activation runs: said beside each in the editor.
 *  The rest are kept and not run; why, for what a definition now says, is `notRunning`'s. */
export const VALUE_RUNS = {
  activation: (v: string) => v === 'manual',
  operation: (v: string) => v === 'extract',
  ai: (v: string) => v === 'none',
  output: (v: string) => v === 'records',
  destination: (v: string) => v === 'magnet-conversation',
} as const
export const valueWord = (facet: keyof typeof VALUE_RUNS, v: string): string =>
  `${v}: ${VALUE_RUNS[facet](v) ? 'runs' : 'kept, not run'}`

/** What M1's facets ask: kept and said, but for what a manual activation of a lone `extract` runs. */
const moreNotRunning = (c: MagnetConfig): Array<{ facet: string; reason: CapabilityUnavailable }> => {
  const off = (facet: string, message: string) => ({ facet, reason: { code: 'runtime' as const, message, retryable: false } })
  const theme = readMagnetTheme(c)
  const runs = activationRuns(c)
  return [
    ...(c.activation && c.activation.mode !== 'manual' ? [off('activation', `${c.activation.mode[0].toUpperCase()}${c.activation.mode.slice(1)} activation is kept but not run in this build; it reads when shown.`)] : []),
    ...(!runs && c.processing?.operations.length ? [off('processing', 'Its processing steps are kept in order. Only a manual activation of a lone extract step runs, and only where nothing else this Magnet asks rules it out: it materializes one bounded M1 page in this Magnet’s own Conversation. Schedules, events, continuous collection and other operations do not run.')] : []),
    ...(c.ai && c.ai.mode !== 'none' ? [off('ai', `AI participation (${c.ai.mode}) is kept but not run in this build.`)] : []),
    ...(!runs && c.outputs?.length ? [off('outputs', 'Its outputs are kept. A manual activation of extract records its page; nothing else produces an output in this build.')] : []),
    ...(!runs && c.destinations?.length ? [off('destinations', 'Its destinations are kept. A manual activation of extract writes to this Magnet’s own Conversation; nothing is delivered anywhere else in this build.')] : []),
    /* a theme it knows is drawn (magnetLook); one it does not is kept and said */
    ...(theme.state === 'unavailable' ? [off('presentation', theme.reason)] : []),
  ]
}

/** What a config asks for that this build keeps but never runs, each with
 *  its reason. Nothing here is ever executed: no collector, synthesis,
 *  notification delivery, connector or web call exists in this build. */
export function notRunning(c: MagnetConfig, env: MagnetEnv, adapters: AdapterRegistry): Array<{ facet: string; reason: CapabilityUnavailable }> {
  const out: Array<{ facet: string; reason: CapabilityUnavailable }> = []
  for (const s of c.sources) {
    const r = sourceReason(s, env, adapters)
    if (r) out.push({ facet: 'source', reason: r })
  }
  const extras = selectionExtras(c)
  if (extras.length)
    out.push({ facet: 'selection', reason: { code: 'source', message: `Its ${extras.join(', ')}: ${SELECTION_KEPT}`, retryable: false } })
  if (c.selection.dates?.after || c.selection.dates?.before)
    out.push({ facet: 'selection', reason: { code: 'source', message: DATES_KEPT, retryable: false } })
  if (c.collection.mode === 'paused')
    out.push({ facet: 'collection', reason: { code: 'runtime', message: 'Paused: kept as asked. Nothing collects in the background in this build, so it still reads once, when shown.', retryable: false } })
  else if (!env.runtime.has(c.collection.mode))
    out.push({ facet: 'collection', reason: { code: 'runtime', message: `${c.collection.mode[0].toUpperCase()}${c.collection.mode.slice(1)} collection is kept but not run in this build; it collects once, when shown.`, retryable: false } })
  if (c.synthesis.mode !== 'manual')
    out.push({ facet: 'synthesis', reason: { code: 'runtime', message: 'Summaries are kept as asked but never generated in this build.', retryable: false } })
  const n = c.notifications
  if (n.newItems || n.changes || n.failures)
    out.push({ facet: 'notifications', reason: { code: 'runtime', message: 'Notification interests are kept, but nothing delivers notifications in this build.', retryable: false } })
  out.push(...moreNotRunning(c))
  return out
}

/* -- the zone and the workspace ------------------------------------------------ */

/** A new Magnet's zone, before the server names it (the id is the config's). */
export const newMagnetZone = (name: string): Omit<MagnetZone, 'id' | 'options'> =>
  ({ type: 'zone', show: 'magnet', name, level: MAGNET_CHOICES.newLevel })

export const isMagnetZone = (z: Pick<Zone, 'show'>): boolean => z.show === MAGNET_SHOW
export const magnetIdOf = (z: Zone): MagnetId | null =>
  z.show === MAGNET_SHOW && typeof z.options?.magnet === 'string' && z.options.magnet.startsWith('mag-') ? z.options.magnet as MagnetId : null

/** Every Magnet zone in the workspace, on every page, wherever it is. */
export function magnetZones(a: Arr): Zone[] {
  const out: Zone[] = []
  const walk = (n: Arr['tree']) => { if (n.type === 'zone') { if (n.show === MAGNET_SHOW) out.push(n) } else n.kids.forEach(walk) }
  for (const { view } of allPageViews(a)) {
    walk(view.tree)
    for (const f of view.focus?.floats ?? []) if (f.zone.show === MAGNET_SHOW) out.push(f.zone)
    for (const z of view.setAside ?? []) if (z.show === MAGNET_SHOW) out.push(z)
  }
  return [...new Map(out.map((z) => [z.id, z])).values()]
}

/** The Magnet this workspace already has that reads only `conversation`. */
export function existingFor(a: Arr, conversation: string): MagnetId | null {
  for (const z of magnetZones(a)) {
    const id = magnetIdOf(z)
    if (id && conversationOf(a.magnets?.[id]) === conversation) return id
  }
  return null
}

/** The letter a disc shows. */
export const initialOf = (title: string): string => (title.match(/[\p{L}\p{N}]/u)?.[0] ?? '•').toUpperCase()

/* -- the disc's cues: what it reads, what it holds, how it is ------------------- */

export type InformationType = (typeof INFORMATION_TYPES)[number]
/** The disc's source badge: the one kind it reads, or several. */
export type SourceGlyph = MagnetSource['kind'] | 'mixed'
export const glyphOf = (c: MagnetConfig): SourceGlyph => {
  const kinds = [...new Set(c.sources.map((s) => s.kind))]
  return kinds.length === 1 ? kinds[0] : 'mixed'
}
export const SOURCE_WORD: Record<SourceGlyph, string> = {
  conversation: 'a conversation', brain: 'a Brain', connector: 'a connector', web: 'the web', other: 'another source', mixed: 'several sources',
  'agent-results': 'agent results', file: 'files', database: 'a database',
}
/** What each type is called where it is counted (the summary, the orbit). */
export const CATEGORY_LABEL: Record<InformationType, string> = {
  post: 'Posts', file: 'Files', image: 'Images & media', attachment: 'Attachments', link: 'Links', form: 'Forms', other: 'Other',
}

/** How many of each type a Magnet holds, in the fixed order, types with none
 *  left out. Posts are the source's own total where it says one (the results
 *  hold its newest page), never a count of a copy. */
export type Holding = Array<{ type: InformationType; count: number }>
export function holdingOf(results: readonly MagnetResult[], postsTotal?: number, countPostsUnread = false): Holding {
  const n = new Map<string, number>()
  for (const r of results) n.set(r.kind, (n.get(r.kind) ?? 0) + 1)
  /* `countPostsUnread`: a disc read no page, so its posts are its count, or nothing */
  if (postsTotal != null && (n.has('post') || countPostsUnread)) n.set('post', Math.max(postsTotal, n.get('post') ?? 0))
  return INFORMATION_TYPES.filter((t) => (n.get(t) ?? 0) > 0).map((t) => ({ type: t, count: n.get(t)! }))
}
const ONE_OF: Record<InformationType, string> = {
  post: 'post', file: 'file', image: 'image or media item', attachment: 'attachment', link: 'link', form: 'form', other: 'other item',
}
/** "1 post", "2 posts": what a count of a type is called, in words. */
export const countWords = (n: number, type: InformationType): string =>
  `${n} ${n === 1 ? ONE_OF[type] : CATEGORY_LABEL[type].toLowerCase()}`
export const holdingWords = (h: Holding): string =>
  h.length ? h.map((x) => countWords(x.count, x.type)).join(', ') : 'nothing yet'

/** What a disc is called: its zone's own name where it has one, so two Magnets
 *  of one source read apart, else its source's. A Magnet placed by its reference
 *  was named with that reference until it knew better: no name to show anyone. */
export function magnetTitle(zoneName: string | undefined, sourceName: string | undefined): string {
  const own = zoneName?.trim()
  return own && !own.startsWith('mag-') && own !== 'Magnet' ? own : sourceName ?? own ?? 'Magnet'
}

/** The orbit: one arc per type it holds, sized by its share, with a gap
 *  between arcs. Fractions of the circle, from the top, clockwise. Types with
 *  few items still get an arc that can be seen. */
export function orbitArcs(h: Holding, gap = 0.035, least = 0.06): Array<{ type: InformationType; from: number; to: number }> {
  if (!h.length) return []
  if (h.length === 1) return [{ type: h[0].type, from: 0, to: 1 }]
  const room = 1 - gap * h.length
  /* the least first, to every kind its share would leave smaller; the rest by share */
  const small = new Set<number>()
  let size: number[] = []
  for (;;) {
    const free = room - least * small.size
    const share = h.reduce((s, x, i) => s + (small.has(i) ? 0 : x.count), 0)
    size = h.map((x, i) => (small.has(i) ? least : free * x.count / share))
    const under = size.map((s, i) => (!small.has(i) && s < least ? i : -1)).filter((i) => i >= 0)
    if (!under.length) break
    under.forEach((i) => small.add(i))
  }
  let at = gap / 2
  return h.map((x, i) => {
    const from = at, to = at + size[i]
    at = to + gap
    return { type: x.type, from, to }
  })
}

/** How a Magnet is now, for the disc's ring, badge and words. One state at a
 *  time, the most pressing first; `limited` (it asks for something this build
 *  keeps but does not run) is said beside it. */
export type MagnetState = 'missing' | 'error' | 'reading' | 'paused' | 'new' | 'quiet'
export interface MagnetStatus { state: MagnetState; words: string; limited: boolean }
export function magnetStatus(c: MagnetConfig | undefined, s: { unread: number; loading: boolean; held: number; error?: string; off: number; newer?: boolean }): MagnetStatus {
  const limited = s.off > 0
  if (!c) return { state: 'missing', words: MAGNET_CONFIG_GONE, limited: false }
  if (s.error) return { state: 'error', words: `It could not be read: ${s.error}`, limited }
  if (s.loading && !s.held) return { state: 'reading', words: 'Reading what it collects…', limited }
  if (c.collection.mode === 'paused') return { state: 'paused', words: 'Collection is paused', limited }
  if (s.unread > 0) return { state: 'new', words: `${s.unread} new since you last opened it`, limited }
  /* a disc reads no posts: it knows there is something new, not how much */
  if (s.newer) return { state: 'new', words: 'Something new since you last opened it', limited }
  return { state: 'quiet', words: 'Nothing new since you last opened it', limited }
}

/* -- the configuration editor's rules ------------------------------------------- */

/** Every source kind the editor offers, each with whether this build reads it. */
export function sourceChoices(env: MagnetEnv, adapters: AdapterRegistry): Array<{ kind: MagnetSource['kind']; label: string; availability: Availability }> {
  const label: Record<MagnetSource['kind'], string> = { conversation: 'Conversation', brain: 'Brain', connector: 'Connector', web: 'Web', other: 'Other', 'agent-results': 'Agent results', file: 'File', database: 'Database' }
  return MAGNET_SOURCE_KINDS.map((kind) => {
    let availability: Availability = AVAILABLE
    if (kind === 'web') availability = no('source', 'Reading the web is not in this build.')
    else if (kind === 'connector') availability = env.connectors.size ? AVAILABLE : no('connector', 'No connector is connected here; connectors are not in this build.', true)
    else if (!adapters.kinds().includes(kind)) availability = no('source', `Nothing in this build reads a ${label[kind].toLowerCase()} source yet.`)
    else if (!env.permissions.has('read')) availability = no('permission', 'You may not read this source.', false, { permission: 'read' })
    return { kind, label: label[kind], availability }
  })
}

/* a Magnet's own Conversation is asked for, and no reconfigure ever names it */
const facets = ['sources', 'selection', 'collection', 'synthesis', 'notifications', 'presentation', 'activation', 'processing', 'ai', 'outputs', 'destinations'] as const
/** The facets `after` changes of `before`, and nothing else: what reconfigure sends.
 *  A facet it took out goes as null, which is how a reconfigure hears it. */
export function changeOf(before: MagnetConfig, after: MagnetSeed): MagnetConfigChange {
  const out: Record<string, unknown> = {}
  for (const f of facets) if (JSON.stringify(before[f]) !== JSON.stringify(after[f])) out[f] = after[f] ?? null
  return out as MagnetConfigChange
}

type OptionalFacet = 'activation' | 'processing' | 'ai' | 'outputs' | 'destinations'
/** A draft with one of M1's optional facets set, or, given undefined, taken out: absent, never
 *  empty, because an empty list asks for something a missing one doesn't. */
export function withFacet<K extends OptionalFacet>(d: MagnetSeed, facet: K, value: MagnetSeed[K] | undefined): MagnetSeed {
  const { [facet]: _gone, ...rest } = d
  return (value === undefined ? rest : { ...rest, [facet]: value }) as unknown as MagnetSeed
}

/** Empty values left out, so a cleared field is not kept as an empty one. */
export function tidySelection(s: MagnetSeed['selection']): MagnetSeed['selection'] {
  const out: MagnetSeed['selection'] = {}
  if (s.criteria?.trim()) out.criteria = s.criteria.trim()
  const phrases = (s.phrases ?? []).map((p) => p.trim()).filter(Boolean)
  if (phrases.length) out.phrases = phrases
  if (s.topics?.length) out.topics = s.topics
  if (s.informationTypes) out.informationTypes = INFORMATION_TYPES.filter((t) => s.informationTypes!.includes(t))
  const dates = { ...(s.dates?.after ? { after: s.dates.after } : {}), ...(s.dates?.before ? { before: s.dates.before } : {}) }
  if (dates.after || dates.before) out.dates = dates
  if (s.filters && Object.keys(s.filters).length) out.filters = s.filters
  return out
}

/** What is wrong with a draft before it is sent, in the server's bounds. */
export function draftProblems(d: MagnetSeed): string[] {
  const out: string[] = []
  const b = MAGNET_BOUNDS
  if (d.sources.length < b.sources.min) out.push('A Magnet reads at least one source.')
  if (d.sources.length > b.sources.max) out.push(`A Magnet reads at most ${b.sources.max} sources.`)
  if (new Set(d.sources.map(sourceKey)).size < d.sources.length) out.push('A Magnet reads each source once.')
  if (d.sources.some((s) => s.kind === 'conversation' && !s.conversation)) out.push('Choose the conversation it reads.')
  if (d.sources.some((s) => (s.kind === 'file' || s.kind === 'database') && !s.collection)) out.push('Name the collection it reads.')
  if (d.selection.informationTypes && !d.selection.informationTypes.length) out.push('Choose at least one type of information to collect.')
  if ((d.selection.phrases?.length ?? 0) > b.phrases) out.push(`At most ${b.phrases} phrases.`)
  if (d.selection.phrases?.some((p) => p.length > b.phraseChars)) out.push(`A phrase is at most ${b.phraseChars} characters.`)
  const iso = /^\d{4}-\d{2}-\d{2}/
  for (const k of ['after', 'before'] as const) {
    const v = d.selection.dates?.[k]
    if (v && !iso.test(v)) out.push(`The “${k}” date is not a date.`)
  }
  if ((d.collection.mode === 'scheduled' && !d.collection.schedule) || (d.synthesis.mode === 'scheduled' && !d.synthesis.schedule))
    out.push('A schedule needs its timing (five cron fields, or a duration such as PT1H).')
  if (d.activation?.mode === 'scheduled' && !d.activation.schedule?.trim()) out.push('A scheduled activation needs its timing (five cron fields, or a duration such as PT1H).')
  if (d.activation?.mode === 'event' && !d.activation.event?.trim()) out.push('An event activation needs the event it would wait for.')
  if (d.activation?.mode === 'condition' && !d.activation.condition?.trim()) out.push('A condition activation needs its condition.')
  if ((d.processing?.operations.length ?? 0) > b.operations) out.push(`At most ${b.operations} processing steps.`)
  return out
}

/** Where a Magnet window is drawn, wide, at `level`: the disc at the
 *  window's corner; the slide-out (compact) at the window's rectangle within
 *  its bounds; standard and expanded fill it. */
export function drawnMagnetRect(level: Level, r: Rect): Rect {
  if (level === 'icon') return { x: r.x, y: r.y, w: MAGNET_CHOICES.disc, h: MAGNET_CHOICES.disc }
  if (level === 'compact') return { x: r.x, y: r.y, ...slideSize(r) }
  return r
}

/** A slide-out's size: `want` within its bounds and, given, within `room`
 *  (what is left of the windows' layer right of and below its corner). The
 *  least wins over the room, so it never draws smaller than it can be used. */
export function slideSize(want: { w: number; h: number }, room?: { w: number; h: number }): { w: number; h: number } {
  const { min, max } = MAGNET_CHOICES.slide
  const fit = (v: number, lo: number, hi: number, left?: number) => Math.round(Math.max(lo, Math.min(hi, left ?? hi, v)))
  return { w: fit(want.w, min.w, max.w, room?.w), h: fit(want.h, min.h, max.h, room?.h) }
}

/** Whether a slide-out drawn at `size` is enlarged: past its normal size on
 *  either side, so Restore size is what its size control offers. */
export const slideEnlarged = (size: { w: number; h: number }): boolean =>
  size.w > MAGNET_CHOICES.slide.normal.w + 8 || size.h > MAGNET_CHOICES.slide.normal.h + 8

/** A Magnet window's look: its own (`own`, focus/model.ts lookOf: kept in its
 *  options as a thread window keeps its), property by property, over its
 *  theme where `config` has one this build knows (presentation.ts); with none,
 *  over its slide-out's opaque look for reading (choices.ts slideLook), else
 *  the place's, as any window's. One reading for the window that draws it
 *  (Floats.tsx, NarrowFloats.tsx) and its Look column. */
export function magnetLook(own: unknown, place: unknown, slide: boolean, config?: unknown): Appearance {
  return themedLook(config, own, slide ? MAGNET_CHOICES.slideLook : readAppearance(place, DEFAULT_APPEARANCE)).appearance
}
