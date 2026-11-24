/** H4: the one search index over everything this Magnet has collected and
 *  recorded (§5-H4 of the hybrid Magnet plan, `adm-8ba17c0776c6`).
 *
 *  The index is assembled from each view's `SearchSource` (H1's published
 *  contract): `entries()` is what that view already holds, and `complete()` owes
 *  everything else it holds, so the index is over collected information and not
 *  over whatever happened to be loaded. A query-independent source completes
 *  once per opened search overlay; the one query-dependent source asks the
 *  server with the query, debounced and cached per query string.
 *
 *  Two rules this file exists to keep:
 *
 *  1. **Nothing here invents a source.** A content type whose owning part has
 *     not landed its `SearchSource` is reported, by name and module, as not
 *     searched. It is never searched by a substitute assembled here, and no
 *     result is simulated.
 *  2. **Every sentence of the results header is derived from the index's own
 *     state** (`scopeSentences`). There is no literal that claims a complete
 *     search, so a complete claim the index cannot support is not expressible.
 *
 *  Nothing here reads a live source: `GET /fluid/api/magnets/<id>/read` is in
 *  the plan's "Nobody" row and is not called.
 */
import type {
  MagnetResource, MagnetSearchKind, MagnetSearchType, SearchEntry, SearchSource,
} from './contract'

/** How a view's `SearchSource` is obtained for one Magnet.
 *
 *  A gap in the published contract, filled here rather than in it: §4 declares
 *  `SearchSource` and says each owner exports one, but a bare `SearchSource`
 *  object cannot know which Magnet it belongs to. The assembly seam therefore
 *  takes a factory over the resource. H4 does not edit `contract.ts`. */
export type SearchSourceFactory = (resource: MagnetResource) => SearchSource

export interface MagnetSearchSource {
  /** The export named in §4's source table. */
  readonly name: string
  /** The content types this source owes the index. */
  readonly kinds: readonly MagnetSearchKind[]
  /** The part that owes it, and the module §4 says exports it. */
  readonly owner: string
  readonly module: string
  /** `null` until that part's `SearchSource` lands. Never substituted. */
  readonly make: SearchSourceFactory | null
}

/** §4's source table, in the order the index reads it.
 *
 *  Every `make` is `null` at H1's contract commit: no part has exported a
 *  `SearchSource` yet, so in this build the index holds nothing and says so for
 *  each content type. Wiring one is a single line here -- import the part's
 *  export and put it in `make` -- and nothing else in H4 changes. */
export const MAGNET_SEARCH_SOURCES: readonly MagnetSearchSource[] = [
  { name: 'summarySource', kinds: ['Summary'], owner: 'H3', module: 'Summary.tsx', make: null },
  { name: 'evidenceSource', kinds: ['Posts', 'Files'], owner: 'H3', module: 'EvidenceViews.tsx', make: null },
  { name: 'messageSource', kinds: ['Conversation'], owner: 'H2', module: 'conversation.ts', make: null },
  { name: 'perspectiveSource', kinds: ['Perspectives'], owner: 'H5', module: 'perspectives.ts', make: null },
  { name: 'settingsSource', kinds: ['Settings'], owner: 'H5', module: 'configuration.ts', make: null },
  { name: 'batchSource', kinds: ['Batches'], owner: 'H3', module: 'BatchHistory.tsx', make: null },
]

/** What the index knows about one source's completeness. `absent` is a part that
 *  has not landed its source; `idle` is a source searched as the card already
 *  held it, with no further read asked for or possible. */
export type SearchSourceState = 'absent' | 'idle' | 'running' | 'complete' | 'bounded' | 'refused'

export interface SearchSourceReport {
  name: string
  kinds: readonly MagnetSearchKind[]
  owner: string
  module: string
  state: SearchSourceState
  /** The source's own honest sentence when `complete()` could not finish. */
  bound: string | null
  /** How many entries of this source are in the index. */
  count: number
  queryDependent: boolean
}

export interface SearchIndexState {
  /** The whole index, in a stable order: a late merge appends, never inserts. */
  entries: SearchEntry[]
  reports: readonly SearchSourceReport[]
  running: boolean
  query: string
}

/** Injected so a test can settle the debounce without waiting. */
export interface SearchClock { schedule(run: () => void, ms: number): () => void }
export const realClock: SearchClock = {
  schedule(run, ms) { const t = setTimeout(run, ms); return () => clearTimeout(t) },
}
/** §4: the query-dependent source runs after typing settles, never per keystroke. */
export const DEBOUNCE_MS = 300

