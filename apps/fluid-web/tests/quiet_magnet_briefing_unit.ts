/** PART 3: the reasoned Summary briefing, asked for and read.
 *
 *  What these prove, against owner request #1017 `ent-599e68de0893` ("I want the
 *  Summary to read like an intelligent research briefing or book report") and
 *  the plan's Part 3 done-when:
 *
 *  - the briefing is asked for through the mechanism that already exists: the
 *    standing question is made the active one, its words are frozen as this
 *    wording of it, and the immutable input package is prepared from the
 *    collection in hand (`store.prepare`) -- three durable writes and no
 *    fourth, no new route, and nothing else written;
 *  - NOTHING IS DISPATCHED by the press: the frozen ask is carried into this
 *    Magnet's Conversation for the owner to address and send, and the owner's
 *    own unsent words are never overwritten -- refused before anything is
 *    written;
 *  - the frozen wording is the owner's own ask (themes, discoveries,
 *    developments, implications, avenues), opens with the standing question
 *    verbatim so the sent Turn begins with it, and demotes counts;
 *  - an answer a run wrote is told from one the synthesis wrote by the two
 *    fields only `finalize` records, and its frozen words are read from the
 *    frozen package it names -- verified by exact size and digest, with nothing
 *    substituted when it does not verify;
 *  - with those words in hand the Summary's lead IS the briefing, drawn as the
 *    document it is by the renderer Fluid already has, with what the record
 *    checked before freezing it said beside it;
 *  - and the counted floor is never written over a briefing on its own. */
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import Summary, {
  BRIEFING_ASK, BRIEFING_BY_RUN, BRIEFING_COLLECTION_UNKNOWN, BRIEFING_FROM_EARLIER,
  BRIEFING_IS_YOURS_TO_SEND, BRIEFING_NOT_QUALIFIED, BRIEFING_OWN_WORDS_KEPT, BRIEFING_RESUMED,
  BRIEFING_REWRITTEN, BRIEFING_STANDS, BRIEFING_UNREAD,
  NOT_ANSWERED_YET, WRITE_THE_BRIEFING,
  agentWritten, askForBriefing, briefingFrozenWords, frozenWords, heldAnswer, needsWrittenAnswer,
  readFrozenAnswer, readStandingBriefing, withWords, writtenFromShown,
  type BriefingFrozen, type StandingBriefing,
} from '../src/quiet2/magnets/Summary'
import { managedSelector } from '../src/quiet2/magnets/ComposerBar'
import { STANDING_QUESTION, answerText, perspectiveRequest, perspectivesOf,
  type InquiryEvent, type PreparedInquiry } from '../src/quiet2/magnets/perspectives'
import { createMagnetResource } from '../src/quiet2/magnets/state'
import { miniComposerDraft, saveMiniComposer } from '../src/quiet2/magnets/conversation'
import { emptyDraft } from '../src/composer/draft'
import type { MagnetConfig } from '../src/fluid/surface/magnet/types'
import type { MagnetResource } from '../src/quiet2/magnets/contract'
import { page as binding } from '../src/brainBinding'

const SOURCE = 'ent-source111111'
const brainKey = 'origin|fixture|brain-briefing'
const digest = 'a'.repeat(64)
const STANDING = 'ent-standing11111'
const BATCH = 'adm-batch111111'

const store = () => {
  const mem = new Map<string, string>()
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: {
    getItem: (k: string) => mem.get(k) ?? null, setItem: (k: string, v: string) => mem.set(k, v),
    removeItem: (k: string) => mem.delete(k), clear: () => mem.clear() } })
  binding.saw('brain-briefing@instance-one')
  return mem
}

const config = (id: `mag-${string}`): MagnetConfig => ({ id,
  sources: [{ kind: 'conversation', conversation: SOURCE }],
  selection: { informationTypes: ['post', 'file'], dates: {} },
  conversation: 'ent-own111111', collection: { mode: 'one-time' }, synthesis: { mode: 'manual' },
  notifications: { newItems: false, changes: false, failures: false }, presentation: { renderer: 'disc' } })

const POSTS = [
  { kind: 'post', id: 'ent-post111111', number: 11, version: 'ent-post111111', conversation: SOURCE, via: 'home',
    at: 1763900000, value: { parts: [{ type: 'text', text: 'The lander reached the south pole and returned its first images.' }] } },
  { kind: 'post', id: 'ent-post222222', number: 12, version: 'ent-post222222', conversation: SOURCE, via: 'home',
    at: 1764000300, value: { parts: [{ type: 'text', text: 'A second launch window opens next spring for the same orbiter.' }] } },
]
const ACTIVATION = { post: 'ent-activation111', artifact: { ref: BATCH, digest, size: 2048, media_type: 'application/json' },
  at: 1764000500, state: 'recorded' }

function resource(id: `mag-${string}`, collected = true) {
  const c = config(id)
  const r = createMagnetResource({ id: `qm-${id}`, brainKey, saved: { id, name: 'Space missions', config: c },
    get: async () => ({ status: 200, body: collected
      ? { magnet: id, config: c, activation: ACTIVATION, page: { sources: [{ source: c.sources[0], key: `conversation:${SOURCE}`, status: 'ok', results: POSTS }] } }
      : { magnet: id, config: c, activation: null, page: null } }) })
  return r
}
const html = (node: Parameters<typeof renderToStaticMarkup>[0]) => renderToStaticMarkup(node)

