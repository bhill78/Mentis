/** H4: the universal Magnet search.
 *
 *  Proves the search over the whole index rather than over what was loaded: the
 *  results replacing the reading body, the content-type filter, the retained
 *  query/filter/list-position/disclosure on inspect, Back-to-results, Return to
 *  the tab the search was begun from, resume-by-query, the empty-match recovery
 *  and the intervening-search case; and, against fake sources, that a match
 *  present only in a `complete()` result appears, that a query-independent
 *  `complete()` runs once per opened overlay and not per keystroke while the
 *  query-dependent one is debounced and cached per query, that a pending,
 *  bounded or refused read is stated in the header, and that the list position
 *  survives a late merge.
 *
 *  Real sources land in H2, H3 and H5; cross-content-type coverage against them
 *  is the integration check of §8.2. Here every source is a fake, because the
 *  point of these tests is H4's assembly, not another part's retrieval. */
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import Magnet from '../src/quiet2/magnets/Magnet'
import SearchView, { backToResults, clearSearch, openResult, resumeSearch, SearchToolbar, setSearchType, typeSearch } from '../src/quiet2/magnets/SearchView'
import {
  BOUNDARY_SENTENCE, COMPLETE_SENTENCE, LOADING_SENTENCE, MAGNET_SEARCH_SOURCES,
  createSearchIndex, filterEntries, matchesEntry, mergeByKey, scopeSentences, searchIsComplete,
} from '../src/quiet2/magnets/search'
import type { MagnetSearchSource, SearchClock, SearchSourceReport } from '../src/quiet2/magnets/search'
import { MAGNET_SEARCH_TYPES } from '../src/quiet2/magnets/contract'
import type { MagnetResource, MagnetRoute, MagnetSearchKind, SearchEntry, SearchSource } from '../src/quiet2/magnets/contract'
import { createMagnetResource } from '../src/quiet2/magnets/state'
import { closeOverlay, goTab, inspect, openOverlay, place, placeAt, restore, route, setOpen, writePlace } from '../src/quiet2/magnets/places'
import { page as binding } from '../src/brainBinding'

const SOURCE = 'ent-source111111'
const brainKey = 'origin|fixture|brain-h4'
const store = () => {
  const mem = new Map<string, string>()
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: {
    getItem: (k: string) => mem.get(k) ?? null, setItem: (k: string, v: string) => mem.set(k, v),
    removeItem: (k: string) => mem.delete(k), clear: () => mem.clear() } })
  binding.saw('brain-h4@instance-one')
  return mem
}
const configFor = (id: `mag-${string}`) => ({ id, sources: [{ kind: 'conversation' as const, conversation: SOURCE }], selection: {}, conversation: 'ent-own111111',
  collection: { mode: 'one-time' as const }, synthesis: { mode: 'manual' as const },
  notifications: { newItems: false, changes: false, failures: false }, presentation: { renderer: 'disc' as const } })
const resource = (id: `mag-${string}`) => {
  const config = configFor(id)
  return createMagnetResource({ id: `qm-${id}`, brainKey, saved: { id, name: 'Calibration inquiry', config },
    get: async () => ({ status: 200, body: { magnet: id, config, activation: null, page: null } }) })
}

const entryOf = (key: string, kind: MagnetSearchKind, title: string, text: string, open: () => void = () => {}): SearchEntry =>
  ({ key, kind, title, text, open })
/** A source row under one of §4's real names, so the header wording is the real one. */
const rowOf = (name: string, kinds: MagnetSearchKind[], source: SearchSource): MagnetSearchSource =>
  ({ name, kinds, owner: 'fake', module: 'fake', make: () => source })
const held = (name: string, kinds: MagnetSearchKind[], entries: SearchEntry[]) =>
  rowOf(name, kinds, { entries: () => entries })

const manual = () => {
  const queue: (() => void)[] = []
  const clock: SearchClock = { schedule(run) { queue.push(run); return () => { const i = queue.indexOf(run); if (i >= 0) queue.splice(i, 1) } } }
  return { clock, pending: () => queue.length, settle: () => { for (const run of queue.splice(0)) run() } }
}
/** A declaration, not a generic arrow: the test loader transpiles `.ts` with JSX
 *  on, which reads `<T>() =>` as an element. */
