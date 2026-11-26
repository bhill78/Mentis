/** PART 4: COLLECTION BROWSING, COMPACT, GROUPED, CONTENT-SHAPED.
 *
 *  `04-browse.png` stood a row at roughly 115-140 px (title, up to 180 chars of
 *  preview, byline) in one flat `<ul>` with no grouping and no density control
 *  -- 72 rows was an unreadable column, and TEST showed 4-6 rows in one
 *  viewport. This file pins what Part 4 does about it:
 *
 *    - a row is one line by default -- title, then what it is and when -- with
 *      its captured excerpt and its own address moved into a block
 *      (`q2-magnet-row-more`) that sits outside the row's button and is
 *      revealed by hovering or focusing the row, never shown by default;
 *    - the list is grouped by day and by source within each day, each a
 *      counted header;
 *    - the fourth filter the mockup always showed -- Images -- exists and
 *      narrows to `kind === 'image'`, and every pill reads its own label
 *      ("Everything", not the raw "All" tab key);
 *    - a held item whose path is nothing but a raw storage object key (a run
 *      of hex, digest-named rather than reader-named) does not title itself
 *      from that key; a real filename, kept exactly as it was, still does.
 *
 *  Visual density -- 20+ rows in one real viewport -- is not something a node
 *  unit test renders; that is checked with a screenshot against the TEST
 *  candidate, alongside this file's checks of the markup and the grouping that
 *  make the density possible. */
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import EvidenceViews, { resultTitle } from '../src/quiet2/magnets/EvidenceViews'
import { createMagnetResource } from '../src/quiet2/magnets/state'
import { MAGNET_COLLECTION_FILTERS } from '../src/quiet2/magnets/places'
import { page as binding } from '../src/brainBinding'
import type { MagnetConfig } from '../src/fluid/surface/magnet/types'
import type { RouteResult } from '../src/fluid/surface/magnet/route'

const SOURCE = 'ent-source222222'
const brainKey = 'origin|fixture|brain-compaction'
const digest = 'a'.repeat(64)

const store = () => {
  const mem = new Map<string, string>()
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: {
    getItem: (k: string) => mem.get(k) ?? null, setItem: (k: string, v: string) => mem.set(k, v),
    removeItem: (k: string) => mem.delete(k), clear: () => mem.clear() } })
  binding.saw('brain-compaction@instance-one')
}

const config = (): MagnetConfig => ({ id: 'mag-compaction',
  sources: [{ kind: 'conversation', conversation: SOURCE }],
  selection: { informationTypes: ['post', 'file', 'image', 'attachment'], dates: {} },
  collection: { mode: 'one-time' }, synthesis: { mode: 'manual' }, activation: { mode: 'manual' },
  processing: { operations: [{ op: 'extract' }] },
  notifications: { newItems: false, changes: false, failures: false }, presentation: { renderer: 'disc' } })

/* Every row rides the one `conversation` source (`collectionRows.ts` only
   demands a strict shape -- digest, offsets, a `held-source` via -- from a
   `file`-kind SOURCE, not from a row's own `kind`), so a row here is free to
   say `kind: 'file'` or `'image'` and `via: 'held-source'` for this file's own
   logic to read, carrying only what `conversation` rows must: an `ent-`
   conversation id and version. */
const now = Math.floor(Date.now() / 1000)
const TODAY = now
const YESTERDAY = now - 86400

const webHeader = (headline: string, link: string) => `${headline}\n\n${link}`

const POST = { kind: 'post', id: 'post-today', conversation: SOURCE, version: 'ent-version000001', number: 1, at: TODAY,
  value: { parts: [{ type: 'text', text: 'A synthetic retained post, for grouping only.' }] } }
const NASA_TODAY = { kind: 'file', id: 'file-nasa-today', conversation: SOURCE, version: 'ent-version000002', at: TODAY, via: 'held-source',
  value: { text: webHeader('Juno launch recap', 'https://nasa.gov/today-article') } }
