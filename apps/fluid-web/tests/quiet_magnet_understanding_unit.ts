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
 *  - PART F: a question asked in the panel gets a real persisted answer, the
 *    Summary's lead is that answer rather than word counts, what changed is the
 *    difference between the current answer and the one it superseded, asking
 *    again supersedes rather than overwrites, and every answer states what it
 *    was grounded in -- grounded-in-the-collection and explored-outside being
 *    rendered as different things from Part A's own `explored_outside`;
 *  - the placeholders that said none of this worked are gone, and nothing in
 *    the interface claims a grounding it does not have (#521 section 7);
 *  - Perspectives is question-first: the question box comes before every
 *    administrative control, naming is automatic, drafts survive, and every
 *    control the owner reads uses question rather than inquiry wording
 *    (ent-3191baeb33d2 §2). */
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFileSync } from 'node:fs'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import type { MagnetConfig } from '../src/fluid/surface/magnet/types'
import Summary, {
  ANSWER_THIS_COLLECTION, EXTRACTIVE_LABEL, Grounded, HOW_THIS_WAS_MADE,
  NOT_ANSWERED_YET, NO_COMPARISON, SUMMARY_IS_A_QUESTION,
  askOrdinaryQuestion, capturedKeys, collectedExcerpts, collectedSpan, collectedText, collectionOverview,
  compareCollections, compareWithPrevious, comparisonWords, exploreQuestion,
  frequentWords, itemIdentity, offeredQuestions, recordedChallenges, startingAction, summaryFacts, summarySource,
} from '../src/quiet2/magnets/Summary'
import Perspectives, {
  ABOUT_THIS_ANSWER, ANSWER_WRITTEN_BY, AnswerGrounding, DISCUSSION_READS, PastQuestions, READ_AGAIN,
  SupportingItems, TAKE_TO_CONVERSATION, discussSelectedQuestion, tryAsking,
} from '../src/quiet2/magnets/InquiryPanel'
import { createMagnetResource } from '../src/quiet2/magnets/state'
import { miniComposerDraft, saveMiniComposer } from '../src/quiet2/magnets/conversation'
import { forgetPanelDrafts, panelAt, panelDrafts, setQuestionDraft, setRenameDraft } from '../src/quiet2/magnets/panelDrafts'
import type { MagnetContext, MagnetResource } from '../src/quiet2/magnets/contract'
import {
  answerDiff, answerText, changeWords, derivedPerspectiveName, grounding, perspectivesOf, provenanceOf,
  questionVersion, showPerspectiveContext, stampAttachedQuestion, statements,
  ALLOWED_OUTSIDE_UNUSED, EXPLORED_OUTSIDE, GROUNDED_IN_COLLECTION, NOTHING_RECORDED_YET,
  PERSPECTIVE_DISCLOSURE, SUPPORTING_WHY, UNSTATED_PROVENANCE,
  type AnswerProvenance, type InquiryEvent, type Perspective,
} from '../src/quiet2/magnets/perspectives'
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
  // WHERE IT CAME FROM, WITHOUT AN IDENTITY (owner request ent-1e82a8786c37).
  // The written overview is what a reader sees first, so it says which KINDS of
  // source the material came from and how many of each, and carries no
  // Conversation entry id or collection key. What each source gave is still
  // stated per source -- one press away, in the facts disclosure below, which
  // is where the owner kept provenance.
  assert.ok(text.includes('They came from 1 Conversation and 1 held file.'),
    `it says which kinds of source the material came from, and how many: ${text}`)
  for (const line of lines) assert.doesNotMatch(line, /(?:ent|adm|col|mag)-[0-9a-z]{4,}/,
    `the written overview carries no recorded identifier: ${line}`)
  assert.ok(summaryFacts(r.saved, r.snapshot()).join(' | ').includes(`Conversation ${SOURCE} (2 collected items)`),
    'and the per-source breakdown is still stated on demand')
  // Not "written": `collectedSpan` reads each row's own `at`, which for an
  // acquired row is when this Magnet fetched it, not when its material was
  // written (Part 5 review ent-e3c43663010a).
  assert.match(text, /The collected material was collected between .+ and .+\./, 'it states the span of collection, not of writing')
  assert.match(text, /Its collected text runs to about \d+ words\./, 'it measures the text it holds')
  // THE COUNTED WORDS ARE A FACT, SAID WHERE THE FACTS ARE (plan Part 5). They
  // were a sentence of the written overview, so "Most used words, counted: …"
  // was part of what a reader met before anything the material says -- the
  // "collection statistics presented as the primary content" the owner asked to
  // be demoted (#1017 ent-599e68de0893). The same counted line, unchanged, is
  // now stated in the facts; the overview holds no word count at all.
  const facts = summaryFacts(r.saved, r.snapshot()).join(' | ')
  assert.ok(facts.includes('bench (4)') && facts.includes('calibration (3)'),
    `recurring words are counted and named with their counts, in the facts: ${facts}`)
  assert.ok(/Most used words, counted/.test(facts), 'and they say they are counts')
  assert.doesNotMatch(text, /Most used words|counted:/,
    `the written overview no longer counts words at a reader: ${text}`)
})

