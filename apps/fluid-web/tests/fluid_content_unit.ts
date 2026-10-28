import assert from 'node:assert/strict'

/* Fluid Focus, second round, A: a post's words taken out by their live
   address, and object floats that go with the owner from place to place. */
const mem = new Map<string, string>()
;(globalThis as any).sessionStorage = { getItem: (k: string) => mem.get(k) ?? null, setItem: (k: string, v: string) => { mem.set(k, v) }, removeItem: (k: string) => { mem.delete(k) } }
;(globalThis as any).fetch = async () => { throw new Error('offline in a unit test') }

const { objectsOfPost } = await import('../src/experimental/postobjects')
const { store } = await import('../src/fluid/store')
const { textObjectsOf } = await import('../src/fluid/conversation/Grip')
const { carryPinnedFloats, closeFloat, floatObject, floatOut, floatRun, objectFloatsOf, pinnedFloatsOf, setPinned } = await import('../src/fluid/focus/model')
const { Holder, fromLayout, toLayout } = await import('../src/fluid/workspace/place')
const { keepSlot } = await import('../src/fluid/workspace/tree')
type Arr = import('../src/fluid/workspace/place').Arr
type Zone = import('../src/fluid/workspace/tree').Zone
type Node = import('../src/fluid/workspace/tree').Node

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }
const z = (id: string): Zone => ({ type: 'zone', id, show: 'objects', name: id, slot: keepSlot() })
const arr = (tree: Node, extra: Partial<Arr> = {}): Arr => ({ tree, pages: [], ...extra })

/* 1. A post's words already have live addresses: one post-text object per run. */
const text = 'First words of the post.\n\n```chart version=1 title="Sales"\nmonth,n\njan,1\n```\n\nSecond run of words.'
const post = { id: 'p1', parts: [{ type: 'text', text }] }
const objs = objectsOfPost(post as any)
const texts = objs.filter((o) => o.kind === 'post-text')
eq(texts.length, 2, 'two runs of text around the chart, each an object')
const addr = (k: string) => `live:p1:${k}`
for (const o of objs) (store.objects as Map<string, unknown>).set(addr(o.key), { address: addr(o.key), object: { ...o, post: 'p1', version: 'v1', address: { exact: `exact:v1:${o.part}:${o.key}`, live: addr(o.key) } } })
store.postObjects.set('p1', { post: 'p1', version: 'v1', addresses: objs.map((o) => addr(o.key)), extracted: true } as any)
;(store.posts as Map<string, unknown>).set('p1', { id: 'p1', parts: post.parts, home: 'c1', number: 3 })
const got = textObjectsOf('p1')
eq(got.map((t) => t.address), texts.map((o) => addr(o.key)), 'the grips carry the post-text objects\' live addresses, in reading order')
ok(got.every((t) => t.address.startsWith('live:p1:') && t.address.includes('/text#')), 'each address is live:<post>:<part scope>/text#<n>')
eq(got.map((t) => t.words), ['First words of the post.', 'Second run of words.'], 'each grip knows its own words, not the chart')
ok(!got.some((t) => t.address.includes('chart')), 'a block keeps its own grip; it is not text')

