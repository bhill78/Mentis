import { CLIENT_HEADERS } from '../../api'
import { BRAIN_HEADER, confirmBrain, page, refusedAsOtherBrain } from '../../brainBinding'
import { fluidFetch } from '../../fluid/http'
import { matchesBinding } from './managementApi'
import type { MagnetContext, MagnetResource, SearchEntry, SearchSource } from './contract'
import { remember, setOpen } from './places'

/** THE GATE IS OPEN, so nothing here mirrors a shut one any more.
 *
 *  `PERSPECTIVE_ANSWERS_ENABLED = false`, `PERSPECTIVE_BLOCK_REASON`,
 *  `FUTURE_CONCEPT` and `GROUNDED_NOT_YET` were this file's statement of the
 *  server's `grounded-answers-blocked` refusal, and of the mockups' "future
 *  concept" mark on a picture of answering that did not work. The refusal was
 *  there because the owner's correction `ent-d85254fe5e1b` was not enforced;
 *  Part A enforced it (`mentis/magnet/scope.py`, applied at the one door), the
 *  server's `GROUNDED_ANSWERS_ENABLED` is `True`, and this part makes the
 *  pictures true. They are deleted rather than flipped: there is no longer
 *  anything for them to say. The refusal keeps its code server-side for a build
 *  that shuts the gate again, and this client reads `grounded_answers` from the
 *  response instead of carrying a constant of its own. */
export const PERSPECTIVE_DISCLOSURE = 'This Magnet’s answers are grounded in its own collection: a run carrying one of its exchanges reads that Magnet’s recorded collection batches, the posts of its own Conversation and the references the owner selected, and every other Brain record or acquired source is refused at the door. A Perspective answer and an evolving summary are grounded in the collected rows and nothing else; no authorization widens them.'

/** HOW AN ANSWER SAYS WHAT IT REACHED (Part A's published contract,
 *  `docs/magnets/part-b-perspectives-api.md` §"The provenance field Part F and
 *  the client render"). The field names are A's exactly, and this part invents
 *  none of its own: `explored_outside` is THE field to render.
 *
 *  Grounded-in-the-collection and explored-outside must never be mistaken for
 *  each other, so they are three distinct statements and not one scale:
 *  grounded (nothing outside was opened), allowed-but-did-not (the owner opened
 *  something and the answer did not reach it), and explored-outside (it did,
 *  and what it reached is named). For a synthesis -- a Perspective answer or
 *  the evolving summary -- all of it is empty and false structurally. */
export interface AnswerProvenance {
  grounded_in: 'collection'
  outside_authorized: ({ kind: 'runtime-web-search' } | { kind: 'collection'; collection: string })[]
  outside_reads: { what: string; collection: string; ref?: string }[]
  explored_outside: boolean
}
export const GROUNDED_IN_COLLECTION = 'Grounded in this collection'
export const EXPLORED_OUTSIDE = 'Explored outside this collection'
export const ALLOWED_OUTSIDE_UNUSED = 'Allowed to look outside; did not'
export const GROUNDED_WHY = 'Written from this Magnet’s collected records and nothing else. No authorization widens a Perspective answer or an evolving summary.'
export const EXPLORED_WHY = 'This answer reached a source outside this Magnet’s collection, which the owner explicitly opened for that one exchange. It is not grounded in the collection alone.'

/** The provenance an answer event carries, or null when it carries none — and
 *  null is never read as "grounded": an answer that cannot state what it
 *  reached says that instead (`UNSTATED_PROVENANCE`). */
export function provenanceOf(event?: InquiryEvent | null): AnswerProvenance | null {
  const p = event?.data?.provenance
  if (!p || typeof p !== 'object' || p.grounded_in !== 'collection' || typeof p.explored_outside !== 'boolean') return null
  return { grounded_in: 'collection', explored_outside: p.explored_outside,
    outside_authorized: Array.isArray(p.outside_authorized) ? p.outside_authorized : [],
    outside_reads: Array.isArray(p.outside_reads) ? p.outside_reads : [] }
}
export const UNSTATED_PROVENANCE = 'This answer does not record what it was allowed to reach, so it is not shown as grounded in this collection.'
export interface Grounding { label: string; detail: string; outside: boolean; stated: boolean; reached: string[] }
/** What to show beside an answer's citations. One of three statements, never a
 *  blend of them, and never silence. */
export function grounding(p: AnswerProvenance | null): Grounding {
  if (!p) return { label: 'Grounding not recorded', detail: UNSTATED_PROVENANCE, outside: false, stated: false, reached: [] }
  if (p.explored_outside) return { label: EXPLORED_OUTSIDE, detail: EXPLORED_WHY, outside: true, stated: true,
    reached: p.outside_reads.map((r) => [r.what, r.collection].filter(Boolean).join(' · ')) }
  if (p.outside_authorized.length) return { label: ALLOWED_OUTSIDE_UNUSED, outside: false, stated: true,
    detail: `${GROUNDED_WHY} The owner opened ${p.outside_authorized.length} outside ${p.outside_authorized.length === 1 ? 'source' : 'sources'} for an exchange; this answer reached none of them.`,
    reached: [] }
  return { label: GROUNDED_IN_COLLECTION, detail: GROUNDED_WHY, outside: false, stated: true, reached: [] }
}

/** THE STANDING PERSPECTIVE: one question every Magnet keeps, whose answer is
 *  the evolving summary. It is created with its deterministic key, so it is
 *  created exactly once however often this is called. */
export const STANDING_QUESTION = 'What is the state of what this Magnet has gathered?'
export const STANDING_NAME = 'What this Magnet has gathered'
export const standingOp = (magnet: string) => `magnet-standing:${magnet}`
export const standingAnswerOp = (magnet: string, batch: string) => `magnet-standing-answer:${magnet}:${batch}`
/** What the answer says about itself, so no reader has to guess who wrote it.
 *  The server records the same sentence on every answer package it writes
 *  (`perspectives_work.WRITTEN_BY_MENTIS`); this is the fallback for an answer
 *  recorded before it carried one. */
export const WRITTEN_BY_MENTIS = 'Written by Mentis from this Magnet’s collected records alone.'
/** Said where the collected items are listed beside a question, so the list is
 *  never read as the answer's own chosen support. */
