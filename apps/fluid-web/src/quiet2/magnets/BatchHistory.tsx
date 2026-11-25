/** Earlier collection history, and its contribution to the universal index.
 *
 *  H5 owns where this is rendered (the Settings overlay); H3 owns the component
 *  and its `batchSource`. Selecting an earlier collection never collects and
 *  never reads a live source: it reads another immutable, already-recorded
 *  collection.
 *
 *  `batchSource.complete()` walks `collection/history?limit=20&cursor=` to
 *  exhaustion, so the index lists *every* earlier collection and not just the
 *  first twenty (§4, §5-H3-6). The *contents* of an unselected collection are
 *  not indexed: it is an immutable alternative to the one displayed, and
 *  selecting it is what searches it (§5-H4-8). */
import { useEffect, useRef, useState } from 'react'
import type { MagnetResource, SearchEntry, SearchSource } from './contract'
import { configurationRead } from './configuration'

export interface Batch { post: string; artifact: { ref: string; digest: string; size: number }; at: number; state: string }

/** What this Magnet's batch history has actually been read to, so `entries()`
 *  can offer it synchronously without claiming more than was read. */
const known = new WeakMap<MagnetResource, Batch[]>()
export const knownBatches = (resource: MagnetResource): Batch[] => known.get(resource) ?? []

const historyPath = (resource: MagnetResource, cursor?: string) => {
  const params = new URLSearchParams({ limit: '20' })
  if (cursor) params.set('cursor', cursor)
  return `/fluid/api/magnets/${encodeURIComponent(resource.saved.id)}/collection/history?${params}`
}
const batchesOf = (v: any, resource: MagnetResource): { batches: Batch[]; next: string | null } => {
  if (v.magnet !== resource.saved.id || !Array.isArray(v.batches)) throw new Error('The collection history did not identify this Magnet.')
  return { batches: v.batches as Batch[], next: typeof v.next === 'string' && v.next ? v.next : null }
}
const remember = (resource: MagnetResource, rows: Batch[]) => {
  const out = new Map<string, Batch>((known.get(resource) ?? []).map((b) => [b.artifact.ref, b]))
  for (const b of rows) out.set(b.artifact.ref, b)
  known.set(resource, [...out.values()])
}

export const batchLabel = (b: Batch) => `Collected ${new Date(b.at * 1000).toLocaleString()} · ${b.state}`
const entryOf = (resource: MagnetResource, b: Batch): SearchEntry => ({
  key: `batch:${b.artifact.ref}`, kind: 'Batches', title: batchLabel(b),
  text: [b.artifact.ref, b.artifact.digest, b.post, b.state, `${b.artifact.size} bytes`, new Date(b.at * 1000).toLocaleString()].join(' '),
  // Opening an earlier collection selects it. Rule 1 then searches it in full.
  open: () => { void resource.selectBatch?.(b.artifact) },
})

/** Every earlier collection, enumerated to exhaustion with a no-advance
 *  guard, so a server that repeats its cursor stops the walk instead of looping. */
export function batchSource(resource: MagnetResource): SearchSource {
  let bound: string | null = null
  return {
    queryDependent: false,
    entries: () => knownBatches(resource).map((b) => entryOf(resource, b)),
    async complete(_query: string, signal?: AbortSignal): Promise<SearchEntry[]> {
      bound = null
      const rows: Batch[] = []
      const seen = new Set<string>()
      let cursor: string | undefined
      try {
        for (;;) {
          const got = batchesOf(await configurationRead(historyPath(resource, cursor), signal), resource)
          rows.push(...got.batches)
          if (!got.next) break
          if (seen.has(got.next)) { bound = 'Earlier collection history stopped being listed: the server repeated its cursor. Some earlier history is not in these results.'; break }
          seen.add(got.next); cursor = got.next
        }
      } catch (e) {
        bound = `Earlier collection history could not be listed in full: ${(e as Error).message}`
      }
      remember(resource, rows)
      return rows.map((b) => entryOf(resource, b))
    },
    bound: () => bound,
  }
}

export default function BatchHistory({ resource }: { resource: MagnetResource }) {
  const [rows, setRows] = useState<Batch[]>(() => knownBatches(resource)), [next, setNext] = useState<string | null>(null)
  const [error, setError] = useState(''), [busy, setBusy] = useState(false)
  const alive = useRef(true), generation = useRef(0)
  const load = async (cursor?: string) => {
    const mine = ++generation.current; setBusy(true)
    try {
      const got = batchesOf(await configurationRead(historyPath(resource, cursor)), resource)
      remember(resource, got.batches)
      if (alive.current && mine === generation.current) { setRows((old) => cursor ? [...old, ...got.batches] : got.batches); setNext(got.next); setError('') }
    } catch (e) { if (alive.current && mine === generation.current) setError((e as Error).message) }
    finally { if (alive.current && mine === generation.current) setBusy(false) }
  }
  useEffect(() => { alive.current = true; void load(); return () => { alive.current = false; generation.current++ } }, [resource])
  const choose = async (batch: Batch | null) => {
    setBusy(true)
    try { await resource.selectBatch?.(batch?.artifact ?? null) }
    catch (e) { if (alive.current) setError((e as Error).message) }
    finally { if (alive.current) setBusy(false) }
  }
  /** Which collection is on screen now, so the list says where the reader is
   *  rather than offering a row that is already what they are looking at. The
   *  snapshot is read, never a request. */
  const shown = resource.snapshot().activation?.artifact.ref ?? null
  const chosen = resource.snapshot().batchSelection?.ref ?? null
  /* EARLIER COLLECTIONS, in the approved design's language. This is rendered in
     the Settings overlay, behind the `history` disclosure H5 keeps there, so it
     is already one press away from the resting surface; what changes here is
     that it reads as the same product as the rebuilt surfaces -- the heading
     block of `04-browse.png`, its rows as `mgd-item`, its one explanation as a
     subtle line rather than a paragraph above the list. Every row, the way back
     to the latest collection and the walk through earlier pages are unchanged,
     and selecting one still reads an already-recorded collection and never a
     live source. */
  return <section aria-label="Collection history">
    <div className="mgd-row mgd-spread q2-magnet-place-head">
      <div className="mgd-grow">
        <div className="mgd-eyebrow">Collection</div>
        <h3 className="mgd-h3">Earlier collections{rows.length ? <span className="mgd-subtle"> {rows.length}</span> : null}</h3>
      </div>
      <button type="button" className="mgd-link mgd-small" disabled={busy || !chosen} onClick={() => void choose(null)}>Latest collection →</button>
    </div>
    <p className="mgd-subtle">Each keeps its original captured content. Selecting one never collects or refreshes its sources.</p>
    {rows.map((b) => <div className="mgd-item mgd-row mgd-spread" key={b.artifact.ref} aria-current={b.artifact.ref === shown ? 'true' : undefined}>
      <button type="button" className="mgd-link mgd-small mgd-grow" disabled={busy || b.artifact.ref === shown} onClick={() => void choose(b)}>{batchLabel(b)}</button>
      <small className="mgd-subtle">{b.artifact.ref === shown ? 'Showing this one' : `${b.artifact.size.toLocaleString()} bytes`}</small>
    </div>)}
    {next && <button type="button" className="mgd-button mgd-secondary" disabled={busy} onClick={() => void load(next)}>Earlier collections</button>}
    {busy && <p className="mgd-subtle" role="status">Reading collection history…</p>}
    {error && <p className="mgd-subtle" role="status">{error}</p>}
  </section>
}
