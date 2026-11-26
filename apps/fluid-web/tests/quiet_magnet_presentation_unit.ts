/** Part 5: information presented by what it represents, with existing renderers.
 *
 *  What these prove, against owner request #1017 `ent-599e68de0893` ("present
 *  information according to what it represents, not its internal storage type
 *  ... prose, images, tables, charts or timelines where appropriate", and
 *  "collection statistics are secondary") and `MAGNET-EXPERIENCE-PLAN.md`
 *  Part 5's done-when:
 *
 *  - the structure the server records is READ: an answer's `lines`, each with
 *    the `cites` it was written from, instead of `data.text` re-split on
 *    newlines -- which is what every surface in `src/quiet2/magnets/` did,
 *    discarding the one thing that makes a statement checkable;
 *  - each statement is pressable to the captured records it cites, and a cited
 *    id the batch shown does not hold is dropped rather than drawn as an
 *    opening that would not open;
 *  - a recorded answer that is a written document is rendered as prose by the
 *    renderer Fluid already has (`Prose`): headings, paragraphs, lists, pipe
 *    tables. A statement-per-line synthesis keeps the statement-and-quotation
 *    layout whose citations are pressable;
 *  - the lead is what the material NAMES, read out of the rows' own captured
 *    words, and no record count or counted-word line is above the fold. Every
 *    measurement is still written, behind the facts disclosure;
 *  - dated published material is drawn as a table, from each row's own recorded
 *    `Published:`/`Publisher:` lines -- never from `r.at`, which is when Mentis
 *    fetched it; and no table is drawn where the material has no such shape;
 *  - a collected record opens as what it represents: its recorded headline a
 *    heading, its address a link, its words prose -- and acquired words go to
 *    `Prose` as untrusted, so no marked block or HTML preview is drawn from a
 *    page Mentis fetched;
 *  - nothing on these surfaces shows a raw storage path, id or digest. */
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import type { MagnetConfig } from '../src/fluid/surface/magnet/types'
import type { RouteResult } from '../src/fluid/surface/magnet/route'
import Summary, {
  BRIEFING_REWRITTEN, Briefing, DATED_WHY, NAMES_NOTHING_YET, WRITTEN_FROM,
  answerLines, answerRecordCount, citedRows, collectionOverview, datedMaterial, datedTable, isWrittenBriefing,
  materialLead, namedSubjects, offeredQuestions, rowPublication, summaryFacts, worthTabulating,
} from '../src/quiet2/magnets/Summary'
import Inspection, { CapturedWords, NOTHING_BUT_A_HEADER } from '../src/quiet2/magnets/Inspection'
import { createMagnetResource } from '../src/quiet2/magnets/state'
import type { InquiryEvent } from '../src/quiet2/magnets/perspectives'
import { page as binding } from '../src/brainBinding'

const brainKey = 'brain-presentation'
const html = (node: Parameters<typeof renderToStaticMarkup>[0]) => renderToStaticMarkup(node)

/** A device store the resource can write its places into, as the other focused
 *  Magnet tests set one up. */
const store = () => {
  const mem = new Map<string, string>()
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: {
    getItem: (k: string) => mem.get(k) ?? null, setItem: (k: string, v: string) => mem.set(k, v),
    removeItem: (k: string) => mem.delete(k), clear: () => mem.clear() } })
  binding.saw('brain-presentation@instance-one')
  return mem
}

/* --- fixtures: the real astronomy Magnet's own recorded shape ---------------
   A Google News feed entry as `mentis/sources/feeds.py::_entry_body` writes it:
   the headline, a blank line, the permalink, a blank line, the summary, then a
   `--` rule and the provenance trailer with `Published:` and `Publisher:`. The
   byte shapes here are that writer's, so what the client reads back is what
   the server recorded. ------------------------------------------------------ */

const feedBytes = (headline: string, link: string, body: string, published: string, publisher: string) =>
  `${headline}\n\n${link}\n\n${body}\n\n--\nPublished: ${published}\nPublisher: ${publisher}\n`

