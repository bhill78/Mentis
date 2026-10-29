import assert from 'node:assert/strict'

/* The conversation minimized to its launcher, and restored: from the column, a
 * leaf and a float; restored where it was or as the launcher's menu says; per
 * page; one Undo step; saved and read back with the page's focus; and the 3D
 * Brain's own put-away. Presentation only: nothing else on the page moves. */
const mem = new Map<string, string>()
;(globalThis as any).sessionStorage = {
  getItem: (k: string) => mem.get(k) ?? null,
  setItem: (k: string, v: string) => { mem.set(k, v) },
  removeItem: (k: string) => { mem.delete(k) },
}
;(globalThis as any).fetch = async () => { throw new Error('offline in a unit test') }

const { columnEmpty, columnZone, locate, makePrimary, minimize, minimizedOf, primaryOf, readMinimized, restore, setAllMinimized, unreadSince } = await import('../src/fluid/focus/model')
const { CONVERSATION_ID } = await import('../src/fluid/focus/types')
const { allPageViews, onPage, pageView, THIS_POST } = await import('../src/fluid/focus/page')
const { Holder, fromLayout, toLayout } = await import('../src/fluid/workspace/place')
const { keepSlot, zones } = await import('../src/fluid/workspace/tree')
const { minimise, openOver, readOverlays, restoreOver, CONVERSATION_OVERLAY } = await import('../src/fluid/brain/overlays')

type Arr = import('../src/fluid/workspace/place').Arr
type Node = import('../src/fluid/workspace/tree').Node
type Zone = import('../src/fluid/workspace/tree').Zone

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }
const near = (a: number, b: number) => Math.abs(a - b) < 1e-9
const z = (id: string): Zone => ({ type: 'zone', id, show: 'objects', name: id, slot: keepSlot() })
const conv = (): Zone => ({ type: 'zone', id: CONVERSATION_ID, show: 'conversation', name: 'Conversation' })
const arr = (tree: Node, focus?: Arr['focus'], pages: Arr['pages'] = []): Arr => ({ tree, pages, ...(focus ? { focus } : {}) })
const T = 1_700_000_000_000

/* Every ordinary float uses the same persisted `min` flag. Bulk actions keep
   array order and leave pinned windows byte-for-byte alone. */
const bulk = arr(z('base'), { floats: [
  { id: 'one', zone: z('One'), x: 1, y: 2, w: 300, h: 200 },
  { id: 'pinned', zone: z('Pinned'), x: 3, y: 4, w: 300, h: 200, pinned: true, min: true },
  { id: 'three', zone: z('Three'), x: 5, y: 6, w: 300, h: 200, min: true },
] })
const bulkMin = setAllMinimized(bulk, true)
eq(bulkMin.focus!.floats!.map((f) => [f.id, !!f.min]), [['one', true], ['pinned', true], ['three', true]], 'minimise all keeps float order and minimises ordinary windows')
eq(bulkMin.focus!.floats![1], bulk.focus!.floats![1], 'minimise all leaves a pinned float unchanged')
eq(setAllMinimized(bulkMin, true), bulkMin, 'minimise all is idempotent')
const bulkBack = setAllMinimized(bulkMin, false)
eq(bulkBack.focus!.floats!.map((f) => [f.id, !!f.min]), [['one', false], ['pinned', true], ['three', false]], 'restore all restores ordinary windows and still exempts pinned')
eq((toLayout(bulkMin) as any).focus.floats.map((f: any) => [f.id, f.min]), [['one', true], ['three', true]], 'the existing layout save persists each unpinned minimized tab in order')

/* 1. FROM THE COLUMN: the column empties, the tree is untouched; restored, the
   arrangement is exactly what it was. */
const pair: Node = { type: 'split', dir: 'row', sizes: [.4, .6], kids: [z('a'), z('b')] }
const col = arr(pair, { floats: [{ id: 'fl-1', zone: z('f'), x: 1, y: 2, w: 300, h: 200 }] })
const colMin = minimize(col, T)
eq(minimizedOf(colMin), { from: 'column', at: T }, 'minimized from the column, at its time')
eq(locate(colMin, CONVERSATION_ID), null, 'the conversation is in no place')
ok(columnEmpty(colMin), 'the column place is empty, so it is drawn at no width')
eq(colMin.tree, pair, 'the sections are untouched')
eq(colMin.focus!.floats, col.focus!.floats, 'the floats are untouched')
eq(minimize(colMin, T + 5), colMin, 'minimizing twice changes nothing')
eq(restore(colMin), col, 'restored: back in the column, minimized cleared, nothing else changed')

/* 2. FROM A LEAF: its share goes to one neighbour; restored, it goes back
   beside that neighbour on its side at its share, and nobody else's share moved. */
