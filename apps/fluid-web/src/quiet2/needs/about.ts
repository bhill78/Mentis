/* WHAT EACH NEEDS YOU ITEM IS ABOUT, READ FOR THE LIST
 * (`GET /fluid/api/needs-you/about?ids=`), and THE WAY BACK TO A DECISION
 * after one of its references was opened.
 *
 * WHAT IS SHOWN IS WHAT THIS OPENING OF THE LIST READ, FROM THIS BRAIN, AND
 * NOTHING OLDER (independent review, 2026-11-20). The same address can serve
 * another Brain later, and a restored or copied Brain reuses ids, so details
 * read earlier are never drawn as current:
 *   - each reading is marked with the Brain it came from (the server says
 *     which, `brain`) and the opening of the list that asked for it;
 *   - only a reading for this Brain and this opening is shown. Until it
 *     arrives the item says it is being read;
 *   - a read that fails REMOVES what was held for those requests and says
 *     the details could not be read. The decision itself stays usable;
 *   - an answer from a Brain other than the one this page opened is refused
 *     in words, never shown. */
import { useEffect, useSyncExternalStore } from 'react'
import { scopeOf } from '../../experimental/draftKeep'
import { fluidFetch } from '../../fluid/http'
import type { NeedsItem } from '../../needsItems'
import type { About } from './inspect'

const PATH = '/fluid/api/needs-you/about'
/** the server's batch (mentis/fluid/read.py BATCH) */
const BATCH = 64
export const OTHER_BRAIN = 'this page was opened on a different Brain than the one now answering; reload the page'

interface Held { about: About; scope: string | null; opening: number }
/** What was read, by request: a store apart from React, so it is checkable. */
export interface AboutStore {
  /** what THIS Brain and THIS opening read for a request, or null */
  of(ask: string, scope: string | null, opening: number): About | null
  /** why it could not be read, where the last read for it failed */
  errorOf(ask: string, scope: string | null, opening: number): string | null
  /** one answer from the server (`brain` is which Brain answered), or a failure */
  took(ids: string[], scope: string | null, opening: number, got: { about?: About[]; brain?: { corpus_id?: string | null; corpus_path?: string | null } | null } | null, why?: string): void
}

export function createAboutStore(): AboutStore {
  const held = new Map<string, Held>()
  const failed = new Map<string, { why: string; scope: string | null; opening: number }>()
  return {
    of: (ask, scope, opening) => {
      const h = held.get(ask)
      return h && h.scope === scope && h.opening === opening ? h.about : null
    },
    errorOf: (ask, scope, opening) => {
      const f = failed.get(ask)
      return f && f.scope === scope && f.opening === opening ? f.why : null
    },
    took(ids, scope, opening, got, why) {
      const from = got?.brain ? scopeOf(got.brain) : null
      /* a Brain other than this page's answered: nothing of it is shown */
      const other = !!got?.about && scope !== null && from !== null && from !== scope
      if (!got?.about || other) {
        for (const id of ids) { held.delete(id); failed.set(id, { why: other ? OTHER_BRAIN : why ?? 'the server did not answer', scope, opening }) }
        return
      }
      const said = new Set<string>()
      for (const a of got.about) { held.set(a.id, { about: a, scope, opening }); failed.delete(a.id); said.add(a.id) }
      for (const id of ids) if (!said.has(id)) { held.delete(id); failed.set(id, { why: 'the server did not say', scope, opening }) }
    },
  }
}

const about = createAboutStore()
const heard = new Set<() => void>()
let version = 0
const changed = () => { version++; heard.forEach((f) => f()) }
const subscribe = (f: () => void) => { heard.add(f); return () => { heard.delete(f) } }

/** The request an item is read by: its first ask (a form answers whole). */
export const askOf = (it: Pick<NeedsItem, 'asks' | 'key'>) => it.asks[0] ?? it.key

async function read(ids: string[], scope: string | null, opening: number): Promise<void> {
  for (let i = 0; i < ids.length; i += BATCH) {
    const part = ids.slice(i, i + BATCH)
    try {
      const res = await fluidFetch(`${PATH}?ids=${part.map(encodeURIComponent).join(',')}`, { headers: { 'X-Mentis-Client': '1' } })
      const body = await res.json().catch(() => null) as { about?: About[]; brain?: { corpus_id?: string; corpus_path?: string | null }; error?: string } | null
      if (!res.ok || !body?.about) about.took(part, scope, opening, null, body?.error ?? (res.statusText || String(res.status)))
      else about.took(part, scope, opening, body)
    } catch (e) {
      about.took(part, scope, opening, null, String(e instanceof Error ? e.message : e))
    }
  }
  changed()
}

/** What these items are about, read by this opening of the list (`opening`)
 *  from this Brain (`scope`; undefined while which Brain is not yet known,
 *  and then nothing is read). */
export function useAbout(items: NeedsItem[], opening: number, scope: string | null | undefined): { of: (it: NeedsItem) => About | null; errorOf: (it: NeedsItem) => string | null } {
  const key = items.map(askOf).join(',')
  useSyncExternalStore(subscribe, () => version)
  useEffect(() => { if (key && scope !== undefined) void read(key.split(','), scope, opening) }, [key, opening, scope])
  return {
    of: (it) => (scope === undefined ? null : about.of(askOf(it), scope, opening)),
    errorOf: (it) => (scope === undefined ? null : about.errorOf(askOf(it), scope, opening)),
  }
}

/* -- answering here, kept open ------------------------------------------------
   Which items have their form open in the list, by Brain and item. The
   form's own draft (what is chosen and typed) is the form's
   (experimental/types/decision.tsx, ../../experimental/draftKeep.ts); this is
   only whether it is unfolded, kept so that coming back from a reference, or
   a reload, finds the form as it was left. With no Brain known it is kept
   for the page only. */
const UNFOLDED_KEY = 'mentis.q2.needs.unfolded.v2'
const unfolded = new Set<string>((() => {
  try {
    const got = JSON.parse((typeof sessionStorage === 'undefined' ? null : sessionStorage.getItem(UNFOLDED_KEY)) ?? '[]') as unknown
    return Array.isArray(got) ? got.filter((x): x is string => typeof x === 'string') : []
  } catch { return [] }
})())
export function useUnfolded(key: string, scope: string | null | undefined): [boolean, (open: boolean) => void] {
  const k = `${scope ?? ''}|${key}`
  const open = useSyncExternalStore(subscribe, () => unfolded.has(k))
  return [open, (to) => {
    if (to) unfolded.add(k); else unfolded.delete(k)
    /* only what is bound to a known Brain outlives the page */
    try { sessionStorage.setItem(UNFOLDED_KEY, JSON.stringify([...unfolded].filter((x) => !x.startsWith('|')))) } catch { /* kept on this page only */ }
    changed()
  }]
}

/* -- the way back -------------------------------------------------------------
   Opening a reference from a decision leaves the list (the panel closes, the
   centre shows the thing). What was left is remembered -- which item, which
   reference -- so ONE CONTROL returns to that item with its form as it was,
   and focus goes back to the reference that was opened. It stays until the
   reader returns, answers, or dismisses it. The browser's own Back is the
   page's history and nothing else: this never listens to it. */
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
