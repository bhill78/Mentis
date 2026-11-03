import assert from 'node:assert/strict'

const mem = new Map<string, string>()
;(globalThis as any).sessionStorage = {
  getItem: (k: string) => mem.get(k) ?? null,
  setItem: (k: string, v: string) => { mem.set(k, v) },
  removeItem: (k: string) => { mem.delete(k) },
}
;(globalThis as any).fetch = async () => { throw new Error('offline in a unit test') }

const { Holder, applyDisplacements, toLayout } = await import('../src/fluid/workspace/place')
type Arr = import('../src/fluid/workspace/place').Arr
type Zone = import('../src/fluid/workspace/tree').Zone

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const z = (id: string): Zone => ({ type: 'zone', id, show: 'objects' })
const start = (): Arr => ({
  tree: z('dock'), pages: [], focus: { floats: [
    { id: 'fa', zone: z('a'), x: 10, y: 20, w: 100, h: 80 },
    { id: 'fb', zone: z('b'), x: 200, y: 50, w: 120, h: 90 },
  ] },
})

const h = new Holder(start)
const original = JSON.stringify(h.arr)
const layout = JSON.stringify(toLayout(h.arr, { tab: true }))

h.displace(new Map())
eq(JSON.stringify(h.arr), original, 'Make room Off is byte-identical')
eq(h.canUndo(), false, 'Off adds no undo step')

h.displace(new Map([['a', { dx: 30, dy: -10 }], ['b', { dx: -20, dy: 40, w: 80, h: 70 }]]))
eq(JSON.stringify(h.arr), original, 'preview does not change arrangement geometry')
eq(JSON.stringify(toLayout(h.arr, { tab: true })), layout, 'toLayout never contains displacements')
eq(h.displacementSnapshot().size, 2, 'preview holds both transient displacements')
h.clearDisplacements()
eq(JSON.stringify(h.arr), original, 'cancel returns every rectangle')
eq(h.canUndo(), false, 'cancel adds no undo entry')

h.displace(new Map([['a', { dx: 30, dy: -10 }], ['b', { dx: -20, dy: 40, w: 80, h: 70 }]]))
h.commitDisplacements('Made room for Incoming')
eq(h.arr.focus?.floats?.map((f: any) => [f.zone.id, f.x, f.y, f.w, f.h]),
  [['a', 40, 10, 100, 80], ['b', 180, 90, 80, 70]], 'commit applies every delta together')
eq(h.displacementSnapshot().size, 0, 'commit clears the transient layer')
eq(h.canUndo(), true, 'commit creates exactly one undo step')
h.undo()
eq(JSON.stringify(h.arr), original, 'one Undo restores every rectangle together')
eq(h.canUndo(), false, 'the one undo step was consumed')

const folded = applyDisplacements(start(), new Map([['a', { dx: 0, dy: 0, fold: true }]]))
eq(folded.focus?.floats?.[0].min, true, 'fold commits as the existing minimized representation')
eq(start().focus?.floats?.[0].min, undefined, 'pure application does not mutate its input')

console.log(`fluid displacement: ${checks} checks`)
