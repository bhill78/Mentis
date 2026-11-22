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
 *   - AND NEITHER IS AN HTTP 200 THAT ESTABLISHED NOTHING (review finding B1,
 *     ent-5b7ef83a4e40). The answer is taken QUESTION BY QUESTION, and a
 *     question's material is established only where THAT question's own item
 *     came back without an error, projected its references, declared the one
 *     exact record, and carried that server's resolution OF THAT EXACT ID. An
 *     item that errored, a server that does not project `question_references`,
 *     a declaration with no `availability`, an id that is not the one the
 *     question declares, or a question the answer skipped are each unestablished
 *     -- said as the read not having established it, NEVER as the record being
 *     missing, and never filled in from another question's resolution.
 *   - ONE BRAIN. An answer naming another Brain than this reader was bound to
 *     by its first answer -- or a page that has already moved -- shows nothing:
 *     a form is never drawn against one Brain's resolution of another's id.
 *   - NOTHING IS SUBSTITUTED. An id this read resolved nothing for is answered
 *     null, exactly as a host's resolution answers it.
 *   - IT IS BOUNDED, AND IT IS NOT KEPT PAST THE DRAWING IT WAS MADE FOR
 *     (review finding B2). One read per set of questions while a form needing
 *     that set is drawn, begun when such a form is drawn; at most `IDS_MAX`
 *     questions in one read. When the last form needing the set stops being
 *     drawn, what was read for it is let go, so the next drawing reads again
 *     and an answer made against material that has since changed is not offered
 *     from a result nobody read again. There is still no timer, no poll and no
 *     retry of its own.
 *   - AND IT IS READ AGAIN AT THE SEAM WHERE IT MATTERS AS MUCH AS WHEN IT WAS
 *     DRAWN: before a recorded choice is sent, and before an attempted one is
 *     sent again (`readAgain`). One read per attempt, awaited, writing nothing:
 *     the answer's own key, the owner's words and the outbox are untouched by
 *     it, and a read that does not establish the material simply means the
 *     choice is not sent.
 *   - AND THAT READING IS ANSWERED BY ITS OWN READ OR BY A LATER ONE, NEVER BY
 *     WHAT WAS IN HAND BEFORE IT BEGAN (review finding R1 on B2,
 *     ent-f863f84301fc). The same question drawn in two places -- a post and
 *     its thread -- reads for one set, so two readings begun at the same moment
 *     are two reads of it, and the store keeps only the later one's answer. The
 *     earlier reading is then holding nothing of its own: what stayed in hand
 *     is from BEFORE it began, which is exactly the answer it was made to
 *     replace. So a reading says whether what the page holds now was read no
 *     earlier than it began (`Checked`), and a sender turns on that and on what
 *     the read came to -- on nothing else.
 *
 * Presentation only: nothing here sends anything, and what a choice records is
 * untouched (`./decisions.ts`). The store is apart from React so it is
 * checkable (`tests/material_standing_unit.ts`). */
import { createContext, useEffect, useSyncExternalStore } from 'react'
import { brainKeyOf, createBinding, page, type BrainId } from '../brainBinding'
import { fluidFetch } from '../fluid/http'
import { PRIMARY_ROLE, type About, type Ref } from '../quiet2/needs/inspect'
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

/* -- WHY ONE QUESTION'S MATERIAL WAS NOT ESTABLISHED BY A READ THAT ANSWERED.
      Each says what became of THE READ. None of them says anything whatever
      about the record the question names: not that this Brain holds it, and
      not that it does not (review finding B1). */

/** the answer carried no item for this question at all */
export const NOT_ANSWERED_FOR = 'the read answered without saying anything about this question, so how the thing it names stands was not established.'
/** the server's own per-item failure envelope, in its own words */
export const READ_SAID = 'the read could not say how this question stands:'
/** the answer did not project what this question declares */
export const NOT_PROJECTED = 'the read did not say which exact thing this question is about, so how that thing stands was not established.'
/** it named it without saying how it stands */
export const NOT_RESOLVED = 'the read named the thing this question is about without saying how it stands, so nothing of it was established.'
/** it answered about some other id than the one the question declares */
export const ANOTHER_ID = 'the read answered about a different record than the one this question declares, so nothing of that one was established.'

/** The answer, as `GET /fluid/api/needs-you/about?ids=` gives it. */
export interface AboutAnswer { about?: About[]; brain?: BrainId; error?: string }

