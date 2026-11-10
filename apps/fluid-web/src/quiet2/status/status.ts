/* A POST'S OPERATIONAL STATUS (Track B): WHO IT WAS ADDRESSED TO, AND WHERE
 * EACH STANDS.
 *
 * Read from the record's own facts and nothing else, as Fluid's addressing
 * (`fluid/conversation/Addressing.tsx`) and Classic read them: each post's
 * `addressees` and `expectations` exactly as the server's Turn view gives
 * them (`mentis/web` `_turn_view`, `_expectation_view`), who is working now
 * from the one activity reader (presence.ts), and -- once somebody opens a
 * post's status -- the acts recorded on the post (`/api/turns?ids=`, the
 * inspector's `operational`), which carry the times.
 *
 * THREE DIMENSIONS, KEPT APART (owner's brief, B1). Addressing (named on the
 * post, brought in later, asked for something), acknowledgment, and work
 * (started, running, waiting on somebody else, failed, replied, claimed
 * complete, closed without an answer) are separate facts per participant,
 * never one lifecycle:
 *  - ACKNOWLEDGMENT IS NOT RECORDED. Mentis keeps no act by which an agent
 *    says it received or accepted a request (`status_of`: "There is no
 *    `read` and no `understood`, because no runtime path establishes
 *    either"). A delivery says it reached them; a reply says they replied;
 *    neither is acknowledgment, and none is inferred. It is said as "not
 *    recorded" wherever it would be shown.
 *  - COMPLETED IS A CLAIM, and only the carrier's: `satisfied_by`, an
 *    `expectation-met` act. A reply is not one, and a run ending is not one.
 *  - THE POST IS COMPLETED ONLY WHEN EVERY REQUEST ON IT IS CLAIMED COMPLETE
 *    and everyone it addressed has replied; one participant finishing among
 *    several says so for that participant alone.
 *
 * The words are Classic's, as Fluid's `ofExpectation` composes them (lifted
 * here: Addressing.tsx exports only its drawn component, and these facts
 * arrive with Mark 2's own conversation read rather than its card's). */
import { useCallback, useEffect, useSyncExternalStore } from 'react'
import { ago, CLIENT_HEADERS } from '../../api'
import { hearPulse } from '../../fluid/identity/activity'
import type { Working } from '../presence'
import type { Id } from '../sample'

/* -- the record's facts, as the Turn view gives them ------------------------ */

export interface AddresseeFact {
  participant: Id; alias: string; delivered: boolean; responded: boolean; failed: string | null
  addressed_later: boolean; addressed_by: string | null; addressed_because: string | null
}
export interface ExpectationFact {
  id: Id; expects: string; of: Id | null; of_alias: string | null; by: Id; by_alias: string; because?: string | null
  response_present: boolean; live_execution: boolean; unassigned?: boolean; unresolved_because?: string | null
  satisfied_by?: Id[]; failures?: { act?: Id; because?: string | null; at?: number }[]
  delegations?: { act?: Id; expectation?: Id | null; by?: Id; at?: number }[]
  withdrawn?: { by_alias?: string | null; because?: string | null; at?: number; reply?: Id | null } | null
  lapsed?: { by_alias?: string | null; because?: string | null; at?: number } | null
  answered_by?: { turn: Id; number: number | null } | null
  requires?: string[]
  /** a question of a decision form: answered only by the reply that names it */
  form?: Id
}
/** What a post's status is drawn from: its Turn view's two lists. */
export interface StatusFacts { addressees: AddresseeFact[]; expectations: ExpectationFact[] }

/** One act recorded on the post (the inspector's `operational`), as far as
 *  status reads it: who did what, when. */
export interface PostAct { id: Id; act: string; at: number; actor: Id | null; about?: Id[] | null; because?: string | null; execution?: string | null }

/** The two lists out of a Turn as any read gives it; undefined when the post
 *  addresses nobody and asks nothing. */
export function factsOf(t: unknown): StatusFacts | undefined {
  const x = t as { addressees?: AddresseeFact[]; expectations?: ExpectationFact[] }
  const facts = { addressees: x.addressees ?? [], expectations: x.expectations ?? [] }
  return facts.addressees.length || facts.expectations.length ? facts : undefined
}

