import assert from 'node:assert/strict'

/* The pin on a floating window (owner feedback): a pinned window goes with the
   owner across Pages and conversations; an unpinned one stays where it was
   made. Old travel entries and old saved arrangements still read. */
const mem = new Map<string, string>()
;(globalThis as any).sessionStorage = {
  getItem: (k: string) => mem.get(k) ?? null,
  setItem: (k: string, v: string) => { mem.set(k, v) },
  removeItem: (k: string) => { mem.delete(k) },
}
;(globalThis as any).fetch = async () => { throw new Error('offline in a unit test') }

const { gatherTravel } = await import('../src/fluid/focus/travel')
const { canPin, carryPinnedFloats, closeFloat, floatObject, floatOut, floatRun, objectFloatsOf, pinnedFloatsOf, setPinned, toFront } = await import('../src/fluid/focus/model')
const { restoreArr, entryOf } = await import('../src/fluid/focus/compose')
const { pageView, THIS_POST } = await import('../src/fluid/focus/page')
const { Holder, fromLayout, pagePinnedFloatsOf, readTravel, toLayout } = await import('../src/fluid/workspace/place')
const { keepSlot } = await import('../src/fluid/workspace/tree')

type Arr = import('../src/fluid/workspace/place').Arr
type PageArr = import('../src/fluid/workspace/place').PageArr
type Zone = import('../src/fluid/workspace/tree').Zone
type Node = import('../src/fluid/workspace/tree').Node

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }

const z = (id: string): Zone => ({ type: 'zone', id, show: 'objects', name: id, slot: keepSlot() })
const page = (id: string, tree: Node): PageArr => ({ id, title: id, tree })
const arr = (tree: Node, pages: PageArr[] = []): Arr => ({ tree, pages })
const idOf = (a: Arr, address: string) => a.focus!.floats!.find((f) => f.zone.slot?.items[0] === address)!.id
const addresses = (a: Arr) => (a.focus?.floats ?? []).map((f) => f.zone.slot?.items[0] ?? f.zone.id)

/* 1. The pin is part of the float record; only windows that show something of the owner's can carry it. */
let a = arr({ type: 'split', dir: 'row', sizes: [.5, .5], kids: [z('s1'), z('s2')] }, [page('p2', z('p2-tree'))])
a = floatObject(a, 'post:42', 'A post', { x: 30, y: 40, w: 320, h: 240 }, undefined, 'Dungeons and Dragons · #4')
a = floatObject(a, 'live:r:chart', 'A chart', { x: 400, y: 40, w: 300, h: 200 })
const postId = idOf(a, 'post:42')
const pinnedA = setPinned(a, postId, true)
eq(pinnedA.focus!.floats!.find((f) => f.id === postId)!.pinned, true, 'pinned: the float record says so')
eq(setPinned(pinnedA, postId, true), pinnedA, 'pinning twice changes nothing')
eq(setPinned(setPinned(pinnedA, postId, false), postId, false).focus!.floats!.find((f) => f.id === postId)!.pinned, undefined, 'unpinned: the flag is gone')
const withRun = floatRun(a, 'run-9', 'Claude', { x: 0, y: 0, w: 300, h: 200 })
const runFloat = withRun.focus!.floats!.find((f) => f.zone.show === 'run')!
eq(setPinned(withRun, runFloat.id, true), withRun, 'a run window cannot be pinned')
ok(!canPin({ type: 'zone', id: 'conv', show: 'conversation' }), 'nor can the conversation')
const withSection = floatOut(a, 's2', { x: 5, y: 5, w: 260, h: 180 })
const sectionFloat = withSection.focus!.floats!.find((f) => f.zone.id === 's2')!
ok(setPinned(withSection, sectionFloat.id, true) !== withSection, 'a section window can be pinned')

/* 2. Across Pages: pinned moves to the Page shown, unpinned stays on its own. */
const toP2 = gatherTravel(pinnedA, 'p2')
eq(addresses(pageView(toP2, 'p2')), ['post:42'], 'the pinned post went to Page 2')
eq(addresses(pageView(toP2, THIS_POST)), ['live:r:chart'], 'the unpinned chart stayed on This post')
const moved = pageView(toP2, 'p2').focus!.floats![0]
eq([moved.x, moved.y, moved.w, moved.h], [30, 40, 320, 240], 'same rectangle')
eq(moved.zone.options, { says: 'Dungeons and Dragons · #4' }, 'its provenance goes with it')
eq(gatherTravel(a, 'p2'), a, 'nothing pinned: nothing moves between Pages')

/* 3. Front-most order kept: two pinned windows arrive in the order they were stacked. */
let two = floatObject(arr(z('t'), [page('q', z('q-tree'))]), 'live:x:1', 'One', { x: 0, y: 0, w: 220, h: 120 })
two = floatObject(two, 'live:x:2', 'Two', { x: 50, y: 50, w: 220, h: 120 })
two = setPinned(setPinned(two, idOf(two, 'live:x:1'), true), idOf(two, 'live:x:2'), true)
two = toFront(two, idOf(two, 'live:x:1'))
eq(addresses(pageView(gatherTravel(two, 'q'), 'q')), ['live:x:2', 'live:x:1'], 'back to front as it was')

