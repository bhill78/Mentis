import { CLIENT_HEADERS } from '../../api'
import { BRAIN_HEADER, confirmBrain, page, refusedAsOtherBrain } from '../../brainBinding'
import { fluidFetch } from '../../fluid/http'
import type { MagnetConfig, MagnetSource } from '../../fluid/surface/magnet/types'
import { matchesBinding } from './managementApi'
import type { MagnetResource, SavedMagnet, SearchEntry, SearchSource } from './contract'
import { openOverlay } from './places'
import type { StagedSettings } from './panelDrafts'

export const sourceIdentity = (s: MagnetSource) => s.kind === 'conversation' ? `conversation:${s.conversation}`
  : s.kind === 'file' ? `file:${s.collection}:${s.path ?? ''}` : JSON.stringify(s)
export function exactFileIssue(collection: string, path: string): string | null {
  if (!/^[A-Za-z0-9_.:-]{1,80}$/.test(collection)) return 'This collection name cannot be saved by this Magnet schema (80 characters maximum).'
  if (!path.trim()) return 'Choose one file; whole-collection file reads are unavailable.'
  if (Array.from(path).length > 300) return 'This file path exceeds the Magnet limit of 300 characters.'
  if (path !== path.trim() || /[\\:*?\[\]\u0000]/.test(path) || path.split('/').some((p) => !p || p === '.' || p === '..'))
    return 'Choose one exact file path, without a directory, wildcard or traversal.'
  return null
}
export function supportsManualCollection(config: MagnetConfig): boolean {
  const operations = config.processing?.operations
  return config.activation?.mode === 'manual' && config.collection?.mode === 'one-time' && config.synthesis?.mode === 'manual'
    && !Object.values(config.notifications ?? {}).some(Boolean) && operations?.length === 1 && operations[0].op === 'extract'
    && (!operations[0].options || !Object.keys(operations[0].options).length || JSON.stringify(operations[0].options) === '{"mode":"m1-page"}')
    && (!config.ai || JSON.stringify(config.ai) === '{"mode":"none"}') && (!config.outputs || JSON.stringify(config.outputs) === '["records"]')
    && (!config.destinations || JSON.stringify(config.destinations) === '[{"kind":"magnet-conversation"}]')
}
export function collectionChange(config: MagnetConfig, sources: MagnetSource[], types: string[], after: string, before: string, manual = false) {
  // Up to 20, and none is a valid answer: a Magnet may be saved with no source
  // and told what to collect later, and the last source may be taken away
  // again. Nothing fills an empty list in.
  if (sources.length > 20) throw new Error('Choose up to 20 supported sources.')
  if (new Set(sources.map(sourceIdentity)).size !== sources.length) throw new Error('Each source can be selected once.')
  for (const s of sources) {
    if (s.kind === 'conversation') { if (!/^ent-[a-zA-Z0-9]{6,40}$/.test(s.conversation)) throw new Error('Choose an existing Conversation.') }
    else if (s.kind === 'file') { const issue = exactFileIssue(s.collection, s.path ?? ''); if (issue) throw new Error(issue) }
    else throw new Error(`${s.kind} collection is unavailable in this milestone.`)
  }
  if (types.some((t) => !['post', 'file', 'image', 'attachment'].includes(t))) throw new Error('Choose supported Conversation information types.')
  if (!types.length && sources.some((s) => s.kind === 'conversation')) throw new Error('Choose supported Conversation information types.')
  for (const date of [after, before]) if (date) {
    const day = /^(\d{4}-\d{2}-\d{2})(?:$|T)/.exec(date)?.[1]
    if (!day || !Number.isFinite(Date.parse(date)) || new Date(day + 'T00:00:00Z').toISOString().slice(0, 10) !== day) throw new Error('Choose a valid date or ISO timestamp.')
  }
  if (after && before && Date.parse(after) > Date.parse(before)) throw new Error('The end date is before the start date.')
  return { sources, selection: { ...config.selection, informationTypes: types as NonNullable<MagnetConfig['selection']['informationTypes']>, dates: { ...(after ? { after } : {}), ...(before ? { before } : {}) } },
    ...(manual ? { collection: { mode: 'one-time' as const }, synthesis: { mode: 'manual' as const },
      activation: { mode: 'manual' as const }, processing: { operations: [{ op: 'extract' as const }] },
      notifications: { newItems: false, changes: false, failures: false }, ai: { mode: 'none' as const },
      outputs: ['records' as const], destinations: [{ kind: 'magnet-conversation' as const }] } : {}) }
}
export async function configurationRead(path: string, signal?: AbortSignal): Promise<any> {
  const r = await fetch(path, { headers: CLIENT_HEADERS, signal, cache: 'no-store' })
  const v = await r.json().catch(() => null)
  if (!r.ok || !v || v.error) throw new Error(v?.error ?? `Configuration information unavailable (${r.status}).`)
  return v
}
export async function holdingArrangement(arrangement: string, magnet: string, signal?: AbortSignal) {
  const v = await configurationRead(`/fluid/api/arrangements/${encodeURIComponent(arrangement)}`, signal)
  if (!v.layout?.magnets?.[magnet]) throw new Error('This arrangement does not hold the Magnet. Choose an existing holding arrangement; attach the Magnet first if none holds it.')
  return v
}

