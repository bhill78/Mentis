/** CLICKABLE LINKS, AND STATEMENTS LAID OUT TO BE READ.
 *
 *  The owner approved the Magnet and asked for one refinement (ent-0b4f3f69b836):
 *  "The summaries and replies about the information could be formatted a bit
 *  better. Include clickable links and maybe slightly better formatting for
 *  reading". On the deployed candidate `20261125-5294531-f4e3ecd4` a collected
 *  web row led with its held-file key -- the owner's own Magnet showed
 *  "space-missions-and-astronomy-what-launch/a733ec1ec5e51a4b" -- while the
 *  article's headline and its address sat as plain text in the preview.
 *
 *  What this file pins is the two halves of that, and the three things the fix
 *  must not do:
 *
 *    - the address a row shows is the one PART W RECORDED, read out of the
 *      row's own captured bytes, and no address is constructed from a key;
 *    - a row that is not web-shaped -- a README, a Git file, a collected post,
 *      a feed entry with no link of its own -- keeps exactly the title, preview
 *      and byline it had;
 *    - a statement is laid out, never edited: every character of a recorded
 *      answer comes back, and nothing new is claimed.
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import {
  Citations, Linked, SOURCES_HEADING, SourceNotes, citedInline, citedRefs,
  heldHeader, linkHost, linkPieces, restates, rowBody, rowHeadline, rowLink, saidIn, shortLink,
  statement,
} from '../src/quiet2/magnets/links'
import { resultPreview, resultTitle, rowByline } from '../src/quiet2/magnets/EvidenceViews'
import { collectedExcerpts } from '../src/quiet2/magnets/Summary'
import type { RouteResult } from '../src/fluid/surface/magnet/route'

const WHEN = Date.parse('2026-11-23T17:08:00Z') / 1000

/* The exact bytes TEST's own collection holds for one row of the owner's
   Magnet `mag-265878e92e5c987c`, read from
   GET /fluid/api/magnets/<id>/collection on release 20261125-5294531-f4e3ecd4.
   The shape is `mentis/sources/feeds.py` `_entry_body`'s. */
const FEED_TEXT = [
  'Juno - NASA Science (.gov)',
  '',
  'https://news.google.com/rss/articles/CBMiT0FVX3lxTE45Yy1LbDRvVGs5VXJwS0FzWEZrVnMwb3N0VGRNaXNQd1FtZVdDeGVxWjNyejFHY0dmU3BXdmJPVGZlS2ZGSWNzVnNmQnhRVXc?oc=5',
  '',
  'Juno NASA Science (.gov)',
  '',
  '--',
  'Published: 2011-08-05T07:00:00+00:00',
  'Publisher: news.google.com',
  'Results are Google News links; each links to its publisher.',
  'Entry id (guid): https://news.google.com/rss/articles/CBMiT0FV',
].join('\n')
const FEED_LINK = 'https://news.google.com/rss/articles/CBMiT0FVX3lxTE45Yy1LbDRvVGs5VXJwS0FzWEZrVnMwb3N0VGRNaXNQd1FtZVdDeGVxWjNyejFHY0dmU3BXdmJPVGZlS2ZGSWNzVnNmQnhRVXc?oc=5'

/* `mentis/sources/webpages.py` `_page_body`: the material follows the address
   with no blank line between them. */
const PAGE_TEXT = [
  'Europa Clipper completes its Mars gravity assist',
  '',
  'https://science.nasa.gov/mission/europa-clipper/',
  'The spacecraft passed 550 miles above the Martian surface on 1 March,',
  'trimming its arrival at Jupiter to April 2030.',
].join('\n')

const webRow = (text = FEED_TEXT): RouteResult => ({
  kind: 'file', id: 'adm-eae23465f170', version: 'adm-eae23465f170', at: WHEN,
  conversation: null, author: null,
  value: { collection: 'col-fea202869d76', path: 'space-missions-and-astronomy-what-launch/a733ec1ec5e51a4b', text },
  ...{ via: 'held-source' },
} as unknown as RouteResult)

