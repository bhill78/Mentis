/* CLOSE, KEPT ON THIS BROWSER DEVICE (plan §3.9 item 1; part P5).
 *
 * What is closed here is one set of zone ids per brain, place and
 * presentation class, in localStorage:
 *
 *   mentis.fluid.closed:<brain>:<place>:<class>  ->  ["z1", "float-…", …]
 *
 * Every tab of this browser profile shares it (a `storage` event tells the
 * others), so Close survives a reload and a new tab until Reopen, Remove
 * from workspace, or the zone going from the arrangement. Another browser
 * or device has its own. It is never sent to the server and is no part of
 * the arrangement. Browser-free: the storage is handed in. */

import type { PresentationClass, ZoneId } from './types'

export const CLOSED_PREFIX = 'mentis.fluid.closed:'
/** At most this many ids per set; the oldest closed goes first. */
export const MAX_CLOSED = 64
const ID = /^[A-Za-z0-9_.:-]{1,80}$/

/** The localStorage a set is kept in (window.localStorage, or a test's). */
export interface LocalStore {
  getItem(key: string): string | null
  setItem(key: string, value: string): void
  removeItem(key: string): void
}

export const closedKey = (brain: string, place: string, cls: PresentationClass): string => `${CLOSED_PREFIX}${brain}:${place}:${cls}`

/** The class a key names, when it is this brain and place's. */
export function classOfKey(key: string, brain: string, place: string): PresentationClass | null {
  const head = `${CLOSED_PREFIX}${brain}:${place}:`
  if (!key.startsWith(head)) return null
  const c = key.slice(head.length)
  return c === 'wide' || c === 'medium' || c === 'compact' ? c : null
}

/** A set as kept: what is not an id is not read. */
export function parseClosed(raw: string | null): Set<ZoneId> {
  if (!raw) return new Set()
  try {
    const v: unknown = JSON.parse(raw)
    return new Set(Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string' && ID.test(x)).slice(-MAX_CLOSED) : [])
  } catch { return new Set() }
}

export function readClosed(store: LocalStore | null, key: string): Set<ZoneId> {
  if (!store) return new Set()
  try { return parseClosed(store.getItem(key)) } catch { return new Set() }
}

/** Keep a set (the latest closed last); an empty one is removed. */
export function writeClosed(store: LocalStore | null, key: string, closed: ReadonlySet<ZoneId>) {
  if (!store) return
  const ids = [...closed].filter((x) => ID.test(x)).slice(-MAX_CLOSED)
  try {
    if (ids.length) store.setItem(key, JSON.stringify(ids))
    else store.removeItem(key)
  } catch { /* private mode: this page only */ }
}

/** The browser's localStorage, where there is one. */
export const browserStore = (): LocalStore | null => {
  try { return typeof localStorage !== 'undefined' ? localStorage : null } catch { return null }
}
