/* Arrange sheet, thumbnail geometry and swap history unit tests (W3-ui Antigravity).
 * Pure geometry, swap history and control correction checks. */

import assert from 'node:assert/strict'
import { layoutThumbRects } from '../src/fluid/workspace/thumbnail'
import type { Node, Split, Zone } from '../src/fluid/workspace/tree'
import type { Arr } from '../src/fluid/workspace/place'
import { CONVERSATION_ID } from '../src/fluid/focus/types'
import {
  columnZone,
  dockFloat,
  dockSection,
  floatObject,
  locate,
  makePrimary,
  primaryOf,
  swapBack,
} from '../src/fluid/focus/model'
import { placeCtl } from '../src/fluid/focus/ColumnPlace'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (v: unknown, what: string) => { assert.ok(v, what); checks++ }

const z = (id: string, name?: string): Zone => ({
  type: 'zone',
  id,
  name: name ?? id,
  show: 'objects',
  slot: { follow: true, show: 'objects', items: [], present: 'cards' },
})

const arr = (tree: Node, focus?: Arr['focus']): Arr => ({
  tree,
  pages: [],
  ...(focus ? { focus } : {}),
})

/* =========================================================================
   1. THUMBNAIL GEOMETRY FROM A TREE (Pure geometry)
   ========================================================================= */

// Null or invalid input returns 1 rect spanning full bounds
eq(layoutThumbRects(null, { w: 60, h: 40 }), [{ x: 0, y: 0, w: 60, h: 40 }], 'null input returns default bounds')
eq(layoutThumbRects({}, { w: 60, h: 40 }), [{ x: 0, y: 0, w: 60, h: 40 }], 'empty input returns default bounds')

// Single zone
const singleZone = z('stage', 'Stage')
const singleRects = layoutThumbRects(singleZone, { w: 60, h: 40 })
eq(singleRects.length, 1, 'single zone produces 1 rect')
eq(singleRects[0], { x: 0, y: 0, w: 60, h: 40, name: 'Stage', id: 'stage' }, 'single zone fills thumbnail bounds')

// Row split: side by side
const rowSplit: Split = {
  type: 'split',
  dir: 'row',
  sizes: [0.5, 0.5],
  kids: [z('left', 'Left'), z('right', 'Right')],
}
const rowRects = layoutThumbRects(rowSplit, { w: 60, h: 40 }, 2)
eq(rowRects.length, 2, 'row split produces 2 rects')
eq(rowRects[0].x, 0, 'first child starts at 0')
eq(rowRects[0].y, 0, 'first child starts at y=0')
eq(rowRects[0].w, 29, 'first child width is (60-2)/2 = 29')
eq(rowRects[0].h, 40, 'first child height is full 40')
eq(rowRects[1].x, 31, 'second child starts at x = 29 + gap(2) = 31')
eq(rowRects[1].w, 29, 'second child width is 29')
eq(rowRects[0].w + 2 + rowRects[1].w, 60, 'total width equals bounds width exactly')

// Col split: stacked top and bottom
const colSplit: Split = {
  type: 'split',
  dir: 'col',
  sizes: [0.5, 0.5],
  kids: [z('top', 'Top'), z('bottom', 'Bottom')],
}
const colRects = layoutThumbRects(colSplit, { w: 60, h: 40 }, 2)
eq(colRects.length, 2, 'col split produces 2 rects')
eq(colRects[0].x, 0, 'first child starts at x=0')
eq(colRects[0].y, 0, 'first child starts at y=0')
eq(colRects[0].w, 60, 'first child width is full 60')
eq(colRects[0].h, 19, 'first child height is (40-2)/2 = 19')
eq(colRects[1].y, 21, 'second child starts at y = 19 + gap(2) = 21')
eq(colRects[1].h, 19, 'second child height is 19')
eq(colRects[0].h + 2 + colRects[1].h, 40, 'total height equals bounds height exactly')

// 3-way split with uneven sizes
const threeSplit: Split = {
  type: 'split',
  dir: 'row',
  sizes: [0.5, 0.3, 0.2],
  kids: [z('a'), z('b'), z('c')],
}
const threeRects = layoutThumbRects(threeSplit, { w: 100, h: 50 }, 4)
eq(threeRects.length, 3, '3-way split produces 3 rects')
// total gaps = 2 * 4 = 8; availW = 100 - 8 = 92
// sizes: 92 * 0.5 = 46; 92 * 0.3 = 27.6; last takes remainder: 100 - (46+4 + 27.6+4) = 18.4
ok(threeRects[0].w > threeRects[1].w && threeRects[1].w > threeRects[2].w, 'rect widths are ordered proportionally')
const lastRight = threeRects[2].x + threeRects[2].w
eq(lastRight, 100, 'three rects span exactly to width bounds')