const readme = (): RouteResult => ({ kind: 'file', id: 'adm-5260ed8d10f2', at: WHEN,
  value: { collection: 'col-5260ed8d10f2', path: 'README.md', text: '# Disposable audit folder\n\nNotes kept here.' },
  ...{ via: 'held-source' } } as unknown as RouteResult)

const post = (): RouteResult => ({ kind: 'post', id: 'ent-0d2c70c474ec', conversation: 'ent-a1d2c5e714ea',
  author: 'ent-5936369158a8', at: WHEN, number: 1,
  value: { parts: [{ type: 'text', text: 'Synthetic retained acceptance post.' }] } } as unknown as RouteResult)

/* --- the recorded header, read back ---------------------------------------- */

test('a feed entry’s recorded header gives its headline, its permalink and its words', () => {
  const got = heldHeader(FEED_TEXT)
  assert.equal(got.headline, 'Juno - NASA Science (.gov)')
  assert.equal(got.link, FEED_LINK, 'the address recorded, character for character')
  assert.equal(got.body, 'Juno NASA Science (.gov)',
    'the entry’s own words, without the `--` trailer the feed recorded about it')
})

test('a web page’s recorded header gives the same three things, with no blank line to skip', () => {
  const got = heldHeader(PAGE_TEXT)
  assert.equal(got.headline, 'Europa Clipper completes its Mars gravity assist')
  assert.equal(got.link, 'https://science.nasa.gov/mission/europa-clipper/')
  assert.ok(got.body.startsWith('The spacecraft passed 550 miles'), got.body)
  assert.ok(got.body.endsWith('April 2030.'), got.body)
})

test('a page with no title of its own has an address where a headline goes, and that is not a headline', () => {
  const url = 'https://example.org/launch-report'
  const got = heldHeader([url, '', url, '', 'The report.'].join('\n'))
  assert.equal(got.headline, null, 'the address is already the link; it is not shown twice')
  assert.equal(got.link, url)
  assert.equal(got.body, 'The report.')
})

test('NOTHING THAT IS NOT WEB-SHAPED IS TOUCHED', () => {
  for (const text of [
    '# Disposable audit folder\n\nNotes kept here.',          // a README
    'A newly arrived record about calibration drift.',        // one line
    'Title\n\nA feed entry that recorded no link of its own.', // feeds.py, no link
    'Title\nhttps://example.org/x\nno blank line above',      // not the header shape
    '',
  ]) {
    const got = heldHeader(text)
    assert.equal(got.link, null, `no address read from ${JSON.stringify(text)}`)
    assert.equal(got.headline, null)
    assert.equal(got.body, text, 'the captured text comes back whole and unchanged')
  }
})

test('no address is ever read from a line that is not purely an https address', () => {
  for (const third of ['http://example.org/x', 'ftp://example.org/x', 'javascript:alert(1)',
    'see https://example.org/x', 'https://example.org/x and more', '  ']) {
    assert.equal(heldHeader(['Headline', '', third, '', 'Body'].join('\n')).link, null, third)
  }
})

/* --- one row --------------------------------------------------------------- */

test('a collected row carries its recorded address, its headline and its material', () => {
  assert.equal(rowLink(webRow()), FEED_LINK)
  assert.equal(rowHeadline(webRow()), 'Juno - NASA Science (.gov)')
  // This feed records the entry's title as its summary too, so the material is
  // the headline again: said once (`restates`), as the written answer says it.
  assert.equal(rowBody(webRow()), '')
  assert.equal(rowBody(webRow(PAGE_TEXT))!.startsWith('The spacecraft passed'), true)
})