function deferred<T>() {
  let resolve!: (v: T) => void, reject!: (e: unknown) => void
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}
const tick = () => new Promise<void>((r) => setTimeout(r, 0))
const report = (over: Partial<SearchSourceReport> & { name: string }): SearchSourceReport =>
  ({ kinds: ['Posts'], owner: 'H?', module: 'x.ts', state: 'complete', bound: null, count: 0, queryDependent: false, ...over })

// ---------------------------------------------------------------- the view

test('results replace the reading body in the frame’s view slot', () => {
  store()
  const r = resource('mag-h4body')
  setOpen(r, true)
  const index = createSearchIndex({ resource: r, sources: [held('evidenceSource', ['Posts'], [entryOf('p1', 'Posts', 'Calibration drift', 'the drift report')])] })
  index.opened('')
  openOverlay(r, 'search')
  const html = renderToStaticMarkup(createElement(Magnet, { resource: r, onExpand: () => {}, onCollapse: () => {},
    views: { Summary: createElement('p', null, 'the summary reading body'), search: createElement(SearchView, { resource: r, index }) } }))
  assert.ok(html.includes('Search this Magnet'), 'the search overlay is the body')
  assert.ok(!html.includes('the summary reading body'), 'results replace the reading body, never stack under it')
  assert.ok(html.includes('Calibration drift'), 'the index is shown')
  assert.equal((html.match(/q2-magnet-view/g) ?? []).length, 1, 'still one scroll container')
  assert.ok(html.includes('← Return to Summary'), 'the return to the tab the search was begun from')
  index.dispose()
})

test('the content-type filter covers the eight approved types and selects by kind', () => {
  store()
  const r = resource('mag-h4filter')
  setOpen(r, true)
  openOverlay(r, 'search')
  const index = createSearchIndex({ resource: r, sources: [
    held('evidenceSource', ['Posts', 'Files'], [entryOf('p1', 'Posts', 'Calibration drift', 'drift'), entryOf('f1', 'Files', 'drift.csv', 'rows')]),
    held('perspectiveSource', ['Perspectives'], [entryOf('l1', 'Perspectives', 'What drifted?', 'wording')]),
  ] })
  index.opened('')
  assert.deepEqual([...MAGNET_SEARCH_TYPES], ['All', 'Summary', 'Posts', 'Files', 'Perspectives', 'Conversation', 'Settings', 'Batches'])
  const all = renderToStaticMarkup(createElement(SearchView, { resource: r, index }))
  for (const t of MAGNET_SEARCH_TYPES) assert.ok(all.includes(`>${t}</option>`), `the filter offers ${t}`)
  assert.ok(all.includes('3 results'))
  writePlace(r, 'search', { scroll: 260 })
  r.update({ searchTarget: { kind: 'Posts' } })
  setSearchType(r, 'Files')
  assert.equal(r.snapshot().searchType, 'Files')
  assert.equal(placeAt(r.snapshot(), 'search').scroll, 0, 'changing the filter returns the list to the top')
  assert.equal(r.snapshot().searchTarget, null, 'changing the filter returns to the list')
  const files = renderToStaticMarkup(createElement(SearchView, { resource: r, index }))
  assert.ok(files.includes('1 result') && !files.includes('1 results'))
  assert.ok(files.includes('drift.csv') && !files.includes('Calibration drift'))
  // The match is over title + text + kind, case-insensitively.
  const e = entryOf('x', 'Posts', 'Calibration drift', 'Bounded capture')
  assert.ok(matchesEntry(e, 'CALIBRATION', 'All'))
  assert.ok(matchesEntry(e, 'bounded', 'Posts'))
  assert.ok(matchesEntry(e, 'posts', 'All'), 'the kind is part of the haystack')
  assert.ok(!matchesEntry(e, 'calibration', 'Files'), 'the filter wins over the phrase')
  index.dispose()
})