const WHEN = 1795600000
/** One acquired row exactly as `collectionRows` admits one: its own Admission
 *  reference, its recorded digest, and a captured range whose bounds and
 *  citation agree with its bytes. Nothing here is relaxed, so what these tests
 *  read back is what a verified batch actually holds. */
function webRow(hex: string, headline: string, body: string, published: string, publisher: string): RouteResult {
  const id = `adm-${hex}`, digest = hex[0].repeat(64)
  const text = feedBytes(headline, `https://example.org/${hex}`, body, published, publisher)
  const end = new TextEncoder().encode(text).length
  return { kind: 'file', id, version: id, conversation: null, author: null, at: WHEN,
    via: 'held-source',
    value: { ref: id, digest, collection: 'col-astro', path: `space-missions/${hex}`, text,
      offset: 0, end, size: end, acquired_at: WHEN, shortened: false, omitted_bytes: 0, next_offset: null,
      citation: `${id}@${digest.slice(0, 12)}[0:${end}]` } } as unknown as RouteResult
}

const ROWS: RouteResult[] = [
  webRow('aaa111111111', 'Roman Space Telescope passes its final thermal test - NASA',
    'The Roman Space Telescope completed thermal vacuum testing ahead of its launch window.',
    '2026-03-27T07:00:00+00:00', 'NASA'),
  webRow('bbb222222222', 'Europa Clipper adjusts its Mars gravity assist - NASA',
    'Europa Clipper fired its thrusters to refine the Mars gravity assist that sends it outward.',
    '2025-11-02T09:30:00+00:00', 'NASA'),
  webRow('ccc333333333', 'Artemis Programme names the Artemis III landing site - Space',
    'The Artemis Programme narrowed the Artemis III candidate regions near the lunar south pole.',
    '2024-06-14T12:00:00+00:00', 'Space'),
]
const [ROMAN, CLIPPER] = ROWS.map((r) => r.id)

const config = (id: `mag-${string}`): MagnetConfig => ({ id,
  sources: [{ kind: 'file', collection: 'col-astro' }],   // the whole collection
  selection: { informationTypes: ['post', 'file'], dates: {} },
  conversation: 'ent-own111111', collection: { mode: 'manual' }, synthesis: { mode: 'manual' },
  notifications: { newItems: false, changes: false, failures: false },
  presentation: { renderer: 'disc' } } as unknown as MagnetConfig)

const ACTIVATION = { post: 'ent-activation111', at: 1795700000, state: 'recorded',
  artifact: { ref: 'adm-batch111111', digest: 'd'.repeat(64), size: 2048, media_type: 'application/json' } }
const pageOf = (id: `mag-${string}`, results: RouteResult[]) => ({
  sources: [{ source: config(id).sources[0], key: 'file:col-astro:', status: 'ok', results }] })

function resource(id: `mag-${string}`, results = ROWS) {
  return createMagnetResource({
    id: `qm-${id}`, brainKey, saved: { id, name: 'Space missions and astronomy', config: config(id) },
    get: async () => ({ status: 200, body: { magnet: id, config: config(id), activation: ACTIVATION, page: pageOf(id, results) } }),
  })
}

/** An answered event in the shape `perspectives_work.answer` records: the
 *  joined `text` AND the `lines` with their `cites`. */
function answered(lines: { text: string; cites: string[] }[], extra: Record<string, unknown> = {}): InquiryEvent {
  return {
    seq: 1, post: 'ent-answer111111', event: 'answered', perspective: 'ent-topic11111',
    snapshot: { ref: 'adm-answer111111', digest: 'sha256:cc' } as any,
    data: { text: lines.map((l) => l.text).join('\n'), lines, method: 'mentis.magnet.synthesis/1',
      provenance: { grounded_in: 'collection', explored_outside: false, outside_authorized: [], outside_reads: [] },
      ...extra },
  }
}

