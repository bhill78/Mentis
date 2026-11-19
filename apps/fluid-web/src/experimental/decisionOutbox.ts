/* WHAT BECAME OF AN ANSWER THAT WAS SENT, KEPT WHERE A REFRESH CANNOT LOSE IT
 * (Needs You reliability, 2026-11-19).
 *
 * The decision form used to hold "an answer on its way" in memory only. A
 * slow or lost acknowledgment left the form saying "Sent" with nothing behind
 * it, and a refresh said "Nothing sent yet" about an answer the record held.
 *
 * EVERY SUBMISSION HAS AN IDENTITY. Pressing Decide makes an operation key
 * (`op`) and keeps the whole request under its question BEFORE it is sent, in
 * the browser's storage. The server records a post once per (author, op)
 * however often it arrives (`mentis.conversation.posting.post`), so sending
 * the kept request again can never make a second post, a second decision or
 * a second piece of work.
 *
 * FOUR STATES, EACH MEANING ONE THING:
 *
 *   sending    the request is out; nothing is known yet
 *   recorded   THE SERVER said it wrote the post (its id and number). Only
 *              this, or the record read showing the reply, is "recorded"
 *   unknown    the request ended without an answer (connection lost, page
 *              refreshed, server error). It may or may not have landed. The
 *              server is ASKED (`GET /api/operations`, a read); it is never
 *              assumed either way and never resent without being told to
 *   refused    the server answered that it wrote nothing, and why
 *
 * WHETHER THE ANSWER CLOSED ITS QUESTION, AND WHAT IT STARTED, ARE SEPARATE
 * and are read from the record (`decisions.ts`), never from this.
 *
 * PURE: storage, the clock and the network are handed in, so every path here
 * is tested without a browser (tests/fluid_decision_outbox_unit.mjs).
 * ------------------------------------------------------------------------ */

export type Phase = 'sending' | 'recorded' | 'unknown'

/** One answer that was sent, by the question it answers. */
export interface Sent {
  ask: string
  op: string
  conversation: string
  author: string | null
  /** exactly what was posted, `op` included: sending it again is the same post */
  body: Record<string, unknown>
  /** what the owner chose and typed, so it can be put back in the form */
  pick: unknown
  text: string
  label: string | null
  continued: boolean
  phase: Phase
  at: number
  turn: string | null
  number: number | null
  /** how many runs the post started, as the server said (null: it did not say) */
  dispatched: number | null
  /** unknown: what went wrong with the request */
  why: string | null
  /** false when the browser would not keep it: it will not survive a refresh */
  kept: boolean
}

export interface StorageLike {
  getItem(key: string): string | null
  setItem(key: string, value: string): void
}

export const STORE_KEY = 'mentis.decisions.sent.v1'