/* -- what each request is in, read in the record's own order ----------------
   Closures first (withdrawn, then lapsed, then claimed complete: the server
   reads `withdrawn` before `satisfied_by`, which also names that act, and a
   lapse is an `expectation-met` too); then what is happening now; then what
   is owed. A reply settles nothing; an earlier failure under a later reply is
   kept in the words, not the state. */
export type AskState = 'withdrawn' | 'lapsed' | 'completed' | 'answered' | 'running' | 'unclaimed' | 'handed-on' | 'failed' | 'replied' | 'awaiting-person' | 'pending'

/** The kinds of request a person answers rather than a run: a decision, an
 *  input to fill in. Waiting on one is waiting on a decision. */
const PERSON_KINDS = new Set(['decision', 'input', 'question', 'permission'])

export function askState(e: ExpectationFact): AskState {
  if (e.withdrawn) return 'withdrawn'
  if (e.lapsed) return 'lapsed'
  if (e.satisfied_by?.length) return 'completed'
  if (e.live_execution) return 'running'
  if (e.unassigned) return 'unclaimed'
  if (e.delegations?.length) return 'handed-on'
  if (e.failures?.length && !e.response_present) return 'failed'
  /* A DECISION FORM'S QUESTION, AN INPUT: the record's own rule says what
     answers them (the reply that names the question, the set marked ready),
     so a response present is their answer. Any other reply settles nothing. */
  if (e.response_present) return e.form || e.expects === 'input' ? 'answered' : 'replied'
  return PERSON_KINDS.has(e.expects) ? 'awaiting-person' : 'pending'
}

/* -- one participant's line ----------------------------------------------- */

export type PartyState = 'running' | 'waiting' | 'failed' | 'unclaimed' | 'pending' | 'replied' | 'completed' | 'closed'

export interface Ask { fact: ExpectationFact; state: AskState; words: string }

export interface Party {
  /** null: a request nobody carries */
  participant: Id | null
  alias: string | null
  /** named on the post itself (`addressed_to`), or brought in later; null when
   *  they are only asked through a request, or only working on it */
  addressed: AddresseeFact | null
  asks: Ask[]
  /** working on the post now, by the activity reader */
  work: Working[]
  state: PartyState
}

/** Which state a participant shows when the record says several things of
 *  them: what is happening now, then what went wrong, then what is owed,
 *  then what settled. */
const FIRST: PartyState[] = ['running', 'failed', 'unclaimed', 'waiting', 'pending', 'replied', 'completed', 'closed']
const OF_ASK: Record<AskState, PartyState> = {
  running: 'running', failed: 'failed', unclaimed: 'unclaimed', 'handed-on': 'waiting', 'awaiting-person': 'waiting',
  pending: 'pending', replied: 'replied', completed: 'completed', answered: 'completed', withdrawn: 'closed', lapsed: 'closed',
}
const first = (xs: PartyState[]) => xs.reduce((a, b) => (FIRST.indexOf(b) < FIRST.indexOf(a) ? b : a))

const at = (n: string | null | undefined) => (n ? (n.startsWith('@') ? n : '@' + n) : 'somebody')

/** Classic's words for one request (Fluid's `ofExpectation`), with what its
 *  state rests on. */