test('a feed that repeats its own title as its summary does not say it twice', () => {
  assert.equal(restates('Juno - NASA Science (.gov)', 'Juno NASA Science (.gov)'), true)
  assert.equal(restates('Juno - NASA Science (.gov)', 'The spacecraft passed 550 miles'), false)
  assert.equal(restates(null, 'anything'), false)
  assert.equal(restates('a headline', ''), false)
})

test('only a held-source row can carry one: a collected post never does', () => {
  // The batch captures a post's identity and parts, never a page for it.
  const forged = { ...post(), value: { parts: [{ type: 'text', text: FEED_TEXT }] } } as unknown as RouteResult
  for (const r of [post(), forged, readme()]) {
    assert.equal(rowLink(r), null)
    assert.equal(rowHeadline(r), null)
  }
  assert.equal(rowBody(readme()), null, 'a row with no header is read whole, as before')
})

/* --- the row the reader sees ----------------------------------------------- */

test('THE ROW LEADS WITH THE HEADLINE, NOT THE HELD-FILE KEY', () => {
  const title = resultTitle(webRow())
  assert.equal(title, 'Juno - NASA Science (.gov)')
  assert.ok(!title.includes('a733ec1ec5e51a4b'),
    'the opaque key the owner was reading is gone from the row’s first line')
})

test('the preview is the material, not the headline and address said again', () => {
  const preview = resultPreview(webRow(PAGE_TEXT))
  assert.ok(preview.startsWith('The spacecraft passed 550 miles'), preview)
  assert.ok(!preview.includes('https://'), 'a 200-character permalink is not a preview')
  assert.equal(resultPreview(webRow()), '',
    'and a feed whose summary is its own headline shows the headline once')
  assert.ok(!resultPreview(webRow(FEED_TEXT)).includes('Published:'),
    'nor is the feed’s recorded trailer a preview')
})

test('a row that recorded only a headline and a link shows no empty quotation', () => {
  const bare = webRow(['Only a headline', '', 'https://example.org/a', '', '--', 'Published: 2026-01-01'].join('\n'))
  assert.equal(resultPreview(bare), '', 'nothing is quoted where nothing was retained')
  assert.equal(resultTitle(bare), 'Only a headline')
  assert.equal(rowLink(bare), 'https://example.org/a', 'and it is still openable')
})

test('the byline says the site a row came from, and still carries no recorded identity', () => {
  const byline = rowByline(webRow())
  assert.ok(byline.startsWith('news.google.com · '), byline)
  assert.ok(!/ent-[a-z0-9]{6,}|col-[a-z0-9]{6,}|adm-[a-z0-9]{6,}/.test(byline), byline)
  // Every other held file keeps the byline it had.
  assert.ok(rowByline(readme()).startsWith('Held file'), rowByline(readme()))
})

test('titles, previews and bylines of everything else are exactly as they were', () => {
  assert.equal(resultTitle(readme()), 'README.md')
  assert.equal(resultPreview(readme()), '# Disposable audit folder Notes kept here.')
})

/* A collected post leads with its own subject, read from the same captured
   words the preview already read (correction, review ent-e23af56bb855: "Post
   #15" names where it sits, never what it is about). A post whose whole
   captured text IS that one-sentence subject has nothing left to add under
   it, so the preview is empty rather than quoting the title back. */
test('a collected post leads with its subject, not its record number', () => {
  assert.equal(resultTitle(post()), 'Synthetic retained acceptance post.')
  assert.equal(resultPreview(post()), '', 'nothing is quoted again under a subject that was the whole post')
})

/* --- a Summary excerpt ----------------------------------------------------- */