const three: Node = { type: 'split', dir: 'row', sizes: [.2, .3, .5], kids: [z('a'), conv(), z('b')] }
const leaf = arr(three, { column: z('held') })
const leafMin = minimize(leaf, T)
eq(minimizedOf(leafMin)?.from, 'leaf', 'minimized from a leaf')
eq(minimizedOf(leafMin)?.near?.near, 'a', 'the neighbour that took its share is kept')
eq(zones(leafMin.tree).map((x) => x.id), ['a', 'b'], 'its leaf is gone from the tree')
eq(columnZone(leafMin).id, 'held', 'what the column holds stays in the column')
ok(!columnEmpty(leafMin), 'a column holding something is not empty')
const leafBack = restore(leafMin)
eq(zones(leafBack.tree).map((x) => x.id), ['a', CONVERSATION_ID, 'b'], 'restored on its side of the neighbour')
ok(((leafBack.tree as any).sizes as number[]).every((s, i) => near(s, [.2, .3, .5][i])), 'every share is as it was')
eq(minimizedOf(leafBack), null, 'minimized is cleared')
eq(leafBack.focus, leaf.focus, 'the column is untouched')
const pairConv = arr({ type: 'split', dir: 'row', sizes: [.3, .7], kids: [z('a'), conv()] }, { column: z('held') })
const pairBack = restore(minimize(pairConv, T))
eq(zones(pairBack.tree).map((x) => x.id), ['a', CONVERSATION_ID], 'a two-leaf page restores its side')
ok(near((pairBack.tree as any).sizes[0], .3) && near((pairBack.tree as any).sizes[1], .7), 'and its exact shares')
const only = minimize(arr(conv(), { column: z('held') }), T)
eq(zones(only.tree).length, 1, 'the only section gives way to a fresh one: a page keeps one section')
ok(zones(only.tree)[0].id !== CONVERSATION_ID && zones(only.tree)[0].slot?.follow, 'which follows what is read')

/* 3. FROM A FLOAT: its rectangle is kept and given back exactly. */
const rect = { x: 50, y: 60, w: 420, h: 500 }
const fl = arr(pair, { column: z('held'), floats: [{ id: 'fl-c', zone: conv(), ...rect }, { id: 'fl-o', zone: z('o'), x: 0, y: 0, w: 240, h: 160 }] })
const flMin = minimize(fl, T)
eq(minimizedOf(flMin), { from: 'float', rect, at: T }, 'minimized from a float with its rect')
eq(flMin.focus!.floats!.map((f) => f.id), ['fl-o'], 'only the conversation float leaves')
const flBack = restore(flMin)
const back = flBack.focus!.floats!.find((f) => f.zone.id === CONVERSATION_ID)!
eq({ x: back.x, y: back.y, w: back.w, h: back.h }, rect, 'restored at its own rect')
eq(flBack.focus!.floats![0].id, 'fl-o', 'the other float is untouched')
eq(flBack.tree, pair, 'the tree is untouched')

/* 4. THE LAUNCHER'S MENU: as a float, the column, or a section beside the primary. */
const room = { w: 1000, h: 700 }
const asFloat = restore(colMin, 'float', room)
eq(locate(asFloat, CONVERSATION_ID)?.place, 'float', 'from the column, restored as a floating window')
ok(columnEmpty(asFloat), 'and the column stays empty: no page needs a reserved column')
eq(asFloat.tree, pair, 'nothing in the tree moved')
const f0 = asFloat.focus!.floats!.find((f) => f.zone.id === CONVERSATION_ID)!
ok(f0.x >= 0 && f0.y >= 0 && f0.x + f0.w <= room.w && f0.y + f0.h <= room.h, 'its new float is inside the room')
eq(restore(minimize(asFloat, T + 1)).focus!.floats!.find((f) => f.zone.id === CONVERSATION_ID)!.x, f0.x, 'minimized again, it goes back to the float')
const asLeaf = restore(minimize(makePrimary(arr(pair), 'b'), T), 'leaf')
eq(locate(asLeaf, CONVERSATION_ID)?.place, 'leaf', 'put in a section')
ok(zones(asLeaf.tree).some((x) => x.id === CONVERSATION_ID), 'the section is a leaf of the tree')
const primaryLeaf = (() => { const m = makePrimary(arr(pair), 'b'); return locate(m, primaryOf(m)) })()
ok(primaryLeaf?.place === 'column', 'make-primary of a leaf swaps it into the column (precondition)')
const besidePrimary = restore(minimize(arr(pair, { primary: 'b' }), T), 'leaf')
eq(zones(besidePrimary.tree).map((x) => x.id), ['a', 'b', CONVERSATION_ID], 'beside the primary section, at its right')
eq((besidePrimary.tree as any).sizes[0], .4, 'the sections not beside it keep their share')
const asColumn = restore(flMin, 'column', room)
eq(locate(asColumn, CONVERSATION_ID)?.place, 'column', 'docked as the column')
eq(asColumn.focus!.floats!.map((f) => f.zone.id), ['o', 'held'], 'what the column held floats, never lost')
eq(asColumn.tree, pair, 'and the tree is untouched')