/** A store whose durable reads answer for the standing question, and whose
 *  writes are recorded rather than sent.
 *
 *  THE WORDING MOVES WHEN IT IS WRITTEN, as the record's does: the detail read
 *  answers with the wording held BEFORE the press until `/question` records
 *  the briefing wording, and with the new revision after. A fixture that
 *  answered with the new revision all along could not see the state the send
 *  actually refused (review `ent-5acd177f3aa8` F2), which is why the chip
 *  checks below are run against this transition.
 *
 *  `events` is the durable question history `prepare` reads before it freezes
 *  anything, so an unanswered earlier intent can be put in front of it. */
const BEFORE = 'adm-revision111', FROZEN = 'adm-revision222'
function asking(r: MagnetResource, opts: {
  standing?: string | null
  events?: Record<string, unknown>[]
  intents?: Record<string, Record<string, unknown>>
  receipt?: Record<string, unknown>
  wording?: string
} = {}) {
  const s = perspectivesOf(r), sent: unknown[][] = []
  let selected: string | null = null
  let revision = BEFORE, words = opts.wording ?? STANDING_QUESTION
  const standing = opts.standing === undefined ? STANDING : opts.standing
  const detail = (topic: string) => ({ magnet: r.saved.id, perspective: topic, selected,
    name: 'What this Magnet has gathered', retired: false,
    question: { ref: revision, digest, size: 40, media_type: 'application/json' },
    current_question: { text: words, revision }, events: 3 })
  s.get = async (tail = '') => {
    if (tail.startsWith('?')) return { magnet: r.saved.id, perspectives: [], selected, standing, next: null }
    const topic = tail.split('/')[1]
    if (tail.includes('/history')) return { magnet: r.saved.id, perspective: topic, events: opts.events ?? [], next: null }
    if (tail.includes('/intents/')) {
      const held = opts.intents?.[decodeURIComponent(tail.split('/intents/')[1])]
      if (!held) throw new Error(`unexpected intent read ${tail}`)
      return held
    }
    return detail(topic)
  }
  s.write = async (tail: string, data: Record<string, unknown>, op?: string) => {
    sent.push([tail, data, op])
    if (tail === '') return { perspective: standing ?? STANDING }
    if (tail === '/selected') { selected = (data.perspective as string) ?? null; return { perspective: selected } }
    if (tail.endsWith('/question')) { revision = FROZEN; words = data.text as string
      return { perspective: STANDING, question: { ref: revision, digest, size: 40, media_type: 'application/json' } } }
    if (tail.endsWith('/reconcile')) return opts.receipt ?? { status: 'qualified', execution: 'ent-execution111' }
    if (tail.endsWith('/prepare')) return prepared()
    throw new Error(`unexpected write ${tail}`)
  }
  /** What `prepare` answers with: the frozen wording's own revision, and the
   *  collection it was frozen from among its records, as the server's own
   *  closure holds it. */
  const prepared = () => ({ intent: 'ent-intent111111', perspective: STANDING, brain: binding.bound(),
    question: { ref: revision, digest, size: 40, media_type: 'application/json' },
    manifest: { ref: 'adm-manifest1111', digest, size: 10, media_type: 'application/json' },
    records: { ref: 'adm-records11111', digest, size: 10, media_type: 'application/json' },
    artifacts: [{ ref: BATCH, digest, size: 2048, media_type: 'application/json' },
      { ref: 'adm-manifest1111', digest, size: 10, media_type: 'application/json' }],
    parts: [], reach: 'work', request_op: 'perspective-request:ent-intent111111',
    text: words, closure: { count: 2, bytes: 20 }, disclosure: '' })
  return { s, sent, prepared, selectedNow: () => selected, revisionNow: () => revision }
}

/** Serve named records as the one artifact door, with their real digests, so
 *  everything this view verifies is verified against actual bytes. */
async function serving(bytesOf: Record<string, Uint8Array>) {
  const asked: string[] = []
  const held: Record<string, { digest: string; size: number }> = {}
  for (const [ref, raw] of Object.entries(bytesOf))
    held[ref] = { size: raw.byteLength,
      digest: [...new Uint8Array(await crypto.subtle.digest('SHA-256', raw as unknown as ArrayBufferView<ArrayBuffer>))]
        .map((n) => n.toString(16).padStart(2, '0')).join('') }
  ;(globalThis as any).fetch = async (url: string) => {
    asked.push(url)
    const ref = decodeURIComponent(url.split('/api/artifacts/')[1] ?? '')
    const raw = bytesOf[ref]
    if (!raw) return { ok: false, arrayBuffer: async () => new ArrayBuffer(0) }
    return { ok: true, arrayBuffer: async () => raw.buffer.slice(raw.byteOffset, raw.byteOffset + raw.byteLength) }
  }
  return { asked, held, stop: () => { delete (globalThis as any).fetch } }
}
const encoded = (value: unknown) => new TextEncoder().encode(JSON.stringify(value))
/** The chip as the card holds it, read as plain fields for the assertions. */
const chipOf = (r: MagnetResource) => (r.snapshot().context ?? {}) as unknown as Record<string, unknown>

/* --- the frozen wording ----------------------------------------------------- */