test('nothing in the overview characterises, concludes or summarises the material', async () => {
  store()
  const { r } = resource('mag-ehonest')
  await r.read()
  const text = [...collectionOverview(r.saved, r.snapshot()), ...summaryFacts(r.saved, r.snapshot())].join('\n')
  assert.ok(!/\b(suggests|indicates|appears|concludes|shows that|overall|key (finding|theme)|in summary|therefore|we found)\b/i.test(text),
    'no derived claim about what the material means')
  assert.ok(!/\bthis collection is about\b/i.test(text))
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
  // THE EXCERPT'S ORIGIN IS CLEAN (owner request ent-1e82a8786c37): it says what
  // kind of record the words came from, and a held file's name, and carries no
  // Conversation entry id or collection key. The exact captured key stays in the
  // inspection's provenance disclosure, which `evidenceOrigin` still states.
  assert.equal(excerpts[0].origin, 'Collected post')
  assert.equal(excerpts[2].origin, 'Held file · nested/calibration.txt')
  for (const e of excerpts) assert.ok(!/ent-[a-z0-9]{6,}|col-[a-z0-9]{6,}/.test(e.origin), `no raw identifier in "${e.origin}"`)
  assert.ok(excerpts.every((e) => !!e.title), 'each excerpt names the record it came from')
  const rendered = html(createElement(Summary, { resource: r, onPost: () => {} }))
  assert.ok(rendered.includes('In the records’ own words'))
  assert.ok(rendered.includes('id="excerpt-ent-post111111"'), 'each quote is the control that opens its record')
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
  assert.ok(questions.some((q) => /collected from each source|material this source collected/.test(q)),
    'a collected source becomes something to ask about')
  for (const q of questions) assert.doesNotMatch(q, /(?:ent|adm|col|mag)-[0-9a-z]{4,}/,
    `an offered question carries no recorded identifier: ${q}`)
  assert.ok(!questions.some((q) => /\b(suggests|indicates|shows|proves|because the data)\b/i.test(q)),
    'none of them asserts anything about the material')
  assert.ok(offeredQuestions(r.snapshot(), true).some((q) => /previous one/.test(q)),
    'an earlier comparable batch makes a comparison question askable')
  const rendered = html(createElement(Summary, { resource: r, onPost: () => {} }))
  assert.ok(rendered.includes('Questions to explore'))
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
  assert.ok(!open.includes('Evidence links'), 'no per-record support or contradiction is mocked up as available')
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
    assert.equal(calls.length, 0, 'Summary fetches nothing while it renders')
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
    await assert.rejects(compareWithPrevious(r), /did not return the collection that was asked for/)
    // An answer for another Magnet is refused.
    answers.history = { magnet: 'mag-other', batches: [] }
    await assert.rejects(compareWithPrevious(r), /another Magnet/)
    // The first collection has nothing before it, and says so.
    answers.history = { magnet: 'mag-ecompare', batches: [ACTIVATION], next: null }
    assert.deepEqual(await compareWithPrevious(r), { bound: 'No earlier collection to compare with: this is the first one.' })
  } finally {
    if (previous) Object.defineProperty(globalThis, 'fetch', { configurable: true, writable: true, value: previous })
  }
})

/* --- no control offers answering from the collected records ------------------
   THE INVARIANT (revised boundary contract adm-c5c73679ac1e §§2-3): no control
   offers or triggers retained-content agent answering while configured-source
   enforcement is unverified. Summary's own whole-collection press used to break
   it twice over -- it attached the retained batch as the message's reference and
   set the Composer's reading choice to `retained`, which is exactly what makes
   the adapter take the retained-content path. Both are gone, and these check
   that no other press here re-creates either half. */

test('the Summary offers one press that answers from the collected records, and attaches nothing', async () => {
  store()
  const { r } = resource('mag-ewhole')
  await r.read()
  const rendered = html(createElement(Summary, { resource: r, onPost: () => {} }))
  assert.ok(rendered.includes(ANSWER_THIS_COLLECTION), 'the press that writes the answer is offered')
  for (const gone of ['Draft an answer from selected records', 'aria-describedby="grounded-status"',
    'is unavailable until configured-source']) {
    assert.ok(!rendered.includes(gone), `${gone} is gone`)
  }
  // No press in this view reaches the reading choice or attaches a reference.
  const src = code(summarySrc())
  assert.ok(!src.includes('assistanceMode'), 'Summary never sets what the Composer reads')
  assert.ok(!src.includes('discussEvidence'), 'Summary attaches no reference to the next message')
  assert.ok(!/kind: *'batch'/.test(src), 'and never makes the retained batch into one')
  // Everything the view can still do leaves both untouched.
  exploreQuestion(r, 'What do the collected records say about bench?')
  assert.equal(r.snapshot().assistanceMode, undefined, 'exploring a question chooses no reading mode')
  assert.equal(r.snapshot().context, null, 'and attaches nothing')
  assert.deepEqual(await compareWithPrevious(r).catch(() => ({ bound: 'refused' })), { bound: 'refused' })
  assert.equal(r.snapshot().assistanceMode, undefined, 'nor does comparing two retained batches')
  assert.equal(r.snapshot().context, null)
})

test('the ordinary source-free route is still there, and carries no collection', async () => {
  store()
  const { r } = resource('mag-ewholeempty', empty)
  await r.read()
  assert.equal(askOrdinaryQuestion(r, 'How do I configure this Magnet?'), '')
  assert.equal(miniComposerDraft(r).text, 'How do I configure this Magnet?', 'the words are the owner’s own')
  assert.equal(r.snapshot().tab, 'Conversation')
  assert.equal(r.snapshot().assistanceMode, undefined, 'an ordinary question stays ordinary')
  assert.equal(r.snapshot().context, null, 'with nothing attached to it')
  const rendered = html(createElement(Summary, { resource: r, onPost: () => {} }))
  assert.ok(!rendered.includes(ANSWER_THIS_COLLECTION), 'with nothing collected there is nothing to answer from')
  assert.ok(rendered.includes('Start a conversation'), 'the ordinary route is still offered')
})

/* --- the empty collection --------------------------------------------------- */

test('an empty Summary offers a useful start and ordinary help, and keeps the owner’s own words', async () => {
  store()
  const { r } = resource('mag-eempty', empty)
  await r.read()
  const rendered = html(createElement(Summary, { resource: r, onPost: () => {} }))
  assert.ok(rendered.includes('No collected information yet.'))
  // THE USEFUL ACTION IS A BUTTON, NOT A SENTENCE (owner ent-a24ec84c8176:
  // "Present current information and useful actions prominently"). What the
  // sentence "Choose sources in Settings, then collect." described is the press
  // itself, with the note `startingAction` states beside it.
  const start = startingAction(r.saved)
  assert.ok(rendered.includes(`<button type="button" class="mgd-button">${start.label}</button>`),
    'the useful action is a button on the surface')
  assert.ok(rendered.includes(start.note), 'with its own note beside it')
  assert.ok(rendered.includes('Start a conversation'))
  assert.ok(rendered.includes('How do I configure this Magnet?'), 'ordinary configuration help is offered first')
  assert.ok(!rendered.includes(ANSWER_THIS_COLLECTION) && !rendered.includes('Draft an answer from selected records'),
    'with nothing collected there is nothing to answer from, and no press claims otherwise')
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
    ANSWER_THIS_COLLECTION, EXTRACTIVE_LABEL, SUMMARY_IS_A_QUESTION]) {
    assert.ok(!rendered.includes(absent), `${absent.slice(0, 32)} is not offered before anything was read`)
  }
  assert.deepEqual(collectionOverview(r.saved, r.snapshot()), [], 'there is nothing written to say yet')
})