test('an empty match offers recovery and keeps the return control', () => {
  store()
  const r = resource('mag-h4empty')
  setOpen(r, true)
  openOverlay(r, 'search')
  r.update({ query: 'nothing matches this', searchType: 'Files' })
  const index = createSearchIndex({ resource: r, sources: [held('evidenceSource', ['Posts'], [entryOf('p1', 'Posts', 'Calibration drift', 'drift')])] })
  index.opened('nothing matches this')
  const html = renderToStaticMarkup(createElement(SearchView, { resource: r, index }))
  assert.ok(html.includes('0 results'))
  assert.ok(html.includes('No matches. Try another phrase or content type.'))
  assert.ok(html.includes('Clear the phrase and show everything in the index'))
  assert.ok(html.includes('Search every content type'))
  assert.ok(html.includes('← Return to Summary'), 'the return control survives an empty result')
  index.dispose()
})

// ------------------------------------------------------- opening a result

const evidenceRow = (r: MagnetResource, ref: string) =>
  rowOf('evidenceSource', ['Posts'], { entries: () => [entryOf(ref, 'Posts', 'Calibration drift', 'the drift report', () => inspect(r, ref))] })
const lensRow = (r: MagnetResource, lens: string) =>
  rowOf('perspectiveSource', ['Perspectives'], { entries: () => [entryOf(lens, 'Perspectives', 'What drifted?', 'wording', () => r.update({ lens }))] })

test('inspecting a result keeps the query, the filter, the list position and the tab’s disclosure', () => {
  store()
  const r = resource('mag-h4inspect')
  setOpen(r, true)
  goTab(r, 'Perspectives')
  writePlace(r, 'Perspectives', { scroll: 310, history: true, provenance: true })
  typeSearch(r, 'drift')
  r.update({ searchType: 'Posts' })
  writePlace(r, 'search', { scroll: 180 })
  const index = createSearchIndex({ resource: r, sources: [evidenceRow(r, 'ent-post111111')] })
  index.opened('drift')
  const [hit] = index.snapshot().entries
  openResult(r, hit)
  const after = r.snapshot()
  assert.equal(after.query, 'drift', 'the query is kept')
  assert.equal(after.searchType, 'Posts', 'the filter is kept')
  assert.equal(after.searchListScroll, 180, 'the list position is kept to come back to')
  assert.deepEqual(after.searchTarget, { kind: 'Posts', item: 'ent-post111111' }, 'the target is derived from what the source’s open() did')
  assert.equal(placeAt(after, 'search').inspected, 'ent-post111111')
  assert.equal(placeAt(after, 'search').scroll, 0, 'the opened result starts at the top')
  assert.equal(after.places.Perspectives.history, true, 'searching never disturbs the tab it was begun from')
  assert.equal(after.places.Perspectives.scroll, 310)
  // The opened result is read inside the card, not on a separate screen.
  const html = renderToStaticMarkup(createElement(SearchView, { resource: r, index }))
  assert.ok(html.includes('← Back to results') && html.includes('← Return to Perspectives'))
  assert.ok(html.includes('Search: drift · Posts'))
  index.dispose()
})

test('a Perspectives result also selects that lens, and a Settings result opens the settings overlay', () => {
  store()
  const r = resource('mag-h4targets')
  setOpen(r, true)
  openOverlay(r, 'search')
  const lensIndex = createSearchIndex({ resource: r, sources: [lensRow(r, 'ent-lens111111')] })
  lensIndex.opened('')
  openResult(r, lensIndex.snapshot().entries[0])
  assert.equal(r.snapshot().lens, 'ent-lens111111')
  assert.deepEqual(r.snapshot().searchTarget, { kind: 'Perspectives', lens: 'ent-lens111111' })
  lensIndex.dispose()
  backToResults(r)
  const settingsIndex = createSearchIndex({ resource: r, sources: [held('settingsSource', ['Settings'], [entryOf('settings', 'Settings', 'Sources and collection', 'conversation posts')])] })
  settingsIndex.opened('')
  openResult(r, settingsIndex.snapshot().entries[0])
  assert.equal(r.snapshot().overlay, 'settings', 'a Settings result opens the settings overlay')
  assert.equal(r.snapshot().settingsReturn?.overlay, 'search', 'leaving settings returns to the search it was opened from')
  settingsIndex.dispose()
})

