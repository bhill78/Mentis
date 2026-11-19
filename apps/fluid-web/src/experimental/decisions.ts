/* WHAT A DECISION FORM IS DRAWN FROM, AND WHAT ANSWERING IT SENDS
 * (forms build P9; design revision 3, section 9B).
 *
 * ONE FORM, EVERY VIEW. Classic's Turn, Fluid's conversation column, its
 * thread sheet and full screen, and the Needs You zone all draw a decision
 * with ./types/decision.tsx from this. What it is drawn from is what the
 * record says (`GET /fluid/api/decisions?post=`, or Classic's own Turn view,
 * which carries the same fields): every decision form on the post with each
 * of its questions, and each ask recorded on the post itself -- every
 * decision asked before P7, drawn as a one-question form.
 *
 * ANSWERING IS TODAY'S ANSWER. Each question is answered by one reply that
 * names it, posted to `POST /api/conversations/<id>/turns` exactly as the
 * decision cards posted it: a choice is its label then anything added, with
 * `chose: {expectation, option, label}`; a withdrawal is the reason with
 * `chose: {expectation, withdraw: true}`; an answer in the owner's own words
 * is the words, and on a question of a form also `chose: {expectation}`, so
 * it closes that question and no other (P7). The bodies are built here, not
 * imported from the composer, so this module reaches nothing production's
 * pages do not already share; `tests/test_decision_form_ui.py` runs them
 * beside `chosenBody` and `withdrawBody` and requires the same output.
 *
 * WHAT WAS SENT is kept by question (./decisionOutbox.ts), in the browser's
 * storage, under an operation key the server records a post once for. So
 * every copy of a form -- the post, its thread, full screen, a zone, another
 * tab -- locks while it is sent; a refresh still knows what was sent; and
 * sending the same answer again cannot make a second post. Recorded is what
 * THE SERVER said it wrote, or what the record read shows; never the request
 * having been made.
 * ------------------------------------------------------------------------ */
import { useEffect, useSyncExternalStore } from 'react'
import { fluidFetch } from '../fluid/http'
import * as O from './decisionOutbox'

const API = '/fluid/api/decisions'
const HEADERS = { 'X-Mentis-Client': '1', 'Content-Type': 'application/json' }
/** How often a form with an open question on screen rereads. */
export const REREAD_MS = 5000

export interface Option {
  label: string
  consequence?: string
  per_finding?: boolean
  /** each finding: what it says, why it was set aside where that was
   *  recorded, and its exact reference (shown on demand, never as its words) */
  findings?: { ref: string; label: string; why?: string }[]
  /** what choosing this does to each finding, on work found along the way */
  selections?: Record<string, string>
}

export type FindingChoice = 'pursue' | 'defer' | 'dismiss'

export interface StoppedWork {
  request: string
  request_number: number | null
  request_said: string | null
  requester_alias: string | null
  run: string
  execution: string | null
  runtime: string | null
  carrier_alias: string | null
  run_state: string | null
  stopped_at: number | null
}

/** One ask as the Turn view states it (`mentis.web._expectation_view`). */
export interface Ask {
  id: string
  expects: string
  of: string | null
  of_alias?: string | null
  by?: string
  by_alias: string
  because?: string | null
  options?: Option[] | null
  response_present: boolean
  withdrawn?: { act: string; by: string; by_alias?: string | null; at: number; because?: string | null; reply?: string | null } | null
  /** a run's permission question its run can no longer take an answer to */
  lapsed?: { act: string; by: string; by_alias?: string | null; at: number; because?: string | null; reason?: string | null; run?: string | null } | null
  answered_by?: {
    turn: string
    number: number | null
    said: string
    author: string
    chose: { expectation: string; option: number; label: string; withdraw?: boolean } | null
    withdrawn?: boolean
  } | null
  continues_work?: boolean
  stopped_work?: StoppedWork | null
  /** a question of a decision form (P7): its form, place and own words */
  form?: string
  index?: number
  question?: string | null
}

