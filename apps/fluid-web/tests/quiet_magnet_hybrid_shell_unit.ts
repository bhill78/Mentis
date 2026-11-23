/** H1: the hybrid Magnet shell, its tabs and its view-state spine.
 *  Checks the approved open model, the width-only size switch, per-place reading
 *  position and disclosure, deep-copy route/restore, the full v1 migration and
 *  that the frame is a frame. */
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFileSync } from 'node:fs'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import Magnet, { cardGeometry, magnetScroll } from '../src/quiet2/magnets/Magnet'
import { MAGNET_TABS } from '../src/quiet2/magnets/contract'
import type { MagnetRoute } from '../src/quiet2/magnets/contract'
import { createMagnetResource } from '../src/quiet2/magnets/state'
import { emptyPlaces, closeInspect, inspect, goTab, openOverlay, leaveSettings, place, restore, route, setOpen, writePlace } from '../src/quiet2/magnets/places'
import { loadWorking, saveWorking } from '../src/quiet2/magnets/workingState'
import { miniComposerDraft, saveMiniComposer } from '../src/quiet2/magnets/conversation'
import { page as binding } from '../src/brainBinding'

const SOURCE = 'ent-source111111'
const brainKey = 'origin|fixture|brain-h1'
const frameSource = () => readFileSync(new URL('../src/quiet2/magnets/Magnet.tsx', import.meta.url), 'utf8')
const store = () => {
  const mem = new Map<string, string>()
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: {
    getItem: (k: string) => mem.get(k) ?? null, setItem: (k: string, v: string) => mem.set(k, v),
    removeItem: (k: string) => mem.delete(k), clear: () => mem.clear() } })
  binding.saw('brain-h1@instance-one')
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
const keyFor = (id: string) => `mentis.magnet.working.v1:${brainKey}:brain-h1@instance-one:${id}`

test('the six approved tabs are in order and Summary is the default', () => {
  store()
  assert.deepEqual([...MAGNET_TABS], ['Summary', 'All', 'Posts', 'Files', 'Perspectives', 'Conversation'])
  const r = resource('mag-hybridtabs')
  assert.equal(r.snapshot().tab, 'Summary')
  assert.equal(r.snapshot().open, false)
  assert.equal(r.snapshot().wide, false)
  const html = renderToStaticMarkup(createElement(Magnet, { resource: r, onExpand: () => {}, onCollapse: () => {} }))
  // Closed: the puck rests with its name and no card.
  assert.ok(html.includes('Calibration inquiry'))
  assert.ok(!html.includes('role="tablist"'), 'a closed Magnet renders no card')
  setOpen(r, true)
  const open = renderToStaticMarkup(createElement(Magnet, { resource: r, onExpand: () => {}, onCollapse: () => {} }))
  const order = [...MAGNET_TABS].map((t) => open.indexOf(`>${t}<`))
  assert.ok(order.every((n, i) => n > 0 && (i === 0 || n > order[i - 1])), `tabs render in the approved order: ${order}`)
  assert.ok(open.includes('aria-label="Magnet settings"'), 'the header gear is icon-only with an accessible name')
  assert.ok(open.includes('aria-label="Expand Magnet"') && open.includes('aria-label="Close Magnet"'))
  assert.ok(!open.includes('>Settings<'), 'the gear has no visible Settings text')
})

test('open is persisted working state toggled only by the puck and the header close', () => {
  const mem = store()
  const r = resource('mag-hybridopen')
  assert.equal(r.snapshot().open, false)
  setOpen(r, true)
  assert.equal(r.snapshot().open, true)
  assert.ok(typeof r.snapshot().openedAt === 'number', 'the open transition writes the activity baseline')
  assert.equal(r.snapshot().previousOpen, undefined)
  const first = r.snapshot().openedAt
  setOpen(r, true)
  assert.equal(r.snapshot().openedAt, first, 'an already-open card is not re-opened')
  setOpen(r, false)
  setOpen(r, true)
  assert.equal(r.snapshot().previousOpen, first, 'reopening carries the previous open time')
  assert.ok([...mem.keys()].some((k) => k.includes('mag-hybridopen')))
  assert.equal(loadWorking(brainKey, 'mag-hybridopen').open, true, 'open survives recreation')
  setOpen(r, false)
  assert.equal(loadWorking(brainKey, 'mag-hybridopen').open, false)
})

test('hover and focus are inert: nothing in the frame opens or closes on a pointer or focus', () => {
  const source = frameSource()
  for (const dead of ['onMouseEnter', 'onMouseLeave', 'setHover', 'setFocused', 'onFocus', 'onBlur', 'pinned', 'expanded:']) {
    assert.ok(!source.includes(dead), `the frame no longer carries ${dead}`)
  }
  assert.ok(source.includes('const open = s.open'), 'the card is open because it is open, not because a pointer is near')
})

