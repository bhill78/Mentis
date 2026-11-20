/* WHAT EACH NEEDS YOU ITEM IS ABOUT, READ FOR THE LIST
 * (`GET /fluid/api/needs-you/about?ids=`), and THE WAY BACK TO A DECISION
 * after one of its references was opened.
 *
 * WHAT IS SHOWN IS WHAT THE LATEST READ OF THIS OPENING OF THE LIST SAID, AND
 * NOTHING OLDER:
 *   - every opening of the list reads afresh, and reads again whenever the
 *     list itself is read again. Details read by an earlier opening are never
 *     drawn as current;
 *   - EACH READ HAS A GENERATION, and only the latest one begun for an opening
 *     may change what is shown: an older answer arriving late is discarded;
 *   - while a later read is on its way, what is shown is said to be BEING
 *     READ AGAIN, not current;
 *   - a read that fails REMOVES what was held for those requests and says the
 *     details could not be read. The decision itself stays usable;
 *   - the answer names the Brain that gave it (`brain`). If that is another
 *     Brain than the opening's previous answer named, everything that one
 *     said is dropped and only the new answer is shown.
 *
 * Nothing here is kept beyond the page, and no draft depends on any of it. */
import { useEffect, useSyncExternalStore } from 'react'
import { fluidFetch } from '../../fluid/http'
import type { NeedsItem } from '../../needsItems'
import type { About } from './inspect'

const PATH = '/fluid/api/needs-you/about'
/** the server's batch (mentis/fluid/read.py BATCH) */
const BATCH = 64

type Brain = { corpus_id?: string | null; corpus_path?: string | null } | null | undefined
const brainOf = (b: Brain): string | null => ((b?.corpus_id ?? '').trim() ? `${b!.corpus_id}@${b!.corpus_path ?? ''}` : null)

/** What was read, by request: a store apart from React, so it is checkable. */
export interface AboutStore {
  /** a read begins for this opening: its generation, later than every earlier one */
  begin(opening: number): number
  /** one answer of that read (`brain` is which Brain answered), or its failure.
   *  Ignored, and false, where a later read has begun for the opening. */
  took(ids: string[], opening: number, gen: number, got: { about?: About[]; brain?: Brain } | null, why?: string): boolean
  /** that read is over */
  done(opening: number, gen: number): void
  /** a read begun for this opening has not finished: what is shown is being read again */
  reading(opening: number): boolean
  /** what this opening's latest read said of a request, or null */
  of(ask: string, opening: number): About | null
  /** why it could not be read, where the latest read for it failed */
  errorOf(ask: string, opening: number): string | null
}

export function createAboutStore(): AboutStore {
  const held = new Map<string, { about: About; opening: number }>()
  const failed = new Map<string, { why: string; opening: number }>()
  /** per opening: the latest generation begun, the latest finished, and the Brain last named */
  const at = new Map<number, { begun: number; ended: number; brain: string | null | undefined }>()
  let gens = 0
  return {
    begin(opening) {
      for (const k of [...at.keys()]) if (k !== opening) at.delete(k)
      const now = at.get(opening) ?? { begun: 0, ended: 0, brain: undefined }
      now.begun = ++gens
      at.set(opening, now)
      return now.begun
    },
    took(ids, opening, gen, got, why) {
      const now = at.get(opening)
      if (!now || gen !== now.begun) return false                      // superseded: not the latest read
      if (!got?.about) {
        for (const id of ids) { held.delete(id); failed.set(id, { why: why ?? 'the server did not answer', opening }) }
        return true
      }
      const from = brainOf(got.brain)
      if (now.brain !== undefined && from !== now.brain) {
        /* another Brain answers now: nothing the earlier one said is shown */
        for (const [k, h] of [...held]) if (h.opening === opening) held.delete(k)
        for (const [k, f] of [...failed]) if (f.opening === opening) failed.delete(k)
      }
      now.brain = from
      const said = new Set<string>()
      for (const a of got.about) { held.set(a.id, { about: a, opening }); failed.delete(a.id); said.add(a.id) }
      for (const id of ids) if (!said.has(id)) { held.delete(id); failed.set(id, { why: 'the server did not say', opening }) }
      return true
    },
    done(opening, gen) { const now = at.get(opening); if (now && gen > now.ended) now.ended = gen },
    reading(opening) { const now = at.get(opening); return !!now && now.ended < now.begun },
    of: (ask, opening) => { const h = held.get(ask); return h && h.opening === opening ? h.about : null },
    errorOf: (ask, opening) => { const f = failed.get(ask); return f && f.opening === opening ? f.why : null },
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
  const gen = about.begin(opening)
  changed()
  for (let i = 0; i < ids.length; i += BATCH) {
    const part = ids.slice(i, i + BATCH)
    try {
      const res = await fluidFetch(`${PATH}?ids=${part.map(encodeURIComponent).join(',')}`, { headers: { 'X-Mentis-Client': '1' } })
      const body = await res.json().catch(() => null) as { about?: About[]; brain?: Brain; error?: string } | null
      if (!res.ok || !body?.about) about.took(part, opening, gen, null, body?.error ?? (res.statusText || String(res.status)))
      else about.took(part, opening, gen, body)
    } catch (e) {
      about.took(part, opening, gen, null, String(e instanceof Error ? e.message : e))
    }
  }
  about.done(opening, gen)
  changed()
}

/** What these items are about, read by this opening of the list (`opening`)
 *  and again whenever the list itself is read again (`stamp`). */
export function useAbout(items: NeedsItem[], opening: number, stamp: unknown): {
  of: (it: NeedsItem) => About | null; errorOf: (it: NeedsItem) => string | null
  /** a read is on its way: what is shown is being read again */
  reading: boolean
} {
  const key = items.map(askOf).join(',')
  useSyncExternalStore(subscribe, () => version)
  useEffect(() => { if (key) void read(key.split(','), opening) }, [key, opening, stamp])
  return {
    of: (it) => about.of(askOf(it), opening),
    errorOf: (it) => about.errorOf(askOf(it), opening),
    reading: about.reading(opening),
  }
}

/* -- answering here, kept open ------------------------------------------------
   Which items have their form open in the list, for the page. The form's own
   draft (what is chosen and typed) is the form's
   (experimental/types/decision.tsx); this is only whether it is unfolded,
   kept so that coming back from a reference finds the form as it was left.
   In memory: a reload starts with every form folded. */
const unfolded = new Set<string>()
export function useUnfolded(key: string): [boolean, (open: boolean) => void] {
  const open = useSyncExternalStore(subscribe, () => unfolded.has(key))
  return [open, (to) => { if (to) unfolded.add(key); else unfolded.delete(key); changed() }]
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
