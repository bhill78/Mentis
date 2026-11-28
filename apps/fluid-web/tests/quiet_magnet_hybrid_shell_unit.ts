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
import { MAGNET_COLLECTION_FILTERS, MAGNET_COLLECTION_TABS, MAGNET_PRIMARY_TABS, collectionTabOf, emptyPlaces, closeInspect, inCollection, inspect, goTab, openOverlay, leaveSettings, place, restore, route, setOpen, writePlace } from '../src/quiet2/magnets/places'
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

/** THE OWNER'S HIERARCHY (ent-3191baeb33d2 §1): three primary places, and the
 *  collection as one secondary place with type filters. The six place keys stay
 *  the state spine -- every view keeps its own reading position and the host
 *  still supplies one view per key -- which is what the rest of this file
 *  exercises. */
test('Summary, Perspectives and Conversation are primary; the collection is one secondary place with type filters', () => {
  store()
  // Part 4 adds the fourth filter the approved mockup always showed
  // (`04-browse.png`: All / Posts / Files / Images), closing the seam
  // recorded as `opr-937e911eadcd`. The place keys gain one more member; a
  // place key already absent from a reader's persisted shape still reads
  // back as `emptyPlace()` (`places.ts`), so this is backward-readable.
  assert.deepEqual([...MAGNET_TABS], ['Summary', 'All', 'Posts', 'Files', 'Images', 'Perspectives', 'Conversation'],
    'the place keys, and therefore the persisted shape and the view slots, now carry the fourth filter')
  assert.deepEqual([...MAGNET_PRIMARY_TABS], ['Summary', 'Perspectives', 'Conversation'])
  assert.deepEqual([...MAGNET_COLLECTION_TABS], ['All', 'Posts', 'Files', 'Images'])
  assert.deepEqual(MAGNET_COLLECTION_FILTERS.map((f) => f.label), ['Everything', 'Posts', 'Files', 'Images'])
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
  // The approved order (owner request ent-1e82a8786c37): Summary, Collection,
  // Perspectives, Conversation.
  const order = ['Summary', 'Collection', 'Perspectives', 'Conversation'].map((t) => open.indexOf(`>${t}<`))
  assert.ok(order.every((n, i) => n > 0 && (i === 0 || n > order[i - 1])), `the hierarchy renders in order: ${order}`)
  for (const gone of ['>All<', '>Posts<', '>Files<']) {
    assert.ok(!open.includes(gone), `${gone} is no longer a primary tab of its own`)
  }
  assert.ok(open.includes('aria-label="Magnet settings"'), 'the header gear is icon-only with an accessible name')
  assert.ok(open.includes('q2-magnet-resize-se') && open.includes('aria-label="Close Magnet"'))
  assert.ok(!open.includes('>Settings<'), 'the gear has no visible Settings text')
  // The collection is still one place over three lens places, each keeping its
  // own reading position. What changed is only who draws the controls.
  goTab(r, 'All')
  assert.ok(inCollection(r.snapshot()))
  assert.equal(collectionTabOf(r.snapshot()), 'All')
  const collection = renderToStaticMarkup(createElement(Magnet, { resource: r, onExpand: () => {}, onCollapse: () => {} }))
  assert.ok(!collection.includes('q2-magnet-filters'), 'the frame draws no filter row, in the collection or anywhere else')
  for (const f of MAGNET_COLLECTION_FILTERS) assert.ok(!collection.includes(`>${f.label}<`), `the frame does not draw the ${f.label} filter; Collected items does`)
  goTab(r, 'Files')
  assert.equal(collectionTabOf(r.snapshot()), 'Files', 'a filter is the lens place, so it keeps its own reading position')
  const files = renderToStaticMarkup(createElement(Magnet, { resource: r, onExpand: () => {}, onCollapse: () => {} }))
  assert.match(files, /class="q2-magnet-tab-collection"[^>]*aria-selected="true"/, 'the Collection control is the one selected')
  // The header spends no line on a second count or a standing collection status.
  assert.ok(!files.includes('q2-magnet-head-sub'), 'the header carries no second line')
  assert.ok(!files.includes('>Not yet<') && !files.includes('>Unavailable<'), 'no standing collection status sentence')
})

/** PART A, the approved round-3 chrome (`02-compact-current.png`,
 *  `03-sources.png`): a quiet header, a tab row, a generous body and one footer
 *  line. The frame draws nothing that belongs to a view. */
test('the frame is header, tabs, body and one footer line, and draws no view’s controls', () => {
  store()
  const r = resource('mag-chrome')
  setOpen(r, true)
  const open = renderToStaticMarkup(createElement(Magnet, { resource: r, onExpand: () => {}, onCollapse: () => {} }))
  // The header is the name, then ⤢, ⚙, × -- and nothing else on the line.
  const head = open.slice(open.indexOf('<header'), open.indexOf('</header>'))
  assert.ok(head.includes('Calibration inquiry'), 'the header is the Magnet’s name')
  assert.ok(!head.includes('Collect now'), 'Collect now has left the header for Collection’s Collect manually row')
  assert.ok(!head.includes('q2-magnet-collection'), 'the header carries no collection cluster')
  const icons = ['⤢', '⚙', '×'].map((g) => head.indexOf(g))
  assert.ok(icons.every((n, i) => n > 0 && (i === 0 || n > icons[i - 1])), `⤢ ⚙ × in that order at the far edge: ${icons}`)
  assert.ok(head.indexOf('Calibration inquiry') < icons[0], 'the name comes before the controls')
  assert.ok(head.includes('aria-label="Magnet settings"'), 'the gear is kept: it is the only way to rename or remove a Magnet')
  // No control of a view's is drawn by the frame, on any place.
  assert.ok(!open.includes('q2-magnet-toolbar'), 'no pinned search toolbar row')
  assert.ok(!open.includes('type="search"'), 'the frame draws no search box of its own')
  assert.ok(!open.includes('q2-magnet-filters'), 'no filter pill row')
  // The body is the one scroll container and carries the mockup's body padding.
  assert.match(open, /class="q2-magnet-view mgd-body"/, 'the view container takes design.css’s .mgd-body')
  // The resize hint line was removed from the panel (d3bfa39a, "Correct Magnet
  // composer picker and resize hint"); the frame draws no footer line of its own.
  assert.ok(!open.includes('Drag the panel edge to resize'), 'no resize hint line is drawn')
})