function askWords(e: ExpectationFact, s: AskState): string {
  const of = at(e.of_alias ?? null)
  const kind = e.expects || 'response'
  switch (s) {
    case 'withdrawn': return `${at(e.withdrawn?.by_alias ?? e.of_alias)} withdrew this ${kind}${e.withdrawn?.because ? `: ${e.withdrawn.because}` : ''}. It was not answered.`
    case 'lapsed': return `${at(e.by_alias)} no longer asks this: ${(e.lapsed?.because ?? 'its run can no longer take an answer').replace(/^no longer asked: /, '')}. It was not answered.`
    case 'completed': return `${of} says this ${kind} is complete. That is their claim about their own work, not a verification of it.`
    case 'answered': return `${of} has answered this ${kind}${e.form ? ', by the reply that names it' : ''}.`
    case 'running': return `${of} is working on this ${kind} now.`
    case 'unclaimed': return `${at(e.by_alias)} asked for a ${kind}, and nobody is carrying it${e.unresolved_because ? `: ${e.unresolved_because}` : ''}.`
    case 'handed-on': {
      const n = e.delegations!.length
      return `${of} handed ${n === 1 ? 'part of this on' : `parts of this on ${n} times`}; each is its own request, and whether those are done is not read here. The ${kind} itself is still owed${e.response_present ? ', though they have replied' : ''}.`
    }
    case 'failed': return `${of} was to answer this, and it failed: ${e.failures![e.failures!.length - 1].because ?? 'no reason was recorded'}.`
    case 'replied': return `${of} has replied. Nothing records the ${kind} as complete${e.failures?.length ? `; ${e.failures.length === 1 ? 'an earlier attempt' : `${e.failures.length} earlier attempts`} failed` : ''}.`
    case 'awaiting-person': return `${at(e.by_alias)} is waiting on ${of} for a ${kind}.`
    case 'pending': return `${at(e.by_alias)} asked ${of} for a ${kind}. Nothing running, replied or failed is recorded for it yet.`
  }
}

/** Everyone a post concerns, each once, with where they stand. */
export function partiesOf(facts: StatusFacts | undefined, work: Working[]): Party[] {
  const by = new Map<string, Party>()
  const party = (participant: Id | null, alias: string | null, key: string) => {
    let p = by.get(key)
    if (!p) by.set(key, p = { participant, alias, addressed: null, asks: [], work: [], state: 'pending' })
    if (!p.alias && alias) p.alias = alias
    return p
  }
  for (const a of facts?.addressees ?? []) party(a.participant, a.alias, a.participant).addressed = a
  for (const e of facts?.expectations ?? []) {
    const s = askState(e)
    party(e.of, e.of_alias, e.of ?? 'nobody:' + e.id).asks.push({ fact: e, state: s, words: askWords(e, s) })
  }
  for (const w of work) party(w.participant, w.alias, w.participant).work.push(w)
  for (const p of by.values()) {
    const states: PartyState[] = p.asks.map((x) => OF_ASK[x.state])
    if (p.work.length) states.push(p.work.every((w) => w.waiting) ? 'waiting' : 'running')
    /* addressed on the post: their reply, or a failed delivery, is the fact */
    if (p.addressed && !p.asks.length && !p.work.length)
      states.push(p.addressed.failed ? 'failed' : p.addressed.responded ? 'replied' : 'pending')
    p.state = states.length ? first(states) : 'pending'
  }
  return [...by.values()]
}

/* -- the post's one state, for the dog-ear --------------------------------- */

export type PostState = 'running' | 'attention' | 'waiting' | 'pending' | 'replied' | 'completed' | 'closed'

export interface PostStatus { state: PostState; label: string; parties: Party[]; summary: string }

const STATE_LABEL: Record<PostState, string> = {
  running: 'Work running', attention: 'Failed or stopped', waiting: 'Waiting on somebody',
  pending: 'Addressed, nothing started', replied: 'Replied, not marked complete', completed: 'Completed', closed: 'Closed without completion',
}
const PARTY_WORD: Record<PartyState, string> = {
  running: 'working', waiting: 'waiting', failed: 'failed', unclaimed: 'nobody carrying it', pending: 'addressed',
  replied: 'replied', completed: 'completed', closed: 'closed',
}

/** The post's status from its parties, or null when it addresses nobody,
 *  asks nothing and nobody is working on it. */
export function statusOf(facts: StatusFacts | undefined, work: Working[]): PostStatus | null {
  const parties = partiesOf(facts, work)
  if (!parties.length) return null
  const has = (s: PartyState) => parties.some((p) => p.state === s)
  const state: PostState = has('running') ? 'running'
    : has('failed') || has('unclaimed') ? 'attention'
      : has('waiting') ? 'waiting'
        : has('pending') ? 'pending'
          : has('replied') ? 'replied'
            /* every request claimed complete, everyone addressed answered */
            : parties.every((p) => p.state === 'completed') ? 'completed'
              : 'closed'
  const counts = new Map<PartyState, number>()
  for (const p of parties) counts.set(p.state, (counts.get(p.state) ?? 0) + 1)
  const summary = parties.length === 1 ? (parties[0].participant ? `${at(parties[0].alias)}: ${PARTY_WORD[parties[0].state]}` : 'Nobody is carrying it')
    : FIRST.filter((s) => counts.has(s)).map((s) => `${counts.get(s)} ${PARTY_WORD[s]}`).join(' · ')
  /* replies where nothing was asked: there is nothing to mark complete */
  const label = state === 'replied' && !parties.some((p) => p.asks.length) ? 'Replied'
    : state === 'closed' && has('completed') ? 'Closed; not every request completed' : STATE_LABEL[state]
  return { state, label, parties, summary }
}

