/** H1/H4 frame scroll seam (independent review adm-012e854e39e3, finding B3).
 *
 *  The saved reading position is written by the view that navigates and applied
 *  by the frame. Navigation *inside* one view -- the search's typing, filtering,
 *  opening a result and Back to results -- moves the saved number without
 *  changing which place is shown, and the frame used to apply the position only
 *  when the place, the inspection, `open` or `loading` changed, so those saved
 *  changes never reached the rendered container.
 *
 *  These are the decision and the state either side of that seam. The mounted
 *  reproduction is `quiet_magnet_frame_scroll_browser.py`, which drives the real
 *  DOM in Edge. */
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFileSync } from 'node:fs'
import { magnetScroll, scrollToApply } from '../src/quiet2/magnets/Magnet'
import type { MagnetResource, MagnetSnapshot } from '../src/quiet2/magnets/contract'
import { emptyPlaces, inspect, closeInspect, goTab, place, placeAt, registerViewScroll, remember, writePlace } from '../src/quiet2/magnets/places'

const frameSource = () => readFileSync(new URL('../src/quiet2/magnets/Magnet.tsx', import.meta.url), 'utf8')

/** A resource with nothing behind it: this seam is state and arithmetic only. */
const held = (over: Partial<MagnetSnapshot> = {}) => {
  let current: MagnetSnapshot = { title: 'Seam', loading: false, results: [], x: 32, y: 80, open: true, wide: false,
    tab: 'Summary', overlay: 'search', places: emptyPlaces(), query: 'match', searchType: 'All', searchTarget: null,
    searchListScroll: 0, lens: null, returnRoute: null, settingsReturn: null, context: null, contextSuppressed: false, ...over }
  const r: MagnetResource = { id: 'seam', brainKey: 'fixture', saved: { id: 'mag-seam', name: 'Seam' },
    snapshot: () => current, subscribe: () => () => {}, update: (change) => { current = { ...current, ...change } },
    read: async () => {}, cancel: () => {}, dispose: () => {} }
  return r
}

/** The frame's own reconciliation, as a value: what it would write into the
 *  container for this snapshot, given the container's last reported position
 *  and its live offset. */
const reconcile = (reported: number | null, live: number, s: MagnetSnapshot) => scrollToApply(reported, live, magnetScroll(s))

test('the first reconciliation on a container restores the saved position', () => {
  assert.equal(scrollToApply(null, 0, 420), 420, 'a mounted card opens where the reader left it')
  assert.equal(scrollToApply(null, 0, 0), null, 'nothing to write when the top is already shown')
  assert.equal(scrollToApply(null, 180, 0), 0, 'a remounted container holding a stale offset is returned to the top')
})

test('a position the container already holds is never written again', () => {
  assert.equal(scrollToApply(400, 400, 400), null)
  assert.equal(scrollToApply(400, 400.4, 400), null, 'a sub-pixel container offset counts as being there')
})

test('a position the container itself reported is the reader\'s own, and is left alone', () => {
  // The reader is scrolling: the container reported 330 and the saved number is
  // that same report arriving in a render. Writing it back could only pull a
  // gesture still in flight backwards, so it is not written.
  assert.equal(scrollToApply(330, 520, 330), null)
  assert.equal(scrollToApply(330, 330, 330), null)
  // A number the container never reported is a navigation's, and is applied
  // however far the live offset has drifted -- scroll anchoring and clamping
  // move it without reporting anything.
  assert.equal(scrollToApply(400, 323, 0), 0, 'anchoring having shifted the list does not cancel the navigation')
  assert.equal(scrollToApply(160, 160, 400), 400)
})

test('an unusable saved number is the top, never a negative or fractional write', () => {
  assert.equal(scrollToApply(400, 400, Number.NaN), 0)
  assert.equal(scrollToApply(400, 400, -30), 0)
  assert.equal(scrollToApply(0, 0, Number.POSITIVE_INFINITY), null, 'an infinite number is the top, which is where it already is')
  assert.equal(scrollToApply(400, 400, 299.6), 300)
})

test('search typing and filtering reach the container, which is the B3 failure', () => {
  const r = held()
  registerViewScroll(r, () => 400)
  writePlace(r, 'search', { scroll: 400 })
  // Typing, as the search view writes it: the list position resets to the top.
  remember(r)
  assert.equal(place(r.snapshot()).scroll, 400, 'the live position is remembered before the reset')
  r.update({ query: 'row', overlay: 'search', searchTarget: null, searchListScroll: 0,
    places: { ...r.snapshot().places, search: { ...placeAt(r.snapshot(), 'search'), scroll: 0, inspected: null, inspectScroll: 0, inspectOrigin: null, provenance: false } } })
  assert.equal(reconcile(400, 400, r.snapshot()), 0, 'typing returns the rendered list to the top')
  // Filtering, from a list the reader had scrolled again.
  writePlace(r, 'search', { scroll: 400 })
  r.update({ searchType: 'Posts', searchTarget: null, searchListScroll: 0,
    places: { ...r.snapshot().places, search: { ...placeAt(r.snapshot(), 'search'), scroll: 0 } } })
  assert.equal(reconcile(400, 400, r.snapshot()), 0, 'changing the content type returns the rendered list to the top')
})