/** One decision form as the record holds it (`Conversations.decision_form`). */
export interface FormRow {
  form: string
  post: string | null
  pending: boolean
  conversation: string
  asked_by: string
  because?: string | null
  questions: { expectation: string }[]
  /** a permission form's operation (docs/run-consent.md §3); absent otherwise */
  operation?: Operation | null
}

/** WHAT A RUN ASKS PERMISSION FOR, described: what it would do, what it
 *  affects, why it belongs to the task, and whether it is inside the task's
 *  boundary. The question is this description, never the raw command, which
 *  is kept for Details. Every field may be absent. */
export interface Operation {
  summary?: string
  action?: string
  category?: string
  resources?: string[]
  workspace?: string | null
  why?: string | null
  agent_says?: string | null
  tool?: string
  tool_label?: string
  within?: boolean
  outside?: string[]
  command?: string | null
  cwd?: string | null
  kind?: string
}

/** The post a form is on, as answering it needs it. */
export interface PostHead {
  id: string
  number: number | null
  author: string
  author_alias: string | null
  topics: string[]
  conversation: string | null
  deleted?: boolean
}

export interface Read {
  post: PostHead | null
  you: string | null
  expectations: Ask[]
  decision_forms: FormRow[]
}

/** What one drawn form holds: a decision form, or one ask on its own post. */
export interface Group {
  key: string
  form: string | null
  asks: Ask[]
  post: PostHead | null
  conversation: string | null
  because: string | null
  /** what a permission form asks about, from its form row */
  operation: Operation | null
}

/** The forms on this read, in order: each ask asked as its own post first
 *  (the post is its question), then each decision form on it. `only`
 *  keeps the forms holding any of these asks (a Needs You entry). */
export function groupsOf(r: Read, only?: string[]): Group[] {
  const byId = new Map(r.expectations.map((e) => [e.id, e]))
  const inForm = new Set(r.decision_forms.flatMap((f) => f.questions.map((q) => q.expectation)))
  const conv = r.post?.conversation ?? null
  /* INPUT ON A BLOCK (`request_input`) IS ANSWERED BY DONE AT THAT BLOCK, never
     by a reply, so it is not drawn as something a reply could answer. */
  const out: Group[] = r.expectations
    .filter((e) => !inForm.has(e.id) && !e.form && e.expects !== 'input')
    .map((e) => ({ key: e.id, form: null, asks: [e], post: r.post, conversation: conv, because: null, operation: null }))
  for (const f of r.decision_forms) {
    const asks = f.questions.map((q) => byId.get(q.expectation)).filter((e): e is Ask => !!e)
    if (asks.length) out.push({ key: f.form, form: f.form, asks, post: r.post, conversation: f.conversation ?? conv, because: f.because ?? null, operation: f.operation ?? null })
  }
  return only ? out.filter((g) => g.asks.some((a) => only.includes(a.id))) : out
}

/** Classic's Turn view carries what the read does: drawn from it as is. */
export function fromTurn(
  turn: { id: string; number: number; author: string; author_alias: string; topics: string[]; expectations: Ask[]; decision_forms?: FormRow[]; deleted?: unknown },
  conversation: string,
  you: string | null,
): Read {
  return {
    post: { id: turn.id, number: turn.number, author: turn.author, author_alias: turn.author_alias, topics: turn.topics, conversation, deleted: !!turn.deleted },
    you,
    expectations: turn.expectations,
    decision_forms: turn.decision_forms ?? [],
  }
}

/* ------------------------------------------------------------------ bodies */

/** What the owner is told when they withdraw without saying why. */
export const WITHDRAW_NEEDS_REASON =
  'Withdraw needs a reason. Write why in the field below, then press Withdraw.'

const SAID: Record<FindingChoice, string> = { pursue: 'Pursue', defer: 'Keep deferred', dismiss: 'Dismiss' }

/** What is chosen for one question before it is sent. */
export type Pick =
  | { kind: 'option'; option: number; findings?: Record<string, FindingChoice> }
  | { kind: 'own' }
  | { kind: 'withdraw' }