/** What one question's material came to in a read that answered: the exact
 *  record id that read resolved for it, or why it established nothing. */
export type Came = { id: string } | { why: string }

/** What was read, by the exact set of questions it was read for. */
export interface StandingStore {
  /** a read begins for this set: its generation, later than every earlier one */
  begin(key: string): number
  /** that read's answer, or its failure. Ignored, and false, where a later read
   *  for the same set has begun. */
  took(key: string, gen: number, got: AboutAnswer | null, why?: string): boolean
  /** every exact record this read established, by its exact id; null where
   *  there is no answer in hand (none yet, it failed, or another Brain
   *  answered) */
  shown(key: string): Map<string, Ref> | null
  /** why there is nothing in hand AT ALL, or null while a read is still on its
   *  way (and null where the read answered) */
  why(key: string): string | null
  /** WHAT THAT READ CAME TO FOR ONE QUESTION AND THE ONE EXACT RECORD IT
   *  DECLARES -- the only thing any choice of that question turns on. Settled
   *  only where this read established THAT id FOR THAT question. */
  answeredFor(key: string, question: string, required: string): MaterialRead
  /** a read begun for this set has not finished */
  reading(key: string): boolean
  /** THE READ WHOSE ANSWER IS IN HAND for this set, by its generation, and 0
   *  where none is: nothing was read, what was read was let go of, or every
   *  read since was superseded before its answer could be taken. A reading made
   *  at a sending seam is answered only where this is its own generation or a
   *  later one (review finding R1 on B2) -- the one thing that tells a late
   *  answer from a stale one, since both leave an earlier read in hand. */
  held(key: string): number
  /** A FORM NEEDING THIS SET IS DRAWN, and what was read is kept while at least
   *  one is. The returned release is that drawing ending; when the last one
   *  ends, what was read is let go, so the next drawing reads again. */
  hold(key: string): () => void
  /** let go of what was read for this set, without waiting for a release */
  forget(key: string): void
}

interface Held {
  begun: number
  ended: number
  shown: Map<string, Ref> | null
  why: string | null
  /** by question id, what that question's material came to in this answer */
  came: Map<string, Came> | null
  /** how many drawings of a form needing this set are on the page */
  drawn: number
}

const empty = (): Held => ({ begun: 0, ended: 0, shown: null, why: null, came: null, drawn: 0 })

/** THE ONE EXACT RECORD ONE QUESTION'S ITEM ESTABLISHED, or why it established
 *  none. The question's own item, its own projection, its own declaration and
 *  that server's resolution of that exact id -- nothing pooled, nothing
 *  inferred, and nothing taken from another question. */
function cameTo(item: About | undefined, question: string): { came: Came; ref?: Ref } {
  if (!item) return { came: { why: NOT_ANSWERED_FOR } }
  if (item.error) return { came: { why: `${READ_SAID} ${item.error}` } }
  if (!Array.isArray(item.question_references)) return { came: { why: NOT_PROJECTED } }
  const q = item.question_references.find((x) => !!x && x.expectation === question)
  if (!q) return { came: { why: NOT_PROJECTED } }
  const p = q.primary
  if (!p || typeof p !== 'object' || p.kind !== 'record' || typeof p.id !== 'string') {
    return { came: { why: NOT_PROJECTED } }
  }
  const a = p.availability
  if (!a || typeof a !== 'object' || typeof a.id !== 'string' || typeof a.state !== 'string') {
    return { came: { why: NOT_RESOLVED } }
  }
  if (a.id !== p.id) return { came: { why: ANOTHER_ID } }
  return { came: { id: a.id }, ref: { ...a, relation: PRIMARY_ROLE } }
}

