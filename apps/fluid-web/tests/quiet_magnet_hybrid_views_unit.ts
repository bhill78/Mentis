/** H3: the Summary and the evidence views of the hybrid Magnet card.
 *
 *  What these prove: Summary is derived from the retained batch and issues no
 *  request of its own (never `magnets/<id>/read`); the lists show every retained
 *  item of their kind with real counts and are **not** filtered by the universal
 *  search query; inspection is inline and, on Summary, inside the Summary
 *  section; the provenance disclosure keeps its state per place; the grounding
 *  affordance is disabled and carries the gate's own reason; the empty
 *  collection says Conversation is still available; and the three search sources
 *  cover the whole batch and every earlier batch. */
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFileSync } from 'node:fs'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import type { MagnetConfig } from '../src/fluid/surface/magnet/types'
import Magnet from '../src/quiet2/magnets/Magnet'
import Summary, { GROUNDED_UNAVAILABLE, summaryFacts, summarySource } from '../src/quiet2/magnets/Summary'
import EvidenceViews, { evidenceSource, resultTitle } from '../src/quiet2/magnets/EvidenceViews'
import { batchSource, knownBatches } from '../src/quiet2/magnets/BatchHistory'
import { discussEvidence, evidenceBounds, evidenceOrigin } from '../src/quiet2/magnets/Inspection'
import { createMagnetResource } from '../src/quiet2/magnets/state'
import { goTab, inspect, setOpen, writePlace } from '../src/quiet2/magnets/places'
import { PERSPECTIVE_BLOCK_REASON } from '../src/quiet2/magnets/perspectives'
import { page as binding } from '../src/brainBinding'

const SOURCE = 'ent-source111111'
const brainKey = 'origin|fixture|brain-h3'
const digest = 'a'.repeat(64)
const summarySrc = () => readFileSync(new URL('../src/quiet2/magnets/Summary.tsx', import.meta.url), 'utf8')
const viewsSrc = () => readFileSync(new URL('../src/quiet2/magnets/EvidenceViews.tsx', import.meta.url), 'utf8')
/** The code, without the comments that discuss what it must not do. */
const code = (source: string) => source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^[ \t]*\/\/.*$/gm, '')

const store = () => {
  const mem = new Map<string, string>()
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: {
    getItem: (k: string) => mem.get(k) ?? null, setItem: (k: string, v: string) => mem.set(k, v),
    removeItem: (k: string) => mem.delete(k), clear: () => mem.clear() } })
  binding.saw('brain-h3@instance-one')
  return mem
}

const config = (id: `mag-${string}`): MagnetConfig => ({ id,
  sources: [{ kind: 'conversation', conversation: SOURCE }, { kind: 'file', collection: 'col-held', path: 'nested/calibration.txt' }],
  selection: { informationTypes: ['post', 'file'], dates: { after: '2026-11-01', before: '2026-11-23' } },
  conversation: 'ent-own111111', collection: { mode: 'one-time' }, synthesis: { mode: 'manual' },
  notifications: { newItems: false, changes: false, failures: false }, presentation: { renderer: 'disc' } })

const POST = { kind: 'post', id: 'ent-post111111', number: 12, version: 'ent-version111111', conversation: SOURCE, via: 'home', at: 1764000300,
  value: { parts: [{ type: 'text', text: 'Calibration delta of 37 recorded against the bench reference.' }] } }
const HELD = { kind: 'file', id: 'adm-file111111', version: 'adm-file111111', conversation: null, author: null, at: 1764000400, via: 'held-source',
  value: { ref: 'adm-file111111', digest, collection: 'col-held', path: 'nested/calibration.txt', text: 'é🙂', offset: 0, end: 6, size: 65540,
    acquired_at: 1764000400, shortened: true, omitted_bytes: 65534, next_offset: 6, citation: `adm-file111111@${digest.slice(0, 12)}[0:6]` } }
const ACTIVATION = { post: 'ent-activation111', artifact: { ref: 'adm-batch111111', digest, size: 2048, media_type: 'application/json' }, at: 1764000500, state: 'recorded' }
const batchPage = (id: `mag-${string}`) => ({ sources: [
  { source: config(id).sources[0], key: `conversation:${SOURCE}`, status: 'ok', results: [POST] },
  { source: config(id).sources[1], key: 'file:col-held:nested/calibration.txt', status: 'partial', reason: 'Shortened at the first 64 KiB.', results: [HELD] },
] })