test('the frozen briefing wording is the owner’s own ask, and begins with the standing question', () => {
  // `perspectives_work.bind` refuses a sent Turn that does not begin with the
  // frozen question, and the frozen question is this wording, so it has to
  // open with the kept question itself.
  assert.ok(BRIEFING_ASK.startsWith(STANDING_QUESTION), 'it opens with the kept question verbatim')
  for (const asked of ['themes', 'discoveries', 'developments', 'imply', 'avenues', 'cite'])
    assert.match(BRIEFING_ASK, new RegExp(asked, 'i'), `the owner's own ask for ${asked} is in the frozen words`)
  assert.match(BRIEFING_ASK, /statistics are secondary/i, 'and counts are demoted, as the owner asked')
  // Nothing the owner reads here uses the record's own vocabulary
  // (ent-3191baeb33d2 §2), which is checked for every new sentence of this part.
  for (const line of [BRIEFING_ASK, WRITE_THE_BRIEFING, BRIEFING_IS_YOURS_TO_SEND, BRIEFING_BY_RUN,
    BRIEFING_STANDS, BRIEFING_UNREAD, BRIEFING_NOT_QUALIFIED, BRIEFING_OWN_WORDS_KEPT, BRIEFING_RESUMED,
    BRIEFING_FROM_EARLIER, BRIEFING_COLLECTION_UNKNOWN])
    assert.doesNotMatch(line, /retained|batch/i, `a line the owner reads says it: ${line}`)
})

/* --- the sentences say no more than the record checked (review F3, F5) ------ */

test('the press’s own note no longer promises this collection as the only evidence', () => {
  // `store.prepare` sends the collection AND this question's selections,
  // declarations, priors and continuation, so "the only evidence for it" was a
  // promise the act does not keep (review F3).
  assert.doesNotMatch(BRIEFING_IS_YOURS_TO_SEND, /only evidence/i)
  assert.match(BRIEFING_IS_YOURS_TO_SEND, /selected, declared or carried over/i,
    'what else can travel with the question is said where the promise was')
})

test('what the record checked is claimed as what it is, and its limits are said', () => {
  // The old sentence said the record checked that what the run could reach was
  // EXACTLY the frozen package and nothing else. Reconciliation enumerates what
  // Mentis OFFERED (`artifacts.available`), the boundary admits this Magnet's
  // own Conversation and held packages, and no check reads statements (F5).
  assert.doesNotMatch(BRIEFING_BY_RUN, /\bexactly\b/i, 'no exact-reach claim')
  assert.doesNotMatch(BRIEFING_BY_RUN, /nothing else\b/i)
  assert.match(BRIEFING_BY_RUN, /offered/i, 'it says what the accounting is of')
  assert.match(BRIEFING_BY_RUN, /not of everything the run read/i, 'and what it is not')
  assert.match(BRIEFING_BY_RUN, /own Conversation/i, 'the boundary’s own admissions are named')
  assert.match(BRIEFING_BY_RUN, /own tools/i, 'and the runtime’s own tools are told, not policed')
  assert.match(BRIEFING_BY_RUN, /statement by statement/i, 'and per-statement support is not claimed')
})

test('what was frozen is counted from the frozen request, inherited context included', () => {
  const frozen = (over: Partial<BriefingFrozen> = {}): BriefingFrozen => ({ intent: 'ent-intent111111',
    question: BRIEFING_ASK, revision: FROZEN, manifest: 'adm-manifest1111', records: 4,
    collection: BATCH, resumed: false,
    inherited: { priors: 0, declared: 0, selected: 0, continuation: false }, ...over })
  assert.match(briefingFrozenWords(frozen()), /4 records in all, written from the collection shown here/)
  assert.match(briefingFrozenWords(frozen()), /Nothing else is carried with it/)
  const carrying = briefingFrozenWords(frozen({
    inherited: { priors: 2, declared: 1, selected: 3, continuation: true } }))
  assert.match(carrying, /3 collected records you had selected/)
  assert.match(carrying, /1 record you declared for this question/)
  assert.match(carrying, /2 earlier answers to read as interpretations/)
  assert.match(carrying, /said about this question in this Magnet’s Conversation/)
  assert.match(briefingFrozenWords(frozen({ collection: null })),
    /the collection it was frozen with, which is not the one shown here/)
})

/* --- the press -------------------------------------------------------------- */

test('asking for a briefing refuses, writing nothing, with nothing collected', async () => {
  store()
  const r = resource('mag-bempty', false)
  await r.read()
  const { s, sent } = asking(r)
  await assert.rejects(askForBriefing(r, s), /Collect something first/)
  assert.deepEqual(sent, [], 'a refusal before anything is collected writes nothing')
})

test('asking for a briefing refuses, writing nothing, over words of the owner’s own', async () => {
  store()
  const r = resource('mag-bdraft')
  await r.read()
  const { s, sent } = asking(r)
  saveMiniComposer(r, { ...emptyDraft(), text: 'Words of my own I have not sent' })
  await assert.rejects(askForBriefing(r, s), /different words of yours/)
  assert.deepEqual(sent, [], 'the owner’s unsent words are never overwritten, and nothing is written for them')
  assert.equal(miniComposerDraft(r).text, 'Words of my own I have not sent')
})