export function createStandingStore(binding = createBinding()): StandingStore {
  const at = new Map<string, Held>()
  let gens = 0
  const nothing = (key: string): MaterialRead => ({ settled: false, why: at.get(key)?.why ?? null })
  return {
    begin(key) {
      const now = at.get(key) ?? empty()
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
      const none = (said: string) => { now.shown = null; now.came = null; now.why = said }
      if (!got || !Array.isArray(got.about)) {
        none(why ?? got?.error ?? 'the server did not answer.')
        return true
      }
      if (!binding.saw(brainKeyOf(got.brain)) || binding.moved()) {
        none(OTHER_BRAIN)
        return true
      }
      /* QUESTION BY QUESTION, each from its OWN item of this answer. An HTTP
         200 is the read having answered; what it established is this. */
      const items = new Map<string, About>()
      for (const a of got.about) {
        if (a && typeof a.id === 'string' && !items.has(a.id)) items.set(a.id, a)
      }
      const refs = new Map<string, Ref>()
      const came = new Map<string, Came>()
      for (const q of key.split(',')) {
        const got1 = cameTo(items.get(q), q)
        came.set(q, got1.came)
        if (got1.ref && !refs.has(got1.ref.id)) refs.set(got1.ref.id, got1.ref)
      }
      now.shown = refs
      now.came = came
      now.why = null
      return true
    },
    shown: (key) => (binding.moved() ? null : at.get(key)?.shown ?? null),
    why: (key) => (binding.moved() ? OTHER_BRAIN : at.get(key)?.why ?? null),
    answeredFor(key, question, required) {
      if (binding.moved()) return { settled: false, why: OTHER_BRAIN }
      const now = at.get(key)
      if (!now || !now.came) return nothing(key)
      const came = now.came.get(question)
      if (!came) return { settled: false, why: NOT_ANSWERED_FOR }
      if ('why' in came) return { settled: false, why: came.why }
      /* AND IT IS THIS QUESTION'S OWN DECLARED ID OR IT IS NOTHING: one
         question's resolution is never read as another's answer. */
      if (came.id !== required) return { settled: false, why: ANOTHER_ID }
      return { settled: true, why: null }
    },
    reading(key) { const now = at.get(key); return !!now && now.ended < now.begun },
    held: (key) => at.get(key)?.ended ?? 0,
    hold(key) {
      const now = at.get(key) ?? empty()
      now.drawn++
      at.set(key, now)
      let let_go = false
      return () => {
        if (let_go) return
        let_go = true
        const held = at.get(key)
        if (!held) return
        held.drawn--
        if (held.drawn <= 0) at.delete(key)
      }
    },
    forget(key) { at.delete(key) },
  }
}

/* -- the page's own reader ---------------------------------------------------
   One store for the page, so a form drawn in two places at once reads once and
   both show the same resolution. In memory: a reload reads again, and so does
   the next drawing of a form that needs it. */
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

/** One read of this set, and WHICH read it was: a reading that must know
 *  whether what the page holds afterwards is its own answer needs its own
 *  generation, because a superseded answer is discarded without a trace. */
async function read(key: string): Promise<number> {
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
  return gen
}

/** HOW THE EXACT THINGS A FORM NAMES STAND, as the form itself read them, and
 *  what that read has come to. */
export interface OwnStanding {
  /** the same shape a host supplies (`../refWords` `standing`): what this read
   *  resolved for one exact id, or null where it resolved nothing */
  standing: Standing
  /** WHAT THAT READ CAME TO FOR ONE QUESTION and the one exact record that
   *  question declares (`./decisionPresentation` `MaterialRead`); null where no
   *  read is needed for it, or where it is not one of the questions read for */
  readOf: (question: string, required: string) => MaterialRead | null
}

export const NONE: OwnStanding = { standing: null, readOf: () => null }

/** What the form drawn here resolved for itself, where it had to: given to the
 *  questions under it so that `Presented` and `Open` read the one resolution. */
export const OwnStandingContext = createContext<OwnStanding | null>(null)

/** What the page's own reader holds for these questions RIGHT NOW, apart from
 *  React: the same answer `useOwnStanding` draws, for the sending paths that
 *  must look again after reading again (`readAgain`). */
export function standingNow(ids: readonly string[]): OwnStanding {
  const key = ids.length ? keyOf(ids) : ''
  if (!key) return NONE
  const of = new Set(ids)
  const said = (why: string): OwnStanding =>
    ({ standing: null, readOf: (q) => (of.has(q) ? { settled: false, why } : null) })
  if (ids.length > IDS_MAX) return said(TOO_MANY)
  /* THE PAGE'S OWN BINDING TOO: where Quiet Chat has already moved to another
     Brain, nothing this reader holds is used either. */
  if (page.moved()) return said(OTHER_BRAIN)
  const refs = store.shown(key)
  const standing: Standing = refs
    ? (id: string): RefStanding | null => {
      const r = refs.get(id)
      return r ? { available: r.available, state: r.state, why: r.why } : null
    }
    : null
  return { standing, readOf: (q, required) => (of.has(q) ? store.answeredFor(key, q, required) : null) }
}

