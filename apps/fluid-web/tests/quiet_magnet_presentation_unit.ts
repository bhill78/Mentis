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
  BRIEFING_REWRITTEN, Briefing, CITED_ITEM, CITED_ITEMS, CITED_NOT_HELD, CITED_PART,
  CITED_PLACE_UNSHOWN, CITED_ROW, CITED_ROWS, DATED_WHY,
  WRITTEN_FROM,
  answerLines, answerRecordCount, answerSources, briefingGroups, citedPart, citedRows,
  collectionOverview, datedMaterial, datedTable, isWrittenBriefing,
  materialLead, namedSubjects, offeredQuestions, readFrozenAnswer, rowPublication, summaryFacts,
  unfused, withoutNarration, worthTabulating,
} from '../src/quiet2/magnets/Summary'
import { SOURCES_HEADING } from '../src/quiet2/magnets/links'
import { adapt } from '../src/quiet2/real'
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

test('a table split across recorded entries stays one table, each row’s own citations kept distinct (review ent-19c3c55af28c)', async () => {
  store()
  const r = resource('mag-ptablespan')
  await r.read()
  const ARTEMIS = ROWS[2].id
  // Three recorded entries: a header-and-divider-and-first-row entry, then two
  // orphan rows -- each citing a different record, the way different rows of
  // one table can be written from different sources.
  const rendered = html(createElement(Briefing, { resource: r, answer: answered([
    { text: '| Mission | Agency |\n|---|---|\n| Roman Space Telescope | NASA |', cites: [ROMAN] },
    { text: '| Europa Clipper | NASA |', cites: [CLIPPER] },
    { text: '| Artemis Programme | NASA |', cites: [ARTEMIS] },
  ]) }))
  assert.equal((rendered.match(/<table class="pr-table">/g) ?? []).length, 1,
    'the three recorded rows read as one table, not three broken fragments')
  assert.equal((rendered.match(/<tr>/g) ?? []).length, 4, 'header row plus all three data rows survive')
  assert.ok(rendered.includes('Artemis Programme'), 'the last orphan row is still in the table')
  assert.equal((rendered.match(new RegExp(WRITTEN_FROM, 'g')) ?? []).length, 3,
    'each row’s own citation is still shown, not merged into one set for the whole table')
  for (const id of [ROMAN, CLIPPER, ARTEMIS])
    assert.ok(rendered.includes(`id="cite-${id}"`), `${id}’s citation is still a press`)
})

test('an ordered list split across recorded entries keeps its numbering, each item’s own citations kept distinct', async () => {
  store()
  const r = resource('mag-plistspan')
  await r.read()
  const ARTEMIS = ROWS[2].id
  const rendered = html(createElement(Briefing, { resource: r, answer: answered([
    { text: '1. Roman Space Telescope cleared thermal testing.', cites: [ROMAN] },
    { text: '2. Europa Clipper refined its Mars gravity assist.', cites: [CLIPPER] },
    { text: '3. Artemis Programme narrowed its landing site.', cites: [ARTEMIS] },
  ]) }))
  assert.equal((rendered.match(/<ol class="pr-list">/g) ?? []).length, 1,
    'the three recorded items read as one list, not three separate one-item lists')
  assert.equal((rendered.match(/<li>/g) ?? []).length, 3, 'all three items survive in the one list')
  assert.equal((rendered.match(new RegExp(WRITTEN_FROM, 'g')) ?? []).length, 3,
    'each item’s own citation is still shown, not merged into one set for the whole list')
})

test('a paragraph split across recorded entries stays one paragraph, and complete statements never merge', async () => {
  store()
  const r = resource('mag-pparaspan')
  await r.read()
  const rendered = html(createElement(Briefing, { resource: r, answer: answered([
    { text: '## What launched', cites: [] },
    // Cut off mid-sentence (no terminal punctuation): continues into the next entry.
    { text: 'The **Roman Space Telescope** cleared thermal testing, and', cites: [ROMAN] },
    { text: 'Europa Clipper refined its Mars gravity assist.', cites: [CLIPPER] },
    // A complete sentence ending its own thought: never merged into what follows.
    { text: 'Both records were collected from the web search.', cites: [ROMAN, CLIPPER] },
  ]) }))
  assert.equal((rendered.match(/<p>/g) ?? []).length, 2,
    'the cut-off sentence and its continuation are one paragraph; the complete sentence after it is its own')
  assert.ok(/cleared thermal testing, and\s*\nEuropa Clipper refined/.test(rendered) ||
    rendered.includes('cleared thermal testing, and\nEuropa Clipper refined'),
    'the continuation reads as part of the same paragraph as what it continues')
  assert.equal((rendered.match(new RegExp(WRITTEN_FROM, 'g')) ?? []).length, 3,
    'each of the three recorded entries keeps its own citations, none implied for a statement it was not recorded against')
})

/* --- the correction for review ent-c0f9cca287b7 ----------------------------
   Two properties the first grouping correction left unmet. (1) Citations under
   a merged construct identified nothing: moving one from entry to entry
   produced byte-for-byte identical HTML, so the recorded attribution could not
   be read off the surface at all. (2) Entry splits a real answer can arrive in
   still broke the construct: two rows recorded in ONE entry, and a list item
   continued by a plain entry. Both are fixed here without touching the shared
   renderer -- the mapping is stated in each citation line, in the entry's own
   recorded words. ----------------------------------------------------------- */

/** Each citation line of a rendered briefing: its inner markup, and its words
 *  with the markup taken out, in the order they are drawn. */
const citeLines = (rendered: string) =>
  [...rendered.matchAll(/<p class="mgd-subtle">([\s\S]*?)<\/p>/g)].map((m) => ({
    markup: m[1], words: m[1].replace(/<[^>]+>/g, '').replace(/\s+/g, ' ').trim() }))

