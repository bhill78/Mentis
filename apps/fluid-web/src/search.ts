/* ------------------------------------------------------------------------ *
 * THE CLIENT FOR THE SEARCH MENTIS ALREADY HAS.
 *
 * There is no second search engine here, and there must not be one. The record
 * is already searched by `Surface.find` in `mentis/worker.py`, reached over
 * `/api/references` -- the same resolver a dispatched worker asks, so the
 * picker, the workers and this field cannot disagree about what exists. It
 * answers three grammars, and the order is its own:
 *
 *   IDENTITY    `ent-…`  the reference itself, exact by construction
 *   COORDINATE  a number the Turn shows in its margin; inside a Conversation
 *               that Conversation's Nth Turn, at Brain scope every
 *               Conversation that has one, and it says it was ambiguous
 *   TEXT        everything else: Participants, Conversations, Topics, Links by
 *               relation, and the full prose of every Turn in the Brain
 *
 * This file adds a debounce, the types, and MORE RESULTS. Nothing here ranks,
 * filters or re-orders what the record returned.
 *
 * WHY THIS MATTERS MORE THAN IT LOOKS. The capability was reachable only by
 * typing `#` inside a composer, and choosing a result there INSERTS A
 * REFERENCE INTO A DRAFT -- it has never navigated anywhere. So the one global
 * way to find an old Turn by its words could not take you to it, and the field
 * in the app bar said, truthfully, that it queried nothing. Material was
 * reachable in the record and not reachable by a person.
 *
 * WHAT THE NUMBERS IN AN ANSWER MEAN (measured, Mentis UI/UX #362). `find`
 * walks Turns in record order -- Conversation by Conversation, Turn by Turn --
 * and STOPS once it has gathered about three times the limit. So `matched` is
 * how far the scan got, not a total: "history" said 40 at limit 12, 123 at 40
 * and 261 at 200 and above. `not_returned` is `matched - limit` and is not
 * "how many are left" either. Showing "12 of 40" was untrue.
 *
 * What IS true, and is all this file relies on:
 *   - the order is the record's and does not change with the limit, so asking
 *     again with a larger limit returns what was shown plus more;
 *   - an answer with `not_returned == 0` held fewer rows than the limit, so
 *     the scan never stopped early: that answer is EVERYTHING. Only then is a
 *     count exact. Until then every count is a lower bound and says so ("12+").
 * No backend change was needed for either.
 * ------------------------------------------------------------------------ */

import { useCallback, useEffect, useRef, useState } from 'react'
import { qs, read, type Id } from './api'

/** One hit. `what` is the record's own word for the thing, never ours. */
export interface Hit {
  what: 'turn' | 'conversation' | 'topic' | 'participant' | 'link' | string
  ref: Id
  /** why it is exact, where it is: `identity` or `coordinate`. Absent for text. */
  exact?: 'identity' | 'coordinate' | string
  name?: string
  said?: string
  number?: number | null
  conversation?: Id | null
  conversation_name?: string
  relation?: string
  stands?: boolean
}

export interface Found {
  found: Hit[]
  /** how far the scan got before it stopped. NOT a total -- see above. */
  matched: number
  exact: number
  /** a coordinate named more than one Turn and nothing narrowed it */
  ambiguous: boolean
  /** `matched - limit`. Zero means the answer is everything there is. */
  not_returned: number
  why_not?: string
  /** file contents not searched YET: their text is being extracted now */
  pending?: Pending
}

/* ------------------------------------------------------------------------ *
 * FILE CONTENTS NOT SEARCHED YET (Sources C, acceptance finding A1).
 *
 * `find` never waits for a PDF's text to be extracted: it starts it and
 * answers at once, and the PDF is simply not in that answer. Unsaid, a
 * missing file reads as "it does not contain these words". So the answer
 * carries `pending` -- the content scan's own count, over the same held
 * record the content hits came from, never the page -- and the picker and
 * the search panel say it, then ask again a little later until it is gone.
 * The notice is a property of ONE answer and is never kept past it.
 * ------------------------------------------------------------------------ */

/** `find`'s `pending`: extractions being made, by payload type. */
export interface Pending {
  extractions: number
  by_type: Record<string, number>
  note?: string
}

/** How often, and how many times, an answer with something pending is asked
 *  again. Past the last ask the notice stays, still true of that answer. */
export const PENDING_RECHECK_MS = 2000
export const PENDING_RECHECKS = 30

const kindOf = (t: string, n: number): string =>
  t === 'application/pdf' ? (n === 1 ? 'PDF' : 'PDFs') : (n === 1 ? 'file' : 'files')