/** The card's one read, recorded: nothing else may be asked. */
function resource(id: `mag-${string}`, body?: (c: MagnetConfig) => unknown) {
  const c = config(id)
  const asked: string[] = []
  const r = createMagnetResource({ id: `qm-${id}`, brainKey, saved: { id, name: 'Calibration inquiry', config: c },
    get: async (path) => { asked.push(path); return { status: 200, body: body ? body(c) : { magnet: id, config: c, activation: ACTIVATION, page: batchPage(id) } } } })
  return { r, asked }
}
const empty = (c: MagnetConfig) => ({ magnet: c.id, config: c, activation: null, page: null })
const html = (node: Parameters<typeof renderToStaticMarkup>[0]) => renderToStaticMarkup(node)

test('Summary opens alone with the composer, and renders only retained facts', async () => {
  store()
  const { r } = resource('mag-h3summary')
  setOpen(r, true)
  await r.read()
  const card = html(createElement(Magnet, { resource: r, onExpand: () => {}, onCollapse: () => {},
    views: { Summary: createElement(Summary, { resource: r, onPost: () => {} }) },
    footerComposer: createElement('form', { id: 'supplied-composer' }, 'composer') }))
  assert.ok(card.includes('id="summary-title"'), 'the default tab renders Summary')
  assert.ok(card.includes('supplied-composer'), 'Summary opens with the composer present')
  assert.ok(!card.includes('id="view-title"') && !card.includes('id="inquiry-title"'), 'Summary opens alone: no evidence list or Perspectives panel beside it')
  assert.ok(card.includes('1 posts · 1 files'), 'the badge is the real retained count')
  assert.ok(card.includes('Collection overview · facts only'))
  assert.ok(card.includes('Sample records · not agent analysis or synthesis.'), 'the boundary line is rendered in the approved wording')
})

test('every Summary line is a fact about the collection, from the batch and the definition only', async () => {
  store()
  const { r } = resource('mag-h3facts')
  await r.read()
  const facts = summaryFacts(r.saved, r.snapshot())
  const text = facts.join('\n')
  assert.ok(facts.some((l) => l === '1 collected posts and 1 collected files in the collection shown.'))
  assert.ok(text.includes(`Conversation ${SOURCE} (1 collected item)`), 'each configured source is named with what it actually captured')
  assert.ok(text.includes('Held file col-held / nested/calibration.txt (1 collected item)'))
  assert.ok(text.includes('2 configured sources'))
  assert.ok(text.includes('recorded state recorded'))
  assert.ok(text.includes('This collection is partial') && text.includes('Shortened at the first 64 KiB.'), 'a partial collection states its own reason')
  assert.ok(text.includes('Showing the latest collection.'))
  assert.ok(text.includes('Selected Conversation types: post, file.'))
  assert.ok(text.includes('Selected dates: 2026-11-01 to 2026-11-23.'))
  // Change is no longer a fact line: it belongs to the comparison, which is
  // made only against an earlier comparable batch (Part E, `compareCollections`).
  assert.ok(!/\bchange(d|s)?\b/i.test(text), 'the fact lines claim nothing about change')
  assert.ok(text.includes('No last-open baseline in this tab yet.'))
  // No sentence characterises the material: the captured words appear nowhere.
  assert.ok(!text.includes('Calibration delta of 37'), 'Summary never summarises content')
  assert.ok(!/\b(suggests|indicates|appears|concludes|overall|key (finding|theme))\b/i.test(text), 'no derived claim about what the material says')
})