test('each citation under a merged table names the row it was recorded against (review ent-c0f9cca287b7)', async () => {
  store()
  const r = resource('mag-pattribrow')
  await r.read()
  const ARTEMIS = ROWS[2].id
  const entries = [
    { text: '| Mission | Agency |\n|---|---|\n| Roman Space Telescope | NASA |', cites: [ROMAN] },
    { text: '| Europa Clipper | NASA |', cites: [CLIPPER] },
    { text: '| Artemis Programme | Space |', cites: [ARTEMIS] },
  ]
  const rendered = html(createElement(Briefing, { resource: r, answer: answered(entries) }))
  assert.equal((rendered.match(/<table class="pr-table">/g) ?? []).length, 1, 'still one table')
  const lines = citeLines(rendered)
  assert.equal(lines.length, 3, 'one citation line per contributing entry')
  // The row each line names is that entry's own recorded cells, so a reader
  // scanning the drawn table finds the row a source supports.
  assert.ok(lines[1].words.startsWith(`${CITED_PART} 2, ${CITED_ROW} 2 “Europa Clipper · NASA” — ${WRITTEN_FROM}`),
    `the second row's line names that row: ${lines[1].words}`)
  assert.ok(lines[1].markup.includes(`id="cite-${CLIPPER}"`), 'and carries that row’s own citation')
  assert.ok(lines[2].words.startsWith(`${CITED_PART} 3, ${CITED_ROW} 3 “Artemis Programme · Space”`), lines[2].words)
  assert.ok(lines[0].words.startsWith(`${CITED_PART} 1, ${CITED_ROW} 1 “Roman Space Telescope · NASA”`),
    'the header is the table’s first line, not something a citation was recorded against')
  // THE PROBE THE REVIEW RAN: moving a citation from one entry to another must
  // change what the surface says. It used to produce identical HTML.
  const swapped = html(createElement(Briefing, { resource: r, answer: answered([
    { ...entries[0], cites: [] }, { ...entries[1], cites: [ROMAN, CLIPPER] }, entries[2]]) }))
  assert.notEqual(swapped, rendered, 'a citation that moves between entries moves what is rendered')
  const after = citeLines(swapped)
  assert.equal(after.length, 2, 'the entry that no longer cites anything shows no citation line')
  assert.ok(after[0].words.startsWith(`${CITED_PART} 2, ${CITED_ROW} 2 “Europa Clipper · NASA”`),
    'and the line that holds both citations still names the one row it was recorded against')
  assert.ok(after[0].markup.includes(`id="cite-${ROMAN}"`) && after[0].markup.includes(`id="cite-${CLIPPER}"`))
})

test('a citation whose row is not held leaves the surviving lines still named', async () => {
  store()
  const r = resource('mag-pattribunheld')
  await r.read()
  const rendered = html(createElement(Briefing, { resource: r, answer: answered([
    { text: '| Mission | Agency |\n|---|---|\n| Roman Space Telescope | NASA |', cites: ['adm-notinbatch11'] },
    { text: '| Europa Clipper | NASA |', cites: [CLIPPER] },
  ]) }))
  const lines = citeLines(rendered)
  assert.equal(lines.length, 1, 'a citation the batch shown does not hold is still dropped, not substituted')
  assert.ok(lines[0].words.startsWith(`${CITED_PART} 2, ${CITED_ROW} 2 “Europa Clipper · NASA”`),
    'and the line that remains names its own row, so it cannot be read as the first row’s')
})

test('two table rows recorded in one entry still join the table (review ent-c0f9cca287b7)', async () => {
  store()
  const r = resource('mag-ptworows')
  await r.read()
  const ARTEMIS = ROWS[2].id
  // The review's reproduction: a header with one row, then an entry holding TWO
  // orphan rows -- which rendered as literal pipes in a paragraph outside the
  // table, because a newline disqualified the fragment.
  const rendered = html(createElement(Briefing, { resource: r, answer: answered([
    { text: '| Mission | Agency |\n|---|---|\n| Roman Space Telescope | NASA |', cites: [ROMAN] },
    { text: '| Europa Clipper | NASA |\n| Artemis Programme | Space |', cites: [CLIPPER, ARTEMIS] },
  ]) }))
  assert.equal((rendered.match(/<table class="pr-table">/g) ?? []).length, 1, 'one table, not a table and a paragraph')
  assert.equal((rendered.match(/<tr>/g) ?? []).length, 4, 'header plus all three rows')
  assert.ok(!/<p>[^<]*\|/.test(rendered), 'no row is left as literal pipes in a paragraph')
  const lines = citeLines(rendered)
  assert.equal(lines.length, 2, 'each entry keeps its own citation line')
  assert.ok(lines[1].words.startsWith(`${CITED_PART} 2, ${CITED_ROWS} 2–3 “Europa Clipper · NASA”, “Artemis Programme · Space”`),
    `an entry of two rows names both: ${lines[1].words}`)
})

test('a list item continued in the next entry stays one item, numbering unbroken (review ent-c0f9cca287b7)', async () => {
  store()
  const r = resource('mag-plistcont')
  await r.read()
  // The review's reproduction: an item cut off mid-sentence, continued by a
  // plain entry, then the next item. It rendered as TWO lists with the
  // continuation between them, so the second list restarted at 1.
  const rendered = html(createElement(Briefing, { resource: r, answer: answered([
    { text: '1. Roman Space Telescope cleared thermal vacuum', cites: [ROMAN] },
    { text: 'testing at Goddard.', cites: [ROMAN] },
    { text: '2. Europa Clipper refined its Mars gravity assist.', cites: [CLIPPER] },
  ]) }))
  assert.equal((rendered.match(/<ol class="pr-list">/g) ?? []).length, 1,
    'one list, so the second item is the second item and not a new list numbered from 1')
  assert.equal((rendered.match(/<li>/g) ?? []).length, 2, 'the continuation is part of its item, not an item of its own')
  assert.ok(rendered.includes('Roman Space Telescope cleared thermal vacuum testing at Goddard.'),
    'the item reads as the one sentence it was written as')
  const lines = citeLines(rendered)
  assert.equal(lines.length, 3, 'all three entries keep their own citations')
  assert.ok(lines[0].words.startsWith(`${CITED_PART} 1, ${CITED_ITEM} 1 “Roman Space Telescope cleared thermal`), lines[0].words)
  assert.ok(lines[1].words.startsWith(`${CITED_PART} 2, ${CITED_ITEM} 1 “testing at Goddard.”`),
    'a continuation names the words it contributed and the item they were read into, not the whole item')
  assert.ok(lines[2].words.startsWith(`${CITED_PART} 3, ${CITED_ITEM} 2 “Europa Clipper refined its Mars gravity`), lines[2].words)
})

