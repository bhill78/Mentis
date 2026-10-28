/* The Focus lens (focus/compose.ts) and the one Esc (fluid/escape.ts), as
 * pure functions: compose, switching keeps the Focus area, Restore is exact,
 * Keep this layout is one arrangement, Esc does one thing in order. */
import assert from 'node:assert/strict'
import {
  backLens, compose, forwardLens, hiddenOf, keepArr, prefHeight, restoreArr, sameTarget, shapeOf, shelfOf, startLens, surfacesOf,
  switchLens, targetExists, tidyInBand, MIN_TILE, LENS_BAR,
} from '../src/fluid/focus/compose'
import { floatObject, floatOut, locate, moveFloat, primaryOf, toFront, makePrimary } from '../src/fluid/focus/model'
import { ESC, escapeOnce, escOrder } from '../src/fluid/escape'
import type { Arr } from '../src/fluid/workspace/place'
import { findZone, keepIn, keepSlot, zones, type Node, type Zone } from '../src/fluid/workspace/tree'
import type { FocusTarget } from '../src/fluid/focus/lens'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }
const z = (id: string, name = id): Zone => ({ type: 'zone', id, show: 'objects', name, slot: keepSlot() })
const arr = (tree: Node, focus?: Arr['focus']): Arr => ({ tree, pages: [], ...(focus ? { focus } : {}) })
const room = { w: 1600, h: 900 }

/* A page: the conversation column, two docked sections, two windows. */
const tree: Node = { type: 'split', dir: 'row', sizes: [.5, .5], kids: [z('notes', 'Notes'), z('sources', 'Sources')] }
let page = floatObject(arr(tree), 'live:p:chart', 'Chart', { x: 900, y: 60, w: 420, h: 300 })
page = floatObject(page, 'live:p:map', 'Map', { x: 200, y: 500, w: 360, h: 260 })
const [w1, w2] = page.focus!.floats!
const chart: FocusTarget = { kind: 'surface', id: w1.zone.id, title: 'Chart' }
const notes: FocusTarget = { kind: 'surface', id: 'notes' }
const post: FocusTarget = { kind: 'object', address: 'live:p2:diagram', title: 'Diagram' }

/* -- compose: the Focus area is genuinely large, and right for each presentation */
const L0 = startLens(page, 'this-post', notes, 'docked')
const docked = compose(room, shapeOf(L0, false))
ok(docked.shelf && docked.shelf.x < docked.area.x, 'Docked: the shelf is beside the area, on the column side')
ok(docked.area.w >= room.w * 0.7 && docked.area.h >= room.h - 2 * 12 - 1, 'Docked: the Focus area takes all but the shelf')
eq(docked.floats, 'shelved', 'Docked: the windows go on the shelf')
eq(docked.stage.y - docked.area.y, LENS_BAR, 'the bar sits on top of the area, the stage below it')
const floating = compose(room, { ...shapeOf(L0, false), presentation: 'floating' })
eq([floating.area.w, floating.area.h], [room.w - 24, room.h - 24], 'Floating: the Focus area is the main area')
eq([floating.floats, floating.docked], ['shown', 'hidden'], 'Floating: windows stay real windows over it')
const mixed = compose(room, { ...shapeOf(L0, false), presentation: 'mixed' })
eq([mixed.floats, mixed.docked, !!mixed.shelf], ['shown', 'shelved', true], 'Mixed: a shelf for the docked, windows stay windows')
const only = compose(room, { ...shapeOf(L0, false), presentation: 'only' })
eq([only.area, only.shelf, only.floats], [{ x: 12, y: 12, w: room.w - 24, h: room.h - 24 }, null, 'hidden'], 'Only Focus: the whole Page, the rest hidden')
const narrow = compose({ w: 390, h: 760 }, shapeOf(L0, true))
eq([narrow.presentation, narrow.area], ['only', { x: 0, y: 0, w: 390, h: 760 }], 'narrow screens behave as Only Focus')
const tiny = compose({ w: 0, h: 0 }, shapeOf(L0, true))
ok(tiny.stage.h >= 0 && tiny.area.w >= 0, 'an unmeasured room does not produce negative geometry')
const hid = compose(room, { ...shapeOf(L0, false), presentation: 'floating', hideOthers: true })
eq(hid.floats, 'hidden', 'Hide other windows hides them')
eq(compose(room, { ...shapeOf(L0, false), presentation: 'floating' }).floats, 'shown', 'and again shows them (reversible)')