/* 5. PAGES: each page minimizes on its own; the others keep their arrangement. */
const paged = arr(pair, undefined, [{ id: 'p2', title: 'Two', tree: z('two') }, { id: 'p3', title: 'Three', tree: z('three'), focus: { column: z('c3'), floats: [{ id: 'fl-3', zone: conv(), ...rect }] } }])
const p2Min = onPage((v) => minimize(v, T), 'p2')(paged)
eq(minimizedOf(pageView(p2Min, 'p2'))?.from, 'column', 'page two is minimized')
eq(minimizedOf(p2Min), null, 'This post is not')
eq(p2Min.pages[1], paged.pages[1], 'page three is untouched')
eq(p2Min.tree, paged.tree, 'This post is untouched')
const p3Min = onPage((v) => minimize(v, T + 1), 'p3')(p2Min)
eq(minimizedOf(pageView(p3Min, 'p3'))?.from, 'float', 'page three minimized its float')
eq(allPageViews(p3Min).map(({ view }) => minimizedOf(view)?.from ?? null), [null, 'column', 'float'], 'every page keeps its own')
const p2Back = onPage((v) => restore(v), 'p2')(p3Min)
eq(p2Back.pages[0], paged.pages[0], 'page two restored as it was')
eq(minimizedOf(pageView(p2Back, 'p3'))?.from, 'float', 'page three still minimized')
eq(onPage((v) => minimize(v, T), THIS_POST)(paged).pages, paged.pages, 'minimizing This post leaves the pages alone')

/* 6. SAVED AND READ BACK in the contract's shape, top-level and per page. */
const saved = toLayout(p3Min) as any
eq(saved.pages[0].focus.minimized, { from: 'column', at: T }, 'a page saves its minimized')
eq(saved.pages[1].focus.minimized, { from: 'float', rect, at: T + 1 }, 'with its rect')
const read = fromLayout(JSON.parse(JSON.stringify(saved)))!
eq(minimizedOf(pageView(read, 'p2')), { from: 'column', at: T }, 'read back on page two')
eq(minimizedOf(pageView(read, 'p3')), { from: 'float', rect, at: T + 1 }, 'read back on page three')
const leafSaved = fromLayout(JSON.parse(JSON.stringify(toLayout(leafMin))))!
eq(minimizedOf(leafSaved), minimizedOf(leafMin), 'a leaf origin round-trips with its neighbour')
eq(fromLayout(toLayout(col))!.focus?.minimized, undefined, 'a layout never minimized has none')
eq(readMinimized({ from: 'column', at: T }, three), undefined, 'a saved minimized is dropped where the conversation is in a leaf anyway')
eq(readMinimized({ from: 'nowhere', at: T }, pair), undefined, 'an unknown origin is dropped')
eq(readMinimized({ from: 'float', at: T, rect: { x: 'x' } }, pair), { from: 'float', at: T }, 'an unreadable rect is left out, never guessed')

/* 7. ONE UNDO STEP. */
const h = new Holder(() => arr(pair))
h.enter('place-min', 'conversation')
h.edit(onPage((v) => minimize(v, T), THIS_POST))
eq(minimizedOf(h.arr)?.from, 'column', 'minimized through the workspace')
ok(h.canUndo(), 'it is a step')
h.undo()
eq(minimizedOf(h.arr), null, 'Undo brings the conversation back')
eq(locate(h.arr, CONVERSATION_ID)?.place, 'column', 'into the column')

/* 8. UNREAD: posts after the moment it was put away, not deleted ones. */
eq(unreadSince([{ at: T / 1000 - 1 }, { at: T / 1000 + 1 }, { at: T / 1000 + 2, deleted: { at: 1 } }, { at: T / 1000 + 3, deleted: null }], T), 2, 'only newer, live posts count')

/* 9. OVER THE 3D BRAIN: put away records when; restored where it was, as a float or docked. */
let over = openOver([], { type: 'conversation', conversation: 'c1', title: 'Survey' }, { w: 1000, h: 700 })
over = minimise(over, CONVERSATION_OVERLAY, true, T)
eq(over[0].min && over[0].at, T, 'put away, with its time')
eq(minimise(over, CONVERSATION_OVERLAY, true, T + 9)[0].at, T, 'put away again keeps the first time')
eq(readOverlays(JSON.stringify(over))[0].at, T, 'kept for the tab')
const dockedBack = restoreOver(over, CONVERSATION_OVERLAY, 'left')
eq([dockedBack[0].min, dockedBack[0].dock, dockedBack[0].at], [false, 'left', undefined], 'docked at the left, unread cleared')
const floatBack = restoreOver(minimise(dockedBack, CONVERSATION_OVERLAY, true, T), CONVERSATION_OVERLAY, 'float')
eq([floatBack[0].min, floatBack[0].dock], [false, undefined], 'as a float again')
eq(restoreOver(minimise(dockedBack, CONVERSATION_OVERLAY, true, T), CONVERSATION_OVERLAY)[0].dock, 'left', 'restored where it was: docked')

console.log(`fluid minimize: ${checks} checks passed`)
