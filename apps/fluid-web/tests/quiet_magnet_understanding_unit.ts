/** Part E: a Summary that says something, and question-first Perspectives.
 *
 *  What these prove, against the owner's request (ent-3191baeb33d2 §7) and the
 *  plan's Part E done-when:
 *
 *  - a populated Summary conveys substantive written information -- what was
 *    collected, from where, over what span, how much text, which words recur,
 *    and the records' own opening words -- and not counts alone;
 *  - the four kinds of statement stay apart and labelled: collection facts, the
 *    records' own words, questions and hypotheses, and interpretations somebody
 *    recorded. Per-record support and contradiction is stated as unrecorded
 *    rather than mocked up;
 *  - nothing is fabricated: every written line is counted or quoted, the
 *    offered questions are questions, and no synthesis is claimed;
 *  - change is explained only against a valid comparable retained batch, and
 *    refused by name otherwise;
 *  - the whole collection can be discussed without picking a record;
 *  - the existing access gate is intact: the grounded affordance stays disabled
 *    with the server's own reason, and Summary reads nothing on its own;
 *  - Perspectives is question-first: the question box comes before every
 *    administrative control, naming is automatic, and drafts survive. */
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFileSync } from 'node:fs'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import type { MagnetConfig } from '../src/fluid/surface/magnet/types'
import Summary, {
  EXTRACTIVE_LABEL, GROUNDED_UNAVAILABLE, NO_COMPARISON, SUPPORT_UNRECORDED, WHOLE_COLLECTION_LABEL,
  askOrdinaryQuestion, capturedKeys, collectedExcerpts, collectedSpan, collectedText, collectionOverview,
  compareCollections, compareWithPrevious, comparisonWords, discussWholeCollection, exploreQuestion,
  frequentWords, itemIdentity, offeredQuestions, recordedChallenges, summaryFacts, summarySource,
} from '../src/quiet2/magnets/Summary'
import Perspectives, { DISCUSS_IS_ORDINARY } from '../src/quiet2/magnets/InquiryPanel'
import { createMagnetResource } from '../src/quiet2/magnets/state'
import { miniComposerDraft, saveMiniComposer } from '../src/quiet2/magnets/conversation'
import { forgetPanelDrafts, panelAt, panelDrafts, setQuestionDraft, setRenameDraft } from '../src/quiet2/magnets/panelDrafts'
import { derivedPerspectiveName, perspectivesOf, PERSPECTIVE_BLOCK_REASON } from '../src/quiet2/magnets/perspectives'
import { setOpen } from '../src/quiet2/magnets/places'
import { emptyDraft } from '../src/composer/draft'
import { page as binding } from '../src/brainBinding'

const SOURCE = 'ent-source111111', OTHER = 'ent-source222222'
const brainKey = 'origin|fixture|brain-e'
const digest = 'a'.repeat(64), digest2 = 'b'.repeat(64)
const summarySrc = () => readFileSync(new URL('../src/quiet2/magnets/Summary.tsx', import.meta.url), 'utf8')
const panelSrc = () => readFileSync(new URL('../src/quiet2/magnets/InquiryPanel.tsx', import.meta.url), 'utf8')
/** The code, without the comments that discuss what it must not do. */
const code = (source: string) => source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^[ \t]*\/\/.*$/gm, '')

const store = () => {
  const mem = new Map<string, string>()
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: {
    getItem: (k: string) => mem.get(k) ?? null, setItem: (k: string, v: string) => mem.set(k, v),
    removeItem: (k: string) => mem.delete(k), clear: () => mem.clear() } })
  binding.saw('brain-e@instance-one')
  forgetPanelDrafts()
  return mem
}

const config = (id: `mag-${string}`): MagnetConfig => ({ id,
  sources: [{ kind: 'conversation', conversation: SOURCE }, { kind: 'file', collection: 'col-held', path: 'nested/calibration.txt' }],
  selection: { informationTypes: ['post', 'file'], dates: {} },
  conversation: 'ent-own111111', collection: { mode: 'one-time' }, synthesis: { mode: 'manual' },
  notifications: { newItems: false, changes: false, failures: false }, presentation: { renderer: 'disc' } })

