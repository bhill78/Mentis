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
 * THREE STATES ARE KEPT, EACH MEANING ONE THING:
 *
 *   sending    the request is out; nothing is known yet
 *   recorded   THE SERVER said it wrote the post (its id and number). Only
 *              this, or the record read showing the reply, is "recorded"
 *   unknown    the request ended without an answer (connection lost, page
 *              refreshed, server error). It may or may not have landed, or
 *              may yet land. The server is ASKED (a read); "it does not hold
 *              it" is never taken as "it never will", because the request
 *              may still be on its way
 *
 * A refusal keeps nothing: the server said it wrote nothing.
 *
 * AN UNKNOWN ANSWER ENDS IN ONE OF TWO WAYS, BOTH THE SERVER'S WORD: it is
 * found recorded; or its author gives the key up (`void`, one transaction on
 * the server), after which it can never be recorded. Only then are the words
 * handed back to change, so a first answer can never surface beside a second.
 *
 * WHETHER THE ANSWER CLOSED ITS QUESTION, AND WHAT IT STARTED, ARE SEPARATE
 * and are read from the record and the server's answer, never assumed.
 *
 * PURE: storage, the clock and the network are handed in, so every path here
 * is tested without a browser (tests/fluid_decision_outbox_unit.mjs).
 * ------------------------------------------------------------------------ */

export type Phase = 'sending' | 'recorded' | 'unknown'

/** What the server said a recorded choice about findings did. */
export interface Did {
  pursued: number
  deferred: number
  dismissed: number
  /** pieces of work the server said it started for what was pursued (null: it did not say) */
  started: number | null
}

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
  /** what a choice about findings did, as the server said (null: not such a choice, or not said) */
  did: Did | null
  /** unknown: what went wrong with the request, or what the server said when asked */
  why: string | null
  /** false when the browser would not keep it: it will not survive a refresh */
  kept: boolean
  /** the Brain it was made on, where the page was bound to one (Quiet Chat); kept with it and
   *  held under it, so it is never asked about, sent again, given up or let lock a question on
   *  another Brain */
  brain?: string | null
}

export interface StorageLike {
  getItem(key: string): string | null
  setItem(key: string, value: string): void
  removeItem(key: string): void
  readonly length: number
  key(index: number): string | null
}

/** One storage entry PER QUESTION, so two tabs writing about different
 *  questions never write over each other. */
export const STORE_PREFIX = 'mentis.decisions.sent.v2:'

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
  | { kind: 'recorded'; turn: string | null; number: number | null; dispatched: number | null; did: Did | null }
  | { kind: 'refused'; why: string }
  | { kind: 'unknown'; why: string }

function didOf(got: Record<string, unknown>): Did | null {
  const r = got.reconsidered
  if (!r || typeof r !== 'object') return null
  const x = r as Record<string, unknown>
  const n = (v: unknown) => (Array.isArray(v) ? v.length : 0)
  return { pursued: n(x.pursued), deferred: n(x.deferred), dismissed: n(x.dismissed), started: Array.isArray(x.started) ? x.started.length : null }
}

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
      did: didOf(got),
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
  /** tell whoever is drawing that another tab changed what is kept */
  refresh(): void
}

/** The kept answers, in `storage` when it works and in memory when it does
 *  not (private browsing, a full disk): a failing storage never stops an
 *  answer being sent, it only means that answer will not survive a refresh,
 *  and `kept: false` says so. Each question is its own storage entry, read
 *  and written alone: what this tab does about one question cannot undo what
 *  another tab did about another. */
