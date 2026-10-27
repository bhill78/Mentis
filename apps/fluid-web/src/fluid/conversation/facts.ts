/* WHAT THE CONVERSATION'S SURFACES READ BESIDE ITS POSTS (completion stream B).
 *
 * The composer's `@` and `#` and the About slide-out need what production's
 * conversation read already answers -- its participants with each name's
 * DECLARED runtime, its Topics, what is owed in it -- and none of its Turns:
 * `GET /api/conversations/<id>?batch=0` is exactly that read with an empty
 * batch. Everybody the record holds, for `@` beyond this conversation, is
 * production's `/api/participants` (identity/people.ts). Both are read once
 * per page and again on asking (`refresh`), never per keystroke. */

import { useEffect, useSyncExternalStore } from 'react'
import { CLIENT_HEADERS } from '../../api'
import { whenQuiet, type Id } from '../store'
import type { Person } from '../identity/people'

/* Who is who moved to identity/people.ts (E2); kept here for its callers. */
export { refreshPeople, usePeople, type Person } from '../identity/people'

export interface Topic { id: Id; name: string; about?: string }
export interface Owed {
  expectation: Id
  turn: Id
  expects: string
  requested_by: Id | null
  requested_by_alias?: string | null
  expected_of: Id | null
  expected_of_alias?: string | null
  unassigned: boolean
  live_execution: unknown[]
  failures: { because: string; at: number }[]
  options?: unknown
}
export interface Facts {
  id: Id
  name: string
  participants: Person[]
  topics: Topic[]
  owed: Owed[]
  failures: { act?: string; because?: string; at?: number; turn?: Id }[]
  turns_total: number
}

export async function getJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { ...init, headers: { ...CLIENT_HEADERS, ...(init?.headers ?? {}) } })
  const body = await res.json().catch(() => null)
  if (!res.ok || !body || body.error) throw new Error(body?.error ?? res.statusText)
  return body as T
}

type Slot<T> = { data: T | null; error: string | null; loading: boolean }
const facts = new Map<Id, Slot<Facts>>()
let tick = 0
const heard = new Set<() => void>()
const emit = () => { tick += 1; for (const fn of [...heard]) fn() }
const subscribe = (fn: () => void) => { heard.add(fn); return () => { heard.delete(fn) } }
const useTick = () => useSyncExternalStore(subscribe, () => tick)

/** First reads waiting for the store to be quiet, so each is asked once. */
const asked = new Set<Id>()

export function refreshFacts(id: Id) {
  const had = facts.get(id)
  facts.set(id, { data: had?.data ?? null, error: null, loading: true })
  emit()
  void getJson<Facts>(`/api/conversations/${encodeURIComponent(id)}?batch=0`)
    .then((d) => { facts.set(id, { data: d, error: null, loading: false }); emit() })
    .catch((e: Error) => { facts.set(id, { data: had?.data ?? null, error: e.message, loading: false }); emit() })
}

/** This conversation's participants, Topics and what is owed in it.
 *  `defer`: first read once the store's own reads are quiet (`whenQuiet`),
 *  so opening a conversation reads its posts first and these after them.
 *  A reader somebody is using now (the composer once opened, an addressing
 *  sheet) passes false and has them read at once. */
export function useFacts(id: Id | null, defer = true): Slot<Facts> {
  useTick()
  useEffect(() => {
    if (!id || facts.has(id)) return
    if (!defer) { asked.delete(id); refreshFacts(id); return }
    if (asked.has(id)) return
    asked.add(id)
    void whenQuiet().then(() => { if (!asked.delete(id)) return; if (!facts.has(id)) refreshFacts(id) })
  }, [id, defer])
  return (id && facts.get(id)) || { data: null, error: null, loading: !!id }
}
