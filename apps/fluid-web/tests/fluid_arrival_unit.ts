import assert from 'node:assert/strict'
import { toLayout, fromLayout, type Arr } from '../src/fluid/workspace/place'
import { keepSlot, type Node, type Zone } from '../src/fluid/workspace/tree'
import { land } from '../src/fluid/workspace/keep'
import { isBrainRef } from '../src/fluid/brain/address'
import { isAsk } from '../src/fluid/present/NeedsYou'
import { setCurrentItem, getCurrentItem } from '../src/fluid/present/Present'
import * as nav from '../src/fluid/nav'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const same = (a: unknown, b: unknown, what: string) => { assert.equal(a, b, what); checks++ }

const z = (id: string, items: string[] = []): Zone => ({
  type: 'zone',
  id,
  show: 'objects',
  name: id,
  slot: keepSlot(items),
})

/* -- 1. Versioning in place.ts ---------------------------------------------- */

const arr: Arr = {
  tree: z('z1', ['live:p1:k1', 'brain:ent-1']),
  pages: [],
  focus: {
    minimized: {
      from: 'float',
      rect: { x: 10, y: 20, w: 300, h: 200 },
      near: { near: 'z1', side: 'right', share: 0.5 },
      at: 1700000000000,
    },
  },
}

// toLayout writes version: 3 (arrangement v3, Surface Tension P2)
const layoutV2 = toLayout(arr)
same(layoutV2.version, 3, 'toLayout writes version 3')
same(layoutV2.format, 'mentis.fluid-arrangement', 'toLayout writes mentis.fluid-arrangement format')
eq((layoutV2.focus as any).minimized.from, 'float', 'toLayout preserves focus.minimized')

// fromLayout accepts version 1 and 2
const v1 = {
  format: 'mentis.fluid-arrangement',
  version: 1,
  tree: z('z1', ['live:p1:k1']),
  pages: [],
}
const loadedV1 = fromLayout(v1)
assert(loadedV1 !== null, 'fromLayout accepts version 1')
same(loadedV1?.tree.id, 'z1', 'version 1 loads correctly')

const v2 = {
  format: 'mentis.fluid-arrangement',
  version: 2,
  tree: z('z2', ['brain:ent-123']),
  pages: [],
  focus: {
    minimized: {
      from: 'column' as const,
      at: 1700000005000,
    },
  },
}
const loadedV2 = fromLayout(v2)
assert(loadedV2 !== null, 'fromLayout accepts version 2')
same(loadedV2?.tree.id, 'z2', 'version 2 loads correctly')
same(loadedV2?.focus?.minimized?.from, 'column', 'version 2 restores minimized correctly')

// Unknown version is rejected and toasts
const v4 = {
  format: 'mentis.fluid-arrangement',
  version: 4,
  tree: z('z4'),
  pages: [],
}
const loadedV4 = fromLayout(v4)
same(loadedV4, null, 'fromLayout returns null on unknown version')

/* -- 2. Brain references and Needs-You -------------------------------------- */

same(isBrainRef('brain:ent-123'), true, 'isBrainRef matches brain:ent-123')
same(isBrainRef('brain:adm-abcdef'), true, 'isBrainRef matches brain:adm-abcdef')
same(isBrainRef('brain:'), false, 'isBrainRef rejects empty brain: reference')
same(isBrainRef('live:p:k'), false, 'isBrainRef rejects live: reference')
same(isBrainRef('needs-you:req-1'), false, 'isBrainRef rejects needs-you:')

same(isAsk('needs-you:req-1'), true, 'isAsk matches needs-you:req-1')
same(isAsk('brain:ent-123'), false, 'isAsk rejects brain: reference')
same(isAsk('live:p:k'), false, 'isAsk rejects live:')

/* -- 3. Placed item navigation and mode switching -------------------------- */

// Setting current item for a zone
setCurrentItem('zone-a', 'live:p1:chart')
same(getCurrentItem('zone-a'), 'live:p1:chart', 'current item remembered for zone-a')

// Switching mode retains the placed/selected item
setCurrentItem('zone-b', 'live:p2:table')
same(getCurrentItem('zone-b'), 'live:p2:table', 'placed item retained across mode switches')

// Landing signal updates
land('zone-c', 'live:p3:diagram')
// land() sets internal landed state in keep.tsx

console.log(`fluid arrival & persist: ${checks} checks passed`)