export function createOutbox(storage: StorageLike | null, scope: string | null = null): Outbox {
  /* ONE BRAIN'S ANSWERS, WHERE `scope` NAMES IT: each is kept under the Brain as well as the
     question, so a box for one Brain never sees another's, nor the unscoped ones a page bound
     to no Brain keeps (Fluid); and the unscoped box never sees a Brain's. */
  const keyOf = (ask: string) => STORE_PREFIX + (scope ? scope + '|' : '') + ask
  const askOfKey = (k: string): string | null => {
    if (!k.startsWith(STORE_PREFIX)) return null
    const rest = k.slice(STORE_PREFIX.length)
    if (scope) return rest.startsWith(scope + '|') ? rest.slice(scope.length + 1) : null
    return rest.includes('|') ? null : rest
  }
  /** what this tab holds that storage would not take */
  const loose = new Map<string, Sent>()
  const told = new Set<() => void>()
  const tell = () => told.forEach((f) => f())
  const parse = (ask: string, raw: string | null): Sent | undefined => {
    if (!raw) return undefined
    try {
      const s = JSON.parse(raw) as Sent
      return s && typeof s === 'object' && s.op && s.ask === ask ? s : undefined
    } catch {
      return undefined
    }
  }
  const stored = (): Sent[] => {
    const out: Sent[] = []
    if (!storage) return out
    try {
      for (let i = 0; i < storage.length; i++) {
        const k = storage.key(i)
        const ask = k ? askOfKey(k) : null
        if (!k || ask === null) continue
        const s = parse(ask, storage.getItem(k))
        if (s) out.push(s)
      }
    } catch { /* unreadable: only what this tab holds */ }
    return out
  }
  const get = (ask: string): Sent | undefined => {
    if (storage) {
      try {
        const s = parse(ask, storage.getItem(keyOf(ask)))
        if (s) return s
      } catch { /* fall through to what this tab holds */ }
    }
    return loose.get(ask)
  }
  return {
    all: () => {
      const seen = new Map(stored().map((s) => [s.ask, s]))
      for (const [ask, s] of loose) if (!seen.has(ask)) seen.set(ask, s)
      return [...seen.values()]
    },
    get,
    put(s) {
      let ok = false
      if (storage) {
        try {
          storage.setItem(keyOf(s.ask), JSON.stringify({ ...s, ...(scope ? { brain: scope } : {}), kept: true }))
          ok = true
        } catch { ok = false }
      }
      if (ok) loose.delete(s.ask)
      else loose.set(s.ask, { ...s, ...(scope ? { brain: scope } : {}), kept: false })
      tell()
      return ok
    },
    drop(ask) {
      loose.delete(ask)
      if (storage) {
        try { storage.removeItem(keyOf(ask)) } catch { /* nothing to remove */ }
      }
      tell()
    },
    subscribe(f) { told.add(f); return () => { told.delete(f) } },
    refresh() { tell() },
  }
}

export interface Net {
  /** POST the kept body; resolves with the status and parsed JSON (or null) */
  post(conversation: string, body: Record<string, unknown>): Promise<{ status: number; body: unknown }>
  /** GET what the keyed write came to: a READ, it writes nothing */
  lookup(op: string, author: string): Promise<{ recorded: boolean; voided?: boolean; result?: Record<string, unknown> } | null>
  /** POST: give the key up for good, or learn the write landed (one transaction on the server) */
  void(op: string, author: string): Promise<{ recorded: boolean; voided: boolean; result?: Record<string, unknown> } | null>
}

/** KEPT BY A PAGE FROM BEFORE ANSWERS NAMED THEIR BRAIN: it has no `brain` at all (a page
 *  bound to none keeps `brain: null`). Which Brain it was sent to is not known, so it is never
 *  sent again or withdrawn from any page -- either could act on another Brain. Asking about it
 *  is a read, and stays allowed. */
export const isLegacy = (s: Sent): boolean => !Object.prototype.hasOwnProperty.call(s, 'brain')
export const LEGACY = 'This answer was sent before Mentis named the Brain on each answer, so it is not known which Brain it went to. It is never sent again or withdrawn from here. Check asks this Brain whether it holds it; if it does not, answer again.'

/** Said of a kept answer whose key its author gave up: the server will never record it. */
export const WITHDRAWN = 'withdrawn before it was recorded: the server will not record it'
/** Said when the server was asked and does not hold it. NOT final: it may still arrive. */
export const NOT_HELD_YET = 'the server does not hold it. It may never have arrived, or it may still be on its way'

const recordedFrom = (now: Sent, r: Record<string, unknown>): Sent => ({
  ...now, phase: 'recorded', why: null,
  turn: typeof r.turn === 'string' ? r.turn : now.turn,
  number: typeof r.number === 'number' ? r.number : now.number,
  dispatched: typeof r.dispatched === 'number' ? r.dispatched : now.dispatched,
  did: didOf(r) ?? now.did,
})

/** Send one kept answer and say what it came to. It is kept as `sending`
 *  BEFORE the request leaves, and what is kept afterwards is the outcome:
 *  recorded, or unknown. A refusal keeps nothing (nothing was written) and is
 *  returned for the form to show beside the owner's untouched words. */
