/* WHAT EACH NEEDS YOU ITEM IS ABOUT, READ ONCE FOR THE LIST
 * (`GET /fluid/api/needs-you/about?ids=`), and THE WAY BACK TO A DECISION
 * after one of its references was opened.
 *
 * Kept for the life of the tab, by the request's id, so the list does not
 * flicker to bare ids while it is read again. A read that fails is said (the
 * item then says it could not be read); what was read before stays shown. */
import { useEffect, useSyncExternalStore } from 'react'
import { fluidFetch } from '../../fluid/http'
import type { NeedsItem } from '../../needsItems'
import type { About } from './inspect'

const PATH = '/fluid/api/needs-you/about'
/** the server's batch (mentis/fluid/read.py BATCH) */
const BATCH = 64

const held = new Map<string, About>()
const failed = new Map<string, string>()
const heard = new Set<() => void>()
let version = 0
const changed = () => { version++; heard.forEach((f) => f()) }
const subscribe = (f: () => void) => { heard.add(f); return () => { heard.delete(f) } }

/** The request an item is read by: its first ask (a form answers whole). */
export const askOf = (it: Pick<NeedsItem, 'asks' | 'key'>) => it.asks[0] ?? it.key

async function read(ids: string[]): Promise<void> {
  for (let i = 0; i < ids.length; i += BATCH) {
    const part = ids.slice(i, i + BATCH)
    try {
      const res = await fluidFetch(`${PATH}?ids=${part.map(encodeURIComponent).join(',')}`, { headers: { 'X-Mentis-Client': '1' } })
      const body = await res.json().catch(() => null) as { about?: About[]; error?: string } | null
      if (!res.ok || !body?.about) throw new Error(body?.error ?? (res.statusText || String(res.status)))
      for (const a of body.about) { held.set(a.id, a); failed.delete(a.id) }
    } catch (e) {
      const why = String(e instanceof Error ? e.message : e)
      for (const id of part) failed.set(id, why)
    }
  }
  changed()
}

/** What these items are about, read when the list changes and again each
 *  time the list is opened (`again`). */
export function useAbout(items: NeedsItem[], again: unknown): { of: (it: NeedsItem) => About | null; errorOf: (it: NeedsItem) => string | null } {
  const ids = items.map(askOf)
  const key = ids.join(',')
  useSyncExternalStore(subscribe, () => version)
  useEffect(() => { if (key) void read(key.split(',')) }, [key, again])
  return {
    of: (it) => held.get(askOf(it)) ?? null,
    errorOf: (it) => (held.has(askOf(it)) ? null : failed.get(askOf(it)) ?? null),
  }
}

/* -- answering here, kept open ------------------------------------------------
   Which items have their form open in the list. The form's own draft (what
   is chosen and typed) is the form's (experimental/types/decision.tsx
   `useDraft`); this is only whether it is unfolded, kept so that coming back
   from a reference finds the form as it was left. */
const UNFOLDED_KEY = 'mentis.q2.needs.unfolded.v1'
const unfolded = new Set<string>((() => {
  try {
    const got = JSON.parse((typeof sessionStorage === 'undefined' ? null : sessionStorage.getItem(UNFOLDED_KEY)) ?? '[]') as unknown
    return Array.isArray(got) ? got.filter((x): x is string => typeof x === 'string') : []
  } catch { return [] }
})())
export function useUnfolded(key: string): [boolean, (open: boolean) => void] {
  const open = useSyncExternalStore(subscribe, () => unfolded.has(key))
  return [open, (to) => {
    if (to) unfolded.add(key); else unfolded.delete(key)
    try { sessionStorage.setItem(UNFOLDED_KEY, JSON.stringify([...unfolded])) } catch { /* kept on this page only */ }
    changed()
  }]
}

/* -- the way back -------------------------------------------------------------
   Opening a reference from a decision leaves the list (the panel closes, the
   centre shows the thing). What was left is remembered -- which item, which
   reference -- so one press, or the browser's Back, returns to that item with
   its form as it was, and focus goes back to the reference that was opened. */
export interface Leave {
  /** the item's key */
  item: string
  /** the reference opened, by id */
  ref: string
  /** the item, in the reader's words */
  what: string
  /** the reference, in the reader's words */
  opened: string
  /** whether the item is a decision (else a request or an input) */
  decision: boolean
  at: number
}
let left: Leave | null = null
export function leaveFor(l: Omit<Leave, 'at'>) { left = { ...l, at: Date.now() }; changed() }
export function clearLeave() { if (left) { left = null; changed() } }
export function useLeave(): Leave | null { return useSyncExternalStore(subscribe, () => left) }
export const leaveNow = () => left