// ---------------------------------------------------------------- matching

export const entryHaystack = (e: SearchEntry) => `${e.title} ${e.text} ${e.kind}`.toLocaleLowerCase()
/** Case-insensitive substring over title + text + kind, with the type filter. */
export function matchesEntry(e: SearchEntry, query: string, type: MagnetSearchType): boolean {
  if (type !== 'All' && type !== e.kind) return false
  return entryHaystack(e).includes(query.trim().toLocaleLowerCase())
}
export const filterEntries = (entries: readonly SearchEntry[], query: string, type: MagnetSearchType) =>
  entries.filter((e) => matchesEntry(e, query, type))

const KINDS: readonly MagnetSearchKind[] = ['Summary', 'Posts', 'Files', 'Perspectives', 'Conversation', 'Settings', 'Batches']
export function validEntry(v: unknown): v is SearchEntry {
  const e = v as SearchEntry | null
  return !!e && typeof e === 'object' && typeof e.key === 'string' && e.key.length > 0
    && typeof e.title === 'string' && typeof e.text === 'string'
    && KINDS.includes(e.kind) && typeof e.open === 'function'
}

/** Merge groups of entries by `key`, keeping the order already shown.
 *
 *  `order` is the index's own key order and is extended in place: an entry that
 *  is already in the list stays where it is, and entries from a `complete()`
 *  that returns late are appended. That is what keeps the reader's list position
 *  when a merge arrives after they have scrolled. */
export function mergeByKey(order: string[], groups: readonly (readonly SearchEntry[])[]): SearchEntry[] {
  const byKey = new Map<string, SearchEntry>()
  for (const group of groups) for (const e of group) if (!byKey.has(e.key)) byKey.set(e.key, e)
  const out: SearchEntry[] = []
  const seen = new Set<string>()
  for (const key of order) {
    const e = byKey.get(key)
    if (e && !seen.has(key)) { out.push(e); seen.add(key) }
  }
  for (const [key, e] of byKey) if (!seen.has(key)) { out.push(e); seen.add(key); order.push(key) }
  return out
}

// ------------------------------------------------- the derived scope header

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`

/** The clause for a source that is read as it stands, without its own sentence. */
function heldClause(r: SearchSourceReport): string {
  if (r.state === 'running') return 'a complete read of this source is still running'
  if (r.state === 'bounded') return `the complete read stopped at its stated bound: ${r.bound ?? 'no reason was given'}`
  if (r.state === 'refused') return `the complete read was refused, so only what the card already held was searched: ${r.bound ?? 'no reason was given'}`
  if (r.state === 'complete') return 'searched in full'
  return 'searched as the card already held it; no further read was asked for'
}

/** One sentence per source, every number taken from the index itself. */
export function sentenceFor(r: SearchSourceReport): string {
  const kinds = r.kinds.join(' and ')
  if (r.state === 'absent') {
    return `${kinds}: not searched. ${r.module} (${r.owner}) exports no search source in this build, so no ${kinds.toLocaleLowerCase()} entry is in the index.`
  }
  switch (r.name) {
    case 'summarySource':
      return `Summary: ${plural(r.count, 'fact', 'facts')}, ${heldClause(r)}.`
    case 'evidenceSource':
      return `${plural(r.count, 'retained item', 'retained items')} in the batch shown, ${heldClause(r)}.`
    case 'messageSource':
      if (r.state === 'complete') return `The Magnet's whole own Conversation was searched: ${plural(r.count, 'matching post', 'matching posts')}.`
      if (r.state === 'refused') return `Only the Conversation pages already loaded in the card were searched (${plural(r.count, 'match', 'matches')}): ${r.bound ?? 'the search route gave no reason'}.`
      if (r.state === 'bounded') return `${plural(r.count, 'matching post', 'matching posts')} in the Magnet's own Conversation; the paged read stopped at its bound, so more matches exist: ${r.bound ?? 'no reason was given'}.`
      if (r.state === 'running') return `The Magnet's own Conversation is still being searched; ${plural(r.count, 'match', 'matches')} so far.`
      return `The Magnet's own Conversation is searched when a phrase is typed; ${plural(r.count, 'match', 'matches')} from the pages already loaded.`
    case 'perspectiveSource': {
      const held = `${plural(r.count, 'Perspective entry', 'Perspective entries')}`
      if (r.state === 'complete') return `${held}, searched including every earlier wording.`
      if (r.state === 'running') return `${held} so far; earlier wordings are still being read.`
      if (r.state === 'bounded') return `${held}; earlier wordings are not complete: ${r.bound ?? 'no reason was given'}.`
      if (r.state === 'refused') return `${held}; earlier wordings could not be read: ${r.bound ?? 'no reason was given'}.`
      return `${held}; earlier wordings are not included yet.`
    }
    case 'settingsSource':
      return `The committed configuration and its source wording, ${heldClause(r)}.`
    case 'batchSource': {
      const listed = `${plural(r.count, 'earlier batch', 'earlier batches')} listed; selecting one searches that batch in full, and the contents of a batch that is not shown are not indexed.`
      if (r.state === 'complete') return listed
      if (r.state === 'running') return `${listed} The list of earlier batches is still being read.`
      if (r.state === 'bounded') return `${listed} The list stopped at its stated bound: ${r.bound ?? 'no reason was given'}.`
      if (r.state === 'refused') return `${listed} The full list could not be read: ${r.bound ?? 'no reason was given'}.`
      return `${listed} No further batches were asked for.`
    }
    default:
      return `${kinds}: ${plural(r.count, 'entry', 'entries')}, ${heldClause(r)}.`
  }
}