const SYNTHESIS = [
  { text: 'This Magnet’s collected material speaks mainly about Roman Space Telescope and Europa Clipper.',
    cites: [ROMAN, CLIPPER] },
  { text: 'Most recently, from the web search (2026-03-27) · Roman Space Telescope passes its final thermal test: “The Roman Space Telescope completed thermal vacuum testing.”',
    cites: [ROMAN] },
  { text: 'This Magnet has gathered 3 records from 1 source, collected 26 November 2026.',
    cites: [ROMAN, CLIPPER, ROWS[2].id] },
]

/* --- the structure the server records is read ------------------------------- */

test('an answer’s recorded lines and their citations are read, not re-derived from its text', () => {
  const lines = answerLines(answered(SYNTHESIS))
  assert.equal(lines.length, 3, 'one statement per recorded line')
  assert.deepEqual(lines[1].cites, [ROMAN], 'each statement keeps the records it was written from')
  assert.equal(lines[0].text, SYNTHESIS[0].text, 'the recorded characters are unchanged')
  // AN ANSWER RECORDED BEFORE `lines` EXISTED still renders, with no citations,
  // because it recorded none -- and never with guessed ones.
  const older = { ...answered([]), data: { text: 'One statement.\nAnother statement.' } } as InquiryEvent
  assert.deepEqual(answerLines(older), [{ text: 'One statement.', cites: [] }, { text: 'Another statement.', cites: [] }])
  assert.deepEqual(answerLines(null), [], 'no answer is no statements')
  // A malformed recorded line is skipped rather than drawn as an empty one.
  const bad = answered([]) ; (bad.data as any).lines = [{ text: '  ' }, { text: 'Real.', cites: ['x', 7, null] }]
  assert.deepEqual(answerLines(bad), [{ text: 'Real.', cites: ['x'] }], 'only recorded strings become citations')
})

test('a citation resolves to the collected row it names, and an unheld one is dropped', async () => {
  store()
  const r = resource('mag-pcites')
  await r.read()
  const rows = r.snapshot().results
  const cited = citedRows([CLIPPER, CLIPPER, 'adm-notinbatch11'], rows)
  assert.equal(cited.length, 1, 'a repeated citation is one opening, and one the batch lacks is not drawn')
  assert.equal(cited[0].id, CLIPPER)
  assert.equal(cited[0].title, 'Europa Clipper adjusts its Mars gravity assist - NASA',
    'a cited row is named by its own recorded headline, never by where it is stored')
  for (const c of citedRows([ROMAN], rows))
    assert.doesNotMatch(c.title, /space-missions\/|sha256:|adm-|col-/, `no storage identity in "${c.title}"`)
  assert.deepEqual(citedRows([], rows), [])
})

test('each statement is pressable to the captured records it cites', async () => {
  store()
  const r = resource('mag-ppress')
  await r.read()
  const rendered = html(createElement(Briefing, { resource: r, answer: answered(SYNTHESIS) }))
  assert.ok(rendered.includes(WRITTEN_FROM), 'the statement says what it was written from')
  assert.ok(rendered.includes(`id="cite-${ROMAN}"`), 'and that is a press')
  assert.ok(rendered.includes('Roman Space Telescope passes its final thermal test'),
    'the press is named by the record’s own words')
  // The statement itself is still laid out by `links.tsx` -- statement, then the
  // record's own words -- which this part consumes and does not edit.
  assert.ok(rendered.includes('q2-magnet-statement'), 'the recorded statement keeps its own layout')
  assert.ok(rendered.includes('q2-magnet-lead'), 'and the opening statement is still the lead')
})

/* --- a written briefing is prose, drawn by the renderer that exists --------- */

