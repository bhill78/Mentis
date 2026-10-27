import { post, read, type Id } from '../../api'

/* ------------------------------------------------------------------------ *
 * MANAGE SOURCES: WHERE YOU ARE INSIDE IT, AND WHAT IT ASKS THE SERVER.
 *
 * The address is `#/brain/sources/<path>` (U1). The path is held exactly as
 * written -- each segment percent-encoded -- so an object key that holds `/`
 * stays one segment. Reading it is this file's job and nobody else's:
 *
 *   ''                          the overview
 *   add                         choose a connector
 *   add/<connector>             the flow for one connector (Folder today)
 *   <col>                       a collection, Overview tab
 *   <col>/sweeps|browse|scope   its other tabs
 *   <col>/plan                  Refresh: plan again, preview, confirm
 *   <col>/o/<key>               one object, its latest observation
 *   v/<adm>                     one observation, pinned (where a reference
 *                               chip's "Open in Sources" lands)
 *   v/<adm>/compare/<adm>       two observations of one object
 *   v/<adm>/at/<offset>-<end>   one observation, scrolled to and highlighting
 *                               those bytes (a content search hit)
 *   v/<adm>/x/<extractor_id>[/at/<offset>-<end>]
 *                               one observation read through that exact
 *                               extraction (Sources C): offsets are CODE
 *                               POINTS of its text, never bytes
 *
 * Nothing here is recorded. Navigation is UI state (nav.ts).
 * ------------------------------------------------------------------------ */

export type SourcesRoute =
  | { at: 'overview' }
  | { at: 'add' }
  | { at: 'flow'; connector: string }
  | { at: 'collection'; col: Id; tab: Tab }
  | { at: 'object'; col: Id; key: string }
  | { at: 'observation'; ref: Id; span?: Span; extraction?: string }
  | { at: 'compare'; a: Id; b: Id }

/** A range a content search hit cites: bytes in the stored file, or --
 *  for a hit in an extraction -- code points of that extraction's text.
 *  Which one is said by the route that carries it (`extraction`). */
export interface Span {
  offset: number
  end: number
}

export type Tab = 'overview' | 'sweeps' | 'browse' | 'scope' | 'plan'

const TABS: Tab[] = ['overview', 'sweeps', 'browse', 'scope', 'plan']

const dec = (s: string) => {
  try {
    return decodeURIComponent(s)
  } catch {
    return s
  }
}

export function readRoute(path: string): SourcesRoute {
  const bits = path.split('/').filter(Boolean)
  if (bits.length === 0) return { at: 'overview' }
  if (bits[0] === 'add') return bits[1] ? { at: 'flow', connector: dec(bits[1]) } : { at: 'add' }
  if (bits[0] === 'v' && bits[1]) {
    if (bits[2] === 'compare' && bits[3]) return { at: 'compare', a: dec(bits[1]), b: dec(bits[3]) }
    const x = bits[2] === 'x' && bits[3] ? dec(bits[3]) : undefined
    const rest = x ? bits.slice(4) : bits.slice(2)
    const m = rest[0] === 'at' ? /^(\d+)-(\d+)$/.exec(rest[1] ?? '') : null
    const base = x ? { at: 'observation' as const, ref: dec(bits[1]), extraction: x } : { at: 'observation' as const, ref: dec(bits[1]) }
    if (m && Number(m[2]) > Number(m[1])) return { ...base, span: { offset: Number(m[1]), end: Number(m[2]) } }
    return base
  }
  const col = dec(bits[0])
  if (bits[1] === 'o' && bits[2]) return { at: 'object', col, key: dec(bits.slice(2).join('/')) }
  const tab = (TABS as string[]).includes(bits[1] ?? '') ? (bits[1] as Tab) : 'overview'
  return { at: 'collection', col, tab }
}

export function writeRoute(r: SourcesRoute): string {
  const e = encodeURIComponent
  switch (r.at) {
    case 'overview':
      return ''
    case 'add':
      return 'add'
    case 'flow':
      return `add/${e(r.connector)}`
    case 'collection':
      return r.tab === 'overview' ? e(r.col) : `${e(r.col)}/${r.tab}`
    case 'object':
      return `${e(r.col)}/o/${e(r.key)}`
    case 'observation': {
      const x = r.extraction ? `/x/${e(r.extraction)}` : ''
      return r.span ? `v/${e(r.ref)}${x}/at/${r.span.offset}-${r.span.end}` : `v/${e(r.ref)}${x}`
    }
    case 'compare':
      return `v/${e(r.a)}/compare/${e(r.b)}`
  }
}