test('an excerpt of a collected article carries the address, so it can be followed', () => {
  const [one] = collectedExcerpts([webRow()])
  assert.equal(one.title, 'Juno - NASA Science (.gov)')
  assert.equal(one.link, FEED_LINK)
  assert.equal(one.text, '', 'the headline is not quoted again beneath itself')
  // ITS ORIGIN IS THE SITE, NOT THE OBJECT KEY. This line was reading "Held
  // file · space-missions-and-astronomy-what-launch/a733ec1ec5e51a4b".
  assert.equal(one.origin, 'news.google.com')
  assert.ok(!one.origin.includes('a733ec1ec5e51a4b'))
  // And an ordinary record has no link, and is unchanged.
  const [other] = collectedExcerpts([readme()])
  assert.equal(other.link, undefined)
  assert.equal(other.origin, 'Held file · README.md')
  assert.equal(other.text, '# Disposable audit folder Notes kept here.')
})

test('a record with an address but no retained words is still offered', () => {
  const bare = webRow(['Only a headline', '', 'https://example.org/a'].join('\n'))
  const [one] = collectedExcerpts([bare])
  assert.ok(one, 'it is the one thing the reader can open; it is not dropped')
  assert.equal(one.text, '')
  assert.equal(one.link, 'https://example.org/a')
})

/* --- an address shown in prose -------------------------------------------- */

test('an address is shortened for reading, and the whole of it is still the link', () => {
  assert.equal(shortLink('https://news.google.com/rss/articles/CBMiT0FVX3lxTE45Yy1LbDRvVGs5VXJwS0FzWEZr?oc=5').length <= 48, true)
  assert.equal(shortLink('https://science.nasa.gov/'), 'science.nasa.gov')
  assert.equal(shortLink('https://www.bbc.co.uk/news/science-123'), 'bbc.co.uk/news/science-123')
  assert.equal(linkHost(FEED_LINK), 'news.google.com')
  assert.equal(linkHost('not an address'), null)
})

test('a statement is split into its words and its addresses, losing not one character', () => {
  const said = `From the web search: 71 records, most recently “Juno - NASA Science (.gov)” · ${FEED_LINK}`
  const pieces = linkPieces(said)
  assert.deepEqual(pieces.filter((p) => 'url' in p), [{ url: FEED_LINK }])
  assert.equal(pieces.map(saidIn).join(''), said,
    'lossless: the recorded characters are rendered, never edited')
})

test('a full stop after an address belongs to the sentence, not to the address', () => {
  const pieces = linkPieces('See https://example.org/launch-report. Then stop.')
  assert.deepEqual(pieces, [{ text: 'See ' }, { url: 'https://example.org/launch-report' },
    { text: '. Then stop.' }])
})

test('AN ADDRESS THAT WAS CUT IS NOT MADE A LINK THAT DOES NOT RESOLVE', () => {
  // The owner's own standing answer on 20261125-5294531-f4e3ecd4 holds a
  // 220-character excerpt that ends inside an address: linking it would hand
  // the owner a press that goes nowhere.
  const said = 'most recently “… - Space https://news.google.com/rss/articles/CBMi0AF…”.'
  assert.deepEqual(linkPieces(said).filter((p) => 'url' in p), [],
    'a shortened address stays the plain text it is')
  assert.equal(linkPieces(said).map(saidIn).join(''), said)
})

test('only an https address in the text itself can ever become a link', () => {
  for (const said of ['javascript:alert(1)', 'data:text/html,x', 'http://example.org/x',
    'file:///c:/secret', 'ftp://example.org']) {
    assert.deepEqual(linkPieces(said), [{ text: said }], said)
  }
})

/* --- a statement, laid out ------------------------------------------------- */

test('a statement that quoted a record is told apart from the quotation', () => {
  const got = statement('New, from the web search (2011-08-05) · “Juno - NASA Science (.gov)” · https://example.org/a: “Juno NASA Science.”')
  assert.equal(got.lead, 'New, from the web search (2011-08-05) · “Juno - NASA Science (.gov)” · https://example.org/a')
  assert.equal(got.quote, 'Juno NASA Science.')
})