export const BOUNDARY_SENTENCE =
  'This searches what this Magnet has collected and recorded, not the sources themselves; a batch’s own capture bounds are what its provenance states.'
export const LOADING_SENTENCE =
  'Still searching: a source is still being read, so this scope is not final yet.'
export const COMPLETE_SENTENCE =
  'Every source of this index was read in full for this search.'

/** True only when every source reported `complete`. An absent, idle, running,
 *  bounded or refused source makes it false, which is why `COMPLETE_SENTENCE`
 *  cannot appear over an incomplete index. */
export const searchIsComplete = (reports: readonly SearchSourceReport[]) =>
  reports.length > 0 && reports.every((r) => r.state === 'complete')

/** The results header, derived. Loading first, then one sentence per source,
 *  then the complete claim only if it holds, then the boundary. */
export function scopeSentences(reports: readonly SearchSourceReport[]): string[] {
  const out: string[] = []
  if (reports.some((r) => r.state === 'running')) out.push(LOADING_SENTENCE)
  for (const r of reports) out.push(sentenceFor(r))
  if (searchIsComplete(reports)) out.push(COMPLETE_SENTENCE)
  out.push(BOUNDARY_SENTENCE)
  return out
}

// ------------------------------------------------------------- the index

export interface SearchIndex {
  snapshot(): SearchIndexState
  subscribe(fn: () => void): () => void
  /** A search overlay was opened. Query-independent sources complete once per
   *  opening; this is the only thing that starts them. */
  opened(query: string): void
  setQuery(query: string): void
  dispose(): void
}

interface Held {
  row: MagnetSearchSource
  source: SearchSource | null
  state: SearchSourceState
  bound: string | null
  entries: SearchEntry[]
  cache: Map<string, { entries: SearchEntry[]; state: SearchSourceState; bound: string | null }>
  control: AbortController | null
  stop: (() => void) | null
  runKey: string | null
  generation: number
}

const safeEntries = (source: SearchSource): SearchEntry[] => {
  try { const got = source.entries(); return Array.isArray(got) ? got.filter(validEntry) : [] } catch { return [] }
}
const boundOf = (source: SearchSource): string | null => {
  try { const b = source.bound?.(); return typeof b === 'string' && b.trim() ? b.trim() : null } catch { return null }
}
const dedupe = (entries: readonly SearchEntry[]): SearchEntry[] => {
  const byKey = new Map<string, SearchEntry>()
  for (const e of entries) if (!byKey.has(e.key)) byKey.set(e.key, e)
  return [...byKey.values()]
}