/* -- the shelf: everything else, content-aware heights, nothing squeezed */
const shelved = shelfOf(page, notes, docked).map((s) => s.id)
eq(shelved, ['conv', 'sources', w2.zone.id, w1.zone.id], 'Docked shelf: the column, the docked sections, the windows front first; not the target')
eq(shelfOf(page, notes, mixed).map((s) => s.id), ['conv', 'sources'], 'Mixed shelf: the docked only')
eq(hiddenOf(page, notes, only).map((s) => s.id).sort(), ['conv', 'sources', w1.zone.id, w2.zone.id].sort(), 'Only Focus: the compact control reveals all the rest')
eq(hiddenOf(page, notes, floating).map((s) => s.id), ['conv', 'sources'], 'Floating: the docked are what is revealed')
ok(prefHeight('conversation', 900) >= 420 && prefHeight('post', 900) >= MIN_TILE && prefHeight('chart', 900) > prefHeight('post', 900), 'heights follow content, never under the minimum')

/* -- switching keeps the Focus area: same geometry, same presentation */
const L1 = switchLens(L0, chart)
eq(compose(room, shapeOf(L1, false)), docked, 'switching to a window: the Focus area does not move or shrink')
const L2 = switchLens(L1, post)
eq(compose(room, shapeOf(L2, false)), docked, 'switching to a small object: still the same area')
eq([L2.presentation, L2.shelfFor, L2.entry], [L0.presentation, L0.shelfFor, L0.entry], 'presentation, shelf and the entry are fixed for the session')
eq(L2.history.map((t) => (t.kind === 'surface' ? t.id : t.address)), ['notes', w1.zone.id], 'history keeps the earlier targets, newest last')
eq(switchLens(L2, post), L2, 'focusing the target again is no step')

/* -- Esc / ‹ step back through history; › forward */
const B1 = backLens(L2, (t) => targetExists(page, t))!
ok(sameTarget(B1.target, chart) && sameTarget(B1.forward[0], post), 'back: the previous target, the one left is forward')
const F1 = forwardLens(B1, (t) => targetExists(page, t))!
ok(sameTarget(F1.target, post), 'forward: the target stepped back from')
const B2 = backLens(backLens(L2, () => true)!, () => true)!
ok(sameTarget(B2.target, notes), 'back again: the first target')
eq(backLens(B2, () => true), null, 'at the start of history there is nothing to step back to (Esc then restores)')
const gone = backLens(L2, (t) => !sameTarget(t, chart))!
ok(sameTarget(gone.target, notes), 'a target no longer on the Page is skipped')

/* -- Restore is exact: rects and stacking come back; content edits stay */
const L = startLens(page, 'this-post', chart, 'floating')
let during = moveFloat(page, w1.id, { x: 5, y: 5, w: 600, h: 500 })
during = moveFloat(during, w2.id, { x: 40, y: 40, w: 300, h: 200 })
during = toFront(during, w1.id)
during = { ...during, tree: keepIn(during.tree, 'notes', 'live:p:kept') }
during = floatObject(during, 'live:p:new', 'New', { x: 10, y: 10, w: 300, h: 200 })
const restored = restoreArr(during, L.entry)
eq(restored.focus!.floats!.slice(0, 2).map(({ id, x, y, w, h }) => ({ id, x, y, w, h })), L.entry.floats, 'restore: every window back at its rect, in its stacking order')
eq(restored.focus!.floats!.at(-1)!.zone.name, 'New', 'a window opened during Focus stays, in front')
eq(findZone(restored.tree, 'notes')!.slot!.items, ['live:p:kept'], 'what was kept during Focus stays kept')
eq(restored.tree, during.tree, 'the docked tree is never touched by the lens')
eq(restoreArr(page, L.entry), page, 'nothing moved: restore is no change at all')
eq(primaryOf(restored), primaryOf(page), 'restore leaves Primary as it was')

/* -- a docked section floated during Focus goes back to its dock on Restore */
{
  const L2 = startLens(page, 'this-post', post, 'mixed')
  const floated = floatOut(page, 'sources', { x: 700, y: 80, w: 400, h: 300 })
  ok(locate(floated, 'sources')?.place === 'float', 'floating a docked section during Focus makes it a window')
  const back = restoreArr(floated, L2.entry)
  eq(locate(back, 'sources')?.place, 'leaf', 'Restore docks it again where it was')
  eq(back.tree, page.tree, 'the tree is the entry tree again')
  eq((back.focus?.floats ?? []).map((f) => f.id), (page.focus?.floats ?? []).map((f) => f.id), 'the windows are the entry windows again')
}