const SPACE_TODAY = { kind: 'file', id: 'file-space-today', conversation: SOURCE, version: 'ent-version000003', at: TODAY, via: 'held-source',
  value: { text: webHeader('ISS resupply mission', 'https://space.com/today-article') } }
const NASA_YESTERDAY = { kind: 'file', id: 'file-nasa-yesterday', conversation: SOURCE, version: 'ent-version000004', at: YESTERDAY, via: 'held-source',
  value: { text: webHeader('Perseverance update', 'https://nasa.gov/yesterday-article') } }
const IMAGE_TODAY = { kind: 'image', id: 'image-today', conversation: SOURCE, version: 'ent-version000005', at: TODAY,
  value: { title: 'Launch photo' } }
/* THE RAW-STORAGE-KEY LEAK (plan Part 4 item 5): a held item with no header
   of its own, whose recorded `path` IS the digest-named storage key -- not a
   filename a reader recognises. */
const RAW_LEAK_TODAY = { kind: 'file', id: 'file-raw-today', conversation: SOURCE, version: 'ent-version000006', at: TODAY, via: 'held-source',
  value: { collection: 'col-leak', path: 'a733ec1ec5e51a4b', digest, text: 'binary content, no recorded header' } }
/* A REAL FILENAME, UNCHANGED: the same shape, a path a reader recognises. */
const README_TODAY = { kind: 'file', id: 'file-readme-today', conversation: SOURCE, version: 'ent-version000007', at: TODAY, via: 'held-source',
  value: { collection: 'col-readme', path: 'README.md' } }

const ROWS = [POST, NASA_TODAY, SPACE_TODAY, NASA_YESTERDAY, IMAGE_TODAY, RAW_LEAK_TODAY, README_TODAY]
const ACTIVATION = { post: 'ent-activation222', artifact: { ref: 'adm-batch222222', digest, size: 2048, media_type: 'application/json' }, at: now, state: 'recorded' }
const page = (c: MagnetConfig) => ({ sources: [{ source: c.sources[0], key: `conversation:${SOURCE}`, status: 'ok', results: ROWS }] })

function resource() {
  const c = config()
  return createMagnetResource({ id: 'qm-compaction', brainKey, saved: { id: 'mag-compaction', name: 'Space missions and astronomy', config: c },
    get: async () => ({ status: 200, body: { magnet: 'mag-compaction', config: c, activation: ACTIVATION, page: page(c) } }) })
}
const may = () => true
const browse = (r: ReturnType<typeof resource>, lens: 'All' | 'Posts' | 'Files' | 'Images' = 'All') =>
  renderToStaticMarkup(createElement(EvidenceViews, { resource: r, lens, onPost: () => {}, onFile: () => {}, canWrite: may }))

/** The sequence pinned, as positions in the markup -- what matters is the
 *  order things appear in, not one build's exact attribute spelling. */
const order = (html: string, parts: string[]) => {
  let last = -1
  for (const part of parts) {
    const at = html.indexOf(part, last + 1)
    assert.ok(at >= 0, `says "${part}", after what came before it (last the resting surface found at ${last})`)
    last = at
  }
}

/* -- one row, one line by default -------------------------------------------- */

test('a row is one line by default: the preview and the row’s own address sit outside the button, not inside it', async () => {
  store()
  const r = resource()
  await r.read()
  const html = browse(r)
  const rowStart = html.indexOf('id="item-file-nasa-today"')
  assert.ok(rowStart >= 0, 'the NASA row is rendered')
  const buttonClose = html.indexOf('</button>', rowStart)
  const buttonMarkup = html.slice(rowStart, buttonClose)
  // The button is the title and the byline, on one line, and nothing else.
  assert.ok(buttonMarkup.includes('q2-magnet-row-line'), 'the title and the byline share one line')
  assert.ok(buttonMarkup.includes('Juno launch recap'), 'the headline leads the row')
  assert.ok(buttonMarkup.includes('nasa.gov'), 'the byline names the site, on the same line')
  assert.ok(!buttonMarkup.includes('q2-magnet-preview'), 'the captured excerpt is not inside the one-line button')
  assert.ok(!buttonMarkup.includes('q2-magnet-row-link'), 'the row’s own address is not inside the one-line button')
  // They are still rendered -- as a sibling block the row reveals, not inside it.
  const afterButton = html.slice(buttonClose)
  const moreAt = afterButton.indexOf('q2-magnet-row-more')
  assert.ok(moreAt >= 0 && moreAt < (afterButton.indexOf('</li>') >= 0 ? afterButton.indexOf('</li>') : afterButton.length),
    'the preview and the address are in the same row, outside its button')
})

