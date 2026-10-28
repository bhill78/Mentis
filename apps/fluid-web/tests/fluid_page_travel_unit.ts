import assert from 'node:assert/strict'

/* Fluid Focus across pages: travelling floats, page-owned floats, and references. */
const mem = new Map<string, string>()
;(globalThis as any).sessionStorage = {
  getItem: (k: string) => mem.get(k) ?? null,
  setItem: (k: string, v: string) => { mem.set(k, v) },
  removeItem: (k: string) => { mem.delete(k) },
}
;(globalThis as any).fetch = async () => { throw new Error('offline in a unit test') }

const { gatherTravel } = await import('../src/fluid/focus/travel')
const { floatObject, floatOut, objectFloatsOf, CONVERSATION_SHOW } = await import('../src/fluid/focus/model')
const { MAX_FLOATS } = await import('../src/fluid/focus/types')
const { pageView, withPageView, THIS_POST } = await import('../src/fluid/focus/page')
const { Holder, toLayout } = await import('../src/fluid/workspace/place')
const { keepSlot, keepIn, zones } = await import('../src/fluid/workspace/tree')

type Arr = import('../src/fluid/workspace/place').Arr
type PageArr = import('../src/fluid/workspace/place').PageArr
type Zone = import('../src/fluid/workspace/tree').Zone
type Node = import('../src/fluid/workspace/tree').Node

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }

const z = (id: string, name = id, slot = keepSlot()): Zone => ({ type: 'zone', id, show: 'objects', name, slot })
const page = (id: string, tree: Node, focus?: Arr['focus']): PageArr => ({ id, title: id, tree, ...(focus ? { focus } : {}) })
const arr = (tree: Node, pages: PageArr[] = [], focus?: Arr['focus']): Arr => ({ tree, pages, ...(focus ? { focus } : {}) })

/* 1. gatherTravel moves object floats from page A to page B and back */
const a0 = arr(z('tree-this'), [page('page-b', z('tree-b'))])
const a1 = floatObject(a0, 'live:obj-1', 'First Object', { x: 10, y: 20, w: 300, h: 200 })
eq(objectFloatsOf(pageView(a1, THIS_POST)).length, 1, 'object floats on This post')
eq(objectFloatsOf(pageView(a1, 'page-b')).length, 0, 'no object floats on page B initially')

// Move to page B
const toB = gatherTravel(a1, 'page-b')
eq(objectFloatsOf(pageView(toB, THIS_POST)).length, 0, 'object float left This post')
eq(objectFloatsOf(pageView(toB, 'page-b')).length, 1, 'object float arrived on page B')
const flB = objectFloatsOf(pageView(toB, 'page-b'))[0]
eq([flB.x, flB.y, flB.w, flB.h], [10, 20, 300, 200], 'same rectangle preserved')
eq(flB.zone.slot!.items, ['live:obj-1'], 'same live address')

// Move back to This post
const toA = gatherTravel(toB, THIS_POST)
eq(objectFloatsOf(pageView(toA, 'page-b')).length, 0, 'object float left page B')
eq(objectFloatsOf(pageView(toA, THIS_POST)).length, 1, 'object float returned to This post')
const flA = objectFloatsOf(pageView(toA, THIS_POST))[0]
eq([flA.x, flA.y, flA.w, flA.h], [10, 20, 300, 200], 'same rectangle returned')
eq(flA.zone.slot!.items, ['live:obj-1'], 'same live address back')

/* 2. Page-owned floats (section/run/conversation) never move */
const treeThis: Node = { type: 'split', dir: 'row', sizes: [0.5, 0.5], kids: [z('sec-a'), z('sec-b')] }
const treePageB: Node = { type: 'split', dir: 'row', sizes: [0.5, 0.5], kids: [z('sec-c'), z('sec-d')] }
let mixed = arr(treeThis, [page('page-b', treePageB)])
mixed = floatOut(mixed, 'sec-a', { x: 1, y: 2, w: 200, h: 100 })
mixed = floatObject(mixed, 'live:travel-obj', 'Travel Object', { x: 50, y: 60, w: 250, h: 150 })

const convFloat = { id: 'fl-conv', zone: { type: 'zone' as const, id: 'z-conv', show: CONVERSATION_SHOW }, x: 11, y: 22, w: 333, h: 444 }
mixed = withPageView(mixed, 'page-b', {
  ...pageView(mixed, 'page-b'),
  focus: { floats: [convFloat] },
})

// Gather to page B:
const atB = gatherTravel(mixed, 'page-b')
const thisPostFloats = pageView(atB, THIS_POST).focus?.floats ?? []
eq(thisPostFloats.length, 1, 'This post kept its page-owned section float')
eq(thisPostFloats[0].zone.id, 'sec-a', 'section float stayed on This post')

const bFloats = pageView(atB, 'page-b').focus?.floats ?? []
eq(bFloats.length, 2, 'Page B has its conversation float plus the travelling object float')
eq(bFloats[0].id, 'fl-conv', 'Page B conversation float stayed')
eq(bFloats[1].zone.slot!.items, ['live:travel-obj'], 'Travelling object float added')