test('asking for a briefing freezes the standing question with this collection and hands it to the Conversation', async () => {
  store()
  const r = resource('mag-bask')
  await r.read()
  const { s, sent, selectedNow } = asking(r)
  const draft = { ...emptyDraft(), action: 'ask-mentis' as const, coordinate: true }
  saveMiniComposer(r, draft)
  await askForBriefing(r, s)
  // THE STANDING QUESTION IS MADE THE ACTIVE ONE, because the composer's own
  // check is against the chip, and the chip follows the active question.
  assert.deepEqual(sent[0], ['/selected', { perspective: STANDING }, `${sent[0][2]}`])
  assert.equal(selectedNow(), STANDING)
  // THEN the words are frozen as this wording of that question...
  assert.equal(sent[1][0], `/${STANDING}/question`)
  assert.deepEqual(sent[1][1], { text: STANDING_QUESTION }, 'answer instructions do not revise the standing question')
  assert.match(String(sent[1][2]), new RegExp(`^magnet-briefing:${r.saved.id}:`))
  // ...and the input package is prepared from the collection in hand.
  assert.equal(sent[2][0], `/${STANDING}/prepare`)
  assert.equal((sent[2][1] as any).question, 'adm-revision222')
  assert.deepEqual((sent[2][1] as any).batches, [BATCH])
  assert.equal(sent.length, 3, 'three durable writes, and never a fourth')
  // NOTHING IS DISPATCHED. The frozen ask is kept for the composer's own
  // `beforeRequest` to carry, the words are in the Conversation's composer, and
  // the owner's send choices are untouched.
  assert.equal(s.snapshot().active?.intent, 'ent-intent111111')
  assert.equal(s.snapshot().active?.reach, 'work')
  assert.equal(miniComposerDraft(r).text, BRIEFING_ASK)
  assert.equal(miniComposerDraft(r).action, 'ask-mentis')
  assert.equal(r.snapshot().tab, 'Conversation')
  assert.equal(r.snapshot().open, true)
})

/* --- the owner's own unsent words survive the waits (review F1) ------------- */

test('words written WHILE the question is being frozen are kept, and nothing is written over them', async () => {
  store()
  const r = resource('mag-bwait')
  await r.read()
  const { s } = asking(r)
  // Hold preparation open, type during the wait, then let it finish: this is
  // the reviewer's own reproduction, and the words must still be there.
  const base = s.prepare.bind(s)
  let entered: () => void = () => {}, release: () => void = () => {}
  const waiting = new Promise<void>((done) => { entered = done })
  const pending = new Promise<void>((done) => { release = done })
  s.prepare = async (...args: Parameters<typeof base>) => { entered(); await pending; return base(...args) }
  const asking_ = askForBriefing(r, s)
  await waiting
  const mine = 'New owner words typed during the network wait'
  saveMiniComposer(r, { ...emptyDraft(), text: mine })
  release()
  await assert.rejects(asking_, new RegExp(BRIEFING_OWN_WORDS_KEPT.slice(0, 40)))
  assert.equal(miniComposerDraft(r).text, mine, 'the owner’s words are exactly as they were typed')
})

test('the same words typed during the wait are not treated as a stranger’s', async () => {
  store()
  const r = resource('mag-bwaitsame')
  await r.read()
  const { s } = asking(r)
  const base = s.prepare.bind(s)
  let entered: () => void = () => {}, release: () => void = () => {}
  const waiting = new Promise<void>((done) => { entered = done })
  const pending = new Promise<void>((done) => { release = done })
  s.prepare = async (...args: Parameters<typeof base>) => { entered(); await pending; return base(...args) }
  const asking_ = askForBriefing(r, s)
  await waiting
  saveMiniComposer(r, { ...emptyDraft(), text: BRIEFING_ASK })
  release()
  await asking_
  assert.equal(miniComposerDraft(r).text, BRIEFING_ASK)
})

/* --- what is handed over can actually be sent (review F2) ------------------- */

test('the chip stands for the wording that was frozen, and the send accepts it', async () => {
  store()
  const r = resource('mag-bchip')
  await r.read()
  const { s, revisionNow } = asking(r)
  await askForBriefing(r, s)
  // The wording moved when it was written, and the chip moved with it: before
  // this, selection stamped the chip at the wording BEFORE the press and the
  // send refused every prepared question.
  assert.equal(revisionNow(), FROZEN)
  const chip = chipOf(r)
  assert.equal(chip.kind, 'perspective')
  assert.equal(chip.ref, STANDING)
  assert.equal(chip.version, FROZEN, 'the chip stands for the wording that was frozen')
  assert.equal(chip.digest, digest)
  // The actual send boundary, against the real store and its fresh read.
  const selector = await managedSelector({ resource: r, inquiries: s }, {})
  assert.deepEqual(selector.perspective, { id: STANDING, question_ref: FROZEN, question_digest: digest })
})