/** The brief notice, or null when nothing is pending. */
export function pendingNote(p?: Pending | null): string | null {
  if (!p || !p.extractions) return null
  const parts = Object.entries(p.by_type)
    .filter(([, n]) => n > 0)
    .map(([t, n]) => `${n} ${kindOf(t, n)}`)
  return `Still reading ${parts.join(', ') || `${p.extractions} files`} — `
    + 'not searched yet, will update when ready'
}

/** ASK AGAIN WHILE SOMETHING IS PENDING, a bounded number of times. `answer`
 *  is the answer on screen (a new object each ask); `key` is the question,
 *  and a new question starts the count again. */
export function useRecheckWhilePending(pending: number, answer: unknown,
                                       key: string, reload: () => void) {
  const tries = useRef({ key, n: 0 })
  if (tries.current.key !== key) tries.current = { key, n: 0 }
  useEffect(() => {
    if (!pending || tries.current.n >= PENDING_RECHECKS) return
    const t = window.setTimeout(() => {
      tries.current.n += 1
      reload()
    }, PENDING_RECHECK_MS)
    return () => window.clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pending, answer, key])
}

/** IS THIS HIT A TURN? Not `what === 'turn'`, which is true only of the TEXT
 *  grammar. An identity hit carries the Kind's own name -- a Turn resolves as
 *  `contribution`, and a Kind nobody has heard of would resolve as itself --
 *  so the question is asked of the shape the record returned: a Turn is the
 *  thing that has a coordinate in a Conversation. */
export const isTurn = (h: Hit): boolean =>
  h.what === 'turn' || (h.number != null && !!h.conversation)

/** How many hits the first answer asks for. */
export const SHOWN = 12

/** EACH "MORE RESULTS" ASKS AGAIN WITH THE NEXT LIMIT. The approved steps
 *  are 12 → 40 → 120 → 360; past that it keeps tripling, because a search
 *  that has not finished at 360 has not finished, and stopping the ladder
 *  there would turn "more available" into a dead end. */
export const LADDER = [SHOWN, 40, 120, 360]
export const nextLimit = (limit: number): number => {
  const i = LADDER.indexOf(limit)
  return i >= 0 && i < LADDER.length - 1 ? LADDER[i + 1] : limit * 3
}

/** The answer is everything there is: it came back under its own limit. */
export const exhausted = (f: Found): boolean => f.not_returned === 0

/** Rows not already held, in the order the record gave them. Nothing that is
 *  on screen moves: new rows are only ever added after it. */
export function appendNew(held: Hit[], more: Hit[]): Hit[] {
  const seen = new Set(held.map((h) => h.ref))
  const add = more.filter((h) => !seen.has(h.ref))
  return add.length ? [...held, ...add] : held
}

/** A loaded search: everything asked so far, and what it is known to be. */
export interface Session {
  /** the words that were asked */
  q: string
  /** WHERE IT WAS ASKED FROM. Kept, not followed: `find` offers this
   *  Conversation's rows first, so asking a continuation from somewhere else
   *  would be a different search wearing this one's rows. */
  here: Id | null
  limit: number
  rows: Hit[]
  /** the newest answer as the record gave it */
  last: Found
  /** every match there is is in `rows`; counts are exact */
  done: boolean
}

/** A QUESTION THAT WAS NOT ANSWERED, and which kind of question it was. A
 *  new search that fails is not "could not load more": nothing was loaded for
 *  it at all, and the rows still held belong to the question before it. */
export interface Failure {
  /** the words whose question failed */
  q: string
  /** `search`: the first answer to `q` never came. `more`: `q` was answered,
   *  and only its continuation failed. */
  kind: 'search' | 'more'
  message: string
}

/** A search, continued only when somebody asks for more.
 *
 *  THERE IS NO AUTOMATIC CONTINUATION. Each "More results" rescans the record
 *  from its start (~0.3-0.8s for 12 on a common word, 2-4.5s for 1,000), which
 *  is fine for a deliberate press and not for a scroll position. */