test('a written briefing is rendered as prose, headings and tables included', async () => {
  store()
  const r = resource('mag-pprose')
  await r.read()
  const briefing = ['## What launched', '',
    'The **Roman Space Telescope** cleared thermal testing, and Europa Clipper refined its',
    'Mars gravity assist.', '',
    '| Mission | Published | Agency |', '|---|---|---|',
    '| Roman Space Telescope | 2026-03-27 | NASA |', '| Europa Clipper | 2025-11-02 | NASA |'].join('\n')
  assert.equal(isWrittenBriefing(briefing), true, 'a document is read as a document')
  assert.equal(isWrittenBriefing(SYNTHESIS.map((l) => l.text).join('\n')), false,
    'consecutive single-line statements are one paragraph, so the synthesis keeps its statement layout')
  const rendered = html(createElement(Briefing, { resource: r,
    answer: answered([{ text: briefing, cites: [ROMAN] }]) }))
  assert.ok(/<h\d class="pr-h/.test(rendered), 'its heading is a heading')
  assert.ok(rendered.includes('<strong>Roman Space Telescope</strong>'), 'its emphasis is emphasis')
  assert.ok(rendered.includes('<table class="pr-table">'), 'its table is a table, drawn by Prose')
  assert.ok(rendered.includes('q2-prose'), 'in the quiet2 surface’s own prose measure')
  assert.ok(!rendered.includes('q2-magnet-statement'), 'a document is not split into one statement per line')
})

test('a written briefing keeps each recorded block’s own citations (review ent-e3c43663010a)', async () => {
  store()
  const r = resource('mag-pprosecites')
  await r.read()
  // Two recorded blocks, each a prose fragment with its own cites -- the
  // structured contract a written briefing used to be read straight into
  // `Prose` without, dropping every citation its fixture carried.
  const rendered = html(createElement(Briefing, { resource: r, answer: answered([
    { text: '## What launched\n\nThe **Roman Space Telescope** cleared thermal testing.', cites: [ROMAN] },
    { text: 'Europa Clipper refined its Mars gravity assist.', cites: [CLIPPER] },
  ]) }))
  assert.ok(/<h\d class="pr-h/.test(rendered), 'the written block is still drawn as prose')
  assert.ok(rendered.includes('<strong>Roman Space Telescope</strong>'), 'its emphasis is still emphasis')
  assert.equal((rendered.match(new RegExp(WRITTEN_FROM, 'g')) ?? []).length, 2,
    'each recorded block carries its own citations, not one dropped for the whole document')
  assert.ok(rendered.includes(`id="cite-${ROMAN}"`), 'the first block’s citation is a press')
  assert.ok(rendered.includes(`id="cite-${CLIPPER}"`), 'and so is the second block’s')
})

test('a written answer’s change is not a diff of its Markdown lines', async () => {
  store()
  const r = resource('mag-pchange')
  await r.read()
  // `answerDiff` splits the recorded text on newlines, which is right for the
  // synthesis -- one statement per line -- and wrong for a document, where it
  // listed a table rule and a `**bold**` fragment among sixteen things the
  // answer "now says". The Summary says what a written answer's change is
  // instead, and still keeps both answers under the standing question.
  const doc = ['## A heading', '', 'Words with **emphasis**.', '',
    '| A | B |', '|---|---|', '| 1 | 2 |'].join('\n')
  const rendered = html(createElement(Briefing, { resource: r,
    answer: answered([{ text: doc, cites: [ROMAN] }]) }))
  assert.ok(rendered.includes('<table class="pr-table">'), 'the document itself still renders whole')
  assert.ok(!rendered.includes('|---|---|'), 'and never as its own source')
  assert.equal(isWrittenBriefing(doc), true)
  assert.match(BRIEFING_REWRITTEN, /written as a document/,
    'the view has one sentence for a written answer’s change, in place of the line diff')
})

/* --- the lead is what the material names, not a count of it ----------------- */

test('the subjects are read out of the material’s own words, and nothing is invented', async () => {
  store()
  const r = resource('mag-psubj')
  await r.read()
  const subjects = namedSubjects(r.snapshot().results, 3)
  assert.ok(subjects.includes('Roman Space Telescope'), `a named subject is read whole: ${subjects.join(' | ')}`)
  assert.ok(subjects.includes('Europa Clipper'))
  assert.ok(!subjects.some((p) => /^(The|This|From) /.test(p)), 'a leading grammatical word is not part of a name')
  assert.ok(!subjects.some((p) => p.split(' ').length < 2), 'one capitalised word is not a named subject')
  // A RUN NEVER SPANS TWO PASSAGES. A feed title ends in its byline ("- NASA")
  // and the material under it opens with a name, so reading the two as one run
  // produced "NASA The Roman Space Telescope" -- a phrase neither passage says.
  // The headline and the material are read apart, and a sentence end closes a
  // run, so a name is only ever words that sit together in one sentence.
  assert.ok(!subjects.some((p) => /^NASA |^Space |^ESA /.test(p)),
    `no run spans a byline into the next passage: ${subjects.join(' | ')}`)
  for (const p of subjects) assert.ok(
    ROWS.some((r) => (r.value as any).text.includes(p)), `"${p}" is words the material itself holds`)
  // MATERIAL THAT NAMES NOTHING YIELDS NOTHING, and says so rather than falling
  // back to a frequency table dressed up as a theme.
  const plain = [webRow('ddd444444444', 'nothing named here at all',
    'the collected words of this row name no subject of their own whatsoever.',
    '2026-01-05T00:00:00+00:00', 'somewhere')]
  assert.deepEqual(namedSubjects(plain), [])
})

test('the lead before an answer names subjects, and no count is above the fold', async () => {
  store()
  const r = resource('mag-plead')
  await r.read()
  const s = r.snapshot()
  const lead = materialLead(s)
  assert.match(lead, /^The collected material names /, `the lead is what the material names: ${lead}`)
  assert.ok(lead.includes('Roman Space Telescope'))
  assert.doesNotMatch(lead, /\d/, `no number is in the lead at all: ${lead}`)
  assert.equal(materialLead({ ...s, activation: null } as any), '', 'nothing collected is no lead')
  const rendered = html(createElement(Summary, { resource: r, onPost: () => {} }))
  const fold = rendered.slice(0, rendered.indexOf('Limits and dates'))
  assert.ok(fold.includes('The collected material names'), 'and the view leads with it')
  assert.doesNotMatch(fold, /Most used words/, 'no counted-word line above the fold')
  assert.doesNotMatch(fold, /This Magnet holds \d+ collected/, 'and no record-count line either')
  // NOTHING IS LOST. Every measurement the counted lead used to open with is
  // still written, where the owner kept the rest of them.
  const measured = collectionOverview(r.saved, s).join(' | ')
  assert.match(measured, /This Magnet holds 3 collected files, collected /, 'the counts are still stated')
  assert.ok(rendered.slice(rendered.indexOf('Limits and dates')).includes('This Magnet holds 3 collected files'),
    'in the facts disclosure, which is where the view renders them')
  assert.match(summaryFacts(r.saved, s).join(' | '), /Most used words, counted/, 'as are the counted words')
})

test('a recorded answer’s own trailing record-count line is kept out of the answer and into the facts disclosure (review ent-e3c43663010a)', async () => {
  store()
  const r = resource('mag-pcount')
  await r.read()
  const answer = answered(SYNTHESIS)
  assert.match(answerLines(answer).at(-1)?.text ?? '', /^This Magnet has gathered \d+ records? from /,
    'the fixture itself closes with the server’s count line')
  assert.match(answerRecordCount(answer) ?? '', /^This Magnet has gathered 3 records from 1 source/,
    'the count line is read out for the facts disclosure')
  const briefing = html(createElement(Briefing, { resource: r, answer }))
  assert.doesNotMatch(briefing, /This Magnet has gathered \d+ records? from/, 'and never shown in the answer itself')
  assert.equal(answerRecordCount(answered([{ text: '## Briefing\n\nProse body.', cites: [] }])), null,
    'a written briefing never closes with this line, so nothing is pulled from it')
})

test('an offered question asks about a subject the material names', async () => {
  store()
  const r = resource('mag-pask')
  await r.read()
  const questions = offeredQuestions(r.snapshot())
  assert.ok(questions.every((q) => q.trim().endsWith('?')), 'every offered line is a question')
  assert.ok(questions.some((q) => q.includes('Roman Space Telescope')),
    `a named subject is what is offered: ${questions.join(' | ')}`)
  assert.ok(!questions.some((q) => /\babout (the|this|telescope|space)\?/.test(q)),
    'not a bare recurring word')
  assert.ok(questions.some((q) => /material this source collected|collected from each source/.test(q)))
  for (const q of questions) assert.doesNotMatch(q, /(?:ent|adm|col|mag)-[0-9a-z]{4,}/, `no identifier: ${q}`)
})

/* --- dated published material is a table ----------------------------------- */

test('a row’s publication date and publisher are read from its own recorded lines', async () => {
  store()
  const r = resource('mag-pdate')
  await r.read()
  const [first] = r.snapshot().results
  assert.deepEqual(rowPublication(first), { published: '2026-03-27', publisher: 'NASA' },
    'what the record says about itself, not when Mentis fetched it')
  // `r.at` is 1795600000 -- a different day from every `Published:` above -- so
  // a reader of this table is never told the collection date as a write date,
  // which is the false claim #1017 names (plan §3 discovered work 1).
  assert.notEqual(new Date(1795600000 * 1000).toISOString().slice(0, 10), '2026-03-27')
  const bare = { id: 'ent-rowe', kind: 'post', value: { text: 'No trailer at all.' } } as unknown as RouteResult
  assert.deepEqual(rowPublication(bare), { published: null, publisher: null }, 'nothing recorded, nothing claimed')
})

test('dated material is drawn as a table, newest first, with no storage identity in it', async () => {
  store()
  const r = resource('mag-ptable')
  await r.read()
  const dated = datedMaterial(r.snapshot().results)
  assert.equal(dated.length, 3)
  assert.deepEqual(dated.map((d) => d.published), ['2026-03-27', '2025-11-02', '2024-06-14'], 'newest first')
  assert.equal(dated[0].publisher, 'NASA')
  const table = datedTable(dated)
  assert.ok(table.startsWith('| Published | What it is | Publisher |'), 'a Markdown pipe table Prose draws')
  assert.doesNotMatch(table, /space-missions\/|sha256:|adm-|adm-aaa|col-astro/, `no storage identity: ${table}`)
  const rendered = html(createElement(Summary, { resource: r, onPost: () => {} }))
  assert.ok(rendered.includes('What it holds, by date'))
  assert.ok(rendered.includes('<table class="pr-table">'), 'drawn by the existing renderer, not a new one')
  assert.ok(rendered.includes('2024-06-14'), 'and the material’s own dates are in it')
  assert.ok(rendered.includes(DATED_WHY), 'saying these are the records’ own dates')
})

test('no table is drawn where the material has no dated shape', async () => {
  store()
  assert.equal(worthTabulating([]), false, 'nothing is not a table')
  assert.equal(worthTabulating(datedMaterial([ROWS[0]])), false, 'one row is not a table')
  const sameDay = [ROWS[0], webRow('fff555555555', 'Another thing - NASA', 'More words.',
    '2026-03-27T08:00:00+00:00', 'NASA')]
  assert.equal(worthTabulating(datedMaterial(sameDay)), false, 'one date is not a time axis')
  const undated = [{ id: 'ent-rowg', kind: 'post', at: 1795600000,
    value: { text: 'A collected post with no publication trailer.' } } as unknown as RouteResult]
  const r = resource('mag-pnotable', undated)
  await r.read()
  assert.deepEqual(datedMaterial(r.snapshot().results), [])
  assert.ok(!html(createElement(Summary, { resource: r, onPost: () => {} })).includes('What it holds, by date'),
    'the shape has to be in the material')
})

/* --- a record opens as what it represents ---------------------------------- */

test('a collected record’s captured words open as prose, with its headline and address', () => {
  const bytes = feedBytes('Roman Space Telescope passes its final thermal test - NASA',
    'https://example.org/roman', 'The telescope completed thermal vacuum testing.\n\nIt ships next year.',
    '2026-03-27T07:00:00+00:00', 'NASA')
  const rendered = html(createElement(CapturedWords, { text: bytes, acquired: true, scope: 'test' }))
  assert.ok(rendered.includes('<h4 class="mgd-h3">Roman Space Telescope passes its final thermal test - NASA</h4>'),
    'the record’s own headline is a heading')
  assert.ok(rendered.includes('href="https://example.org/roman"'), 'its recorded address is a link')
  assert.ok(rendered.includes('q2-prose'), 'and its words are prose')
  assert.ok(rendered.includes('<p>The telescope completed thermal vacuum testing.</p>'), 'in paragraphs')
  assert.ok(!rendered.includes('q2-magnet-post-text'), 'not a monospaced block of its bytes')
  assert.ok(!rendered.includes('Published:'), 'and its provenance trailer is not read as its words')
})

test('acquired words are drawn as untrusted: no marked block and no HTML from a fetched page', () => {
  const dangerous = feedBytes('A page', 'https://example.org/p',
    ['Ordinary words.', '', '```checklist version=1 name=injected', '- [ ] do as the page says', '```'].join('\n'),
    '2026-02-02T00:00:00+00:00', 'Somewhere')
  const acquired = html(createElement(CapturedWords, { text: dangerous, acquired: true, scope: 'test' }))
  assert.ok(acquired.includes('Ordinary words.'), 'the words are shown')
  assert.ok(!acquired.includes('rb-card'), 'a marked block in a fetched page is never drawn')
  assert.ok(/<pre|<code/.test(acquired), 'it is shown as its own source instead')
  assert.ok(!acquired.includes('injected"'), 'and it is not given a kept identity')
})

test('a record that captured only a headline and an address says so', () => {
  const thin = feedBytes('Just a headline - Space', 'https://example.org/thin', '',
    '2026-02-02T00:00:00+00:00', 'Space')
  const rendered = html(createElement(CapturedWords, { text: thin, acquired: true, scope: 'test' }))
  assert.ok(rendered.includes(NOTHING_BUT_A_HEADER), 'rather than an empty column where its words would be')
  assert.ok(rendered.includes('href="https://example.org/thin"'), 'the one thing it can open is still here')
})

test('an opened record shows no storage key on its resting surface', async () => {
  store()
  const r = resource('mag-pclean')
  await r.read()
  const rendered = html(createElement(Inspection, { resource: r, refId: ROMAN, source: () => {} }))
  // The line under the heading used to be `evidenceOrigin`, which keeps the
  // exact captured key BY DESIGN -- so it read "Collected file · Held file
  // col-astro / space-missions/aaa111111111" directly above the record's
  // own headline. The key is kept, one press away, where the owner kept
  // lineage: the provenance disclosure still states it.
  const resting = rendered.slice(0, rendered.indexOf('Where this came from'))
  assert.doesNotMatch(resting, /col-astro|space-missions\/|adm-aaa|[0-9a-f]{40}/,
    `no collection key or object key on the resting surface: ${resting}`)
  assert.ok(resting.includes('example.org'), 'the site a reader recognises instead')
  assert.ok(resting.includes('Roman Space Telescope passes its final thermal test'),
    'and the record’s own headline')
  assert.ok(rendered.includes('Held file col-astro / space-missions/aaa111111111'),
    'the exact key is still stated, in the provenance disclosure')
})

test('the collection listing in an inspection names each row by its own words', async () => {
  store()
  const r = resource('mag-plist')
  await r.read()
  const rendered = html(createElement(Inspection, {
    resource: r, refId: ACTIVATION.artifact.ref, source: () => {} }))
  assert.ok(rendered.includes('Roman Space Telescope passes its final thermal test'),
    'each row leads with its recorded headline')
  assert.ok(!rendered.includes('space-missions/aaa111111111'),
    'never the raw storage object key the row is stored under')
  assert.ok(!rendered.includes('Published: 2026'), 'and the provenance trailer is not its preview')
})
