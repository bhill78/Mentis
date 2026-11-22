/* WHAT NEEDS YOU LISTS, WHAT EACH ITEM IS ABOUT, AND WHICH BRAIN SAID SO -- ONE ANSWER
 * (`GET /fluid/api/needs-you/about?items=1`), and THE WAY BACK TO A DECISION after one of its
 * references was opened.
 *
 * ONE ANSWER, ONE BRAIN. The list, every item's subject and evidence, and the Brain that read
 * them come from one read on the server, so they can never be two Brains' (a deployment or
 * restore on the same address keeps the same ids). The panel draws its list and details from
 * that answer only:
 *   - EACH READ HAS A GENERATION, and only the latest one begun for an opening may change what
 *     is shown: an older answer arriving late is discarded;
 *   - while a later read is on its way, the answer last shown stays (it is one Brain's list
 *     with that same Brain's details) and is said to be being read again;
 *   - a read that fails shows nothing it said: the panel falls back to the plain list, without
 *     details, and says the details could not be read;
 *   - NEEDS YOU IS BOUND TO ONE BRAIN FOR THE PAGE: the Brain of the first answer. An answer
 *     from another one means the server on this address now serves a different Brain than the
 *     one this page has been showing: nothing is shown as current, and Needs you asks for a
 *     reload before deciding (`brainChanged`). Only a reload binds the page again.
 *
 * Nothing here is kept beyond the page. */
import { useEffect, useSyncExternalStore } from 'react'
import { fluidFetch } from '../../fluid/http'
import { brainKeyOf, page, type BrainId } from '../../brainBinding'
import type { NeedsItem } from '../../needsItems'
import type { LaunchContext } from '../results/launch'
import type { About } from './inspect'

const PATH = '/fluid/api/needs-you/about?items=1'

/** Which Brain answered: its id, and its instance fingerprint (a copy served elsewhere or
 *  restored in place shares the id, not the fingerprint). Never where it is. */
type Brain = BrainId
const brainOf = brainKeyOf

/** The request an item is read by: its first ask (a form answers whole). */
export const askOf = (it: Pick<NeedsItem, 'asks' | 'key'>) => it.asks[0] ?? it.key

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

/** One answer, shown whole: the list, its summary words, every ask it holds, and each item's details. */
export interface Bound { items: NeedsItem[]; words: string | null; asks: string[]; about: Map<string, About> }

/** The answer from the server, as it comes. */
export interface BoundAnswer { items?: NeedsItem[]; words?: string | null; about?: About[]; brain?: Brain; error?: string }

/** What was read: a store apart from React, so it is checkable. */
export interface BoundStore {
  /** a read begins for this opening: its generation, later than every earlier one */
  begin(opening: number): number
  /** that read's answer, or its failure. Ignored, and false, where a later read has begun. */
  took(opening: number, gen: number, got: BoundAnswer | null, why?: string): boolean
  /** the answer shown for this opening, or null: none yet, it failed, or another Brain answered */
  shown(opening: number): Bound | null
  /** why nothing is shown, where the latest read failed or another Brain answered */
  why(opening: number): string | null
  /** a read begun for this opening has not finished */
  reading(opening: number): boolean
}

/** what Needs you says where the server now serves another Brain than this page was showing */
export const OTHER_BRAIN = 'this page was showing another Brain than the server serves now; reload the page before deciding'

export function createBoundStore(page: PageBrain = createPageBrain()): BoundStore {
  const at = new Map<number, { begun: number; ended: number; shown: Bound | null; why: string | null }>()
  let gens = 0
  return {
    begin(opening) {
      for (const k of [...at.keys()]) if (k !== opening) at.delete(k)       // an opening that is over shows nothing
      const now = at.get(opening) ?? { begun: 0, ended: 0, shown: null, why: null }
      now.begun = ++gens
      at.set(opening, now)
      return now.begun
    },
    took(opening, gen, got, why) {
      const now = at.get(opening)
      if (!now || gen !== now.begun) return false                           // superseded: not the latest read
      now.ended = gen
      if (!got || !Array.isArray(got.items) || !Array.isArray(got.about)) {
        now.shown = null
        now.why = why ?? got?.error ?? 'the server did not answer'
        return true
      }
      if (!page.saw(brainOf(got.brain)) || page.changed()) {
        now.shown = null
        now.why = OTHER_BRAIN
        return true
      }
      now.shown = {
        items: got.items, words: got.words ?? null,
        asks: got.items.flatMap((it) => it.asks),
        about: new Map(got.about.map((a) => [a.id, a])),
      }
      now.why = null
      return true
    },
    shown: (opening) => at.get(opening)?.shown ?? null,
    why: (opening) => at.get(opening)?.why ?? null,
    reading(opening) { const now = at.get(opening); return !!now && now.ended < now.begun },
  }
}

