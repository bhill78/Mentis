/* EXPERIMENTAL: THE ONE DOOR TO THE DUNGEON HELPER EXPERIMENT BACKEND.

   The helper type and the `camp:` reference provider both reach a backend
   OUTSIDE Mentis (experiments/dungeon_helper/server.py). Every request to it
   goes through this module, and nothing here runs because a block was drawn:

   * A helper session is opened only by `connect`, which only a reader's
     Connect button calls. A connection belongs to (backend origin, block
     state key, requested scope). Two views of one block (inline and pinned,
     a remount, StrictMode) share it and its one in-flight request; none of
     them opens another. A block whose scope is edited is a different
     connection: it never reuses a session opened requesting another scope.
   * Every attempt and every allowance has a generation. Disconnect (or Cancel
     while connecting) ends the generation, so nothing still in flight from it
     -- a session being opened, an answer, a refusal, a reference read -- is
     accepted afterwards, even if the reader connects again before it lands.
   * A `camp:` reference is read only under a session this tab's reader
     allowed: by connecting the helper that opened it, or by pressing Connect
     on the reference. A `via=` written into a block grants nothing by itself.
     Allowing is SESSION-WIDE: every reference in this tab naming that
     session is read while it is allowed, including ones written later. The
     session id is random but it is not a secret -- it is written into the
     helper's replies and pins -- so isolation is never argued from it.
   * One poller per (session, reference), however many views show it. A
     refused or unreachable read stops and waits for Retry. A missing item
     (404) is asked again every period, as a live view, until Disconnect.
     Disconnect stops every read under the session, everywhere.

   The scope a helper requests (player or dm) comes from the block and the
   experiment backend accepts it as asked. Connecting is the reader's consent
   to contact that backend; it is NOT DM/player authorization, and Mentis
   enforces nothing about it. The backend has no route to end a session, so
   Disconnect stops this tab using it; the backend forgets it on restart.
   Everything here lasts for the life of the tab.

   KNOWN GATE (I1): the block state key is what the renderer gives a block.
   Two unrelated blocks given the SAME key and requesting the same scope (as
   linked Turns are until the I1 identity correction) are one connection
   here. This module cannot tell them apart; isolating them is I1's, and S1
   is not accepted as isolated until the two are checked together. */
import { useSyncExternalStore } from 'react'

/* On this PC the helper is 127.0.0.1:8794. Opened from another device over the
   tailnet, it is the same host on :8795 (tailscale serve :8795 -> 127.0.0.1:8794).
   Fixed for the life of the tab; no block can name another backend. */
export const HELPER_ORIGIN = typeof location === 'undefined' || /^(127\.0\.0\.1|localhost)$/.test(location.hostname)
  ? 'http://127.0.0.1:8794'
  : `${location.protocol}//${location.hostname}:8795`

export const POLL_MS = 3000

export type Link =
  | { status: 'off' }
  | { status: 'connecting' }
  /** `scope` is the scope the session was opened requesting. */
  | { status: 'on'; session: string; scope: string }
  | { status: 'failed'; error: string }
  /** The backend no longer knows the session (it restarted). */
  | { status: 'lost'; error: string }

let v = 0
const listeners = new Set<() => void>()
const bump = () => { v++; listeners.forEach((f) => f()) }
const subscribe = (f: () => void) => { listeners.add(f); return () => { listeners.delete(f) } }
/** Re-render when any connection or campaign read changes. */
export const useExternal = () => useSyncExternalStore(subscribe, () => v, () => v)

let gens = 0

/* ------------------------------------------------------------ helper links */

const links = new Map<string, Link>()
/** The generation that owns each connection now; anything from another is stale. */
const owner = new Map<string, number>()
const inflight = new Map<string, { gen: number; p: Promise<string | null> }>()
/** Sessions this tab's reader allowed to be used, each with the generation of that allowance. */
const allowed = new Map<string, number>()

/** One connection: this backend, this block, this requested scope. */
const cid = (key: string, scope: string) => `${HELPER_ORIGIN}\n${key}\n${scope}`
const keyOf = (id: string) => id.split('\n')[1]

export const linkOf = (key: string, scope: string): Link => links.get(cid(key, scope)) ?? { status: 'off' }
export const isAllowed = (session: string) => allowed.has(session)

/** An answer that landed after the connection it was asked under ended. It changes nothing. */
export class Stale extends Error {
  stale = true
  constructor() { super('the connection this was asked under has ended; its answer was discarded') }
}