export const SUPPORTING_WHY = 'These are the records this Magnet has collected. The answer standing now names the ones it was written from; the rest are here to read yourself.'
export const NOTHING_RECORDED_YET = 'Nothing is recorded against this question yet. Ask it of the collection, or discuss it to keep what is said with the question.'
export const ANSWER_FROM_COLLECTION = 'Answer from this collection'
export const NOTHING_NEW_CODE = 'nothing-new'

/** WHAT THE RECORD HOLDS AS THE CURRENT UNDERSTANDING OF A QUESTION.
 *
 *  Answers somebody recorded against it, and challenges recorded to it, newest
 *  first. It derives nothing, concludes nothing and reads nothing live: these
 *  are the durable events the history already returned. */
export interface RecordedUnderstanding { answers: InquiryEvent[]; challenges: InquiryEvent[] }
export function recordedUnderstanding(events: InquiryEvent[]): RecordedUnderstanding {
  const newest = [...events].reverse()
  return {
    answers: newest.filter((e) => e.event === 'answer' || e.event === 'answered' || typeof e.data?.answer?.ref === 'string'),
    challenges: newest.filter((e) => e.event === 'challenge' || e.event === 'challenged'),
  }
}

/** A PERSISTENT QUESTION, AND AN ANSWER THAT EVOLVES (owner ent-901ef1a816bb).
 *
 *  A Perspective is a question that is KEPT: it is asked once and stays, and
 *  what is understood of it changes as the Magnet collects more. So the answer
 *  that stands now is told apart from the answers that stood before it --
 *  `current` is the newest recorded answer, `superseded` the ones recorded
 *  earlier, newest first. A newer answer never removes an earlier one: each is
 *  a durable event that stays readable at its own recorded version, which is
 *  what preserving answer history means here.
 *
 *  Nothing in this derives, merges or summarises an answer. It splits what the
 *  history already returned, in the order the record holds. */
export interface AnswerHistory { current: InquiryEvent | null; superseded: InquiryEvent[] }
export function answerHistory(events: InquiryEvent[]): AnswerHistory {
  const [current, ...superseded] = recordedUnderstanding(events).answers
  return { current: current ?? null, superseded }
}

/** The words an answer event stands for, exactly as recorded. */
export const answerText = (e?: InquiryEvent | null): string =>
  typeof e?.data?.text === 'string' ? e.data.text : ''

/** An answer's own statements, in the order it recorded them. An answer is
 *  written as one statement per line, each naming the records it was written
 *  from, so a reader sees statements rather than a paragraph. */
export const statements = (words: string): string[] =>
  String(words).split(/\r?\n/).map((l) => l.trim()).filter(Boolean)

/** WHAT CHANGED, between the answer standing now and the one it follows.
 *
 *  A diff of the recorded answers, not a second comparison of collections:
 *  the evolving summary is re-answered when a collection brings rows the last
 *  answer did not read, so the difference between those two answers IS what
 *  changed. Statement by statement, in the order the newer answer holds them,
 *  and nothing is inferred: a line is either in both answers or in one. */
export interface AnswerChange { added: string[]; gone: string[]; same: number }
export function answerDiff(current?: InquiryEvent | null, previous?: InquiryEvent | null): AnswerChange | null {
  if (!current) return null
  const lines = (e?: InquiryEvent | null) => answerText(e).split('\n').map((l) => l.trim()).filter(Boolean)
  const now = lines(current)
  if (!previous) return { added: now, gone: [], same: 0 }
  const before = lines(previous)
  const was = new Set(before), is = new Set(now)
  return { added: now.filter((l) => !was.has(l)), gone: before.filter((l) => !is.has(l)),
    same: now.filter((l) => was.has(l)).length }
}
/** The one sentence that difference is worth. */
export function changeWords(c: AnswerChange | null): string {
  if (!c) return 'No answer is recorded for this collection yet, so nothing is claimed to have changed.'
  if (!c.added.length && !c.gone.length) return `This answer says the same as the one before it: all ${c.same} statements are unchanged.`
  const bits = [c.added.length ? `${c.added.length} new ${c.added.length === 1 ? 'statement' : 'statements'}` : '',
    c.gone.length ? `${c.gone.length} no longer said` : ''].filter(Boolean)
  return `Since the previous answer: ${bits.join(', ')}; ${c.same} unchanged.`
}

/** Said where a kept question is read, so a Perspective is never taken for a
 *  second conversation system: it is one question that stays, with what is
 *  understood of it recorded under it. */
export const QUESTION_IS_KEPT = 'This question is kept. What is understood of it can change as this Magnet collects more, and earlier answers stay readable.'
export const ANSWER_STANDS_NOW = 'Answer standing now'
export const EARLIER_ANSWERS_KEPT = 'Earlier answers are kept in the order they were recorded. A newer answer never removes one.'
/** What reading the record again found. Reading is all it is: no agent is
 *  started, nothing is recorded, and no answer is formed here. */
export const CHECKED_SAME = 'Read again: no newer answer is recorded against this question.'
export const CHECKED_NEW = 'Read again: a newer answer is recorded. The one it follows is kept below.'
export const COLLECTION_MOVED = 'This Magnet has collected more since this question was last read, so it was read again. No newer answer is recorded yet.'

/** The past questions, narrowed by what was typed in the find box. Both the
 *  name and the saved wording are searched, because the name is derived from
 *  the wording and a later revision may have moved them apart. */
export function pastQuestions(rows: Perspective[], query: string): Perspective[] {
  const want = query.trim().toLowerCase()
  if (!want) return rows
  return rows.filter((p) => `${p.name} ${p.current_question?.text ?? ''}`.toLowerCase().includes(want))
}