/* "OPEN IN SOURCES" FROM ANYWHERE. A reference chip in a Turn is several
   components deep; it announces where it wants to go and the shell moves
   there, with a history entry, so Back returns to the Conversation. The same
   idiom as `announceGoTo` in nav.ts. */
export const SOURCES_EVENT = 'mentis:sources'

export function openInSources(r: SourcesRoute): void {
  window.dispatchEvent(new CustomEvent<string>(SOURCES_EVENT, { detail: writeRoute(r) }))
}

/* ------------------------------ the answers ------------------------------ */

export interface ScopeField {
  name: string
  type: string
  label: string
  default?: string[] | string | number
  help?: string
  /** not a pattern list: a connector's own scope field (a Git ref, a commit
   *  window), carried as the scope's `options` */
  option?: boolean
  min?: number
  max?: number
}

/** A connector's own scope fields, by name: text or whole numbers. */
export type ScopeOptions = Record<string, string | number | Record<string, unknown>>
export interface Picker { available: boolean; why_not: string | null }

export interface Preset {
  id: string
  label: string
  include: string[] | null
  exclude: string[] | null
}

/** An evidence category (Logs, Build output): a named set of exclude
 *  patterns, off while they are excluded. Acquiring any of it newly needs a
 *  category decision in a preview. */
export interface Category {
  id: string
  label: string
  patterns: string[]
  default: 'off' | 'on'
  help: string
}

export type Choice = 'include' | 'exclude'
export type Choices = Record<string, Choice>

/** What a preview found and left out, bounded. An excluded folder is listed
 *  where the walk met it and never entered: its contents are unknown. */
export interface NotSelected {
  excluded_folders: { path: string; pattern: string; category: string | null; contents: 'unknown' }[]
  excluded_folders_total: number
  excluded_folders_truncated: boolean
  excluded_folders_by_pattern: { pattern: string; category: string | null; folders: number }[]
  excluded_folders_by_pattern_total: number
  excluded_folders_by_pattern_truncated: boolean
  excluded_folder_contents: 'unknown'
  excluded_folder_note: string
  unselected_files: { category: string | null; pattern: string | null; files: number }[]
  unselected_files_total: number
  unselected_files_truncated: boolean
}

export interface Descriptor {
  id: string
  label: string
  available: boolean
  binding: 'local-folder' | 'local-file' | 'account' | 'endpoint'
  /** Where a collection of this kind can be: `local-folder` (chosen on this
   *  machine) and/or `address` (a location elsewhere, typed). Drawn from
   *  this, never from which connector it is. */
  locations?: string[]
  scope_fields: ScopeField[]
  presets: Preset[]
  preview: 'exact' | 'bounded'
  modes: string[]
  live: string | null
  browse: string
  key: string
  summary?: string
  connect: string
  why_not?: string
  categories?: Category[]
}

export interface Scope {
  include: string[]
  exclude: string[]
  options?: ScopeOptions
  act?: Id | null
  revision?: Id | null
  declaration?: Id
  revised_by?: Id | null
  at?: number
}

export interface SweepRow {
  act: Id
  at: number
  actor: Id | null
  batch: string
  plan: string
  counts: Record<string, number>
  scope: { declaration: Id; revision: Id | null; within: string | null }
  binding: string
  binding_changed: boolean
  not_acquired: { path: string; reason: string }[]
  refused: { path: string; reason: string }[]
  unexamined: { path: string; reason: string }[]
  visible_not_selected: number | null
}

export interface Revision {
  act: Id
  at: number
  scope: { include: string[]; exclude: string[] }
  previous: { include: string[]; exclude: string[]; act: Id }
  revised_by: Id
  because: string | null
}

export interface Binding {
  bound: boolean
  binding: string | null
  state: string
  /** the address it was bound by, when it was bound by one (never a path) */
  remote?: string
}

/** Whether a descriptor's collections can be bound by a typed address. */
export const takesAddress = (d: Descriptor): boolean => (d.locations ?? [d.binding]).includes('address')

export interface CollectionView {
  collection: Id
  name: string
  connector: string
  declared_by: Id
  declared_at: number
  declaration: Id
  declared_scope: { include: string[]; exclude: string[] }
  scope: Scope
  revisions: Revision[]
  counts: {
    present: number
    absent: number
    links_to: number
    embeds: number
    held_bytes: number
    visible_not_selected: number | null
  }
  last_sweep: SweepRow | null
  sweeps: SweepRow[]
  binding: Binding
  state: string
  run: RunView | null
  /** the extraction store's progress for this collection (Sources C):
   *  derived material beside the record, never recorded */
  extraction?: { sources_with_extractor: number; by_state: Record<string, number> }
}