/** THE PLAIN WORDS FOR A PLACE THAT KEEPS NOTHING: `mentis.magnet.schema.NO_SAVED_PLACE`
 *  is the server's own refusal, and this is what the panel says before sending. */
export const NO_SAVED_PLACE = 'Nothing is saved for this location yet, so a configuration cannot be sent through it. Choose another saved location.'
/** A saved location a configuration may be addressed through: whether it also
 *  happens to hold the Magnet, which the save does not require. */
export type ConfigurationPlace = { arrangement: string; holds: boolean }
/** Whether `arrangement` is a saved location at all, and whether it holds the
 *  Magnet. Reads only. A place with nothing saved throws `NO_SAVED_PLACE`: the
 *  operation key is kept there, so that one thing it must have. */
export async function savedPlace(arrangement: string, magnet: string, signal?: AbortSignal): Promise<ConfigurationPlace> {
  const v = await configurationRead(`/fluid/api/arrangements/${encodeURIComponent(arrangement)}`, signal)
  if (!v.layout) throw new Error(NO_SAVED_PLACE)
  return { arrangement, holds: !!v.layout?.magnets?.[magnet] }
}

/** WHICH SAVED LOCATION THE CONFIGURATION IS SENT THROUGH, found rather than asked.
 *
 *  The definition belongs to no arrangement (`mentis/magnet/__init__.py`), and a
 *  Magnet's identity and configuration do not depend on where it is displayed
 *  (request §4). Only the reconfigure door is addressed through a saved location,
 *  which keeps its operation key; that location need not hold the Magnet, and
 *  carrying the save attaches nothing to it (`arrangements.reconfigure_magnet`).
 *
 *  So this looks, read-only: Brain Home first, then each saved workspace. A
 *  location that holds the Magnet is preferred, because its own projection is
 *  then kept current in the same write; failing that, the first saved location
 *  there is carries the save. Null only when no saved location exists at all,
 *  which the panel says rather than guesses. */
export async function findConfigurationLocation(magnet: string, candidates: string[], signal?: AbortSignal): Promise<ConfigurationPlace | null> {
  let carries: ConfigurationPlace | null = null
  for (const key of candidates) {
    if (signal?.aborted) return null
    try {
      const place = await savedPlace(key, magnet, signal)
      if (place.holds) return place
      carries ??= place
    } catch { /* Not this one; a read failure is not an answer about the others. */ }
  }
  return carries
}
/** The holding location alone, kept for what already asks only that. */
export async function findHoldingArrangement(magnet: string, candidates: string[], signal?: AbortSignal): Promise<string | null> {
  for (const key of candidates) {
    if (signal?.aborted) return null
    try {
      await holdingArrangement(key, magnet, signal)
      return key
    } catch { /* Not this one; a read failure is not an answer about the others. */ }
  }
  return null
}

/** THE CANONICAL FORM AND DIGEST OF A VALIDATED DEFINITION (revised contract
 *  adm-c5c73679ac1e §3), the client's half of `mentis.magnet.snapshot`.
 *
 *  The digest covers the ENTIRE validated durable definition -- the name, every
 *  source and its configuration, selection and its filters, collection and
 *  synthesis behaviour, and every optional facet -- with exactly two fields left
 *  out: `conversation`, the nonauthoritative own-Conversation mirror the record's
 *  claim overrides, and `schema_version`, the file's own. Both are carried
 *  beside a snapshot, never inside its digest.
 *
 *  Object keys are sorted recursively, array order is as given, the encoding is
 *  UTF-8 with no whitespace and no BOM, Unicode is literal, and only the escaping
 *  JSON requires is used. Numbers in this schema are integers: an integral value
 *  is written as an integer and anything else is refused rather than digested
 *  differently in each half. `tests/fixtures/magnet-definition-digest/vectors.json`
 *  holds both halves to the same bytes. */