/** What to say under a past question's name: counted from the row, never guessed. */
export function questionSubtitle(p: Perspective, selected: string | null): string {
  return [
    p.perspective === selected ? 'Current discussion' : null,
    p.retired ? 'Retired' : null,
    `${p.events} recorded ${p.events === 1 ? 'change' : 'changes'}`,
  ].filter(Boolean).join(' · ')
}
export interface Perspective { perspective: string; name: string; retired: boolean; question: Artifact | null; current_question?: { text: string; revision: string } | null; events: number }
export interface Artifact { ref: string; digest: string; size: number; media_type: string }
export interface InquiryEvent { seq: number; post: string; event: string; perspective: string | null; snapshot: Artifact; data: Record<string, any> }
export interface PreparedInquiry { intent: string; perspective: string; brain: string; question: Artifact; manifest: Artifact; records: Artifact; artifacts: Artifact[]; parts: { type: 'file'; ref: string; media_type: string; alt: string }[]; reach: 'work'; request_op: string; text: string; closure: { count: number; bytes: number }; disclosure: string }
export interface OrdinaryContext { perspective: string; name: string; question: string; revision: string }
export interface PendingAction { brain: string; magnet: string; kind: string; target: string | null; tail: string; data: Record<string, unknown>; op: string; result?: any; selectOp: string }
export interface InquirySnapshot { pending?: PendingAction; viewedDetail?: Perspective; selectedDetail?: Perspective; rows: Perspective[]; selected: string | null; viewed?: string | null; loading: boolean; error?: string; events: InquiryEvent[]; next: string | null; listNext: string | null; historyComplete: boolean; priors: string[]; continuation: boolean; selections: Record<string, 'supporting' | 'contradicting' | 'context'>; declared: string[]; active?: PreparedInquiry; receipt?: any; answer?: any
  /** THE ACTUAL AGENT REQUEST this Perspective's frozen ask is bound to
   *  (`bind`'s own `request`, the expectation id) -- what the recorded
   *  agent-reply boundary is read against. Set once by `afterRecorded`, after
   *  the actual send; cleared whenever a fresh question is frozen (`prepare`)
   *  or the active lens changes, so a stale reply is never read against a
   *  question it does not belong to. */
  bound?: { perspective: string; request: string } | null
  /** THE ONE REPLY CURRENTLY BEING FROZEN, by its Turn id -- set for the
   *  duration of `finalizeReply`'s own write, so a second observation of the
   *  same still-in-flight reply (the pulse reads again before the first write
   *  answers) does not send a second request. */
  finalizing?: string | null
  /** This Magnet's standing Perspective, as the listing read reports it. */
  standing?: string | null
  /** The standing Perspective's recorded answers: the evolving summary and
   *  the ones it superseded. Read by the Summary, which shows the current one
   *  as its lead and the difference from the previous one as what changed. */
  summary?: StandingSummary | null
}
export interface StandingSummary { perspective: string; current: InquiryEvent | null; superseded: InquiryEvent[]; batch: string | null }
const stores = new WeakMap<MagnetResource, PerspectiveStore>()
const uuid = (kind: string) => `perspective-${kind}-${crypto.randomUUID()}`

/** THE EXACT SAVED QUESTION VERSION A PERSPECTIVE CHIP STANDS FOR.
 *
 *  `version` is the saved question's own artifact reference and `digest` is
 *  that version's recorded digest -- the two optional `MagnetContext` fields
 *  the composer reads (D's correction, adm-394af815cdce §"Interface published
 *  by this correction"). They are declared here, in this part's own file,
 *  because this part owns the view that attaches the chip and may not edit
 *  another part's: the names, types and meaning are the contract's, so the
 *  merged `MagnetContext` carries exactly this shape structurally.
 *
 *  Why a chip must carry it: an id alone says "this Perspective", not which
 *  wording of it, so a question revised after the owner attached it would be
 *  sent in place of the one they read. With the stamp on the chip, the send
 *  compares it against a fresh durable read and refuses on any difference
 *  instead of substituting. */
export interface AttachedQuestionVersion { version: string | null; digest: string }
const DIGEST_HEX = /^[0-9a-f]{64}$/

/** The version a durable Perspective row stands for, or null when the row
 *  cannot state one exactly. `detail()` has already required
 *  `current_question.revision === question.ref`, so a row that disagrees, or
 *  that carries no recorded digest, is left UNSTAMPED rather than stamped from
 *  something else: a wrong stamp would send the wrong version, where no stamp
 *  only means the composer must read the version itself before it sends. */
export function questionVersion(row?: Perspective | null): AttachedQuestionVersion | null {
  const saved = row?.question, current = row?.current_question
  if (!saved || !current || current.revision !== saved.ref || !DIGEST_HEX.test(saved.digest ?? '')) return null
  return { version: saved.ref, digest: saved.digest }
}

/** The version a chip already stands for, if it stands for one. A recorded
 *  64-hex digest is what says it does. Read through the contract's own two
 *  optional fields, which this build's `MagnetContext` may not declare yet. */
export function attachedQuestionVersion(context?: MagnetContext | null): AttachedQuestionVersion | null {
  const c = context as (MagnetContext & Partial<AttachedQuestionVersion>) | null | undefined
  if (!c || c.kind !== 'perspective' || !DIGEST_HEX.test(c.digest ?? '')) return null
  return { version: c.version ?? null, digest: c.digest! }
}

/** Say what an ALREADY ATTACHED chip stands for, from a durable read this
 *  surface has just made and is showing. It attaches nothing, re-attaches
 *  nothing and clears no suppression -- an intentional removal stays removed
 *  (owner §6) -- and a chip that already states a version is left exactly as
 *  it is, so a later revision refuses instead of being substituted. This is
 *  the other path in this part that hands a saved question to the Composer:
 *  `discussSelectedQuestion` copies the wording it just read, and the chip
 *  beside those words has to stand for that same version. */
export function stampAttachedQuestion(resource: MagnetResource, row?: Perspective | null): void {
  const attached = resource.snapshot().context
  if (!row || !attached || attached.kind !== 'perspective' || attached.ref !== row.perspective) return
  if (attachedQuestionVersion(attached)) return
  const stamp = questionVersion(row)
  if (stamp) resource.update({ context: Object.assign({ ...attached }, stamp) })
}

/** A durable lens choice is also an explicit composer-context choice. Like
 * "Discuss this evidence", selecting one may replace an attached chip and
 * clears suppression. Choosing ordinary Conversation removes only a
 * Perspective chip; removing the chip itself never changes the active lens.
 *
 * The chip is attached AT THE VERSION the owner was viewing: `row` is the
 * durable read this surface is showing, and its saved question version is
 * stamped onto the chip as it goes on, rather than left for the composer to
 * stamp from whatever is durable by the time it next looks. A chip that
 * already stands for a version of the same Perspective is never re-stamped --
 * that is what makes a later revision a refusal instead of a silent
 * substitution. */