/** Captured text with words that actually recur, so a count is a real count. */
const post = (n: number, text: string, at: number, version = `ent-version${n}11111`) => ({
  kind: 'post', id: `ent-post${n}11111`, number: 10 + n, version, conversation: SOURCE, via: 'home', at,
  value: { parts: [{ type: 'text', text }] } })
const POSTS = [
  post(1, 'Calibration of the bench reference drifted by 37 microns this week. Calibration matters.', 1763900000),
  post(2, 'The bench reference was recalibrated. Calibration of the spare bench is still pending.', 1764000300),
]
const HELD = { kind: 'file', id: 'adm-file111111', version: 'adm-file111111', conversation: null, author: null, at: 1764000400, via: 'held-source',
  value: { ref: 'adm-file111111', digest, collection: 'col-held', path: 'nested/calibration.txt', text: 'Bench log', offset: 0, end: 9, size: 9,
    acquired_at: 1764000400, shortened: false, omitted_bytes: 0, next_offset: null, citation: `adm-file111111@${digest.slice(0, 12)}[0:9]` } }
const ACTIVATION = { post: 'ent-activation111', artifact: { ref: 'adm-batch111111', digest, size: 2048, media_type: 'application/json' }, at: 1764000500, state: 'recorded' }
const EARLIER = { post: 'ent-activation222', artifact: { ref: 'adm-batch222222', digest: digest2, size: 1024, media_type: 'application/json' }, at: 1763900500, state: 'recorded' }

const pageOf = (id: `mag-${string}`, posts: unknown[], held: unknown[] = [HELD]) => ({ sources: [
  { source: config(id).sources[0], key: `conversation:${SOURCE}`, status: 'ok', results: posts },
  { source: config(id).sources[1], key: 'file:col-held:nested/calibration.txt', status: 'ok', results: held },
] })

function resource(id: `mag-${string}`, body?: (c: MagnetConfig) => unknown) {
  const c = config(id)
  const asked: string[] = []
  const r = createMagnetResource({ id: `qm-${id}`, brainKey, saved: { id, name: 'Calibration inquiry', config: c },
    get: async (path) => { asked.push(path); return { status: 200, body: body ? body(c) : { magnet: id, config: c, activation: ACTIVATION, page: pageOf(id, POSTS) } } } })
  return { r, asked }
}
const empty = (c: MagnetConfig) => ({ magnet: c.id, config: c, activation: null, page: null })
const html = (node: Parameters<typeof renderToStaticMarkup>[0]) => renderToStaticMarkup(node)

/* --- the written overview --------------------------------------------------- */

test('the written overview says what was collected, from where, when and how much', async () => {
  store()
  const { r } = resource('mag-ewritten')
  await r.read()
  const lines = collectionOverview(r.saved, r.snapshot())
  const text = lines.join('\n')
  assert.ok(lines.length >= 4, 'the overview is written sentences, not a single count line')
  assert.ok(text.includes('2 collected posts and 1 collected file'), 'it says what it holds in ordinary words')
  assert.ok(text.includes(`Conversation ${SOURCE} (2)`) && text.includes('Held file col-held / nested/calibration.txt (1)'),
    'it says which sources the material came from, with what each gave')
  assert.match(text, /The collected material was written between .+ and .+\./, 'it states the span of the material itself')
  assert.match(text, /Its retained text runs to about \d+ words\./, 'it measures the text it holds')
  assert.ok(text.includes('bench (4)') && text.includes('calibration (3)'), 'recurring words are counted and named with their counts')
  assert.ok(/counted/i.test(text), 'the counts say they are counts')
})

test('nothing in the overview characterises, concludes or summarises the material', async () => {
  store()
  const { r } = resource('mag-ehonest')
  await r.read()
  const text = [...collectionOverview(r.saved, r.snapshot()), ...summaryFacts(r.saved, r.snapshot())].join('\n')
  assert.ok(!/\b(suggests|indicates|appears|concludes|shows that|overall|key (finding|theme)|in summary|therefore|we found)\b/i.test(text),
    'no derived claim about what the material means')
  assert.ok(!/\bthis collection is about\b/i.test(text))
  // The honest label is rendered beside the written lines, not merely exported.
  const rendered = html(createElement(Summary, { resource: r, onPost: () => {} }))
  assert.ok(rendered.includes(EXTRACTIVE_LABEL.slice(0, 40)), 'the view states that nothing read or summarised the collection')
  assert.ok(!code(summarySrc()).includes('synthes') || code(summarySrc()).includes('Synthesize from evidence'),
    'the only synthesis word in the code is the disabled affordance')
})

