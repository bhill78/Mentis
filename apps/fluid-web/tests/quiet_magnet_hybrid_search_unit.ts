/** H4: the universal Magnet search.
 *
 *  Proves the search over the whole index rather than over what was loaded: the
 *  results replacing the reading body, the content-type filter, the retained
 *  query/filter/list-position/disclosure on inspect, Back-to-results, Return to
 *  the tab the search was begun from, resume-by-query, the empty-match recovery
 *  and the intervening-search case -- including that a restored route reads the
 *  result it restored rather than one opened since, and that a Return keeps what
 *  was open for the resume; and, against fake sources, that a match
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
import SearchView, { backToResults, clearSearch, openResult, resultFor, resumeSearch, returnFromSearch, SearchToolbar, setSearchType, typeSearch } from '../src/quiet2/magnets/SearchView'
import {
  BOUNDARY_SENTENCE, COMPLETE_SENTENCE, LOADING_SENTENCE, MAGNET_SEARCH_SOURCES,
  createSearchIndex, filterEntries, matchesEntry, mergeByKey, messageOfEntryKey, scopeSentences, searchIsComplete,
  searchTypeLabel, targetEntry,
} from '../src/quiet2/magnets/search'
import type { MagnetSearchSource, SearchClock, SearchSourceReport } from '../src/quiet2/magnets/search'
import {
  MESSAGES_UNMOUNTED, forgetMiniStores, messageSearchSource, miniConversationOf, openMessage,
  type MiniGet,
} from '../src/quiet2/magnets/conversation'
import { MAGNET_SEARCH_TYPES } from '../src/quiet2/magnets/contract'
import type { MagnetResource, MagnetRoute, MagnetSearchKind, MagnetSearchTarget, SearchEntry, SearchSource } from '../src/quiet2/magnets/contract'
import { perspectivesOf } from '../src/quiet2/magnets/perspectives'
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
  assert.ok(html.includes('id="results-title"'), 'the search overlay is the body')
  assert.ok(!html.includes('the summary reading body'), 'results replace the reading body, never stack under it')
  assert.ok(html.includes('Calibration drift'), 'the index is shown')
  assert.equal((html.match(/q2-magnet-view/g) ?? []).length, 1, 'still one scroll container')
  // One search line, in the frame's toolbar: the overlay repeats no second
  // search box and no second standing "Return to …" line (owner request §1, §3).
  assert.equal((html.match(/type="search"/g) ?? []).length, 1, 'exactly one search input in the card')
  assert.ok(html.includes('aria-label="Close search and return to Summary"'), 'the way back is a compact control, and says where it goes')
  assert.ok(!html.includes('← Return to Summary'), 'the standing return line is gone')
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
  // The stored values are unchanged; only the words are the reader's own (§2).
  for (const t of MAGNET_SEARCH_TYPES) {
    assert.ok(all.includes(`value="${t}"`), `the filter still stores ${t}`)
    assert.ok(all.includes(`>${searchTypeLabel(t)}</option>`), `the filter offers ${searchTypeLabel(t)}`)
  }
  assert.equal(searchTypeLabel('All'), 'Everything')
  assert.equal(searchTypeLabel('Batches'), 'Collection history')
  assert.equal(searchTypeLabel('Posts'), 'Posts')
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
  assert.ok(html.includes('Nothing matches. Try another phrase, or another type.'))
  assert.ok(html.includes('Clear the phrase and show everything'))
  assert.ok(html.includes('Search every type'))
  assert.ok(html.includes('aria-label="Close search and return to Summary"'), 'the return control survives an empty result')
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
  // `entry` is the opened entry's own index key, carried so the result can be
  // read back by identity; `item` is still what the source's open() inspected.
  assert.deepEqual(after.searchTarget, { kind: 'Posts', entry: 'ent-post111111', item: 'ent-post111111' }, 'the target is derived from what the source’s open() did')
  assert.equal(placeAt(after, 'search').inspected, 'ent-post111111')
  assert.equal(placeAt(after, 'search').scroll, 0, 'the opened result starts at the top')
  assert.equal(after.places.Perspectives.history, true, 'searching never disturbs the tab it was begun from')
  assert.equal(after.places.Perspectives.scroll, 310)
  // The opened result is read inside the card, not on a separate screen.
  const html = renderToStaticMarkup(createElement(SearchView, { resource: r, index }))
  assert.ok(html.includes('← Back to results'), 'the way back to the list')
  assert.ok(html.includes('aria-label="Close search and return to Perspectives"'), 'and out of the search, to where it was begun')
  // The phrase and the filter are in the one search line above, not repeated
  // over the opened result (owner request §1: no duplicate search).
  assert.ok(!html.includes('Search: drift · Posts'))
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
  assert.deepEqual(r.snapshot().searchTarget, { kind: 'Perspectives', entry: 'ent-lens111111', lens: 'ent-lens111111' })
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

// ------------------------------- the restored result is the inspected one (B1)

/** Two retained posts under one source, each inspecting itself, so an opened
 *  result and the result opened after it are told apart by their own text. */