test('an unsent draft survives close and reopen', () => {
  store()
  const r = resource('mag-hybriddraft')
  setOpen(r, true)
  saveMiniComposer(r, { ...miniComposerDraft(r), text: 'words not yet sent' })
  setOpen(r, false)
  setOpen(r, true)
  assert.equal(miniComposerDraft(r).text, 'words not yet sent')
})

test('the size button is a width only', () => {
  const narrow = cardGeometry(50, 105, 1440, 900, false)
  const wide = cardGeometry(50, 105, 1440, 900, true)
  assert.equal(narrow.width, 650)
  assert.equal(wide.width, 900)
  const small = cardGeometry(12, 12, 390, 844, false)
  assert.equal(small.width, 390 - 24, 'a narrow screen gives the card the full width')
  assert.equal(cardGeometry(12, 12, 390, 844, true).width, 390 - 24, 'wide changes nothing on a narrow screen')
})

test('every view keeps its own reading position, inspection and disclosure', () => {
  store()
  const r = resource('mag-hybridplaces')
  setOpen(r, true)
  writePlace(r, 'Posts', { scroll: 310 })
  writePlace(r, 'Files', { scroll: 240 })
  writePlace(r, 'Perspectives', { history: true })
  goTab(r, 'Posts')
  assert.equal(place(r.snapshot()).scroll, 310)
  goTab(r, 'Files')
  assert.equal(place(r.snapshot()).scroll, 240)
  goTab(r, 'Perspectives')
  assert.equal(place(r.snapshot()).history, true)
  assert.equal(place(r.snapshot()).scroll, 0, 'an untouched view starts at the top')
  // Overlays are places of their own.
  openOverlay(r, 'search')
  writePlace(r, 'search', { scroll: 90 })
  assert.equal(place(r.snapshot()).scroll, 90)
  assert.equal(r.snapshot().places.Perspectives.history, true, 'opening an overlay keeps the tab it covers')
  // Inspection remembers where it was entered from and returns there.
  leaveSettings(r)
  goTab(r, 'Posts')
  writePlace(r, 'Posts', { scroll: 310 })
  inspect(r, 'ent-post111111', 'item-ent-post111111')
  assert.equal(place(r.snapshot()).inspected, 'ent-post111111')
  assert.equal(place(r.snapshot()).inspectScroll, 0)
  assert.equal(magnetScroll(r.snapshot()), 0, 'an inspection starts at the top of the inspection')
  inspect(r, 'adm-file111111')
  assert.equal(place(r.snapshot()).inspectOrigin, 'item-ent-post111111', 'a deeper inspection keeps the first origin')
  closeInspect(r)
  assert.equal(place(r.snapshot()).inspected, null)
})

test('route and restore deep-copy, so a return survives a second mutation and an intervening search', () => {
  store()
  const r = resource('mag-hybridroute')
  setOpen(r, true)
  goTab(r, 'Posts')
  writePlace(r, 'Posts', { scroll: 420, inspected: 'ent-post111111', provenance: true })
  r.update({ searchTarget: { kind: 'Posts', item: 'ent-post111111' } })
  const kept: MagnetRoute = route(r.snapshot())
  // Mutate live state twice after taking the route.
  writePlace(r, 'Posts', { scroll: 0, inspected: null, provenance: false })
  r.update({ searchTarget: { kind: 'Files', item: 'adm-other111111' } })
  openOverlay(r, 'search')
  r.update({ query: 'calibration', searchType: 'Files' })
  writePlace(r, 'search', { scroll: 77 })
  assert.equal(kept.placeSnapshot.scroll, 420, 'the route kept a copy, not a reference')
  assert.equal(kept.searchTarget?.kind, 'Posts')
  restore(r, kept)
  assert.equal(r.snapshot().tab, 'Posts')
  assert.equal(r.snapshot().overlay, null)
  assert.equal(r.snapshot().searchTarget?.item, 'ent-post111111')
  assert.equal(place(r.snapshot()).scroll, 420)
  assert.equal(place(r.snapshot()).inspected, 'ent-post111111')
  assert.equal(place(r.snapshot()).provenance, true)
  assert.equal(r.snapshot().places.search.scroll, 77, 'the search place it passed through is left as it was')
  // Restoring again from the same route is unaffected by what the first restore wrote.
  writePlace(r, 'Posts', { scroll: 5 })
  restore(r, kept)
  assert.equal(place(r.snapshot()).scroll, 420)
})

