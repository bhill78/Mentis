import assert from 'node:assert/strict'
import { pageView, onPage, withPageView } from '../src/fluid/focus/page'
import { fromLayout, pageObjectFloatsOf, toLayout, type Arr } from '../src/fluid/workspace/place'
import { keepSlot, type Node, type Zone } from '../src/fluid/workspace/tree'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const same = (a: unknown, b: unknown, what: string) => { assert.equal(a, b, what); checks++ }
const z = (id: string, items: string[] = [], show = 'objects'): Zone => ({ type: 'zone', id, show, name: id, slot: keepSlot(items) })
const fl = (id: string, zone: Zone) => ({ id, zone, x: 1, y: 2, w: 300, h: 200 })
const canon = (v: unknown): string => JSON.stringify(v, (_k, x) =>
  x && typeof x === 'object' && !Array.isArray(x) ? Object.fromEntries(Object.keys(x).sort().map((k) => [k, x[k]])) : x)

const firstTree: Node = { type: 'split', dir: 'row', sizes: [.4, .6], kids: [z('p1-a'), z('p1-b')] }
const secondTree = z('p2-tree')
const a: Arr = {
  tree: z('post'),
  pages: [
    { id: 'p1', title: 'One', tree: firstTree, focus: {
      primary: 'p1-float', column: z('p1-column'),
      floats: [fl('f1', z('p1-float')), fl('object-one', z('object-zone', ['live:p:one'], 'object'))],
      previous: ['conv', 'p1-a'],
    } },
    { id: 'p2', title: 'Two', tree: secondTree, focus: {
      primary: 'p2-tree', column: z('p2-column'), floats: [fl('f2', z('p2-float'))],
    } },
  ],
}

const layout = toLayout(a)
const restored = fromLayout(layout)!
eq(toLayout(restored), layout, 'two pages round-trip their distinct trees, columns, primaries and section floats')
eq((layout.pages as any[])[0].focus.floats.map((f: any) => f.id), ['f1'], 'a page object float is not saved')
eq(restored.pages[0].focus!.primary, 'p1-float', 'the first page restores only its own primary')
eq(restored.pages[1].focus!.primary, 'p2-tree', 'the second page restores only its own primary')

const crossed = structuredClone(layout) as any
crossed.pages[0].focus.primary = 'p2-tree'
eq(fromLayout(crossed)!.pages[0].focus!.primary, undefined, 'a page cannot restore another pages content as primary')

const legacy = { format: 'mentis.fluid-arrangement', version: 1, tree: z('legacy-post'),
  pages: [{ id: 'legacy', title: 'Legacy', tree: z('legacy-page') }] }
eq(canon(toLayout(fromLayout(legacy)!)), canon({ ...legacy, version: 2 }), 'a legacy layout without page focus loads and writes version 2')

same(pageView(a, 'this-post'), a, 'This post view is the arrangement itself')
same(pageView(a, 'missing'), a, 'an unknown page falls back to This post')
same(pageView(a, 'p1'), pageView(a, 'p1'), 'a page view is memoised')
same(onPage((v) => v, 'p1')(a), a, 'a page no-op returns the same arrangement')
const changedView = { ...pageView(a, 'p1'), tree: z('replacement') }
const changed = withPageView(a, 'p1', changedView)
same(changed.tree, a.tree, 'writing a page view leaves This posts tree alone')
same(changed.pages[0].tree, changedView.tree, 'writing a page view replaces that pages tree')
same(changed.pages[1], a.pages[1], 'writing a page view leaves another page alone')
const postChanged = withPageView(a, 'this-post', { ...a, tree: z('post-replacement') })
eq(postChanged.tree, z('post-replacement'), 'writing This posts view returns the view arrangement')

const travelling: Arr = structuredClone(a)
travelling.focus = { floats: [fl('post-object', z('post-object-zone', ['live:p:post'], 'object'))] }
travelling.pages[1].focus!.floats!.push(
  fl('page-object', z('page-object-zone', ['live:p:page'], 'object')),
  fl('duplicate-object', z('duplicate-object-zone', ['live:p:one'], 'object')),
)
eq(pageObjectFloatsOf(travelling).map((f) => f.zone.slot!.items[0]),
  ['live:p:post', 'live:p:one', 'live:p:page'], 'carry picks object floats from every page and deduplicates by address')

console.log(`fluid page focus: ${checks} checks passed`)