test('rendering Summary issues no request at all beyond the retained collection read', async () => {
  store()
  const calls: string[] = []
  const previous = (globalThis as { fetch?: unknown }).fetch
  Object.defineProperty(globalThis, 'fetch', { configurable: true, writable: true,
    value: async (input: unknown) => { calls.push(String(input)); throw new Error('Summary asked the network.') } })
  try {
    const { r, asked } = resource('mag-h3network')
    setOpen(r, true)
    await r.read()
    assert.deepEqual(asked, ['/fluid/api/magnets/mag-h3network/collection'], 'the card makes exactly one retained read')
    const rendered = html(createElement(Summary, { resource: r, onPost: () => {} }))
    assert.ok(rendered.includes('id="summary-title"'))
    // Inspecting a retained post is still local to the batch.
    inspect(r, POST.id, `support-${POST.id}`)
    html(createElement(Summary, { resource: r, onPost: () => {} }))
    assert.deepEqual(asked, ['/fluid/api/magnets/mag-h3network/collection'], 'rendering Summary asked nothing more')
    assert.deepEqual(calls, [], 'Summary made no fetch of its own')
    assert.ok(!asked.some((p) => /\/read(\?|$)/.test(p)) && !calls.some((p) => /\/read(\?|$)/.test(p)),
      'magnets/<id>/read is never called: it reads the sources live, which this surface exists not to do')
    assert.ok(!code(summarySrc()).includes('/read') && !code(viewsSrc()).includes('/read'),
      'neither view names the live-source route anywhere but in the comment forbidding it')
  } finally {
    if (previous) Object.defineProperty(globalThis, 'fetch', { configurable: true, writable: true, value: previous })
  }
})

test('All, Posts and Files show every retained item of their kind, with real counts', async () => {
  store()
  const { r } = resource('mag-h3lists')
  await r.read()
  const all = html(createElement(EvidenceViews, { resource: r, lens: 'All', onPost: () => {}, onFile: () => {} }))
  const posts = html(createElement(EvidenceViews, { resource: r, lens: 'Posts', onPost: () => {}, onFile: () => {} }))
  const files = html(createElement(EvidenceViews, { resource: r, lens: 'Files', onPost: () => {}, onFile: () => {} }))
  const rows = (s: string) => (s.match(/q2-magnet-evidence-row/g) ?? []).length
  assert.equal(rows(all), 2); assert.equal(rows(posts), 1); assert.equal(rows(files), 1)
  assert.ok(all.includes('2 collected items') && posts.includes('1 collected item') && files.includes('1 collected item'))
  assert.ok(posts.includes('Post #12') && !posts.includes('nested/calibration.txt'), 'Posts shows only post evidence')
  assert.ok(files.includes('nested/calibration.txt') && !files.includes('Post #12'), 'Files shows only file evidence')
  assert.ok(all.includes('¶') && all.includes('▤'), 'each row carries its type glyph')
  assert.ok(all.includes(`Conversation ${SOURCE}`) && all.includes('Held file col-held'), 'each row names its captured source')
  assert.ok(all.includes('Calibration delta of 37'), 'each row shows its captured excerpt')
})

test('a tab list is never filtered by the universal search query', async () => {
  store()
  const { r } = resource('mag-h3query')
  await r.read()
  const before = html(createElement(EvidenceViews, { resource: r, lens: 'All', onPost: () => {}, onFile: () => {} }))
  r.update({ query: 'a phrase no retained item contains' })
  const after = html(createElement(EvidenceViews, { resource: r, lens: 'All', onPost: () => {}, onFile: () => {} }))
  assert.equal((after.match(/q2-magnet-evidence-row/g) ?? []).length, 2, 'the search query hides no retained row')
  assert.equal(after, before, 'the list is identical with and without a query')
  r.update({ overlay: 'search' })
  const overlay = html(createElement(EvidenceViews, { resource: r, lens: 'Posts', onPost: () => {}, onFile: () => {} }))
  assert.ok(overlay.includes('1 collected item'), 'an open search overlay does not narrow the tab it covers')
  for (const gone of ['s.query', 'toLowerCase', 'No retained items match this search']) {
    assert.ok(!code(viewsSrc()).includes(gone), `the in-tab substring filter is gone (${gone})`)
  }
})

test('inspection is inline: inside the Summary section, and beneath the clicked row in a list', async () => {
  store()
  const { r } = resource('mag-h3inline')
  await r.read()
  inspect(r, POST.id, `support-${POST.id}`)
  const summary = html(createElement(Summary, { resource: r, onPost: () => {} }))
  const section = summary.indexOf('q2-magnet-summary'), inspectTitle = summary.indexOf('id="inspect-title"')
  assert.ok(section >= 0 && inspectTitle > section, 'the inspection renders inside the Summary section')
  assert.ok(summary.includes('Collection overview · facts only'), 'Summary is not replaced by a separate inspection screen')
  assert.ok(summary.includes('Sample records · not agent analysis or synthesis.'))
  assert.ok(summary.includes('aria-expanded="true"'), 'the support that was clicked says it is expanded')
  assert.ok(summary.includes('Close evidence inspection'))
  assert.ok(summary.includes('Discuss this evidence'))
  goTab(r, 'All')
  inspect(r, HELD.id, `item-${HELD.id}`)
  const list = html(createElement(EvidenceViews, { resource: r, lens: 'All', onPost: () => {}, onFile: () => {} }))
  const row = list.indexOf(`id="item-${HELD.id}"`)
  assert.ok(row >= 0 && list.indexOf('id="inspect-title"') > row, 'the inspection renders directly beneath its row')
  assert.equal((list.match(/q2-magnet-evidence-row/g) ?? []).length, 2, 'the other rows stay listed around it')
  assert.ok(list.includes('Collected file · Held file col-held / nested/calibration.txt'))
})