test('the frozen ask carries no generated work override, which the one door refuses', async () => {
  store()
  const r = resource('mag-bcarrier')
  await r.read()
  const { s, prepared } = asking(r)
  await askForBriefing(r, s)
  const active = s.snapshot().active as PreparedInquiry
  assert.equal(active.intent, prepared().intent)
  const out = perspectiveRequest({ action: 'ask-participant', text: 'Original words',
    parts: [{ type: 'text', text: 'Original words' }],
    dispatch: [{ participant: 'ent-agent111111', runtime: 'codex', work: 'composed for it' }] }, active)
  // `mentis.fluid.message_context.gate` refuses ANY dispatch spec carrying a
  // `work` value with `invalid-managed-intent`, before any record or dispatch.
  for (const spec of out.dispatch as Record<string, unknown>[]) {
    assert.ok(!('work' in spec), 'no generated work override reaches the door')
    assert.equal(spec.reach, 'work', 'and the work reach `bind` requires is still carried')
  }
  // What the run is told travels as the message's own words instead, after the
  // frozen question, which `bind` requires the Turn to BEGIN with.
  assert.ok(String(out.text).startsWith(active.text), 'the sent words begin with the frozen question')
  assert.equal(active.text, STANDING_QUESTION, 'the frozen question has no answer instructions')
  assert.match(String(out.text), /publication prose/)
  assert.match(String(out.text), /omit first-person process narration/)
  assert.match(String(out.text), /internal Topic IDs, manifest IDs, batch IDs and other bookkeeping/)
  assert.match(String(out.text), /status\/outcome footer or closing work report/)
  assert.match(String(out.text), /citation tokens exact and inline, without backticks or other code wrappers/)
  assert.match(String(out.text), /read_artifact/, 'and go on to say what to do with the attached records')
  assert.deepEqual(out.parts[0], { type: 'text', text: out.text },
    'the one text part is the exact projection of the words, as the door checks')
})

test('refreshing preserves a saved standing question byte for byte', async () => {
  store()
  const r = resource('mag-stable-question')
  await r.read()
  const original = '  What changed in Roman\u2019s mission?\nKeep this wording.  '
  const { s, sent } = asking(r, { wording: original })
  await askForBriefing(r, s)
  const written = sent.find(([tail]) => String(tail).endsWith('/question'))![1] as { text: string }
  assert.equal(written.text, original)
  const active = s.snapshot().active!
  assert.equal(active.text, original)
  const out = perspectiveRequest({ text: miniComposerDraft(r).text }, active)
  assert.ok(String(out.text).startsWith(original + '\n\n'))
  assert.match(String(out.text).slice(original.length), /publication prose/)
})

/* --- a stale intent is resumed, and said to be (review F3) ------------------ */

test('an earlier unanswered briefing question is resumed, said so, and nothing is frozen again', async () => {
  store()
  const r = resource('mag-bresume')
  await r.read()
  const older = 'adm-older111111'
  const earlier = { intent: 'ent-earlier11111', perspective: STANDING, brain: binding.bound(),
    question: { ref: BEFORE, digest, size: 40, media_type: 'application/json' },
    manifest: { ref: 'adm-oldmanifest1', digest, size: 10, media_type: 'application/json' },
    records: { ref: 'adm-records11111', digest, size: 10, media_type: 'application/json' },
    artifacts: [{ ref: older, digest, size: 2048, media_type: 'application/json' }],
    parts: [], reach: 'work', request_op: 'perspective-request:ent-earlier11111',
    text: BRIEFING_ASK, closure: { count: 1, bytes: 10 }, disclosure: '' }
  // The record's own wording already IS the briefing wording, at the revision
  // that earlier intent was frozen with: that is what makes it reusable.
  const { s, sent } = asking(r, { wording: BRIEFING_ASK,
    events: [{ seq: 1, post: 'ent-earlier11111', event: 'prepared', perspective: STANDING, data: {} }],
    intents: { 'ent-earlier11111': { prepared: earlier, binding: null, answers: [] } } })
  const got = await askForBriefing(r, s)
  assert.deepEqual(sent.filter(([tail]) => String(tail).endsWith('/question') || String(tail).endsWith('/prepare')), [],
    'neither a new wording nor a new package is written')
  assert.equal(got.resumed, true)
  assert.equal(got.intent, 'ent-earlier11111')
  assert.equal(got.collection, null, 'and its evidence is not claimed to be the collection shown')
  assert.match(briefingFrozenWords(got), /not the one shown here/)
  assert.equal(miniComposerDraft(r).text, BRIEFING_ASK)
  // The chip stands for the wording THAT intent was frozen with, so the send
  // carries that request and not a different question.
  assert.equal(chipOf(r).version, BEFORE)
  assert.match(BRIEFING_RESUMED, /not a new one/i, 'and the owner is told which act happened')
})

test('what this question already carried is counted into what was frozen', async () => {
  store()
  const r = resource('mag-bcarried')
  await r.read()
  const { s } = asking(r)
  s.update({ priors: ['adm-prior111111'], declared: ['adm-declared1111', 'adm-declared2222'],
    continuation: true, selections: { 'ent-post111111': 'supporting' } })
  const got = await askForBriefing(r, s)
  assert.deepEqual(got.inherited, { priors: 1, declared: 2, selected: 1, continuation: true },
    'the press neither clears this question’s own context nor may claim it is absent')
  assert.equal(got.collection, BATCH, 'a question frozen here IS frozen with the collection shown')
  assert.match(briefingFrozenWords(got), /1 collected record you had selected/)
})

test('asking for a briefing creates the standing question exactly once, where the record holds none', async () => {
  store()
  const r = resource('mag-bstanding')
  await r.read()
  const { s, sent } = asking(r, { standing: null })
  await askForBriefing(r, s)
  assert.equal(sent[0][0], '', 'the standing question is created through its own keyed write')
  assert.equal((sent[0][1] as any).standing, true)
  assert.equal(sent[0][2], `magnet-standing:${r.saved.id}`, 'keyed by the Magnet, so a replay creates no second one')
})

