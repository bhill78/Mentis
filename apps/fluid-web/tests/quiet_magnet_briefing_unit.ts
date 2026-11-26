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
  BRIEFING_ASK, BRIEFING_BY_RUN, BRIEFING_IS_YOURS_TO_SEND, BRIEFING_STANDS, BRIEFING_UNREAD,
  NOT_ANSWERED_YET, WRITE_THE_BRIEFING,
  agentWritten, askForBriefing, frozenWords, heldAnswer, needsWrittenAnswer, readFrozenAnswer, withWords,
} from '../src/quiet2/magnets/Summary'
import { STANDING_QUESTION, answerText, perspectivesOf, type InquiryEvent } from '../src/quiet2/magnets/perspectives'
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
 *  writes are recorded rather than sent. */
function asking(r: MagnetResource, opts: { standing?: string | null } = {}) {
  const s = perspectivesOf(r), sent: unknown[][] = []
  let selected: string | null = null
  const standing = opts.standing === undefined ? STANDING : opts.standing
  s.get = async (tail = '') => {
    if (tail.startsWith('?')) return { magnet: r.saved.id, perspectives: [], selected, standing, next: null }
    const topic = tail.split('/')[1]
    if (tail.includes('/history')) return { magnet: r.saved.id, perspective: topic, events: [], next: null }
    return { magnet: r.saved.id, perspective: topic, selected, name: 'What this Magnet has gathered', retired: false,
      question: { ref: 'adm-revision222', digest, size: 40, media_type: 'application/json' },
      current_question: { text: BRIEFING_ASK, revision: 'adm-revision222' }, events: 3 }
  }
  s.write = async (tail: string, data: Record<string, unknown>, op?: string) => {
    sent.push([tail, data, op])
    if (tail === '') return { perspective: standing ?? STANDING }
    if (tail === '/selected') { selected = (data.perspective as string) ?? null; return { perspective: selected } }
    if (tail.endsWith('/question')) return { perspective: STANDING, question: { ref: 'adm-revision222' } }
    if (tail.endsWith('/prepare')) return { intent: 'ent-intent111111', perspective: STANDING, brain: binding.bound(),
      question: { ref: 'adm-revision222', digest, size: 40, media_type: 'application/json' },
      manifest: { ref: 'adm-manifest1111', digest, size: 10, media_type: 'application/json' },
      records: { ref: 'adm-records11111', digest, size: 10, media_type: 'application/json' },
      artifacts: [], parts: [], reach: 'work', request_op: 'perspective-request:ent-intent111111',
      text: BRIEFING_ASK, closure: { count: 2, bytes: 20 }, disclosure: '' }
    throw new Error(`unexpected write ${tail}`)
  }
  return { s, sent, selectedNow: () => selected }
}

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
    BRIEFING_STANDS, BRIEFING_UNREAD])
    assert.doesNotMatch(line, /retained|batch/i, `a line the owner reads says it: ${line}`)
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
  assert.deepEqual(sent[1][1], { text: BRIEFING_ASK })
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
