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
 *   - WHEN A READ BEGINS, NOTHING EARLIER IS SHOWN ANY MORE. The list itself
 *     may have just been read from another Brain (a deployment or restore on
 *     the same address keeps the same ids), so the earlier details could sit
 *     beside a decision they are not about. Until the new read is over the
 *     item says its details are being read; the decision stays usable;
 *   - A READ IS PUBLISHED WHOLE, when it is over: its batches are gathered
 *     apart and shown together, and only if every batch named the Brain the
 *     page is bound to (below);
 *   - a read, or a batch of it, that fails says the details could not be
 *     read;
 *   - NEEDS YOU IS BOUND TO ONE BRAIN FOR THE PAGE: the Brain the page first
 *     got an answer from. A later answer from another one -- a details read,
 *     or the identity read made each time the list is fetched again -- means
 *     the server on this address now serves a different Brain than the one
 *     this page has been showing. Nothing more is shown as current: Needs you
 *     says so and asks for a reload before deciding (`brainChanged`). Every
 *     other read of the page is as stale as it is anywhere in the app; this
 *     only stops Needs you putting one Brain's subject beside a decision that
 *     another Brain will receive.
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

/** Which Brain the page's Needs you is bound to, and whether another has answered since. */
export interface PageBrain {
  /** an answer named this Brain (null: it named none). False where it is not the bound one */
  saw(brain: string | null): boolean
  /** the server now serves another Brain than the page was bound to */
  changed(): boolean
}

export function createPageBrain(): PageBrain {
  let bound: string | undefined
  let moved = false
  return {
    saw(brain) {
      if (brain === null) return !moved                                     // naming none decides nothing
      if (bound === undefined) bound = brain
      if (brain !== bound) moved = true
      return !moved
    },
    changed: () => moved,
  }
}

export function createAboutStore(page: PageBrain = createPageBrain()): AboutStore {
  /** what is SHOWN: the last read that was published, by request */
  const held = new Map<string, { about: About; opening: number }>()
  const failed = new Map<string, { why: string; opening: number }>()
  /** per opening: the latest generation begun, and what that read has gathered so far */
  const at = new Map<number, {
    begun: number; ended: number
    about: Map<string, About>; failed: Map<string, string>; brains: Set<string | null>
  }>()
  let gens = 0
  const clear = (opening: number) => {
    for (const [k, h] of [...held]) if (h.opening === opening) held.delete(k)
    for (const [k, f] of [...failed]) if (f.opening === opening) failed.delete(k)
  }
  return {
    begin(opening) {
      for (const k of [...at.keys()]) if (k !== opening) at.delete(k)
      for (const [k, h] of [...held]) if (h.opening !== opening) held.delete(k)
      for (const [k, f] of [...failed]) if (f.opening !== opening) failed.delete(k)
      const ended = at.get(opening)?.ended ?? 0
      const now = { begun: ++gens, ended, about: new Map<string, About>(), failed: new Map<string, string>(), brains: new Set<string | null>() }
      at.set(opening, now)
      clear(opening)                                                   // nothing earlier is shown while this one is read
      return now.begun
    },
    took(ids, opening, gen, got, why) {
      const now = at.get(opening)
      if (!now || gen !== now.begun) return false                      // superseded: not the latest read
      if (!got?.about) {
        for (const id of ids) { now.about.delete(id); now.failed.set(id, why ?? 'the server did not answer') }
        return true
      }
      now.brains.add(brainOf(got.brain))
      const said = new Set<string>()
      for (const a of got.about) { now.about.set(a.id, a); now.failed.delete(a.id); said.add(a.id) }
      for (const id of ids) if (!said.has(id)) now.failed.set(id, 'the server did not say')
      return true
    },
    done(opening, gen) {
      const now = at.get(opening)
      if (!now || gen !== now.begun) return                               // a superseded read ending changes nothing
      now.ended = gen
      clear(opening)
      const named = [...now.brains]
      if (named.some((b) => !page.saw(b)) || page.changed()) {
        /* another Brain than the page was bound to answered: nothing it said is shown */
        for (const id of [...now.about.keys(), ...now.failed.keys()]) failed.set(id, { why: OTHER_BRAIN, opening })
        return
      }
      for (const [id, a] of now.about) held.set(id, { about: a, opening })
      for (const [id, why] of now.failed) failed.set(id, { why, opening })
    },
    reading(opening) { const now = at.get(opening); return !!now && now.ended < now.begun },
    of: (ask, opening) => { const h = held.get(ask); return h && h.opening === opening ? h.about : null },
    errorOf: (ask, opening) => { const f = failed.get(ask); return f && f.opening === opening ? f.why : null },
  }
}

/** what Needs you says where the server now serves another Brain than this page was showing */
export const OTHER_BRAIN = 'this page was showing another Brain than the server serves now; reload the page before deciding'

const pageBrain = createPageBrain()
const about = createAboutStore(pageBrain)
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

/** WHICH BRAIN THE SERVER SERVES NOW, asked past every cache, each time the list is fetched
 *  again: a list that reads exactly as before can still be another Brain's. */
async function checkBrain(): Promise<void> {
  try {
    const res = await fluidFetch('/api/brain?identity=1', { headers: { 'X-Mentis-Client': '1' }, cache: 'no-store' })
    if (!res.ok) return
    const was = pageBrain.changed()
    pageBrain.saw(brainOf(await res.json().catch(() => null) as Brain))
    if (pageBrain.changed() !== was) changed()
  } catch { /* unread: decides nothing */ }
}

/** What these items are about, read by this opening of the list (`opening`) and again whenever
 *  what the list says changes (`stamp`); and the server's Brain checked each time the list is
 *  fetched again at all (`fetched`). */
export function useAbout(items: NeedsItem[], opening: number, stamp: unknown, fetched?: unknown): {
  of: (it: NeedsItem) => About | null; errorOf: (it: NeedsItem) => string | null
  /** a read is on its way: what is shown is being read again */
  reading: boolean
  /** the server now serves another Brain than this page was showing: nothing here is current */
  brainChanged: boolean
} {
  const key = items.map(askOf).join(',')
  useSyncExternalStore(subscribe, () => version)
  useEffect(() => { if (key) void read(key.split(','), opening) }, [key, opening, stamp])
  useEffect(() => { if (fetched !== undefined) void checkBrain() }, [fetched])
  const moved = pageBrain.changed()
  return {
    of: (it) => moved ? null : about.of(askOf(it), opening),
    errorOf: (it) => moved ? OTHER_BRAIN : about.errorOf(askOf(it), opening),
    reading: about.reading(opening),
    brainChanged: moved,
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