export function showPerspectiveContext(resource: MagnetResource, perspective: string | null, name?: string | null,
                                       row?: Perspective | null): void {
  if (perspective) {
    const attached = resource.snapshot().context
    const already = attached?.ref === perspective ? attachedQuestionVersion(attached) : null
    const stamp = already ?? questionVersion(row?.perspective === perspective ? row : null)
    const context: MagnetContext = { ref: perspective, kind: 'perspective', label: name || perspective }
    resource.update({ context: stamp ? Object.assign(context, stamp) : context, contextSuppressed: false })
  } else if (resource.snapshot().context?.kind === 'perspective') {
    resource.update({ context: null, contextSuppressed: false })
  }
}

/** Question-first creation (§5-H5-5). The create route requires a name, so the
 *  client derives the one it suggests from the question itself and the owner is
 *  never asked for a second field. The approved rule: the question unchanged
 *  through 52 characters, otherwise its first 49 plus an ellipsis -- counted in
 *  characters, so an emoji is one character and is never cut in half. */
export const PERSPECTIVE_NAME_KEEP = 52
export const PERSPECTIVE_NAME_HEAD = 49
export function derivedPerspectiveName(question: string): string {
  const words = question.trim().replace(/\s+/g, ' ')
  const chars = Array.from(words)
  return chars.length <= PERSPECTIVE_NAME_KEEP ? words : chars.slice(0, PERSPECTIVE_NAME_HEAD).join('') + '…'
}

/** Every page is bounded and frozen by the server cursor, so walking one to
 *  exhaustion is bounded too -- provided a cursor that does not advance is
 *  treated as a defect and not as a loop. This is the one guard; both
 *  `completeHistory()` and `perspectiveSource.complete()` use it. */