export function useSearch(query: string, conversation: Id | null) {
  const q = query.trim()
  const [settled, setSettled] = useState('')
  const [session, setSession] = useState<Session | null>(null)
  const [loading, setLoading] = useState(false)
  const [more, setMore] = useState(false)
  const [error, setError] = useState<Failure | null>(null)
  const ask = useRef(0)
  const here = useRef(conversation)
  here.current = conversation

  useEffect(() => {
    // Nothing is asked for one or two characters: `find` walks every Turn in
    // the Brain, and a single letter matches most of them.
    if (q.length < 2) {
      setSettled('')
      return
    }
    const t = window.setTimeout(() => setSettled(q), 180)
    return () => window.clearTimeout(t)
  }, [q])

  /* A NEW QUESTION IS ASKED ONLY WHEN THE WORDS CHANGE. Not when the reader
     moves to another Conversation: opening a result moves them, and the
     search they came from must still be there, unchanged, when they look
     again. */
  useEffect(() => {
    const token = ++ask.current
    setMore(false)
    setError(null)
    if (!settled) {
      setSession(null)
      setLoading(false)
      return
    }
    const from = here.current
    setLoading(true)
    read<Found>(`/api/references${qs({ q: settled, conversation: from, limit: SHOWN })}`)
      .then((f) => {
        if (ask.current !== token) return
        setSession({ q: settled, here: from, limit: SHOWN, rows: f.found,
                     last: f, done: exhausted(f) })
      })
      .catch((e: Error) => {
        if (ask.current !== token) return
        // The rows held answer an earlier question -- possibly in these very
        // words, asked before. Kept, they would read as this one's answer.
        setSession(null)
        setError({ q: settled, kind: 'search', message: e.message })
      })
      .finally(() => {
        if (ask.current === token) setLoading(false)
      })
  }, [settled])

  /** MORE RESULTS: the same search, asked again with the next limit, and only
   *  the rows not already shown appended. */
  const loadMore = useCallback(() => {
    const s = session
    if (!s || s.done || more) return
    const token = ask.current
    const limit = nextLimit(s.limit)
    setMore(true)
    setError(null)
    read<Found>(`/api/references${qs({ q: s.q, conversation: s.here, limit })}`)
      .then((f) => {
        if (ask.current !== token) return
        setSession((was) => was && was.q === s.q
          ? { ...was, limit, rows: appendNew(was.rows, f.found), last: f,
              done: exhausted(f) }
          : was)
      })
      .catch((e: Error) => {
        if (ask.current === token) setError({ q: s.q, kind: 'more', message: e.message })
      })
      .finally(() => {
        if (ask.current === token) setMore(false)
      })
  }, [session, more])

  /* STILL READING A FILE: the same question, at the same limit, asked again
     until nothing is pending. Rows already on screen stay where they are;
     a file that has become searchable is added after them. */
  const recheck = useCallback(() => {
    const s = session
    if (!s || more) return
    const token = ask.current
    read<Found>(`/api/references${qs({ q: s.q, conversation: s.here, limit: s.limit })}`)
      .then((f) => {
        if (ask.current !== token) return
        setSession((was) => was && was.q === s.q && was.limit === s.limit
          ? { ...was, rows: appendNew(was.rows, f.found), last: f, done: exhausted(f) }
          : was)
      })
      .catch(() => {
        // The answer on screen still says what is pending; nothing to undo.
      })
  }, [session, more])
  useRecheckWhilePending(more ? 0 : session?.last.pending?.extractions ?? 0,
                         session?.last, session?.q ?? '', recheck)

  /* THE WORDS IN THE BOX NOW, not yet debounced. Rows are acted on only when
     they answer these: during the debounce the box already holds a new
     question, and Enter must not open the old one's answer. */
  const typed = q.length < 2 ? '' : q
  return { session, loading, more, error, asked: settled, typed, loadMore }
}

/* ------------------------------------------------------------------------ *
 * COUNTS, AND HOW MUCH EACH ONE CAN CLAIM.
 * ------------------------------------------------------------------------ */

/** The result classes search actually returns, in the order it returns them,
 *  and the word a tab says for each. Nothing is offered that search cannot
 *  return. */
export type Klass = 'turn' | 'conversation' | 'topic' | 'participant' | 'link'
export const KLASSES: { k: Klass; label: string }[] = [
  { k: 'turn', label: 'Turns' },
  { k: 'conversation', label: 'Conversations' },
  { k: 'topic', label: 'Topics' },
  { k: 'participant', label: 'People' },
  { k: 'link', label: 'Links' },
]

export const klassOf = (h: Hit): Klass | null => {
  if (isTurn(h)) return 'turn'
  const w = h.what as Klass
  return KLASSES.some((x) => x.k === w) ? w : null
}

/** A count, and whether it is the whole of it. */
export interface Count {
  n: number
  exact: boolean
}
export const said = (c: Count): string => `${c.n}${c.exact ? '' : '+'}`

/** ARE THE PLACES ALL HERE? `find` gathers every Participant, Conversation,
 *  Topic and Link that matches BEFORE it reads a single Turn's prose, and only
 *  the Turns are cut off. So once a text Turn from outside the "offered first"
 *  Conversation is among the rows held, every Place came before it and is
 *  held too: those counts are exact from the first answer, while the Turn
 *  count is still a lower bound. Without such a row nothing is claimed. */
export function placesComplete(s: Session): boolean {
  if (s.done) return true
  return s.rows.some((h) => isTurn(h) && !h.exact && h.conversation !== s.here)
}