/** The reply that answers one question, as the decision cards posted it.
 *  Throws, saying why, when it cannot be sent: a withdrawal with no reason,
 *  own words with no words. `continueWith` hands the work back to the
 *  post's author, which only an ask on its own post offers (a form's work
 *  resumes by itself when its last question closes). */
export function replyFor({ ask, pick, text, me, post, continueWith }: {
  ask: Ask
  pick: Pick
  text: string
  me: string | null
  post: PostHead | null
  continueWith?: string | null
}) {
  const added = text.trim()
  const topics = post?.topics ?? []
  const to = post?.author ?? ask.by ?? null
  const base = (words: string, parts: { type: string; text: string }[]) => ({
    author: me,
    parts,
    text: words,
    addressed_to: [] as string[],
    topics,
    because: null as string | null,
    action: 'record-only' as string,
    dispatch: [] as unknown[],
  })
  let body: ReturnType<typeof base> & { chose?: unknown }
  if (pick.kind === 'withdraw') {
    if (!added) throw new Error(WITHDRAW_NEEDS_REASON)
    body = { ...base(added, [{ type: 'text', text: added }]), chose: { expectation: ask.id, withdraw: true } }
  } else if (pick.kind === 'option') {
    const o = (ask.options ?? [])[pick.option]
    if (!o) throw new Error('that is not one of the options offered')
    const selections = o.per_finding && o.findings
      ? Object.fromEntries(o.findings.map((f) => [f.ref, pick.findings?.[f.ref] ?? 'defer']))
      : undefined
    const each = selections && o.findings ? o.findings.map((f) => `${SAID[selections[f.ref]]}: ${f.label}`) : []
    const head = [o.label, ...each].join('\n')
    body = {
      ...base(head + (added ? '\n\n' + added : ''),
        [{ type: 'text', text: head + (added ? '\n\n' : '') }, ...(added ? [{ type: 'text', text: added }] : [])]),
      chose: { expectation: ask.id, option: pick.option, label: o.label, ...(selections ? { selections } : {}) },
    }
  } else {
    if (!added) throw new Error('Write your answer in the field below, or choose one of the options.')
    body = { ...base(added, [{ type: 'text', text: added }]), ...(ask.form ? { chose: { expectation: ask.id } } : {}) }
  }
  if (continueWith && pick.kind !== 'withdraw') {
    body.action = 'ask-participant'
    body.dispatch = [{ participant: continueWith, runtime: null, model: null, effort: null, persona: null, new_instance: false, coordinate: false }]
  }
  return {
    ...body,
    replies_to: post?.id ?? null,
    addressed_to: to ? [to] : [],
    because: `${pick.kind === 'withdraw' ? 'withdrawing' : 'answering'} expectation ${ask.id}`,
  }
}

/* ------------------------------------------------------------------- store */

interface Entry { read?: Read; error?: string; at: number }
const entries = new Map<string, Entry>()
const subs = new Map<string, Set<() => void>>()
const inflight = new Map<string, Promise<void>>()

function notify(key: string) { subs.get(key)?.forEach((f) => f()) }
function subscribe(key: string, f: () => void) {
  let s = subs.get(key)
  if (!s) subs.set(key, (s = new Set()))
  s.add(f)
  return () => { s!.delete(f) }
}

/** The key a read is held under: a post, or asks by id. */
export const keyOf = (q: { post?: string | null; ids?: string[] }) => (q.post ? 'post:' + q.post : 'ids:' + (q.ids ?? []).join(','))

/** Read (or reread) what is held under this key. */
export function load(key: string): Promise<void> {
  const going = inflight.get(key)
  if (going) return going
  const url = key.startsWith('post:') ? `${API}?post=${encodeURIComponent(key.slice(5))}` : `${API}?ids=${encodeURIComponent(key.slice(4))}`
  const p = fluidFetch(url, { headers: HEADERS })
    .then(async (r) => {
      const got = await r.json().catch(() => null)
      if (!r.ok || !got) throw new Error(got?.error ?? r.statusText)
      entries.set(key, { read: got as Read, at: Date.now() })
      settle(got as Read)
    })
    .catch((e) => { entries.set(key, { ...(entries.get(key) ?? { at: 0 }), error: String((e as Error)?.message ?? e) }) })
    .finally(() => { inflight.delete(key); notify(key) })
  inflight.set(key, p)
  return p
}