/** The short attribution for one participant (B4): "Addressed to @Caretaker",
 *  "Working: @Builder", "Completed by @Caretaker". Never "Acknowledged by":
 *  nothing records it. */
export function attributionOf(p: Party): string {
  const who = at(p.alias)
  if (!p.participant) return 'Nobody carries it'
  const asks = p.asks.map((x) => x.state)
  switch (p.state) {
    case 'running': return `Working: ${who}`
    case 'waiting': return p.work.some((w) => w.waiting) ? `${who} waiting on a decision`
      : asks.includes('handed-on') ? `Handed on by ${who}` : `Waiting on ${who}`
    case 'failed': return p.addressed?.failed && !p.asks.length ? `Delivery failed: ${who}` : `Failed: ${who}`
    case 'unclaimed': return 'Nobody carries it'
    case 'pending': return p.addressed?.addressed_later ? `Brought in: ${who}` : p.addressed ? `Addressed to ${who}` : `Asked of ${who}`
    case 'replied': return `Replied: ${who}`
    case 'completed': return asks.length && asks.every((s) => s === 'answered') ? `Answered by ${who}` : `Completed by ${who}`
    case 'closed': {
      const by = p.asks.find((x) => x.fact.withdrawn)?.fact.withdrawn?.by_alias
      return asks.every((s) => s === 'withdrawn') ? `Withdrawn by ${at(by ?? p.alias)}` : asks.every((s) => s === 'lapsed') ? `No longer asked of ${who}` : `Closed: ${who}`
    }
  }
}

/* -- the times, from the acts on the post ---------------------------------- */

export interface Times {
  /** when the post addressed them, or asked of them */
  asked: number | null
  /** each run of theirs that started on this post */
  runs: number[]
  /** waiting on other work they declared, and not resumed since */
  awaiting: { at: number; because: string | null } | null
  failed: number | null
}

export function timesOf(acts: PostAct[] | null, p: Party, postAt: number | null): Times | null {
  if (!acts) return null
  const who = p.participant
  const mine = (a: PostAct) => !!who && a.actor === who
  /* an expectation's id is the id of the act that recorded it; a later
     addressing is its own act; else they were named when it was posted */
  const asks = new Set(p.asks.map((x) => x.fact.id))
  const asked = acts.find((a) => asks.has(a.id))?.at
    ?? (p.addressed?.addressed_later ? acts.find((a) => a.act === 'turn-addressed' && !!who && (a.about ?? []).includes(who))?.at : undefined)
    ?? (p.addressed ? postAt ?? undefined : undefined)
  const runs = acts.filter((a) => a.act === 'execution-started' && mine(a)).map((a) => a.at)
  /* waiting on other work: their latest `work-awaited`, unless they were
     resumed or started again after it */
  const lastWait = [...acts].reverse().find((a) => a.act === 'work-awaited' && mine(a))
  const after = lastWait && acts.some((a) => a.at > lastWait.at && ((a.act === 'work-resumed' && (a.about ?? []).includes(who!)) || (a.act === 'execution-started' && mine(a))))
  const failed = [...acts].reverse().find((a) => a.act === 'delivery-failed' && mine(a))?.at ?? null
  return { asked: asked ?? null, runs, awaiting: lastWait && !after ? { at: lastWait.at, because: lastWait.because ?? null } : null, failed }
}