export interface SourcesAnswer {
  picker?: Picker
  collections: CollectionView[]
  descriptors: Descriptor[]
  note: string
}

export interface Preview {
  draft?: string
  collection: Id | null
  name: string
  plan: string
  within: string | null
  binding_changed: boolean
  can_confirm?: boolean
  sensitive_columns?: { path: string; table: string; column: string; decision: Choice | null }[]
  partial_required?: boolean
  partial_confirmed?: boolean
  capture_semantics?: string
  coverage?: Record<string, string>
  sensitive_files?: { path: string; size: number | null; size_from?: 'record'; rule: string; previously_acquired: boolean; decision: 'include' | 'exclude' | null }[]
  sensitive_decisions?: Record<string, 'include' | 'exclude'>
  categories?: {
    category: string
    label: string
    decision: Choice | null
    new_files: number
    new_bytes: number
    files: string[]
    files_truncated: boolean
    previously_acquired: number
  }[]
  category_decisions?: Choices
  category_note?: string
  not_selected?: NotSelected
  /** a Git repository at, or enclosing, the folder: an offer, never an act */
  repository?: { detected: boolean; at: 'root' | 'enclosing'; levels_up: number; offer: string; note: string } | null
  binding_note?: string
  admit: { path: string; action: string; size: number; digest: string; payload_type: string }[]
  absent: string[]
  counts: Record<string, number>
  not_acquired: { path: string; reason: string }[]
  refused: { path: string; reason: string }[]
  unexamined: { path: string; reason: string }[]
  absence_withheld: string[]
  visible_not_selected: number
  links: { links_to: number; embeds: number }
  largest: { path: string; size: number }[]
  bytes_to_retain: number
  bytes_new_to_store: number
  evidence?: {
    change_records: number; blobs: number; trees: number; new_bytes: number
    limit_disclosed: number; limit_disclosed_label: string
    withheld: { key: string; reason: string }[]
    coverage: { status: string; complete: number; partial: number
      records?: { key: string; status: string; reasons: { id: string; reason: string }[] }[] }
  }
  scope: Scope
  revising?: { from: Scope; to: Scope }
  confirm: Record<string, unknown>
  /** what the connector read at, when it reads at a point (a Git ref and
   *  the commit it named) */
  at?: { ref: string; commit: string; remote?: string }
}

export interface SweepResult {
  act: Id
  batch: string
  admitted: Id[]
  absent: string[]
  unchanged: string[]
  not_examined: string[]
  withheld: string[]
  admitted_by_action: Record<string, string[]>
  collection?: Id
}

export interface RunView {
  run: string
  key: string
  kind: 'plan' | 'preview' | 'sweep'
  state: 'running' | 'done' | 'cancelled' | 'refused' | 'failed'
  progress: { files: number; bytes: number; current: string | null }
  started_at: number
  ended_at: number | null
  result: unknown
  /** why the run ended without a result. Never `error`: an answer carrying
   *  `error` is read by `api.ts` as the route refusing. */
  failure: string | null
  failure_kind: string | null
  cancel_requested: boolean
}

export interface ObjectRow {
  ref: Id
  path: string
  key: string
  label: string
  state: string
  action: string
  digest: string | null
  size: number | null
  payload_type: string | null
  text: boolean | null
  batch: string
  admitted_at: number
}

export interface LinkRow {
  rel: 'links-to' | 'embeds'
  syntax: string
  authored: string
  resolution: string
  resolved: string | null
  resolver: string
  target: string
  target_ref?: Id
  reason?: string
  in_scope?: boolean
}

export interface LinksAnswer {
  collection: Id
  path: string
  label: string
  ref: Id | null
  state: string
  links: LinkRow[]
  linked_from: { from: string; label: string; ref: Id; rel: string; authored: string }[]
}

/** Which exact extraction a hit or a window is in (Sources C). */
export interface ExtractionId {
  extractor_id: string
  representation_digest: string
  map_digest: string
  locator_scheme: string
  status?: string
}

export interface Page {
  ref: Id
  path: string
  digest: string
  size: number
  offset: number
  end: number
  next_offset: number | null
  text?: string
  bytes_b64?: string
  encoding: string
  cite: string
  /** `codepoint` for a window of an extraction; bytes otherwise */
  unit?: 'codepoint'
  extraction?: ExtractionId
  display?: string
  scheme?: string
}