test('a statement that quoted nothing is one paragraph, exactly as recorded', () => {
  for (const said of [
    'This Magnet has gathered 71 records from 1 source, collected 2026-11-25.',
    'From the web search: 71 records, most recently “Juno - NASA Science (.gov)” · https://example.org/a',
    '71 of them arrived in this collection and were not in the one before it.',
    'Nothing outside this collection was read, so this is what the collection can answer.',
    '',
  ]) {
    const got = statement(said)
    assert.equal(got.lead, said, said)
    assert.equal(got.quote, null, said)
  }
})

test('splitting a statement loses nothing: the characters recorded are the characters shown', () => {
  const said = 'From the Conversation (2026-11-20), on “calibration” and “drift”: “A newly arrived record about calibration drift.”'
  const got = statement(said)
  assert.equal(`${got.lead}: “${got.quote}”`, said)
})

/* --- a citation as a number, not as forensic evidence -----------------------
   Owner `ent-bce57ba67f38`: "Stop presenting ordinary information as forensic
   evidence. Use natural prose with numbered inline citations [1], [2], etc.,
   and accessible source details. Preserve provenance internally without
   forcing users to read it."

   The token below is the shape the owner read on TEST's own candidate --
   `mentis.sources.extract.cite`'s direct form, written into the middle of the
   answer's sentence by the run that wrote the answer. --------------------- */

const CITED = 'adm-e3d8cae2cb43@a79673349571[0:7631]'
const CITED_B = 'adm-aaa111111111@aaaaaaaaaaaa[0:412]'

/** The words a reader actually sees: the markup without its tags, so an
 *  attribute that KEEPS provenance is not mistaken for prose that shows it. */
const visible = (markup: string) => markup.replace(/<[^>]*>/g, '')

test('a direct citation is read as a citation, and the brackets around it with it', () => {
  const said = `The collection combines [${CITED}] and the feed rows under it.`
  const pieces = linkPieces(said)
  const cited = pieces.find((p) => 'cites' in p)
  assert.ok(cited && 'cites' in cited)
  assert.deepEqual(cited.cites.map((c) => c.ref), ['adm-e3d8cae2cb43'])
  assert.equal(cited.said, `[${CITED}]`,
    'the brackets the agent wrote around it are taken in, so its number is not drawn inside a second pair')
  assert.equal(cited.cites[0].source12, 'a79673349571')
  assert.deepEqual([cited.cites[0].start, cited.cites[0].end], [0, 7631])
  assert.equal(pieces.map(saidIn).join(''), said,
    'lossless: the recorded characters are all still accounted for')
})

test('A BRACKETED GROUP OF CITATIONS IS ONE RUN, brackets and separators with it', () => {
  // The shape the owner's own answer uses:
  // "[adm-a0dc…@ead7…[0:757]; adm-d364…@c2ec…[0:837]]". Matching each citation
  // alone left the group's `[` and `]` stranded around the numbers.
  const said = `They do not establish a timeline. [${CITED}; ${CITED_B}]`
  const pieces = linkPieces(said)
  const run = pieces.find((p) => 'cites' in p)
  assert.ok(run && 'cites' in run)
  assert.deepEqual(run.cites.map((c) => c.ref), ['adm-e3d8cae2cb43', 'adm-aaa111111111'])
  assert.equal(run.said, `[${CITED}; ${CITED_B}]`, 'the whole run, brackets and separator included')
  assert.equal(pieces.map(saidIn).join(''), said)
})

test('a bare direct citation is read too, and loses no character', () => {
  const said = `Two rows agree on the launch window ${CITED} and nothing outside them was read.`
  const pieces = linkPieces(said)
  assert.equal(pieces.filter((p) => 'cites' in p).length, 1)
  assert.equal(pieces.map(saidIn).join(''), said)
})