/** A time as the post's own byline says it, and how long ago. */
export function clock(t: number): string {
  const d = new Date(t * 1000)
  const time = d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
  const day = d.toDateString() === new Date().toDateString() ? 'Today' : d.toLocaleDateString([], { month: 'short', day: 'numeric' })
  const since = ago(t)
  return /ago|now/.test(since) ? `${day}, ${time} (${since})` : `${day}, ${time}`
}

/* -- the reader ------------------------------------------------------------
   SEEDED BY THE CONVERSATION READ, which already carries each post's two
   lists (real.ts `adapt`): nothing more is asked to draw a dog-ear. Asked
   again, through production's batched `GET /api/turns?ids=` (at most 64,
   Addressing.tsx's own read), only
     - for a post whose status is opened, for the acts and their times, and
     - when Fluid's one pulse (`hearPulse`) says the record moved in a
       conversation a shown status belongs to -- no poller of its own.
   Who is working now is the activity reader's, already live. */

interface Held { facts: StatusFacts | undefined; acts: PostAct[] | null; stamp: number }
const held = new Map<Id, Held>()
let tick = 0
const heard = new Set<() => void>()
const tell = () => { tick += 1; heard.forEach((fn) => fn()) }
const sub = (fn: () => void) => { heard.add(fn); return () => { heard.delete(fn) } }

/** The conversation read's facts for a post, newer than what was held. */
export function seedStatus(id: Id, facts: StatusFacts | undefined) {
  const had = held.get(id)
  held.set(id, { facts, acts: had?.acts ?? null, stamp: Date.now() })
}

/** Posts drawn now with a status, and their conversations: what a move reads. */
const shown = new Map<Id, { conversation: Id | null; n: number }>()
const asked = new Set<Id>()
let flushing = 0
let reading = false
const MOST = 64   // production's TURNS_PER_READ

function want(id: Id) {
  asked.add(id)
  if (!flushing) flushing = window.setTimeout(flush, 40)
}
async function flush() {
  flushing = 0
  if (reading) { flushing = window.setTimeout(flush, 400); return }
  const batch = [...asked].slice(0, MOST)
  batch.forEach((id) => asked.delete(id))
  if (asked.size) flushing = window.setTimeout(flush, 40)
  if (!batch.length) return
  reading = true
  try {
    const res = await fetch('/api/turns?ids=' + batch.map(encodeURIComponent).join(','), { headers: CLIENT_HEADERS })
    const body = await res.json()
    for (const row of body.turns ?? []) {
      if (!row.turn) continue
      held.set(row.id, { facts: factsOf(row.turn), acts: (row.turn.inspector?.operational ?? []) as PostAct[], stamp: Date.now() })
    }
  } catch { /* what was read last stands until it can be read again */ } finally { reading = false }
  tell()
}

let stopHearing: (() => void) | null = null
function hear() {
  if (stopHearing) return
  stopHearing = hearPulse((m, where) => {
    if (m !== 'durable') return
    for (const [id, s] of shown) {
      const open = held.get(id)
      /* a move nobody narrowed, one in this post's conversation, or a run's
         acts while something on it is still owed */
      if (!where || where.loose || (s.conversation && where.conversations.includes(s.conversation))
        || (where.executions.length > 0 && !!open && statusOf(open.facts, [])?.state !== 'completed' && statusOf(open.facts, [])?.state !== 'closed')) want(id)
    }
  })
}

/** The post's facts as last read, its acts once read, and the way to ask for
 *  them; re-read on the pulse while it is drawn. */
export function usePostStatus(id: Id, conversation: Id | null, fallback: StatusFacts | undefined, live: boolean): { facts: StatusFacts | undefined; acts: PostAct[] | null; readActs: () => void } {
  useSyncExternalStore(sub, () => tick)
  useEffect(() => {
    if (!live) return
    const s = shown.get(id) ?? { conversation, n: 0 }
    s.n += 1
    shown.set(id, s)
    hear()
    return () => {
      s.n -= 1
      if (s.n <= 0) shown.delete(id)
      if (!shown.size && stopHearing) { stopHearing(); stopHearing = null }
    }
  }, [id, conversation, live])
  const readActs = useCallback(() => { if (live) want(id) }, [id, live])
  const h = held.get(id)
  return { facts: h ? h.facts : fallback, acts: h?.acts ?? null, readActs }
}