test('a Batches result selects the batch and leaves the reader on the list', async () => {
  store()
  const r = resource('mag-h4batch')
  setOpen(r, true)
  openOverlay(r, 'search')
  writePlace(r, 'search', { scroll: 95 })
  let chosen: { ref: string; digest: string } | null = null
  const batch = { ref: 'adm-batch111111', digest: 'a'.repeat(64) }
  const index = createSearchIndex({ resource: r, sources: [rowOf('batchSource', ['Batches'], {
    entries: () => [entryOf(batch.ref, 'Batches', 'Earlier batch', 'collected earlier', () => { chosen = batch; void r.selectBatch?.(batch) })] })] })
  index.opened('')
  openResult(r, index.snapshot().entries[0])
  await tick()
  assert.deepEqual(chosen, batch, 'the entry selects its batch')
  assert.equal(r.snapshot().searchTarget, null, 'a batch selection is not a result to read')
  assert.equal(r.snapshot().searchListScroll, 95, 'the list position is kept')
  index.dispose()
})

test('Back to results restores the list, its filter and its position', () => {
  store()
  const r = resource('mag-h4back')
  setOpen(r, true)
  typeSearch(r, 'drift')
  r.update({ searchType: 'Posts' })
  writePlace(r, 'search', { scroll: 240 })
  const index = createSearchIndex({ resource: r, sources: [evidenceRow(r, 'ent-post111111')] })
  index.opened('drift')
  openResult(r, index.snapshot().entries[0])
  writePlace(r, 'search', { provenance: true })
  backToResults(r)
  const s = r.snapshot()
  assert.equal(s.searchTarget, null)
  assert.equal(s.overlay, 'search', 'Back to results stays in the search')
  assert.equal(placeAt(s, 'search').inspected, null)
  assert.equal(placeAt(s, 'search').provenance, false)
  assert.equal(placeAt(s, 'search').scroll, 240, 'the list is where it was left')
  assert.equal(s.query, 'drift')
  assert.equal(s.searchType, 'Posts')
  index.dispose()
})

// -------------------------------------------------- returning and resuming

test('Return to the tab the search was begun from, and returnRoute is never overwritten', () => {
  store()
  const r = resource('mag-h4return')
  setOpen(r, true)
  goTab(r, 'Files')
  writePlace(r, 'Files', { scroll: 155 })
  // H2 saved a return route when it sent a message. A search must not touch it.
  goTab(r, 'Conversation')
  const saved: MagnetRoute = { ...route(r.snapshot()), tab: 'Files', placeKey: 'Files', placeSnapshot: { ...placeAt(r.snapshot(), 'Files') } }
  r.update({ returnRoute: saved })
  typeSearch(r, 'drift')
  const index = createSearchIndex({ resource: r, sources: [evidenceRow(r, 'ent-post111111')] })
  index.opened('drift')
  openResult(r, index.snapshot().entries[0])
  backToResults(r)
  closeOverlay(r)
  const s = r.snapshot()
  assert.equal(s.overlay, null)
  assert.equal(s.tab, 'Conversation', 'the tab the search was begun from')
  assert.deepEqual(s.returnRoute, saved, 'the Conversation’s own return route survives the whole search')
  index.dispose()
})

test('resume by the retained query, and × clears query, target and overlay', () => {
  store()
  const r = resource('mag-h4resume')
  setOpen(r, true)
  goTab(r, 'Posts')
  typeSearch(r, 'calibration')
  r.update({ searchType: 'Posts' })
  assert.equal(r.snapshot().overlay, 'search')
  closeOverlay(r)
  assert.equal(r.snapshot().overlay, null)
  assert.equal(r.snapshot().query, 'calibration', 'the query stays in the box')
  const toolbar = renderToStaticMarkup(createElement(SearchToolbar, { resource: r }))
  assert.ok(toolbar.includes('value="calibration"'), 'the retained query is in the box')
  assert.ok(toolbar.includes('aria-label="Clear search"'))
  resumeSearch(r)
  assert.equal(r.snapshot().overlay, 'search', 'clicking or Enter re-enters the search')
  assert.equal(r.snapshot().searchType, 'Posts', 'with the previous filter')
  resumeSearch(r)
  assert.equal(r.snapshot().overlay, 'search', 'resuming an open search changes nothing')
  clearSearch(r)
  assert.equal(r.snapshot().query, '')
  assert.equal(r.snapshot().overlay, null)
  assert.equal(r.snapshot().searchTarget, null)
  // An empty query does not resume.
  resumeSearch(r)
  assert.equal(r.snapshot().overlay, null)
})

