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
  if (!path.trim()) return 'Choose one held file; collection-wide file reads are unavailable.'
  if (Array.from(path).length > 300) return 'This held file path exceeds the Magnet limit of 300 characters.'
  if (path !== path.trim() || /[\\:*?\[\]\u0000]/.test(path) || path.split('/').some((p) => !p || p === '.' || p === '..'))
    return 'Choose an exact held file path, without a directory, wildcard or traversal.'
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
  if (!sources.length || sources.length > 20) throw new Error('Choose from one to 20 supported sources.')
  if (new Set(sources.map(sourceIdentity)).size !== sources.length) throw new Error('Each source can be selected once.')
  for (const s of sources) {
    if (s.kind === 'conversation') { if (!/^ent-[a-zA-Z0-9]{6,40}$/.test(s.conversation)) throw new Error('Choose an existing Conversation.') }
    else if (s.kind === 'file') { const issue = exactFileIssue(s.collection, s.path ?? ''); if (issue) throw new Error(issue) }
    else throw new Error(`${s.kind} collection is unavailable in this milestone.`)
  }
  if (!types.length || types.some((t) => !['post', 'file', 'image', 'attachment'].includes(t))) throw new Error('Choose supported Conversation information types.')
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
export async function saveCollection(at: { brainKey: string; arrangement: string; magnet: string; change: ReturnType<typeof collectionChange>; op: string }) {
  if (await confirmBrain() !== true || !matchesBinding(at.brainKey)) throw new Error('This page cannot confirm its Brain. The configuration has not been sent.')
  await holdingArrangement(at.arrangement, at.magnet)
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
  { kind: 'file', words: 'Exact UTF-8 text files already held by an acquired filesystem collection, chosen one exact path at a time.' },
] as const
export const PROPOSED_SOURCES = [
  { kind: 'brain', words: 'Topics' }, { kind: 'web', words: 'Web pages' },
  { kind: 'web', words: 'Web searches' }, { kind: 'database', words: 'Databases' },
  { kind: 'other', words: 'Repositories' }, { kind: 'connector', words: 'Connected services' },
] as const
export const PROPOSED_REASON = 'Proposed only, and not interactive here: the Magnet schema names these kinds, but this build has no adapter for them and the server refuses collection from them. An existing connector does not enable a Magnet adapter.'
export const SUPPORTED_REASON = 'Collect manually from Conversations and exact text files already held by Mentis. Opening or saving never collects. No folder is scanned or refreshed.'

/** Item 3: the first failing rule wins, in the approved wording, and nothing is
 *  committed. Deeper rules (identity, duplication, the 20-source bound, date
 *  validity) stay in `collectionChange`, which the save path still runs. */
export function collectionIssue(staged: StagedSettings): string | null {
  if (!staged.sources.length) return 'Choose at least one source.'
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
  return [
    `Configured sources: ${config.sources.length ? config.sources.map(sourceIdentity).join(' · ') : 'none'}`,
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