/** Forget and immediately reread one post's decision forms. A permission can
 *  be recorded after this post was already drawn; its Answer action uses this
 *  instead of waiting for the five-second open-question refresh. */
export function invalidateDecisions(post: string): Promise<void> {
  const key = keyOf({ post })
  entries.delete(key)
  notify(key)
  const going = inflight.get(key)
  return going
    ? going.then(() => { entries.delete(key); return load(key) })
    : load(key)
}

/** Reread every post's forms that is held, after an answer lands. */
export function reloadAll() { return Promise.all([...entries.keys()].map(load)) }

/** What is held for a post (or asks), read on first use, on focus, and
 *  every few seconds while one of its questions is open. Off: nothing. */
export function useDecisions(key: string | null): Entry | undefined {
  const read = () => (key ? entries.get(key) : undefined)
  const got = useSyncExternalStore((f) => (key ? subscribe(key, f) : () => {}), read, read)
  /* Only what is owed by the person answering here keeps it rereading: an
     agent's open request on the same post is not this form's to watch. */
  const you = got?.read?.you
  const open = !!got?.read?.expectations.some((e) => !e.response_present && !!you && e.of === you)
  useEffect(() => {
    if (!key) return
    if (!entries.has(key)) void load(key)
    const onFocus = () => void load(key)
    window.addEventListener('focus', onFocus)
    const t = open ? window.setInterval(() => { if (document.visibilityState === 'visible') void load(key) }, REREAD_MS) : 0
    return () => { window.removeEventListener('focus', onFocus); if (t) window.clearInterval(t) }
  }, [key, open])
  return got
}

/* -------------------------------------------------------------- what was sent */

export type Sent = O.Sent

const storage = (() => {
  try {
    return typeof window !== 'undefined' && window.localStorage ? window.localStorage : null
  } catch {
    return null
  }
})()
const box = O.createOutbox(storage)

const net: O.Net = {
  async post(conversation, body) {
    const res = await fluidFetch(`/api/conversations/${encodeURIComponent(conversation)}/turns`, { method: 'POST', headers: HEADERS, body: JSON.stringify(body) })
    return { status: res.status, body: await res.json().catch(() => null) }
  },
  async lookup(op, author) {
    const res = await fluidFetch(`/api/operations?op=${encodeURIComponent(op)}&author=${encodeURIComponent(author)}`, { headers: HEADERS })
    const got = await res.json().catch(() => null)
    if (!res.ok || !got || got.error || typeof got.recorded !== 'boolean') return null
    return got as { recorded: boolean; result?: Record<string, unknown> }
  },
}

const SENT = 'sent'
let snapshot = new Map(box.all().map((x) => [x.ask, x]))
/* The snapshot follows the box itself, not whoever happens to be drawn: what
   is learned before any form is on the page (a refresh asking the server) is
   what the first form to draw sees. */
box.subscribe(() => { snapshot = new Map(box.all().map((x) => [x.ask, x])); notify(SENT) })
/** Every answer that was sent and that the record does not yet show, by question. */
export function useSent(): Map<string, Sent> {
  return useSyncExternalStore((f) => subscribe(SENT, f), () => snapshot, () => snapshot)
}
export const sentFor = (ask: string): Sent | undefined => box.get(ask)

/** The record was read: a kept answer the record now shows has done its job,
 *  and from here the form is drawn from the record alone. */
function settle(r: Read) {
  for (const e of r.expectations) {
    const kept = box.get(e.id)
    if (kept && O.settledBy(kept, e)) {
      if (e.response_present) freshly.set(e.id, kept)
      box.drop(e.id)
    }
  }
}
/** Answers this page sent that the record has since shown closed their
 *  question: drawn as just-recorded here, and gone with the page. */