test('an original route survives an intervening search, its filter, its own inspected item and a Return from it', () => {
  store()
  const r = resource('mag-h4intervening')
  setOpen(r, true)
  goTab(r, 'Posts')
  writePlace(r, 'Posts', { scroll: 420, inspected: 'ent-first1111111', provenance: true })
  r.update({ searchTarget: { kind: 'Posts', item: 'ent-first1111111' } })
  const kept: MagnetRoute = route(r.snapshot())
  // First search: a different phrase, a different filter, a different result.
  typeSearch(r, 'drift')
  r.update({ searchType: 'Posts' })
  const first = createSearchIndex({ resource: r, sources: [evidenceRow(r, 'ent-second111111')] })
  first.opened('drift')
  openResult(r, first.snapshot().entries[0])
  assert.equal(placeAt(r.snapshot(), 'search').inspected, 'ent-second111111')
  backToResults(r)
  closeOverlay(r)
  first.dispose()
  // Second search: another phrase, another filter, another result, and a Return.
  typeSearch(r, 'bounds')
  r.update({ searchType: 'Files' })
  const second = createSearchIndex({ resource: r, sources: [evidenceRow(r, 'ent-third1111111')] })
  second.opened('bounds')
  r.update({ searchType: 'Posts' })
  openResult(r, second.snapshot().entries[0])
  closeOverlay(r)
  second.dispose()
  // The route taken before either search is still exact.
  restore(r, kept)
  const s = r.snapshot()
  assert.equal(s.tab, 'Posts')
  assert.equal(s.overlay, null)
  assert.equal(s.searchTarget?.item, 'ent-first1111111')
  assert.equal(place(s).scroll, 420)
  assert.equal(place(s).inspected, 'ent-first1111111')
  assert.equal(place(s).provenance, true)
})

// ---------------------------------------------- completeness of the index

test('a match present only in a complete() result appears, and the list position survives a late merge', async () => {
  store()
  const r = resource('mag-h4complete')
  const late = deferred<SearchEntry[]>()
  const source: SearchSource = {
    entries: () => [entryOf('loaded-1', 'Posts', 'Loaded page item', 'drift on the loaded page'),
      entryOf('loaded-2', 'Posts', 'Second loaded item', 'more drift')],
    complete: () => late.promise,
  }
  const index = createSearchIndex({ resource: r, sources: [rowOf('evidenceSource', ['Posts'], source)] })
  index.opened('drift')
  const before = index.snapshot()
  assert.deepEqual(before.entries.map((e) => e.key), ['loaded-1', 'loaded-2'])
  assert.equal(before.running, true, 'the completion is running')
  assert.equal(filterEntries(before.entries, 'older', 'All').length, 0, 'the older match is not in hand yet')
  late.resolve([entryOf('older-1', 'Posts', 'An older retained item', 'drift from an older page')])
  await tick()
  const after = index.snapshot()
  assert.deepEqual(after.entries.map((e) => e.key), ['loaded-1', 'loaded-2', 'older-1'],
    'the late merge appends, so the reader’s list position is unmoved')
  assert.equal(after.running, false)
  assert.equal(filterEntries(after.entries, 'older', 'All')[0]?.key, 'older-1',
    'a match present only in the complete() result is searchable')
  assert.equal(after.reports[0].state, 'complete')
  index.dispose()
})

test('mergeByKey keeps what is shown where it is and appends what arrives late', () => {
  const order: string[] = []
  const a = entryOf('a', 'Posts', 'A', ''), b = entryOf('b', 'Posts', 'B', ''), c = entryOf('c', 'Posts', 'C', '')
  assert.deepEqual(mergeByKey(order, [[a, b]]).map((e) => e.key), ['a', 'b'])
  assert.deepEqual(mergeByKey(order, [[b, a], [c]]).map((e) => e.key), ['a', 'b', 'c'], 'order is the order already shown')
  assert.deepEqual(mergeByKey(order, [[a, a, c]]).map((e) => e.key), ['a', 'c'], 'one entry per key')
})