/* -- Keep this layout: one ordinary arrangement */
const keptLeaf = keepArr(page, startLens(page, 'p', notes, 'mixed'), mixed, 'Notes')
eq(primaryOf(keptLeaf), 'notes', 'kept: the target is Primary')
eq((keptLeaf.tree as any).sizes, [.3, .7], 'kept: the target takes 0.7 of the row, away from the shelf')
eq(zones((keptLeaf.tree as any).kids[1]).map((x) => x.id), ['notes'], 'kept: the target is the main section')
eq(keptLeaf.focus!.previous, ['conv'], 'kept: the old Primary is on the Esc history')
eq(keptLeaf.focus!.floats!.length, 2, 'Mixed: the windows stay windows')
const keptObj = keepArr(page, L2, docked, 'Diagram')
const main = (keptObj.tree as any).kids[1] as Zone
eq([main.show, main.slot!.items], ['object', ['live:p2:diagram']], 'an object target is kept as its own section')
eq(keptObj.focus?.floats ?? [], [], 'Docked: the shelved windows are docked')
ok(zones(keptObj.tree).some((x) => x.id === w1.zone.id) && zones(keptObj.tree).some((x) => x.id === w2.zone.id), 'and every one is still on the Page')
eq(primaryOf(keptObj), main.id, 'and the object is Primary')
const keptWin = keepArr(page, startLens(page, 'p', chart, 'floating'), floating, 'Chart')
ok(locate(keptWin, w1.zone.id)?.place === 'leaf' && keptWin.focus!.floats!.length === 1, 'a window kept in Focus becomes the main section; the others stay windows')

/* -- Tidy around Focus: windows in the band, reversible, nothing under the least */
const tl = { ...L, tidy: {} }
const band = compose(room, { ...shapeOf(tl, false), tidy: true })
ok(band.band && band.area.w < floating.area.w, 'tidy reserves a band beside the Focus area')
const t = tidyInBand(page.focus!.floats!, band.band!)
ok(Object.values(t).every((r) => r.x === band.band!.x && r.w === band.band!.w && r.h >= 120), 'each window is aligned in the band, readable')
ok(t[w1.id].y + t[w1.id].h <= t[w2.id].y, 'they do not overlap when they fit')
const many = tidyInBand(Array.from({ length: 9 }, (_, i) => ({ id: 'f' + i, h: 300 })), band.band!)
ok(Object.values(many).every((r) => r.h >= 120 && r.y + r.h <= band.band!.y + band.band!.h + 0.5), 'too many share the band, none under the least, none past it')

/* -- surfaces: every surface, once */
eq(surfacesOf(page).map((s) => s.place), ['column', 'leaf', 'leaf', 'float', 'float'], 'the column, the docked, the windows')
ok(makePrimary(page, 'sources') !== page, 'Make primary is untouched by the lens (still today’s swap)')

/* -- the one Esc: highest priority first, one thing, nothing else */
const did: string[] = []
const h = (name: string, priority: number, does: boolean, n: number) => ({ priority, n, handler: () => { did.push(name); return does } })
const e = {} as KeyboardEvent
eq(escapeOnce([h('primary', ESC.primary, true, 1), h('lens', ESC.lens, true, 2), h('peek', ESC.peek, true, 3), h('sheet', ESC.sheet, false, 4)], e), true, 'Esc is used')
eq(did, ['sheet', 'peek'], 'a sheet first, then Peek: Peek closes and nothing else happens')
did.length = 0
escapeOnce([h('primary', ESC.primary, true, 1), h('lens', ESC.lens, true, 2), h('detail', ESC.detail, false, 3)], e)
eq(did, ['detail', 'lens'], 'with nothing open, Focus steps back before the primary swaps back')
did.length = 0
escapeOnce([h('primary', ESC.primary, true, 1), h('lens', ESC.lens, false, 2)], e)
eq(did, ['lens', 'primary'], 'with no Focus, Esc swaps the primary back')
eq(escOrder([{ priority: 1, n: 1 }, { priority: 1, n: 2 }]).map((x) => x.n), [2, 1], 'of equal priority, the most recent first')
ok(ESC.sheet > ESC.peek && ESC.peek > ESC.detail && ESC.detail > ESC.lens && ESC.lens > ESC.primary, 'the order: sheet, Peek / open object, Focus, previous primary')
eq(escapeOnce([], e), false, 'nobody to ask: Esc is left alone')

console.log(`fluid lens: ${checks} checks passed`)