/** One place a phrase occurs in acquired text (`/api/sources/search`). */
export interface SearchHit {
  ref: Id
  collection: Id
  collection_name: string
  key: string
  label: string
  digest: string
  /** what `offset`, `end` and the excerpt count: bytes of the stored file,
   *  or code points of the extraction named in `extraction` */
  unit: 'byte' | 'codepoint'
  extraction: ExtractionId | null
  /** where in the source an extraction hit came from, for people */
  display?: string
  offset: number
  end: number
  /** the line in the stored file; null for a hit in an extraction */
  line: number | null
  snippet: string
  excerpt: { offset: number; length: number; cite: string; unit: 'byte' | 'codepoint' }
  cite: string
  match: { n: number; of: number }
  more_in_file: number
  embeds_in_excerpt: (Omit<LinkRow, 'rel' | 'resolver' | 'resolution'> & { offset: number; end: number; view?: string | null })[]
}

export interface SearchAnswer {
  q: string
  hits: SearchHit[]
  /** Every hit in the answer: the first three matches of each file. */
  hits_total: number
  /** hits_total + not_returned.beyond_per_file + not_returned.over_excerpt */
  total_matches: number
  files_with_hits: number
  not_returned: {
    beyond_per_file: number
    over_excerpt: number
    over_excerpt_files: { ref: Id; collection: Id; key: string; matches: number }[]
  }
  offset: number
  limit: number
  next_offset: number | null
  searched: { files: number; bytes: number; extractions: number; extraction_bytes: number }
  not_searched: {
    non_text: number
    by_type: Record<string, number>
    /** why, by type: no_extractor, extraction_pending, transient, empty, failed, unavailable, corrupt */
    extraction: Record<string, Record<string, number>>
    unreadable: number
    /** files that alone exceed one slice's budget: never read */
    over_slice?: number
    over_budget: number
  }
  truncated: boolean
  /** How much of the scope this search has examined (Stage F). Partial
   *  unless `complete`; `said` puts it in words. */
  coverage: SearchCoverage
  /** Pass back to search the next slice; null once the scope is complete. */
  continuation: string | null
  /** Exactly what to ask for after this answer: the next page of this
   *  slice, or the first page of the next slice; null when nothing is left. */
  next: { continuation: string | null; offset: number } | null
  slice: { n: number; continuation: string | null; budget_bytes: number }
  order: string
  note: string
}

export interface SearchCoverage {
  complete: boolean
  exhaustive: boolean
  slice: number
  total: { objects: number; bytes: number }
  examined: { objects: number; bytes: number }
  this_slice: { objects: number; bytes: number }
  remaining: { objects: number; bytes: number }
  matches_so_far: number
  said: string
}

export interface Provenance {
  ref: Id
  what: string
  collection: Id
  collection_name: string | null
  connector: string
  connector_label: string
  live: string | null
  object: string
  label: string
  action: string
  state: string
  batch: string
  digest: string | null
  size: number | null
  payload_type: string | null
  text: boolean | null
  admitted_at: number
  sweep: { act: Id; at: number; actor: Id | null } | null
  version: { n: number | null; of: number }
  latest: Id
  latest_state: string
  newer_exists: boolean
  observations: { ref: Id; state: string; action: string; admitted_at: number }[]
  /** extractions of these bytes a reader can ask for (Sources C) */
  extractions?: {
    extractor_id: string | null
    name: string
    state: string
    status?: string | null
    current: boolean
    chars?: number | null
    locator_scheme?: string | null
    why?: string
  }[]
}

/* --------------------------------- words --------------------------------- */

export function bytes(n: number | null | undefined): string {
  if (n === null || n === undefined) return '—'
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(n < 10 * 1024 ? 1 : 0)} KB`
  return `${(n / (1024 * 1024)).toFixed(1)} MB`
}

export const count = (n: number | null | undefined) => (n ?? 0).toLocaleString()

/* --------------------------------- acts ---------------------------------- */

/** Start a background run and poll it until it ends. `onProgress` sees each
 *  view while it runs. Resolves with the final view, whatever its state; a
 *  refusal to START is thrown, as every refusal from `post` is. */
export async function runToEnd(
  start: Promise<RunView>,
  onProgress: (v: RunView) => void,
): Promise<RunView> {
  let v = await start
  onProgress(v)
  while (v.state === 'running') {
    await new Promise((r) => setTimeout(r, 400))
    const got = await read<{ run: RunView | null }>(`/api/sources/${encodeURIComponent(v.key)}/run`)
    if (!got.run) break
    v = got.run
    onProgress(v)
  }
  return v
}

export const cancelRun = (key: string) =>
  post<{ cancelled: boolean }>(`/api/sources/${encodeURIComponent(key)}/run/cancel`, {})

export const reveal = (col: Id, object: string) =>
  post<{ revealed: boolean; state: string; why?: string; note?: string }>(
    `/api/sources/${encodeURIComponent(col)}/reveal`,
    { object },
  )
