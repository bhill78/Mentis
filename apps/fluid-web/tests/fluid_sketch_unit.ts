/* Layout sketcher unit tests (Antigravity fq-sketch):
 *   - vertical stroke across 1200x800 page makes a row split near the stroke (snapped)
 *   - too-short stroke is rejected with a reason
 *   - stroke that would leave a side under minimum (MIN_W=240, MIN_H=140) is rejected
 *   - erase merges back
 *   - assign keeps every old zone either placed or leftover and preserves ids
 */

import assert from 'node:assert/strict'
import type { Node, Zone } from '../src/fluid/workspace/tree'
import { zone, zones } from '../src/fluid/workspace/tree'
import {
  sketchLayout,
  cut,
  erase,
  assign,
  type Line,
} from '../src/fluid/workspace/sketch'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (v: unknown, what: string) => { assert.ok(v, what); checks++ }

/* -- 1. A vertical stroke across an empty 1200x800 page makes a row split snapped near the stroke -- */

const page: Zone = { ...zone(null), id: 'stage', name: 'Stage' }
const W = 1200
const H = 800

// A vertical stroke at x ~ 605 across most of H (100 to 700)
const stroke1 = [
  { x: 605, y: 100 },
  { x: 605, y: 300 },
  { x: 605, y: 500 },
  { x: 605, y: 700 },
]

const res1 = cut(page, W, H, stroke1)
ok('tree' in res1, 'cut returned a tree')
const tree1 = (res1 as { tree: Node }).tree

eq(tree1.type, 'split', 'the cut produced a split')
if (tree1.type === 'split') {
  eq(tree1.dir, 'row', 'dominant vertical stroke creates a row split (side by side)')
  eq(tree1.kids.length, 2, 'split into 2 kids')
  // Snapped to 1/2 of 1200 = 600 px (605 is within 14px of 600)
  eq(tree1.sizes[0], 0.5, 'first size snapped to 0.5')
  eq(tree1.sizes[1], 0.5, 'second size snapped to 0.5')
  // Original leaf is kept in the first part (frac >= 0.5)
  eq((tree1.kids[0] as Zone).id, 'stage', 'kept stage zone id in the larger/first part')
  ok((tree1.kids[1] as Zone).id !== 'stage', 'fresh zone created for the other part')
}

/* -- 2. A too-short stroke is rejected with a reason -- */

const shortStroke = [
  { x: 600, y: 350 },
  { x: 600, y: 400 },
  { x: 600, y: 450 },
]
const res2 = cut(page, W, H, shortStroke)
ok('reject' in res2, 'too-short stroke was rejected')
const r2 = res2 as { reject: string; line?: Line }
ok(r2.reject.includes('Too short'), `rejection reason explains it is too short: "${r2.reject}"`)
ok(r2.line != null, 'rejected cut returns line coordinates')

/* -- 3. A stroke that would leave a side under the minimum is rejected -- */

// A vertical stroke too close to left edge (x=100 < MIN_W=240)
const edgeStroke = [
  { x: 100, y: 100 },
  { x: 100, y: 300 },
  { x: 100, y: 500 },
  { x: 100, y: 700 },
]
const res3 = cut(page, W, H, edgeStroke)
ok('reject' in res3, 'stroke too close to edge was rejected')
const r3 = res3 as { reject: string; line?: Line }
ok(r3.reject.includes('Too close to an edge'), `rejection reason explains minimum: "${r3.reject}"`)
ok(r3.reject.includes('240 px'), 'specifies the 240 px minimum width')

// A horizontal stroke too close to top edge (y=60 < MIN_H=140)
const topStroke = [
  { x: 100, y: 60 },
  { x: 400, y: 60 },
  { x: 800, y: 60 },
  { x: 1100, y: 60 },
]
const resTop = cut(page, W, H, topStroke)
ok('reject' in resTop, 'horizontal stroke too close to top edge was rejected')
const rTop = resTop as { reject: string; line?: Line }
ok(rTop.reject.includes('140 px'), 'specifies the 140 px minimum height')

/* -- 4. Erase merges back -- */

// Erase the dividing line of tree1 (at x=600, y=400)
const erased = erase(tree1, { x: 600, y: 400 }, W, H)
ok(erased !== null, 'erase returned a merged tree')
eq(erased?.type, 'zone', 'erasing the line collapsed the split back into a single zone')
eq((erased as Zone)?.id, 'stage', 'erased result kept the stage zone id')

/* -- 5. Horizontal stroke divides into col (top/bottom) -- */

