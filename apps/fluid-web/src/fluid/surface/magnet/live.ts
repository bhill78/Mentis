/* WHAT A MAGNET SHOWS NOW (plan adm-b848fa881c8d §3.10.1; part P7).
 *
 * useMagnet's core, browser-free: each configured source dispatched to its
 * adapter, the pages merged with every result keeping its source, and held
 * per MAGNET (its `mag-` id) and per source -- never per conversation -- so
 * two Magnets reading the same conversation share no cursor, page or search,
 * and two sources never leak into each other's key.
 *
 * The revision is what the results depend on (sources and selection). A
 * change that leaves it alone (the renderer, notifications) reads nothing
 * again; a change of selection drops the pages; a change of sources keeps
 * the pages of the sources that stayed and reads only the new ones.
 *
 * ONE SOURCE NEVER HOLDS UP OR FAILS ANOTHER: each answers for itself, in
 * `statuses`, and what the others hold still shows. A summary read (a disc)
 * walks nothing where the server's route answers; where it doesn't, it reads
 * as it always did, through the store. An abandoned read changes nothing.
 *
 * `more` says a source holds pages not yet read, so a type with nothing in the
 * pages read may still be in those. readOn reads on for one type, a few pages at
 * a go and one page at a time (the route's own lane), so it is bounded and leaves
 * room for everything else. A page the server answers `partial` is asked again
 * before going older: "asking again gets further" (M1-contract), and its cursor
 * moves on regardless, so going on would leave its unread objects behind for
 * good. One that gets no further is passed, and its source says so from then on
 * (`gap`): it may be missing something, so it never reads as empty. */

import type { MagnetConfig, MagnetEnv, MagnetLive, MagnetLoadOpts, MagnetResult, MagnetSource, MagnetSourceStatus, MagnetSummary } from './types'
import { type AdapterRegistry, sourceKey, sourceReason, tabsOf } from './model'

/** What the results of `c` depend on. */
export const revisionOf = (c: MagnetConfig): string => JSON.stringify({ sources: c.sources.map(sourceKey), selection: c.selection })
const selectionOf = (c: MagnetConfig): string => JSON.stringify(c.selection)

/** `partial`: shown, and read again, which gets further; `at` is that page's
 *  cursor (none: the first page) and `said` what it said then. `gap`: why a page
 *  that got no further was passed. */
interface SourcePage { results: MagnetResult[]; next?: string; partial?: boolean; at?: string; said?: string; gap?: string }
/** What is held, with a page asked again: each thing once, where it first came. */
const merged = (had: readonly MagnetResult[], got: readonly MagnetResult[]): MagnetResult[] => {
  const seen = new Set(had.map((r) => `${r.kind}:${r.id}`))
  return [...had, ...got.filter((r) => !seen.has(`${r.kind}:${r.id}`))]
}
interface Held {
  selection: string
  bySource: Map<string, SourcePage>
  summaries: Map<string, MagnetSummary>
  searches: Map<string, MagnetResult[]>
  said: Map<string, { status: MagnetSourceStatus; reason?: string }>
  /** the server's route answered, whatever it said: never a reason to read the store */
  routed?: boolean
}
const isAbort = (e: unknown): boolean => (e as Error | null)?.name === 'AbortError'
/** What a read's words say of how it went. A later read says again. */
const noted = (h: Held, k: string, got: { status?: MagnetSourceStatus; reason?: string } | null, otherwise?: { status?: MagnetSourceStatus; reason?: string } | null) => {
  const worst = [got, otherwise].find((x) => x?.status && x.status !== 'ok')
  if (worst) h.said.set(k, { status: worst.status!, ...(worst.reason ? { reason: worst.reason } : {}) })
  else if (got || otherwise) h.said.set(k, { status: 'ok' })
}

/** How many pages one read-on asks for, at most, before it says what it read. */
export const READ_ON_PAGES = 5