/* 2. Only pinned floats go with the owner; everything else stays with its place. */
const conv: Zone = { type: 'zone', id: 'conv', show: 'conversation', name: 'Conversation' }
let a: Arr = arr({ type: 'split', dir: 'row', sizes: [.5, .5], kids: [z('a1'), z('a2')] }, { conversation: { width: 420 }, threads: { pinned: ['p9'], active: null } })
a = floatOut(a, 'a2', { x: 1, y: 2, w: 300, h: 200 })
a = floatRun(a, 'run-1', 'Claude', { x: 5, y: 5, w: 300, h: 200 })
a = floatObject(a, got[0].address, 'Post text', { x: 40, y: 50, w: 320, h: 220 }, 'a1', 'Tidewater · #3')
a = setPinned(a, objectFloatsOf(a)[0].id, true)
a = { ...a, focus: { ...a.focus!, floats: [...a.focus!.floats!, { id: 'f-conv', zone: conv, x: 0, y: 0, w: 300, h: 300 }], previous: ['a1'] } }
const obj = objectFloatsOf(a)
eq(obj.length, 1, 'one object float among four')
const kept = toLayout(a) as { focus?: { floats?: { zone: Zone }[] } }
eq(kept.focus!.floats!.map((f) => f.zone.show), ['objects', 'run', 'conversation'], 'a place\'s layout keeps its section, run and conversation floats, never the travelling one')
const b0 = arr(z('b1'), { conversation: { width: 600 } })
const b = carryPinnedFloats(b0, a)
eq(b.tree, b0.tree, 'the place arrived at keeps its own tree')
eq(b.conversation, { width: 600 }, 'its own column width')
eq(b.threads, undefined, 'none of the left place\'s pins')
eq(b.focus!.previous, undefined, 'none of its focus history')
eq(b.focus!.primary, undefined, 'nor its primary')
eq(b.focus!.floats!.length, 1, 'only the object float came along')
const carried = b.focus!.floats![0]
eq([carried.id, carried.x, carried.y, carried.w, carried.h], [obj[0].id, 40, 50, 320, 220], 'same float, same rectangle')
eq(carried.zone.slot!.items, [got[0].address], 'the same live address: nothing copied')
eq(carried.zone.options, { says: 'Tidewater · #3' }, 'it still says where it came from; the left place\'s zone (from) does not come along')
eq(carryPinnedFloats(b, a), b, 'carried twice, it is there once')
eq((toLayout(b) as { focus?: unknown }).focus, undefined, 'a travelling float is no part of the place it is shown over: Save does not keep it')
let full: Arr = arr(z('c1'))
for (let i = 0; i < 12; i++) full = floatObject(full, `live:x:${i}`, 'X', { x: 0, y: 0, w: 220, h: 120 })
eq(carryPinnedFloats(full, a), full, 'never past MAX_FLOATS')

/* 3. Holder.enter: the float leaves the place left and is shown in the next; back again, it returns. */
const h = new Holder(() => arr(z('start')), { carry: { pick: pinnedFloatsOf, bring: carryPinnedFloats } })
h.enter('conv-a', 'conversation')
h.edit((x) => floatObject(x, got[1].address, 'Post text', { x: 10, y: 10, w: 320, h: 220 }, undefined, 'Tidewater · #3'))
h.edit((x) => setPinned(x, objectFloatsOf(x)[0].id, true))
eq(objectFloatsOf(h.arr).length, 1, 'floated in A')
h.enter('conv-b', 'conversation')
eq(objectFloatsOf(h.arr).map((f) => f.zone.slot!.items[0]), [got[1].address], 'still floating after opening B')
eq(objectFloatsOf(fromLayout(JSON.parse(mem.get('mentis.fluid.arr:conv-a')!))!).length, 0, 'A\'s layout never held it')
eq(mem.has('mentis.fluid.arr:conv-b') ? objectFloatsOf(fromLayout(JSON.parse(mem.get('mentis.fluid.arr:conv-b')!))!).length : 0, 0, 'nor does B\'s: it is not reassigned to the place shown')
eq(JSON.parse(mem.get('mentis.fluid.travel')!).length, 1, 'the workspace keeps it in this tab, so a reload keeps it')
eq(h.changed(), false, 'carrying it changes nothing the place keeps')
const reloaded = new Holder(() => arr(z('start')), { carry: { pick: pinnedFloatsOf, bring: carryPinnedFloats } })
reloaded.enter('conv-c', 'conversation')
eq(objectFloatsOf(reloaded.arr).length, 1, 'after a reload it is still floating')
h.enter('conv-a', 'conversation')
eq(objectFloatsOf(h.arr).length, 1, 'back in A, it is there once')
const fid = objectFloatsOf(h.arr)[0].id
h.edit((x) => closeFloat(x, fid))
h.enter('conv-b', 'conversation')
eq(objectFloatsOf(h.arr).length, 0, 'closed, it does not come back from another place')
const plain = new Holder(() => arr(z('s')))
plain.enter('one', 'conversation')
plain.edit((x) => floatObject(x, 'live:q:k', 'Q', { x: 0, y: 0, w: 220, h: 120 }))
plain.enter('two', 'conversation')
eq(objectFloatsOf(plain.arr).length, 0, 'a holder that carries nothing (Home) is as before')

console.log(`fluid content: ${checks} checks passed`)