test('a construct that is complete is never merged into the one before it', async () => {
  store()
  const r = resource('mag-pboundary')
  await r.read()
  // TWO COMPLETE TABLES stay two: merging the second turns its header and
  // divider into data rows of the first.
  const tables = html(createElement(Briefing, { resource: r, answer: answered([
    { text: '| Mission | Agency |\n|---|---|\n| Roman Space Telescope | NASA |', cites: [ROMAN] },
    { text: '| Mission | Arrival |\n|---|---|\n| Europa Clipper | 2030 |', cites: [CLIPPER] },
  ]) }))
  assert.equal((tables.match(/<table class="pr-table">/g) ?? []).length, 2, 'two recorded tables are two tables')
  assert.equal((tables.match(/<tr>/g) ?? []).length, 4, 'each keeps its own header row')
  assert.ok(!tables.includes('<td>---</td>'), 'no divider is drawn as data')
  assert.equal(citeLines(tables).length, 2, 'each table’s citation sits under the table it was recorded against')
  for (const line of citeLines(tables))
    assert.ok(!line.words.includes('—'), 'a group of one entry needs no part: its citation sits under that one thing')
  // A STATEMENT THAT ENDS IN EMPHASISED PUNCTUATION is finished, and does not
  // swallow the statement after it.
  const emphasised = html(createElement(Briefing, { resource: r, answer: answered([
    { text: '## What launched', cites: [] },
    { text: '**Roman Space Telescope is ready to ship.**', cites: [ROMAN] },
    { text: 'Europa Clipper refined its Mars gravity assist.', cites: [CLIPPER] },
  ]) }))
  assert.equal((emphasised.match(/<p>/g) ?? []).length, 2,
    'the emphasised sentence closes, exactly as the same words unemphasised do')
  assert.equal(citeLines(emphasised).length, 2, 'and each keeps its own citation')
  // A LIST THAT IS FINISHED is not continued by the paragraph after it.
  const closed = html(createElement(Briefing, { resource: r, answer: answered([
    { text: '1. Roman Space Telescope cleared thermal vacuum testing.', cites: [ROMAN] },
    { text: 'Nothing in the collection records a launch.', cites: [CLIPPER] },
  ]) }))
  assert.equal((closed.match(/<ol class="pr-list">/g) ?? []).length, 1, 'the list is drawn once')
  assert.equal((closed.match(/<li>/g) ?? []).length, 1, 'and the paragraph after it is not an item of it')
  assert.ok(/<p>Nothing in the collection records a launch\.<\/p>/.test(closed), 'it is its own paragraph')
})

test('what a citation names is read out of the entry’s own characters', () => {
  assert.equal(citedPart('| 2026-03-27 | Roman | Cleared to ship |'),
    `${CITED_ROW} “2026-03-27 · Roman · Cleared to ship”`, 'a row is named by its own cells, in column order')
  assert.equal(citedPart('| Mission | Agency |\n|---|---|'), `${CITED_ROW} “Mission · Agency”`,
    'an entry that is only a header is named by that header')
  assert.equal(citedPart('3. First lunar-Earth gravity assist flown for **JUICE**.'),
    `${CITED_ITEM} “First lunar-Earth gravity assist flown for JUICE.”`,
    'an item is named by its words, without the markers the drawn item shows as emphasis')
  assert.equal(citedPart('- One\n- Two'), `${CITED_ITEMS} “One”, “Two”`, 'two items in one entry name both')
  const long = citedPart('The Roman Space Telescope finished thermal vacuum testing at Goddard and is cleared to ship, and')
  assert.ok(long.startsWith('“The Roman Space Telescope finished thermal'), long)
  assert.ok(long.endsWith('…”'), 'a long statement is cut at a word boundary, never reworded')
  assert.ok(long.length <= 60, `a label stays one quiet line (${long.length})`)
  // Grouping is what decides a construct, and it is readable on its own.
  const groups = briefingGroups([
    { text: '| A | B |\n|---|---|\n| 1 | 2 |', cites: [] },
    { text: '| 3 | 4 |', cites: [] },
    { text: 'A statement of its own.', cites: [] },
  ])
  assert.equal(groups.length, 2, 'the orphan row joins the table; the statement after it does not')
  assert.deepEqual(groups.map((g) => g.lines.length), [2, 1])
})

/* --- the correction for review ent-7ca49dfd8393 ----------------------------
   The second independent re-review ran seven reproductions against 188dfead
   and both of its properties failed on them. Each is reproduced here with the
   reviewer's own inputs, and one source id is reused across the whole group
   (as the reviewer did) so that source identity cannot be what distinguishes
   an occurrence.

   F1 -- four probes moved the group's only citation from one entry to the
   next and got byte-for-byte identical HTML: labels truncate at 56 characters
   with no collision handling, repeated wording labels identically, and a list
   label discarded its item number. The citation line now states WHICH
   recorded part of the group it is, and -- where the reader of the assembled
   body can determine it -- which drawn row or item that part produced.

   F2 -- three probes recorded an entry that BEGINS as a continuation and then
   carries further blocks. `continues` rejected every such entry outright, so
   a table lost its later rows to literal pipes, a list restarted at 1, and a
   sentence was split into two paragraphs. The continuation is now read from
   the entry's FIRST block, with the rest of the entry kept verbatim after it,
   and the join is confirmed with the renderer's own reader before it is
   taken. ------------------------------------------------------------------- */

/** The reviewer's long first cell: 66 characters, so two labels built from it
 *  are identical after the 56-character cut. */
const LONG_CELL = 'Roman Space Telescope completed the planned thermal vacuum testing'

/** One group rendered twice, with the only citation on a different entry each
 *  time: what the reviewer's probes compared. */
async function moved(id: `mag-${string}`, texts: string[], from: number, to: number) {
  store()
  const r = resource(id)
  await r.read()
  const at = (which: number) => answered(texts.map((text, i) => ({ text, cites: i === which ? [ROMAN] : [] })))
  return { before: html(createElement(Briefing, { resource: r, answer: at(from) })),
    after: html(createElement(Briefing, { resource: r, answer: at(to) })) }
}