/** A new operation key for one press of Decide on one question. */
export function newOp(ask: string, random: () => string = defaultRandom): string {
  return `decision:${ask}:${random()}`
}
function defaultRandom(): string {
  const c = (globalThis as { crypto?: { randomUUID?: () => string } }).crypto
  return c?.randomUUID ? c.randomUUID() : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`
}

/** What a request came to. */
export type Outcome =
  | { kind: 'recorded'; turn: string | null; number: number | null; dispatched: number | null }
  | { kind: 'refused'; why: string }
  | { kind: 'unknown'; why: string }

/** Read an answer to the post. ONLY the server's own words decide:
 *  a post id is recorded; an `error` it stated is a refusal (it wrote
 *  nothing); anything else -- no answer, an answer that is not the server's
 *  JSON, a server failure -- is unknown, because the write may have happened. */
export function outcomeOf(status: number, body: unknown): Outcome {
  const got = body && typeof body === 'object' ? (body as Record<string, unknown>) : null
  if (got && typeof got.turn === 'string' && got.turn && !got.error) {
    return {
      kind: 'recorded', turn: got.turn,
      number: typeof got.number === 'number' ? got.number : null,
      dispatched: typeof got.dispatched === 'number' ? got.dispatched : null,
    }
  }
  if (got && got.error && status < 500) return { kind: 'refused', why: String(got.error) }
  if (status >= 200 && status < 300) return { kind: 'unknown', why: 'the server answered without saying what it recorded' }
  return { kind: 'unknown', why: `the server answered ${status} without saying whether it recorded the answer` }
}

export interface Outbox {
  all(): Sent[]
  get(ask: string): Sent | undefined
  /** keep (or replace) what was sent for a question; false: only in memory */
  put(s: Sent): boolean
  drop(ask: string): void
  subscribe(f: () => void): () => void
  /** re-read what another tab kept */
  refresh(): void
}

/** The kept answers, in `storage` when it works and in memory when it does
 *  not (private browsing, a full disk): a failing storage never stops an
 *  answer being sent, it only means that answer will not survive a refresh,
 *  and `kept: false` says so. */
export function createOutbox(storage: StorageLike | null): Outbox {
  let held = new Map<string, Sent>()
  const told = new Set<() => void>()
  const readAll = () => {
    if (!storage) return
    try {
      const raw = storage.getItem(STORE_KEY)
      const doc = raw ? (JSON.parse(raw) as Record<string, Sent>) : {}
      const next = new Map<string, Sent>()
      for (const [ask, s] of Object.entries(doc)) if (s && typeof s === 'object' && s.op && s.ask === ask) next.set(ask, s)
      // what this tab holds only in memory is still held
      for (const [ask, s] of held) if (!s.kept && !next.has(ask)) next.set(ask, s)
      held = next
    } catch { /* unreadable: keep what is held in memory */ }
  }
  const writeAll = (): boolean => {
    if (!storage) return false
    try {
      storage.setItem(STORE_KEY, JSON.stringify(Object.fromEntries(held)))
      return true
    } catch {
      return false
    }
  }
  readAll()
  const tell = () => told.forEach((f) => f())
  return {
    all: () => [...held.values()],
    get: (ask) => held.get(ask),
    put(s) {
      held.set(s.ask, { ...s, kept: true })
      const ok = writeAll()
      if (!ok) held.set(s.ask, { ...s, kept: false })
      tell()
      return ok
    },
    drop(ask) {
      if (!held.has(ask)) return
      held.delete(ask)
      writeAll()
      tell()
    },
    subscribe(f) { told.add(f); return () => { told.delete(f) } },
    refresh() { readAll(); tell() },
  }
}

/** Said of a kept answer the server was asked about and does not hold. */
export const NOT_RECORDED = 'the server holds no record of it: it was not recorded'

export interface Net {
  /** POST the kept body; resolves with the status and parsed JSON (or null) */
  post(conversation: string, body: Record<string, unknown>): Promise<{ status: number; body: unknown }>
  /** GET what the keyed write came to: a READ, it writes nothing */
  lookup(op: string, author: string): Promise<{ recorded: boolean; result?: Record<string, unknown> } | null>
}

/** Send one kept answer and say what it came to. It is kept as `sending`
 *  BEFORE the request leaves, and what is kept afterwards is the outcome:
 *  recorded, or unknown. A refusal keeps nothing (nothing was written) and is
 *  returned for the form to show beside the owner's untouched words. */
export async function deliver(box: Outbox, net: Net, s: Sent): Promise<Outcome> {
  box.put({ ...s, phase: 'sending', why: null })
  let out: Outcome
  try {
    const got = await net.post(s.conversation, s.body)
    out = outcomeOf(got.status, got.body)
  } catch (e) {
    out = { kind: 'unknown', why: `the request did not complete (${String((e as Error)?.message ?? e)})` }
  }
  const now = box.get(s.ask)
  // answered by another path while this was out (the record read, another tab)
  if (!now || now.op !== s.op) return out
  if (out.kind === 'recorded') box.put({ ...now, phase: 'recorded', turn: out.turn, number: out.number, dispatched: out.dispatched, why: null })
  else if (out.kind === 'refused') box.drop(s.ask)
  else box.put({ ...now, phase: 'unknown', why: out.why })
  return out
}

/** Ask the server what a kept answer came to, WITHOUT sending it again.
 *  recorded: it landed, and is kept as recorded. absent: the server holds no
 *  such write, so it never landed (it stays kept, as unknown, with the
 *  owner's words; only they decide to send it again). null: could not ask. */
export async function ask(box: Outbox, net: Net, askId: string): Promise<'recorded' | 'absent' | null> {
  const s = box.get(askId)
  if (!s || !s.author) return null
  let got
  try {
    got = await net.lookup(s.op, s.author)
  } catch {
    return null
  }
  if (!got) return null
  const now = box.get(askId)
  if (!now || now.op !== s.op) return null
  if (got.recorded) {
    const r = got.result ?? {}
    box.put({
      ...now, phase: 'recorded', why: null,
      turn: typeof r.turn === 'string' ? r.turn : now.turn,
      number: typeof r.number === 'number' ? r.number : now.number,
      dispatched: typeof r.dispatched === 'number' ? r.dispatched : now.dispatched,
    })
    return 'recorded'
  }
  box.put({ ...now, phase: 'unknown', why: NOT_RECORDED })
  return 'absent'
}

/** After a refresh: an answer still marked `sending` belonged to a page that
 *  is gone, so its outcome is unknown until the server is asked. Asks about
 *  each. Nothing is sent again. */
export async function resume(box: Outbox, net: Net): Promise<void> {
  for (const s of box.all()) {
    if (s.phase === 'sending') box.put({ ...s, phase: 'unknown', why: 'the page was reloaded before the server answered' })
  }
  for (const s of box.all()) if (s.phase === 'unknown') await ask(box, net, s.ask)
}

/** What the record now says of a question, as far as a kept answer cares. */
export interface RecordSays {
  response_present: boolean
  answered_by?: { turn: string; number: number | null } | null
}

/** A kept answer has done its job once the RECORD shows it: the question
 *  closed, or the reply itself listed on the question. From then on the form
 *  is drawn from the record alone, on this page and after any refresh. */
export function settledBy(s: Sent, says: RecordSays): boolean {
  if (says.response_present) return true
  return s.phase === 'recorded' && !!s.turn && says.answered_by?.turn === s.turn
}