/* -- grouped by day, and by source within each day, each counted ------------ */

test('the list is grouped by day, and by source within each day, each a counted header', async () => {
  store()
  const r = resource()
  await r.read()
  const html = browse(r)
  order(html, [
    '>Today<span class="mgd-subtle"> 6</span>',
    '>Collected post<span class="mgd-subtle"> 1</span>', 'A synthetic retained post',
    '>nasa.gov<span class="mgd-subtle"> 1</span>', 'Juno launch recap',
    '>space.com<span class="mgd-subtle"> 1</span>', 'ISS resupply mission',
    '>Collected file<span class="mgd-subtle"> 1</span>', 'Launch photo',
    '>Held file<span class="mgd-subtle"> 2</span>',
    '>Yesterday<span class="mgd-subtle"> 1</span>',
    '>nasa.gov<span class="mgd-subtle"> 1</span>', 'Perseverance update',
  ])
})

/* -- the fourth pill, and every pill’s own label ----------------------------- */

test('four filters -- Everything, Posts, Files, Images -- each reading its own label, not the raw tab key', async () => {
  store()
  const r = resource()
  await r.read()
  const html = browse(r)
  assert.deepEqual(MAGNET_COLLECTION_FILTERS.map((f) => f.tab), ['All', 'Posts', 'Files', 'Images'])
  assert.equal((html.match(/mgd-pill/g) ?? []).length, 4, 'one pill per filter, and no second filter row')
  order(html, ['mgd-pill', 'Everything', 'Posts', 'Files', 'Images'])
  assert.ok(!html.includes('>All<'), 'the pill reads its label ("Everything"), never the raw "All" tab key')
  assert.ok(html.includes('class="mgd-pill mgd-active"'), 'the showing filter carries the active pill')
})

test('Images narrows the collection to kind \'image\', under the same list and the same gate', async () => {
  store()
  const r = resource()
  await r.read()
  const html = browse(r, 'Images')
  assert.ok(html.includes('Launch photo'), 'the one image is shown')
  assert.ok(!html.includes('Juno launch recap'), 'a held web file is not shown under Images')
  assert.ok(!html.includes('A synthetic retained post'), 'a post is not shown under Images')
  order(html, ['>Today<span class="mgd-subtle"> 1</span>', 'Launch photo'])
})

/* -- no raw storage path, id, digest or byte offset in any row -------------- */

test('no row carries a raw storage path, id, digest or byte offset', async () => {
  store()
  const r = resource()
  await r.read()
  const html = browse(r)
  assert.ok(!html.includes('a733ec1ec5e51a4b'), 'the raw storage object key never reaches the row')
  assert.ok(!html.includes(digest), 'no recorded digest reaches a row')
  assert.ok(!/col-[a-z0-9]{6,}/.test(html), 'no recorded collection id reaches a row')
})

/* -- a raw storage key does not become a title; a real filename still does -- */

test('a held item whose path IS the raw storage key does not title itself from it', () => {
  const title = resultTitle(RAW_LEAK_TODAY as unknown as RouteResult)
  assert.ok(!title.includes('a733ec1ec5e51a4b'), `the row's first line is not the opaque storage key: got "${title}"`)
  assert.equal(title, 'File from a collected post', 'it says what the item is instead')
})

test('a real filename is kept exactly as it was', () => {
  assert.equal(resultTitle(README_TODAY as unknown as RouteResult), 'README.md')
})
