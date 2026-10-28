import assert from 'node:assert/strict'
import { columnZone, dockBack, dockFloat, floatObject, floatOut, locate, makePrimary, primaryOf, swapBack, tidyFloats } from '../src/fluid/focus/model'
import { fromLayout, toLayout, type Arr } from '../src/fluid/workspace/place'
import { findZone, fitMeasureKey, keepSlot, zones, type Node, type Zone } from '../src/fluid/workspace/tree'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }
const z = (id: string, name = id): Zone => ({ type: 'zone', id, show: 'objects', name, slot: keepSlot() })
const arr = (tree: Node, focus?: Arr['focus']): Arr => ({ tree, pages: [], ...(focus ? { focus } : {}) })

/* Leaf focus is an exact two-record rewrite: geometry and everyone else stay. */
const tree: Node = { type: 'split', dir: 'row', sizes: [.2, .3, .5], kids: [z('a'), z('b'), z('c')] }
const focused = makePrimary(arr(tree, { primary: 'a' }), 'c')
eq(zones(focused.tree).map((x) => x.id), ['c', 'b', 'a'], 'only the selected and primary leaves trade records')
eq((focused.tree as any).sizes, [.2, .3, .5], 'every share is unchanged')
eq(findZone(focused.tree, 'b'), z('b'), 'the other leaf is unchanged')
eq(primaryOf(focused), 'c', 'the incoming content is primary')
eq(primaryOf(swapBack(focused)), 'a', 'Esc restores the previous primary')

/* Float focus swaps content, never the floating place's rectangle. */
const floated = floatObject(arr(z('stage')), 'live:p:k', 'Survey', { x: 31, y: 42, w: 333, h: 222 })
const fl = floated.focus!.floats![0]
const first = makePrimary(floated, fl.zone.id)
eq(first.focus!.floats![0].zone.id, 'conv', 'the old primary occupies the float')
eq(({ ...first.focus!.floats![0], zone: undefined, id: undefined }), ({ ...fl, zone: undefined, id: undefined }), 'the float rectangle is exact')
eq(columnZone(first).name, 'Survey', 'the floating content occupies the primary column')
const again = makePrimary(first, first.focus!.floats![0].zone.id)
eq(columnZone(again).id, 'conv', 'pressing the same floating window swaps back')
eq(again.focus!.floats![0].zone.name, 'Survey', 'and restores its content')

/* Column and leaf exchange records in place. */
const columnLeaf = makePrimary(arr(z('leaf'), { column: { ...z('special'), show: 'conversation' }, primary: 'special' }), 'leaf')
eq(columnZone(columnLeaf).id, 'leaf', 'leaf content moves to the column')
eq((columnLeaf.tree as Zone).id, 'special', 'column content moves to the same leaf position')

/* Dock back restores the pair's original share. */
const pair = arr({ type: 'split', dir: 'row', sizes: [.3, .7], kids: [z('left'), z('right')] })
const out = floatOut(pair, 'left', { x: 5, y: 6, w: 300, h: 200 })
const back = dockBack(out, out.focus!.floats![0].id)
ok(Math.abs((back.tree as any).sizes[0] - .3) < 1e-12 && Math.abs((back.tree as any).sizes[1] - .7) < 1e-12, 'dock back restores the removed pair share')
eq(zones(back.tree).map((x) => x.id), ['left', 'right'], 'dock back restores its side')

/* A column edge is an outer tree dock: the old tree keeps all its geometry. */
const outerFloat = floatObject(pair, 'live:p:outer', 'Outer', { x: 5, y: 6, w: 300, h: 200 })
const outer = dockFloat(outerFloat, outerFloat.focus!.floats![0].id, columnZone(outerFloat).id, 'left')
eq(zones(outer.tree).map((x) => x.name), ['Outer', 'left', 'right'], 'a column edge docks at the outside of This post')
eq(((outer.tree as any).kids[1] as any).sizes, [.3, .7], 'the existing tree keeps its internal shares')

/* Object centre keeps its live address and closes only that float. */
const target = arr({ ...z('target'), slot: keepSlot() })
const obj = floatObject(target, 'live:p:k', 'One', { x: 0, y: 0, w: 220, h: 120 })
const kept = dockFloat(obj, obj.focus!.floats![0].id, 'target', 'center')
eq((kept.tree as Zone).slot!.items, ['live:p:k'], 'centre keeps the object in the target')
eq(kept.focus?.floats ?? [], [], 'the object float closes')

/* Layout persistence round-trips focus and drops collisions/garbage. */
const layout = toLayout(first)
eq(toLayout(fromLayout(layout)!), layout, 'focus round-trips through storage')
const bad = structuredClone(layout) as any
bad.focus.floats.push({ id: 'stage', zone: z('stage'), x: 0, y: 0, w: 1, h: 1 })
const read = fromLayout(bad)!
eq(read.focus!.floats!.length, 1, 'a float colliding with tree content is dropped')
ok(locate(read, primaryOf(read)), 'the restored primary names present content')

/* Fit rereads placement changes, not changes to what the zone renders. */
const fitted: Node = { type: 'split', dir: 'row', sizes: [.4, .6], kids: [{ ...z('fit'), fit: true }, z('other')] }
const changedContent: Node = { ...(fitted as any), kids: [{ ...(fitted as any).kids[0], name: 'Different object' }, (fitted as any).kids[1]] }
eq(fitMeasureKey(changedContent), fitMeasureKey(fitted), 'Fit content changes do not request another measurement')
const movedFit: Node = { ...(fitted as any), kids: [(fitted as any).kids[1], (fitted as any).kids[0]] }
ok(fitMeasureKey(movedFit) !== fitMeasureKey(fitted), 'moving fitted content to another place requests a measurement')

/* Tidy changes positions only, keeps back-to-front order, and wraps left. */
const tidyStart = arr(z('stage'), { floats: [
  { id: 'f1', zone: z('one'), x: 1, y: 2, w: 300, h: 200 },
  { id: 'f2', zone: z('two'), x: 3, y: 4, w: 260, h: 240 },
  { id: 'f3', zone: z('three'), x: 5, y: 6, w: 220, h: 100 },
] })
const tidied = tidyFloats(tidyStart, 1000, 500)
eq(tidied.focus!.floats!.map((f) => [f.id, f.x, f.y]), [['f1', 688, 12], ['f2', 728, 224], ['f3', 456, 12]], 'Tidy stacks at the right and wraps into a column to its left')
eq(tidied.focus!.floats!.map((f) => [f.id, f.zone.id, f.w, f.h]), tidyStart.focus!.floats!.map((f) => [f.id, f.zone.id, f.w, f.h]), 'Tidy preserves order, content, and sizes')

console.log(`fluid focus: ${checks} checks passed`)