test('the provenance disclosure states origin, version, capture and bounds, and keeps its state per place', async () => {
  store()
  const { r } = resource('mag-h3provenance')
  await r.read()
  goTab(r, 'Files')
  inspect(r, HELD.id, `item-${HELD.id}`)
  const shut = html(createElement(EvidenceViews, { resource: r, lens: 'Files', onPost: () => {}, onFile: () => {} }))
  assert.ok(shut.includes('Source &amp; captured version') && !/<details[^>]*open/.test(shut), 'a fresh inspection opens its provenance shut')
  writePlace(r, 'Files', { provenance: true })
  const open = html(createElement(EvidenceViews, { resource: r, lens: 'Files', onPost: () => {}, onFile: () => {} }))
  assert.ok(/<details[^>]*open/.test(open), 'the disclosure state lives in the place')
  for (const line of ['<dt>Origin</dt>', '<dt>Version</dt>', '<dt>Captured</dt>', '<dt>Bounds</dt>']) assert.ok(open.includes(line))
  assert.ok(open.includes('Captured bytes 0–6 of 65540'), 'bounds are the recorded capture range')
  assert.ok(open.includes('shortened, 65534 bytes omitted'))
  assert.ok(open.includes(HELD.value.citation), 'the held-file citation is shown as captured')
  // The other place keeps its own disclosure.
  assert.equal(r.snapshot().places.Posts.provenance, false)
  assert.equal(r.snapshot().places.Files.provenance, true)
  assert.equal(evidenceOrigin(r.snapshot().results[0]), `Conversation ${SOURCE}`)
  assert.equal(evidenceBounds(r.snapshot().results[0]), 'The whole retained post, as captured')
})

test('the grounding affordance is disabled and carries the gate’s own reason', async () => {
  store()
  const { r } = resource('mag-h3grounding')
  await r.read()
  const rendered = html(createElement(Summary, { resource: r, onPost: () => {} }))
  assert.match(rendered, /<button[^>]*disabled[^>]*aria-describedby="grounded-status"/)
  assert.ok(rendered.includes('Synthesize from evidence'))
  assert.ok(rendered.includes(PERSPECTIVE_BLOCK_REASON), 'the reason is the server-side gate’s own words')
  assert.equal(GROUNDED_UNAVAILABLE, `Unavailable · ${PERSPECTIVE_BLOCK_REASON}`)
  assert.ok(!/Unavailable · [a-z]/.test(code(summarySrc()).replace('`Unavailable · ${PERSPECTIVE_BLOCK_REASON}`', '')), 'the reason is not a sentence written here')
})

test('an empty collection says Conversation is still available, on Summary and in every list', async () => {
  store()
  const { r } = resource('mag-h3empty', empty)
  await r.read()
  const summary = html(createElement(Summary, { resource: r, onPost: () => {} }))
  assert.ok(summary.includes('No collected information yet. Conversation is still available.'))
  assert.ok(summary.includes('Opening never collects'), 'it says what opening does not do')
  assert.ok(summary.includes('Synthesize from evidence'), 'the honest grounding statement stays on an empty collection')
  for (const lens of ['All', 'Posts', 'Files'] as const) {
    const list = html(createElement(EvidenceViews, { resource: r, lens, onPost: () => {}, onFile: () => {} }))
    assert.ok(list.includes('No collected information yet. Conversation is still available.'), `${lens} says the collection is empty`)
    assert.ok(list.includes('0 collected items'))
  }
})

