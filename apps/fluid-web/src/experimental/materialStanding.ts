/* HOW THE EXACT THINGS A DECISION NAMES STAND, READ BY THE FORM ITSELF WHERE
 * ITS HOST RESOLVES NONE (the seam left open by review finding F2,
 * ent-4ca09a1119c8; owner request ent-6f6d22b5c962).
 *
 * The form withholds the choices of an approval of ONE EXACT THING that cannot
 * be inspected (`./decisionPresentation` `materialGone`), and it can only do
 * that where somebody resolved the id the question declared. Quiet Chat's Needs
 * you resolves every reference of the request it draws and hands the form its
 * own resolution (`../quiet2/needs/NeedsAbout` `refWordsFor`). THE SAME SHARED
 * FORM DRAWN ANYWHERE ELSE -- Fluid's conversation column, a post, the thread
 * sheet, full screen, the Needs You zone, governance's asks -- resolved
 * nothing, so nothing was claimed there and the guard was inactive. This module
 * is the form resolving for itself, through the SAME read and the same
 * resolution, so no host can say a different thing about the same reference.
 *
 *   GET /fluid/api/needs-you/about?ids=<ask>,<ask>   (mentis/fluid/inspect.py)
 *
 * which is the read Needs you already makes. Nothing is added to the server and
 * no other read is invented: what each declared reference resolves to is that
 * read's own `availability`, drawn by `../quiet2/needs/inspect` exactly as the
 * panel above the form draws it.
 *
 * THE RULES IT KEEPS:
 *   - IT READS ONLY WHAT IT NEEDS. Only for a question whose record declares an
 *     approval of one exact record (`requiredRecord`), only for the questions
 *     actually drawn and still open, and only where the host resolves nothing.
 *     An ordinary choice, a free response, an action approval and a
 *     system-produced permission form cost no read at all.
 *   - A READ THAT HAS NOT ANSWERED IS NOT AN ANSWER. Pending, failed and
 *     answered-by-another-Brain are each said as what they are and claim
 *     NOTHING about any reference -- not that it is there, and not that it is
 *     gone. What follows is only that a choice is not offered yet
 *     (`clarifyNeeded`); the owner's own words, Leave open and the withdrawal
 *     are untouched, and nothing in the record or in the outbox is changed.
 *   - ONE BRAIN. An answer naming another Brain than this reader was bound to
 *     by its first answer -- or a page that has already moved -- shows nothing:
 *     a form is never drawn against one Brain's resolution of another's id.
 *   - NOTHING IS SUBSTITUTED. An id this read resolved nothing for is answered
 *     null, exactly as a host's resolution answers it.
 *   - IT IS BOUNDED. One read per set of questions for the life of the page,
 *     begun when a form that needs it is drawn; at most `IDS_MAX` questions in
 *     one read. There is no timer, no poll and no retry of its own: a read that
 *     failed is read again the next time such a form is drawn.
 *
 * Presentation only: nothing here sends anything, and what a choice records is
 * untouched (`./decisions.ts`). The store is apart from React so it is
 * checkable (`tests/material_standing_unit.ts`). */
import { createContext, useEffect, useSyncExternalStore } from 'react'
import { brainKeyOf, createBinding, page, type BrainId } from '../brainBinding'
import { fluidFetch } from '../fluid/http'
import { refsOf, type About, type Ref } from '../quiet2/needs/inspect'
import type { MaterialRead, RefStanding, Standing } from './decisionPresentation'

const PATH = '/fluid/api/needs-you/about?ids='

/** At most this many questions read at once. The server takes 64
 *  (`mentis/fluid/read.py` BATCH); a form asking more approvals of exact
 *  material than this is not read at all, and says so rather than reading some. */
export const IDS_MAX = 24

/** What the form says where it has more questions needing material than one
 *  read covers. Nothing is claimed about any of their references. */
export const TOO_MANY = 'this form asks more approvals of exact material than one read covers, so it was not read.'
/** What it says where the server now answers for another Brain. */
export const OTHER_BRAIN = 'it was answered for another Brain than this page is showing, so nothing of it is used; reload the page.'

/** The answer, as `GET /fluid/api/needs-you/about?ids=` gives it. */
export interface AboutAnswer { about?: About[]; brain?: BrainId; error?: string }

/** What was read, by the exact set of questions it was read for. */
export interface StandingStore {
  /** a read begins for this set: its generation, later than every earlier one */
  begin(key: string): number
  /** that read's answer, or its failure. Ignored, and false, where a later read
   *  for the same set has begun. */
  took(key: string, gen: number, got: AboutAnswer | null, why?: string): boolean
  /** every reference that read resolved, by its exact id; null where there is
   *  no answer in hand (none yet, it failed, or another Brain answered) */
  shown(key: string): Map<string, Ref> | null
  /** why there is nothing in hand, or null while a read is still on its way */
  why(key: string): string | null
  /** a read begun for this set has not finished */
  reading(key: string): boolean
}