const horizStroke = [
  { x: 100, y: 395 },
  { x: 500, y: 395 },
  { x: 900, y: 395 },
  { x: 1100, y: 395 },
]
const resHoriz = cut(page, W, H, horizStroke)
ok('tree' in resHoriz, 'horizontal cut succeeded')
const treeHoriz = (resHoriz as { tree: Node }).tree
eq(treeHoriz.type, 'split', 'horizontal cut produced a split')
if (treeHoriz.type === 'split') {
  eq(treeHoriz.dir, 'col', 'horizontal stroke creates a col split (top/bottom)')
  eq(treeHoriz.sizes[0], 0.5, 'snapped to half (0.5)')
}

/* -- 6. Assign keeps every old zone either placed or leftover and preserves ids -- */

// Test 6a: Tree expanded from 1 zone to 2 zones
const oldRects1 = sketchLayout(page, W, H)
const newRects1 = sketchLayout(tree1, W, H)
const assigned1 = assign(page, oldRects1, tree1, newRects1)

eq(zones(assigned1.tree).length, 2, 'assigned tree has 2 regions')
ok(zones(assigned1.tree).some((z) => z.id === 'stage'), 'Stage zone id preserved in assigned tree')
eq(assigned1.leftover.length, 0, 'no leftover zones when old zones all placed')

// Test 6b: Tree shrunk from 2 zones to 1 zone (erased line)
const zA: Zone = { type: 'zone', id: 'za', show: 'objects', name: 'Alpha' }
const zB: Zone = { type: 'zone', id: 'zb', show: 'objects', name: 'Beta' }
const twoTree: Node = { type: 'split', dir: 'row', kids: [zA, zB], sizes: [0.5, 0.5] }
const twoOldRects = sketchLayout(twoTree, W, H)

const singleNew: Node = { type: 'zone', id: 'fresh-1', show: 'objects', name: 'Full' }
const singleNewRects = sketchLayout(singleNew, W, H)

const assigned2 = assign(twoTree, twoOldRects, singleNew, singleNewRects)
eq(zones(assigned2.tree).length, 1, 'assigned tree has 1 zone')
eq(assigned2.leftover.length, 1, '1 zone is leftover (to float)')

const allTwoIds = new Set(['za', 'zb'])
const placedId = zones(assigned2.tree)[0].id
const leftoverId = assigned2.leftover[0].id

ok(allTwoIds.has(placedId), 'placed zone has one of the original old ids')
ok(allTwoIds.has(leftoverId), 'leftover zone has the other original old id')
ok(placedId !== leftoverId, 'placed and leftover ids are distinct')

// Test 6c: Three old zones to two new regions with fresh IDs
const z1: Zone = { type: 'zone', id: 'z1', show: 'objects', name: 'One', slot: { follow: true, show: 'objects', items: ['addr:1'], present: 'cards' } }
const z2: Zone = { type: 'zone', id: 'z2', show: 'objects', name: 'Two', slot: { follow: true, show: 'objects', items: ['addr:2'], present: 'cards' } }
const z3: Zone = { type: 'zone', id: 'z3', show: 'objects', name: 'Three', slot: { follow: false, show: 'objects', items: ['addr:3'], present: 'list' } }
const threeTree: Node = { type: 'split', dir: 'row', kids: [z1, z2, z3], sizes: [1 / 3, 1 / 3, 1 / 3] }
const threeOldRects = sketchLayout(threeTree, W, H)

const twoNew: Node = {
  type: 'split',
  dir: 'row',
  kids: [
    { type: 'zone', id: 'new-left', show: 'objects' },
    { type: 'zone', id: 'new-right', show: 'objects' },
  ],
  sizes: [0.5, 0.5],
}
const twoNewRects = sketchLayout(twoNew, W, H)

const assigned3 = assign(threeTree, threeOldRects, twoNew, twoNewRects)
const placedZones3 = zones(assigned3.tree)

eq(placedZones3.length, 2, '2 zones placed in the new tree')
eq(assigned3.leftover.length, 1, '1 zone returned in leftover')

const unionIds = new Set([...placedZones3.map((z) => z.id), ...assigned3.leftover.map((z) => z.id)])
eq(unionIds.size, 3, 'every old zone is accounted for (placed + leftover = 3)')
ok(unionIds.has('z1') && unionIds.has('z2') && unionIds.has('z3'), 'all original ids z1, z2, z3 preserved')

// Check that whole Zone record is preserved (slot, items, etc.)
const foundZ1 = placedZones3.find((z) => z.id === 'z1') ?? assigned3.leftover.find((z) => z.id === 'z1')
ok(foundZ1 != null, 'z1 found')
eq(foundZ1?.slot?.items, ['addr:1'], 'z1 preserved its full slot record')
eq(foundZ1?.name, 'One', 'z1 preserved its name')

console.log(`fluid sketch: ${checks} checks passed`)