/* --- telling a run’s answer from the written one ---------------------------- */

const synthesised = (text: string): InquiryEvent => ({ seq: 1, post: 'ent-written1111', event: 'answered',
  perspective: STANDING, snapshot: { ref: 'adm-answer111111', digest, size: 10, media_type: 'application/json' },
  data: { text, lines: [{ text, cites: [] }], method: 'mentis.magnet.synthesis/1', basis: { batch: BATCH } } })

const byRun = (over: Record<string, unknown> = {}): InquiryEvent => ({ seq: 2, post: 'ent-briefing111', event: 'answered',
  perspective: STANDING, snapshot: { ref: 'adm-event1111111', digest, size: 10, media_type: 'application/json' },
  data: { answer_post: 'ent-reply1111111', execution: 'ent-execution111', run: 'opr-run111111',
    answer: { ref: 'adm-frozen111111', digest, size: 10, media_type: 'application/json' }, ...over } })

test('an answer a run wrote is told from one the synthesis wrote, by the fields only finalize records', () => {
  assert.equal(agentWritten(byRun()), true)
  assert.equal(agentWritten(synthesised('Counted words.')), false)
  assert.equal(agentWritten(null), false)
  assert.equal(agentWritten(byRun({ execution: '' })), false, 'half a record is not a run-written answer')
  assert.deepEqual(heldAnswer(byRun()), { ref: 'adm-frozen111111', digest, size: 10 })
  assert.equal(heldAnswer(synthesised('x')), null, 'a package named without its digest and size is not read')
})

test('the frozen words of a run’s answer are its reply’s own text, in the order they were frozen', () => {
  assert.equal(frozenWords({ parts: [{ type: 'text', text: '## Themes\n\nThe lander reached the pole.' },
    { type: 'file', ref: 'adm-x' }, { type: 'text', text: 'And a second launch window opens.' }] }),
    '## Themes\n\nThe lander reached the pole.\n\nAnd a second launch window opens.')
  assert.equal(frozenWords({ parts: [{ type: 'text', text: '   ' }] }), '', 'nothing is read as words')
  assert.equal(frozenWords(null), '')
})

test('a run’s frozen answer is read through the artifact door and verified, or nothing is shown', async () => {
  const pkg = { format: 'mentis.magnet.perspective/1', kind: 'answer',
    parts: [{ type: 'text', text: '## Themes\n\n| Mission | Date |\n|---|---|\n| Lander | 2026 |' }] }
  const raw = new TextEncoder().encode(JSON.stringify(pkg))
  const sha = [...new Uint8Array(await crypto.subtle.digest('SHA-256', raw))].map((n) => n.toString(16).padStart(2, '0')).join('')
  const asked: string[] = []
  const serve = (body: Uint8Array, ok = true) => {
    ;(globalThis as any).fetch = async (url: string) => { asked.push(url)
      return { ok, arrayBuffer: async () => body.buffer.slice(body.byteOffset, body.byteOffset + body.byteLength) } }
  }
  const answer = byRun({ answer: { ref: 'adm-frozen111111', digest: sha, size: raw.byteLength, media_type: 'application/json' } })
  serve(raw)
  assert.equal(await readFrozenAnswer(answer), pkg.parts[0].text)
  assert.deepEqual(asked, ['/api/artifacts/adm-frozen111111'], 'one read of the one named record')
  // A package that does not verify against the record shows nothing of itself.
  serve(new TextEncoder().encode(JSON.stringify({ parts: [{ type: 'text', text: 'Substituted words' }] })))
  await assert.rejects(readFrozenAnswer(answer), /did not verify/)
  serve(raw, false)
  await assert.rejects(readFrozenAnswer(answer), /unavailable/)
  // And where the event itself records the words, nothing is fetched at all.
  asked.length = 0
  assert.equal(await readFrozenAnswer(synthesised('Counted words.')), 'Counted words.')
  assert.deepEqual(asked, [])
  await assert.rejects(readFrozenAnswer(byRun({ answer: null })), /names no frozen record/)
  delete (globalThis as any).fetch
})

test('the frozen words are put where every part of this view reads an answer’s words, and nothing else changes', () => {
  const answer = byRun()
  const read = { post: answer.post, words: '## Themes\n\nThe lander reached the pole.' }
  const shown = withWords(answer, read)!
  assert.equal(answerText(shown), read.words)
  assert.equal(shown.post, answer.post)
  assert.equal(shown.data.answer_post, 'ent-reply1111111', 'the recorded event is otherwise untouched')
  assert.equal(agentWritten(shown), true)
  // Never the words of another answer, and never over words the event records.
  assert.equal(answerText(withWords(answer, { post: 'ent-other111111', words: 'Elsewhere' })!), '')
  assert.equal(answerText(withWords(synthesised('Counted words.'), { post: 'ent-written1111', words: 'Replaced' })!),
    'Counted words.')
  assert.equal(withWords(null, read), null)
})

/* --- qualified before it is read, and knowing its own collection (F4, F6) --- */

const WORDS = ['## What this collection shows', '',
  'Two themes run through the records: a landing at the south pole, and a launch window next spring.', '',
  '| Mission | When |', '|---|---|', '| Lander | 2026 |'].join('\n')