test('evidenceSource and summarySource cover the whole two-source batch', async () => {
  store()
  const { r } = resource('mag-h3index')
  await r.read()
  const entries = evidenceSource(r).entries()
  assert.equal(entries.length, 2, 'one entry per retained item of the batch, posts and files')
  assert.deepEqual(entries.map((e) => e.kind).sort(), ['Files', 'Posts'])
  const post = entries.find((e) => e.kind === 'Posts')!
  assert.equal(post.title, resultTitle(r.snapshot().results[0]))
  assert.ok(post.text.includes('Calibration delta of 37'), 'the captured text is searchable')
  assert.ok(post.text.includes(POST.id) && post.text.includes(`Conversation ${SOURCE}`), 'id and source are searchable')
  const file = entries.find((e) => e.kind === 'Files')!
  assert.ok(file.text.includes('adm-file111111') && file.text.includes('Held file col-held'))
  assert.equal(evidenceSource(r).complete, undefined, 'one collection read returns the whole batch, so nothing is owed')
  post.open()
  assert.equal(r.snapshot().places[r.snapshot().tab].inspected, POST.id, 'opening a result inspects it in place')
  const facts = summarySource(r).entries()
  assert.equal(facts.length, 1)
  assert.equal(facts[0].kind, 'Summary')
  assert.ok(facts[0].text.includes('2 configured sources'), 'the Summary entry searches the lines Summary shows')
})

test('batchSource walks every earlier retained batch to exhaustion, and stops if the cursor repeats', async () => {
  store()
  const { r } = resource('mag-h3batches')
  const batch = (n: number) => ({ post: `ent-batchpost${n}1111`, artifact: { ref: `adm-batch${n}11111`, digest, size: 1024 + n }, at: 1764000000 + n, state: 'recorded' })
  const pages: Record<string, unknown> = {
    '': { magnet: 'mag-h3batches', batches: [batch(1), batch(2)], next: 'cur-2' },
    'cur-2': { magnet: 'mag-h3batches', batches: [batch(3)], next: null },
  }
  const asked: string[] = []
  Object.defineProperty(globalThis, 'fetch', { configurable: true, writable: true, value: async (input: unknown) => {
    const url = String(input); asked.push(url)
    const cursor = new URL(url, 'http://host').searchParams.get('cursor') ?? ''
    return { ok: true, status: 200, json: async () => pages[cursor] ?? { error: 'Unknown cursor.' } }
  } })
  const source = batchSource(r)
  assert.deepEqual(source.entries(), [], 'nothing is claimed before the history is read')
  const all = await source.complete!('')
  assert.equal(all.length, 3, 'every earlier batch is listed, not just the first page')
  assert.equal(asked.length, 2, 'the walk follows the server cursor')
  assert.ok(asked.every((u) => u.includes('/collection/history?limit=20')))
  assert.equal(source.bound!(), null, 'a completed walk states no bound')
  assert.equal(source.queryDependent, false, 'the batch list does not depend on the query')
  assert.equal(knownBatches(r).length, 3, 'what was read is what entries() may offer')
  assert.equal(source.entries().length, 3)
  assert.ok(all[0].title.startsWith('Collected ') && all[0].text.includes('adm-batch111111'))
  // A server that repeats its cursor stops the walk and says so.
  pages['cur-2'] = { magnet: 'mag-h3batches', batches: [batch(3)], next: 'cur-2' }
  const again = batchSource(r)
  const stopped = await again.complete!('')
  assert.equal(stopped.length, 3)
  assert.match(again.bound!()!, /repeated its cursor/)
  // A refusal is stated, never hidden.
  pages['cur-2'] = { error: 'Retained history unavailable.' }
  const refused = batchSource(r)
  await refused.complete!('')
  assert.match(refused.bound!()!, /could not be listed in full/)
})

test('Discuss this evidence attaches the reference only, and clears suppression', async () => {
  store()
  const { r } = resource('mag-h3discuss')
  await r.read()
  r.update({ contextSuppressed: true })
  discussEvidence(r, r.snapshot().results[0])
  const context = r.snapshot().context!
  assert.equal(context.ref, POST.id)
  assert.equal(context.kind, 'post')
  assert.equal(context.label, `Collected post · Conversation ${SOURCE}`)
  assert.equal(context.text, undefined, 'captured content never enters the attached context')
  assert.equal(r.snapshot().contextSuppressed, false, 'an explicit discuss clears suppression')
})