test('a citation that moves between two identically worded table rows changes the surface (review ent-7ca49dfd8393 §1)', async () => {
  const texts = [
    `| Mission | Status |\n|---|---|\n| ${LONG_CELL} | ready |`,
    `| ${LONG_CELL} | delayed |`,
  ]
  const { before, after } = await moved('mag-pduprow', texts, 0, 1)
  assert.notEqual(before, after, 'the recorded attribution is readable off the surface, not identical HTML')
  assert.equal((before.match(/<table class="pr-table">/g) ?? []).length, 1, 'still one table')
  assert.ok(citeLines(before)[0].words.startsWith('Part 1, Row 1 '),
    `the first row's citation names row 1: ${citeLines(before)[0].words}`)
  assert.ok(citeLines(after)[0].words.startsWith('Part 2, Row 2 '),
    `and the second row's names row 2: ${citeLines(after)[0].words}`)
})

test('a citation that moves between two identical list items changes the surface (review ent-7ca49dfd8393 §2)', async () => {
  const texts = ['1. Calibration completed.', '2. Calibration completed.']
  const { before, after } = await moved('mag-pdupitem', texts, 0, 1)
  assert.notEqual(before, after, 'the item a source was recorded against is distinguishable')
  assert.equal((before.match(/<ol class="pr-list">/g) ?? []).length, 1, 'one list, as written')
  assert.ok(citeLines(before)[0].words.includes(`${CITED_ITEM} 1`), citeLines(before)[0].words)
  assert.ok(citeLines(after)[0].words.includes(`${CITED_ITEM} 2`),
    `the second item is named as the second: ${citeLines(after)[0].words}`)
})

test('a citation that moves between two fragments of one paragraph changes the surface (review ent-7ca49dfd8393 §3)', async () => {
  // As the reviewer worded it the two fragments differ, and their own words
  // already distinguish them; the case that collides is the same wording
  // recorded twice, which is checked second.
  const differing = await moved('mag-ppara', ['## Findings', 'The same pattern recurred and', 'the launch was delayed.'], 1, 2)
  assert.notEqual(differing.before, differing.after, 'moving the citation between fragments changes the surface')
  const REPEATED = 'the same pattern recurred and'
  const same = await moved('mag-pparadup', ['## Findings', REPEATED, REPEATED], 1, 2)
  assert.notEqual(same.before, same.after, 'and still does where the two fragments are worded identically')
  const lines = citeLines(same.after)
  assert.equal(lines.length, 1, 'only the entry that cites anything shows a citation line')
  assert.ok(lines[0].words.startsWith('Part 2 '),
    `a fragment inside a paragraph is named by which recorded part it is: ${lines[0].words}`)
  assert.equal((same.before.match(/<p>/g) ?? []).length, 1, 'the two fragments are the one paragraph they were written as')
})

/* --- the correction for re-review ent-a4a90e65e3d5 --------------------------
   The third independent re-review found the part and row/item numbers right --
   no incorrect row or item span, every earlier probe distinguishable -- and
   blocked one thing: in a paragraph, `Part 2` was all a label carried, and a
   reader takes that for the second occurrence of the words it quotes. It is
   not: it counts RECORDED ENTRIES, and one entry can hold two occurrences. Its
   A/B counterexample (`adm-3d3cc2b7dcd3`) is reproduced here with its own
   inputs, and the label now states that it cannot show the place.
   ------------------------------------------------------------------------- */

/** The reviewer's repeated phrase: open at both ends, so every entry of it
 *  merges into the one paragraph. */
const REPEATED_PHRASE = 'The same pattern recurred and'

test('a part number never passes for an occurrence of repeated prose (re-review ent-a4a90e65e3d5)', async () => {
  store()
  const r = resource('mag-poccurrence')
  await r.read()
  const render = (lines: { text: string; cites: string[] }[]) =>
    html(createElement(Briefing, { resource: r, answer: answered(lines) }))
  // THE REVIEWER'S A AND B: one drawn paragraph -- the phrase three times and
  // the clause that closes it -- assembled from four recorded entries and from
  // three, with the only citation recorded against part 2 both times. In A that
  // part produced the SECOND occurrence; in B, whose part 1 holds two of them,
  // the THIRD. Nothing in the record or the drawn body tells them apart.
  const a = render([
    { text: '## Findings', cites: [] },
    { text: REPEATED_PHRASE, cites: [] },
    { text: REPEATED_PHRASE, cites: [ROMAN] },
    { text: REPEATED_PHRASE, cites: [] },
    { text: 'the launch was delayed.', cites: [] },
  ])
  const b = render([
    { text: '## Findings', cites: [] },
    { text: `${REPEATED_PHRASE}\n${REPEATED_PHRASE}`, cites: [] },
    { text: REPEATED_PHRASE, cites: [ROMAN] },
    { text: 'the launch was delayed.', cites: [] },
  ])
  const body = [REPEATED_PHRASE, REPEATED_PHRASE, REPEATED_PHRASE, 'the launch was delayed.'].join('\n')
  for (const [which, rendered] of [['A', a], ['B', b]] as const) {
    assert.ok(rendered.includes(`<p>${body}</p>`), `${which}: all three occurrences are the one paragraph`)
    const lines = citeLines(rendered)
    assert.equal(lines.length, 1, `${which}: only the entry that cites anything shows a citation line`)
    assert.ok(lines[0].words.startsWith(`${CITED_PART} 2 (${CITED_PLACE_UNSHOWN})`),
      `${which}: the recorded part is stated and qualified in plain words: ${lines[0].words}`)
    assert.ok(lines[0].words.includes(`“${REPEATED_PHRASE}”`),
      `${which}: the recorded words are still quoted: ${lines[0].words}`)
    assert.doesNotMatch(lines[0].words, /(Row|Item)s? \d/,
      `${which}: and no drawn row or item is claimed: ${lines[0].words}`)
    assert.ok(lines[0].markup.includes(`id="cite-${ROMAN}"`), `${which}: the citation itself is unchanged`)
  }
  // The two assemblies draw the same body and say the same thing about it --
  // which is the point: the surface cannot distinguish the occurrence, and no
  // longer reads as though it had.
  assert.equal(a, b, 'identical output, and neither claims a position the record does not hold')
})