/* THE PAGE'S OWN BINDING (`../../brainBinding`): the Brain Quiet Chat was opened on, which every
   write names. Needs you's answers bind it too, and an answer from another Brain -- or a write
   the server refused as another Brain's -- moves the whole page, not this list alone. */
const pageBrain: PageBrain = { saw: (b) => page.saw(b), changed: () => page.moved() }
const bound = createBoundStore(pageBrain)
const heard = new Set<() => void>()
let version = 0
const changed = () => { version++; heard.forEach((f) => f()) }
page.subscribe(changed)
const subscribe = (f: () => void) => { heard.add(f); return () => { heard.delete(f) } }

async function read(opening: number): Promise<void> {
  const gen = bound.begin(opening)
  changed()
  try {
    const res = await fluidFetch(PATH, { headers: { 'X-Mentis-Client': '1' }, cache: 'no-store' })
    const body = await res.json().catch(() => null) as BoundAnswer | null
    if (!res.ok) bound.took(opening, gen, null, body?.error ?? (res.statusText || String(res.status)))
    else bound.took(opening, gen, body)
  } catch (e) {
    bound.took(opening, gen, null, String(e instanceof Error ? e.message : e))
  }
  changed()
}

/** Needs you's list and details, read by this opening of the list (`opening`) and again each
 *  time the plain list is fetched again (`fetched`: on record movement and every minute). */
export function useNeedsBound(opening: number, fetched: unknown): {
  /** the answer shown, or null (none yet, failed, or another Brain answered) */
  shown: Bound | null
  /** the item's details, from the answer shown only */
  of: (it: NeedsItem) => About | null
  /** why there are no details for this item */
  errorOf: (it: NeedsItem) => string | null
  /** a read is on its way */
  reading: boolean
  /** no answer has been taken yet for this opening */
  first: boolean
  /** the server now serves another Brain than this page was showing: nothing here is current */
  brainChanged: boolean
} {
  useSyncExternalStore(subscribe, () => version)
  useEffect(() => { void read(opening) }, [opening, fetched])
  const moved = pageBrain.changed()
  const shown = moved ? null : bound.shown(opening)
  const why = moved ? OTHER_BRAIN : bound.why(opening)
  return {
    shown,
    of: (it) => shown?.about.get(askOf(it)) ?? null,
    errorOf: (it) => shown ? (shown.about.has(askOf(it)) ? null : 'the server did not say') : why,
    reading: bound.reading(opening),
    first: !shown && !why,
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
  /** WHERE THE READER WAS WHEN THEY LEFT (HOST-INTEGRATION.md §3.1).
   *
   *  The launch the dock built for the press, so that ONE control puts back
   *  the PLACE -- the originating conversation and whatever held the centre
   *  over it -- together with this pending item, its chosen option and its
   *  typed words. Without it the way back restored the panel only and left
   *  the centre and the address on whichever conversation the evidence
   *  happened to be read in.
   *
   *  IDENTITY AND POSITION, NEVER AN ANSWER (`results/launch.ts`
   *  `LaunchContext`): the draft is named by its key in the existing draft
   *  store, and the decision by its form, question, item and reference.
   *  Applying it is the result module's own gated operation
   *  (`results/mount.ts` `takeReturn`), which asks which Brain the server
   *  serves at the moment the page would be written to.
   *
   *  OPTIONAL, because a page with no mounted result opener has no launch to
   *  give: there the way back restores the panel only, exactly as before. */
  launch?: LaunchContext | null
  at: number
}
let left: Leave | null = null
export function leaveFor(l: Omit<Leave, 'at'>) { left = { ...l, at: Date.now() }; changed() }
export function clearLeave() { if (left) { left = null; changed() } }
export function useLeave(): Leave | null { return useSyncExternalStore(subscribe, () => left) }
export const leaveNow = () => left
