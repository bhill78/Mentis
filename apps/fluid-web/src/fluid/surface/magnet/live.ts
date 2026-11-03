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
 * the pages of the sources that stayed and reads only the new ones. */

import type { MagnetConfig, MagnetEnv, MagnetLive, MagnetResult, MagnetSource, MagnetSummary } from './types'
import { type AdapterRegistry, sourceKey, sourceReason, tabsOf } from './model'

/** What the results of `c` depend on. */
export const revisionOf = (c: MagnetConfig): string => JSON.stringify({ sources: c.sources.map(sourceKey), selection: c.selection })
const selectionOf = (c: MagnetConfig): string => JSON.stringify(c.selection)

interface SourcePage { results: MagnetResult[]; next?: string }
interface Held {
  selection: string
  bySource: Map<string, SourcePage>
  summaries: Map<string, MagnetSummary>
  searches: Map<string, MagnetResult[]>
}

export interface LiveCache {
  /** read what `c` shows, from the held pages where they are still good */
  load(c: MagnetConfig, env: MagnetEnv): Promise<MagnetLive>
  /** the next page of every source that has one */
  more(c: MagnetConfig, env: MagnetEnv): Promise<MagnetLive>
  /** search every source that searches; held per Magnet and query */
  search(c: MagnetConfig, q: string, env: MagnetEnv): Promise<MagnetResult[]>
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
      h = { selection: selectionOf(c), bySource: new Map(), summaries: new Map(), searches: new Map() }
      held.set(c.id, h)
    }
    /* sources gone: their pages go; sources that stayed keep theirs */
    const keys = new Set(c.sources.map(sourceKey))
    for (const k of [...h.bySource.keys()]) if (!keys.has(k)) h.bySource.delete(k)
    for (const k of [...h.summaries.keys()]) if (!keys.has(k)) h.summaries.delete(k)
    return h
  }

  const readable = (c: MagnetConfig, env: MagnetEnv): MagnetSource[] => c.sources.filter((s) => !sourceReason(s, env, adapters))

  const live = (c: MagnetConfig, h: Held, env: MagnetEnv): MagnetLive => ({
    config: c,
    summaries: c.sources.flatMap((source) => { const summary = h.summaries.get(sourceKey(source)); return summary ? [{ source, summary }] : [] }),
    results: c.sources.flatMap((s) => h.bySource.get(sourceKey(s))?.results ?? []),
    tabs: tabsOf(c, env, adapters).map((t) => t.id),
  })

  return {
    async load(c, env) {
      const h = heldFor(c)
      await Promise.all(readable(c, env).map(async (s) => {
        const k = sourceKey(s)
        const a = adapters.of(s)!
        const [page, summary] = await Promise.all([
          h.bySource.has(k) ? null : a.fetch(s, c.selection),
          h.summaries.has(k) ? null : a.summary(s),
        ])
        if (page) h.bySource.set(k, page)
        if (summary) h.summaries.set(k, summary)
      }))
      return live(c, h, env)
    },
    async more(c, env) {
      const h = heldFor(c)
      await Promise.all(readable(c, env).map(async (s) => {
        const k = sourceKey(s)
        const had = h.bySource.get(k)
        if (!had?.next) return
        const got = await adapters.of(s)!.fetch(s, c.selection, had.next)
        h.bySource.set(k, { results: [...had.results, ...got.results], ...(got.next ? { next: got.next } : {}) })
      }))
      return live(c, h, env)
    },
    async search(c, q, env) {
      const h = heldFor(c)
      const query = q.trim()
      if (!query) return []
      const had = h.searches.get(query)
      if (had) return had
      const pages = await Promise.all(readable(c, env).map((s) => {
        const a = adapters.of(s)!
        return a.capabilities(s, env).has('search') ? a.search(s, query) : Promise.resolve({ results: [] as MagnetResult[] })
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