test('Back to results puts the rendered list back where it was left', () => {
  const r = held()
  registerViewScroll(r, () => 400)
  writePlace(r, 'search', { scroll: 400 })
  // Opening a result keeps the list position and shows the result from its top.
  remember(r)
  const here = placeAt(r.snapshot(), 'search')
  r.update({ searchListScroll: here.scroll,
    places: { ...r.snapshot().places, search: { ...here, scroll: 0 } } })
  r.update({ searchTarget: { kind: 'Summary' } })
  assert.equal(reconcile(400, 400, r.snapshot()), 0, 'the opened result is read from its top')
  // The reader scrolls the opened result, which writes the same place.
  writePlace(r, 'search', { scroll: 160 })
  assert.equal(reconcile(160, 160, r.snapshot()), null, 'reading the result is the reader scrolling, not a navigation')
  // Back to results restores the stashed list position.
  r.update({ searchTarget: null,
    places: { ...r.snapshot().places, search: { ...placeAt(r.snapshot(), 'search'), scroll: r.snapshot().searchListScroll } } })
  assert.equal(r.snapshot().places.search.scroll, 400)
  assert.equal(reconcile(160, 160, r.snapshot()), 400, 'Back to results reaches the rendered container')
})

test('following the saved number destroys no other per-view state', () => {
  const r = held({ overlay: null, tab: 'Posts' })
  // The frame registers the live container position; `remember` reads it before
  // every navigation, so the fixture moves with the rendered position.
  let live = 310
  registerViewScroll(r, () => live)
  writePlace(r, 'Posts', { scroll: 310 })
  writePlace(r, 'Files', { scroll: 240, history: true })
  writePlace(r, 'search', { scroll: 400 })
  r.update({ searchListScroll: 400, query: 'match', searchType: 'Posts' })
  // A search navigation writes the search place and only the search place.
  r.update({ overlay: 'search', places: { ...r.snapshot().places, search: { ...placeAt(r.snapshot(), 'search'), scroll: 0 } } })
  assert.equal(reconcile(310, 310, r.snapshot()), 0)
  assert.equal(r.snapshot().places.Posts.scroll, 310, 'the covered tab keeps its reading position')
  assert.equal(r.snapshot().places.Files.scroll, 240)
  assert.equal(r.snapshot().places.Files.history, true, 'disclosure elsewhere is untouched')
  assert.equal(r.snapshot().searchListScroll, 400, 'the stashed list position is not cleared by the frame')
  assert.equal(r.snapshot().query, 'match')
  assert.equal(r.snapshot().searchType, 'Posts')
  // And the tab it covered comes back exactly, inspection included.
  live = 0
  goTab(r, 'Posts')
  assert.equal(reconcile(0, 0, r.snapshot()), 310)
  live = 310
  inspect(r, 'ent-post111111')
  assert.equal(reconcile(310, 310, r.snapshot()), 0, 'an inspection is read from its own top')
  writePlace(r, 'Posts', { inspectScroll: 90 })
  assert.equal(reconcile(90, 90, r.snapshot()), null)
  closeInspect(r)
  assert.equal(place(r.snapshot()).scroll, 310, 'leaving the inspection keeps the list position it was entered from')
  assert.equal(reconcile(90, 90, r.snapshot()), 310)
})

test('the frame reconciles on the saved number and the opened result, not only on the place', () => {
  const source = frameSource()
  const effect = source.slice(source.indexOf('const el = view.current'))
  const deps = effect.slice(effect.indexOf('}, ['), effect.indexOf('])') + 2)
  for (const dep of ['open', 'placeKey', 'here.inspected', 'targetKey', 's.loading', 'wantScroll']) {
    assert.ok(deps.includes(dep), `the scroll reconciliation runs when ${dep} changes`)
  }
  assert.ok(!source.includes('view.current.scrollTop = magnetScroll(s)'),
    'the position is reconciled through scrollToApply, never written unconditionally')
  assert.ok(source.includes('reported.current = { el: e.currentTarget, top }'),
    'the scroll handler records what the container reported, per element')
})