export async function walkPages(read: (cursor?: string) => Promise<string | null>): Promise<void> {
  const seen = new Set<string>()
  let cursor = await read(undefined)
  while (cursor) {
    if (seen.has(cursor)) throw new Error('The question history did not advance. Nothing was sent.')
    seen.add(cursor)
    cursor = await read(cursor)
  }
}
export class PerspectiveStore {
  private state: InquirySnapshot = { rows: [], selected: null, loading: false, events: [], next: null, listNext: null, historyComplete: false, priors: [], continuation: false, selections: {}, declared: [] }
  private listeners = new Set<() => void>()
  private version = 0
  private brain = page.bound()
  private lensVersion = 0
  private historyVersion = 0
  constructor(readonly resource: MagnetResource) {
    try {
      const raw = globalThis.localStorage?.getItem(this.storageKey())
      if (raw && raw.length <= 300000) {
        const pending = JSON.parse(raw) as PendingAction
        if (pending.brain === this.brain && pending.magnet === resource.saved.id &&
            typeof pending.op === 'string' && typeof pending.selectOp === 'string' &&
            typeof pending.kind === 'string' && typeof pending.tail === 'string' &&
            pending.tail === (pending.kind === 'create' ? '' : pending.kind === 'selected' ? '/selected' : `/${pending.target}/${pending.kind}`) &&
            pending.data && typeof pending.data === 'object') this.state.pending = pending
      }
    } catch { /* An unreadable browser record never becomes a new write. */ }
  }
  private storageKey() { return `mentis:perspective-action:${this.resource.brainKey}:${this.brain}:${this.resource.saved.id}` }
  private keep(pending?: PendingAction) {
    // Persist before sending. A failed browser write must not discard uncertainty.
    if (globalThis.localStorage) {
      if (pending) globalThis.localStorage.setItem(this.storageKey(), JSON.stringify(pending))
      else globalThis.localStorage.removeItem(this.storageKey())
    }
    this.update({ pending })
  }
  snapshot = () => this.state
  subscribe = (fn: () => void) => { this.listeners.add(fn); return () => { this.listeners.delete(fn) } }
  update = (v: Partial<InquirySnapshot>) => {
    if ('selected' in v && v.selected !== this.state.selected) {
      this.lensVersion++
      v = { selectedDetail: undefined, active: undefined, receipt: undefined, answer: undefined, bound: undefined, finalizing: undefined, ...v }
    }
    this.state = { ...this.state, ...v }; this.listeners.forEach((f) => f())
  }
  private path = (tail = '') => `/fluid/api/magnets/${encodeURIComponent(this.resource.saved.id)}/perspectives${tail}`
  async get(tail = ''): Promise<any> {
    if (!matchesBinding(this.resource.brainKey)) throw new Error('This Perspective belongs to another Brain instance. Reload before continuing.')
    if (this.brain && page.bound() !== this.brain) throw new Error('This question was opened on a different Brain instance. Reopen it after reloading.')
    this.brain ??= page.bound()
    const expected = page.bound(), r = await fetch(this.path(tail), { headers: CLIENT_HEADERS, cache: 'no-store' }), v = await r.json().catch(() => null)
    if (!r.ok || !v || v.error) throw new Error(v?.error ?? 'Perspective records are unavailable.')
    if (page.bound() !== expected || page.moved() || v.brain !== expected) throw new Error('A late Perspective response from a different Brain was refused.')
    return v
  }
  async write(tail: string, data: Record<string, unknown>, op = uuid('write')): Promise<any> {
    if (await confirmBrain() !== true || !matchesBinding(this.resource.brainKey)) throw new Error('Confirm the Brain before changing this question.')
    if (this.brain && page.bound() !== this.brain) throw new Error('The Brain instance changed. The original intent was not sent to its replacement.')
    this.brain ??= page.bound()
    const brain = page.bound()!, r = await fluidFetch(this.path(tail), { method: 'POST', headers: { ...CLIENT_HEADERS, [BRAIN_HEADER]: brain, 'Content-Type': 'application/json' }, body: JSON.stringify({ ...data, brain, op }) }), v = await r.json().catch(() => null)
    if (refusedAsOtherBrain(r.status, v)) page.move()
    if (!r.ok || !v || v.error) throw Object.assign(new Error(v?.error ?? 'The outcome of that question action is unknown. Retry the same action and key.'), { refused: !!v?.refused, details: v })
    if (page.bound() !== brain || page.moved() || v.brain !== brain) throw new Error('A late response from another Brain was refused.')
    return v
  }
  private detail(v: any, topic: string): Perspective {
    const q = v.current_question
    if (v.magnet !== this.resource.saved.id || v.perspective !== topic || typeof v.name !== 'string' ||
        !q || typeof q.text !== 'string' || typeof q.revision !== 'string' || q.revision !== v.question?.ref)
      throw new Error('The saved current question did not match this Perspective.')
    return v
  }
  private merged(rows: Perspective[], row?: Perspective) {
    return row ? [...rows.filter((r) => r.perspective !== row.perspective), row] : rows
  }
  async read(cursor?: string) {
    const mine = ++this.version, lens = this.lensVersion; this.update({ loading: true, error: undefined })
    try {
      const v = await this.get('?' + new URLSearchParams({ limit: '100', ...(cursor ? { cursor } : {}) }))
      const selected = v.selected ?? null
      const detail = selected ? this.detail(await this.get(`/${selected}`), selected) : undefined
      if (detail && (detail as any).selected !== selected) throw new Error('The active Perspective changed during refresh.')
      if (mine !== this.version || lens !== this.lensVersion) return
      this.update({ rows: this.merged(cursor ? [...this.state.rows, ...v.perspectives] : v.perspectives, detail), selected, selectedDetail: detail, listNext: v.next ?? null,
        ...(typeof v.standing === 'string' || v.standing === null ? { standing: v.standing } : {}) })
    } catch (e) { if (mine === this.version) this.update({ error: (e as Error).message }) }
    finally { if (mine === this.version) this.update({ loading: false }) }
  }
  /** Read the durable lens and exact saved question afresh, never from history or editor state. */
  async ordinaryContext(): Promise<OrdinaryContext | null> {
    if (this.state.pending) throw new Error('Resolve the unchanged question action before discussing its saved question.')
    const lens = this.lensVersion
    const v = await this.get('?limit=1'), topic = v.selected ?? null
    const detail = topic ? this.detail(await this.get(`/${topic}`), topic) : undefined
    const check = await this.get('?limit=1')
    if (lens !== this.lensVersion || (check.selected ?? null) !== topic || detail && (detail as any).selected !== topic)
      throw new Error('The active Perspective changed while its saved question was being read. Nothing was sent.')
    if (detail) {
      const latest = this.detail(await this.get(`/${topic}`), topic!)
      if (lens !== this.lensVersion || this.state.pending || (latest as any).selected !== topic || latest.current_question?.revision !== detail.current_question?.revision)
        throw new Error('The active Perspective or saved question changed while it was being read. Nothing was sent.')
    }
    this.update({ selected: topic, selectedDetail: detail, rows: this.merged(this.state.rows, detail) })
    if (!detail) return null
    return { perspective: topic!, name: detail.name, question: detail.current_question!.text, revision: detail.current_question!.revision }
  }
  async history(cursor?: string) {
    const selected = this.state.viewed ?? this.state.selected, mine = ++this.historyVersion
    if (!selected) { this.update({ events: [], next: null, historyComplete: true }); return }
    const v = await this.get(`/${selected}/history?` + new URLSearchParams({ limit: '100', ...(cursor ? { cursor } : {}) }))
    if (mine !== this.historyVersion || (this.state.viewed ?? this.state.selected) !== selected) return
    if (v.perspective !== selected || v.magnet !== this.resource.saved.id) throw new Error('History answered for another Perspective.')
    this.update({ events: cursor ? [...this.state.events, ...v.events] : v.events, next: v.next ?? null, historyComplete: !v.next })
  }
  async select(perspective: string | null, op = uuid('select')) {
    return this.action('selected', { perspective }, null, op)
  }
  async lifecycle(kind: string, data: Record<string, unknown>, op = uuid('action')) {
    return this.action(kind, data, this.state.viewed ?? this.state.selected, op)
  }
  private async action(kind: string, data: Record<string, unknown>, target: string | null, op: string) {
    if (this.state.pending) throw new Error('An earlier question action has an unknown outcome. Retry that unchanged action first.')
    if (kind !== 'create' && kind !== 'selected' && !target) throw new Error('View a Perspective first.')
    const brain = this.brain
    if (!matchesBinding(this.resource.brainKey) || !brain || brain !== page.bound()) throw new Error('Confirm the original Brain before changing this question.')
    this.lensVersion++
    this.keep({ brain, magnet: this.resource.saved.id, kind, target,
      tail: kind === 'create' ? '' : kind === 'selected' ? '/selected' : `/${target}/${kind}`,
      data: structuredClone(data), op, selectOp: `${op}-select` })
    return this.retryPending()
  }
  async retryPending() {
    const pending = this.state.pending
    if (!pending) return
    if (pending.brain !== page.bound() || page.moved() || pending.magnet !== this.resource.saved.id) throw new Error('The original question action belongs to another Brain. It was not sent.')
    let v: any
    try {
      v = pending.result ?? await this.write(pending.tail, pending.data, pending.op)
      // Create and selection are separate keyed writes; retain the acknowledged create.
      if (pending.kind === 'create' || pending.kind === 'branch') {
        if (typeof v.perspective !== 'string') throw new Error('The saved question did not return its identity. Retry the original key.')
        this.keep({ ...pending, result: v })
        await this.write('/selected', { perspective: v.perspective }, pending.selectOp)
      }
    } catch (e) { if ((e as any).refused) this.keep(); throw e }
    this.keep()
    const chosen = pending.kind === 'selected' ? pending.data.perspective as string | null :
      pending.kind === 'create' || pending.kind === 'branch' ? v.perspective : this.state.selected
    const chosenName = chosen ? (typeof v?.name === 'string' ? v.name
      : typeof pending.data.name === 'string' ? pending.data.name
      : this.state.rows.find((row) => row.perspective === chosen)?.name) : null
    this.version++; this.historyVersion++
    this.update({ selected: chosen, viewed: pending.kind === 'selected' ? chosen : v.perspective ?? pending.target,
      viewedDetail: undefined, events: [], next: null, historyComplete: false, active: undefined, receipt: undefined, answer: undefined,
      bound: undefined, finalizing: undefined })
    showPerspectiveContext(this.resource, chosen, chosenName)
    // An acknowledged write stays acknowledged even if its follow-up read fails.
    try {
      await this.read()
      if (this.state.error) throw new Error(this.state.error)
      const target = this.state.viewed ?? this.state.selected
      if (target) await this.view(target)
      const selected = this.state.rows.find((row) => row.perspective === this.state.selected)
      // With the durable read in hand, the chip is stamped with the version
      // this card is now showing -- unless it already stands for one.
      if (this.state.selected && selected) showPerspectiveContext(this.resource, this.state.selected, selected.name, selected)
    } catch (e) { this.update({ error: `Question action saved. Refresh failed: ${(e as Error).message}` }) }
    return v
  }
  async view(perspective: string) {
    const mine = ++this.historyVersion
    this.update({ viewed: perspective, viewedDetail: undefined, events: [], next: null, historyComplete: false, active: undefined, receipt: undefined, answer: undefined, bound: undefined, finalizing: undefined })
    const v = this.detail(await this.get(`/${perspective}`), perspective)
    if (mine !== this.historyVersion || this.state.viewed !== perspective) return
    this.update({ viewedDetail: v, rows: this.merged(this.state.rows, v) })
    await this.history()
  }
  /** REFRESH WHAT IS RECORDED AGAINST THE KEPT QUESTION, by hand or when the
   *  collection moves. It re-reads the question being viewed through `view()`
   *  -- the same guarded durable read, with the same identity and lens checks
   *  -- and says whether the answer standing now is a different recorded event
   *  than the one just shown. It writes nothing, selects nothing and starts no
   *  agent: a refresh that formed an answer would be a write, and this is a
   *  read -- an answer is formed only where the owner asks for one (`ask`,
   *  `summarise`).
   *
   *  One read per call, and no caller may turn it into a loop: there is no
   *  timer here and nothing retries. An unresolved write still blocks it, so a
   *  refresh never runs over an action whose outcome is unknown. */
  async recheck(): Promise<'none' | 'unchanged' | 'changed'> {
    const target = this.state.viewed ?? this.state.selected
    if (!target) return 'none'
    if (this.state.pending) throw new Error('Resolve the unchanged question action before reading this question again.')
    const before = answerHistory(this.state.events).current?.post ?? null
    await this.view(target)
    if ((this.state.viewed ?? this.state.selected) !== target) return 'none'
    return (answerHistory(this.state.events).current?.post ?? null) === before ? 'unchanged' : 'changed'
  }
  /** ASK THIS QUESTION OF THE COLLECTION, and keep the answer.
   *
   *  One owner action, one appended answer. Asking again later SUPERSEDES
   *  rather than overwrites: the server records a new `answered` event and
   *  leaves every earlier one exactly where it was, which is why
   *  `answerHistory` can name the one standing now and keep the rest. Omitting
   *  `text` re-answers the question already saved -- which is what the
   *  evolving summary is -- and the server refuses that when the collection
   *  holds no record the last answer did not read.
   *
   *  It goes through the same frozen, keyed, retryable write every other
   *  question action uses, so a lost acknowledgement is retried unchanged and
   *  never asked twice. */
  async ask(text?: string, op = uuid('answer')) {
    const target = this.state.viewed ?? this.state.selected
    if (!target) throw new Error('Open a question before asking it of this collection.')
    return this.action('answer', text && text.trim() ? { text } : {}, target, op)
  }