test('a stated row or item position is kept, and only an unstated one is qualified (re-review ent-a4a90e65e3d5)', async () => {
  store()
  const r = resource('mag-pknownplace')
  await r.read()
  const render = (lines: { text: string; cites: string[] }[]) =>
    html(createElement(Briefing, { resource: r, answer: answered(lines) }))
  // KNOWN POSITIONS ARE UNTOUCHED by the correction: where the body's own
  // reader gave the rows or items an entry produced, they are still the number
  // a reader counts to, and nothing is qualified.
  const rows = citeLines(render([
    { text: '| Mission | Status |\n|---|---|\n| Roman | ready |', cites: [ROMAN] },
    { text: '| Europa | refined |\n| JUICE | flown |', cites: [CLIPPER] },
  ]))
  assert.ok(rows[0].words.startsWith(`${CITED_PART} 1, ${CITED_ROW} 1 `), rows[0].words)
  assert.ok(rows[1].words.startsWith(`${CITED_PART} 2, ${CITED_ROWS} 2–3 `), rows[1].words)
  const items = citeLines(render([
    { text: '1. Roman completed thermal vacuum', cites: [ROMAN] },
    { text: 'testing at Goddard.\n2. Europa refined its assist.', cites: [CLIPPER] },
  ]))
  assert.ok(items[0].words.startsWith(`${CITED_PART} 1, ${CITED_ITEM} 1 `), items[0].words)
  assert.ok(items[1].words.startsWith(`${CITED_PART} 2, ${CITED_ITEMS} 1–2 `), items[1].words)
  for (const line of [...rows, ...items])
    assert.ok(!line.words.includes(CITED_PLACE_UNSHOWN),
      `a position the body gave is not qualified away: ${line.words}`)
  // AN UNSTATED POSITION INSIDE A NUMBERED CONSTRUCT, the reviewer's other
  // unknown-position case: an entry whose words crossed a heading and the first
  // item has no item number to give, and a bare `Item` is nothing to count to.
  // The label says what is not shown; the entry after it still says `Item 2`.
  const mixed = citeLines(render([
    { text: '## Findings\n\n1. Calibration completed.', cites: [ROMAN] },
    { text: '2. Calibration completed.', cites: [CLIPPER] },
  ]))
  assert.ok(mixed[0].words.startsWith(`${CITED_PART} 1 (${CITED_PLACE_UNSHOWN})`), mixed[0].words)
  assert.doesNotMatch(mixed[0].words, new RegExp(`${CITED_ITEM}s? \\d`),
    `no item number where the body gave none: ${mixed[0].words}`)
  assert.ok(mixed[1].words.startsWith(`${CITED_PART} 2, ${CITED_ITEM} 2 `), mixed[1].words)
  // A GROUP OF ONE is labelled with nothing at all, qualification included.
  assert.equal(citedPart('| 2026-03-27 | Roman | Cleared to ship |'),
    `${CITED_ROW} “2026-03-27 · Roman · Cleared to ship”`, 'no part, no position, no qualification')
})

test('list labels that collide after truncation still name their own item (review ent-7ca49dfd8393 §4)', async () => {
  const texts = [`1. ${LONG_CELL} and is ready.`, `2. ${LONG_CELL} and is delayed.`]
  const { before, after } = await moved('mag-ptruncitem', texts, 0, 1)
  assert.notEqual(before, after, 'a label cut at 56 characters is no longer all that identifies the item')
  const [one] = citeLines(before), [two] = citeLines(after)
  assert.notEqual(one.words, two.words, `${one.words} / ${two.words}`)
  assert.ok(one.words.startsWith(`Part 1, ${CITED_ITEM} 1 `) && two.words.startsWith(`Part 2, ${CITED_ITEM} 2 `),
    `${one.words} / ${two.words}`)
})

test('an entry of orphan rows and a paragraph keeps both (review ent-7ca49dfd8393 F2 §1)', async () => {
  store()
  const r = resource('mag-prowspara')
  await r.read()
  const rendered = html(createElement(Briefing, { resource: r, answer: answered([
    { text: '| Mission | Status |\n|---|---|\n| Roman | ready |', cites: [ROMAN] },
    { text: '| Europa | refined |\n| JUICE | flown |\n\nThese are completed tests.', cites: [CLIPPER] },
  ]) }))
  assert.equal((rendered.match(/<table class="pr-table">/g) ?? []).length, 1, 'one table')
  assert.equal((rendered.match(/<tr>/g) ?? []).length, 4, 'header plus all three rows')
  assert.ok(!/<p>[^<]*\|/.test(rendered), 'no row is left as literal pipes in a paragraph')
  assert.ok(/<p>These are completed tests\.<\/p>/.test(rendered), 'and the entry’s own paragraph is still a paragraph')
  const lines = citeLines(rendered)
  assert.equal(lines.length, 2, 'each entry keeps its own citation line')
  assert.ok(lines[1].words.startsWith(`Part 2, ${CITED_ROWS} 2–3 `), lines[1].words)
})

test('an entry that continues a list item and then starts the next keeps one list (review ent-7ca49dfd8393 F2 §2)', async () => {
  store()
  const r = resource('mag-plistmixed')
  await r.read()
  const rendered = html(createElement(Briefing, { resource: r, answer: answered([
    { text: '1. Roman completed thermal vacuum', cites: [ROMAN] },
    { text: 'testing at Goddard.\n2. Europa refined its assist.', cites: [CLIPPER] },
  ]) }))
  assert.equal((rendered.match(/<ol class="pr-list">/g) ?? []).length, 1,
    'one list, so the second item is the second and not a new list numbered from 1')
  assert.equal((rendered.match(/<li>/g) ?? []).length, 2, 'two items')
  assert.ok(rendered.includes('Roman completed thermal vacuum testing at Goddard.'),
    'the first item reads as the one sentence it was written as')
  assert.ok(!/<p>testing at Goddard\.<\/p>/.test(rendered), 'the continuation is not a paragraph between two lists')
  const lines = citeLines(rendered)
  assert.equal(lines.length, 2, 'each entry keeps its own citation line')
  assert.ok(lines[1].words.startsWith(`${CITED_PART} 2, ${CITED_ITEMS} 1–2 `),
    `an entry that finished one item and started the next names both: ${lines[1].words}`)
})