test('a query-independent complete() runs once per opened overlay and never per keystroke', () => {
  store()
  const r = resource('mag-h4once')
  let calls = 0
  const source: SearchSource = { entries: () => [], complete: async () => { calls += 1; return [] } }
  const index = createSearchIndex({ resource: r, sources: [rowOf('evidenceSource', ['Posts'], source)] })
  index.opened('')
  assert.equal(calls, 1, 'one completion per opening')
  index.setQuery('d'); index.setQuery('dr'); index.setQuery('dri'); index.setQuery('drift')
  assert.equal(calls, 1, 'typing never re-runs a query-independent source')
  index.opened('drift')
  assert.equal(calls, 2, 'the next opening completes again')
  index.dispose()
})

test('the query-dependent source is debounced, cached per query, and abandoned when the query changes', async () => {
  store()
  const r = resource('mag-h4debounce')
  const clock = manual()
  const asked: string[] = []
  const aborted: boolean[] = []
  let gate = deferred<SearchEntry[]>()
  const source: SearchSource = {
    entries: () => [],
    queryDependent: true,
    complete: (query, signal) => {
      asked.push(query)
      signal?.addEventListener('abort', () => aborted.push(true))
      return gate.promise
    },
  }
  const index = createSearchIndex({ resource: r, sources: [rowOf('messageSource', ['Conversation'], source)], clock: clock.clock, debounceMs: 300 })
  index.opened('')
  assert.deepEqual(asked, [], 'an empty query asks the server nothing')
  assert.equal(index.snapshot().reports[0].state, 'idle')
  index.setQuery('d'); index.setQuery('dr'); index.setQuery('drift')
  assert.deepEqual(asked, [], 'nothing is asked until typing settles')
  assert.equal(index.snapshot().running, true, 'the header already says it is still searching')
  clock.settle()
  assert.deepEqual(asked, ['drift'], 'one request, for the settled query')
  gate.resolve([entryOf('m1', 'Conversation', 'Your message', 'drift in an older page')])
  await tick()
  assert.equal(index.snapshot().entries[0]?.key, 'm1')
  assert.equal(index.snapshot().reports[0].state, 'complete')
  // A second query asks again; coming back to the first is served from the cache.
  gate = deferred<SearchEntry[]>()
  index.setQuery('bounds')
  clock.settle()
  assert.deepEqual(asked, ['drift', 'bounds'])
  index.setQuery('drift')
  assert.ok(aborted.length >= 1, 'the in-flight request is abandoned when the query changes')
  clock.settle()
  assert.deepEqual(asked, ['drift', 'bounds'], 'a query already answered is not asked again')
  assert.equal(index.snapshot().entries[0]?.key, 'm1', 'its cached result is restored')
  index.dispose()
})

test('a refused complete() is reported as refused and never retried here', async () => {
  store()
  const r = resource('mag-h4refused')
  let calls = 0
  const source: SearchSource = {
    entries: () => [entryOf('loaded', 'Conversation', 'A loaded message', 'drift')],
    queryDependent: true,
    complete: async () => { calls += 1; throw new Error('the search route refused this Conversation') },
    bound: () => 'only the Conversation pages loaded in the card were searched',
  }
  const clock = manual()
  const index = createSearchIndex({ resource: r, sources: [rowOf('messageSource', ['Conversation'], source)], clock: clock.clock })
  index.opened('drift')
  clock.settle()
  await tick()
  const got = index.snapshot()
  assert.equal(got.reports[0].state, 'refused')
  assert.equal(got.reports[0].bound, 'only the Conversation pages loaded in the card were searched')
  assert.deepEqual(got.entries.map((e) => e.key), ['loaded'], 'what the card held is still searched')
  index.setQuery('drift')
  clock.settle()
  assert.equal(calls, 1, 'a refused read is not retried for the same query')
  index.dispose()
})

// --------------------------------------------- the header says what was searched