/* --- the access gate -------------------------------------------------------- */

test('the gate is open and nothing claims a grounding it does not have', async () => {
  store()
  const { r } = resource('mag-egate')
  await r.read()
  const rendered = html(createElement(Summary, { resource: r, onPost: () => {} }))
  // The placeholders that mirrored the shut gate are deleted, not flipped.
  for (const file of ['../src/quiet2/magnets/perspectives.ts', '../src/quiet2/magnets/Summary.tsx',
    '../src/quiet2/magnets/InquiryPanel.tsx']) {
    const source = readFileSync(new URL(file, import.meta.url), 'utf8')
    for (const gone of ['export const PERSPECTIVE_ANSWERS_ENABLED', 'export const PERSPECTIVE_BLOCK_REASON',
      'export const FUTURE_CONCEPT', 'export const GROUNDED_NOT_YET', 'export const GROUNDED_UNAVAILABLE',
      'export const COLLECTION_NOT_ANSWERABLE', 'export const TRY_ASKING'])
      assert.ok(!source.includes(gone), `${gone} is deleted (${file})`)
  }
  // And no sentence anywhere here says answering does not work.
  for (const source of [code(summarySrc()), code(panelSrc())])
    assert.doesNotMatch(source, /not available yet|unavailable until|do not enforce/,
      'no sentence says answering from the collection does not work')
  // With no answer recorded the lead is the counted line, and it SAYS it is
  // counted rather than letting a measurement read as an answer.
  assert.ok(rendered.includes(NOT_ANSWERED_YET), 'and says which of the two it is showing')
  assert.ok(!rendered.includes(SUMMARY_IS_A_QUESTION), 'the answer block is absent when there is no answer')
})

/* --- what an answer says it was grounded in (Part A's own field names) ------ */

const provenance = (over: Partial<AnswerProvenance> = {}): AnswerProvenance =>
  ({ grounded_in: 'collection', outside_authorized: [], outside_reads: [], explored_outside: false, ...over })
const answerEvent = (text: string, over: Record<string, unknown> = {}): InquiryEvent => ({
  seq: 1, post: `ent-answer${text.length}1111`, event: 'answered', perspective: 'ent-topicA11111',
  snapshot: { ref: 'adm-answer111111', digest, size: 10, media_type: 'application/json' },
  data: { text, answer: { ref: 'adm-recorded11111' }, provenance: provenance(), ...over } })

test('grounded in this collection and explored outside it are rendered as different things', () => {
  // THE THREE STATEMENTS, never blended, from `explored_outside` and nothing else.
  assert.equal(grounding(provenance()).label, GROUNDED_IN_COLLECTION)
  assert.equal(grounding(provenance()).outside, false)
  const allowed = grounding(provenance({ outside_authorized: [{ kind: 'runtime-web-search' }] }))
  assert.equal(allowed.label, ALLOWED_OUTSIDE_UNUSED, 'opened but not reached is its own statement')
  assert.equal(allowed.outside, false)
  const went = grounding(provenance({ explored_outside: true,
    outside_authorized: [{ kind: 'runtime-web-search' }],
    outside_reads: [{ what: 'runtime-web-search', collection: 'the runtime own web search' }] }))
  assert.equal(went.label, EXPLORED_OUTSIDE)
  assert.equal(went.outside, true, 'and it is marked as a different kind of answer')
  assert.deepEqual(went.reached, ['runtime-web-search · the runtime own web search'])
  // An answer that records no provenance is not shown as grounded.
  assert.equal(grounding(null).stated, false)
  assert.equal(grounding(null).detail, UNSTATED_PROVENANCE)
  assert.deepEqual(provenanceOf(answerEvent('Grounded words')), provenance())
  assert.equal(provenanceOf({ ...answerEvent('x'), data: { text: 'x' } } as InquiryEvent), null)
  // Rendered, the two are visibly different: one carries the outside class.
  const inside = html(createElement(Grounded, { answer: answerEvent('Grounded words') }))
  assert.ok(inside.includes(GROUNDED_IN_COLLECTION.toUpperCase()) && !inside.includes('q2-magnet-outside'))
  const outside = html(createElement(Grounded, { answer: answerEvent('Wider words', {
    provenance: provenance({ explored_outside: true, outside_reads: [{ what: 'collection', collection: 'col-other' }] }) }) }))
  assert.ok(outside.includes(EXPLORED_OUTSIDE.toUpperCase()) && outside.includes('q2-magnet-outside'))
  assert.ok(outside.includes('col-other'), 'and names what it reached')
  // The panel renders the same distinction with the same field.
  const panel = html(createElement(AnswerGrounding, { answer: answerEvent('Grounded words') }))
  assert.ok(panel.includes(GROUNDED_IN_COLLECTION.toUpperCase()) && !panel.includes('q2p-outside'))
})

test('the Summary lead is the recorded answer, and what changed is the difference between two answers', async () => {
  store()
  const { r } = resource('mag-elead')
  await r.read()
  const earlier = answerEvent('This Magnet has gathered 2 records from 1 source.')
  const now = answerEvent(['This Magnet has gathered 3 records from 1 source.',
    '1 of them arrived in this collection.'].join('\n'))
  perspectivesOf(r).update({ standing: 'ent-topicA11111',
    summary: { perspective: 'ent-topicA11111', current: now, superseded: [earlier], batch: 'adm-batch111111' } })
  const rendered = html(createElement(Summary, { resource: r, onPost: () => {} }))
  // THE LEAD IS THE ANSWER, statement by statement, not a word count.
  assert.ok(rendered.includes('This Magnet has gathered 3 records from 1 source.'), 'the answer leads')
  assert.ok(rendered.includes('1 of them arrived in this collection.'), 'every statement of it is shown')
  assert.ok(!rendered.includes(NOT_ANSWERED_YET), 'and it is not labelled as counted')
  assert.ok(rendered.includes(SUMMARY_IS_A_QUESTION), 'it says it is one kept question answer')
  assert.ok(rendered.includes(GROUNDED_IN_COLLECTION.toUpperCase()), 'with what it was grounded in beside it')
  // The counted lines STAY, as secondary detail behind the disclosure.
  assert.ok(rendered.includes('Limits and dates ▾'))
  assert.ok(collectionOverview(r.saved, r.snapshot()).length > 2, 'the counts are still available')
  // WHAT CHANGED is the difference between the two answers.
  const change = answerDiff(now, earlier)
  assert.deepEqual(change?.added, ['This Magnet has gathered 3 records from 1 source.', '1 of them arrived in this collection.'])
  assert.deepEqual(change?.gone, ['This Magnet has gathered 2 records from 1 source.'])
  assert.match(changeWords(change), /2 new statements, 1 no longer said/)
  assert.ok(rendered.includes('Now says'), 'the new statements are shown under What changed')
  assert.ok(rendered.includes('No longer says'), 'and so are the ones no longer said')
  // A first answer has nothing before it, and nothing is claimed to have changed.
  assert.deepEqual(answerDiff(now, undefined)?.gone, [])
  assert.equal(answerDiff(null, earlier), null)
  assert.match(changeWords(null), /nothing is claimed to have changed/)
  assert.equal(statements(answerText(now)).length, 2)
  assert.deepEqual(statements(' a \n\n b '), ['a', 'b'])
})

