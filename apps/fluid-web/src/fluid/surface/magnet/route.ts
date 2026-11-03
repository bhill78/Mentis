/* THE MAGNET READ ROUTE (docs/magnets/M1-contract.md): GET
 * /fluid/api/magnets/<id>/read, browser-free, its one read injected so tests
 * count every call (runtime.ts binds the real one).
 *
 * The server's Background class has two places, so a screen of discs must not
 * ask at once: a summary waits its turn behind other summaries, and a Magnet's
 * sources share one answer. A page waits behind other pages. Abort drops a
 * read still waiting, and ends one running: the browser closes the connection,
 * the front sees it, and the read stops.
 *
 * What a server says:
 *   200       each source says how it went
 *   503 Busy  no place for the whole request: every source is busy, for now
 *   404       no route here (a Python-only server), or no definition yet: null,
 *             and the caller keeps the store path. Remembered per Magnet. */

import type { MagnetId, MagnetSourceStatus } from './types'

export interface RouteResult {
  kind: string; id: string
  version?: string; conversation?: string; author?: string | null; at?: number | null
  number?: number | null; post?: string; deleted?: boolean
  value?: unknown
}
export interface RouteSummary { title?: string; about?: string | null; activity?: number | null; posts?: number }
export interface RouteSource {
  key: string
  status: MagnetSourceStatus
  reason?: string | null
  summary?: RouteSummary | null
  results?: RouteResult[]
  /** this source's own cursor: one per source, never shared */
  next?: string | null
  dates?: unknown
  /* a summary's, said on the source; a build that doesn't say them leaves them out */
  participants?: unknown
  participants_more?: unknown
  latest?: unknown
}
export interface RouteAnswer {
  magnet?: string
  /** the definition can't be read as this build's schema: never defaulted */
  unavailable?: string
  sources: RouteSource[]
}
export type RouteGet = (path: string, signal?: AbortSignal) => Promise<{ status: number; body: unknown }>

export interface MagnetRoute {
  summary(magnet: MagnetId, signal?: AbortSignal): Promise<RouteAnswer | null>
  page(magnet: MagnetId, key: string, types: readonly string[], cursor?: string, signal?: AbortSignal): Promise<RouteSource | null>
}

const aborted = () => new DOMException('The read was abandoned.', 'AbortError')
const BUSY = 'The server has no room for this read just now; it is read again when something changes.'
const said = (body: unknown): string | undefined => (body as { error?: string } | null)?.error

/** One at a time, in the order asked. */
function lane() {
  let tail: Promise<unknown> = Promise.resolve()
  return <T,>(job: () => Promise<T>): Promise<T> => {
    const run = tail.then(job, job)
    tail = run.catch(() => undefined)
    return run
  }
}

interface Shared { answer: Promise<RouteAnswer | null>; control: AbortController; waiting: number }

export function createMagnetRoute(get: RouteGet): MagnetRoute {
  const none = new Set<string>()
  const summaries = lane()
  const pages = lane()
  const sharing = new Map<string, Shared>()
  const path = (magnet: MagnetId, query: string) => `magnets/${encodeURIComponent(magnet)}/read?${query}`

  /* A later caller shares the read a Magnet already has coming. It ends only
     when everyone who wanted it has gone. */
  const shared = (magnet: MagnetId): Shared => {
    const had = sharing.get(magnet)
    if (had) return had
    const control = new AbortController()
    const answer = summaries(async (): Promise<RouteAnswer | null> => {
      if (control.signal.aborted) throw aborted()
      const got = await get(path(magnet, 'mode=summary'), control.signal)
      if (got.status === 404) { none.add(magnet); return null }
      if (got.status === 503) return { magnet, sources: [], busy: said(got.body) ?? BUSY } as RouteAnswer & { busy: string }
      if (got.status !== 200) throw new Error(said(got.body) ?? `The Magnet could not be read (${got.status}).`)
      return got.body as RouteAnswer
    }).finally(() => { if (sharing.get(magnet)?.control === control) sharing.delete(magnet) })
    const fresh = { answer, control, waiting: 0 }
    sharing.set(magnet, fresh)
    return fresh
  }

  return {
    summary(magnet, signal) {
      if (none.has(magnet)) return Promise.resolve(null)
      if (signal?.aborted) return Promise.reject(aborted())
      const one = shared(magnet)
      one.waiting++
      if (!signal) return one.answer
      return new Promise((resolve, reject) => {
        const leave = () => {
          reject(aborted())
          if (--one.waiting === 0) {
            one.control.abort()
            if (sharing.get(magnet) === one) sharing.delete(magnet)
          }
        }
        signal.addEventListener('abort', leave, { once: true })
        one.answer.then(resolve, reject).finally(() => signal.removeEventListener('abort', leave))
      })
    },
    page(magnet, key, types, cursor, signal) {
      if (none.has(magnet)) return Promise.resolve(null)
      const query = new URLSearchParams({ mode: 'page', source: key, types: types.join(',') })
      if (cursor) query.set('cursor', cursor)
      return pages(async () => {
        if (signal?.aborted) throw aborted()
        const got = await get(path(magnet, query.toString()), signal)
        if (got.status === 404) { none.add(magnet); return null }
        if (got.status === 503) return { key, status: 'busy', reason: said(got.body) ?? BUSY, results: [] }
        if (got.status !== 200) throw new Error(said(got.body) ?? `The Magnet could not be read (${got.status}).`)
        const body = got.body as RouteAnswer
        if (body.unavailable) return { key, status: 'unavailable', reason: body.unavailable, results: [] }
        return body.sources.find((s) => s.key === key) ?? { key, status: 'unavailable', reason: 'The server did not answer for this source.', results: [] }
      })
    },
  }
}

/** One source's part of a summary answer, whichever way it came out. */
export function sourceOfSummary(answer: RouteAnswer & { busy?: string }, key: string): RouteSource {
  if (answer.unavailable) return { key, status: 'unavailable', reason: answer.unavailable }
  if (answer.busy) return { key, status: 'busy', reason: answer.busy }
  return answer.sources.find((s) => s.key === key) ?? { key, status: 'unavailable', reason: 'The server did not answer for this source.' }
}
