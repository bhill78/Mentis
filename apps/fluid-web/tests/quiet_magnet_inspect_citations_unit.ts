/** H1 B1 and B2: inspecting never overwrites the saved list position, and a
 *  citation in any tab renders its evidence inside the card.
 *
 *  B1 reproduces the independent review's failing probes (review-probes.ts) and
 *  the close/reopen/Back sequence its headless Edge run measured: `remember()`
 *  used to write the live offset -- the inspection's own -- into `place.scroll`,
 *  so closing the card, changing size, searching, opening settings or inspecting
 *  something nested destroyed the list position `closeInspect()` returns to.
 *
 *  B2 covers the composition `Host.tsx` supplies: every tab slot shows the
 *  inspection its place holds, so the Conversation and Perspectives citation
 *  controls -- which call the same `inspect()` -- are no longer dead. */
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createElement } from 'react'
import type { ReactNode } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MAGNET_PLACE_KEYS, MAGNET_TABS } from '../src/quiet2/magnets/contract'
import type { MagnetPlaceKey } from '../src/quiet2/magnets/contract'
import { createMagnetResource } from '../src/quiet2/magnets/state'
import { closeInspect, goTab, inspect, openOverlay, place, registerViewScroll, remember, setOpen, writePlace } from '../src/quiet2/magnets/places'
import { magnetScroll } from '../src/quiet2/magnets/Magnet'
import { withInspections } from '../src/quiet2/magnets/Inspection'
import { page as binding } from '../src/brainBinding'

const SOURCE = 'ent-source222222'
const brainKey = 'origin|fixture|brain-b1b2'
const store = () => {
  const mem = new Map<string, string>()
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: {
    getItem: (k: string) => mem.get(k) ?? null, setItem: (k: string, v: string) => mem.set(k, v),
    removeItem: (k: string) => mem.delete(k), clear: () => mem.clear() } })
  binding.saw('brain-b1b2@instance-one')
  return mem
}
const POSTS = Array.from({ length: 12 }, (_, i) => ({
  kind: 'post', id: `ent-post22222${i}`, version: `ent-post22222${i}`, conversation: SOURCE, number: i + 1,
  value: { text: `Captured words of retained item ${i + 1}.` },
}))
const configFor = (id: `mag-${string}`) => ({ id, sources: [{ kind: 'conversation' as const, conversation: SOURCE }], selection: {}, conversation: 'ent-own222222',
  collection: { mode: 'one-time' as const }, synthesis: { mode: 'manual' as const },
  notifications: { newItems: false, changes: false, failures: false }, presentation: { renderer: 'disc' as const } })
const resource = (id: `mag-${string}`) => {
  const config = configFor(id)
  return createMagnetResource({ id: `qm-${id}`, brainKey, saved: { id, name: 'Inspection position', config },
    get: async () => ({ status: 200, body: { magnet: id, config,
      activation: { post: 'ent-batch222222', artifact: { ref: 'adm-batch222222', digest: 'b'.repeat(64), size: 42, media_type: 'application/json' }, at: 1, state: 'complete' },
      page: { sources: [{ key: `conversation:${SOURCE}`, source: config.sources[0], status: 'ok', results: POSTS }] } } }) })
}
/** A view scrolled to `at`, as the frame's registered reader reports it. */
const live = (r: ReturnType<typeof resource>) => { let at = 0; registerViewScroll(r, () => at); return (to: number) => { at = to } }

test('B1: remembering during an inspection keeps the list position it was entered from', () => {
  store()
  const r = resource('mag-b1remember')
  setOpen(r, true)
  goTab(r, 'Posts')
  const scrolled = live(r)
  scrolled(310)
  writePlace(r, 'Posts', { scroll: 310 })
  inspect(r, 'ent-post222221')
  // The reader is now reading the inspection, not the list.
  scrolled(64)
  remember(r)
  assert.equal(place(r.snapshot()).scroll, 310, 'the list position is untouched by remembering inside an inspection')
  assert.equal(place(r.snapshot()).inspectScroll, 64, 'the inspection keeps its own offset instead')
  closeInspect(r)
  assert.equal(place(r.snapshot()).scroll, 310)
})

test('B1: a nested inspection keeps the first list position', () => {
  store()
  const r = resource('mag-b1nested')
  setOpen(r, true)
  goTab(r, 'Posts')
  const scrolled = live(r)
  scrolled(310)
  writePlace(r, 'Posts', { scroll: 310 })
  inspect(r, 'ent-post222221')
  scrolled(64)
  inspect(r, 'adm-file222222')
  assert.equal(place(r.snapshot()).scroll, 310)
  closeInspect(r)
  assert.equal(place(r.snapshot()).scroll, 310)
})

test('B1: close, reopen and Back return to the saved list position', () => {
  store()
  const r = resource('mag-b1reopen')
  setOpen(r, true)
  goTab(r, 'Posts')
  const scrolled = live(r)
  scrolled(350)
  remember(r)
  assert.equal(place(r.snapshot()).scroll, 350)
  inspect(r, 'ent-post222225')
  scrolled(120)
  // The header × remembers, then closes. Reopening restores nothing by itself.
  remember(r)
  setOpen(r, false)
  setOpen(r, true)
  assert.equal(place(r.snapshot()).inspected, 'ent-post222225', 'the inspection is still open on reopen')
  assert.equal(magnetScroll(r.snapshot()), 120, 'and shows the inspection where it was left')
  closeInspect(r)
  assert.equal(place(r.snapshot()).scroll, 350, 'Back returns to the list position, not to the inspection offset')
  assert.equal(magnetScroll(r.snapshot()), 350)
})