export interface LiveCache {
  /** read what `c` shows, from the held pages where they are still good */
  load(c: MagnetConfig, env: MagnetEnv, opts?: MagnetLoadOpts): Promise<MagnetLive>
  /** the next page of every source that has one */
  more(c: MagnetConfig, env: MagnetEnv, signal?: AbortSignal): Promise<MagnetLive>
  /** read on for `kind`: until there is more of it, no page is left, a source can't
   *  answer, or READ_ON_PAGES are read */
  readOn(c: MagnetConfig, env: MagnetEnv, kind: string, signal?: AbortSignal): Promise<MagnetLive>
  /** search every source that searches; held per Magnet and query */
  search(c: MagnetConfig, q: string, env: MagnetEnv, signal?: AbortSignal): Promise<MagnetResult[]>
  /** what is held for a Magnet now, without reading */
  peek(c: MagnetConfig, env: MagnetEnv): MagnetLive | null
  /** the store heard source `key` change (a new post): its pages and
   *  searches are read again next time, in every Magnet; other sources keep theirs */
  stale(key: string): void
  /** forget a Magnet (Remove from workspace) */
  forget(id: string): void
}

export function createLive(adapters: AdapterRegistry): LiveCache {
  const held = new Map<string, Held>()

  const heldFor = (c: MagnetConfig): Held => {
    let h = held.get(c.id)
    /* a new selection: the pages no longer answer it */
    if (!h || h.selection !== selectionOf(c)) {
      h = { selection: selectionOf(c), bySource: new Map(), summaries: new Map(), searches: new Map(), said: new Map() }
      held.set(c.id, h)
    }
    /* sources gone: their pages go; sources that stayed keep theirs */
    const keys = new Set(c.sources.map(sourceKey))
    for (const k of [...h.bySource.keys()]) if (!keys.has(k)) h.bySource.delete(k)
    for (const k of [...h.summaries.keys()]) if (!keys.has(k)) h.summaries.delete(k)
    for (const k of [...h.said.keys()]) if (!keys.has(k)) h.said.delete(k)
    return h
  }

  const readable = (c: MagnetConfig, env: MagnetEnv): MagnetSource[] => c.sources.filter((s) => !sourceReason(s, env, adapters))

  const live = (c: MagnetConfig, h: Held, env: MagnetEnv): MagnetLive => ({
    config: c,
    summaries: c.sources.flatMap((source) => { const summary = h.summaries.get(sourceKey(source)); return summary ? [{ source, summary }] : [] }),
    results: c.sources.flatMap((s) => h.bySource.get(sourceKey(s))?.results ?? []),
    tabs: tabsOf(c, env, adapters).map((t) => t.id),
    ...(h.routed ? { routed: true } : {}),
    ...(readable(c, env).some((s) => { const had = h.bySource.get(sourceKey(s)); return had?.next || had?.partial }) ? { more: true } : {}),
    statuses: c.sources.flatMap((source) => {
      const off = sourceReason(source, env, adapters)
      if (off) return [{ source, status: 'unavailable' as const, reason: off.message }]
      const said = h.said.get(sourceKey(source))
      const gap = h.bySource.get(sourceKey(source))?.gap
      if (gap && (!said || said.status === 'ok')) return [{ source, status: 'partial' as const, reason: gap }]
      return said ? [{ source, ...said }] : []
    }),
  })

  return {
    async load(c, env, opts = {}) {
      const h = heldFor(c)
      const at = { magnet: c.id, ...(opts.signal ? { signal: opts.signal } : {}), ...(opts.glance ? { glance: true } : {}) }
      await Promise.all(readable(c, env).map(async (s) => {
        const k = sourceKey(s)
        const a = adapters.of(s)!
        /* only a partial FIRST page is read again here: past it, what read-on reached stays */
        const pageGood = () => { const had = h.bySource.get(k); return !!had && !(had.partial && had.at === undefined) }
        try {
          const [first, summary] = await Promise.all([
            pageGood() || opts.summaryOnly ? null : a.fetch(s, c.selection, undefined, at),
            h.summaries.has(k) ? null : a.summary(s, at),
          ])
          /* no route here: a disc reads what it always read, through the store */
          const page = first ?? (opts.summaryOnly && summary && !summary.routed && !pageGood() ? await a.fetch(s, c.selection, undefined, at) : null)
          if (page && page.status !== 'busy' && page.status !== 'unavailable') {
            h.bySource.set(k, { results: page.results, ...(page.next ? { next: page.next } : {}), ...(page.status === 'partial' ? { partial: true, ...(page.reason ? { said: page.reason } : {}) } : {}) })
          }
          if (page?.routed || summary?.routed) h.routed = true
          /* a source that couldn't say is asked again next time */
          if (summary && (summary.status ?? 'ok') === 'ok') h.summaries.set(k, summary)
          noted(h, k, page, summary)
        } catch (e) {
          if (!isAbort(e)) h.said.set(k, { status: 'unavailable', reason: (e as Error).message || 'It could not be read.' })
        }
      }))
      return live(c, h, env)
    },
    async more(c, env, signal) {
      const h = heldFor(c)
      await Promise.all(readable(c, env).map(async (s) => {
        const k = sourceKey(s)
        const had = h.bySource.get(k)
        if (!had?.next && !had?.partial) return
        const cursor = had.partial ? had.at : had.next
        try {
          const got = await adapters.of(s)!.fetch(s, c.selection, cursor, { magnet: c.id, ...(signal ? { signal } : {}) })
          /* a change was heard meanwhile (stale): its newest pages stand, not these */
          if (h.bySource.get(k) !== had) return
          noted(h, k, got)
          if (got.status === 'busy' || got.status === 'unavailable') return
          const results = merged(had.results, got.results)
          const next = got.next ? { next: got.next } : {}
          const stuck = had.partial && got.status === 'partial' && got.reason === had.said
          const gap = stuck ? got.reason ?? 'Part of it could not be read.' : had.gap
          h.bySource.set(k, { results, ...next, ...(gap ? { gap } : {}),
            ...(got.status === 'partial' && !stuck ? { partial: true, ...(cursor ? { at: cursor } : {}), ...(got.reason ? { said: got.reason } : {}) } : {}) })
        } catch (e) {
          if (!isAbort(e)) h.said.set(k, { status: 'unavailable', reason: (e as Error).message || 'It could not be read.' })
        }
      }))
      return live(c, h, env)
    },
    async readOn(c, env, kind, signal) {
      const count = (l: MagnetLive) => l.results.filter((r) => r.kind === kind).length
      let now = live(c, heldFor(c), env)
      /* each ask is one read of one page: asking a page again counts as much as a new one */
      const had = count(now)
      for (let i = 0; i < READ_ON_PAGES && now.more && count(now) === had && !signal?.aborted; i++) {
        now = await this.more(c, env, signal)
        if (now.statuses?.some((s) => s.status === 'busy' || s.status === 'unavailable')) break
      }
      return now
    },
    async search(c, q, env, signal) {
      const h = heldFor(c)
      const query = q.trim()
      if (!query) return []
      const had = h.searches.get(query)
      if (had) return had
      const pages = await Promise.all(readable(c, env).map((s) => {
        const a = adapters.of(s)!
        return a.capabilities(s, env).has('search') ? a.search(s, query, undefined, { magnet: c.id, ...(signal ? { signal } : {}) }) : Promise.resolve({ results: [] as MagnetResult[] })
      }))
      const out = pages.flatMap((p) => p.results)
      h.searches.set(query, out)
      return out
    },
    peek(c, env) {
      const h = held.get(c.id)
      return h && h.selection === selectionOf(c) ? live(c, h, env) : null
    },
    stale(key) {
      for (const h of held.values()) {
        /* its summary (activity, how many posts) is read again with its pages */
        h.summaries.delete(key)
        if (!h.bySource.has(key)) continue
        h.bySource.delete(key)
        h.searches.clear()
      }
    },
    forget(id) { held.delete(id) },
  }
}