export const DEFINITION_UNDIGESTED = ['conversation', 'schema_version'] as const
export const DEFINITION_INTEGER_MOST = Number.MAX_SAFE_INTEGER
const DEFINITION_KEY = /^[A-Za-z_][A-Za-z0-9_]{0,39}$/
const canonicalValue = (v: unknown, where: string): unknown => {
  if (v === null || typeof v === 'boolean') return v
  if (typeof v === 'string') {
    for (const c of v) { const n = c.codePointAt(0)!; if (n >= 0xd800 && n <= 0xdfff) throw new Error(`${where}: a lone surrogate cannot be encoded`) }
    return v
  }
  if (typeof v === 'number') {
    if (!Number.isInteger(v)) throw new Error(`${where}: ${v} is not an integer, and this schema's numbers are integers; it cannot be digested identically in both halves`)
    if (Math.abs(v) > DEFINITION_INTEGER_MOST) throw new Error(`${where}: ${v} is outside the integers this schema carries (±${DEFINITION_INTEGER_MOST})`)
    return v === 0 ? 0 : v
  }
  if (Array.isArray(v)) return v.map((x, i) => canonicalValue(x, `${where}[${i}]`))
  if (typeof v === 'object') {
    const out: Record<string, unknown> = {}
    for (const k of Object.keys(v as object).sort()) {
      if (!DEFINITION_KEY.test(k)) throw new Error(`${where}: '${k}' is not a key a definition can hold`)
      out[k] = canonicalValue((v as Record<string, unknown>)[k], `${where}.${k}`)
    }
    return out
  }
  throw new Error(`${where}: ${typeof v} is not a value a definition can hold`)
}
/** The definition the digest covers: all of it but `DEFINITION_UNDIGESTED`. */
export function durableDefinition(config: MagnetConfig): Record<string, unknown> {
  return Object.fromEntries(Object.entries(config as unknown as Record<string, unknown>)
    .filter(([k]) => !(DEFINITION_UNDIGESTED as readonly string[]).includes(k)))
}
export function canonicalDefinition(config: MagnetConfig): string {
  return JSON.stringify(canonicalValue(durableDefinition(config), 'definition'))
}
/** `configuration_digest`: 64 lowercase hexadecimal characters. */
export async function configurationDigest(config: MagnetConfig): Promise<string> {
  const bytes = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(canonicalDefinition(config)))
  return Array.from(new Uint8Array(bytes), (b) => b.toString(16).padStart(2, '0')).join('')
}

/** What a Magnet may be called: `mentis.magnet.schema.MAX_NAME`. */
export const MAGNET_NAME_MOST = 80
export function nameIssue(name: string): string | null {
  if (!name.trim()) return 'Give the Magnet a name, or leave the saved name as it is.'
  if (Array.from(name).length > MAGNET_NAME_MOST) return `A Magnet name is at most ${MAGNET_NAME_MOST} characters.`
  // eslint-disable-next-line no-control-regex
  if (/[\u0000-\u001f\u007f]/.test(name)) return 'A Magnet name cannot carry control characters.'
  return null
}
/** The `identity` facet a rename replaces, whole, through the same reconfigure
 *  door the collection facets use. The name lives in the definition, so it is the
 *  Magnet's wherever it is drawn and whatever arrangement the save went through. */
export const identityChange = (name: string) => ({ identity: { name: name.trim() } })
/** What this Magnet is called now: its own name where it has one, else the name
 *  the catalogue worked out (`mentis/fluid/__init__.py` `name_of`), which the
 *  saved row carries. One rule, so the card, the list and Settings agree. */
export function magnetName(config: MagnetConfig | undefined, fallback: string): string {
  const own = (config as { identity?: { name?: unknown } } | undefined)?.identity?.name
  return typeof own === 'string' && own.trim() ? own.trim() : fallback
}
/** What a Collect with nothing configured means, in plain words. It is a no-op,
 *  not a whole-Brain read: collection walks the configured sources, and there are
 *  none, so nothing is read and nothing is recorded. */
export const NO_SOURCE_TO_COLLECT = 'No sources are configured yet, so there is nothing to collect. Add a Conversation or a file first; nothing else is read in their place.'
/** One reconfigure's facets: the collection facets, the Magnet's own name, or
 *  both committed together by one Save. Every facet named here is one the
 *  existing reconfigure door already replaces whole. */
