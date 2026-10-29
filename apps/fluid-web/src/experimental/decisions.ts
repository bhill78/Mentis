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
 * WHAT IS ON ITS WAY is held by question (`landings`), so every copy of a
 * form -- the post, its thread, full screen, a zone -- locks while it is
 * sent and says what landed. Recorded is read from the record afterwards,
 * never from the request having been made.
 * ------------------------------------------------------------------------ */
import { useEffect, useSyncExternalStore } from 'react'
import { fluidFetch } from '../fluid/http'

const API = '/fluid/api/decisions'
const HEADERS = { 'X-Mentis-Client': '1', 'Content-Type': 'application/json' }
/** How often a form with an open question on screen rereads. */
export const REREAD_MS = 5000

export interface Option {
  label: string
  consequence?: string
  per_finding?: boolean
  findings?: { ref: string; label: string }[]
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
    })
    .catch((e) => { entries.set(key, { ...(entries.get(key) ?? { at: 0 }), error: String((e as Error)?.message ?? e) }) })
    .finally(() => { inflight.delete(key); notify(key) })
  inflight.set(key, p)
  return p
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

/* ---------------------------------------------------------------- landings */

/** An answer on its way to the record, by question. */
export interface Landing {
  pick: Pick
  label: string | null
  phase: 'sending' | 'sent'
  turn: string | null
  number: number | null
  continued: boolean
}
const landings = new Map<string, Landing>()
const LANDINGS = 'landings'
export function land(id: string, l: Landing | null) {
  if (l) landings.set(id, l)
  else landings.delete(id)
  notify(LANDINGS)
}
let snapshot = new Map(landings)
export function useLandings(): Map<string, Landing> {
  return useSyncExternalStore(
    (f) => subscribe(LANDINGS, () => { snapshot = new Map(landings); f() }),
    () => snapshot,
    () => snapshot,
  )
}

/** Post each chosen question's reply, one after another. Stops at the first
 *  that is refused, which says why at its question; the rest stay chosen. */
export async function send(group: Group, picks: { ask: Ask; pick: Pick; text: string }[], me: string | null, continueWith?: string | null): Promise<boolean> {
  const conv = group.conversation
  /* ONE ANSWER, HOWEVER MANY COPIES. A question already on its way from
     another copy of this form is not sent again (opr-6848904b24ec). */
  const now = picks.filter((p) => !landings.has(p.ask.id))
  if (!now.length) return false
  for (const { ask, pick, text } of now) {
    let body
    try {
      body = replyFor({ ask, pick, text, me, post: group.post, continueWith })
    } catch (e) {
      throw Object.assign(new Error(String((e as Error).message)), { ask: ask.id })
    }
    const label = pick.kind === 'option' ? (ask.options ?? [])[pick.option]?.label ?? null : null
    const sending: Landing = { pick, label, phase: 'sending', turn: null, number: null, continued: body.action === 'ask-participant' }
    land(ask.id, sending)
    try {
      const res = await fluidFetch(`/api/conversations/${encodeURIComponent(conv ?? '')}/turns`, { method: 'POST', headers: HEADERS, body: JSON.stringify(body) })
      const got = await res.json().catch(() => null)
      if (!res.ok || !got || got.error) throw new Error(got?.error ?? res.statusText)
      land(ask.id, { ...sending, phase: 'sent', turn: got.turn ?? null, number: got.number ?? null })
    } catch (e) {
      land(ask.id, null)
      throw Object.assign(new Error(String((e as Error).message ?? e)), { ask: ask.id })
    }
  }
  await reloadAll()
  return true
}