export async function deliver(box: Outbox, net: Net, s: Sent): Promise<Outcome> {
  if (isLegacy(s)) return { kind: 'unknown', why: LEGACY }               // never sent again
  box.put({ ...s, phase: 'sending', why: null })
  let out: Outcome
  try {
    const got = await net.post(s.conversation, s.body)
    out = outcomeOf(got.status, got.body)
  } catch (e) {
    out = { kind: 'unknown', why: `the request did not complete (${String((e as Error)?.message ?? e)})` }
  }
  const now = box.get(s.ask)
  // settled or replaced by another path while this was out (the record read, another tab)
  if (!now || now.op !== s.op) return out
  if (out.kind === 'recorded') box.put({ ...now, phase: 'recorded', turn: out.turn, number: out.number, dispatched: out.dispatched, did: out.did, why: null })
  else if (out.kind === 'refused') box.drop(s.ask)
  else if (now.phase !== 'recorded') box.put({ ...now, phase: 'unknown', why: out.why })
  return out
}

/** Ask the server what a kept answer came to, WITHOUT sending it again.
 *  'recorded': it landed, and is kept as recorded. 'absent': the server does
 *  not hold it NOW, which settles nothing (it stays unknown, with the owner's
 *  words). 'voided': its author gave the key up earlier. null: could not ask. */
export async function ask(box: Outbox, net: Net, askId: string): Promise<'recorded' | 'absent' | 'voided' | null> {
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
    box.put(recordedFrom(now, got.result ?? {}))
    return 'recorded'
  }
  if (got.voided) {
    box.put({ ...now, phase: 'unknown', why: WITHDRAWN })
    return 'voided'
  }
  if (now.phase !== 'recorded') box.put({ ...now, phase: 'unknown', why: NOT_HELD_YET })
  return 'absent'
}

/** Give a kept answer up for good, on the server's word. 'voided': it was
 *  never recorded and now never will be; its words are returned and nothing
 *  is kept, so a different answer may be sent. 'recorded': it had landed
 *  after all; it is kept as recorded and nothing is handed back. null: the
 *  server could not be asked, so nothing changes. */
export async function giveUp(box: Outbox, net: Net, askId: string): Promise<{ outcome: 'voided'; pick: unknown; text: string } | { outcome: 'recorded' } | null> {
  const s = box.get(askId)
  if (!s || !s.author || s.phase === 'recorded' || isLegacy(s)) return null   // never withdrawn from here
  let got
  try {
    got = await net.void(s.op, s.author)
  } catch {
    return null
  }
  if (!got) return null
  const now = box.get(askId)
  if (!now || now.op !== s.op) return null
  if (got.recorded) {
    box.put(recordedFrom(now, got.result ?? {}))
    return { outcome: 'recorded' }
  }
  if (!got.voided) return null
  box.drop(askId)
  return { outcome: 'voided', pick: now.pick, text: now.text }
}

/** After a refresh: an answer still marked `sending` belonged to a page that
 *  is gone, so its outcome is unknown until the server is asked. Asks about
 *  each. Nothing is sent again. */
export async function resume(box: Outbox, net: Net, now: number = Date.now()): Promise<void> {
  for (const s of box.all()) {
    /* What the server said it recorded is in the record. A kept copy the
       record read never came back for (its question was deleted with its
       conversation) is not held for ever. An answer of UNKNOWN outcome is
       never dropped by age: only its author gives that up. */
    if (s.phase === 'recorded' && now - s.at > KEEP_RECORDED_MS) { box.drop(s.ask); continue }
    if (s.phase === 'sending') box.put({ ...s, phase: 'unknown', why: 'the page was reloaded before the server answered' })
  }
  for (const s of box.all()) if (s.phase === 'unknown') await ask(box, net, s.ask)
}

/** How long a kept answer the server said it recorded is held when no record
 *  read ever settles it. */
export const KEEP_RECORDED_MS = 7 * 24 * 3600 * 1000

/** What the record now says of a question, as far as a kept answer cares. */
export interface RecordSays {
  response_present: boolean
  answered_by?: { turn: string; number: number | null } | null
}

/** A kept answer has done its job once THE SERVER HAS SAID IT IS RECORDED and
 *  the record read shows where things stand: the question closed, or this
 *  very reply listed on it. From then on the form is drawn from the record
 *  alone, on this page and after any refresh.
 *
 *  An answer of UNKNOWN outcome is never settled by the record alone: that
 *  the question was closed (perhaps by a different answer, from another tab)
 *  says nothing of whether this one landed, and its words are not thrown
 *  away on a guess. It ends by being found recorded, or by being given up. */
export function settledBy(s: Sent, says: RecordSays): boolean {
  if (s.phase !== 'recorded') return false
  return says.response_present || (!!s.turn && says.answered_by?.turn === s.turn)
}