export type ConfigurationChange =
  Partial<ReturnType<typeof collectionChange>> & Partial<ReturnType<typeof identityChange>>
export async function saveCollection(at: { brainKey: string; arrangement: string; magnet: string; change: ConfigurationChange; op: string }) {
  if (await confirmBrain() !== true || !matchesBinding(at.brainKey)) throw new Error('This page cannot confirm its Brain. The configuration has not been sent.')
  // The location must be a saved one, because the operation key is kept there.
  // It need not hold the Magnet: the change is the definition's.
  await savedPlace(at.arrangement, at.magnet)
  if (!matchesBinding(at.brainKey)) throw new Error('The Brain changed before saving. Reload to continue.')
  const r = await fluidFetch(`/fluid/api/arrangements/${encodeURIComponent(at.arrangement)}/magnets/${encodeURIComponent(at.magnet)}/reconfigure`, {
    method: 'POST', headers: { ...CLIENT_HEADERS, [BRAIN_HEADER]: page.bound()!, 'Content-Type': 'application/json' }, body: JSON.stringify({ change: at.change, op: at.op }),
  })
  const v = await r.json().catch(() => null)
  if (refusedAsOtherBrain(r.status, v)) page.move()
  if (!r.ok || !v?.magnet || v.magnet.id !== at.magnet) {
    const error = new Error(v?.error ?? `Save outcome is unknown (${r.status}). Retry the unchanged save.`)
    Object.assign(error, { refused: r.status >= 400 && r.status < 500 && !!v?.refused })
    throw error
  }
  if (!matchesBinding(at.brainKey)) throw new Error('The Brain changed while saving. No response was applied to this page.')
  return v.magnet as MagnetConfig
}

/** The one universal source model, honestly (§5-H5-4). Supported means this
 *  build collects it when Collect now is pressed; proposed means the kind exists
 *  in the Magnet schema but nothing here collects it, and choosing it is not an
 *  interaction this panel offers. The refusals are the server's own:
 *  `mentis/magnet/activation.py` `FILE_CHOICE` and the per-kind refusals in
 *  `crates/mentis-ops/src/magnet.rs`. */
export const SUPPORTED_SOURCES = [
  { kind: 'conversation', words: 'Conversations recorded in this Brain, by post capture — posts and their file or image attachments.' },
  { kind: 'file', words: 'Plain text files Mentis already holds, chosen one exact path at a time.' },
] as const
export const PROPOSED_SOURCES = [
  { kind: 'brain', words: 'Topics' }, { kind: 'web', words: 'Web pages' },
  { kind: 'web', words: 'Web searches' }, { kind: 'database', words: 'Databases' },
  { kind: 'other', words: 'Repositories' }, { kind: 'connector', words: 'Connected services' },
] as const
export const PROPOSED_REASON = 'Proposed only, and not interactive here: the Magnet schema names these kinds, but this build has no adapter for them and the server refuses collection from them. An existing connector does not enable a Magnet adapter.'
export const SUPPORTED_REASON = 'Collect from Conversations and from plain text files Mentis already holds. Opening or saving never collects. No folder is scanned or refreshed.'
/** The three near-identical paragraphs the panel used to stack under its date
 *  fields, said once. Nothing was dropped: individual post selection, schedules,
 *  automatic collection and the relevance and semantic filters are each still
 *  named, and so is what happens to the saved modes. */
export const UNSUPPORTED_REASON = 'Individual post selection, schedules, automatic collection, and relevance and semantic filters are unsupported. The saved collection and processing modes are kept unless you choose manual collection.'
/** The manual-collection switch, as a label and the sentence under it, instead
 *  of one forty-word label. Both halves say exactly what the one label said. */
export const MANUAL_COLLECTION = 'Collect only when I press Collect now'
export const MANUAL_COLLECTION_MEANS = 'One extraction at each press, manual synthesis, no automatic notifications and no agent processing. This replaces the saved collection and processing modes.'

/** THE DAY A DATE LIMIT FALLS ON, for a date input to show.
 *
 *  `collectionChange` accepts a plain `YYYY-MM-DD` or a full ISO timestamp, and
 *  the panel's fields used to be free text because of the second form. A date
 *  input shows days, so this is the day a stored limit falls on, and '' for a
 *  limit that is unset (or, defensively, for one no day can be read from --
 *  the picker then shows empty rather than a misread date). */