export function createStandingStore(binding = createBinding()): StandingStore {
  const at = new Map<string, { begun: number; ended: number; shown: Map<string, Ref> | null; why: string | null }>()
  let gens = 0
  return {
    begin(key) {
      const now = at.get(key) ?? { begun: 0, ended: 0, shown: null, why: null }
      now.begun = ++gens
      /* what was in hand stays in hand while it is read again: it is one
         Brain's resolution of the same ids, not a claim about another's */
      at.set(key, now)
      return now.begun
    },
    took(key, gen, got, why) {
      const now = at.get(key)
      if (!now || gen !== now.begun) return false                  // superseded: not the latest read
      now.ended = gen
      if (!got || !Array.isArray(got.about)) {
        now.shown = null
        now.why = why ?? got?.error ?? 'the server did not answer.'
        return true
      }
      if (!binding.saw(brainKeyOf(got.brain)) || binding.moved()) {
        now.shown = null
        now.why = OTHER_BRAIN
        return true
      }
      const refs = new Map<string, Ref>()
      for (const about of got.about) {
        for (const [id, r] of refsOf(about)) if (!refs.has(id)) refs.set(id, r)
      }
      now.shown = refs
      now.why = null
      return true
    },
    shown: (key) => (binding.moved() ? null : at.get(key)?.shown ?? null),
    why: (key) => (binding.moved() ? OTHER_BRAIN : at.get(key)?.why ?? null),
    reading(key) { const now = at.get(key); return !!now && now.ended < now.begun },
  }
}

/* -- the page's own reader ---------------------------------------------------
   One store for the page, so a form drawn in two places at once reads once and
   both show the same resolution. In memory: a reload reads again. */
const reader = createBinding()
const store = createStandingStore(reader)
const heard = new Set<() => void>()
let version = 0
const changed = () => { version++; heard.forEach((f) => f()) }
reader.subscribe(changed)
/* and the page's own binding: once Quiet Chat has moved, this is drawn again */
page.subscribe(changed)
const subscribe = (f: () => void) => { heard.add(f); return () => { heard.delete(f) } }

/** The questions this read is for, as one key: deduplicated and in a fixed
 *  order, so the same set is one read however the form was drawn. */
export const keyOf = (ids: readonly string[]): string => [...new Set(ids)].sort().join(',')

async function read(key: string): Promise<void> {
  const gen = store.begin(key)
  changed()
  try {
    const res = await fluidFetch(PATH + encodeURIComponent(key), { headers: { 'X-Mentis-Client': '1' }, cache: 'no-store' })
    const body = await res.json().catch(() => null) as AboutAnswer | null
    if (!res.ok) store.took(key, gen, null, body?.error ?? `the server answered ${res.status}.`)
    else store.took(key, gen, body)
  } catch (e) {
    store.took(key, gen, null, String(e instanceof Error ? e.message : e))
  }
  changed()
}

/** HOW THE EXACT THINGS A FORM NAMES STAND, as the form itself read them, and
 *  what that read has come to. */
export interface OwnStanding {
  /** the same shape a host supplies (`../refWords` `standing`): what this read
   *  resolved for one exact id, or null where it resolved nothing */
  standing: Standing
  /** whether that read answered, and why not where it has not
   *  (`./decisionPresentation` `MaterialRead`); null where no read is needed */
  read: MaterialRead | null
}

export const NONE: OwnStanding = { standing: null, read: null }

/** What the form drawn here resolved for itself, where it had to: given to the
 *  questions under it so that `Presented` and `Open` read the one resolution. */
export const OwnStandingContext = createContext<OwnStanding | null>(null)

/** Read, for these questions, how the exact material they declare stands. An
 *  empty list reads nothing and claims nothing. */
export function useOwnStanding(ids: readonly string[]): OwnStanding {
  const key = ids.length ? keyOf(ids) : ''
  const many = ids.length > IDS_MAX
  useSyncExternalStore(subscribe, () => version)
  useEffect(() => {
    /* ONE READ PER SET, AND NO RETRY OF ITS OWN: begun where there is nothing
       in hand and nothing on its way. A read that failed is read again the next
       time a form needing it is drawn, which is this effect running again. */
    if (!key || many) return
    if (store.shown(key) || store.reading(key)) return
    void read(key)
  }, [key, many])
  if (!key) return NONE
  /* THE PAGE'S OWN BINDING TOO: where Quiet Chat has already moved to another
     Brain, nothing this reader holds is used either. */
  if (many) return { standing: null, read: { settled: false, why: TOO_MANY } }
  if (page.moved()) return { standing: null, read: { settled: false, why: OTHER_BRAIN } }
  const refs = store.shown(key)
  if (!refs) return { standing: null, read: { settled: false, why: store.why(key) } }
  const standing: Standing = (id: string): RefStanding | null => {
    const r = refs.get(id)
    return r ? { available: r.available, state: r.state, why: r.why } : null
  }
  return { standing, read: { settled: true, why: null } }
}