test('AN EXTRACTED CITATION KEEPS EXACTLY WHAT IT HAD: the two shapes are disjoint', () => {
  // `refid.ts` draws this one as its own chip through `Prose`. Nothing here may
  // take it, or that chip is lost.
  const extracted = 'adm-e3d8cae2cb43@a79673349571~text.plain@1+0123456789ab/fedcba987654[0:12]{char/1:7}'
  assert.deepEqual(linkPieces(`See ${extracted} for it.`).filter((p) => 'cites' in p), [],
    'the extracted form is not a direct citation')
})

test('a token that is not a citation is not made into one', () => {
  for (const said of [
    'adm-e3d8cae2cb43@a79673349571[7631:0]',   // a range that runs backwards
    'adm-e3d8cae2cb43@a79673349571[0:0]',      // a range of nothing
    'adm-e3d8cae2cb43@a796733[0:12]',          // not a twelve-digit digest
    'adm-e3d8cae2cb43@a79673349571',           // no range at all
    'ent-e3d8cae2cb43@a79673349571[0:12]',     // not a held reference
  ]) {
    assert.deepEqual(linkPieces(said).filter((p) => 'cites' in p), [], said)
    assert.equal(linkPieces(said).map(saidIn).join(''), said, said)
  }
})

test('each cited record is numbered once, in the order a reader meets it', () => {
  const lines = [
    `The collection combines [${CITED}] and the rows beside it.`,
    `Its earliest record is the Juno entry [${CITED_B}].`,
    `The same thermal test [${CITED_B}] is cited again, and [${CITED}] with it.`,
  ]
  assert.deepEqual(citedRefs(lines), ['adm-e3d8cae2cb43', 'adm-aaa111111111'],
    'answer-wide, so a record cited in two statements carries one number in both')
  assert.deepEqual(citedRefs([]), [])
  assert.deepEqual(citedRefs(['Nothing is cited here.']), [])
})

/* What a surface says about a cited record. The real one is
   `Summary.answerSources`, which reads it off the collected row. */
const index = (names: Record<string, string>, opened: string[] = []) => ({
  numberOf: (ref: string) => {
    const at = Object.keys(names).indexOf(ref)
    return at < 0 ? null : at + 1
  },
  nameOf: (ref: string) => names[ref] ?? null,
  open: (ref: string) => { opened.push(ref) },
})

test('a citation is drawn as its number, with the token kept on the element and out of the text', () => {
  const said = `The collection combines [${CITED}] and the feed rows under it.`
  const rendered = renderToStaticMarkup(createElement(Citations.Provider,
    { value: index({ 'adm-e3d8cae2cb43': 'Juno - NASA Science' }) },
    createElement(Linked, { text: said })))
  assert.ok(rendered.includes('[1]'), `drawn as its number: ${rendered}`)
  assert.doesNotMatch(visible(rendered), /a79673349571|0:7631|adm-/,
    'no reference, digest or byte range in the running text the owner reads')
  assert.ok(rendered.includes(`data-cite="[${CITED}]"`),
    'the whole recorded token is kept on the element: provenance preserved, not forced into the prose')
  assert.ok(rendered.includes('Source 1: Juno - NASA Science'),
    'and what the number stands for is said in words')
})

test('WITHOUT AN INDEX NOTHING IS NUMBERED: the recorded characters are drawn as they were', () => {
  const said = `The collection combines [${CITED}] and more.`
  const rendered = renderToStaticMarkup(createElement(Linked, { text: said }))
  assert.ok(rendered.includes(CITED),
    'a number standing for nothing a reader could open would be worse than the token')
})

test('a reference the index does not know keeps its recorded token', () => {
  const said = `It combines [${CITED}] with the rest.`
  const rendered = renderToStaticMarkup(createElement(Citations.Provider,
    { value: index({ 'adm-aaa111111111': 'Somewhere else' }) },
    createElement(Linked, { text: said })))
  assert.ok(rendered.includes(CITED))
})