test('the counted words are counted over captured text only, skipping references and common words', async () => {
  store()
  const { r } = resource('mag-ecount')
  await r.read()
  const all = collectedText(r.snapshot().results)
  assert.ok(all.includes('Calibration of the bench reference drifted') && all.includes('Bench log'),
    'posts and held files are both counted')
  const words = frequentWords(r.snapshot().results, 10)
  assert.ok(words.every((w) => w.count > 1), 'a word used once is not offered as recurring')
  assert.ok(!words.some((w) => /^(the|this|was|were|still)$/.test(w.word)), 'common words carry no subject and are skipped')
  assert.ok(!words.some((w) => /^(ent|adm|mag)-/.test(w.word)), 'references are identity, not subject')
  assert.deepEqual(words.slice(0, 3), [{ word: 'bench', count: 4 }, { word: 'calibration', count: 3 }, { word: 'reference', count: 2 }])
  const span = collectedSpan(r.snapshot().results)!
  assert.equal(span.first, 1763900000)
  assert.equal(span.last, 1764000400)
  assert.equal(collectedSpan([]), null)
})

/* --- the records' own words ------------------------------------------------- */

test('excerpts are the records’ own words, with provenance, and open the record', async () => {
  store()
  const { r } = resource('mag-equote')
  await r.read()
  const excerpts = collectedExcerpts(r.snapshot().results)
  assert.equal(excerpts.length, 3)
  assert.ok(excerpts[0].text.startsWith('Calibration of the bench reference drifted by 37 microns'),
    'the excerpt is the captured characters, not a paraphrase')
  assert.equal(excerpts[0].origin, `Conversation ${SOURCE}`)
  assert.equal(excerpts[2].origin, 'Held file col-held / nested/calibration.txt')
  assert.ok(excerpts.every((e) => !!e.title), 'each excerpt names the record it came from')
  const rendered = html(createElement(Summary, { resource: r, onPost: () => {} }))
  assert.ok(rendered.includes('In the records’ own words'))
  assert.ok(rendered.includes('id="excerpt-ent-post111111"'), 'each quote is the control that opens its record')
  assert.ok(rendered.includes('Quoted exactly as collected'))
})

test('the Summary entry in the universal index searches the written overview and the quoted words', async () => {
  store()
  const { r } = resource('mag-eindex')
  await r.read()
  const entries = summarySource(r).entries()
  assert.equal(entries.length, 1)
  assert.equal(entries[0].kind, 'Summary')
  assert.ok(entries[0].text.includes('2 collected posts'), 'the written overview is searchable')
  assert.ok(entries[0].text.includes('recalibrated'), 'the collected words are searchable')
  assert.ok(entries[0].text.includes('2 configured sources'), 'the facts are still searchable')
  assert.equal(summarySource(r).complete, undefined, 'the batch is in hand, so nothing is owed')
})

/* --- questions, interpretations, support ------------------------------------ */

test('offered questions are questions, built from what was counted, and claim nothing', async () => {
  store()
  const { r } = resource('mag-eask')
  await r.read()
  const questions = offeredQuestions(r.snapshot())
  assert.ok(questions.length >= 3)
  assert.ok(questions.every((q) => q.trim().endsWith('?')), 'every offered line is a question')
  assert.ok(questions.some((q) => q.includes('bench')), 'a counted word becomes something to ask about')
  assert.ok(questions.some((q) => q.includes(`Conversation ${SOURCE}`)), 'a collected source becomes something to ask about')
  assert.ok(!questions.some((q) => /\b(suggests|indicates|shows|proves|because the data)\b/i.test(q)),
    'none of them asserts anything about the material')
  assert.ok(offeredQuestions(r.snapshot(), true).some((q) => /previous one/.test(q)),
    'an earlier comparable batch makes a comparison question askable')
  const rendered = html(createElement(Summary, { resource: r, onPost: () => {} }))
  assert.ok(rendered.includes('Questions you could explore'))
  assert.ok(rendered.includes('Questions, not findings'), 'the block says what kind of statement it holds')
})

