/* WHAT THE CONVERSATION'S SURFACES READ BESIDE ITS POSTS (completion stream B).
 *
 * The composer's `@` and `#` and the About slide-out need what production's
 * conversation read already answers -- its participants with each name's
 * DECLARED runtime, its Topics, what is owed in it -- and none of its Turns:
 * `GET /api/conversations/<id>?batch=0` is exactly that read with an empty
 * batch. What needs only the people and Topics reads `?fields=` instead
 * (`usePeopleAndTopics`, below): the batch=0 read carries everything owed
 * here, which is most of its size. Everybody the record holds is
 * identity/people.ts; `@` beyond this conversation searches it
 * (composer/useAddressable.ts). Read once per page and again on asking
 * (`refresh`), never per keystroke. */

import { useEffect, useSyncExternalStore } from 'react'
import { CLIENT_HEADERS } from '../../api'
import { fluidFetch } from '../http'
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
  const res = await fluidFetch(path, { ...init, headers: { ...CLIENT_HEADERS, ...(init?.headers ?? {}) } })
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
    .then((d) => {
      facts.set(id, { data: d, error: null, loading: false })
      /* The full read holds the narrow one: whoever reads only the people
         and Topics sees these too, without asking again. */
      kept.set(id, { data: { id: d.id, name: d.name, participants: d.participants, topics: d.topics }, error: null, loading: false })
      emit()
    })
    .catch((e: Error) => { facts.set(id, { data: had?.data ?? null, error: e.message, loading: false }); emit() })
}

/** One first read per id, now or once the store is quiet (`whenQuiet`). */
function useFirstRead<T>(slots: Map<Id, Slot<T>>, waiting: Set<Id>, read: (id: Id) => void, id: Id | null, defer: boolean): Slot<T> {
  useTick()
  useEffect(() => {
    if (!id || slots.has(id)) return
    if (!defer) { waiting.delete(id); read(id); return }
    if (waiting.has(id)) return
    waiting.add(id)
    void whenQuiet().then(() => { if (!waiting.delete(id)) return; if (!slots.has(id)) read(id) })
  }, [id, defer])
  return (id && slots.get(id)) || { data: null, error: null, loading: !!id }
}

/** This conversation's participants, Topics and what is owed in it.
 *  `defer`: first read once the store's own reads are quiet (`whenQuiet`),
 *  so opening a conversation reads its posts first and these after them.
 *  A reader somebody is using now (the composer once opened, an addressing
 *  sheet) passes false and has them read at once. */
export function useFacts(id: Id | null, defer = true): Slot<Facts> {
  return useFirstRead(facts, asked, refreshFacts, id, defer)
}

/* -- the people and Topics only (stage 1c) -----------------------------------
 * What `@`, `#`, the who strip and the Topics control read: `?fields=` asks
 * for those parts of the conversation's read alone, a few KB, rather than
 * `?batch=0`, which reads everything owed here with them. */

export interface PeopleAndTopics { id: Id; name: string; participants: Person[]; topics: Topic[] }
const kept = new Map<Id, Slot<PeopleAndTopics>>()
const keptAsked = new Set<Id>()

export const PEOPLE_AND_TOPICS = 'name,participants,topics'

/** Read this conversation's people and Topics again -- after somebody is
 *  brought in or a Topic opened -- and its full facts too, if anything
 *  holds them, so the two never disagree. */
export function refreshPeopleAndTopics(id: Id) {
  const had = kept.get(id)
  kept.set(id, { data: had?.data ?? null, error: null, loading: true })
  emit()
  void getJson<PeopleAndTopics>(`/api/conversations/${encodeURIComponent(id)}?fields=${PEOPLE_AND_TOPICS}`)
    .then((d) => { kept.set(id, { data: d, error: null, loading: false }); emit() })
    .catch((e: Error) => { kept.set(id, { data: had?.data ?? null, error: e.message, loading: false }); emit() })
  if (facts.has(id)) refreshFacts(id)
}

/** This conversation's participants and Topics, and nothing owed. Read as
 *  `useFacts` is (`defer`); a full read already held answers it. */
export function usePeopleAndTopics(id: Id | null, defer = true): Slot<PeopleAndTopics> {
  return useFirstRead(kept, keptAsked, refreshPeopleAndTopics, id, defer)
}