test('a join the body’s own reader does not confirm is not taken (review ent-7ca49dfd8393)', async () => {
  store()
  const r = resource('mag-pnotconfirmed')
  await r.read()
  // An entry whose rows are followed by a table OF ITS OWN: appending the lot
  // would feed the second table's header and divider to the first as data rows.
  // The entry stays its own body instead -- its leading row is then drawn as the
  // pipes it is, which is a visible shortcoming and not a corrupted table.
  const rendered = html(createElement(Briefing, { resource: r, answer: answered([
    { text: '| Mission | Status |\n|---|---|\n| Roman | ready |', cites: [ROMAN] },
    { text: '| Europa | refined |\n| Mission | Arrival |\n|---|---|\n| JUICE | 2031 |', cites: [CLIPPER] },
  ]) }))
  assert.equal((rendered.match(/<table class="pr-table">/g) ?? []).length, 2, 'two tables, as recorded')
  assert.ok(!rendered.includes('<td>---</td>'), 'no divider is drawn as data')
  assert.ok(!/<td>Mission<\/td>/.test(rendered), 'and no header is drawn as data')
  assert.equal(citeLines(rendered).length, 2, 'both citations are still shown')
  for (const line of citeLines(rendered))
    assert.ok(!line.words.includes(`${CITED_PART} `), 'and neither claims to be a part of the other’s construct')
})

test('an entry that continues a sentence and then carries a heading keeps the sentence whole (review ent-7ca49dfd8393 F2 §3)', async () => {
  store()
  const r = resource('mag-pparamixed')
  await r.read()
  const rendered = html(createElement(Briefing, { resource: r, answer: answered([
    { text: '## Findings\n\nRoman completed thermal vacuum', cites: [ROMAN] },
    { text: 'testing at Goddard.\n\n## Implications\n\nLaunch preparations continue.', cites: [CLIPPER] },
  ]) }))
  assert.equal((rendered.match(/<p>/g) ?? []).length, 2,
    'the split sentence is one paragraph, and the conclusion the other')
  assert.ok(/<p>Roman completed thermal vacuum\s*testing at Goddard\.<\/p>/.test(rendered),
    `the sentence is not split across paragraphs: ${rendered}`)
  assert.ok(rendered.includes('Implications'), 'and the entry’s own later heading is still a heading')
  assert.equal((rendered.match(/class="pr-h pr-h2"/g) ?? []).length, 2, 'both headings drawn once, as headings')
})