/** The three named records a standing briefing is read through, with their
 *  real digests, plus the intent read its event points at. */
async function briefingRecords(collection: string[] = [BATCH]) {
  const answerPkg = { format: 'mentis.magnet.perspective/1', kind: 'answer',
    parts: [{ type: 'text', text: WORDS }] }
  const manifestPkg = { format: 'mentis.magnet.perspective/1', kind: 'manifest',
    perspective: STANDING, batches: collection.map((ref) => ({ ref, digest, size: 2048, media_type: 'application/json' })) }
  const bytes = { 'adm-frozen111111': encoded(answerPkg), 'adm-manifest1111': encoded(manifestPkg) }
  const serve = await serving(bytes)
  const prepared = { intent: 'ent-intent111111', perspective: STANDING, brain: binding.bound(),
    question: { ref: FROZEN, digest, size: 40, media_type: 'application/json' },
    manifest: { ref: 'adm-manifest1111', ...serve.held['adm-manifest1111'], media_type: 'application/json' },
    records: { ref: 'adm-records11111', digest, size: 10, media_type: 'application/json' },
    artifacts: [], parts: [], reach: 'work', request_op: 'perspective-request:ent-intent111111',
    text: BRIEFING_ASK, closure: { count: 2, bytes: 20 }, disclosure: '' }
  const event: InquiryEvent = { seq: 2, post: 'ent-briefing111', event: 'answered', perspective: STANDING,
    snapshot: { ref: 'adm-event1111111', digest, size: 10, media_type: 'application/json' },
    data: { intent: 'ent-intent111111', request: 'ent-request11111', answer_post: 'ent-reply1111111',
      execution: 'ent-execution111', run: 'opr-run111111', manifest: prepared.manifest,
      answer: { ref: 'adm-frozen111111', ...serve.held['adm-frozen111111'], media_type: 'application/json' } } }
  return { serve, prepared, event }
}

test('a frozen answer is qualified afresh before any of its words are shown', async () => {
  store()
  const r = resource('mag-bqualify')
  await r.read()
  const { serve, prepared, event } = await briefingRecords()
  try {
    const { s, sent } = asking(r, { intents: { 'ent-intent111111': { prepared, binding: {}, answers: [] } } })
    const got = await readStandingBriefing(s, event)
    assert.equal(got.words, WORDS)
    assert.deepEqual(got.collection, [BATCH], 'and it knows which collection it was written from')
    // The contract's own requirement: a fresh display receipt for THIS
    // answer's frozen question and producing run, carrying no declarations.
    const receipt = sent.find(([tail]) => String(tail).endsWith('/reconcile'))!
    assert.equal(receipt[0], `/${STANDING}/reconcile`)
    assert.deepEqual(receipt[1], { intent: 'ent-intent111111', purpose: 'display', execution: 'ent-execution111' })
    assert.ok(serve.asked.includes('/api/artifacts/adm-manifest1111'), 'its own manifest is read and verified')
    assert.ok(serve.asked.includes('/api/artifacts/adm-frozen111111'), 'and then its frozen words')
  } finally { serve.stop() }
})

test('an answer the record will not qualify now shows none of its words', async () => {
  store()
  const r = resource('mag-bunqualified')
  await r.read()
  const { serve, prepared, event } = await briefingRecords()
  try {
    for (const status of ['pending', 'unqualified']) {
      const { s, sent } = asking(r, { receipt: { status, execution: 'ent-execution111' },
        intents: { 'ent-intent111111': { prepared, binding: {}, answers: [] } } })
      await assert.rejects(readStandingBriefing(s, event),
        new RegExp(`${BRIEFING_NOT_QUALIFIED.slice(0, 40)}|${status}`))
      assert.ok(sent.some(([tail]) => String(tail).endsWith('/reconcile')), 'it did ask the record')
      assert.ok(!serve.asked.includes('/api/artifacts/adm-frozen111111'),
        'and nothing of the frozen words was fetched, let alone shown')
    }
  } finally { serve.stop() }
})

test('an answer naming no frozen question or run is not shown on its digest alone', async () => {
  store()
  const r = resource('mag-bnointent')
  await r.read()
  const { s } = asking(r)
  const bare: InquiryEvent = { seq: 1, post: 'ent-bare1111111', event: 'answered', perspective: STANDING,
    snapshot: { ref: 'adm-event1111111', digest, size: 10, media_type: 'application/json' },
    data: { answer_post: 'ent-reply1111111', execution: 'ent-execution111',
      answer: { ref: 'adm-frozen111111', digest, size: 10, media_type: 'application/json' } } }
  await assert.rejects(readStandingBriefing(s, bare), /does not name the frozen question/)
})

test('which collection a briefing was written from is read from its own manifest', async () => {
  const got = (collection: string[]): StandingBriefing => ({ post: 'ent-briefing111', words: WORDS, collection })
  assert.equal(writtenFromShown(got([BATCH]), 'ent-briefing111', BATCH), true)
  assert.equal(writtenFromShown(got(['adm-older1111111']), 'ent-briefing111', BATCH), false)
  assert.equal(writtenFromShown(got([BATCH]), 'ent-other111111', BATCH), null, 'another answer’s reading claims nothing')
  assert.equal(writtenFromShown(null, 'ent-briefing111', BATCH), null)
  assert.equal(writtenFromShown(got([BATCH]), 'ent-briefing111', undefined), null)
})