// Gather back to This post:
const atA = gatherTravel(atB, THIS_POST)
eq(pageView(atA, 'page-b').focus?.floats?.length, 1, 'Page B kept its conversation float')
eq(pageView(atA, 'page-b').focus?.floats?.[0].id, 'fl-conv', 'Conversation float remains on Page B')
eq(pageView(atA, THIS_POST).focus?.floats?.length, 2, 'This post has its section float plus travelling float')

/* 3. No duplicate address on a page */
let dupArr = arr(z('tree-1'), [page('page-2', z('tree-2'))])
dupArr = floatObject(dupArr, 'live:same-addr', 'Dup on This post', { x: 10, y: 10, w: 200, h: 200 })
const page2View = floatObject(pageView(dupArr, 'page-2'), 'live:same-addr', 'Dup on Page 2', { x: 30, y: 30, w: 200, h: 200 })
dupArr = withPageView(dupArr, 'page-2', page2View)

const gatheredDup = gatherTravel(dupArr, 'page-2')
const p2Floats = objectFloatsOf(pageView(gatheredDup, 'page-2'))
eq(p2Floats.length, 1, 'no duplicate address created on page 2')
eq(objectFloatsOf(pageView(gatheredDup, THIS_POST)).length, 0, 'This post object float stripped')

/* 4. MAX_FLOATS limit enforced */
let fullB = arr(z('tree-a'), [page('page-b', z('tree-b'))])
for (let i = 0; i < MAX_FLOATS - 1; i++) {
  const v = floatObject(pageView(fullB, 'page-b'), `live:b:${i}`, `B ${i}`, { x: 0, y: 0, w: 100, h: 100 })
  fullB = withPageView(fullB, 'page-b', v)
}
fullB = floatObject(fullB, 'live:a:1', 'A 1', { x: 1, y: 1, w: 100, h: 100 })
fullB = floatObject(fullB, 'live:a:2', 'A 2', { x: 2, y: 2, w: 100, h: 100 })
fullB = floatObject(fullB, 'live:a:3', 'A 3', { x: 3, y: 3, w: 100, h: 100 })

const gatheredFull = gatherTravel(fullB, 'page-b')
const fullFloats = pageView(gatheredFull, 'page-b').focus?.floats ?? []
eq(fullFloats.length, MAX_FLOATS, 'page B float count does not exceed MAX_FLOATS')

/* 5. Identity (a returned) when nothing moves */
const cleanA = arr(z('t1'), [page('p2', z('t2'))])
eq(gatherTravel(cleanA, 'p2'), cleanA, 'identity when no floats exist anywhere')
eq(gatherTravel(toB, 'page-b'), toB, 'identity when traveller is already on target page')

const singlePage = arr(z('t1'))
eq(gatherTravel(singlePage, THIS_POST), singlePage, 'identity for single page')

/* 6. Keeping the same address on two pages leaves one address in two slots (no copy) */
let multiArr = arr(z('z1'), [page('p2', z('z2'))])
multiArr = {
  ...multiArr,
  tree: keepIn(multiArr.tree, 'z1', 'live:ref-object'),
  pages: [{
    ...multiArr.pages[0],
    tree: keepIn(multiArr.pages[0].tree, 'z2', 'live:ref-object'),
  }],
}
const thisSlot = zones(multiArr.tree)[0].slot
const p2Slot = zones(multiArr.pages[0].tree)[0].slot
eq(thisSlot!.items, ['live:ref-object'], 'live address kept in This post slot')
eq(p2Slot!.items, ['live:ref-object'], 'exact same live address kept in page 2 slot')
ok(thisSlot!.items[0] === p2Slot!.items[0], 'no copy of identity or address string')

/* 7. The toLayout of either page never contains the traveller */
const l = toLayout(toB) as any
eq(l.focus?.floats, undefined, 'This post saved layout never has travelling object floats')
eq(l.pages?.[0]?.focus?.floats, undefined, 'Page B saved layout never has travelling object floats')

const lMixed = toLayout(atB) as any
eq(lMixed.focus?.floats?.map((f: any) => f.zone.id), ['sec-a'], 'This post layout keeps only section float')
eq(lMixed.pages?.[0]?.focus?.floats?.map((f: any) => f.id), ['fl-conv'], 'Page B layout keeps only conversation float, not traveller')

/* 8. Holder.carryOver leaves touched, edits, and undoStack alone */
const h = new Holder(() => arr(z('h1'), [page('hp2', z('h2'))]))
h.enter('place-1', 'conversation')
eq(h.changed(), false, 'not changed at start')
eq(h.canUndo(), false, 'no undo at start')

const initialEdits = (h as any).edits
h.carryOver((a) => floatObject(a, 'live:h-obj', 'H Obj', { x: 5, y: 5, w: 200, h: 200 }))
eq(objectFloatsOf(h.arr).length, 1, 'carryOver updated arr')
eq(h.changed(), false, 'carryOver did not mark touched or changed')
eq(h.canUndo(), false, 'carryOver did not create an undo step')
eq((h as any).edits, initialEdits, 'carryOver left edits count unchanged')

console.log(`fluid page travel: ${checks} checks passed`)