  /** This Magnet's standing Perspective, creating it if the record holds none.
   *
   *  The key is derived from the Magnet, so creation happens exactly once
   *  however many surfaces call this and however many acknowledgements are
   *  lost -- and the server converges on the first one in the record besides
   *  (`perspectives.standing`). It does not select it: the owner's active
   *  question is theirs. */
  async ensureStanding(): Promise<string> {
    if (!this.state.standing) await this.read()
    const known = this.state.standing
    if (known) return known
    const v = await this.write('', { name: STANDING_NAME, question: STANDING_QUESTION, standing: true },
                               standingOp(this.resource.saved.id))
    if (typeof v.perspective !== 'string') throw new Error('The standing question did not return its identity.')
    this.update({ standing: v.perspective })
    return v.perspective
  }

  /** The standing Perspective's recorded answers. A read: it reads the listing
   *  and that one Perspective's bounded history and nothing else. */
  async readSummary(): Promise<StandingSummary | null> {
    if (!this.state.standing) await this.read()
    const topic = this.state.standing
    if (!topic) { this.update({ summary: null }); return null }
    const seen: InquiryEvent[] = []
    await walkPages(async (cursor) => {
      const v = await this.get(`/${topic}/history?` + new URLSearchParams({ limit: '100', ...(cursor ? { cursor } : {}) }))
      if (v.perspective !== topic) throw new Error('History answered for another Perspective.')
      if (Array.isArray(v.events)) seen.push(...v.events)
      return v.next ?? null
    })
    const { current, superseded } = answerHistory(seen)
    const summary: StandingSummary = { perspective: topic, current, superseded,
      batch: typeof current?.data?.basis?.batch === 'string' ? current.data.basis.batch : null }
    this.update({ summary })
    return summary
  }

  /** RE-ANSWER THE STANDING QUESTION OVER THE COLLECTION NOW HELD.
   *
   *  Keyed by the batch, so one collection produces at most one evolving
   *  summary however often this is pressed or replayed, and a second
   *  collection produces a new current answer with the previous one in its
   *  history. The server decides whether there is anything new to answer --
   *  Part E's own `new_since` count, read there and not trusted from here --
   *  and refuses `nothing-new` rather than recording a second answer that says
   *  the same thing. */
  async summarise(batch: string): Promise<StandingSummary | null> {
    const topic = await this.ensureStanding()
    await this.write(`/${topic}/answer`, {}, standingAnswerOp(this.resource.saved.id, batch))
    return this.readSummary()
  }