test('a briefing written from an earlier collection says so, and is still kept', async () => {
  store()
  const r = resource('mag-bstale')
  await r.read()
  const { serve, prepared, event } = await briefingRecords(['adm-older1111111'])
  try {
    const { s } = asking(r, { intents: { 'ent-intent111111': { prepared, binding: {}, answers: [] } } })
    const read = await readStandingBriefing(s, event)
    assert.deepEqual(read.collection, ['adm-older1111111'], 'its own frozen collection, not the one shown')
    // AND THE SURFACE SAYS IT. An answer the record holds for an earlier
    // collection stands here -- it is not buried -- beside a sentence saying
    // which collection it was written from, and never beside the one that
    // says it was rewritten from the collection shown.
    const earlier = withWords(event, read)!
    s.update({ standing: STANDING,
      summary: { perspective: STANDING, current: earlier, superseded: [], batch: 'adm-older1111111' } })
    const asWritten = html(createElement(Summary, { resource: r, onPost: () => {} }))
    assert.ok(asWritten.includes('Two themes run through the records'), 'the older briefing is NOT buried')
    assert.ok(!asWritten.includes(BRIEFING_REWRITTEN),
      'the "rewritten from the collection shown" sentence is never said of it')
    assert.ok(asWritten.includes(BRIEFING_COLLECTION_UNKNOWN),
      'where this surface has not read its collection, it claims neither')
    // The written synthesis records its own collection, so an older one of
    // those is named as what it is.
    s.update({ summary: { perspective: STANDING,
      current: synthesised('An older counted answer.'), superseded: [], batch: 'adm-older1111111' } })
    const counted = html(createElement(Summary, { resource: r, onPost: () => {} }))
    assert.ok(counted.includes('An older counted answer.'), 'it is kept')
    assert.ok(counted.includes(BRIEFING_FROM_EARLIER), 'and said to be written from an earlier collection')
  } finally { serve.stop() }
})

/* --- the briefing as the Summary’s lead ------------------------------------- */

test('a briefing a run wrote leads the Summary as the document it is, with what the record checked beside it', async () => {
  store()
  const r = resource('mag-blead')
  await r.read()
  const words = ['## What this collection shows', '',
    'Two themes run through the records: a landing at the south pole, and a launch window next spring.', '',
    '| Mission | When |', '|---|---|', '| Lander | 2026 |'].join('\n')
  const answer = byRun()
  perspectivesOf(r).update({ standing: STANDING,
    summary: { perspective: STANDING, current: withWords(answer, { post: answer.post, words }), superseded: [], batch: null } })
  const rendered = html(createElement(Summary, { resource: r, onPost: () => {} }))
  assert.ok(rendered.includes('Two themes run through the records'), 'the briefing itself leads')
  assert.ok(rendered.includes('<h2') || rendered.includes('<h3'), 'drawn as the document it is, by the renderer that exists')
  assert.ok(rendered.includes('<table'), 'its table is a table')
  assert.ok(!rendered.includes(NOT_ANSWERED_YET), 'and it is not labelled as counted')
  assert.ok(rendered.includes(BRIEFING_BY_RUN), 'what the record checked before freezing it is said beside it')
  assert.ok(rendered.includes(BRIEFING_STANDS), 'and it says the counted answer was not written over it')
  assert.ok(!rendered.includes(BRIEFING_IS_YOURS_TO_SEND), 'the press’s own note is not repeated under a standing briefing')
})

test('the press is offered with a collection in hand, and says that it sends nothing', async () => {
  store()
  const r = resource('mag-bpress')
  await r.read()
  const rendered = html(createElement(Summary, { resource: r, onPost: () => {} }))
  assert.ok(rendered.includes(WRITE_THE_BRIEFING), 'the press is offered')
  assert.ok(rendered.includes(BRIEFING_IS_YOURS_TO_SEND), 'and it says what it actually does')
  const empty = resource('mag-bpressempty', false)
  await empty.read()
  const nothing = html(createElement(Summary, { resource: empty, onPost: () => {} }))
  assert.ok(!nothing.includes(WRITE_THE_BRIEFING), 'nothing offers a briefing of an empty collection')
})

/* --- the floor is never written over a briefing ----------------------------- */

test('the counted answer is owed for a collection it has not answered, and never over a run’s briefing', () => {
  assert.equal(needsWrittenAnswer(null, BATCH), true, 'with no answer at all, the floor is owed')
  assert.equal(needsWrittenAnswer({ perspective: STANDING, current: synthesised('Counted.'), superseded: [], batch: BATCH }, BATCH),
    false, 'an answer already written from this collection is not written again')
  assert.equal(needsWrittenAnswer({ perspective: STANDING, current: synthesised('Counted.'), superseded: [], batch: 'adm-older1111111' }, BATCH),
    true, 'a counted answer from an earlier collection is')
  // THE POINT: `finalize` records no collection on a run's answer, so without
  // this a briefing would be written over by the counted floor on the next open.
  assert.equal(needsWrittenAnswer({ perspective: STANDING, current: byRun(), superseded: [], batch: null }, BATCH),
    false, 'a run’s briefing is never written over on its own')
})
