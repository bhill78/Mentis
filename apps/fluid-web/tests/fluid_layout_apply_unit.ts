import assert from 'node:assert/strict'
import { Holder, fromLayout, layoutPage, restoreSetAside, setAsideOf, toLayout, usePreset, workspace, type Arr, type Named, type PageArr, type Preset } from '../src/fluid/workspace/place'
import { keepSlot, zones, type Node, type Zone } from '../src/fluid/workspace/tree'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const same = (a: unknown, b: unknown, what: string) => { assert.equal(a, b, what); checks++ }
const z = (id: string, items: string[] = [], feed?: string): Zone => ({
  type: 'zone', id, show: 'objects', name: id,
  slot: feed ? { ...keepSlot(items), feed: { source: feed } } : keepSlot(items),
})
const split = (...kids: Zone[]): Node => ({ type: 'split', dir: 'row', sizes: kids.map(() => 1 / kids.length), kids })
const page = (id: string, tree: Node): PageArr => ({ id, title: id, tree })
const arr = (tree: Node, pages: PageArr[] = []): Arr => ({ tree, pages })
const fl = (id: string, zone: Zone, x = 20, y = 30, w = 320, h = 240) => ({ id, zone, x, y, w, h })

const current: Arr = {
  tree: split(z('stage', ['live:p:kept']), z('notes', ['live:p:note'])),
  pages: [],
  focus: {
    previous: ['notes', 'stage'],
    floats: [
      fl('section-float', z('sources', ['live:p:source'])),
      fl('object-float', { ...z('object-zone', ['live:p:chart']), show: 'object' }),
    ],
  },
  setAside: [z('older', ['live:p:older'])],
}
const shape: Arr = {
  tree: split(z('stage', [], 'contents'), z('actions', [], 'actions')),
  pages: [],
  focus: { floats: [fl('fraction-float', z('followups', [], 'followups'), .6, .1, .3, .4)] },
}
const laid = layoutPage(current, shape)
eq((laid.tree as any).kids[0].slot.items, ['live:p:kept'], 'a matching section keeps its placed items')
eq(laid.setAside?.map((x) => x.id), ['notes', 'sources', 'older'], 'displaced and already set-aside sections remain recoverable')
eq(laid.focus?.floats?.map((x) => x.id), ['fraction-float', 'object-float'], 'layout section floats and existing object floats both survive')
eq(laid.focus?.floats?.[0] && [laid.focus.floats[0].x, laid.focus.floats[0].y, laid.focus.floats[0].w, laid.focus.floats[0].h],
  [720, 80, 360, 320], 'fractional preset float geometry resolves against the room')
eq(laid.focus?.previous, ['notes', 'stage'], 'layout application leaves primary swap history unchanged')

const roundTrip = fromLayout(toLayout(laid))!
eq(roundTrip.setAside?.map((x) => x.id), ['notes', 'sources', 'older'], 'set-aside sections round-trip with the Page view')
eq(roundTrip.setAside?.[0].slot?.items, ['live:p:note'], 'set-aside placed items round-trip')

const start = (): Arr => arr(z('root-old', ['live:p:root']), [page('research', z('page-old', ['live:p:page']))])
const h = new Holder(start)
const named: Named = { id: 'test-layout', name: 'Test layout', layout: toLayout(arr(z('new-root'), [page('files', z('files'))])) }
h.applyLayout(named, 'page')
eq(h.arr.tree.id, 'new-root', 'Page scope changes the shown Page')
eq(h.arr.pages[0].tree.id, 'page-old', 'Page scope leaves another Page alone')
eq(h.arr.setAside?.map((x) => x.id), ['root-old'], 'Page scope sets aside the displaced section')
same(h.canUndo(), true, 'Page application is one undoable edit')
h.undo()
eq(h.arr.tree.id, 'root-old', 'one Undo restores the Page application')
same(h.canUndo(), false, 'one Undo consumes the one layout step')

h.applyLayout(named, 'place')
eq(h.arr.tree.id, 'new-root', 'place scope changes This post')
eq(h.arr.pages.find((p) => p.id === 'research')?.tree.id, 'new-root', 'place scope applies the shape to existing Pages')
eq(h.arr.pages.find((p) => p.id === 'research')?.setAside?.map((x) => x.id), ['page-old'], 'place scope sets aside each Page displacement')
same(h.arr.pages.some((p) => p.id === 'files'), true, 'place scope adds a layout Page that is not already present')
same(h.canUndo(), true, 'whole-place application is still one undoable edit')

const presetShape = toLayout(arr(z('preset-stage')))
const preset: Preset = {
  id: 'preset-test', name: 'Preset test', says: 'Test the wrapper', preset: true, share: .5,
  home: presetShape, conversation: presetShape,
}
usePreset(preset)
eq(workspace.arr.tree.id, 'preset-stage', 'usePreset is a thin Page-layout wrapper')
same(setAsideOf('this-post').length, 1, 'the displaced product section is exposed as set aside')
const setAsideId = setAsideOf('this-post')[0].id
restoreSetAside('this-post', setAsideId)
same(setAsideOf('this-post').length, 0, 'restore removes a section from set aside')
same(zones(workspace.arr.tree).some((zone) => zone.id === setAsideId), true, 'restore returns the section to the Page tree')

console.log(`fluid layout apply: ${checks} checks passed`)