const twoPostRow = (r: MagnetResource, refs: readonly string[]) =>
  rowOf('evidenceSource', ['Posts'], {
    entries: () => refs.map((ref) => entryOf(ref, 'Posts', `${ref} heading`, `${ref} captured text`, () => inspect(r, ref))),
  })

test('an opened target is resolved from the index, and a click for another target is never read under it', () => {
  const alpha = entryOf('ent-alpha11111111', 'Posts', 'Alpha heading', 'alpha captured text')
  const beta = entryOf('ent-beta111111111', 'Posts', 'Beta heading', 'beta captured text')
  const lens = entryOf('ent-lens111111111', 'Perspectives', 'What drifted?', 'wording')
  const settings = entryOf('settings', 'Settings', 'Sources and collection', 'conversation posts')
  const entries = [alpha, beta, lens, settings]
  const alphaTarget = { kind: 'Posts' as const, item: 'ent-alpha11111111' }
  // The remembered click counts for the target it opened, and for no other.
  assert.equal(resultFor({ target: alphaTarget, entry: alpha }, alphaTarget, entries), alpha)
  assert.equal(resultFor({ target: { kind: 'Posts', item: 'ent-beta111111111' }, entry: beta }, alphaTarget, entries), alpha,
    'a click made for another target is resolved away, never read under this one')
  assert.equal(resultFor(null, alphaTarget, entries), alpha, 'with nothing remembered the index answers')
  // Identity has to agree: the kind, and the key against what the target carries.
  assert.equal(targetEntry(entries, { kind: 'Files', item: 'ent-alpha11111111' }), null, 'the kind must agree')
  assert.equal(targetEntry(entries, { kind: 'Posts', item: 'ent-gone111111111' }), null, 'an item the index does not hold is not guessed at')
  assert.equal(targetEntry(entries, { kind: 'Perspectives', lens: 'ent-lens111111111' }), lens, 'a lens target resolves by its lens')
  assert.equal(targetEntry(entries, { kind: 'Settings' }), settings, 'a target with no item resolves when its kind holds exactly one entry')
  assert.equal(targetEntry(entries, { kind: 'Posts' }), null, 'and never when more than one entry would fit')
  assert.equal(targetEntry([], alphaTarget), null)
  assert.equal(targetEntry(entries, null), null)
})

test('a restored search route reads the result it restored, after an intervening search and mounted again', () => {
  store()
  const r = resource('mag-h4restored')
  setOpen(r, true)
  goTab(r, 'Posts')
  typeSearch(r, 'captured')
  const index = createSearchIndex({ resource: r, sources: [twoPostRow(r, ['ent-alpha11111111', 'ent-beta111111111'])] })
  index.opened('captured')
  const [alpha, beta] = index.snapshot().entries
  openResult(r, alpha)
  // The route H2 saves when the reader leaves the search for the Conversation.
  const kept: MagnetRoute = route(r.snapshot())
  goTab(r, 'Conversation')
  // An intervening search, and another result opened in it.
  typeSearch(r, 'captured')
  openResult(r, beta)
  assert.equal(placeAt(r.snapshot(), 'search').inspected, 'ent-beta111111111')
  restore(r, kept)
  assert.deepEqual(r.snapshot().searchTarget, { kind: 'Posts', entry: 'ent-alpha11111111', item: 'ent-alpha11111111' })
  // Rendering here is a fresh mount, which is also the remount case: nothing of
  // the click survives it, so what is read has to come from the index.
  const html = renderToStaticMarkup(createElement(SearchView, { resource: r, index }))
  assert.ok(html.includes('ent-alpha11111111 heading'), 'the restored result is the one shown')
  assert.ok(html.includes('ent-alpha11111111 captured text'), 'with its own text')
  assert.ok(html.includes('Posts · ent-alpha11111111'), 'and its own attribution')
  assert.ok(!html.includes('ent-beta111111111 captured text'), 'never the text of the result opened since')
  assert.ok(!html.includes('ent-beta111111111 heading'))
  // The owning view is handed the same resolved entry, not a stale one.
  const given: (SearchEntry | null)[] = []
  renderToStaticMarkup(createElement(SearchView, { resource: r, index,
    detail: (_t, entry) => { given.push(entry); return createElement('p', null, 'the owning view') } }))
  assert.deepEqual(given.map((e) => e?.key), ['ent-alpha11111111'], 'detail() receives the restored result')
  index.dispose()
})