test('ordinary prose keeps one citation line per statement, unnumbered and unmerged', async () => {
  store()
  const r = resource('mag-pordinary')
  await r.read()
  // THE NORMAL CASE, which the correction must not disturb: complete sentences,
  // each recorded on its own, each with its own citation. Nothing is merged, so
  // no entry is a part of anything and no label is added at all.
  const rendered = html(createElement(Briefing, { resource: r, answer: answered([
    { text: '## What launched', cites: [] },
    { text: 'The Roman Space Telescope completed thermal vacuum testing at Goddard.', cites: [ROMAN] },
    { text: 'Europa Clipper refined its Mars gravity assist.', cites: [CLIPPER] },
  ]) }))
  assert.equal((rendered.match(/<p>/g) ?? []).length, 2, 'two statements, two paragraphs')
  const lines = citeLines(rendered)
  assert.equal(lines.length, 2, 'one citation line each')
  for (const line of lines) {
    assert.ok(line.words.startsWith(WRITTEN_FROM), `no part label where nothing was merged: ${line.words}`)
    assert.ok(!/Part \d/.test(line.words), line.words)
  }
  const groups = briefingGroups(answerLines(answered([
    { text: 'The Roman Space Telescope completed thermal vacuum testing at Goddard.', cites: [ROMAN] },
    { text: 'Europa Clipper refined its Mars gravity assist.', cites: [CLIPPER] },
  ])))
  assert.equal(groups.length, 2, 'two finished statements are two groups')
  assert.deepEqual(groups.map((g) => g.places.map((p) => p.part)), [[1], [1]],
    'each is the first and only recorded part of its own group')
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

/* --- the answer, not the account of writing it ------------------------------
   Owner `ent-bce57ba67f38`: "Summary and Perspectives should present
   substantive, readable synthesized information, not agent narration,
   collection history, execution details or internal instructions ... display
   the final answer, not intermediate agent commentary."

   The preamble below is the one the owner read, frozen verbatim into a written
   briefing by `perspectives_work.finalize`. ------------------------------- */

const PREAMBLE = "I'll read the frozen question, collection records, manifest, and evidence, then trace the briefing's claims back to the retained rows."
const ANSWER_OPENS = 'The collection holds three records of space missions, all of them dated.'

/* THE EXACT CHARACTERS TEST's RUNNING CANDIDATE HOLDS, read back from
   GET /api/turns/ent-116c910c16c2 (the reply `finalize` froze for
   mag-265878e92e5c987c's standing question on 20261126-94928a5): one text part
   in which the agent's blocks are already fused, apostrophes curled. */
const TEST_FROZEN = 'I’ll read the frozen question, collection records, manifest, and evidence, then trace the briefing’s claims to the exact retained sources.The collection combines a few full NASA articles with many search-result records that retain only headlines and metadata. That distinction matters: several reported discoveries and launch claims can be identified, but their underlying evidence is not present in the frozen rows.The collection’s strongest theme is **how observations become more useful when missions and methods complement one another**.'

test('two sentences the record itself fused are separated, by the one space that is missing', () => {
  assert.ok(unfused(TEST_FROZEN).includes('retained sources. The collection combines'))
  assert.ok(unfused(TEST_FROZEN).includes('frozen rows. The collection’s strongest theme'))
  assert.ok(!unfused(TEST_FROZEN).includes('sources.The'))
  assert.equal(unfused(TEST_FROZEN).replace(/ /g, ''), TEST_FROZEN.replace(/ /g, ''),
    'nothing but spaces is added: every other character is the recorded one')
})

test('ONLY A DEFECT IS REPAIRED, and source is never touched', () => {
  for (const words of [
    'Version 1.2Beta was the build.',                       // a decimal
    'The U.S. Navy reported it.',                           // an abbreviation
    'See example.com/Path for it.',                         // an address
    'It is at x.ORG now.',                                  // not a sentence either side
    'The call is `perspectives_work.Finalize` in Python.',   // inline code
    '```\nconst a = b.Then(c)\n```',                        // a fenced block
    '    const a = b.Then(c)',                              // an indented block
    '| a.Then | b |',                                       // a table row keeps its shape
  ]) assert.equal(unfused(words), words, JSON.stringify(words))
})

test('TEST’s own frozen answer is read as the answer, with its blocks apart', () => {
  const read = withoutNarration(TEST_FROZEN)
  assert.ok(read.startsWith('The collection combines a few full NASA articles'),
    `the narrated sentence goes and the answer leads: ${read.slice(0, 90)}`)
  assert.ok(!read.includes('I’ll read the frozen question'), 'no agent narration in what is drawn')
  assert.ok(read.includes('frozen rows. The collection’s strongest theme'),
    'and the fused sentences inside the answer are apart')
})

test('a frozen answer that opens by narrating the agent’s work is read from the answer', () => {
  assert.equal(withoutNarration(`${PREAMBLE} ${ANSWER_OPENS}`), ANSWER_OPENS,
    'the narrated sentence goes; the answer’s own first sentence leads')
  assert.equal(withoutNarration(`${PREAMBLE}\n\n${ANSWER_OPENS}`), ANSWER_OPENS,
    'a narrated paragraph of its own goes whole')
  assert.equal(withoutNarration(`Okay, I will check each row first. Let me start there.\n\n${ANSWER_OPENS}`),
    ANSWER_OPENS, 'two narrated sentences, and a filler in front of one, go together')
})

test('NOTHING BUT A LEADING NARRATION IS TOUCHED', () => {
  for (const words of [
    ANSWER_OPENS,
    `## What this Magnet holds\n\n${ANSWER_OPENS}`,
    'I found no record of a launch in this collection.',
    `${ANSWER_OPENS}\n\nI'll note that two rows share a publisher.`,
    '- I will check this\n- and this',
    '> I will read the records first.',
    '',
  ]) assert.equal(withoutNarration(words), words, JSON.stringify(words))
})

test('an answer that is NOTHING but narration is shown as the answer it is', () => {
  // Stripping to nothing would hand the owner an empty card and hide the
  // defect; the words are what the record holds.
  assert.equal(withoutNarration(PREAMBLE), PREAMBLE)
  assert.equal(withoutNarration(`${PREAMBLE}\n\nLet me begin.`), `${PREAMBLE}\n\nLet me begin.`)
})

/* --- and the bookkeeping a run closes with ---------------------------------
   The owner read this paragraph in the narration strip's own screenshots. It
   is the closing paragraph of the frozen reply for `mag-265878e92e5c987c`,
   character for character as `tests/quiet_magnet_answer_read_fixture.ts`
   holds it (read off TEST's running candidate, release 20261126-94928a5). */

const CLOSING_BOOKKEEPING = 'The frozen question for Topic `ent-85f547319077` is **answered** here and in the returned briefing, `adm-3cfefbd3d5ad`. The cited versions and byte ranges identify the retained collection text. All configured sources in the extract returned successfully, but the underlying articles behind headline-only rows were not present in the frozen evidence. Nothing is required from the owner.'

const ANSWER_CLOSES = 'The collection also contains headline leads on a lunar cave-search mission. Their schedules remain to be examined in the underlying sources. [adm-3e19e38b2e11@c316d56ffd24[0:818]]'

test('the bookkeeping a run CLOSES with is read out of the answer, as the opening narration is', () => {
  assert.equal(withoutNarration(`${ANSWER_OPENS}\n\n${ANSWER_CLOSES}\n\n${CLOSING_BOOKKEEPING}`),
    `${ANSWER_OPENS}\n\n${ANSWER_CLOSES}`,
    'the closing paragraph goes whole; the answer’s own last paragraph -- which cites records by reference -- stays')
  /* The opening narration, the answer, the closing bookkeeping and the claim
     trailer Mentis appends: the shape the owner's own reply actually has. */
  const read = withoutNarration(
    `${PREAMBLE}\n\n${ANSWER_OPENS}\n\n${CLOSING_BOOKKEEPING}\n\nClaim by @Caretaker: met — Answered it. (the agent's claim; what Mentis recorded is shown with the work)`)
  assert.equal(read, ANSWER_OPENS, 'what is drawn is the answer, with neither end’s bookkeeping')
  assert.ok(!/\b(?:ent|adm)-[0-9a-f]{12}\b/.test(read), 'and no bare reference id is left in it')
})

test('A TRAILING PARAGRAPH IS ONLY READ AS BOOKKEEPING WHERE IT IS RECOGNISABLY THAT', () => {
  for (const words of [
    // ordinary prose that ends a paragraph, naming no reference id
    `${ANSWER_OPENS}\n\nNothing is required from the owner to read them.`,
    // an answer's own citing paragraph: reference ids, but none of the phrases
    `${ANSWER_OPENS}\n\n${ANSWER_CLOSES}`,
    // the phrases inside a construct the author wrote, not running prose
    `${ANSWER_OPENS}\n\n> The frozen question for Topic \`ent-85f547319077\` is answered.`,
    `${ANSWER_OPENS}\n\n- The frozen question for Topic \`ent-85f547319077\` is answered.`,
    // the whole answer is that paragraph: shown as the answer it is
    CLOSING_BOOKKEEPING,
  ]) assert.equal(withoutNarration(words), words, JSON.stringify(words))
})

test('only the bookkeeping SENTENCES of a closing paragraph go', () => {
  const para = `The collection holds no launch date for it. The frozen question for Topic \`ent-85f547319077\` is answered here. Nothing is required from the owner.`
  assert.equal(withoutNarration(`${ANSWER_OPENS}\n\n${para}`),
    `${ANSWER_OPENS}\n\nThe collection holds no launch date for it.`,
    'the answer’s own sentence keeps its place and its characters')
})

test('the frozen words of a run’s answer are read without its preamble', async () => {
  const parts = [{ type: 'text', text: `${PREAMBLE}\n\n${ANSWER_OPENS}` }]
  const body = new TextEncoder().encode(JSON.stringify({ parts }))
  const digest = [...new Uint8Array(await crypto.subtle.digest('SHA-256', body))]
    .map((n) => n.toString(16).padStart(2, '0')).join('')
  const event = { post: 'ent-answer111', perspective: 'ent-topic111', kind: 'answered',
    at: WHEN, data: { answer_post: 'ent-reply111', execution: 'exec-1',
      answer: { ref: 'adm-frozen111111', digest, size: body.byteLength } },
    snapshot: { ref: 'adm-frozen111111' } } as unknown as InquiryEvent
  const was = globalThis.fetch
  globalThis.fetch = (async () => ({ ok: true, arrayBuffer: async () => body.buffer })) as unknown as typeof fetch
  try {
    assert.equal(await readFrozenAnswer(event), ANSWER_OPENS,
      'the package still verifies whole; what is READ is the answer')
  } finally { globalThis.fetch = was }
})

/* --- a citation as a number, with its source named ------------------------- */

const citeOf = (r: RouteResult) => String((r as unknown as { value: { citation: string } }).value.citation)

test('the sources an answer cites are numbered from the rows the collection holds', () => {
  const said = `The collection combines ${citeOf(ROWS[0])} and ${citeOf(ROWS[1])}, and returns to ${citeOf(ROWS[0])}.`
  const opened: string[] = []
  const notes = answerSources([said], ROWS, (id) => opened.push(id))
  assert.deepEqual(notes.map((s) => s.n), [1, 2], 'one number per record, not per mention')
  assert.equal(notes[0].title, 'Roman Space Telescope passes its final thermal test - NASA',
    'named by the row’s own headline, through the mapping the statement citations already use')
  assert.match(notes[0].detail, /example\.org/, 'with the site a reader recognises')
  assert.match(notes[0].detail, /captured /, 'and when it was captured')
  assert.doesNotMatch(notes.map((s) => `${s.title} ${s.detail}`).join(' '),
    /adm-|[0-9a-f]{40}|space-missions\//,
    'no reference, held-file key or digest in what the reader is shown')
  notes[0].open?.()
  assert.deepEqual(opened, [ROMAN], 'and the entry opens the captured record')
})

test('a cited record this collection does not hold is named, and nothing is substituted', () => {
  const notes = answerSources(['It rests on adm-999999999999@999999999999[0:10].'], ROWS, () => {})
  assert.equal(notes.length, 1)
  assert.equal(notes[0].title, CITED_NOT_HELD)
  assert.equal(notes[0].open, null)
})

test('A WRITTEN BRIEFING’S CITATIONS ARE NUMBERS, AND ITS SOURCES ARE LISTED', async () => {
  store()
  const r = resource('mag-pcite')
  await r.read()
  const words = [
    '## What this Magnet has gathered',
    '',
    `Three missions are recorded. The Roman thermal test ${citeOf(ROWS[0])} and the Europa Clipper burn ${citeOf(ROWS[1])} are the two most recent.`,
    '',
    `The Artemis site selection ${citeOf(ROWS[2])} is the earliest of them.`,
  ].join('\n')
  const answer = { post: 'ent-answer222', perspective: 'ent-topic222', kind: 'answered', at: WHEN,
    data: { text: words }, snapshot: { ref: 'adm-snap222222' } } as unknown as InquiryEvent
  const rendered = html(createElement(Briefing, { resource: r, answer }))
  const read = rendered.replace(/<[^>]*>/g, '')
  assert.ok(isWrittenBriefing(words), 'this is the written-document case')
  assert.match(rendered, /<h[1-6] class="pr-h/, 'drawn by the Markdown renderer Fluid already has')
  for (const n of ['[1]', '[2]', '[3]']) assert.ok(rendered.includes(n), `${n}: ${rendered}`)
  assert.doesNotMatch(read, /adm-|@aaaaaaaaaaaa|0:\d{3}|space-missions\//,
    `no reference, digest, byte range or held-file key in what is read: ${read}`)
  assert.ok(read.includes(SOURCES_HEADING), 'and what each number is, is said under the answer')
  assert.ok(read.includes('Roman Space Telescope passes its final thermal test')
    && read.includes('Artemis Programme names the Artemis III landing site'),
  'each by the record’s own words')
  assert.ok(rendered.includes('data-cite='), 'the recorded token is kept on the element it replaced')
})

/* --- two recorded blocks that met with no character between them ----------- */

const adapted = (parts: unknown[]) => {
  const turn = { id: 'ent-fuse1111111', author: 'ent-who1111111', author_alias: '@who',
    at: WHEN, number: 3, parts } as unknown as Parameters<typeof adapt>[0]
  const post = adapt(turn, 'ent-conv1111111', () => undefined)
  const md = post.blocks.find((b) => b.kind === 'text') as { md: string } | undefined
  return { md: md?.md ?? '', stored: post.text ?? '' }
}

test('two text parts that would fuse into one sentence are drawn as two blocks', () => {
  const got = adapted([
    { type: 'text', text: 'Each claim is traced to the exact retained sources.' },
    { type: 'text', text: 'The collection combines a feed and a page.' },
  ])
  assert.ok(got.md.includes('sources.\n\nThe collection'),
    `the two recorded blocks are two paragraphs: ${JSON.stringify(got.md)}`)
  assert.ok(!got.md.includes('sources.The'), 'and never a sentence nobody wrote')
  assert.equal(got.stored,
    'Each claim is traced to the exact retained sources.The collection combines a feed and a page.',
    'the STORED characters are untouched: the edit box compares and saves these')
})

test('nothing else about the join changes: a continued sentence, and an inline reference', () => {
  assert.equal(adapted([{ type: 'text', text: 'The collection combines a feed ' },
    { type: 'text', text: 'and a page.' }]).md,
  'The collection combines a feed and a page.', 'a continued sentence is one sentence')
  assert.equal(adapted([{ type: 'text', text: 'Recorded against ' },
    { type: 'turn', text: 'ent-abc123abc123' }, { type: 'text', text: ' in that Conversation.' }]).md,
  'Recorded against ent-abc123abc123 in that Conversation.', 'an inline reference stays inline')
  assert.equal(adapted([{ type: 'text', text: 'It is done.' },
    { type: 'text', text: ' Next it is read.' }]).md,
  'It is done. Next it is read.', 'a part that already begins with a space needs nothing')
})
