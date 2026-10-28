import assert from 'node:assert/strict'

/* A reply thread is a surface like the others (owner feedback, round 2): it
   opens in a window beside the conversation and clear of other windows, is
   docked, made primary, pinned, minimised and followed like any window, and
   the pinned threads of a saved arrangement read as thread windows. */
const mem = new Map<string, string>()
;(globalThis as any).sessionStorage = {
  getItem: (k: string) => mem.get(k) ?? null,
  setItem: (k: string, v: string) => { mem.set(k, v) },
  removeItem: (k: string) => { mem.delete(k) },
}
;(globalThis as any).fetch = async () => { throw new Error('offline in a unit test') }

const M = await import('../src/fluid/focus/model')
const { fromLayout, toLayout, layoutPage } = await import('../src/fluid/workspace/place')
const { keepSlot, zones } = await import('../src/fluid/workspace/tree')
const { MAX_FLOATS } = await import('../src/fluid/focus/types')
const { gatherTravel } = await import('../src/fluid/focus/travel')
const { pageView } = await import('../src/fluid/focus/page')

type Arr = import('../src/fluid/workspace/place').Arr
type Zone = import('../src/fluid/workspace/tree').Zone
type Node = import('../src/fluid/workspace/tree').Node

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }

const z = (id: string): Zone => ({ type: 'zone', id, show: 'objects', name: id, slot: keepSlot() })
const arr = (tree: Node, extra: Partial<Arr> = {}): Arr => ({ tree, pages: [], ...extra })
const two = (): Arr => arr({ type: 'split', dir: 'row', sizes: [.5, .5], kids: [z('s1'), z('s2')] }, { pages: [{ id: 'p2', title: 'Page 2', tree: z('p2-tree') }] })
const R = { x: 470, y: 24, w: 420, h: 560 }
const roots = (a: Arr) => M.threadsOf(a).map((t) => M.threadRootOf(t.zone))

/* 1. A thread in a window: what it shows is its root, by reference. */
let a = M.floatThread(two(), 'p12', R, 'conv-a', 12)
const t0 = a.focus!.floats![0]
eq(t0.zone.show, M.THREAD_SHOW, 'the window shows a thread')
eq(t0.zone.options, { root: 'p12', conversation: 'conv-a' }, 'its root and the conversation it is replied in')
eq(t0.zone.name, 'Thread #12', 'named by its post until the post is read')
eq([t0.x, t0.y, t0.w, t0.h], [R.x, R.y, R.w, R.h], 'at the rectangle asked for')
ok(!t0.zone.slot, 'no slot: nothing is copied into it')
ok(M.isThreadZone(t0.zone) && M.isContentZone(t0.zone) && !M.isObjectZone(t0.zone), 'a content window, not an object one')
eq(M.threadOf(a, 'p12')?.place, 'float', 'found where it is')
eq(M.threadOf(a, 'p99'), null, 'and only there')
let full = two()
for (let i = 0; i < MAX_FLOATS; i++) full = M.floatThread(full, 'r' + i, R)
eq(M.floatThread(full, 'one-more', R), full, 'never past MAX_FLOATS: the caller falls back to the sheet')

/* 2. Follow: one window follows the post read; it moves to the post read. */
a = M.floatThread(a, 'p20', { ...R, x: 20 }, 'conv-a', 20, true)
eq(M.followerOf(a) && M.threadRootOf(M.followerOf(a)!.zone), 'p20', 'the window opened by Follow follows')
const p12 = M.threadOf(a, 'p12')!.zone.id
const marked = M.markFollower(a, p12)
eq(M.threadRootOf(M.followerOf(marked)!.zone), 'p12', 'Follow from a window: it follows now')
eq(M.threadsOf(marked).filter((t) => t.zone.options?.follow).length, 1, 'only one follows')
eq(M.followerOf(M.markFollower(marked, null)), null, 'Follow off: none follows')
eq(M.markFollower(marked, p12), marked, 'marking it again changes nothing')
const moved = M.setThreadRoot(marked, p12, 'p30', 30)
eq(M.threadRootOf(M.threadOf(moved, 'p30')!.zone), 'p30', 'the follower now shows the post read')
eq(M.threadOf(moved, 'p30')!.zone.name, 'Thread #30', 'and says so')
eq(M.threadOf(moved, 'p30')!.zone.options?.conversation, 'conv-a', 'still replied in its conversation')
eq(M.threadOf(moved, 'p30')!.float!.x, R.x, 'it does not move: its rectangle is the owner\'s')
eq(M.setThreadRoot(moved, p12, 'p30', 30), moved, 'the same root: no change')

/* 3. Where a thread window opens: beside the conversation, clear of other windows. */
const room = { w: 1600, h: 900 }
const conv = { x: 0, y: 0, w: 440, h: 900 }
const r1 = M.threadWindowRect(room, conv)
eq(r1.x, conv.w + 12, 'beside the conversation')
ok(r1.w <= 440 && r1.w >= 220 && r1.h <= 720 && r1.y + r1.h <= room.h, 'a useful size, inside the room, never a fixed third')
const r2 = M.threadWindowRect(room, conv, [r1])
ok(r2.x >= r1.x + r1.w, 'a second one opens where nothing covers it')
ok(r2.x + r2.w <= room.w - 12, 'still inside the room')
const r3 = M.threadWindowRect(room, null)
eq(r3.x + r3.w, room.w - 12, 'with no conversation drawn, at the right of the room')
const wall = [{ x: 0, y: 0, w: room.w, h: room.h }]
const r4 = M.threadWindowRect(room, conv, wall)
ok(r4.x >= 12 && r4.w >= 220 && r4.h >= 120, 'covered everywhere, it still opens, a whole window')
const stacked = M.threadWindowRect(room, conv, [{ ...r1 }])
ok(stacked.x !== r1.x || stacked.y !== r1.y, 'never exactly over another window')
const small = M.threadWindowRect({ w: 700, h: 500 }, { x: 0, y: 0, w: 440, h: 500 })
ok(small.x + small.w <= 700 - 12 && small.x >= 12, 'on a small room it fits, overlapping the conversation if it must')

