/* EVERYBODY THE RECORD HOLDS, AND WHAT EACH DECLARED (moved from
 * conversation/facts.ts, which still re-exports it; E2).
 *
 * Production's `/api/participants` (searched, never pruned): each name, its
 * chosen picture, where it last ran, and its declared runtime. Read once per
 * page, only when something will show it, and again when the pulse says the
 * people moved (a picture chosen, a name joined: production's `concerns`
 * rule for `/api/participants`) -- never per keystroke or per post. Every
 * `<Who>` reads this one copy. */

import { useEffect, useSyncExternalStore } from 'react'
import { CLIENT_HEADERS } from '../../api'
import { fluidFetch } from '../http'
import type { Id } from '../store'
import { hearPulse } from './activity'

export interface Person {
  participant: Id
  alias: string
  about?: string
  default_runtime?: string | null
  runtime_mode?: 'default' | 'auto' | 'undeclared'
  conversations?: Id[]
  /** the held image chosen to picture this name, or null (production's identity.tsx) */
  avatar?: Id | null
  /** where this name last ran, observed; null if it never has */
  runtime?: string | null
}

type Slot<T> = { data: T | null; error: string | null; loading: boolean }
let people: Slot<Person[]> = { data: null, error: null, loading: false }
let byId: Map<Id, Person> = new Map()
const heard = new Set<() => void>()
const emit = () => { for (const fn of [...heard]) fn() }
const subscribe = (fn: () => void) => { heard.add(fn); return () => { heard.delete(fn) } }

export function refreshPeople() {
  people = { ...people, loading: true }
  emit()
  void fluidFetch('/api/participants', { headers: { ...CLIENT_HEADERS } })
    .then(async (res) => {
      const body = await res.json().catch(() => null)
      if (!res.ok || !body || body.error) throw new Error(body?.error ?? res.statusText)
      return body as { participants: Person[] }
    })
    .then((d) => {
      people = { data: d.participants, error: null, loading: false }
      byId = new Map(d.participants.map((p) => [p.participant, p]))
      emit()
    })
    .catch((e: Error) => { people = { data: people.data, error: e.message, loading: false }; emit() })
}

/* Heard once the people are first asked for, for as long as the page lives. */
let following = false
function follow() {
  if (following) return
  following = true
  hearPulse((m, where) => { if (m === 'durable' && where && (where.people || where.loose) && people.data) refreshPeople() })
}

/** Everybody the record holds, with what each declared. Asked only when
 *  something will show it. */
export function usePeople(want: boolean): Slot<Person[]> {
  const got = useSyncExternalStore(subscribe, () => people)
  useEffect(() => {
    if (!want) return
    if (!people.data && !people.loading) refreshPeople()
    follow()
  }, [want])
  return got
}

/** One name, by participant id (null until the people are read). */
export function usePerson(id: Id | null | undefined): Person | undefined {
  usePeople(true)
  return id ? byId.get(id) : undefined
}

/** One name, outside React (for what a notification says). */
export function personOf(id: Id | null | undefined): Person | undefined {
  if (!people.data && !people.loading) refreshPeople()
  return id ? byId.get(id) : undefined
}

/** Production's `whoColour` (api.ts): recognition, never status. */
export function whoColour(id: string | null | undefined): string {
  if (!id) return 'var(--text-faint)'
  let h = 0
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) >>> 0
  return `var(--who-${(h % 6) + 1})`
}

/** A name as Fluid writes it: `@alias`, whatever the record stored. */
export const at = (alias: string | null | undefined) => '@' + (alias ?? '').replace(/^@/, '')