  /** Every page is bounded and frozen by the server cursor. Before a new
   * request, inspect durable unresolved intents even when browser state was lost. */
  async completeHistory() {
    await walkPages(async (cursor) => { await this.history(cursor); return this.state.next })
  }
  async prepare(text: string, op: string): Promise<PreparedInquiry> {
    const topic = this.state.selected
    if (!topic) throw new Error('Choose a Perspective before preparing a question.')
    const row = this.state.rows.find((p) => p.perspective === topic)
    if (row?.retired) throw new Error('Resume this Perspective before asking a new question.')
    this.update({ viewed: topic })
    await this.completeHistory()
    if (this.state.selected !== topic) throw new Error('The active Perspective changed while history was being read. Nothing was sent.')
    const prepares = this.state.events.filter((e) => ['prepare', 'prepared'].includes(e.event))
    const last = prepares.at(-1)
    if (last) {
      const held = await this.get(`/${topic}/intents/${last.post}`)
      if (this.state.selected !== topic) throw new Error('The active Perspective changed while recovering the original intent. Nothing was sent.')
      if (!held.binding || !(held.answers?.length)) {
        if (held.prepared?.text === text && held.prepared?.brain === page.bound()) { this.update({ active: held.prepared }); return held.prepared }
        throw new Error('An earlier frozen question has no accepted answer. Resolve or explicitly resume that original request in the wording history before sending a different question.')
      }
    }
    const question = await this.write(`/${topic}/question`, { text }, `${op}-question`)
    const batch = this.resource.snapshot().activation?.artifact.ref
    if (!batch) throw new Error('Select a collection before asking a Perspective question.')
    const selected = this.resource.snapshot().results.filter((r) => this.state.selections[r.id])
    const selections = selected.flatMap((r) => {
      const value = r.value as any, source = (r as any).capturedSourceKey
      if (!source) throw new Error('The selected item lacks captured source provenance.')
      const base = { batch, source, item: r.id, version: r.version, start: 0, stance: this.state.selections[r.id] }
      if ((r as any).via === 'held-source') return [{ ...base, part: 0, end: value.end }]
      let body = value?.body ?? value
      if (typeof value?.body_json === 'string') body = JSON.parse(value.body_json)
      const parts = Array.isArray(body?.parts) ? body.parts : [{ type: 'text', text: body?.text ?? '' }]
      return parts.flatMap((p: any, part: number) => p.type === 'text' && typeof p.text === 'string' ? [{ ...base, part, end: Array.from(p.text).length }] : [])
    })
    const prepared = await this.write(`/${topic}/prepare`, { question: question.question.ref, batches: [batch], selections, priors: this.state.priors, declared_context: this.state.declared, continuation: this.state.continuation }, `${op}-prepare`) as PreparedInquiry
    if (this.state.selected !== topic || prepared.perspective !== topic || prepared.brain !== page.bound()) throw new Error('The lens or Brain changed during preparation. The original frozen intent is retained; it was not sent under a new selection.')
    // A freshly frozen question is never read against a reply bound to an
    // earlier one: dropping `bound` here is what keeps the agent-reply
    // boundary from being checked against the wrong intent.
    this.update({ active: prepared, bound: undefined, finalizing: undefined }); return prepared
  }
  async bind(prepared: PreparedInquiry, request: string) { return this.write(`/${prepared.perspective}/bind`, { intent: prepared.intent, request }, `${prepared.request_op}-bind`) }
  async manifest(prepared: PreparedInquiry): Promise<any> {
    if (prepared.brain !== page.bound()) throw new Error('This frozen question belongs to a different Brain instance.')
    const r = await fetch(`/api/artifacts/${encodeURIComponent(prepared.manifest.ref)}`, { headers: CLIENT_HEADERS, cache: 'no-store' })
    if (!r.ok) throw new Error('The original frozen manifest is unavailable. No current collection was substituted.')
    const raw = new Uint8Array(await r.arrayBuffer())
    const digest = [...new Uint8Array(await crypto.subtle.digest('SHA-256', raw))].map((n) => n.toString(16).padStart(2, '0')).join('')
    if (raw.byteLength !== prepared.manifest.size || digest !== prepared.manifest.digest || prepared.brain !== page.bound()) throw new Error('The original manifest did not verify for this Brain.')
    return JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(raw))
  }
  async reconcile(prepared: PreparedInquiry, purpose: 'display' | 'resume' | 'reuse' | 'attach', execution?: string) {
    const receipt = await this.write(`/${prepared.perspective}/reconcile`, { intent: prepared.intent, purpose, ...(execution ? { execution } : {}), declared_context: this.state.declared })
    this.update({ receipt }); return receipt
  }
  /** FREEZE AN ACTUAL REPLY AS THIS PERSPECTIVE'S SYNTHESIZED ANSWER.
   *
   *  `execution` is the qualified reconciliation's own (the latest run for
   *  the bound request, as the record states it -- never guessed here), and
   *  `answer` is the exact reply Turn the record shows answered it. The
   *  server re-checks qualification itself and refuses rather than records
   *  an unqualified reply; that refusal comes back here as an ordinary
   *  result, not a thrown error, so a reply the agent sent that the record
   *  cannot reconcile stays an ordinary reply and nothing is left stuck. */
  async finalize(prepared: PreparedInquiry, execution: string, answer: string): Promise<any> {
    return this.write(`/${prepared.perspective}/finalize`, { intent: prepared.intent, execution, answer },
      `${prepared.request_op}-finalize-${answer}`)
  }
}

/** THE RECORDED AGENT-REPLY BOUNDARY, acted on exactly once per reply.
 *
 *  Called wherever the record's own live read says a bound ask was answered
 *  (the pulse-driven Conversation view, which already watches for an agent's
 *  reply): never a new poll or timer of its own. Idempotent against the
 *  three ways this can go wrong --
 *
 *  - UNRELATED: the caller is the one that matches `answer` to this
 *    Perspective's own bound expectation before calling this at all; nothing
 *    here reads any other reply.
 *  - RETRIED: the same reply Turn is read again on a later pulse (nothing
 *    changed, or this call is still in flight) -- `store.snapshot().answer`
 *    and `.finalizing` are checked against the exact Turn id, so the second
 *    observation does nothing.
 *  - FAILED: the agent's run produced a reply that does not reconcile as a
 *    synthesis (missing declared context, a late or superseded execution).
 *    The server's refusal comes back as an ordinary result; it is recorded
 *    so the same unqualified reply is not repeatedly sent, and the raw reply
 *    stays exactly what it is -- an ordinary reply, not a synthesized
 *    answer. */