// Nested split: row with col inside (like Oversight/Triage presets)
const nestedTree: Split = {
  type: 'split',
  dir: 'row',
  sizes: [0.6, 0.4],
  kids: [
    z('left', 'Left'),
    {
      type: 'split',
      dir: 'col',
      sizes: [0.5, 0.5],
      kids: [z('topRight', 'TR'), z('bottomRight', 'BR')],
    },
  ],
}
const nestedRects = layoutThumbRects(nestedTree, { w: 60, h: 40 }, 2)
eq(nestedRects.length, 3, 'nested tree produces 3 zone rects')
eq(nestedRects[0].name, 'Left', 'left zone is first')
eq(nestedRects[1].name, 'TR', 'top right zone is second')
eq(nestedRects[2].name, 'BR', 'bottom right zone is third')
ok(nestedRects[1].x >= nestedRects[0].x + nestedRects[0].w, 'inner rects are to the right of left rect')
ok(nestedRects[2].y >= nestedRects[1].y + nestedRects[1].h, 'bottom inner rect is below top inner rect')

// Layout object passed directly (with .tree)
const layoutObj = { tree: nestedTree, name: 'My Layout' }
const fromLayoutObj = layoutThumbRects(layoutObj, { w: 60, h: 40 }, 2)
eq(fromLayoutObj.length, 3, 'extracts .tree from layout container')

/* =========================================================================
   2. ONE KIND OF SWAP & SWAP HISTORY (dockFloat, dockSection, swapBack)
   ========================================================================= */

// dockSection on center: swapping section onto another section's center
const twoSectionTree: Node = {
  type: 'split',
  dir: 'row',
  sizes: [0.5, 0.5],
  kids: [z('secA', 'Section A'), z('secB', 'Section B')],
}
const initialArr = arr(twoSectionTree, { primary: 'secA', previous: [] })

// Dropping secB onto secA's center
const swappedSections = dockSection(initialArr, 'secB', 'secA', 'center')
// 1. Zones traded positions in tree
eq((swappedSections.tree as Split).kids[0].id, 'secB', 'secB moved into first position')
eq((swappedSections.tree as Split).kids[1].id, 'secA', 'secA moved into second position')
// 2. Primary was recorded: secB is incoming primary
eq(primaryOf(swappedSections), 'secB', 'secB is now primary')
// 3. History was recorded: secA is in previous
eq(swappedSections.focus?.previous, ['secA'], 'secA is recorded in Esc history')

// Esc / swapBack restores the swap exactly
const restoredSections = swapBack(swappedSections)
eq((restoredSections.tree as Split).kids[0].id, 'secA', 'secA restored to first position')
eq((restoredSections.tree as Split).kids[1].id, 'secB', 'secB restored to second position')
eq(primaryOf(restoredSections), 'secA', 'secA restored as primary')
eq(restoredSections.focus?.previous ?? [], [], 'previous history was popped')

// dockFloat on center: section float dropped onto column (conversation) center
const withSectionFloat: Arr = {
  tree: z('notes', 'Notes'),
  pages: [],
  focus: {
    primary: CONVERSATION_ID,
    floats: [
      {
        id: 'float-sources',
        zone: z('sources', 'Sources'),
        x: 100,
        y: 100,
        w: 300,
        h: 200,
      },
    ],
    previous: [],
  },
}

// Dropping section float onto conversation center
const swappedFloat = dockFloat(withSectionFloat, 'float-sources', CONVERSATION_ID, 'center')
// 1. Column now has Sources
eq(columnZone(swappedFloat).id, 'sources', 'Sources moved to primary column')
// 2. Float now holds Conversation
eq(swappedFloat.focus?.floats?.[0].zone.id, CONVERSATION_ID, 'Conversation floats in place of Sources')
// 3. Primary is recorded as Sources
eq(primaryOf(swappedFloat), 'sources', 'Sources is now primary')
// 4. Previous history contains CONVERSATION_ID ('conv')
eq(swappedFloat.focus?.previous, [CONVERSATION_ID], 'CONVERSATION_ID is recorded in previous history')

// Esc / swapBack restores the float swap
const restoredFloat = swapBack(swappedFloat)
eq(columnZone(restoredFloat).id, CONVERSATION_ID, 'Conversation restored to column')
eq(restoredFloat.focus?.floats?.[0].zone.id, 'sources', 'Sources restored to float')
eq(primaryOf(restoredFloat), CONVERSATION_ID, 'Conversation restored as primary')

/* =========================================================================
   3. DEAD "FIT TO CONTENT" ROWS REMOVED
   ========================================================================= */

// Column place control explicitly disables Fit
const colCtl = placeCtl('column place')
eq(colCtl.canFit, false, 'ColumnPlace ctl.canFit is false')
eq(colCtl.toggleFit, undefined, 'ColumnPlace ctl.toggleFit is not defined')

console.log(`fluid arrange: ${checks} checks passed`)