test('an offered question becomes a Perspective draft, and no other draft is touched', async () => {
  store()
  const { r } = resource('mag-eexplore')
  await r.read()
  const at = panelAt(r)
  setRenameDraft(at, 'ent-topicA11111', 'An unsaved name')
  saveMiniComposer(r, { ...emptyDraft(), text: 'unsent message' })
  exploreQuestion(r, 'What do the collected records say about bench?')
  assert.equal(panelDrafts(at).question, 'What do the collected records say about bench?')
  assert.equal(r.snapshot().tab, 'Perspectives', 'the owner is taken to where one press creates it')
  assert.equal(panelDrafts(at).renames['ent-topicA11111'], 'An unsaved name', 'another slot is untouched')
  assert.equal(miniComposerDraft(r).text, 'unsent message', 'the message draft is untouched')
  // And it survives a reload, like every other panel draft.
  forgetPanelDrafts()
  assert.equal(panelDrafts(at).question, 'What do the collected records say about bench?')
})

test('recorded questions and interpretations are shown apart, attributed and versioned, and read only when asked', async () => {
  store()
  const { r } = resource('mag-erecorded')
  await r.read()
  const shut = html(createElement(Summary, { resource: r, onPost: () => {} }))
  assert.ok(shut.includes('Questions and interpretations already recorded'))
  assert.ok(shut.includes('Show recorded questions'), 'nothing is read from the record until the owner asks')
  assert.ok(shut.includes('Nothing is read from the record until you ask for it.'))
  const inquiries = perspectivesOf(r)
  inquiries.update({
    rows: [{ perspective: 'ent-topicA11111', name: 'Does the bench drift?', retired: false, question: null,
      current_question: { text: 'Does the bench drift between batches?', revision: 'adm-revision111' }, events: 3 }],
    events: [
      { seq: 1, post: 'ent-event111111', event: 'created', perspective: 'ent-topicA11111', snapshot: { ref: 'adm-revision111', digest, size: 10, media_type: 'application/json' }, data: { text: 'Does the bench drift between batches?' } },
      { seq: 2, post: 'ent-event222222', event: 'challenged', perspective: 'ent-topicA11111', snapshot: { ref: 'adm-revision222', digest, size: 10, media_type: 'application/json' }, data: { text: 'The spare bench was never in scope.' } },
    ],
  })
  const open = html(createElement(Summary, { resource: r, onPost: () => {} }))
  assert.ok(open.includes('Does the bench drift between batches?'), 'the recorded question is shown in its own words')
  assert.ok(open.includes('revision adm-revision111'), 'it is versioned')
  assert.ok(open.includes('ent-topicA11111'), 'it is attributed to its own record')
  assert.ok(open.includes('Recorded challenges') && open.includes('The spare bench was never in scope.'),
    'a recorded contradiction is shown as a challenge, not as a finding')
  assert.ok(open.includes(SUPPORT_UNRECORDED), 'per-record support and contradiction is stated unrecorded, not mocked up')
  assert.equal(recordedChallenges(inquiries.snapshot().events).length, 1)
  assert.equal(recordedChallenges(inquiries.snapshot().events)[0].post, 'ent-event222222')
})

/* --- change, only where comparable ----------------------------------------- */

test('compareCollections reports new, changed, gone and unchanged between two comparable batches', () => {
  const previous = [...POSTS.slice(0, 1).map((p) => ({ ...p, capturedSourceKey: `conversation:${SOURCE}` })),
    { ...HELD, capturedSourceKey: 'file:col-held:nested/calibration.txt' }]
  const current = [...POSTS.map((p) => ({ ...p, capturedSourceKey: `conversation:${SOURCE}` })),
    { ...HELD, value: { ...HELD.value, text: 'Bench log v2', end: 12, size: 12, digest: digest2 }, capturedSourceKey: 'file:col-held:nested/calibration.txt' }]
  const c = compareCollections(current as never, previous as never)
  assert.equal(c.comparable, true)
  assert.equal(c.added.length, 1, 'the second post is new')
  assert.equal(c.added[0].id, 'ent-post211111')
  assert.equal(c.changed, 1, 'the held file was recaptured with different bytes')
  assert.equal(c.gone, 0)
  assert.equal(c.unchanged, 1)
  assert.match(comparisonWords(c), /^Compared with the previous collection: 1 new record, 1 changed since then; 1 unchanged\.$/)
  // A record that is no longer collected is counted as gone, not as changed --
  // and only while both batches still captured the same sources.
  const shrunk = compareCollections(previous as never, current as never)
  assert.equal(shrunk.comparable, true)
  assert.equal(shrunk.gone, 1, 'the post that is no longer collected is gone')
  assert.equal(shrunk.added.length, 0)
  assert.equal(shrunk.changed, 1)
  // And identical batches say so without claiming a change.
  const same = compareCollections(previous as never, previous as never)
  assert.match(comparisonWords(same), /^Nothing changed between the previous collection and this one/)
  assert.equal(itemIdentity(previous[0] as never).id, 'post:ent-post111111')
  assert.equal(itemIdentity(previous[1] as never).id, 'file:col-held:nested/calibration.txt')
})

