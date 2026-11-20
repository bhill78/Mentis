/* WHAT EACH NEEDS YOU ITEM IS ABOUT, READ FOR THE LIST
 * (`GET /fluid/api/needs-you/about?ids=`), and THE WAY BACK TO A DECISION
 * after one of its references was opened.
 *
 * WHICH BRAIN IS ANSWERING IS READ FROM EACH ANSWER, NOT REMEMBERED: details
 * and drafts are both held under the identity the opening's own answer gave,
 * never one the page read when it loaded, because the same address can start
 * serving another Brain while the tab stays open (re-review, 2026-11-20).
 *
 * WHAT IS SHOWN IS WHAT THIS OPENING OF THE LIST READ, FROM THAT BRAIN, AND
 * NOTHING OLDER (independent review, 2026-11-20). The same address can serve
 * another Brain later, and a restored or copied Brain reuses ids, so details
 * read earlier are never drawn as current:
 *   - each reading is marked with the Brain it came from (the server says
 *     which, `brain`) and the opening of the list that asked for it;
 *   - only a reading for this Brain and this opening is shown. Until it
 *     arrives the item says it is being read;
 *   - a read that fails REMOVES what was held for those requests and says
 *     the details could not be read. The decision itself stays usable;
 *   - when another Brain starts answering, what the earlier one said is no
 *     longer shown, and the forms start empty under the new identity. */
import { useEffect, useSyncExternalStore } from 'react'
import { scopeOf } from '../../experimental/draftKeep'
import { fluidFetch } from '../../fluid/http'
import type { NeedsItem } from '../../needsItems'
import type { About } from './inspect'

const PATH = '/fluid/api/needs-you/about'
/** the server's batch (mentis/fluid/read.py BATCH) */
const BATCH = 64
interface Held { about: About; scope: string | null; opening: number }
/** What was read, by request: a store apart from React, so it is checkable. */
export interface AboutStore {
  /** WHICH BRAIN ANSWERED THIS OPENING'S LATEST READ: undefined before any
   *  answer, null where the read failed or the answer did not say. This --
   *  never an identity remembered from when the page loaded -- is what the
   *  opening's drafts are kept and restored under. */
  scope(opening: number): string | null | undefined
  /** what this opening read for a request, from the Brain now answering it, or null */
  of(ask: string, opening: number): About | null
  /** why it could not be read, where the last read for it failed */
  errorOf(ask: string, opening: number): string | null
  /** one answer from the server (`brain` is which Brain answered), or a failure */
  took(ids: string[], opening: number, got: { about?: About[]; brain?: { corpus_id?: string | null; corpus_path?: string | null } | null } | null, why?: string): void
}

export function createAboutStore(): AboutStore {
  const held = new Map<string, Held>()
  const failed = new Map<string, { why: string; opening: number }>()
  const answered = new Map<number, string | null>()
  return {
    scope: (opening) => answered.get(opening),
    of: (ask, opening) => {
      const h = held.get(ask)
      const now = answered.get(opening)
      /* only what the Brain NOW answering this opening said: details an
         earlier answer of this opening gave under another identity are not it */
      return h && h.opening === opening && now !== undefined && h.scope === now ? h.about : null
    },
    errorOf: (ask, opening) => {
      const f = failed.get(ask)
      return f && f.opening === opening ? f.why : null
    },
    took(ids, opening, got, why) {
      for (const k of [...answered.keys()]) if (k !== opening) answered.delete(k)
      if (!got?.about) {
        /* no answer: which Brain this is is not known now */
        answered.set(opening, null)
        for (const id of ids) { held.delete(id); failed.set(id, { why: why ?? 'the server did not answer', opening }) }
        return
      }
      const from = got.brain ? scopeOf(got.brain) : null
      answered.set(opening, from)
      const said = new Set<string>()
      for (const a of got.about) { held.set(a.id, { about: a, scope: from, opening }); failed.delete(a.id); said.add(a.id) }
      for (const id of ids) if (!said.has(id)) { held.delete(id); failed.set(id, { why: 'the server did not say', opening }) }
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

async function read(ids: string[], opening: number): Promise<void> {
  for (let i = 0; i < ids.length; i += BATCH) {
    const part = ids.slice(i, i + BATCH)
    try {
      const res = await fluidFetch(`${PATH}?ids=${part.map(encodeURIComponent).join(',')}`, { headers: { 'X-Mentis-Client': '1' } })
      const body = await res.json().catch(() => null) as { about?: About[]; brain?: { corpus_id?: string; corpus_path?: string | null }; error?: string } | null
      if (!res.ok || !body?.about) about.took(part, opening, null, body?.error ?? (res.statusText || String(res.status)))
      else about.took(part, opening, body)
    } catch (e) {
      about.took(part, opening, null, String(e instanceof Error ? e.message : e))
    }
  }
  changed()
}

/** What these items are about, read by this opening of the list (`opening`)
 *  and again whenever the list itself is read again (`stamp`). `scope` is the
 *  Brain that answered the latest of those reads: undefined until one has. */
export function useAbout(items: NeedsItem[], opening: number, stamp: unknown): {
  of: (it: NeedsItem) => About | null; errorOf: (it: NeedsItem) => string | null
  scope: string | null | undefined
  /** every item was answered for, by the Brain `scope` names */
  whole: boolean
} {
  const key = items.map(askOf).join(',')
  useSyncExternalStore(subscribe, () => version)
  useEffect(() => { if (key) void read(key.split(','), opening) }, [key, opening, stamp])
  const scope = about.scope(opening)
  return {
    of: (it) => about.of(askOf(it), opening),
    errorOf: (it) => about.errorOf(askOf(it), opening),
    scope,
    whole: !!scope && items.every((it) => { const a = about.of(askOf(it), opening); return !!a && !a.error }),
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