/* 4. Layouts: no saved layout keeps a pinned window or an object window; this tab's copy keeps the unpinned object window. */
const saved = toLayout(pinnedA) as any
eq(saved.focus?.floats, undefined, 'a saved layout keeps neither')
const tab = toLayout(pinnedA, { tab: true }) as any
eq(tab.focus.floats.map((f: any) => f.zone.slot.items[0]), ['live:r:chart'], "this tab's copy keeps the unpinned chart, never the pinned post")
eq(addresses(fromLayout(tab)!), ['live:r:chart'], 'and reads it back')
const pinnedSection = setPinned(withSection, sectionFloat.id, true)
eq((toLayout(pinnedSection) as any).focus?.floats, undefined, 'a pinned section window is no part of the layout either')
eq((toLayout(withSection) as any).focus.floats.map((f: any) => f.zone.id), ['s2'], 'unpinned, a section window is saved as before')

/* 5. Old data: a saved layout from before pins reads as it did; a travel entry kept before pins reads pinned. */
const oldLayout = { format: 'mentis.fluid-arrangement', version: 2, tree: z('old'),
  focus: { floats: [{ id: 'fl-old', zone: z('old-float'), x: 1, y: 2, w: 300, h: 200 }] } }
const oldRead = fromLayout(oldLayout)!
eq(oldRead.focus!.floats!.map((f) => [f.id, f.pinned]), [['fl-old', undefined]], 'an old section float reads, unpinned')
const oldTravel = [{ id: 'fl-t', zone: { type: 'zone', id: 'object-t', show: 'object', name: 'T', slot: keepSlot(['live:t:1'], 'focus'), options: { says: 'Old · #1' } }, x: 9, y: 9, w: 260, h: 180 }]
eq(readTravel(oldTravel).map((f) => [f.id, f.pinned]), [['fl-t', true]], 'an old travel entry (an object float) reads pinned: it was with the owner')
eq(readTravel([{ id: 'fl-s', zone: z('sec'), x: 0, y: 0, w: 260, h: 180 }]), [], 'an unpinned section is never a travel entry')
eq(readTravel([{ id: 'fl-s', zone: z('sec'), x: 0, y: 0, w: 260, h: 180, pinned: true }]).length, 1, 'a pinned section is')
eq(readTravel('nonsense'), [], 'nonsense reads as nothing')

/* 6. Across conversations (the workspace Holder): pinned is carried, unpinned stays in its conversation. */
mem.clear()
const carry = { pick: pagePinnedFloatsOf, bring: carryPinnedFloats }
const h = new Holder(() => arr(z('start')), { carry })
h.enter('conv-a', 'conversation')
h.edit((x) => floatObject(x, 'post:42', 'A post', { x: 30, y: 40, w: 320, h: 240 }, undefined, 'Dungeons and Dragons · #4'))
h.edit((x) => floatObject(x, 'live:r:chart', 'A chart', { x: 400, y: 40, w: 300, h: 200 }))
h.edit((x) => setPinned(x, idOf(x, 'post:42'), true))
h.enter('conv-b', 'conversation')
eq(addresses(h.arr), ['post:42'], 'in B: only the pinned post came along')
eq(h.arr.focus!.floats![0].zone.options, { says: 'Dungeons and Dragons · #4' }, 'still saying where it came from')
eq(JSON.parse(mem.get('mentis.fluid.travel')!).map((f: any) => [f.zone.slot.items[0], f.pinned]), [['post:42', true]], 'kept in this tab as travel, pinned')
h.enter('conv-a', 'conversation')
eq(addresses(h.arr).sort(), ['live:r:chart', 'post:42'], 'back in A: the chart is where it was made, the post is with the owner, each once')
h.edit((x) => setPinned(x, idOf(x, 'post:42'), false))
h.enter('conv-b', 'conversation')
eq(objectFloatsOf(h.arr).length, 0, 'unpinned in A, it stays in A')
h.enter('conv-a', 'conversation')
eq(addresses(h.arr).sort(), ['live:r:chart', 'post:42'], 'and is still there')
h.edit((x) => setPinned(setPinned(x, idOf(x, 'post:42'), true), idOf(x, 'live:r:chart'), true))
const again = new Holder(() => arr(z('start')), { carry })
again.enter('conv-c', 'conversation')
eq(addresses(again.arr), ['live:r:chart', 'post:42'], 'after a reload, the pinned windows are still with the owner, in their stacking order')
h.edit((x) => setPinned(x, idOf(x, 'post:42'), false))
h.edit((x) => closeFloat(x, idOf(x, 'live:r:chart')))
h.enter('conv-b', 'conversation')
eq(pinnedFloatsOf(h.arr).length, 0, 'closed, a pinned window does not come back')

/* 7. Focus: Restore puts back geometry, and keeps the pin as it is now. */
const before = pinnedA
const entry = entryOf(before)
const during = setPinned(before, idOf(before, 'live:r:chart'), true)
const restored = restoreArr(during, entry)
eq(restored.focus!.floats!.find((f) => f.zone.slot?.items[0] === 'live:r:chart')!.pinned, true, 'pinned during Focus, it stays pinned after Restore')
eq(restored.focus!.floats!.find((f) => f.zone.slot?.items[0] === 'post:42')!.pinned, true, 'a window pinned before Focus is still pinned')
eq(restoreArr(before, entryOf(before)), before, 'Restore with nothing changed is no change')

console.log(`fluid pin: ${checks} checks passed`)