test('two batches that captured different sources are refused as not comparable', () => {
  const here = [{ ...POSTS[0], capturedSourceKey: `conversation:${SOURCE}` }]
  const there = [{ ...POSTS[0], capturedSourceKey: `conversation:${OTHER}` }]
  const c = compareCollections(here as never, there as never)
  assert.equal(c.comparable, false)
  assert.match(c.reason!, /captured different sources, so they are not comparable/)
  assert.match(c.reason!, /Nothing is claimed about what changed/)
  assert.equal(c.added.length, 0)
  assert.equal(c.changed, 0)
  assert.equal(c.gone, 0)
  assert.equal(comparisonWords(c), c.reason)
  assert.deepEqual(capturedKeys(here as never), [`conversation:${SOURCE}`])
})

test('with no comparison made the Summary says so, and claims no change anywhere', async () => {
  store()
  const { r } = resource('mag-enochange')
  await r.read()
  const rendered = html(createElement(Summary, { resource: r, onPost: () => {} }))
  assert.ok(rendered.includes('What changed'))
  assert.ok(rendered.includes(NO_COMPARISON), 'the default state is an explicit no-comparison statement')
  assert.ok(rendered.includes('Compare with the previous collection'), 'comparing is something the owner asks for')
  assert.ok(!summaryFacts(r.saved, r.snapshot()).some((l) => /change/i.test(l)), 'no fact line claims a change')
})

test('comparing reads the earlier retained batch only, never a live source, and only when asked', async () => {
  store()
  const { r, asked } = resource('mag-ecompare')
  await r.read()
  const calls: string[] = []
  const previous = (globalThis as { fetch?: unknown }).fetch
  const answers: Record<string, unknown> = {
    history: { magnet: 'mag-ecompare', batches: [ACTIVATION, EARLIER], next: null },
    earlier: { magnet: 'mag-ecompare', config: config('mag-ecompare'), activation: EARLIER,
      page: pageOf('mag-ecompare', POSTS.slice(0, 1)) },
  }
  Object.defineProperty(globalThis, 'fetch', { configurable: true, writable: true, value: async (input: unknown) => {
    const url = String(input); calls.push(url)
    const body = url.includes('/collection/history') ? answers.history : answers.earlier
    return { ok: true, status: 200, json: async () => body }
  } })
  try {
    // Rendering alone asks nothing: the comparison is a press.
    html(createElement(Summary, { resource: r, onPost: () => {} }))
    assert.deepEqual(calls, [], 'Summary fetches nothing while it renders')
    const got = await compareWithPrevious(r)
    assert.ok(!('bound' in got))
    assert.equal((got as { comparable: boolean }).comparable, true)
    assert.match((got as { words: string }).words, /1 new record/)
    assert.equal(calls.length, 2, 'one history read and one retained batch read')
    assert.ok(calls[0].includes('/fluid/api/magnets/mag-ecompare/collection/history?limit=20'))
    assert.ok(calls[1].includes(`batch=${encodeURIComponent(EARLIER.artifact.ref)}`) && calls[1].includes(`digest=${digest2}`),
      'the earlier batch is asked for by its own reference and digest')
    assert.ok(!calls.some((u) => /\/read(\?|$)/.test(u)), 'the live-source route is never called')
    assert.deepEqual(asked, ['/fluid/api/magnets/mag-ecompare/collection'], 'the card still made exactly one collection read')
    assert.ok(!code(summarySrc()).includes('/read'), 'the live-source route is not named in this view')
    // A substituted or mismatched batch is refused rather than compared.
    answers.earlier = { magnet: 'mag-ecompare', config: config('mag-ecompare'), activation: ACTIVATION, page: pageOf('mag-ecompare', POSTS) }
    await assert.rejects(compareWithPrevious(r), /did not return the batch that was asked for/)
    // An answer for another Magnet is refused.
    answers.history = { magnet: 'mag-other', batches: [] }
    await assert.rejects(compareWithPrevious(r), /another Magnet/)
    // The first retained batch has nothing before it, and says so.
    answers.history = { magnet: 'mag-ecompare', batches: [ACTIVATION], next: null }
    assert.deepEqual(await compareWithPrevious(r), { bound: 'No earlier collection to compare with: this is the first retained batch.' })
  } finally {
    if (previous) Object.defineProperty(globalThis, 'fetch', { configurable: true, writable: true, value: previous })
  }
})