/** THE SUMMARY OPENS ON THE ANSWER (owner `ent-15a36a065eb8`: "Remove ...
 *  redundant headings and permanently visible buttons. Keep secondary actions
 *  and provenance available through progressive disclosure").
 *
 *  What stood between the answer and the records it was written from was four
 *  paragraphs of apparatus -- its grounding, what the record checked before
 *  freezing a run's reply as it, that it is a kept question's answer, and what
 *  the presses under it would do. Every word of it is still written, behind
 *  `How this answer was made ▾`. What is NOT behind it is anything that
 *  qualifies the answer's own words: `BRIEFING_FROM_EARLIER` says the answer
 *  was written from a different collection than the one on screen, and that
 *  changes what the words above mean, so it stays in the open. */
test('the Summary opens on the answer, with how it was made one press away', async () => {
  store()
  const { r } = resource('mag-eapparatus-summary')
  await r.read()
  const said = 'The bench reference drifted between the two calibration batches.'
  const now = answerEvent(said)
  perspectivesOf(r).update({ standing: 'ent-topicA11111',
    summary: { perspective: 'ent-topicA11111', current: now, superseded: [], batch: 'adm-batch111111' } })
  const rendered = html(createElement(Summary, { resource: r, onPost: () => {} }))

  const answer = rendered.indexOf(said)
  const how = rendered.indexOf(HOW_THIS_WAS_MADE)
  assert.ok(answer >= 0 && how > answer, 'the answer is read before anything about how it was made')
  assert.match(rendered, /<details class="q2-magnet-provenance q2-magnet-disclosure q2-magnet-how"><summary>/,
    'the apparatus is a disclosure of this surface’s own kind')
  assert.ok(!/q2-magnet-how"[^>]*\sopen/.test(rendered), 'and it rests shut')
  // NOTHING WAS REMOVED, and each of them is behind it rather than above it.
  for (const behind of [GROUNDED_IN_COLLECTION.toUpperCase(), SUMMARY_IS_A_QUESTION]) {
    const at = rendered.indexOf(behind)
    assert.ok(at >= 0, `${behind} is still said`)
    assert.ok(at > how, `${behind} is behind the disclosure, not permanently over the fold`)
  }
  // THE PLACE NAME IS SAID ONCE: the card's own tab already reads `Summary`.
  assert.ok(!rendered.includes('mgd-eyebrow">Summary<'),
    'the eyebrow that repeated the tab under the tab is gone')
  assert.ok(rendered.includes('What this Magnet holds'), 'what the tab does not say is kept')
})

/* --- question-first Perspectives -------------------------------------------- */

/** THE ASKING SURFACE (round-3 `02-compact-current`, `09-current-help`, as the
 *  owner's later hands-on reading of it corrects them).
 *  Nothing asked yet is a place to ask something, not a form to administer:
 *  `Explore a question` with `Past questions ▾` at the far edge, one muted
 *  sentence, the compose box, `TRY ASKING`, a divider, and ONE line pairing
 *  `AVAILABLE NOW` with what ordinary Conversation does. Everything
 *  administrative is behind `Past questions ▾`, and nothing was removed.
 *
 *  THE EYEBROW IS GONE, and that is the change this test now holds in place.
 *  Round 3 drew `PERSPECTIVES` over `Explore a question`; the owner read the
 *  built surface and asked for redundant headings to go
 *  (`ent-15a36a065eb8`, 2026-11-27, later than those mockups and so the
 *  wording that stands). The card's own tab bar already reads `Perspectives` a
 *  hand's width above, so the word was printed twice with nothing between
 *  them. What the surface opens on is what the reader came to do. */
test('nothing asked yet renders the approved asking surface and no administrative control', () => {
  store()
  const { r } = resource('mag-equestionfirst')
  const rendered = html(createElement(Perspectives, { resource: r, canWrite: true, onEvidence: () => {} }))
  const heading = rendered.indexOf('Explore a question')
  const box = rendered.indexOf('What would you like to explore?')
  const press = rendered.indexOf('Ask →')
  const examples = rendered.indexOf('TRY ASKING')
  const today = rendered.indexOf('AVAILABLE NOW')
  assert.ok(heading >= 0, 'the heading says what to do, and leads the surface')
  assert.ok(!rendered.includes('>Perspectives<'),
    'and the place name is not printed a second time under the tab that says it')
  assert.ok(rendered.includes('mgd-h2'), 'the heading is the design’s own heading element')
  assert.ok(box > heading && press > box, 'the compose box and its one press come before anything else')
  assert.ok(examples > press && today > examples, 'then what to try, then what is available today')
  assert.ok(rendered.includes('Past questions ▾'), 'history and provenance are one link away')
  assert.ok(rendered.includes('Question or hypothesis') && rendered.includes('mgd-compose'),
    'the compose box is the design’s, with its subtle label on its footing row')
  // The sentence about what asking and discussing do is said once in the body
  // and once in the aside beside it, and nowhere else: not three times over
  // one surface, which is what the owner objected to.
  assert.ok(rendered.split(DISCUSSION_READS).length - 1 <= 2,
    'what asking keeps and what discussing is, is not repeated over one surface')
  // TRY ASKING is built from what THIS Magnet collected, not a demo sentence.
  assert.ok(!rendered.includes('What might be slowing our releases?'), 'the hardcoded demo question is gone')
  assert.equal(tryAsking(r), offeredQuestions(r.snapshot())[0])
  assert.ok(rendered.includes(tryAsking(r)), 'the suggestion offered is the one this collection makes askable')
  assert.ok(rendered.includes('What can I do?'), 'the one help panel is opened by a link, not spread on the surface')
  // Nothing administrative is rendered here at all.
  for (const gone of ['aria-label="Perspective name"', 'aria-label="Revision reason"', 'aria-label="Active question"',
    'Wording history', 'Rename this Perspective', 'Retire Perspective', 'Edit saved question', '— Remove'])
    assert.ok(!rendered.includes(gone), `${gone} does not occupy the asking surface`)
  const createAction = panelSrc().match(/act\('create', \{([^}]*)\}\)/)?.[1] ?? ''
  assert.match(createAction, /name: suggested, question: drafts\.question/)
  assert.doesNotMatch(createAction, /reason/, 'creating a question sends only its name and question')
  // Renaming, revising, challenging, branching and retiring are still reachable.
  const panel = code(panelSrc())
  for (const kept of ["act('rename'", "act('question'", "act('challenge'", "act('branch'", "'resume' : 'retire'"])
    assert.ok(panel.includes(kept), `nothing was removed to make room (${kept})`)
  // Behind it, the disclosure says what an answer is grounded in -- and the
  // permanently disabled press that said answering did not work is gone.
  const behind = html(createElement(PastQuestions, { resource: r, canWrite: true, onEvidence: () => {}, onNew: () => {}, onOpened: () => {} }))
  assert.ok(behind.includes(PERSPECTIVE_DISCLOSURE), 'what an answer is grounded in is stated here')
  assert.ok(!behind.includes('Answer from selected evidence'), 'the disabled affordance is gone')
  assert.ok(!behind.includes('What this cannot do yet'), 'and so is the heading it sat under')
  assert.ok(behind.includes('aria-label="Active question"'), 'the durable lens is still reachable')
})