async function call(method: 'GET' | 'POST', path: string, body?: unknown) {
  const r = await fetch(HELPER_ORIGIN + path, method === 'POST'
    ? { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
    : undefined)
  let j: any
  try { j = await r.json() } catch { j = {} }
  if (!r.ok) throw Object.assign(new Error(j.error ?? `HTTP ${r.status}`), { code: r.status })
  return j
}

/** End whatever generation owns a connection: a pending attempt or a live link. */
function end(id: string) {
  const now = links.get(id)
  if (now?.status === 'on') revoke(now.session)
  owner.set(id, ++gens)
  inflight.delete(id)
  links.set(id, { status: 'off' })
}

/** The reader pressed Connect: open ONE session for this block, requesting `scope`. */
export function connect(key: string, scope: string): Promise<string | null> {
  const id = cid(key, scope)
  const now = links.get(id)
  if (now?.status === 'on') return Promise.resolve(now.session)
  const pending = inflight.get(id)
  if (pending && owner.get(id) === pending.gen) return pending.p
  const gen = ++gens
  owner.set(id, gen)
  links.set(id, { status: 'connecting' })
  bump()
  const mine = () => owner.get(id) === gen
  const p = call('POST', '/session', { scope })
    .then((s) => {
      /* Disconnected or cancelled meanwhile: the session is never used. */
      if (!mine()) return null
      const session = String(s.session)
      grant(session)
      links.set(id, { status: 'on', session, scope })
      return session
    })
    .catch((e: Error) => {
      if (!mine()) return null
      links.set(id, { status: 'failed', error: e.message })
      return null
    })
    .finally(() => {
      if (inflight.get(id)?.gen === gen) inflight.delete(id)
      bump()
    })
  inflight.set(id, { gen, p })
  return p
}

/** Stop this tab using the block's session, and every read made under it. Cancels a pending Connect. */
export function disconnect(key: string, scope: string) {
  end(cid(key, scope))
  bump()
}

/** The block's scope was edited: end every connection of this block that requested another scope. */
export function retire(key: string, keep: string) {
  let any = false
  for (const [id, l] of [...links]) if (keyOf(id) === key && id !== cid(key, keep) && l.status !== 'off') { end(id); any = true }
  if (any) bump()
}

/* The scope each block last declared, and the scopes its views on screen request
   now. Kept here, for the life of the tab, not in a view: an edit can pass through
   an invalid source, which unmounts the view, and the edit must still be seen. */
const declared = new Map<string, string>()
const shown = new Map<string, number>()

/** A view of a block requesting `scope` is on screen. `was` is the scope that same
    view requested before, if it did. When the block's declared scope changed (across
    a remount too), every connection of the block that requested another scope, and
    that no view on screen still requests, ends: polls, pending Connect and answers
    with it. An unchanged source changes nothing. Returns the view's release. */
export function declare(key: string, scope: string, was?: string): () => void {
  const id = cid(key, scope)
  shown.set(id, (shown.get(id) ?? 0) + 1)
  const before = declared.get(key)
  declared.set(key, scope)
  if ((before !== undefined && before !== scope) || (was !== undefined && was !== scope)) {
    let any = false
    for (const [other, l] of [...links])
      if (keyOf(other) === key && other !== id && l.status !== 'off' && !shown.get(other)) { end(other); any = true }
    if (any) bump()
  }
  return () => {
    const n = (shown.get(id) ?? 1) - 1
    if (n > 0) shown.set(id, n)
    else {
      shown.delete(id)
      // A scope change deferred retirement while this view still requested the
      // old scope. Its last release must finish that retirement, even without
      // another declare. An unchanged-source unmount keeps the connection.
      const current = declared.get(key)
      const link = links.get(id)
      if (current !== undefined && current !== scope && link && link.status !== 'off') {
        end(id)
        bump()
      }
    }
  }
}

/** Ask the backend under the block's connected session. Refuses without one.
    An answer or refusal that lands after that connection ended throws `Stale`
    and changes nothing: it is not shown, pinned or held, and a stale refusal
    does not mark a newer connection lost. */
export async function ask(key: string, scope: string, body: Record<string, unknown>) {
  const id = cid(key, scope)
  const now = linkOf(key, scope)
  if (now.status !== 'on') throw new Error('not connected to the experiment backend')
  const gen = owner.get(id)
  const current = () => owner.get(id) === gen && allowed.has(now.session)
  let r
  try {
    r = await call('POST', '/ask', { ...body, session: now.session })
  } catch (e) {
    if (!current()) throw new Stale()
    if ((e as any).code === 403) {
      revoke(now.session)
      owner.set(id, ++gens)
      links.set(id, { status: 'lost', error: (e as Error).message })
      bump()
    }
    throw e
  }
  if (!current()) throw new Stale()
  return r
}

/* ---------------------------------------------------- campaign references */

export type Read =
  | { st: 'no-grant' }
  | { st: 'not-connected' }
  | { st: 'loading' }
  | { st: 'ok'; data: Record<string, any> }
  /** 404: it does not exist, or it is outside the session's scope. Asked again every period. */
  | { st: 'missing'; err: string }
  /** Stopped: unreachable, refused (403) or unreadable. Waits for Retry. */
  | { st: 'stopped'; err: string; code?: number }

interface Poller {
  session: string; ref: string; subs: number; timer: number | null; last: number; value: Read
  /** The allowance generation the read in flight was asked under, or null. */
  asking: number | null
}
const pollers = new Map<string, Poller>()
const pkey = (session: string, ref: string) => `${session}\n${ref}`

function readNow(p: Poller) {
  const gen = allowed.get(p.session)
  if (gen === undefined || p.asking === gen) return
  p.asking = gen
  p.last = Date.now()
  /* Only the allowance that asked may use the answer: one revoked meanwhile,
     even if allowed again since, is discarded and the new allowance asks afresh. */
  const mine = () => allowed.get(p.session) === gen
  call('GET', `/item/${encodeURIComponent(p.ref)}?session=${encodeURIComponent(p.session)}`)
    .then((data) => { if (mine()) p.value = { st: 'ok', data } })
    .catch((e: Error & { code?: number }) => {
      if (!mine()) return
      if (e.code === 404) p.value = { st: 'missing', err: e.message }
      else {
        p.value = { st: 'stopped', err: e.code ? e.message : `the Dungeon Helper backend is not reachable (${e.message})`, code: e.code }
        stop(p)
      }
    })
    .finally(() => {
      if (p.asking === gen) p.asking = null
      if (!allowed.has(p.session)) p.value = { st: 'not-connected' }
      bump()
    })
}

function stop(p: Poller) {
  if (p.timer !== null) { clearInterval(p.timer); p.timer = null }
}

function start(p: Poller) {
  /* A stopped read waits for Retry: a remount does not retry it. */
  if (p.timer !== null || !p.subs || !allowed.has(p.session) || p.value.st === 'stopped') return
  if (p.value.st === 'not-connected') p.value = { st: 'loading' }
  /* A remount within one period reuses the last answer instead of asking again. */
  const fresh = (p.value.st === 'ok' || p.value.st === 'missing') && Date.now() - p.last < POLL_MS
  if (!fresh) readNow(p)
  p.timer = setInterval(() => readNow(p), POLL_MS) as unknown as number
}

/** Allow a session under a new generation, and start every view waiting on it. */
function grant(session: string) {
  if (allowed.has(session)) return
  allowed.set(session, ++gens)
  for (const p of pollers.values()) if (p.session === session) start(p)
}

function revoke(session: string) {
  allowed.delete(session)
  for (const p of pollers.values()) if (p.session === session) { stop(p); p.value = { st: 'not-connected' } }
}

/** The reader pressed Connect on a reference: allow reads under its session -- every reference naming it, in this tab. */
export function allow(session: string) {
  grant(session)
  bump()
}

/** The reader pressed Disconnect on a reference: stop every read under its session, and any helper connection using it. */
export function disallow(session: string) {
  revoke(session)
  for (const [id, l] of [...links]) if (l.status === 'on' && l.session === session) end(id)
  bump()
}

/** Read again after a failure. */
export function retry(session: string, ref: string) {
  const p = pollers.get(pkey(session, ref))
  if (!p || !allowed.has(session)) return
  p.value = { st: 'loading' }
  stop(p)
  start(p)
  bump()
}

/** One view of a reference starts showing it. Returns its release. */
export function watch(session: string, ref: string): () => void {
  const k = pkey(session, ref)
  let p = pollers.get(k)
  if (!p) {
    p = { session, ref, subs: 0, timer: null, last: 0, value: { st: allowed.has(session) ? 'loading' : 'not-connected' }, asking: null }
    pollers.set(k, p)
  }
  p.subs++
  start(p)
  const q = p
  return () => { q.subs--; if (!q.subs) stop(q) }
}

export function readOf(session: string | null | undefined, ref: string): Read {
  if (!session) return { st: 'no-grant' }
  if (!allowed.has(session)) return { st: 'not-connected' }
  return pollers.get(pkey(session, ref))?.value ?? { st: 'loading' }
}

/** For tests: forget everything. */
export function _reset() {
  for (const p of pollers.values()) stop(p)
  pollers.clear(); links.clear(); inflight.clear(); allowed.clear(); owner.clear(); declared.clear(); shown.clear()
  bump()
}
