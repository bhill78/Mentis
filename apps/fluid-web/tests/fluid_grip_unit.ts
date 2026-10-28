/* An object dragged out of its post (conversation/Grip.tsx), held in Node
   against the store (no server, no browser):

     * `fromOf` says where it came from: the conversation and the post's #;
     * `addressOf` finds the live address of the post's object under a block
       key, once its objects are read, and nothing before;
     * `dragObject` carries the workspace's own payload (keep.tsx `DRAG`):
       the address and where it came from, as flick.ts carries a card.

   Run by tests/run.mjs. */
import assert from 'node:assert/strict'
import { store, type Post } from '../src/fluid/store'
import { DRAG } from '../src/fluid/workspace/keep'
import { addressOf, dragObject, fromOf } from '../src/fluid/conversation/Grip'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }

const post = { id: 'p1', home: 'c1', home_name: 'Tidewater survey', number: 12, parts: [] } as unknown as Post
eq(fromOf(post), 'Tidewater survey · #12', 'from: the conversation and the post')
eq(fromOf({ ...post, home_name: null, home: null } as unknown as Post), '#12', 'from: the post alone where its home is not known')

const key = 'Turn p1/chart#0'
eq(addressOf('p1', key), null, 'nothing before the post\'s objects are read')
const live = 'mentis:obj/p1/chart#0'
;(store.postObjects as Map<string, unknown>).set('p1', { addresses: [live] })
;(store.objects as Map<string, unknown>).set(live, { object: { key, address: { live, exact: live + '@v1' } } })
eq(addressOf('p1', key), live, 'the post\'s object of that key, by its live address')
eq(addressOf('p1', 'Turn p1/table#0'), null, 'another key is not it')

const data = new Map<string, string>()
let allowed = ''
let stopped = false
const e = {
  stopPropagation: () => { stopped = true },
  dataTransfer: { setData: (t: string, v: string) => { data.set(t, v) }, set effectAllowed(v: string) { allowed = v }, setDragImage: () => {} },
} as unknown as React.DragEvent
dragObject(e, { address: live, from: fromOf(post) })
eq(JSON.parse(data.get(DRAG)!), { address: live, from: 'Tidewater survey · #12' }, 'the drag carries the address and where it came from')
eq(data.get('text/plain'), live, 'and the address as text')
eq(allowed, 'copyMove', 'kept or moved, as a card')
eq(stopped, true, 'the post\'s own drag (its head) does not start too')

console.log(`fluid grip: ${checks} checks passed`)