test('the composer is pinned under Conversation only, and never in settings', () => {
  store()
  const r = resource('mag-chromecomposer')
  setOpen(r, true)
  const render = () => renderToStaticMarkup(createElement(Magnet, {
    resource: r, onExpand: () => {}, onCollapse: () => {},
    footerComposer: createElement('form', { id: 'supplied-composer' }, 'composer') }))
  for (const quiet of ['Summary', 'All', 'Posts', 'Files', 'Perspectives'] as const) {
    goTab(r, quiet)
    assert.ok(!render().includes('supplied-composer'), `no approved mockup pins a composer under ${quiet}`)
  }
  goTab(r, 'Conversation')
  assert.ok(render().includes('supplied-composer'), 'Conversation keeps its pinned composer')
  openOverlay(r, 'settings')
  assert.ok(!render().includes('supplied-composer'), 'and settings still has none')
  leaveSettings(r)
  assert.ok(render().includes('supplied-composer'), 'leaving settings returns to Conversation with its composer')
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

test('legacy width preference and per-Magnet dimensions survive recreation', () => {
  const mem = store()
  const a = resource('mag-sizea'), b = resource('mag-sizeb')
  a.update({ dimensions: { width: 720, height: 520 } })
  assert.deepEqual(resource('mag-sizea').snapshot().dimensions, { width: 720, height: 520 })
  assert.equal(b.snapshot().dimensions, undefined)
  mem.set(keyFor('mag-sizeb'), JSON.stringify({ open: false, wide: true }))
  assert.equal(resource('mag-sizeb').snapshot().wide, true)
  assert.equal(cardGeometry(50, 105, 1440, 900, true, a.snapshot().dimensions).width, 720)
  assert.equal(cardGeometry(50, 105, 390, 400, false, a.snapshot().dimensions).maxHeight, 376)
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
  assert.deepEqual(v.places!.search, { scroll: 0, inspected: null, inspectScroll: 0, inspectOrigin: null, provenance: false, history: false, sources: false })
  assert.deepEqual(v.places!.settings, { scroll: 0, inspected: null, inspectScroll: 0, inspectOrigin: null, provenance: false, history: false, sources: false })
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
  assert.deepEqual(emptyPlaces().Summary, { scroll: 0, inspected: null, inspectScroll: 0, inspectOrigin: null, provenance: false, history: false, sources: false })
})

test('the frame is a frame: four slots, one scroll container, no disclosure left in the card', () => {
  store()
  const r = resource('mag-hybridframe')
  setOpen(r, true)
  goTab(r, 'Conversation')
  const html = renderToStaticMarkup(createElement(Magnet, {
    resource: r, onExpand: () => {}, onCollapse: () => {},
    views: { Conversation: createElement('p', null, 'supplied conversation') },
    footerComposer: createElement('form', { id: 'supplied-composer' }, 'composer'),
  }))
  assert.ok(!html.includes('<details'), 'no disclosure survives inside the card')
  assert.equal((html.match(/q2-magnet-view/g) ?? []).length, 1, 'exactly one scroll container')
  assert.ok(html.includes('supplied conversation'), 'the view slot renders what it is given')
  assert.ok(html.includes('supplied-composer'), 'the footer composer slot renders what it is given')
  assert.ok(html.includes('role="tablist"'), 'the tabs slot is present on every tab')
  const frame = frameSource()
  for (const moved of ['postsSection', 'filesSection', 'BatchHistory', 'CollectionConfiguration', 'q2-magnet-scope', 'Workspace navigation', 'Move Magnet']) {
    assert.ok(!frame.includes(moved), `${moved} was moved out of the frame`)
  }
  // The controls the approved design gives to the views are gone from the frame
  // itself, not merely hidden: there is no prop for them and no markup.
  for (const drawn of ['searchToolbar', 'q2-magnet-toolbar', 'q2-magnet-filters', 'resource.collect']) {
    assert.ok(!frame.includes(drawn), `${drawn} is no longer the frame's`)
  }
})

test('the settings overlay shows only the overlay: no composer, and no control of a view’s', () => {
  store()
  const r = resource('mag-hybridoverlay')
  setOpen(r, true)
  goTab(r, 'Conversation')
  openOverlay(r, 'settings')
  const html = renderToStaticMarkup(createElement(Magnet, {
    resource: r, onExpand: () => {}, onCollapse: () => {},
    views: { settings: createElement('p', null, 'supplied settings') },
    footerComposer: createElement('form', { id: 'supplied-composer' }, 'composer'),
  }))
  assert.ok(html.includes('supplied settings'))
  assert.ok(!html.includes('supplied-composer'), 'the composer is hidden in settings')
  assert.ok(!html.includes('type="search"'), 'no search line stands in settings')
  assert.ok(!html.includes('Collect now'), 'collecting is not offered from the frame while settings is open')
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