/** Read, for these questions, how the exact material they declare stands. An
 *  empty list reads nothing and claims nothing. */
export function useOwnStanding(ids: readonly string[]): OwnStanding {
  const key = ids.length ? keyOf(ids) : ''
  const many = ids.length > IDS_MAX
  useSyncExternalStore(subscribe, () => version)
  useEffect(() => {
    /* ONE READ PER SET WHILE A FORM NEEDING IT IS DRAWN, AND NO RETRY OF ITS
       OWN: begun where there is nothing in hand and nothing on its way. A read
       that failed is read again the next time a form needing it is drawn, which
       is this effect running again -- AND SO IS A READ THAT SUCCEEDED, because
       what was read is let go when the last such form stops being drawn (B2).
       Nothing polls: this runs when a form is drawn, and at no other time. */
    if (!key || many) return
    const release = store.hold(key)
    if (!store.shown(key) && !store.reading(key)) void read(key)
    return () => { release(); changed() }
  }, [key, many])
  return standingNow(ids)
}

/** LET GO OF WHAT WAS READ FOR THESE QUESTIONS. The one caller is a seam read
 *  made where NO form is drawn against this reader -- a host supplies the
 *  drawing's resolution (`../quiet2/needs/NeedsAbout` `refWordsFor`) and the
 *  read was made for THAT ATTEMPT alone. What it answered belongs to the
 *  attempt, not to the page: leaving it in hand would let a later drawing, in
 *  this host or another, be answered from a read nobody made for it, which is
 *  the very thing review finding B2 forbids. A set a drawing does hold is
 *  never let go this way. */
export function forget(ids: readonly string[]): void {
  const key = ids.length ? keyOf(ids) : ''
  if (!key) return
  store.forget(key)
  changed()
}

/** WHAT ONE READING MADE AT A SENDING SEAM CAME TO, AS A READING: not what the
 *  server said -- that is `standingNow`, question by question -- but whether
 *  what this page holds for these questions RIGHT NOW was read no earlier than
 *  this reading began. Nothing may be sent on an answer older than the reading
 *  that was made to decide it (review finding R1 on B2). */
export interface Checked {
  /** what the page holds for this set was read no earlier than this reading */
  current: boolean
  /** and why it was not, where it was not */
  why: string | null
}

/** Why a reading established nothing of its own: a later reading of the same
 *  questions -- the same question drawn in a second place, read at the same
 *  moment -- took its place, and has not answered. It says what became of THIS
 *  READING and nothing whatever about the thing the question names. */
export const OVERTAKEN = 'another reading of this question was begun while this one was on its way, so this one answered for nothing and what the page holds was read before either of them.'

/** READ THESE QUESTIONS' MATERIAL AGAIN, NOW, and answer when it has answered:
 *  the one seam, apart from the form being drawn, where how the material stands
 *  decides something -- a recorded choice about to be sent, or sent again.
 *
 *  ONE READ PER ATTEMPT, AND IT WRITES NOTHING. It makes no answer, keeps no
 *  timer and retries nothing; the answer's own key, the owner's words and
 *  everything already in the outbox are untouched by it. What follows from a
 *  read that establishes nothing is only that the choice is not sent.
 *
 *  AND IT ANSWERS WHETHER IT ESTABLISHED ANYTHING AT ALL. Its own read may be
 *  superseded while it is on its way -- by the same form drawn elsewhere
 *  reading at the same moment -- and the store keeps the later read's answer
 *  only, leaving in hand what was read BEFORE this reading began. That is not
 *  an answer for it, however positive it was, so it says `current: false` and
 *  the choice is not sent on it. A later read that has ALREADY answered is: it
 *  began after this reading did, so what it established is at least as new. */
export async function readAgain(ids: readonly string[]): Promise<Checked> {
  const key = ids.length ? keyOf(ids) : ''
  /* nothing is read for these, so there is nothing to supersede: what
     `standingNow` says of them (nothing, or TOO_MANY) is as current as it gets */
  if (!key || ids.length > IDS_MAX) return { current: true, why: null }
  const gen = await read(key)
  return store.held(key) >= gen ? { current: true, why: null } : { current: false, why: OVERTAKEN }
}