const freshly = new Map<string, Sent>()
export const freshOf = (ask: string): Sent | undefined => freshly.get(ask)
export const NOT_RECORDED = O.NOT_RECORDED

/* AFTER A REFRESH, OR IN ANOTHER TAB: an answer that was being sent when its
   page went away is asked about (a read), never sent again by itself. */
if (typeof window !== 'undefined') {
  void O.resume(box, net).then(() => reloadAll())
  window.addEventListener('storage', (ev) => { if (ev.key === O.STORE_KEY) box.refresh() })
}

/** What a send came to, for the form: nothing here is thrown for an
 *  ambiguous ending, because the owner's words are kept and shown with it. */
export interface SendResult { sent: string[]; refused: { ask: string; why: string } | null; unknown: string[] }

/** Post each chosen question's reply, one after another, each under its own
 *  operation key and kept before it leaves. Stops at the first that is
 *  refused or whose outcome is unknown; the rest stay chosen. */
export async function send(group: Group, picks: { ask: Ask; pick: Pick; text: string }[], me: string | null, continueWith?: string | null): Promise<SendResult> {
  const conv = group.conversation
  const out: SendResult = { sent: [], refused: null, unknown: [] }
  /* ONE ANSWER, HOWEVER MANY COPIES OR TABS. A question with an answer
     already sent -- on its way, recorded and not yet shown by the record, or
     of unknown outcome -- is not answered again from here
     (opr-6848904b24ec). */
  box.refresh()
  const now = picks.filter((p) => !box.get(p.ask.id))
  for (const { ask, pick, text } of now) {
    let body
    try {
      body = replyFor({ ask, pick, text, me, post: group.post, continueWith })
    } catch (e) {
      throw Object.assign(new Error(String((e as Error).message)), { ask: ask.id })
    }
    const op = O.newOp(ask.id)
    const label = pick.kind === 'option' ? (ask.options ?? [])[pick.option]?.label ?? null : null
    const kept: Sent = {
      ask: ask.id, op, conversation: conv ?? '', author: me, body: { ...body, op }, pick, text, label,
      continued: body.action === 'ask-participant', phase: 'sending', at: Date.now(),
      turn: null, number: null, dispatched: null, why: null, kept: true,
    }
    const got = await O.deliver(box, net, kept)
    if (got.kind === 'recorded') { out.sent.push(ask.id); continue }
    if (got.kind === 'refused') { out.refused = { ask: ask.id, why: got.why }; break }
    out.unknown.push(ask.id)
    /* NOT KNOWN IS ASKED ABOUT AT ONCE, by a read: when only the answer was
       lost, this finds the post and the form says Recorded; when the server
       cannot be reached either, it stays not confirmed, with the words. */
    void O.ask(box, net, ask.id).then((got) => { if (got === 'recorded') void reloadAll() })
    break
  }
  void reloadAll()
  return out
}

/** Ask the server what a kept answer came to (a read). */
export async function checkSent(ask: string): Promise<'recorded' | 'absent' | null> {
  const got = await O.ask(box, net, ask)
  if (got === 'recorded') void reloadAll()
  return got
}

/** Send a kept answer of unknown outcome again: the SAME request under the
 *  SAME key, so if the first did land this is answered with that post and
 *  nothing is written twice. */
export async function resend(ask: string): Promise<O.Outcome | null> {
  const kept = box.get(ask)
  if (!kept || kept.phase !== 'unknown') return null
  const got = await O.deliver(box, net, kept)
  void reloadAll()
  return got
}

/** Give a kept answer that was NOT recorded back to the form as a draft:
 *  what was chosen and typed, to change or send as a new answer. */
export function takeBack(ask: string): { pick: Pick; text: string } | null {
  const kept = box.get(ask)
  if (!kept || kept.phase !== 'unknown') return null
  box.drop(ask)
  return { pick: kept.pick as Pick, text: kept.text }
}

/** Whether a question's choices carry what happens to findings: such a
 *  decision is made by a choice, and words alone leave it open. */
export const decidesFindings = (e: Ask): boolean => (e.options ?? []).some((o) => !!o.selections || !!o.per_finding)