/* --- discussing the whole collection ---------------------------------------- */

test('the whole collection can be discussed without picking a record', async () => {
  store()
  const { r } = resource('mag-ewhole')
  await r.read()
  r.update({ contextSuppressed: true })
  assert.equal(discussWholeCollection(r), true)
  const context = r.snapshot().context!
  assert.equal(context.ref, ACTIVATION.artifact.ref, 'the batch itself is the reference')
  assert.equal(context.kind, 'batch')
  assert.equal(context.label, WHOLE_COLLECTION_LABEL)
  assert.equal(context.text, undefined, 'captured content never enters the attached context')
  assert.equal(r.snapshot().contextSuppressed, false, 'an explicit discuss clears suppression')
  assert.equal(r.snapshot().assistanceMode, 'retained', 'the message is to be answered from the retained collection')
  assert.equal(r.snapshot().tab, 'Conversation')
  assert.equal(r.snapshot().places.Summary.inspected, null, 'no individual record was selected to do it')
  const rendered = html(createElement(Summary, { resource: r, onPost: () => {} }))
  assert.ok(rendered.includes('Discuss this whole collection'))
})

test('with nothing collected there is nothing to discuss as a collection', async () => {
  store()
  const { r } = resource('mag-ewholeempty', empty)
  await r.read()
  assert.equal(discussWholeCollection(r), false)
  assert.equal(r.snapshot().context, null)
  assert.equal(r.snapshot().assistanceMode, undefined, 'the retained reading choice is not set with nothing retained')
})

/* --- the empty collection --------------------------------------------------- */

test('an empty Summary offers a useful start and ordinary help, and keeps the owner’s own words', async () => {
  store()
  const { r } = resource('mag-eempty', empty)
  await r.read()
  const rendered = html(createElement(Summary, { resource: r, onPost: () => {} }))
  assert.ok(rendered.includes('No collected information yet. Conversation is still available.'))
  assert.ok(rendered.includes('Opening never collects'))
  assert.ok(rendered.includes('A place to start'))
  assert.ok(rendered.includes('How do I configure this Magnet?'), 'ordinary configuration help is offered first')
  assert.ok(rendered.includes('Ordinary help works before anything is collected.'))
  assert.ok(rendered.includes('Synthesize from evidence') && rendered.includes(PERSPECTIVE_BLOCK_REASON),
    'the honest grounding statement stays on an empty collection')
  // A starter question becomes an ordinary message.
  assert.equal(askOrdinaryQuestion(r, 'How do I configure this Magnet?'), '')
  assert.equal(miniComposerDraft(r).text, 'How do I configure this Magnet?')
  assert.equal(r.snapshot().tab, 'Conversation')
  // And it never overwrites words the owner has already typed.
  saveMiniComposer(r, { ...miniComposerDraft(r), text: 'Words of my own' })
  assert.match(askOrdinaryQuestion(r, 'What should I collect first for this idea?'), /already holds words of yours/)
  assert.equal(miniComposerDraft(r).text, 'Words of my own')
  assert.deepEqual(offeredQuestions(r.snapshot()).filter((q) => q.endsWith('?')).length, 3)
})