test('the Sources list names each number, and offers only the records it holds', () => {
  const rendered = renderToStaticMarkup(createElement(SourceNotes, { notes: [
    { n: 1, ref: 'adm-e3d8cae2cb43', title: 'Juno - NASA Science',
      detail: 'Held file · space-missions/aaa · captured 25/11/2026', open: () => {} },
    { n: 2, ref: 'adm-aaa111111111', title: 'Not in the collection shown',
      detail: 'No live source was opened to show it.', open: null },
  ] }))
  assert.ok(rendered.includes(SOURCES_HEADING))
  assert.ok(rendered.includes('Juno - NASA Science') && rendered.includes('captured 25/11/2026'))
  assert.ok(rendered.includes('id="cite-source-1"'), 'the number in the prose links into this entry')
  assert.ok(!/id="cite-source-2"/.test(rendered),
    'a record this collection does not hold is named, not offered as a press')
  assert.equal(renderToStaticMarkup(createElement(SourceNotes, { notes: [] })), '',
    'an answer that cites nothing carries no Sources heading')
})

test('a numbered citation inside Markdown prose goes through the renderer Fluid already has', () => {
  const drawn = citedInline(index({ 'adm-e3d8cae2cb43': 'Juno' }))
  const out = renderToStaticMarkup(createElement('p', {},
    ...drawn(`**Two** rows agree [${CITED}] on the window.`, 'k')))
  assert.ok(out.includes('<strong>Two</strong>'), 'the Markdown reader still reads the Markdown')
  assert.ok(out.includes('[1]'), out)
  assert.doesNotMatch(visible(out), /a79673349571|adm-/, out)
})

test('recorded numeric markers open their mapped source without changing Markdown links', () => {
  const ref = 'adm-e3d8cae2cb43'
  const mapped = { ...index({ [ref]: 'Juno' }), refOf: (n: number) => n === 1 ? ref : null }
  const out = renderToStaticMarkup(createElement('p', {},
    ...citedInline(mapped)('**Juno** [1], again [1], unknown [2], and [1](https://example.org).', 'n')))
  assert.equal((out.match(/class="q2-magnet-cite"/g) ?? []).length, 2)
  assert.match(out, /Source 1: Juno/)
  assert.match(out, /<strong>Juno<\/strong>/)
  assert.match(out, /href="https:\/\/example.org\/"/)
  assert.ok(visible(out).includes('[2]'), 'unknown numbers stay as recorded')
})

test('balanced code wrappers around known citations render only their numbers and preserve the token', () => {
  const ref = 'adm-e3d8cae2cb43'
  const mapped = { ...index({ [ref]: 'Juno' }), refOf: (n: number) => n === 1 ? ref : null }
  for (const token of ['[1]', `[${CITED}]`, CITED]) {
    for (const ticks of ['`', '``']) {
      const out = renderToStaticMarkup(createElement('p', {},
        ...citedInline(mapped)(`Launch ${ticks}${token}${ticks}.`, 'wrapped')))
      assert.equal(visible(out), 'Launch [1].')
      assert.ok(out.includes(`data-cite="${token}"`), 'exact citation identity is retained')
      assert.equal((out.match(/class="q2-magnet-cite"/g) ?? []).length, 1)
      assert.doesNotMatch(out, /<code>/)
    }
  }
})

test('ordinary inline code and unknown citation markers keep their Markdown rendering', () => {
  const ref = 'adm-e3d8cae2cb43'
  const mapped = { ...index({ [ref]: 'Juno' }), refOf: (n: number) => n === 1 ? ref : null }
  const out = renderToStaticMarkup(createElement('p', {},
    ...citedInline(mapped)('Use `array[1]` and `[2]`, then `value = [1]`. Cite [1].', 'code')))
  assert.match(out, /<code>array\[1\]<\/code>/)
  assert.match(out, /<code>\[2\]<\/code>/)
  assert.match(out, /<code>value = \[1\]<\/code>/)
  assert.equal((out.match(/class="q2-magnet-cite"/g) ?? []).length, 1)
})