test('a target the index cannot identify shows nothing in its place', () => {
  store()
  const r = resource('mag-h4unknown')
  setOpen(r, true)
  openOverlay(r, 'search')
  r.update({ searchTarget: { kind: 'Posts', item: 'ent-missing111111' } })
  const index = createSearchIndex({ resource: r, sources: [twoPostRow(r, ['ent-alpha11111111'])] })
  index.opened('')
  const html = renderToStaticMarkup(createElement(SearchView, { resource: r, index }))
  assert.ok(html.includes('none of its text is shown here'), 'it says the result could not be read back')
  assert.ok(!html.includes('ent-alpha11111111 captured text'), 'and no other result is read under this target')
  assert.ok(html.includes('Posts · ent-missing111111'), 'the attribution stays the target’s own')
  assert.ok(html.includes('← Back to results'), 'the way back is still there')
  index.dispose()
})

// ------------------------------ Return keeps what was open, for the resume (B2)

test('Return keeps the inspected result, and resuming the retained query comes back to it', () => {
  store()
  const r = resource('mag-h4resumetarget')
  setOpen(r, true)
  goTab(r, 'Posts')
  typeSearch(r, 'captured')
  r.update({ searchType: 'Posts' })
  const index = createSearchIndex({ resource: r, sources: [twoPostRow(r, ['ent-alpha11111111'])] })
  index.opened('captured')
  openResult(r, index.snapshot().entries[0])
  const open = r.snapshot().searchTarget
  assert.deepEqual(open, { kind: 'Posts', entry: 'ent-alpha11111111', item: 'ent-alpha11111111' })
  returnFromSearch(r)
  const away = r.snapshot()
  assert.equal(away.overlay, null, 'the overlay closes to the tab the search was begun from')
  assert.equal(away.tab, 'Posts')
  assert.equal(away.searchTarget, null, 'the target never outlives its overlay: the frame’s Escape ordering depends on that')
  assert.equal(away.query, 'captured', 'the query stays in the box')
  resumeSearch(r)
  const back = r.snapshot()
  assert.equal(back.overlay, 'search', 'clicking the retained query re-enters the search')
  assert.equal(back.searchType, 'Posts', 'with the previous filter')
  assert.deepEqual(back.searchTarget, open, 'and with the previous target')
  assert.notEqual(back.searchTarget, open, 'written back as a copy, never as a live reference')
  const html = renderToStaticMarkup(createElement(SearchView, { resource: r, index }))
  assert.ok(html.includes('ent-alpha11111111 heading') && html.includes('ent-alpha11111111 captured text'),
    'the resumed search is reading the result it was left on')
  // Typing is a new search: it resets the target and forgets what was kept.
  returnFromSearch(r)
  typeSearch(r, 'bounds')
  closeOverlay(r)
  resumeSearch(r)
  assert.equal(r.snapshot().overlay, 'search')
  assert.equal(r.snapshot().searchTarget, null, 'a new phrase resumes on the list, not on the old result')
  // Leaving the list rather than a result resumes on the list.
  openResult(r, index.snapshot().entries[0])
  backToResults(r)
  returnFromSearch(r)
  resumeSearch(r)
  assert.equal(r.snapshot().searchTarget, null)
  index.dispose()
})