/** A SAVED QUESTION AND WHAT IS UNDERSTOOD OF IT (`05-future-answer`,
 *  `10-current-discussion`): the state line, the question in a chat bubble, the
 *  record's own understanding against the gold rule with ONE link out of it,
 *  the follow-up compose box, and at most one hint. No lecture under the
 *  understanding, and no `Your question` label standing over the question. */
test('a saved question renders as the question and what is understood of it', () => {
  store()
  const { r } = resource('mag-eunderstood')
  const topic = 'ent-topicA11111'
  const perspective = { perspective: topic, name: 'Does the bench drift?', retired: false, question: null,
    current_question: { text: 'Does the bench drift between batches?', revision: 'adm-revision111' }, events: 2 }
  perspectivesOf(r).update({ rows: [perspective], selected: topic, viewed: topic,
    viewedDetail: perspective, selectedDetail: perspective })
  const rendered = html(createElement(Perspectives, { resource: r, canWrite: true, onEvidence: () => {} }))
  assert.ok(rendered.includes('mgd-chatbubble'), 'the question is in a chat bubble')
  assert.ok(rendered.includes('Does the bench drift between batches?'), 'in its own saved words')
  assert.ok(!rendered.includes('Your question'), 'no standing administrative label over it')
  assert.ok(rendered.includes('mgd-answer'),
    'what is understood of it is the answer block')
  assert.ok(rendered.includes(NOTHING_RECORDED_YET), 'with nothing recorded it says so in one sentence')
  assert.equal(rendered.split('Explore supporting items ↗').length - 1, 1, 'and carries exactly one link out of it')
  assert.ok(!rendered.includes('Earlier wordings and recorded answers have no automatic knowledge standing.'),
    'the lecture under the understanding is gone')
  assert.ok(rendered.includes('Send ↑') && rendered.includes('Ask a follow-up or explore an idea…'),
    'the follow-up compose box is in the body, where the design puts it')
  assert.equal(rendered.split('mgd-hint').length - 1, 1, 'at most one hint line at the foot')
  assert.ok(rendered.includes(DISCUSSION_READS), 'and it says what asking keeps and what discussing is')
  assert.ok(rendered.includes(TAKE_TO_CONVERSATION), 'one press takes this question into the Conversation')
  assert.ok(!rendered.includes('— Remove') && !rendered.includes('About “'), 'the administrative row is gone')
})

/** THE ANSWER'S APPARATUS IS DISCLOSED, NOT DISPLAYED AND NOT DELETED (owner
 *  `ent-15a36a065eb8`: "Remove ... permanently visible buttons. Keep secondary
 *  actions and provenance available through progressive disclosure").
 *
 *  On the resting surface: the question, the answer, and the one press to the
 *  records it rests on. Behind `About this answer ▾`: what it was grounded in,
 *  who wrote it, the recorded answer itself, and the three presses that ACT on
 *  the answer rather than read it -- answering again, reading the question
 *  again, and taking it to the Conversation, which used to be a filled button
 *  standing permanently under every answer.
 *
 *  Nothing was removed to make room: every one of them is asserted present,
 *  and asserted to be inside the disclosure rather than above it. The
 *  disclosure is shut at rest, so the surface opens on the answer. */
test('the answer stands alone, and everything secondary to reading it is one disclosure away', () => {
  store()
  const { r } = resource('mag-eapparatus')
  const topic = 'ent-topicA11111'
  const perspective = { perspective: topic, name: 'Does the bench drift?', retired: false, question: null,
    current_question: { text: 'Does the bench drift between batches?', revision: 'adm-revision111' }, events: 2 }
  const current = answerEvent('The bench drifted 0.4 µm over four batches.')
  perspectivesOf(r).update({ rows: [perspective], selected: topic, viewed: topic,
    viewedDetail: perspective, selectedDetail: perspective, events: [current] })
  const rendered = html(createElement(Perspectives, { resource: r, canWrite: true, onEvidence: () => {} }))

  const answer = rendered.indexOf('The bench drifted 0.4 µm over four batches.')
  const support = rendered.indexOf('Explore supporting items ↗')
  const disclosure = rendered.indexOf(ABOUT_THIS_ANSWER)
  assert.ok(answer >= 0, 'the answer itself is on the surface')
  assert.ok(disclosure > answer, 'and the apparatus comes after it, not before')
  assert.ok(support >= 0 && support < disclosure,
    'the one press to the records the answer rests on stays on the surface')

  // SHUT AT REST. A `<details>` with no `open` attribute opens only when asked.
  assert.match(rendered, /<details class="q2p-about q2-magnet-disclosure"><summary>/,
    'the apparatus is a disclosure of this surface’s own kind')
  assert.ok(!/<details class="q2p-about[^"]*"[^>]*\sopen/.test(rendered), 'and it rests shut')

  // NOTHING WAS REMOVED, and each of them is behind it rather than above it.
  for (const behind of [GROUNDED_IN_COLLECTION.toUpperCase(), ANSWER_WRITTEN_BY(current),
    'View the recorded answer', 'Answer again from this collection', READ_AGAIN, TAKE_TO_CONVERSATION]) {
    const at = rendered.indexOf(behind)
    assert.ok(at >= 0, `${behind} is still offered`)
    assert.ok(at > disclosure, `${behind} is behind the disclosure, not permanently on screen`)
  }
  // And the press that took this question to the Conversation is no longer a
  // filled button standing under the answer.
  assert.ok(!/<button[^>]*class="mgd-button mgd-secondary"[^>]*>Discuss this in the Conversation/.test(rendered),
    'taking the question to the Conversation is a lettered action now, not a slab')
})