test('before the one retained read answers, Summary claims nothing about the collection', () => {
  store()
  const { r } = resource('mag-eunread')            // deliberately not read
  const rendered = html(createElement(Summary, { resource: r, onPost: () => {} }))
  assert.ok(rendered.includes('not read yet'), 'the badge says so')
  assert.ok(rendered.includes('This collection has not been read yet.'))
  for (const absent of ['In the records’ own words', 'What changed', 'Questions you could explore',
    'Discuss this whole collection', EXTRACTIVE_LABEL]) {
    assert.ok(!rendered.includes(absent), `${absent.slice(0, 32)} is not offered before anything was read`)
  }
  assert.deepEqual(collectionOverview(r.saved, r.snapshot()), [], 'there is nothing written to say yet')
  assert.ok(rendered.includes(GROUNDED_UNAVAILABLE), 'the gate still states itself')
})

/* --- the access gate -------------------------------------------------------- */

test('the existing access gate is untouched: grounded answering stays disabled with the server’s reason', async () => {
  store()
  const { r } = resource('mag-egate')
  await r.read()
  const rendered = html(createElement(Summary, { resource: r, onPost: () => {} }))
  assert.match(rendered, /<button[^>]*disabled[^>]*aria-describedby="grounded-status"/)
  assert.ok(rendered.includes('Synthesize from evidence'))
  assert.ok(rendered.includes(PERSPECTIVE_BLOCK_REASON), 'the reason is the server-side gate’s own words')
  assert.equal(GROUNDED_UNAVAILABLE, `Unavailable · ${PERSPECTIVE_BLOCK_REASON}`)
  assert.ok(rendered.includes('Sample records · not agent analysis or synthesis.'))
  // Nothing here claims the collection was read by an agent.
  assert.ok(!/\bgrounded (answer|synthesis) (is )?(available|delivered|working)\b/i.test(rendered))
})

/* --- question-first Perspectives -------------------------------------------- */

test('the Perspectives panel puts the question before every administrative control', () => {
  store()
  const { r } = resource('mag-equestionfirst')
  const rendered = html(createElement(Perspectives, { resource: r, canWrite: true, onEvidence: () => {} }))
  const ask = rendered.indexOf('New question or hypothesis')
  const create = rendered.indexOf('Create and select Perspective')
  const lens = rendered.indexOf('aria-label="Active Perspective"')
  const history = rendered.indexOf('Wording history')
  assert.ok(ask > 0 && create > ask, 'the question box and its one press come first, in that order')
  assert.ok(lens > create, 'switching between questions comes after asking one')
  assert.ok(history > lens, 'the recorded wording history is last')
  assert.ok(rendered.indexOf('Ask a question') < lens, 'the panel leads with asking')
  assert.ok(!rendered.includes('aria-label="Perspective name"'), 'creation asks for no name')
  assert.ok(rendered.includes('Its name is taken from the question when you create it.'))
  assert.ok(rendered.includes(DISCUSS_IS_ORDINARY), 'what discussing does, and does not, read is said where it is offered')
  assert.ok(rendered.includes(PERSPECTIVE_BLOCK_REASON), 'the gate keeps its own reason here too')
  // Renaming, revising and retiring are still reachable, just not first.
  const panel = code(panelSrc())
  for (const kept of ["act('rename'", "act('question'", "act('challenge'", "act('branch'", "'resume' : 'retire'"])
    assert.ok(panel.includes(kept), `nothing was removed to make room (${kept})`)
})

test('a question typed into the Summary arrives in the Perspectives box ready to create', () => {
  store()
  const { r } = resource('mag-earrives')
  setOpen(r, true)
  exploreQuestion(r, 'Where do the collected sources disagree with each other?')
  const rendered = html(createElement(Perspectives, { resource: r, canWrite: true, onEvidence: () => {} }))
  assert.ok(rendered.includes('Where do the collected sources disagree with each other?'), 'the draft question is in the box')
  assert.ok(rendered.includes('It will be listed as'), 'its name is already derived, with nothing to fill in')
  const derived = derivedPerspectiveName('Where do the collected sources disagree with each other?')
  assert.ok(derived.endsWith('…') && Array.from(derived).length === 50, 'the derived name keeps the approved bound')
  assert.ok(rendered.includes(derived), 'the derived name is shown, and no name field is asked for')
  assert.ok(!rendered.includes('aria-label="Perspective name"'))
  // The question draft is not sent anywhere by rendering it.
  assert.equal(perspectivesOf(r).snapshot().pending, undefined)
  setQuestionDraft(panelAt(r), '')
})