/* 4. Minimised: its title line, where it is; open again where it was. */
const fid = M.threadOf(a, 'p12')!.float!.id
const minA = M.setMinimized(a, fid, true)
eq(minA.focus!.floats!.find((f) => f.id === fid)!.min, true, 'minimised')
eq(M.setMinimized(minA, fid, true), minA, 'twice: no change')
const back = M.setMinimized(minA, fid, false)
ok(!('min' in back.focus!.floats!.find((f) => f.id === fid)!), 'restored: the flag is gone')
eq(back.focus!.floats!.find((f) => f.id === fid)!.x, R.x, 'and it is where it was')

/* 5. Docked, primary, pinned: what any window can be. */
const docked = M.dockFloat(a, fid, 's2', 'right')
ok(zones(docked.tree).some((x) => M.threadRootOf(x) === 'p12'), 'docked: a section of the page')
eq(M.threadOf(docked, 'p12')?.place, 'leaf', 'found there')
const primary = M.makePrimary(a, M.threadOf(a, 'p12')!.zone.id)
eq(M.primaryOf(primary), M.threadOf(a, 'p12')!.zone.id, 'made primary')
eq(M.threadOf(primary, 'p12')?.place, 'column', 'it took the primary place; the conversation floats where it was')
ok(M.canPin(t0.zone), 'a thread window can be pinned')
const pinned = M.setPinned(a, fid, true)
eq(M.travelKey(pinned.focus!.floats!.find((f) => f.id === fid)!), 't:p12', 'carried once per thread')
const toP2 = gatherTravel(pinned, 'p2')
eq(roots(pageView(toP2, 'p2')), ['p12'], 'pinned, it goes with the owner to Page 2')
const elsewhere = M.carryPinnedFloats(arr(z('b1')), pinned)
eq(M.threadOf(elsewhere, 'p12')!.zone.options?.conversation, 'conv-a', 'to another conversation, still replying in its own')

/* 6. Its look is its own, kept flat in its options. */
const looked = M.setThreadLook(a, M.threadOf(a, 'p12')!.zone.id, { panel: 'solid', content: 'tinted', opacity: 0.8 })
eq(M.lookOf(M.threadOf(looked, 'p12')!.zone), { panel: 'solid', content: 'tinted', opacity: 0.8 }, 'a look of its own')
eq(M.lookOf(M.threadOf(M.setThreadLook(looked, M.threadOf(a, 'p12')!.zone.id, undefined), 'p12')!.zone), undefined, 'back to the place\'s')
eq(M.threadOf(looked, 'p12')!.zone.options?.root, 'p12', 'nothing else of it changed')

/* 7. Saved arrangements: pinned threads read as thread windows, and are saved back the same way. */
const saved = { format: 'mentis.fluid-arrangement', version: 2, tree: z('s1'), threads: { pinned: ['p1', 'p2'], active: 'p2' } }
const read = fromLayout(saved)!
eq(read.threads, undefined, 'no tabs any more')
eq(roots(read), ['p1', 'p2'], 'each pinned thread is a window on This post, in their order')
const [w1, w2] = read.focus!.floats!
ok(w2.x > w1.x && w2.y > w1.y, 'cascading, so neither hides the other')
const out = toLayout(read) as { threads?: { pinned: string[] }; focus?: unknown }
eq(out.threads?.pinned, ['p1', 'p2'], 'Save keeps them as every build reads them')
eq(out.focus, undefined, 'and no window of them in the saved shape')
eq(JSON.stringify(toLayout(fromLayout(out)!)), JSON.stringify(out), 'read and saved again: the same')
const tab = toLayout(read, { tab: true }) as { threads?: unknown; focus?: { floats?: unknown[] } }
eq(tab.threads, undefined, 'this tab\'s copy keeps the windows themselves')
eq(tab.focus!.floats!.length, 2, 'where they are')
eq(roots(fromLayout(tab)!), ['p1', 'p2'], 'and reads them back without opening them twice')
const dockedSave = { ...saved, tree: { type: 'zone', id: 'tz', show: 'thread', name: 'Thread #1', options: { root: 'p1' } } }
eq(roots(fromLayout(dockedSave)!), ['p1', 'p2'], 'a thread already docked is not opened again in a window')
const minSaved = fromLayout(toLayout(M.setMinimized(read, w1.id, true), { tab: true }))!
eq(minSaved.focus!.floats!.find((f) => M.threadRootOf(f.zone) === 'p1')!.min, true, 'minimised, it reads back minimised')

/* 8. A layout applied leaves the thread windows where they are. */
const shaped = layoutPage(read, arr({ type: 'split', dir: 'row', sizes: [.5, .5], kids: [z('x1'), z('x2')] }))
eq(roots(shaped), ['p1', 'p2'], 'a layout is a shape: the threads stay open')
ok(!(shaped.setAside ?? []).some((x) => M.isThreadZone(x)), 'and none is set aside')

console.log(`fluid thread window: ${checks} checks passed`)