test('the header states loading, complete, a reached bound and a refusal, each in its own words', () => {
  const loading = scopeSentences([report({ name: 'evidenceSource', kinds: ['Posts', 'Files'], state: 'running', count: 4 })])
  assert.ok(loading.includes(LOADING_SENTENCE), 'a running read says so')
  assert.ok(loading.some((l) => l.includes('4 retained items in the batch shown') && l.includes('still running')))
  assert.ok(!loading.includes(COMPLETE_SENTENCE))

  const complete = scopeSentences([report({ name: 'messageSource', kinds: ['Conversation'], state: 'complete', count: 7 })])
  assert.ok(complete.some((l) => l === 'The Magnet\'s whole own Conversation was searched: 7 matching posts.'))
  assert.ok(complete.includes(COMPLETE_SENTENCE), 'a wholly complete index may say so')

  const refused = scopeSentences([report({ name: 'messageSource', kinds: ['Conversation'], state: 'refused', count: 2, bound: 'this Magnet has no own Conversation yet' })])
  assert.ok(refused.some((l) => l.includes('Only the Conversation pages already loaded in the card were searched (2 matches)') && l.includes('no own Conversation yet')))
  assert.ok(!refused.includes(COMPLETE_SENTENCE), 'a refused read can never read as complete')

  const bounded = scopeSentences([report({ name: 'messageSource', kinds: ['Conversation'], state: 'bounded', count: 300, bound: 'the paged read stopped after 10 pages' })])
  assert.ok(bounded.some((l) => l.includes('more matches exist') && l.includes('10 pages')))
  assert.ok(!bounded.includes(COMPLETE_SENTENCE))

  for (const lines of [loading, complete, refused, bounded]) assert.ok(lines.includes(BOUNDARY_SENTENCE), 'the source boundary is always stated')
  assert.ok(BOUNDARY_SENTENCE.includes('not the sources themselves'))
  assert.equal(searchIsComplete([]), false, 'an empty index is not a complete search')
})

test('the header states Perspective wording history and the batch-selection boundary from the index', () => {
  const partial = scopeSentences([report({ name: 'perspectiveSource', kinds: ['Perspectives'], state: 'idle', count: 3 })])
  assert.ok(partial.some((l) => l === '3 Perspective entries; earlier wordings are not included yet.'))
  const whole = scopeSentences([report({ name: 'perspectiveSource', kinds: ['Perspectives'], state: 'complete', count: 9 })])
  assert.ok(whole.some((l) => l === '9 Perspective entries, searched including every earlier wording.'))
  const batches = scopeSentences([report({ name: 'batchSource', kinds: ['Batches'], state: 'complete', count: 4 })])
  assert.ok(batches.some((l) => l.includes('4 earlier batches listed') && l.includes('selecting one searches that batch in full')
    && l.includes('contents of a batch that is not shown are not indexed')))
})

test('a content type with no integrated source is named as not searched, and nothing is substituted', () => {
  store()
  const r = resource('mag-h4absent')
  // The real registry, exactly as H1's contract commit leaves it.
  const index = createSearchIndex({ resource: r })
  index.opened('drift')
  const got = index.snapshot()
  assert.equal(got.entries.length, 0, 'no source, no entries: nothing is simulated')
  assert.equal(got.reports.length, 6, 'all six of §4’s sources are accounted for')
  assert.equal(searchIsComplete(got.reports), false)
  const lines = scopeSentences(got.reports)
  assert.ok(!lines.includes(COMPLETE_SENTENCE))
  for (const row of MAGNET_SEARCH_SOURCES) {
    const r0 = got.reports.find((x) => x.name === row.name)
    assert.equal(r0?.state, 'absent', `${row.name} is absent, not substituted`)
    assert.ok(lines.some((l) => l.includes(row.module) && l.includes('not searched')), `${row.module} is named as not searched`)
  }
  const html = renderToStaticMarkup(createElement(SearchView, { resource: r, index }))
  assert.ok(html.includes('What was searched'))
  assert.ok(html.includes('not searched'))
  assert.ok(!html.toLowerCase().includes('universal'), 'nothing in the UI calls the search universal')
  index.dispose()
})

test('the index reads entries() live, so what the card has just taken in is searchable at once', () => {
  store()
  const r = resource('mag-h4live')
  let rows: SearchEntry[] = []
  const index = createSearchIndex({ resource: r, sources: [rowOf('messageSource', ['Conversation'], { entries: () => rows })] })
  index.opened('')
  assert.equal(index.snapshot().entries.length, 0)
  rows = [entryOf('m-new', 'Conversation', 'Your message', 'just sent')]
  r.update({})                                   // the card changed; the index is stale
  assert.equal(index.snapshot().entries[0]?.key, 'm-new')
  index.dispose()
})