test('the settings overlay returns exactly where the gear was pressed', () => {
  store()
  const r = resource('mag-hybridsettings')
  setOpen(r, true)
  goTab(r, 'Files')
  writePlace(r, 'Files', { scroll: 180 })
  openOverlay(r, 'settings')
  assert.equal(r.snapshot().overlay, 'settings')
  assert.equal(r.snapshot().settingsReturn?.tab, 'Files')
  writePlace(r, 'settings', { scroll: 44 })
  leaveSettings(r)
  assert.equal(r.snapshot().overlay, null)
  assert.equal(r.snapshot().tab, 'Files')
  assert.equal(place(r.snapshot()).scroll, 180)
  assert.equal(r.snapshot().settingsReturn, null)
})

/** The full v1 payload: all fourteen keys `workingState.ts` used to write. */
const V1 = {
  x: 152, y: 96, tab: 'Overview', expanded: true, pinned: false,
  inspection: 'ent-inspected111', inspectionScroll: 64,
  inspectionReturn: { tab: 'Files', expanded: true },
  query: 'calibration', scroll: 11,
  scrolls: { Compact: 21, Overview: 130, Posts: 310, Files: 240, Conversation: 105 },
  agentId: 'ent-recipient111111', assistanceMode: 'retained',
  batchSelection: { ref: 'adm-batch111111', digest: 'a'.repeat(64) },
}

test('a literal fourteen-key v1 payload migrates row by row, and nothing durable is lost', () => {
  const mem = store()
  mem.set(keyFor('mag-hybridv1'), JSON.stringify(V1))
  const v = loadWorking(brainKey, 'mag-hybridv1')
  assert.equal(v.x, 152); assert.equal(v.y, 96)                             // x, y unchanged
  assert.equal(v.tab, 'All')                                               // Overview -> All
  assert.equal(v.open, true); assert.equal(v.wide, false)                  // expanded||pinned -> open; wide false
  assert.equal(v.places!.All.inspected, 'ent-inspected111')                // inspection -> places[tab].inspected
  assert.equal(v.places!.All.inspectScroll, 64)                            // inspectionScroll -> same place
  assert.equal(v.places!.All.inspectOrigin, null)
  assert.equal(v.query, 'calibration')                                     // query unchanged
  assert.equal(v.places!.All.scroll, 130)                                  // scrolls wins over scroll for the migrated tab
  assert.equal(v.places!.Posts.scroll, 310)
  assert.equal(v.places!.Files.scroll, 240)
  assert.equal(v.places!.Conversation.scroll, 105)
  assert.equal(v.places!.Summary.scroll, 0)
  assert.ok(!Object.keys(v.places!).includes('Compact'), 'Compact has no hybrid home and is dropped')
  assert.equal(v.agentId, 'ent-recipient111111')
  assert.equal(v.assistanceMode, 'retained')
  assert.deepEqual(v.batchSelection, { ref: 'adm-batch111111', digest: 'a'.repeat(64) })
  // inspectionReturn is kept as the deep return route, not dropped.
  assert.equal(v.returnRoute?.tab, 'Files')
  assert.equal(v.returnRoute?.overlay, null)
  assert.equal(v.returnRoute?.placeKey, 'Files')
  assert.equal(v.returnRoute?.placeSnapshot.scroll, 240)
  // New fields take their defaults.
  assert.equal(v.overlay, null); assert.equal(v.searchType, 'All'); assert.equal(v.searchTarget, null)
  assert.equal(v.searchListScroll, 0); assert.equal(v.settingsReturn, null)
  assert.equal(v.context, null); assert.equal(v.contextSuppressed, false)
  assert.deepEqual(v.places!.search, { scroll: 0, inspected: null, inspectScroll: 0, inspectOrigin: null, provenance: false, history: false })
  assert.deepEqual(v.places!.settings, { scroll: 0, inspected: null, inspectScroll: 0, inspectOrigin: null, provenance: false, history: false })
})

test('v1 `scroll` is used only where `scrolls` has no entry, and the key is not bumped', () => {
  const mem = store()
  const key = keyFor('mag-hybridv1b')
  mem.set(key, JSON.stringify({ tab: 'Posts', scroll: 77, scrolls: { Files: 12 }, pinned: true }))
  const v = loadWorking(brainKey, 'mag-hybridv1b')
  assert.equal(v.places!.Posts.scroll, 77)
  assert.equal(v.places!.Files.scroll, 12)
  assert.equal(v.open, true)
  // The hybrid shape is written back under the same v1 key.
  const r = resource('mag-hybridv1b')
  assert.equal(r.snapshot().tab, 'Posts')
  setOpen(r, false)
  const written = JSON.parse(mem.get(key)!)
  assert.ok('open' in written && 'places' in written && 'returnRoute' in written)
  assert.ok(!('pinned' in written) && !('expanded' in written) && !('scrolls' in written))
  assert.equal(loadWorking(brainKey, 'mag-hybridv1b').open, false, 'the loader reads its own shape back')
})