export const dayOf = (v: string): string => /^(\d{4}-\d{2}-\d{2})/.exec(v ?? '')?.[1] ?? ''
/** The stored limit after a date input is set to `day`.
 *
 *  A stored limit may carry a time of day that no date input can show. So while
 *  its day is unchanged the stored value is kept EXACTLY as it is, times and
 *  all; only a genuine change of day replaces it, and then with the plain day
 *  the person picked. Clearing the input clears the limit. */
export const withDay = (previous: string, day: string): string =>
  !day ? '' : dayOf(previous) === day ? previous : day

/** Item 3: the first failing rule wins, in the approved wording, and nothing is
 *  committed. Deeper rules (identity, duplication, the 20-source bound, date
 *  validity) stay in `collectionChange`, which the save path still runs.
 *
 *  NO SOURCE IS NOT A FAULT. A Magnet is an idea first: it may be saved with no
 *  configured source, and the last one may be removed again. What that means
 *  for collection is said plainly where Collect is (`NO_SOURCE_TO_COLLECT`),
 *  not by refusing to save the configuration. */
export function collectionIssue(staged: StagedSettings): string | null {
  if (staged.sources.some((s) => s.kind === 'conversation') && !staged.types.length) return 'Choose a Conversation content type.'
  if (staged.after && staged.before && Date.parse(staged.after) > Date.parse(staged.before)) return 'After date must be before the before date.'
  return null
}

/** What the committed configuration actually says, as plain lines. The settings
 *  overlay shows these and `settingsSource` indexes them, so one wording serves
 *  both and the search cannot describe a setting the panel does not. */
export function configurationFacts(config: MagnetConfig): string[] {
  const types = config.selection?.informationTypes ?? []
  const dates = config.selection?.dates ?? {}
  const other = Object.entries(config.selection ?? {}).filter(([k]) => !['informationTypes', 'dates'].includes(k))
  const own = (config as { identity?: { name?: unknown } }).identity?.name
  return [
    `Name: ${typeof own === 'string' && own.trim() ? `${own.trim()} (this Magnet's own, independent of where it is shown)` : 'taken from where it is shown; give it one of its own in Settings'}`,
    `Configured sources: ${config.sources.length ? config.sources.map(sourceIdentity).join(' · ') : 'none yet — ordinary conversation still works, and nothing else is read in their place'}`,
    `Selected Conversation content types: ${types.length ? types.join(', ') : 'none'}`,
    `Dates: ${dates.after || dates.before ? `${dates.after || 'any'} to ${dates.before || 'any'}` : 'no date limit'}`,
    `Collection: ${config.collection?.mode ?? 'not configured'} · synthesis: ${config.synthesis?.mode ?? 'not configured'} · activation: ${config.activation?.mode ?? 'not configured'}`,
    `Manual collection supported by these saved modes: ${supportsManualCollection(config) ? 'yes' : 'no'}`,
    ...other.map(([k, v]) => `Saved but not applied — ${k}: ${JSON.stringify(v)}`),
  ]
}

/** H5's second contribution to the universal index (§4). The committed
 *  configuration and the supported/proposed wording are all in hand, so there
 *  is nothing left for a `complete()` to reach. */
export function settingsSource(resource: MagnetResource): SearchSource {
  const open = () => openOverlay(resource, 'settings')
  return {
    entries(): SearchEntry[] {
      const saved: SavedMagnet = resource.saved
      const config = saved.config
      const rows: SearchEntry[] = [{ key: 'settings:magnet', kind: 'Settings', title: 'This Magnet', text: `${saved.name} · ${saved.id}`, open }]
      if (config) {
        rows.push(...configurationFacts(config).map((text, i) => ({ key: `settings:fact:${i}`, kind: 'Settings' as const, title: 'Collection configuration', text, open })))
      } else if (saved.reason) {
        rows.push({ key: 'settings:unavailable', kind: 'Settings', title: 'Collection configuration', text: saved.reason, open })
      }
      rows.push(...SUPPORTED_SOURCES.map((s) => ({ key: `settings:supported:${s.words}`, kind: 'Settings' as const, title: `Supported source: ${s.kind}`, text: s.words, open })))
      rows.push(...PROPOSED_SOURCES.map((s) => ({ key: `settings:proposed:${s.words}`, kind: 'Settings' as const, title: `Proposed source: ${s.words}`, text: `${s.words} — ${PROPOSED_REASON}`, open })))
      rows.push({ key: 'settings:supported-reason', kind: 'Settings', title: 'How collection runs', text: SUPPORTED_REASON, open })
      return rows
    },
    queryDependent: false,
  }
}