export async function finalizeReply(
  store: PerspectiveStore, prepared: PreparedInquiry, answer: string,
): Promise<{ ok: true; out: any } | { ok: false; why: string } | null> {
  const before = store.snapshot()
  if (before.answer?.answer_post_attempted === answer || before.finalizing === answer) return null
  store.update({ finalizing: answer })
  try {
    const receipt = await store.reconcile(prepared, 'attach')
    if (receipt.status !== 'qualified' || typeof receipt.execution !== 'string') {
      store.update({ answer: { answer_post_attempted: answer, refused: true } })
      return { ok: false, why: 'The agent’s reply does not yet reconcile as this Perspective’s answer.' }
    }
    const out = await store.finalize(prepared, receipt.execution, answer)
    store.update({ answer: { ...out, answer_post_attempted: answer } })
    if (out?.refused) return { ok: false, why: out.error ?? 'The agent’s reply did not qualify as this Perspective’s synthesized answer.' }
    return { ok: true, out }
  } catch (e) {
    return { ok: false, why: (e as Error).message }
  } finally {
    if (store.snapshot().finalizing === answer) store.update({ finalizing: undefined })
  }
}
export function perspectivesOf(resource: MagnetResource) {
  let store = stores.get(resource)
  if (!store) { store = new PerspectiveStore(resource); stores.set(resource, store) }
  return store
}

/** Open a Perspective, or one of its earlier wordings, in the Perspectives tab. */
export function openPerspective(resource: MagnetResource, perspective: string, item?: string) {
  remember(resource)
  resource.update({ tab: 'Perspectives', overlay: null,
    searchTarget: { kind: 'Perspectives', lens: perspective, ...(item ? { item } : {}) } })
  setOpen(resource, true)
}

/** The wording an inquiry event carries, if it carries one. */
const wordingOf = (e: InquiryEvent): string | null =>
  typeof e.data?.text === 'string' ? e.data.text : typeof e.data?.name === 'string' ? e.data.name : null
/** Ordinary words for what a durable event is (owner ent-3191baeb33d2 §2, and
 *  ent-068c167fa7e6 §4: no implementation terminology where the owner reads).
 *  The panel's wording history shows these; an event this does not name falls
 *  back to its own word rather than being hidden. */
export const EVENT_WORDS: Record<string, string> = {
  question: 'Earlier wording', created: 'Original wording', branch: 'Branched wording',
  challenge: 'Recorded challenge', challenged: 'Recorded challenge',
  rename: 'Earlier name', retire: 'Retired', resume: 'Resumed', selected: 'Made the active question',
}

/** H5's contribution to the universal index (§4). `entries()` is what the panel
 *  has already read; `complete()` owes every Perspective and every earlier
 *  wording of each, so the search is over what the Magnet holds and not over
 *  whichever page happened to be open. It reads through the store's `get`,
 *  which never writes, so searching cannot move the owner's viewed lens. */
export function perspectiveSource(resource: MagnetResource): SearchSource {
  const store = perspectivesOf(resource)
  let stopped: string | null = null
  const rowEntry = (row: Perspective): SearchEntry => ({
    key: `perspective:${row.perspective}`, kind: 'Perspectives',
    title: `${row.name}${row.retired ? ' (retired)' : ''}`,
    text: [row.name, row.current_question?.text ?? ''].filter(Boolean).join(' · '),
    open: () => openPerspective(resource, row.perspective),
  })
  const wordingEntry = (row: Perspective, e: InquiryEvent): SearchEntry | null => {
    const text = wordingOf(e)
    return text === null ? null : {
      key: `wording:${row.perspective}:${e.post}`, kind: 'Perspectives',
      title: `${EVENT_WORDS[e.event] ?? e.event} · ${row.name}`,
      text, open: () => openPerspective(resource, row.perspective, e.post),
    }
  }
  const unique = (rows: (SearchEntry | null)[]): SearchEntry[] => {
    const by = new Map<string, SearchEntry>()
    for (const row of rows) if (row && !by.has(row.key)) by.set(row.key, row)
    return [...by.values()]
  }
  return {
    entries(): SearchEntry[] {
      const s = store.snapshot()
      const viewed = s.rows.find((p) => p.perspective === (s.viewed ?? s.selected))
      return unique([
        ...s.rows.map(rowEntry),
        ...(viewed ? s.events.map((e) => wordingEntry(viewed, e)) : []),
      ])
    },
    async complete(_query, signal): Promise<SearchEntry[]> {
      stopped = null
      const out: (SearchEntry | null)[] = []
      try {
        const rows: Perspective[] = []
        await walkPages(async (cursor) => {
          if (signal?.aborted) throw new Error('The search was abandoned before it finished.')
          const v = await store.get('?' + new URLSearchParams({ limit: '100', ...(cursor ? { cursor } : {}) }))
          if (Array.isArray(v.perspectives)) rows.push(...v.perspectives)
          return v.next ?? null
        })
        for (const row of rows) {
          out.push(rowEntry(row))
          await walkPages(async (cursor) => {
            if (signal?.aborted) throw new Error('The search was abandoned before it finished.')
            const v = await store.get(`/${row.perspective}/history?` + new URLSearchParams({ limit: '100', ...(cursor ? { cursor } : {}) }))
            if (v.perspective !== row.perspective) throw new Error('History answered for another Perspective.')
            for (const e of Array.isArray(v.events) ? v.events : []) out.push(wordingEntry(row, e))
            return v.next ?? null
          })
        }
      } catch (e) {
        // Say what was reached, rather than claim a complete search.
        stopped = `Perspectives and their wording history were searched only as far as they could be read: ${(e as Error).message}`
      }
      return unique(out)
    },
    queryDependent: false,
    bound: () => stopped,
  }
}
/** Preserve the shared Composer's addressing, runtime, reply and Work choices. */
export function perspectiveRequest(post: Record<string, unknown>, prepared: PreparedInquiry) {
  return { ...post, text: prepared.text, topics: [...new Set([...(Array.isArray(post.topics) ? post.topics : []), prepared.perspective])],
    parts: [{ type: 'text', text: prepared.text }, ...(Array.isArray(post.parts) ? post.parts.filter((p: any) => p.type !== 'text') : []), ...prepared.parts],
    _magnetPerspective: prepared,
    dispatch: (Array.isArray(post.dispatch) ? post.dispatch : []).map((spec: any) => ({ ...spec, reach: 'work', requires: [...new Set([...(spec.requires ?? []), 'call_mentis_tools'])], work: `Use the attached frozen Perspective records, manifest and evidence. Read them with read_artifact. Reconstruct the inquiry by its Topic ${prepared.perspective}, distinguish original support from interpretations and conflicting evidence, cite the exact versions/ranges, and answer the frozen question. ${PERSPECTIVE_DISCLOSURE}` })) }
}