export function createSearchIndex(at: {
  resource: MagnetResource
  sources?: readonly MagnetSearchSource[]
  clock?: SearchClock
  debounceMs?: number
}): SearchIndex {
  const clock = at.clock ?? realClock
  const debounceMs = at.debounceMs ?? DEBOUNCE_MS
  const held: Held[] = (at.sources ?? MAGNET_SEARCH_SOURCES).map((row) => {
    let source: SearchSource | null = null
    // A source that throws on construction is absent, never substituted.
    try { source = row.make ? row.make(at.resource) : null } catch { source = null }
    return { row, source, state: source ? 'idle' : 'absent', bound: null, entries: [],
      cache: new Map(), control: null, stop: null, runKey: null, generation: 0 }
  })
  let opening = 0, query = '', disposed = false
  let order: string[] = []
  let cached: SearchIndexState | null = null
  const heard = new Set<() => void>()
  const changed = () => { cached = null; if (!disposed) heard.forEach((fn) => fn()) }
  // `entries()` is read live, so a change in the card's own state is a change
  // in the index: a just-sent message is in hand before any completion returns.
  const unsubscribe = at.resource.subscribe(changed)

  const run = (rec: Held, key: string, ask: string) => {
    const source = rec.source
    if (!source?.complete) return
    const mine = ++rec.generation
    rec.control?.abort()
    const control = new AbortController()
    rec.control = control
    rec.runKey = key
    rec.state = 'running'
    changed()
    void source.complete(ask, control.signal).then(
      (got) => {
        if (disposed || rec.generation !== mine || control.signal.aborted) return
        const entries = Array.isArray(got) ? got.filter(validEntry) : []
        const bound = boundOf(source)
        rec.entries = entries
        rec.bound = bound
        rec.state = bound ? 'bounded' : 'complete'
        rec.cache.set(key, { entries, state: rec.state, bound })
        rec.control = null
        changed()
      },
      (e: unknown) => {
        if (disposed || rec.generation !== mine || control.signal.aborted) return
        // A refusal is the source's own refusal, reported, never retried here.
        rec.entries = []
        rec.bound = boundOf(source) ?? (e instanceof Error && e.message ? e.message : 'The complete read failed.')
        rec.state = 'refused'
        rec.cache.set(key, { entries: [], state: 'refused', bound: rec.bound })
        rec.control = null
        changed()
      },
    )
  }

  const consider = () => {
    for (const rec of held) {
      const source = rec.source
      if (!source) continue
      if (!source.complete) { rec.state = 'idle'; continue }
      const dependent = source.queryDependent === true
      const key = dependent ? `q:${query.trim()}` : `open:${opening}`
      // Anything in flight or scheduled for something no longer being asked is
      // abandoned first -- including when the query returns to a cached one, so
      // a completion for the abandoned query can never merge into the index.
      if (rec.runKey !== null && rec.runKey !== key) {
        rec.stop?.(); rec.stop = null
        rec.generation += 1
        rec.control?.abort(); rec.control = null
        rec.runKey = null
      }
      const hit = rec.cache.get(key)
      if (hit) {
        rec.entries = hit.entries; rec.state = hit.state; rec.bound = hit.bound
        rec.runKey = key
        continue
      }
      // Already running or scheduled for exactly this key: never started twice.
      if (rec.state === 'running' && rec.runKey === key) continue
      if (dependent) {
        if (!query.trim()) { rec.entries = []; rec.state = 'idle'; rec.bound = null; rec.runKey = null; continue }
        rec.entries = []
        rec.state = 'running'
        rec.runKey = key
        rec.stop = clock.schedule(() => { rec.stop = null; run(rec, key, query) }, debounceMs)
      } else {
        run(rec, key, query)
      }
    }
  }

  const build = (): SearchIndexState => {
    const groups: SearchEntry[][] = []
    const reports: SearchSourceReport[] = []
    for (const rec of held) {
      const merged = rec.source ? dedupe([...safeEntries(rec.source), ...rec.entries]) : []
      groups.push(merged)
      reports.push({ name: rec.row.name, kinds: rec.row.kinds, owner: rec.row.owner, module: rec.row.module,
        state: rec.state, bound: rec.bound, count: merged.length,
        queryDependent: rec.source?.queryDependent === true })
    }
    const entries = mergeByKey(order, groups)
    return { entries, reports, running: reports.some((r) => r.state === 'running'), query }
  }

  return {
    snapshot() { return (cached ??= build()) },
    subscribe(fn) { if (!disposed) heard.add(fn); return () => { heard.delete(fn) } },
    opened(q) {
      if (disposed) return
      opening += 1
      query = typeof q === 'string' ? q : ''
      order = []
      consider()
      changed()
    },
    setQuery(q) {
      if (disposed) return
      const next = typeof q === 'string' ? q : ''
      if (next === query) return
      query = next
      order = []
      consider()
      changed()
    },
    dispose() {
      if (disposed) return
      disposed = true
      unsubscribe()
      for (const rec of held) { rec.control?.abort(); rec.stop?.() }
      heard.clear()
    },
  }
}
