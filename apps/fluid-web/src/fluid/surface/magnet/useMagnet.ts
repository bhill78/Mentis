/* useMagnet (plan adm-b848fa881c8d §3.10.1; part P7): what a Magnet shows,
 * keyed by its id and the revision of what its results depend on, read
 * through the adapter registry (runtime.ts) and kept fresh by the store's
 * own notices for its sources. Its config is the workspace's (the
 * arrangement's `magnets`, which only the Magnet routes write). */

import { useEffect, useRef, useState } from 'react'
import { store } from '../../store'
import { useArr } from '../../workspace/place'
import type { MagnetConfig, MagnetId, MagnetLive, MagnetResult, UseMagnetFn } from './types'
import { BUILD_ENV, sourceKey } from './model'
import { revisionOf } from './live'
import { live, storeKeysOf } from './runtime'

type Got = { live: MagnetLive | null; loading: boolean; error?: string }

export const useMagnet: UseMagnetFn = (configOrId, opts) => {
  const arr = useArr()
  const config: MagnetConfig | undefined = typeof configOrId === 'string' ? arr.magnets?.[configOrId] : configOrId
  if (!config) throw new Error(`no Magnet configuration ${String(configOrId)}`)
  const rev = revisionOf(config)
  const [tick, setTick] = useState(0)
  const [got, setGot] = useState<Got>(() => ({ live: live.peek(config, BUILD_ENV), loading: true }))
  /* the store heard a source change: read that source again */
  useEffect(() => {
    const offs = config.sources.flatMap((s) => storeKeysOf(s as { kind: string; conversation?: string }).map((k) =>
      store.subscribe(k, () => { live.stale(sourceKey(s)); setTick((t) => t + 1) })))
    return () => offs.forEach((off) => off())
  }, [config.id, rev])
  const summaryOnly = !!opts?.summaryOnly
  /* a hover's page; each new number is another read */
  const glance = opts?.glance ?? 0
  useEffect(() => {
    let on = true
    /* leaving ends the read: it stops on the server too, and its place goes back */
    const control = new AbortController()
    setGot((g) => ({ ...g, loading: true }))
    live.load(config, BUILD_ENV, { summaryOnly, ...(glance ? { glance: true } : {}), signal: control.signal }).then(
      (l) => { if (on) setGot({ live: l, loading: false }) },
      (e: Error) => { if (on) setGot((g) => ({ ...g, loading: false, error: e.message || 'It could not be read.' })) })
    return () => { on = false; control.abort() }
    /* keyed by identity and revision: a renderer-only change reads nothing */
  }, [config.id, rev, tick, summaryOnly, glance])
  const l = got.live && got.live.config.id === config.id ? got.live : null
  const statuses = l?.statuses ?? []
  /* the Magnet can't be read only if nothing it reads can: otherwise each source says for itself */
  const nothing = statuses.length > 0 && statuses.every((s) => s.status === 'unavailable') && !l?.results.length
  const error = got.error ?? (nothing ? statuses.find((s) => s.reason)?.reason : undefined)
  const readOn = (kind: string, signal?: AbortSignal) => live.readOn(config, BUILD_ENV, kind, signal).then((now) => { if (!signal?.aborted) setGot({ live: now, loading: false }) })
  return { config, summaries: l?.summaries ?? [], results: l?.results ?? [], tabs: l?.tabs ?? [], statuses, ...(l?.routed ? { routed: true } : {}), ...(l?.more ? { more: true } : {}), loading: got.loading, ...(error ? { error } : {}), readOn }
}

/** A results tab's reading on (live.ts readOn): by itself once, while the tab is
 *  shown with nothing in the pages read and its source has more; after that when
 *  asked (ReadOlder, TabEmpty). Leaving the tab ends the read. */
export function useReadOn(now: ReturnType<UseMagnetFn>, tab: string | undefined, shown: boolean): { reading: boolean; read(): void } {
  const [reading, setReading] = useState(false)
  const going = useRef<AbortController | null>(null)
  const tried = useRef(new Set<string>())
  const read = () => {
    if (!tab || tab === 'search' || going.current) return
    const control = new AbortController()
    going.current = control
    setReading(true)
    void now.readOn(tab, control.signal).catch(() => {}).finally(() => { if (going.current === control) { going.current = null; setReading(false) } })
  }
  useEffect(() => () => {
    if (tab) tried.current.delete(tab)
    going.current?.abort()
    going.current = null
    setReading(false)
  }, [tab, now.config.id])
  const empty = shown && !!tab && tab !== 'search' && !now.loading && !!now.more && !now.results.some((r) => r.kind === tab)
  useEffect(() => {
    if (!empty || tried.current.has(tab!)) return
    tried.current.add(tab!)
    read()
  }, [empty, tab])
  /* about to read counts as reading: it never first says what the newest page lacked */
  return { reading: reading || (empty && !tried.current.has(tab!)), read }
}

/** Search a Magnet's sources for `q` (debounced); held per Magnet and query. */
export function useMagnetSearch(config: MagnetConfig, q: string): { results: MagnetResult[]; searching: boolean; error?: string } {
  const [got, setGot] = useState<{ q: string; results: MagnetResult[]; searching: boolean; error?: string }>({ q: '', results: [], searching: false })
  const query = q.trim()
  useEffect(() => {
    if (!query) { setGot({ q: '', results: [], searching: false }); return }
    let on = true
    const control = new AbortController()
    setGot((g) => ({ ...g, searching: true }))
    const t = setTimeout(() => {
      live.search(config, query, BUILD_ENV, control.signal).then(
        (results) => { if (on) setGot({ q: query, results, searching: false }) },
        (e: Error) => { if (on) setGot({ q: query, results: [], searching: false, error: e.message || 'The search failed.' }) })
    }, 250)
    return () => { on = false; clearTimeout(t); control.abort() }
  }, [config.id, revisionOf(config), query])
  return { results: got.q === query ? got.results : [], searching: got.searching, ...(got.error ? { error: got.error } : {}) }
}

/* -- unread: since this browser last opened the Magnet past its disc ---------- */

const SEEN = 'mentis.fluid.magnet.seen:'
/** When this browser last opened Magnet `id` (epoch ms); first asked, now. */
export function seenAt(id: MagnetId): number {
  try {
    const v = Number(localStorage.getItem(SEEN + id))
    if (v > 0) return v
    const now = Date.now()
    localStorage.setItem(SEEN + id, String(now))
    return now
  } catch { return Date.now() }
}
export function markSeen(id: MagnetId) {
  try { localStorage.setItem(SEEN + id, String(Date.now())) } catch { /* private mode */ }
}