test('what one Magnet kept to resume is never another Magnet’s', () => {
  store()
  const one = resource('mag-h4keptone')
  const two = resource('mag-h4kepttwo')
  for (const r of [one, two]) { setOpen(r, true); goTab(r, 'Posts'); typeSearch(r, 'captured') }
  const index = createSearchIndex({ resource: one, sources: [twoPostRow(one, ['ent-alpha11111111'])] })
  index.opened('captured')
  openResult(one, index.snapshot().entries[0])
  returnFromSearch(one)
  closeOverlay(two)
  resumeSearch(two)
  assert.equal(two.snapshot().searchTarget, null, 'the other Magnet resumes on its own list')
  resumeSearch(one)
  assert.deepEqual(one.snapshot().searchTarget, { kind: 'Posts', entry: 'ent-alpha11111111', item: 'ent-alpha11111111' })
  index.dispose()
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

test('every one of §4’s sources is wired in the integrated registry, and none is reported absent', () => {
  store()
  const r = resource('mag-h4landed')
  // The real registry, as the integrated build leaves it. Every part has landed,
  // H2's `messageSource` included (wired as its `messageSearchSource` factory),
  // so no content type is reported as not searched. A source dropped from the
  // table, or a `make` reverted to null, fails here.
  const index = createSearchIndex({ resource: r })
  index.opened('drift')
  const got = index.snapshot()
  assert.equal(got.reports.length, 6, 'all six of §4’s sources are accounted for')
  assert.deepEqual(MAGNET_SEARCH_SOURCES.filter((row) => !row.make).map((row) => row.name), [],
    'no §4 source is left unwired in the integrated build')
  for (const row of MAGNET_SEARCH_SOURCES) {
    const r0 = got.reports.find((x) => x.name === row.name)
    assert.notEqual(r0?.state, 'absent', `${row.name} has landed and is read by the index`)
  }
  const lines = scopeSentences(got.reports)
  assert.ok(!lines.some((l) => l.includes('not searched')), 'nothing is named as not searched')
  // Still not a complete claim: the Conversation source is query dependent and
  // its paged read has not returned, so the header may not say it read it all.
  assert.equal(searchIsComplete(got.reports), false)
  assert.ok(!lines.includes(COMPLETE_SENTENCE))
  const html = renderToStaticMarkup(createElement(SearchView, { resource: r, index }))
  assert.ok(html.includes('What was searched'))
  assert.ok(!html.toLowerCase().includes('universal'), 'nothing in the UI calls the search universal')
  index.dispose()
})

// ------------- the real sources' own entries, read back by identity (I3, R2)

/** A card holding real retained items and real Perspective rows, so the index
 *  is built from §4's own exported sources and not from a fake whose entry key
 *  happens to be the id its `open()` inspects. That coincidence is what every
 *  fake above relies on, and what the real sources do not provide:
 *  `evidenceSource` keys an entry `evidence:post:<id>` and inspects `<id>`,
 *  `perspectiveSource` keys `perspective:<p>` and opens `<p>`. */
const realCard = (id: `mag-${string}`) => {
  const r = resource(id)
  setOpen(r, true)
  r.update({ results: [
    { kind: 'post', id: 'ent-postalpha111', value: { title: 'Alpha heading', text: 'Alpha captured drift words' } },
    { kind: 'post', id: 'ent-postbeta1111', value: { title: 'Beta heading', text: 'Beta captured drift words' } },
    { kind: 'file', id: 'ent-filegamma111', value: { title: 'gamma-drift.csv', text: 'Gamma captured drift rows' } },
  ] } as never)
  perspectivesOf(r).update({ rows: [
    { perspective: 'ent-lensalpha111', name: 'What drifted first?', current_question: { text: 'drift one' } },
    { perspective: 'ent-lensbeta1111', name: 'What drifted after?', current_question: { text: 'drift two' } },
  ] } as never)
  return r
}

/** Open one real entry from the results and answer the target that ended up in
 *  the snapshot, whoever wrote it: `openResult` for a result read inside the
 *  overlay, and the source itself for one that navigated out (`openPerspective`
 *  writes its own). */
const openedTarget = (r: MagnetResource, e: SearchEntry): MagnetSearchTarget | null => {
  typeSearch(r, 'drift')
  openResult(r, e)
  return r.snapshot().searchTarget
}

test('a result opened from a real source is read back by the target it wrote, and never another’s', () => {
  store()
  const r = realCard('mag-h4realread')
  const index = createSearchIndex({ resource: r })
  index.opened('drift')
  const entries = index.snapshot().entries.filter((e) => e.kind === 'Posts' || e.kind === 'Files' || e.kind === 'Perspectives')
  assert.ok(entries.length >= 5, `the real sources put their own entries in the index (got ${entries.length})`)

  const opened: { entry: SearchEntry; target: MagnetSearchTarget }[] = []
  for (const e of entries) {
    const target = openedTarget(r, e)
    assert.ok(target, `opening the real ${e.kind} result ${e.key} leaves a target to return to`)
    opened.push({ entry: e, target: target! })
  }
  const now = index.snapshot().entries
  for (const { entry, target } of opened) {
    // Mounted again, with no click remembered: the index alone must identify it.
    assert.equal(targetEntry(now, target)?.key, entry.key,
      `${entry.kind} ${entry.key} is what its own target denotes`)
    assert.equal(resultFor(null, target, now)?.key, entry.key,
      `${entry.kind} ${entry.key} is read back after a remount`)
    // And a click remembered for another result is never read under this one.
    for (const other of opened) {
      if (other.entry.key === entry.key) continue
      assert.equal(resultFor({ target: other.target, entry: other.entry }, target, now)?.key, entry.key,
        `${other.entry.key}'s click is not read under ${entry.key}'s target`)
    }
  }
  index.dispose()
})

test('no real source writes a search target that carries no identity', () => {
  store()
  const r = realCard('mag-h4realidentity')
  const index = createSearchIndex({ resource: r })
  index.opened('drift')
  // Every entry of the real registry, of every kind it holds -- not only the
  // kinds that read inside the overlay. An identity-less target is the one
  // shape under which two entries of a kind could be confused for each other
  // (re-review R1), so no real entry may produce one.
  for (const e of index.snapshot().entries) {
    const target = openedTarget(r, e)
    if (!target) continue           // the source navigated out and wrote none
    assert.ok([target.entry, target.item, target.lens, target.message].some((v) => typeof v === 'string' && v.length > 0),
      `the target written for real ${e.kind} entry ${e.key} carries an identity`)
  }
  index.dispose()
})

test('the Conversation source binds the card’s own store late, and searches by the route when it is there', async () => {
  store()
  const r = resource('mag-h4msgsrc')
  forgetMiniStores(r)
  const asked: string[] = []
  const get: MiniGet = async (path) => {
    asked.push(path)
    return { status: 200, body: { hits: [{ post: 'ent-msg111111', number: 4, snippet: 'drifting calibration', at: 1 }], more: false } }
  }
  // Before the footer bar has mounted its store -- which is where the index is
  // on the card's first opening, because the overlay renders above the bar --
  // the source searches nothing and says so. It does not search by any other
  // route, and it does not bind a store of its own.
  const source = messageSearchSource(r, () => {}, get)
  assert.deepEqual(source.entries(), [])
  assert.deepEqual(await source.complete!('drift'), [])
  assert.equal(source.bound!(), MESSAGES_UNMOUNTED)
  assert.equal(asked.length, 0, 'nothing was asked of the search route with no store')
  // The bar mounts; the same source now reads through that store.
  miniConversationOf(r, true, 'brain-h4@instance-one')
  const found = await source.complete!('drift')
  assert.equal(found.length, 1)
  assert.equal(found[0].kind, 'Conversation')
  assert.equal(found[0].key, 'Conversation:ent-msg111111')
  assert.equal(found[0].title, 'Message #4')
  assert.equal(source.bound!(), null, 'a whole paged read is not reported as bounded')
  assert.ok(asked.length >= 1 && asked[0].startsWith('/fluid/api/search?conversation='), 'the existing search route, not a new one')
  assert.equal(source.queryDependent, true)
  forgetMiniStores(r)
})

test('a message found in the search is read in the Conversation, with the way back saved', () => {
  store()
  const r = resource('mag-h4msgopen')
  setOpen(r, true)
  goTab(r, 'All')
  typeSearch(r, 'drift')
  writePlace(r, 'search', { scroll: 220 })
  openMessage(r, 'ent-msg111111')
  const s = r.snapshot()
  assert.equal(s.tab, 'Conversation', 'the message is read where the message is')
  assert.equal(s.overlay, null, 'the source navigated out of the overlay')
  assert.equal(s.searchTarget, null)
  // The same one-level return H2 saves on send, so the Conversation view's
  // `#return-view` control brings the reader back to the results they came from.
  assert.equal(s.returnRoute?.overlay, 'search')
  assert.equal(s.returnRoute?.query, 'drift')
  assert.equal(s.returnRoute?.placeKey, 'search')
  assert.equal(s.returnRoute?.placeSnapshot.scroll, 220)
  restore(r, s.returnRoute!)
  assert.equal(r.snapshot().overlay, 'search')
  assert.equal(placeAt(r.snapshot(), 'search').scroll, 220, 'the results come back where they were left')
  // A hit that is not an entry reference moves nothing.
  const before = r.snapshot()
  openMessage(r, 'not-a-reference')
  assert.equal(r.snapshot().overlay, 'search')
  assert.equal(r.snapshot().tab, before.tab)
})

/** THE C/D SEAM (owner request §6: "Opening a Conversation search result should
 *  take me directly to the matching message"). C's half: opening a Conversation
 *  hit leaves the exact message in the search target for the Conversation view
 *  to find, mount and scroll to -- a hit older than the loaded page, or inside a
 *  thread, included, since the id is the message's and not an offset. */
test('opening a Conversation hit leaves the exact message in the target, for the Conversation view', () => {
  store()
  const r = resource('mag-h4msgtarget')
  setOpen(r, true)
  goTab(r, 'Summary')
  typeSearch(r, 'drift')
  const older = 'ent-oldmsg111111'
  const index = createSearchIndex({ resource: r, sources: [rowOf('messageSource', ['Conversation'], {
    queryDependent: true,
    entries: () => [entryOf(`Conversation:${older}`, 'Conversation', 'Message #4', 'the drift report', () => openMessage(r, older))],
  })] })
  index.opened('drift')
  const target = openResult(r, index.snapshot().entries[0])
  assert.equal(target, null, 'the source navigated out of the overlay, so there is no result to read in it')
  const s = r.snapshot()
  assert.equal(s.tab, 'Conversation')
  assert.equal(s.overlay, null)
  assert.deepEqual(s.searchTarget, { kind: 'Conversation', entry: `Conversation:${older}`, message: older },
    'the message to open is named, by its own entry id')
  assert.equal(s.returnRoute?.overlay, 'search', 'and the way back to the results is still saved')
  // The id is read from the entry key, which is the message source's own; any
  // other key shape leaves the target as the source left it.
  assert.equal(messageOfEntryKey(`Conversation:${older}`), older)
  assert.equal(messageOfEntryKey('Conversation:not-a-reference'), null)
  assert.equal(messageOfEntryKey('evidence:post:ent-post111111'), null)
  index.dispose()
})

test('a content type with no integrated source is named as not searched, and nothing is substituted', () => {
  store()
  const r = resource('mag-h4absent')
  // The rule, not the registry's current state: a row whose part has not landed
  // its `SearchSource` is reported by name and module as not searched, and is
  // never searched by a substitute assembled in the index.
  const unlanded: MagnetSearchSource = { name: 'messageSource', kinds: ['Conversation'], owner: 'H2', module: 'conversation.ts', make: null }
  const index = createSearchIndex({ resource: r, sources: [held('summarySource', ['Summary'], [entryOf('s-1', 'Summary', 'A fact', 'held')]), unlanded] })
  index.opened('drift')
  const got = index.snapshot()
  assert.equal(searchIsComplete(got.reports), false)
  const lines = scopeSentences(got.reports)
  assert.ok(!lines.includes(COMPLETE_SENTENCE))
  const r0 = got.reports.find((x) => x.name === unlanded.name)
  assert.equal(r0?.state, 'absent', 'an unlanded source is absent, not substituted')
  assert.equal(r0?.count, 0, 'an absent source contributes no entries')
  assert.ok(lines.some((l) => l.includes(unlanded.module) && l.includes('not searched')), 'the module is named as not searched')
  assert.equal(got.entries.filter((e) => e.kind === 'Conversation').length, 0, 'no source, no entries: nothing is simulated')
  const html = renderToStaticMarkup(createElement(SearchView, { resource: r, index }))
  assert.ok(html.includes('What was searched'))
  assert.ok(html.includes('not searched'))
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