/** SUPPORTING ITEMS (`06-future-support`): opened from the answer block, the
 *  collected items in the Magnet's own words with one way into each, and a
 *  closing block saying plainly that nothing chose or read them. */
test('supporting items are the collected items themselves, no longer marked as a future concept', async () => {
  store()
  const { r } = resource('mag-esupport')
  await r.read()
  const rendered = html(createElement(SupportingItems, { resource: r, question: 'Does the bench drift?', onOpen: () => {}, onBack: () => {} }))
  assert.ok(rendered.includes('← Back to answer'), 'one way back')
  assert.ok(!rendered.includes('FUTURE CONCEPT'), 'the mark on the absence is gone, because it is not absent')
  assert.ok(rendered.includes('Supporting items') && rendered.includes('For “Does the bench drift?”'),
    'a heading and a muted line saying what they support')
  assert.ok(rendered.includes('mgd-item') && rendered.includes('Open item ↗'), 'the items carry one way into each')
  assert.ok(rendered.includes('Calibration of the bench reference drifted'), 'in the records’ own words')
  assert.ok(rendered.includes('mgd-shade') && rendered.includes('Why these?') && rendered.includes(SUPPORTING_WHY),
    'and the note saying which of them the answer names closes the list')
  assert.doesNotMatch(SUPPORTING_WHY, /not available yet/, 'which no longer says answering does not work')
})

/** PAST QUESTIONS (`08-history`): the list to return through, with the search,
 *  the rows and the way back; and behind it every administrative verb. */
test('past questions is a list to return through, with the administrative verbs behind it', () => {
  store()
  const { r } = resource('mag-epast')
  const rows = [
    { perspective: 'ent-topicA11111', name: 'A', retired: false, question: null,
      current_question: { text: 'What is slowing our releases?', revision: 'adm-a' }, events: 3 },
    { perspective: 'ent-topicB11111', name: 'B', retired: false, question: null,
      current_question: { text: 'Are handoffs clearly owned?', revision: 'adm-b' }, events: 1 },
  ]
  perspectivesOf(r).update({ rows, selected: 'ent-topicA11111', viewed: 'ent-topicA11111', viewedDetail: rows[0], selectedDetail: rows[0] })
  const rendered = html(createElement(PastQuestions, { resource: r, canWrite: true, onEvidence: () => {}, onNew: () => {}, onOpened: () => {} }))
  assert.ok(rendered.includes('＋ New question'), 'asking something new is at the far edge of the eyebrow row')
  assert.ok(rendered.includes('mgd-h2') && rendered.includes('Past questions'), 'the heading says what is shown')
  assert.ok(rendered.includes('Return to a question and continue the conversation.'), 'one muted sentence')
  assert.ok(rendered.includes('mgd-search') && rendered.includes('aria-label="Find a question"'), 'and a search over them')
  assert.ok(rendered.includes('What is slowing our releases?') && rendered.includes('Are handoffs clearly owned?'),
    'the questions are the rows, in their own saved words')
  assert.ok(rendered.includes('Current discussion'), 'a row says when and how much discussion it carries')
  assert.ok(rendered.includes('1 recorded change'), 'counted from the row, never guessed')
  assert.ok(rendered.includes('Back to current →'), 'and the closing line goes back')
  // Everything administrative is here, and shut.
  for (const kept of ['aria-label="Active question"', 'Wording history', 'Rename this Perspective',
    'Edit saved question', PERSPECTIVE_DISCLOSURE])
    assert.ok(rendered.includes(kept), `${kept.slice(0, 40)} is still reachable`)
  for (const section of rendered.match(/<details[^>]*>/g) ?? [])
    assert.doesNotMatch(section, /open/, 'nothing administrative is open until it is asked for')
})

test('Wording history starts compact, preserves stored history and leaves pagination available when expanded', () => {
  store()
  const { r } = resource('mag-ehistorycompact')
  const topic = 'ent-topicA11111'
  const perspective = { perspective: topic, name: 'Does the bench drift?', retired: false, question: null,
    current_question: { text: 'Does the bench drift now?', revision: 'adm-current111' }, events: 101 }
  const events = [
    { seq: 2, post: 'ent-event222222', event: 'rename', perspective: topic,
      snapshot: { ref: 'adm-name111', digest, size: 4, media_type: 'application/json' }, data: { name: 'Older label' } },
    { seq: 1, post: 'ent-event111111', event: 'question', perspective: topic,
      snapshot: { ref: 'adm-question111', digest: digest2, size: 8, media_type: 'application/json' }, data: { text: 'Did the bench drift before?' } },
  ]
  perspectivesOf(r).update({ rows: [perspective], selected: topic, viewed: topic,
    viewedDetail: perspective, selectedDetail: perspective, events, next: 'history-cursor-2', historyComplete: false })
  const rendered = html(createElement(PastQuestions, { resource: r, canWrite: true, onEvidence: () => {}, onNew: () => {}, onOpened: () => {} }))
  const history = rendered.slice(rendered.indexOf('aria-label="Wording history"'))
  const historySection = rendered.match(/<details[^>]*><summary>Wording history[\s\S]*?<\/details>/)?.[0] ?? ''
  assert.ok(historySection, 'wording history is inside a disclosure section')
  assert.ok(!/<details[^>]*open/.test(historySection), 'the section is collapsed initially')
  assert.ok(history.includes('Wording history (2+)'), 'the summary indicates loaded and remaining history')
  assert.ok(history.includes('Older label') && history.includes('Did the bench drift before?'), 'stored wording is still present in the expandable content')
  assert.ok(history.includes('More wording history'), 'the next page remains reachable inside history')
  assert.ok(history.includes('Refresh wording history'), 'refresh remains available inside history')
  assert.equal(perspectivesOf(r).snapshot().events.length, 2, 'rendering does not change the stored history')
})