export function counts(s: Session): { all: Count; by: Map<Klass, Count> } {
  const places = placesComplete(s)
  const by = new Map<Klass, Count>()
  for (const h of s.rows) {
    const k = klassOf(h)
    if (!k) continue
    const c = by.get(k) ?? { n: 0, exact: k === 'turn' ? s.done : places }
    c.n += 1
    by.set(k, c)
  }
  return { all: { n: s.rows.length, exact: s.done }, by }
}

/** TURNS, GROUPED BY THE CONVERSATION THEY OCCURRED IN. Presentation only:
 *  the grouping is the Turn's own `conversation` coordinate and nothing else,
 *  and groups keep the order their first row arrived in. */
export interface Group {
  conversation: Id
  name: string
  turns: Hit[]
  /** every match in this Conversation is held */
  exact: boolean
}

export function groups(s: Session, nameOf: (id: Id) => string | null): Group[] {
  const out: Group[] = []
  const at = new Map<Id, Group>()
  for (const h of s.rows) {
    if (!isTurn(h)) continue
    const cid = h.conversation ?? ''
    let g = at.get(cid)
    if (!g) {
      g = { conversation: cid, name: h.conversation_name || nameOf(cid) || 'a Conversation',
            turns: [], exact: s.done }
      at.set(cid, g)
      out.push(g)
    }
    g.turns.push(h)
  }
  /* A GROUP IS WHOLE WHEN THE TEXT SCAN WENT PAST IT. The prose is read one
     Conversation after another, so a TEXT Turn from a later Conversation
     means the ones whose text Turns came before it were read to their end.

     ONLY TEXT TURNS SAY HOW FAR THE SCAN GOT. Exact hits -- a coordinate (`10`
     is Turn #10 of every Conversation long enough) or an identity -- are
     gathered before the scan starts, so a group they open proves nothing:
     with them counted, a numeric search said "9 turns" of a Conversation
     holding 50 (review adm-67fc30cc5918, finding 1). So the order used is
     the order of the first TEXT Turn from each Conversation, and a group with
     no text Turn, or whose text Turns are the last ones held, stays a lower
     bound until the answer is exhausted.

     The "offered first" Conversation is never provably whole before the end:
     it is lifted to the top after the scan was cut, which is exactly the
     separate bug left out of this work. */
  if (!s.done) {
    const scanned: Id[] = []
    for (const h of s.rows) {
      if (!isTurn(h) || h.exact || h.conversation === s.here) continue
      const cid = h.conversation ?? ''
      if (!scanned.includes(cid)) scanned.push(cid)
    }
    const passed = new Set(scanned.slice(0, -1))
    for (const g of out) if (passed.has(g.conversation)) g.exact = true
  }
  return out
}

/** The distinct Conversations the held Turns occurred in. */
export const conversationsIn = (rows: Hit[]): number =>
  new Set(rows.filter(isTurn).map((h) => h.conversation)).size

/** What the panel says about its own completeness. NEVER "of N": no answer
 *  short of the last one knows N. */
export function footing(s: Session): string {
  if (s.last.ambiguous) return `that number names a turn in ${s.last.exact} conversations`
  if (!s.done) return `${s.rows.length} shown · more available`
  const turns = s.rows.filter(isTurn).length
  const n = s.rows.length
  const head = `${n} ${n === 1 ? 'match' : 'matches'}`
  if (!turns) return head
  const c = conversationsIn(s.rows)
  return turns === n
    ? `${head} in ${c} ${c === 1 ? 'conversation' : 'conversations'}`
    : `${head} · ${turns} ${turns === 1 ? 'turn' : 'turns'} in ${c} ${c === 1 ? 'conversation' : 'conversations'}`
}

/** A READABLE EXCERPT, centred on where the words were found. Presentation
 *  of text the record returned; it adds no words of its own beyond the
 *  ellipses that say something was cut. */
export function excerpt(text: string, q: string, width = 180): { before: string; hit: string; after: string } {
  const flat = text.replace(/\s+/g, ' ').trim()
  const needle = q.trim().replace(/^[@#]/, '').toLowerCase()
  const i = needle ? flat.toLowerCase().indexOf(needle) : -1
  if (i < 0) {
    const cut = flat.length > width
    return { before: cut ? flat.slice(0, width).trimEnd() + '…' : flat, hit: '', after: '' }
  }
  const lead = Math.max(0, Math.min(i - Math.floor((width - needle.length) / 3), flat.length - width))
  const end = Math.min(flat.length, lead + width)
  return {
    before: (lead > 0 ? '…' : '') + flat.slice(lead, i),
    hit: flat.slice(i, i + needle.length),
    after: flat.slice(i + needle.length, end) + (end < flat.length ? '…' : ''),
  }
}