test('B1: size, search and settings while inspecting leave the list position alone', () => {
  store()
  const r = resource('mag-b1actions')
  setOpen(r, true)
  goTab(r, 'Posts')
  const scrolled = live(r)
  scrolled(350)
  remember(r)
  inspect(r, 'ent-post222223')
  scrolled(90)
  remember(r)                       // the width toggle
  r.update({ wide: true })
  remember(r)                       // typing in the search line
  openOverlay(r, 'settings')
  assert.equal(r.snapshot().places.Posts.scroll, 350)
  assert.equal(r.snapshot().places.Posts.inspected, 'ent-post222223')
  goTab(r, 'Posts')
  closeInspect(r)
  assert.equal(place(r.snapshot()).scroll, 350)
})

test('B1: remembering outside an inspection still writes the list position', () => {
  store()
  const r = resource('mag-b1plain')
  setOpen(r, true)
  goTab(r, 'Posts')
  const scrolled = live(r)
  scrolled(275)
  remember(r)
  assert.equal(place(r.snapshot()).scroll, 275)
  assert.equal(place(r.snapshot()).inspectScroll, 0)
  // An unreadable live offset keeps what was saved rather than resetting it.
  remember(r, Number.NaN)
  assert.equal(place(r.snapshot()).scroll, 275)
  inspect(r, 'ent-post222222')
  writePlace(r, 'Posts', { inspectScroll: 48 })
  remember(r, Number.NaN)
  assert.equal(place(r.snapshot()).inspectScroll, 48, 'the inspection offset is kept the same way')
  assert.equal(place(r.snapshot()).scroll, 275)
})

const slots = (): Record<MagnetPlaceKey, ReactNode> => Object.fromEntries(
  MAGNET_PLACE_KEYS.map((k) => [k, createElement('p', { 'data-view': k }, `${k} view`)])) as Record<MagnetPlaceKey, ReactNode>

test('B2: every tab slot is composed to show the inspection its place holds', () => {
  store()
  const r = resource('mag-b2compose')
  const composed = withInspections(r, slots(), () => {})
  for (const tab of MAGNET_TABS) assert.notEqual(composed[tab], slots()[tab])
  for (const overlay of ['search', 'settings'] as const) {
    assert.equal(renderToStaticMarkup(composed[overlay] as any), `<p data-view="${overlay}">${overlay} view</p>`,
      'the overlays are left exactly as supplied: neither is a place a reference is inspected from')
  }
  // An absent slot is not invented; the frame says the view is unavailable.
  assert.equal(withInspections(r, { Summary: slots().Summary }, () => {}).Conversation, undefined)
})

test('B2: with no inspection, a composed tab renders its own view', () => {
  store()
  const r = resource('mag-b2passthrough')
  setOpen(r, true)
  const composed = withInspections(r, slots(), () => {})
  for (const tab of MAGNET_TABS) {
    goTab(r, tab)
    assert.equal(renderToStaticMarkup(composed[tab] as any), `<p data-view="${tab}">${tab} view</p>`)
  }
})

test('B2: a Conversation citation renders the referenced retained post and its Back', async () => {
  store()
  const r = resource('mag-b2conversation')
  setOpen(r, true)
  await r.read()
  goTab(r, 'Conversation')
  const composed = withInspections(r, slots(), () => {})
  assert.ok(renderToStaticMarkup(composed.Conversation as any).includes('Conversation view'))
  // Exactly what MiniConversation's `onEvidence` does with a cited reference.
  inspect(r, 'ent-post222224')
  const html = renderToStaticMarkup(composed.Conversation as any)
  assert.ok(!html.includes('Conversation view'), 'the citation replaces the view with the evidence, as the card did before extraction')
  assert.ok(html.includes('q2-magnet-inspection'), 'the inline inspection is rendered')
  assert.ok(html.includes('Captured words of retained item 5.'), 'the referenced evidence itself is rendered')
  assert.ok(html.includes('Close evidence inspection'), 'and the one close/Back control is present')
  closeInspect(r)
  assert.ok(renderToStaticMarkup(composed.Conversation as any).includes('Conversation view'), 'Back comes back to the Conversation')
})

test('B2: a Perspectives citation renders its retained artifact reference', async () => {
  store()
  const r = resource('mag-b2perspectives')
  setOpen(r, true)
  await r.read()
  goTab(r, 'Perspectives')
  const composed = withInspections(r, slots(), () => {})
  // An immutable Perspective revision: an adm- reference, not a collected post.
  inspect(r, 'adm-revision222222')
  const html = renderToStaticMarkup(composed.Perspectives as any)
  assert.ok(!html.includes('Perspectives view'))
  assert.ok(html.includes('q2-magnet-inspection'))
  assert.ok(html.includes('Retained artifact'), 'a raw historical revision is shown as a retained artifact, unqualified')
  assert.ok(html.includes('Close evidence inspection'))
  // The inspection belongs to the place it was opened from, not to the card.
  assert.equal(r.snapshot().places.Conversation.inspected, null)
  assert.equal(r.snapshot().places.Perspectives.inspected, 'adm-revision222222')
})

test('B2: the retained collection cited from the Conversation is the batch evidence', async () => {
  store()
  const r = resource('mag-b2batch')
  setOpen(r, true)
  await r.read()
  goTab(r, 'Conversation')
  const composed = withInspections(r, slots(), () => {})
  // MiniConversation's "Inspect retained collection" passes the batch artifact.
  inspect(r, 'adm-batch222222')
  const html = renderToStaticMarkup(composed.Conversation as any)
  assert.ok(html.includes('Retained collection evidence'))
  assert.ok(html.includes('adm-batch222222'))
  assert.ok(html.includes('Close evidence inspection'))
})