test('working state never holds collection content, and an unrecognised payload is ignored', () => {
  const mem = store()
  const r = resource('mag-hybridsafe')
  setOpen(r, true)
  r.update({ context: { ref: 'ent-post111111', kind: 'post', label: 'Evidence reference', text: 'Captured words' } })
  saveWorking(brainKey, 'mag-hybridsafe', { ...r.snapshot(), results: [{ kind: 'post', id: 'ent-post111111', value: { text: 'Captured words' } }] })
  assert.ok([...mem.values()].every((v) => !v.includes('Captured words')), 'captured text never enters device storage')
  assert.equal(loadWorking(brainKey, 'mag-hybridsafe').context?.label, 'Evidence reference')
  assert.equal(loadWorking(brainKey, 'mag-hybridsafe').context?.text, undefined)
  mem.set(keyFor('mag-junk'), '{"tab":"Nowhere","open":"yes","places":5}')
  const junk = loadWorking(brainKey, 'mag-junk')
  assert.equal(junk.tab, 'Summary', 'an unrecognised tab falls back to the default')
  assert.equal(junk.open, false, 'an unrecognised open value never opens the card')
  assert.deepEqual(junk.places!.Summary, emptyPlaces().Summary, 'an unreadable places map falls back to empty places')
  assert.deepEqual(emptyPlaces().Summary, { scroll: 0, inspected: null, inspectScroll: 0, inspectOrigin: null, provenance: false, history: false })
})

test('the frame is a frame: six slots, one scroll container, no disclosure left in the card', () => {
  store()
  const r = resource('mag-hybridframe')
  setOpen(r, true)
  const html = renderToStaticMarkup(createElement(Magnet, {
    resource: r, onExpand: () => {}, onCollapse: () => {},
    views: { Summary: createElement('p', null, 'supplied summary') },
    footerComposer: createElement('form', { id: 'supplied-composer' }, 'composer'),
    searchToolbar: createElement('div', { id: 'supplied-toolbar' }, 'toolbar'),
  }))
  assert.ok(!html.includes('<details'), 'no disclosure survives inside the card')
  assert.equal((html.match(/q2-magnet-view/g) ?? []).length, 1, 'exactly one scroll container')
  assert.ok(html.includes('supplied summary'), 'the view slot renders what it is given')
  assert.ok(html.includes('supplied-composer'), 'the footer composer slot renders what it is given')
  assert.ok(html.includes('supplied-toolbar'), 'the search toolbar slot renders what it is given')
  assert.ok(html.includes('Collect now'), 'the foot keeps Collect now')
  assert.ok(html.includes('role="tablist"'), 'the tabs slot is present on every tab')
  const frame = frameSource()
  for (const moved of ['postsSection', 'filesSection', 'BatchHistory', 'CollectionConfiguration', 'q2-magnet-scope', 'Workspace navigation', 'Move Magnet']) {
    assert.ok(!frame.includes(moved), `${moved} was moved out of the frame`)
  }
})

test('the settings overlay hides the composer and the search line, and disables Collect now', () => {
  store()
  const r = resource('mag-hybridoverlay')
  setOpen(r, true)
  openOverlay(r, 'settings')
  const html = renderToStaticMarkup(createElement(Magnet, {
    resource: r, onExpand: () => {}, onCollapse: () => {},
    views: { settings: createElement('p', null, 'supplied settings') },
    footerComposer: createElement('form', { id: 'supplied-composer' }, 'composer'),
    searchToolbar: createElement('div', { id: 'supplied-toolbar' }, 'toolbar'),
  }))
  assert.ok(html.includes('supplied settings'))
  assert.ok(!html.includes('supplied-composer'), 'the composer is hidden in settings')
  assert.ok(!html.includes('supplied-toolbar'), 'the search line is hidden in settings')
  assert.match(html, /disabled=""[^>]*>Collect now<\/button>/, 'Collect now is disabled while settings is open')
})

test('a closed puck shows its name, and a count only once a read has returned', async () => {
  store()
  const r = resource('mag-hybridcount')
  const first = renderToStaticMarkup(createElement(Magnet, { resource: r, onExpand: () => {}, onCollapse: () => {} }))
  assert.ok(first.includes('Calibration inquiry'))
  assert.ok(!first.includes('collected items'), 'before a read the count is genuinely unknown and is not invented')
  await r.read()
  const after = renderToStaticMarkup(createElement(Magnet, { resource: r, onExpand: () => {}, onCollapse: () => {} }))
  assert.ok(after.includes('0 collected items'), 'after a read that returned no batch the count is known')
})