/** The owner's language review covers the whole interface (ent-3191baeb33d2 §2:
 *  "Question rather than inquiry wording"). This renders every place of the
 *  panel -- the current question with its compose box, and past questions with
 *  the lens, the administrative section, the uncertain-action retry and the
 *  history -- and requires that no word of any of it says "inquiry", while each
 *  renamed control is still there doing the same thing. */
test('every control the Perspectives panel shows uses ordinary question language', () => {
  store()
  const { r } = resource('mag-elanguage')
  const topic = 'ent-topicA11111'
  const perspective = { perspective: topic, name: 'Does the bench drift?', retired: false, question: null,
    current_question: { text: 'Does the bench drift between batches?', revision: 'adm-revision111' }, events: 2 }
  perspectivesOf(r).update({
    rows: [perspective], selected: topic, viewed: topic, viewedDetail: perspective, selectedDetail: perspective,
    listNext: 'cursor-2', next: 'cursor-3',
    pending: { kind: 'question', target: topic } as never,
    events: [{ seq: 1, post: 'ent-event111111', event: 'question', perspective: topic,
      snapshot: { ref: 'adm-revision111', digest, size: 10, media_type: 'application/json' },
      data: { text: 'Does the bench drift between batches?' } }],
  })
  // Every place of the panel at once: the current question, the questions
  // already asked with everything administrative behind them, the supporting
  // items, and the asking surface with words in its box.
  const { r: fresh } = resource('mag-elanguagefresh')
  setQuestionDraft(panelAt(fresh), 'Does the spare bench drift too?')
  const rendered = [
    html(createElement(Perspectives, { resource: r, canWrite: true, onEvidence: () => {} })),
    html(createElement(PastQuestions, { resource: r, canWrite: true, onEvidence: () => {}, onNew: () => {}, onOpened: () => {} })),
    html(createElement(SupportingItems, { resource: r, question: 'Does the bench drift?', onOpen: () => {}, onBack: () => {} })),
    html(createElement(Perspectives, { resource: fresh, canWrite: true, onEvidence: () => {} })),
  ].join('\n')
  // What the owner reads: the text between the tags, and the labels a control
  // is announced by. (DOM ids and class names are not interface language.)
  assert.doesNotMatch(rendered.replace(/<[^>]*>/g, ' '), /inquir/i, 'no word on this panel says inquiry')
  const labels = [...rendered.matchAll(/(?:aria-label|title|placeholder|alt)="([^"]*)"/g)].map((m) => m[1])
  assert.ok(labels.length >= 4, 'the labelled controls are there to be checked')
  for (const label of labels) assert.doesNotMatch(label, /inquir/i, `a control is still announced as inquiry: ${label}`)
  for (const named of ['Active question', 'No question — ordinary Conversation', 'More questions',
    'Ask →', 'Save for later', 'Send ↑', 'Past questions ▾', '＋ New question',
    'Explore supporting items ↗', 'Retry unchanged question action']) {
    assert.ok(rendered.includes(named), `${named} is the control's name now`)
  }
  // Renamed, not removed: each one still calls the verb it called before.
  const panel = code(panelSrc())
  for (const kept of ["store.select(", "act('create'", "store.view(", "act('branch'", 'store.retryPending()'])
    assert.ok(panel.includes(kept), `the renamed control still does its own work (${kept})`)
})

/* --- ordinary collection language ------------------------------------------
   THE INVARIANT (owner request ent-3191baeb33d2 §2): nothing the owner reads
   exposes the implementation's vocabulary. "Retained" and "batch" are what the
   record calls an immutable captured copy; what the owner has is a collection,
   and its earlier ones are its history. "Evidence" stays only where it means
   information supporting or contradicting a specific claim -- the owner's own
   exception -- which here is the disabled grounded affordance and the
   statement that no record is recorded as supporting anything. */

