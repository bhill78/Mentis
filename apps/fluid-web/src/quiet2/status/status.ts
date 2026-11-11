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
 *  - FOUR FACTS, NONE IMPLYING ANOTHER (WS-C, docs/modernization/
 *    QUIET-CHAT-INTERFACE.md): a run ENDED; an agent CLAIMED an outcome
 *    (`outcome-claimed`); the objective was RECORDED MET (`satisfied_by`, an
 *    `expectation-met` -- for agent work written only by reconciliation after
 *    the checks, else the owner's or the system's close); and it was VERIFIED
 *    (the work overview's `verified` state: a review's pass by somebody other
 *    than its claimants). A reply is none of them and a run ending is none of
 *    them. A claim the checks hold back (`outcome-pending`), a `partly` and a
 *    `not-met` claim are said in the server's words ("Claimed met · pending:
 *    …", "Partly done · …", "Not done · …") and are never completion; only
 *    the `verified` state is ever said as verification.
 *  - WHERE THE WORK STANDS IS THE SERVER'S: each request that heads its own
 *    work has an item in the conversation's work overview (`/api/work?
 *    conversation=`, read once per conversation and again as the record
 *    moves there), whose `state` and `status_words` say it -- stopped for a
 *    consent change, delegated and not started, a claim and what
 *    reconciliation made of it, later findings. A request that heads none (a
 *    delegated child) reads its claim from the acts on its reply, once the
 *    post's status is opened.
 *  - THE POST IS COMPLETED ONLY WHEN EVERY REQUEST ON IT IS RECORDED MET
 *    and everyone it addressed has replied; one participant finishing among
 *    several says so for that participant alone.
 *
 * The words are Classic's, as Fluid's `ofExpectation` composes them (lifted
 * here: Addressing.tsx exports only its drawn component, and these facts
 * arrive with Mark 2's own conversation read rather than its card's), and the
 * work overview's own for everything WS-C added. */
import { useCallback, useEffect, useSyncExternalStore } from 'react'
import { ago, CLIENT_HEADERS } from '../../api'
import { hearPulse } from '../../fluid/identity/activity'
import { workOverviewPath } from '../../work/api'
import type { WorkItem, WorkOverview } from '../../work/contract'
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
 *  status reads it: who did what, when, under what, and its detail. */
export interface PostAct {
  id: Id; act: string; at: number; actor: Id | null; about?: Id[] | null; because?: string | null; execution?: string | null
  caused_by?: Id | null; detail?: Record<string, unknown> | null
}

/** What the conversation's work overview says of one request that heads its
 *  own work (`/api/work?conversation=`): every word the server's. */
export type WorkFact = Pick<WorkItem, 'expectation' | 'state' | 'status_words'>
  & Partial<Pick<WorkItem, 'objective_met' | 'claim' | 'later_findings' | 'group'>>

/* -- a claim, and what the record made of it ---------------------------------
   An agent's claim (`outcome-claimed`) is its own word about its own request.
   What reconciliation recorded of it is a separate fact: `met` (an
   `expectation-met` naming the claim), `pending` (an `outcome-pending`, with
   its reasons), or, for `partly` and `not-met`, the claim as it stands. A
   claim of met nothing has reconciled yet is said as exactly that. */
export interface ClaimFact {
  result: 'met' | 'partly' | 'not-met' | string
  summary: string
  evidence: string[]
  by: string | null
  via: string | null
  recorded: 'met' | 'pending' | 'partly' | 'not-met' | null
  reasons: string[]
}

/** The claim the work overview read for this request, where it read one. */
export function claimOfWork(w: WorkFact | undefined): ClaimFact | null {
  const c = w?.claim
  if (!c) return null
  return { result: c.result, summary: c.summary ?? '', evidence: c.evidence ?? [], by: c.participant_alias ?? null,
    via: c.via ?? null, recorded: c.recorded ?? null, reasons: c.reasons ?? [] }
}

const str = (x: unknown): string | null => (typeof x === 'string' && x ? x : null)

/** The newest claim about `expectation` among these acts (the acts on its
 *  reply), and what reconciliation recorded of it. Null where none is there. */
export function claimOfActs(acts: PostAct[] | null | undefined, expectation: Id): ClaimFact | null {
  if (!acts?.length) return null
  const claims = acts.filter((a) => a.act === 'outcome-claimed' && a.caused_by === expectation)
  const c = claims[claims.length - 1]
  if (!c) return null
  const d = c.detail ?? {}
  const result = str(d.result) ?? 'met'
  const met = acts.some((a) => a.act === 'expectation-met' && a.caused_by === expectation && a.detail?.reconciled_from === c.id)
  const pend = acts.filter((a) => a.act === 'outcome-pending' && a.detail?.claim === c.id)
  const last = pend[pend.length - 1]
  const reasons = Array.isArray(last?.detail?.reasons) ? (last!.detail!.reasons as unknown[]).map(String) : []
  const recorded: ClaimFact['recorded'] = met ? 'met' : last ? 'pending'
    : result === 'partly' ? 'partly' : result === 'not-met' ? 'not-met' : null
  return { result, summary: str(d.summary) ?? str(c.because) ?? '', evidence: Array.isArray(d.evidence) ? d.evidence.map(String) : [],
    by: null, via: str(d.via), recorded, reasons }
}

/** A claim's line, in the work overview's words (`work_overview` status
 *  words): never completion unless it was recorded met. */
export function claimLine(c: ClaimFact): string {
  switch (c.recorded) {
    case 'met': return 'Objective met'
    case 'pending': return `Claimed met · pending: ${c.reasons[0] ?? 'not yet reconciled'}`
    case 'partly': return `Partly done · ${c.summary || 'no summary given'}`
    case 'not-met': return `Not done · ${c.summary || 'no summary given'}`
    default: return c.result === 'partly' ? `Partly done · ${c.summary || 'no summary given'}`
      : c.result === 'not-met' ? `Not done · ${c.summary || 'no summary given'}`
        : 'Claimed met · not recorded met yet'
  }
}

/** The work overview's states in which a carrier's claim stands unmet. */
const CLAIM_STATES = new Set(['claim-pending', 'claimed-partly', 'claimed-not-met'])

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
export type AskState = 'withdrawn' | 'lapsed' | 'verified' | 'completed' | 'answered' | 'running' | 'stopped' | 'unclaimed' | 'claimed'
  | 'handed-on' | 'failed' | 'replied' | 'awaiting-person' | 'pending'

/** The kinds of request a person answers rather than a run: a decision, an
 *  input to fill in. Waiting on one is waiting on a decision. */
const PERSON_KINDS = new Set(['decision', 'input', 'question', 'permission'])

/** `w`: the work overview's item for this request, where it heads its own
 *  work; `claim`: the newest claim about it (from `w`, else from the acts on
 *  its reply). Neither is needed: without them a request reads as before. */
export function askState(e: ExpectationFact, w?: WorkFact, claim?: ClaimFact | null): AskState {
  if (e.withdrawn) return 'withdrawn'
  if (e.lapsed) return 'lapsed'
  /* RECORDED MET; VERIFIED ONLY WHERE THE SERVER SAYS `verified` */
  if (e.satisfied_by?.length) return w?.state === 'verified' ? 'verified' : 'completed'
  if (e.live_execution) return 'running'
  /* stopped for a consent change and not restarted: somebody's to continue */
  if (w?.state === 'consent-stopped') return 'stopped'
  if (e.unassigned) return 'unclaimed'
  /* a claim not recorded met: the server's state, else the claim read */
  if ((w && CLAIM_STATES.has(w.state)) || (claim && claim.recorded !== 'met')) return 'claimed'
  if (e.delegations?.length) return 'handed-on'
  if (e.failures?.length && !e.response_present) return 'failed'
  /* A DECISION FORM'S QUESTION, AN INPUT: the record's own rule says what
     answers them (the reply that names the question, the set marked ready),
     so a response present is their answer; so is a decision or question the
     server names its answering reply for (`answered_by`, the owner's own
     words). Any other reply settles nothing. */
  if (e.response_present) return e.form || e.expects === 'input' || (PERSON_KINDS.has(e.expects) && e.answered_by) ? 'answered' : 'replied'
  return PERSON_KINDS.has(e.expects) ? 'awaiting-person' : 'pending'
}

/* -- one participant's line ----------------------------------------------- */

export type PartyState = 'running' | 'waiting' | 'failed' | 'stopped' | 'unclaimed' | 'pending' | 'claimed' | 'replied' | 'completed' | 'verified' | 'closed'

export interface Ask { fact: ExpectationFact; state: AskState; words: string
  /** what was asked, where `expects` is the asker's own words rather than a
   *  kind of request: shown apart from the sentence, never as its noun */
  spec: string | null
  /** the work overview's item for it, where it heads its own work */
  work?: WorkFact
  /** the newest claim about it, and what the record made of it */
  claim?: ClaimFact | null
  /** its state in a few words, where the record says more than the kind of
   *  state: the server's status words, or a claim's line */
  line?: string | null }

/** The kinds of request `expects` names when it is a kind. It is often the
 *  asker's whole specification instead (hundreds of characters): then the
 *  sentence says "request" and the words are shown beside it. */
const KINDS = new Set(['result', 'decision', 'input', 'question', 'permission', 'review', 'answer', 'response', 'report', 'finding', 'brief', 'follow-up', 'approval', 'confirmation'])
const kindOf = (e: ExpectationFact) => { const k = (e.expects ?? '').trim().toLowerCase(); return KINDS.has(k) ? k : 'request' }
const specOf = (e: ExpectationFact) => { const k = (e.expects ?? '').trim(); return k && !KINDS.has(k.toLowerCase()) ? k : null }

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
const FIRST: PartyState[] = ['running', 'failed', 'stopped', 'unclaimed', 'waiting', 'pending', 'claimed', 'replied', 'completed', 'verified', 'closed']
const OF_ASK: Record<AskState, PartyState> = {
  running: 'running', failed: 'failed', stopped: 'stopped', unclaimed: 'unclaimed', 'handed-on': 'waiting', 'awaiting-person': 'waiting',
  pending: 'pending', claimed: 'claimed', replied: 'replied', completed: 'completed', verified: 'verified', answered: 'completed',
  withdrawn: 'closed', lapsed: 'closed',
}
const first = (xs: PartyState[]) => xs.reduce((a, b) => (FIRST.indexOf(b) < FIRST.indexOf(a) ? b : a))

const at = (n: string | null | undefined) => (n ? (n.startsWith('@') ? n : '@' + n) : 'somebody')

/** Classic's words for one request (Fluid's `ofExpectation`), with what its
 *  state rests on. */
function askWords(e: ExpectationFact, s: AskState, w?: WorkFact, claim?: ClaimFact | null): string {
  const of = at(e.of_alias ?? null)
  const kind = kindOf(e)
  const said = w?.status_words ? ` (${w.status_words})` : ''
  switch (s) {
    case 'withdrawn': return `${at(e.withdrawn?.by_alias ?? e.of_alias)} withdrew this ${kind}${e.withdrawn?.because ? `: ${e.withdrawn.because}` : ''}. It was not answered.`
    case 'lapsed': return `${at(e.by_alias)} no longer asks this: ${(e.lapsed?.because ?? 'its run can no longer take an answer').replace(/^no longer asked: /, '')}. It was not answered.`
    case 'verified': return `This ${kind} is recorded met, and verified by somebody other than whoever claimed it${said}.`
    case 'completed': return `This ${kind} is recorded met${said}. Nothing records it as independently verified.`
    case 'answered': return `${of} has answered this ${kind}${e.form ? ', by the reply that names it' : ''}.`
    case 'running': return `${of} is working on this ${kind} now.`
    case 'stopped': return `${of}'s run on this ${kind} was stopped for a consent change and not restarted${said}. It is not complete; continuing it is somebody's act.`
    case 'unclaimed': return `${at(e.by_alias)} asked for a ${kind}, and nobody is carrying it${e.unresolved_because ? `: ${e.unresolved_because}` : ''}.`
    case 'claimed': {
      const line = w && CLAIM_STATES.has(w.state) ? w.status_words : claim ? claimLine(claim) : 'Claimed, not recorded met'
      return `${of} claims an outcome: ${line}. That is their own word about their own work; it is not recorded met.`
    }
    case 'handed-on': {
      const n = e.delegations!.length
      return `${of} handed ${n === 1 ? 'part of this on' : `parts of this on ${n} times`}; each is its own request${w ? '' : ', and whether those are done is not read here'}. The ${kind} itself is still owed${e.response_present ? ', though they have replied' : ''}${said}.`
    }
    case 'failed': return `${of} was to answer this, and it failed: ${e.failures![e.failures!.length - 1].because ?? 'no reason was recorded'}.`
    case 'replied': return `${of} has replied. Nothing records the ${kind} as met, and no outcome is claimed for it${e.failures?.length ? `; ${e.failures.length === 1 ? 'an earlier attempt' : `${e.failures.length} earlier attempts`} failed` : ''}${said}.`
    case 'awaiting-person': return `${at(e.by_alias)} is waiting on ${of} for a ${kind}.`
    case 'pending': return `${at(e.by_alias)} asked ${of} for a ${kind}. No reply, live run or failure is recorded for it yet${said}.`
  }
}

/** An ask's state in a few words where the record says more than its kind
 *  of state: what heads a post's status when it is the only one. */
function askLine(s: AskState, w?: WorkFact, claim?: ClaimFact | null): string | null {
  if (s === 'claimed') return w && CLAIM_STATES.has(w.state) ? w.status_words : claim ? claimLine(claim) : null
  if (s === 'stopped' || s === 'verified') return w?.status_words ?? null
  return null
}

/** What else each request's status is read with: the conversation's work
 *  overview (by expectation) and the acts on the post's replies. */
export interface StatusMore {
  work?: ReadonlyMap<Id, WorkFact> | null
  /** acts on the post and its replies: where a claim not in the work
   *  overview is read from */
  claimActs?: PostAct[] | null
}

/** Everyone a post concerns, each once, with where they stand. */
export function partiesOf(facts: StatusFacts | undefined, work: Working[], more: StatusMore = {}): Party[] {
  const by = new Map<string, Party>()
  const party = (participant: Id | null, alias: string | null, key: string) => {
    let p = by.get(key)
    if (!p) by.set(key, p = { participant, alias, addressed: null, asks: [], work: [], state: 'pending' })
    if (!p.alias && alias) p.alias = alias
    return p
  }
  for (const a of facts?.addressees ?? []) party(a.participant, a.alias, a.participant).addressed = a
  for (const e of facts?.expectations ?? []) {
    const w = more.work?.get(e.id)
    const claim = claimOfWork(w) ?? claimOfActs(more.claimActs, e.id)
    const s = askState(e, w, claim)
    party(e.of, e.of_alias, e.of ?? 'nobody:' + e.id).asks.push({ fact: e, state: s, words: askWords(e, s, w, claim), spec: specOf(e),
      work: w, claim, line: askLine(s, w, claim) })
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

export type PostState = 'running' | 'attention' | 'waiting' | 'pending' | 'claimed' | 'replied' | 'completed' | 'verified' | 'closed'

export interface PostStatus { state: PostState; label: string; parties: Party[]; summary: string }

const STATE_LABEL: Record<PostState, string> = {
  running: 'Work running', attention: 'Failed or stopped', waiting: 'Waiting on somebody',
  pending: 'Addressed; no reply recorded', claimed: 'Outcome claimed, not recorded met', replied: 'Replied, not marked complete',
  completed: 'Objective met', verified: 'Objective met · verified', closed: 'Closed without completion',
}
const PARTY_WORD: Record<PartyState, string> = {
  running: 'working', waiting: 'waiting', failed: 'failed', stopped: 'stopped', unclaimed: 'nobody carrying it', pending: 'addressed',
  claimed: 'claimed, not met', replied: 'replied', completed: 'met', verified: 'met · verified', closed: 'closed',
}

/** The post's status from its parties, or null when it addresses nobody,
 *  asks nothing and nobody is working on it. */
export function statusOf(facts: StatusFacts | undefined, work: Working[], more: StatusMore = {}): PostStatus | null {
  const parties = partiesOf(facts, work, more)
  if (!parties.length) return null
  const has = (s: PartyState) => parties.some((p) => p.state === s)
  const met = (p: Party) => p.state === 'completed' || p.state === 'verified'
  const state: PostState = has('running') ? 'running'
    : has('failed') || has('stopped') || has('unclaimed') ? 'attention'
      : has('waiting') ? 'waiting'
        : has('pending') ? 'pending'
          : has('claimed') ? 'claimed'
            : has('replied') ? 'replied'
              /* every request recorded met, everyone addressed answered;
                 verified only where every one of them is */
              : parties.every((p) => p.state === 'verified') ? 'verified'
                : parties.every(met) ? 'completed'
                  : 'closed'
  /* a person who answered what they were asked is said as answered */
  const word = (p: Party) => (p.state === 'completed' && p.asks.length && p.asks.every((x) => x.state === 'answered') ? 'answered' : PARTY_WORD[p.state])
  const counts = new Map<string, number>()
  for (const p of [...parties].sort((a, b) => FIRST.indexOf(a.state) - FIRST.indexOf(b.state))) counts.set(word(p), (counts.get(word(p)) ?? 0) + 1)
  const summary = parties.length === 1 ? (parties[0].participant ? `${at(parties[0].alias)}: ${word(parties[0])}` : 'Nobody is carrying it')
    : [...counts].map(([w, n]) => `${n} ${w}`).join(' · ')
  /* ONE REQUEST ON THE POST, whose state the record says in more words (a
     claim's line, a consent stop, a verification): those words head it */
  const asks = parties.flatMap((p) => p.asks)
  const only = asks.length === 1 && parties.length === 1 && OF_ASK[asks[0].state] === parties[0].state ? asks[0].line : null
  /* replies where nothing was asked: there is nothing to mark complete */
  const label = only ? only
    : state === 'replied' && !parties.some((p) => p.asks.length) ? 'Replied'
      : state === 'closed' && parties.some(met) ? 'Closed; not every request met' : STATE_LABEL[state]
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
    case 'stopped': return `Stopped for a consent change: ${who}`
    case 'unclaimed': return 'Nobody carries it'
    case 'pending': return p.addressed?.addressed_later ? `Brought in: ${who}` : p.addressed ? `Addressed to ${who}` : `Asked of ${who}`
    case 'claimed': return `Claimed, not met: ${who}`
    case 'replied': return `Replied: ${who}`
    case 'verified': return `Met and verified: ${who}`
    case 'completed': return asks.length && asks.every((s) => s === 'answered') ? `Answered by ${who}` : `Met: ${who}`
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
  /** the latest of them (its `execution-started` act: the run's id) */
  lastRun: Id | null
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
  const started = acts.filter((a) => a.act === 'execution-started' && mine(a))
  const runs = started.map((a) => a.at)
  /* waiting on other work: their latest `work-awaited`, unless they were
     resumed or started again after it */
  const lastWait = [...acts].reverse().find((a) => a.act === 'work-awaited' && mine(a))
  const after = lastWait && acts.some((a) => a.at > lastWait.at && ((a.act === 'work-resumed' && (a.about ?? []).includes(who!)) || (a.act === 'execution-started' && mine(a))))
  const failed = [...acts].reverse().find((a) => a.act === 'delivery-failed' && mine(a))?.at ?? null
  return { asked: asked ?? null, runs, lastRun: started[started.length - 1]?.id ?? null,
    awaiting: lastWait && !after ? { at: lastWait.at, because: lastWait.because ?? null } : null, failed }
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
       conversation whose drawn post still owes something, at most every 10 s
       a post -- no poller of its own.
   Who is working now is the activity reader's, already live. */

interface Held { facts: StatusFacts | undefined; acts: PostAct[] | null; read: number }
const held = new Map<Id, Held>()
/* HEARD PER POST: a read re-renders only the posts whose facts or acts it
   changed, never every post drawn */
const heard = new Map<Id, Set<() => void>>()
const ver = new Map<Id, number>()
/* A REPLY'S ACTS ARE READ FOR THE POST IT ANSWERS (where a claim about the
   post's request is recorded): reading one tells that post too */
const readFor = new Map<Id, Set<Id>>()
const tellOne = (id: Id) => { ver.set(id, (ver.get(id) ?? 0) + 1); heard.get(id)?.forEach((fn) => fn()) }
const tell = (id: Id) => { tellOne(id); readFor.get(id)?.forEach(tellOne) }
const subTo = (id: Id) => (fn: () => void) => {
  const fns = heard.get(id) ?? new Set()
  fns.add(fn); heard.set(id, fns)
  return () => { fns.delete(fn); if (!fns.size) heard.delete(id) }
}
const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b)

/** The conversation read's facts for a post: newer than what was held. */
export function seedStatus(id: Id, facts: StatusFacts | undefined) {
  const had = held.get(id)
  held.set(id, { facts, acts: had?.acts ?? null, read: had?.read ?? 0 })
  if (had && !same(had.facts, facts)) tell(id)
}

/** Posts drawn now whose status still owes something, their conversation,
 *  and whether somebody is running on them: what a move reads again. */
const followed = new Map<Id, { conversation: Id | null; running: boolean; n: number }>()
const asked = new Set<Id>()
const later = new Map<Id, number>()
let flushing = 0
let reading = false
const MOST = 64   // production's TURNS_PER_READ
/** No post is read again on the pulse sooner than this after its last read
 *  (the read is the heavy Turn detail): a move inside it is read once, then. */
const SPACING = 10000

function want(id: Id, now = false) {
  const wait = now ? 0 : (held.get(id)?.read ?? 0) + SPACING - Date.now()
  if (wait > 0) {
    if (!later.has(id)) later.set(id, window.setTimeout(() => { later.delete(id); if (followed.has(id)) want(id, true) }, wait))
    return
  }
  asked.add(id)
  if (!flushing) flushing = window.setTimeout(flush, 40)
}
async function flush() {
  flushing = 0
  if (reading) { flushing = window.setTimeout(flush, 1000); return }
  const batch = [...asked].slice(0, MOST)
  batch.forEach((id) => asked.delete(id))
  if (asked.size) flushing = window.setTimeout(flush, 40)
  if (!batch.length) return
  reading = true
  const moved: Id[] = []
  try {
    const res = await fetch('/api/turns?ids=' + batch.map(encodeURIComponent).join(','), { headers: CLIENT_HEADERS })
    const body = await res.json()
    for (const row of body.turns ?? []) {
      if (!row.turn) continue
      const had = held.get(row.id)
      const next: Held = { facts: factsOf(row.turn), acts: (row.turn.inspector?.operational ?? []) as PostAct[], read: Date.now() }
      held.set(row.id, next)
      if (!had || !same(had.facts, next.facts) || !same(had.acts, next.acts)) moved.push(row.id)
    }
  } catch { /* what was read last stands until it can be read again */ } finally { reading = false }
  moved.forEach(tell)
}

let stopHearing: (() => void) | null = null
function hear() {
  if (stopHearing) return
  stopHearing = hearPulse((m, where) => {
    if (m !== 'durable') return
    for (const [id, f] of followed) {
      /* its conversation moved (or the pulse could not say where), or a
         run's acts moved while somebody runs on it */
      if (!where || where.loose || (f.conversation && where.conversations.includes(f.conversation))
        || (f.running && where.executions.length > 0)) want(id)
    }
  })
}

/** The replies that answered a post's requests, as its facts name them. */
const repliesOf = (facts: StatusFacts | undefined): Id[] =>
  [...new Set((facts?.expectations ?? []).map((e) => e.answered_by?.turn).filter((t): t is Id => !!t))]

/** The post's facts as last read, its acts once read, the acts on its
 *  replies (where a claim about its requests is recorded) once read, and the
 *  way to ask for them (now: the view is open). */
export function usePostStatus(id: Id, fallback: StatusFacts | undefined, live: boolean): {
  facts: StatusFacts | undefined; acts: PostAct[] | null; claimActs: PostAct[] | null; readActs: () => void
} {
  const sub = useCallback((fn: () => void) => subTo(id)(fn), [id])
  useSyncExternalStore(sub, () => ver.get(id) ?? 0)
  const h = held.get(id)
  const facts = h ? h.facts : fallback
  const replies = repliesOf(facts)
  const repliesKey = replies.join(',')
  const readActs = useCallback(() => {
    if (!live) return
    want(id, true)
    for (const r of repliesKey ? repliesKey.split(',') : []) {
      if (r === id) continue
      const posts = readFor.get(r) ?? new Set<Id>()
      posts.add(id); readFor.set(r, posts)
      want(r, true)
    }
  }, [id, live, repliesKey])
  const acts = h?.acts ?? null
  const fromReplies = replies.filter((r) => r !== id).map((r) => held.get(r)?.acts).filter((a): a is PostAct[] => !!a)
  const claimActs = acts || fromReplies.length ? [...(acts ?? []), ...fromReplies.flat()] : null
  return { facts, acts, claimActs, readActs }
}

/* -- the conversation's work, as its overview says it -----------------------
   `/api/work?conversation=` (the same read Fluid's work pills make, through
   `workOverviewPath`): every request in the conversation that heads its own
   work, with its state and the server's words for it. READ ONCE per
   conversation while a drawn post there asks something, and again when the
   pulse says the record moved there (or could not say where), no sooner than
   WORK_SPACING after the last read: the read is a projection over the
   record, seconds of the server's time on a big Brain, as for Fluid's pills
   (PILL_SPACING). A failed read leaves what was read last standing. */
const WORK_SPACING = 15000
interface ConvWork { items: Map<Id, WorkFact> | null; read: number; reading: boolean; again: boolean; timer: number; n: number }
const convWork = new Map<Id, ConvWork>()
const workVer = new Map<Id, number>()
const workHeard = new Map<Id, Set<() => void>>()
const tellWork = (c: Id) => { workVer.set(c, (workVer.get(c) ?? 0) + 1); workHeard.get(c)?.forEach((fn) => fn()) }

/** The work overview's items, by the request each heads. */
export function workByExpectation(o: Pick<WorkOverview, 'items'> | null | undefined): Map<Id, WorkFact> {
  const out = new Map<Id, WorkFact>()
  for (const it of o?.items ?? []) if (it?.expectation) out.set(it.expectation, it)
  return out
}

async function readWork(c: Id) {
  const w = convWork.get(c)
  if (!w) return
  if (w.reading) { w.again = true; return }
  w.reading = true; w.again = false; w.read = Date.now()
  try {
    const res = await fetch(workOverviewPath({ viewer: null, conversation: c }), { headers: CLIENT_HEADERS })
    const body = await res.json() as WorkOverview & { error?: string }
    if (res.ok && body && !body.error) {
      const next = workByExpectation(body)
      if (!same([...(w.items ?? new Map()).entries()], [...next.entries()])) { w.items = next; tellWork(c) }
    }
  } catch { /* what was read last stands until it can be read again */ } finally {
    w.reading = false
    if (w.again && w.n > 0) wantWork(c)
  }
}

function wantWork(c: Id) {
  const w = convWork.get(c)
  if (!w || w.timer) return
  const wait = Math.max(0, w.read + WORK_SPACING - Date.now())
  w.timer = window.setTimeout(() => { w.timer = 0; if (w.n > 0) void readWork(c) }, wait)
}

let stopWorkHearing: (() => void) | null = null
function hearWork() {
  if (stopWorkHearing) return
  stopWorkHearing = hearPulse((m, where) => {
    if (m !== 'durable') return
    for (const [c, w] of convWork) if (w.n > 0 && (!where || where.loose || where.conversations.includes(c))) wantWork(c)
  })
}

/** The work overview's items for `conversation`, by expectation, while
 *  `wanted` (a drawn real post there asks something); null until read. */
export function useConversationWork(conversation: Id | null, wanted: boolean): ReadonlyMap<Id, WorkFact> | null {
  const sub = useCallback((fn: () => void) => {
    if (!conversation) return () => {}
    const fns = workHeard.get(conversation) ?? new Set()
    fns.add(fn); workHeard.set(conversation, fns)
    return () => { fns.delete(fn); if (!fns.size) workHeard.delete(conversation) }
  }, [conversation])
  useSyncExternalStore(sub, () => (conversation ? workVer.get(conversation) ?? 0 : 0))
  useEffect(() => {
    if (!conversation || !wanted) return
    let w = convWork.get(conversation)
    if (!w) convWork.set(conversation, w = { items: null, read: 0, reading: false, again: false, timer: 0, n: 0 })
    w.n += 1
    /* first asked: read now; asked again after a while unread: read soon */
    if (!w.read) void readWork(conversation)
    else if (Date.now() - w.read >= WORK_SPACING) wantWork(conversation)
    hearWork()
    const held = w
    return () => {
      held.n -= 1
      if (held.n <= 0 && held.timer) { clearTimeout(held.timer); held.timer = 0 }
      if (![...convWork.values()].some((x) => x.n > 0) && stopWorkHearing) { stopWorkHearing(); stopWorkHearing = null }
    }
  }, [conversation, wanted])
  return conversation ? convWork.get(conversation)?.items ?? null : null
}

/** Follows a drawn post on the pulse while its status still owes something
 *  (`owed`): somebody running, waiting, or addressed without a reply. A post
 *  with no status, or one settled, is not followed; one addressed after it
 *  was drawn arrives with the conversation's next read (`seedStatus`). */
export function useFollowStatus(id: Id, conversation: Id | null, owed: boolean, running: boolean) {
  useEffect(() => {
    if (!owed) return
    const f = followed.get(id) ?? { conversation, running, n: 0 }
    f.n += 1; f.running = running; f.conversation = conversation
    followed.set(id, f)
    hear()
    return () => {
      f.n -= 1
      if (f.n <= 0) { followed.delete(id); const t = later.get(id); if (t) { clearTimeout(t); later.delete(id) } }
      if (!followed.size && stopHearing) { stopHearing(); stopHearing = null }
    }
  }, [id, conversation, owed, running])
}