test('nothing the owner reads in Summary says retained or batch', async () => {
  store()
  const { r } = resource('mag-ewords')
  await r.read()
  r.update({ status: 'partial', reason: 'Shortened at the first 64 KiB.',
    batchSelection: { ref: 'adm-batch222222', digest: digest2 } })
  const forbidden = /retained|batch/i
  // Every sentence of both written blocks, the questions, and the standing statements.
  for (const line of [...summaryFacts(r.saved, r.snapshot()), ...collectionOverview(r.saved, r.snapshot()),
    ...offeredQuestions(r.snapshot(), true), NO_COMPARISON, NOT_ANSWERED_YET, EXTRACTIVE_LABEL,
    ANSWER_THIS_COLLECTION, SUMMARY_IS_A_QUESTION, GROUNDED_IN_COLLECTION, EXPLORED_OUTSIDE])
    assert.doesNotMatch(line, forbidden, `a line the owner reads still says it: ${line}`)
  // And in all three states of the rendered view: populated, empty, unread.
  const { r: emptyOne } = resource('mag-ewordsempty', empty); await emptyOne.read()
  const { r: unread } = resource('mag-ewordsunread')
  for (const view of [r, emptyOne, unread]) {
    const rendered = html(createElement(Summary, { resource: view, onPost: () => {} }))
    // What the owner reads: the text between the tags, and the labels a control
    // is announced by. (DOM ids and artifact references are not language.)
    assert.doesNotMatch(rendered.replace(/<[^>]*>/g, ' '), forbidden, 'rendered words')
    for (const label of [...rendered.matchAll(/(?:aria-label|title|placeholder|alt)="([^"]*)"/g)].map((m) => m[1]))
      assert.doesNotMatch(label, forbidden, `a control is announced as: ${label}`)
  }
  // The comparison and history sentences a press reveals are written here too,
  // so the removed wording is checked where it lived rather than only where it renders.
  for (const gone of ['retained batch', 'retained collection', 'retained posts', 'retained files',
    'retained item', 'retained text', 'retained history', 'batch shown', 'latest batch', 'batch state',
    'first retained', 'under All'])
    assert.ok(!code(summarySrc()).includes(gone), `${gone} is not language this view shows`)
  // Evidence survives exactly where it is about support for a claim: the
  // supporting records an answer names. The disabled press that used to carry
  // that word is gone, so the word is checked where it now lives.
  assert.match(SUPPORTING_WHY, /records/i)
  assert.ok(!html(createElement(Summary, { resource: r, onPost: () => {} })).includes('Draft an answer from selected records'))
})

/* --- the chip stands for the version the owner read -------------------------
   THE INVARIANT (D's correction, adm-394af815cdce §"Finding 4"): a chip
   represents the EXACT version attached, and a changed selection refuses
   rather than silently using a newer one. This part attaches the Perspective
   chip, so the version has to be on it as it goes on -- not stamped later from
   whatever is durable by then, which is how a newer wording could take the
   place of the one the owner read. */

const TOPIC = 'ent-topicA11111', OTHER_TOPIC = 'ent-topicB11111'
const QUESTION = 'adm-question111', LATER = 'adm-question222'
const lensRow = (perspective = TOPIC, revision = QUESTION, recorded = digest) => ({
  magnet: 'mag-elens', perspective, selected: perspective, name: 'Does the bench drift?', retired: false,
  question: { ref: revision, digest: recorded, size: 20, media_type: 'application/json' },
  current_question: { text: 'Does the bench drift between collections?', revision }, events: 1,
}) as unknown as Perspective
const chipOf = (r: MagnetResource) => r.snapshot().context as (MagnetContext & Partial<{ version: string | null; digest: string }>) | null

test('a Perspective chip is attached at the exact saved question version the card read, and is never re-stamped', async () => {
  store()
  const { r } = resource('mag-estamp')
  showPerspectiveContext(r, TOPIC, 'Does the bench drift?', lensRow())
  assert.deepEqual(chipOf(r), { ref: TOPIC, kind: 'perspective', label: 'Does the bench drift?',
    version: QUESTION, digest }, 'the chip says which version it stands for, and nothing of the question’s text')
  // A later wording of the same question does not take the attached one's place.
  showPerspectiveContext(r, TOPIC, 'Does the bench drift?', lensRow(TOPIC, LATER))
  assert.equal(chipOf(r)?.version, QUESTION, 'a revision since is a refusal at the press, never a substitution here')
  // Choosing another Perspective stamps that one, carrying nothing over.
  showPerspectiveContext(r, OTHER_TOPIC, 'Where do the sources disagree?', lensRow(OTHER_TOPIC, LATER))
  assert.deepEqual(chipOf(r), { ref: OTHER_TOPIC, kind: 'perspective', label: 'Where do the sources disagree?',
    version: LATER, digest })
  // A row that cannot state its version exactly leaves the chip unstamped
  // rather than stamped from something else.
  r.update({ context: null })
  showPerspectiveContext(r, TOPIC, 'Does the bench drift?',
    { ...lensRow(), current_question: { text: 'x', revision: 'adm-other1111' } } as unknown as Perspective)
  assert.deepEqual(chipOf(r), { ref: TOPIC, kind: 'perspective', label: 'Does the bench drift?' })
  assert.equal(questionVersion(null), null)
  assert.equal(questionVersion({ ...lensRow(), question: null } as unknown as Perspective), null, 'no saved artifact, no stamp')
  assert.equal(questionVersion(lensRow(TOPIC, QUESTION, 'not-a-digest')), null, 'an unrecorded digest is not a stamp')
  // And ordinary Conversation still takes the chip off.
  showPerspectiveContext(r, null)
  assert.equal(r.snapshot().context, null)
})

test('stamping an attached chip attaches nothing, respects a removal, and leaves another Perspective’s chip alone', () => {
  store()
  const { r } = resource('mag-estampquiet')
  // An intentional removal stays removed: nothing is re-attached to stamp it.
  r.update({ context: null, contextSuppressed: true })
  stampAttachedQuestion(r, lensRow())
  assert.equal(r.snapshot().context, null, 'a removed chip is not brought back')
  assert.equal(r.snapshot().contextSuppressed, true, 'and the removal is still recorded')
  // Another Perspective's chip is not restamped with this one's version.
  r.update({ context: { ref: OTHER_TOPIC, kind: 'perspective', label: 'Another question' } })
  stampAttachedQuestion(r, lensRow())
  assert.equal(chipOf(r)?.digest, undefined)
  // The chip it is about gains the version, and keeps its label.
  r.update({ context: { ref: TOPIC, kind: 'perspective', label: 'Does the bench drift?' } })
  stampAttachedQuestion(r, lensRow())
  assert.deepEqual(chipOf(r), { ref: TOPIC, kind: 'perspective', label: 'Does the bench drift?', version: QUESTION, digest })
  // Already stated, never restated.
  stampAttachedQuestion(r, lensRow(TOPIC, LATER))
  assert.equal(chipOf(r)?.version, QUESTION)
})

test('discussing the selected question says which version those words are', async () => {
  store()
  const { r } = resource('mag-ediscuss')
  await r.read()
  const inquiries = perspectivesOf(r)
  let revision = QUESTION
  inquiries.get = async (tail = '') => tail.startsWith('?') ? { magnet: r.saved.id, perspectives: [], selected: TOPIC, next: null }
    : tail.includes('/history') ? { magnet: r.saved.id, perspective: TOPIC, events: [], next: null }
    : { ...lensRow(TOPIC, revision), magnet: r.saved.id, selected: TOPIC }
  // The chip the lens left, with no version on it yet (a chip saved before this
  // release, or one another surface attached).
  r.update({ context: { ref: TOPIC, kind: 'perspective', label: 'Does the bench drift?' }, contextSuppressed: false })
  await discussSelectedQuestion(r, inquiries)
  assert.equal(miniComposerDraft(r).text, 'Does the bench drift between collections?', 'the words are the saved question’s own')
  assert.deepEqual(chipOf(r), { ref: TOPIC, kind: 'perspective', label: 'Does the bench drift?', version: QUESTION, digest },
    'and the chip beside them stands for that exact version')
  // A revision since does not replace what the chip stands for.
  revision = LATER
  saveMiniComposer(r, { ...emptyDraft() })
  await discussSelectedQuestion(r, inquiries)
  assert.equal(chipOf(r)?.version, QUESTION, 'the version the owner attached is kept, so the send refuses rather than substitutes')
  // With the chip deliberately removed, discussing re-attaches nothing.
  r.update({ context: null, contextSuppressed: true })
  saveMiniComposer(r, { ...emptyDraft() })
  await discussSelectedQuestion(r, inquiries)
  assert.equal(r.snapshot().context, null)
  assert.equal(r.snapshot().contextSuppressed, true)
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
