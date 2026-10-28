/* UNIT TESTS FOR SHEET PLACEMENT MATHS (frame/Sheet.tsx).
 *
 * Verifies:
 * - Pure function placeSheet(anchor, pop, viewport, align):
 *   - Anchors 6px below control by default when room exists below
 *   - Flips 6px above control when no room exists below and room exists above (e.g. lowest comment in Focus mode)
 *   - Clamps horizontally within viewport margins (min 8px, max viewport - width - 8px)
 *   - Caps max-height and scrolls inside itself when taller than available room
 *   - Handles end-aligned controls (TopBar / BarControls) with right-edge anchoring and left-edge clamping
 *   - Handles narrow viewports and default pop dimensions cleanly
 */

import assert from 'node:assert/strict'
import { placeSheet } from '../src/fluid/frame/Sheet'

// 1. Opens below when there is room below
{
  const anchor = { top: 50, bottom: 80, left: 100, right: 180 }
  const pop = { width: 320, height: 200 }
  const viewport = { width: 1024, height: 768 }
  const pos = placeSheet(anchor, pop, viewport, 'start')

  assert.equal(pos.up, false, 'should open below anchor')
  assert.equal(pos.top, 86, 'top should be 6px below anchor bottom (80 + 6)')
  assert.equal(pos.left, 100, 'left should align with anchor left')
  assert.equal(pos.max, undefined, 'no max height needed when fitting naturally')
}

// 2. Flips above when no room below (lowest comment in Focus mode)
{
  const anchor = { top: 700, bottom: 730, left: 200, right: 230 }
  const pop = { width: 300, height: 350 }
  const viewport = { width: 1024, height: 768 }
  const pos = placeSheet(anchor, pop, viewport, 'start')

  assert.equal(pos.up, true, 'should flip above anchor when no room below')
  assert.equal(pos.top, 344, 'top should place pop 6px above anchor top (700 - 350 - 6)')
  assert.equal(pos.top + (pop.height ?? 0), 694, 'bottom of pop should be 6px above anchor top (700 - 6 = 694)')
  assert.equal(pos.left, 200, 'left should align with anchor left')
  assert.equal(pos.max, undefined, 'no max height needed when fitting naturally above')
}

// 3. Taller than room above (scrolls inside itself if taller than room)
{
  const anchor = { top: 400, bottom: 430, left: 100, right: 130 }
  const pop = { width: 300, height: 600 }
  const viewport = { width: 1024, height: 768 }
  const pos = placeSheet(anchor, pop, viewport, 'start')

  // above = 400 - 14 = 386; below = 768 - 430 - 14 = 324; above > below -> flips up
  assert.equal(pos.up, true, 'should flip above when above has more room')
  assert.equal(pos.top, 8, 'top should clamp to 8px margin from viewport top')
  assert.equal(pos.max, 386, 'maxHeight should be capped to room above (386)')
  assert.equal(pos.top + pos.max!, 394, 'bottom of pop should be 6px above anchor top (400 - 6 = 394)')
}

// 4. Taller than room below when below has more room than above
{
  const anchor = { top: 200, bottom: 230, left: 100, right: 130 }
  const pop = { width: 300, height: 700 }
  const viewport = { width: 1024, height: 768 }
  const pos = placeSheet(anchor, pop, viewport, 'start')

  // above = 200 - 14 = 186; below = 768 - 230 - 14 = 524; below > above -> stays down
  assert.equal(pos.up, false, 'should stay below when below has more room')
  assert.equal(pos.top, 236, 'top should be 6px below anchor bottom (230 + 6)')
  assert.equal(pos.max, 524, 'maxHeight should be capped to room below (524)')
  assert.equal(pos.top + pos.max!, 760, 'bottom of pop should be 8px from viewport bottom (768 - 8 = 760)')
}

// 5. Horizontal clamping on right edge (never runs off window right)
{
  const anchor = { top: 100, bottom: 130, left: 950, right: 980 }
  const pop = { width: 300, height: 200 }
  const viewport = { width: 1024, height: 768 }
  const pos = placeSheet(anchor, pop, viewport, 'start')

  assert.equal(pos.left, 716, 'left should clamp to 1024 - 300 - 8 = 716')
  assert.equal(pos.left! + pop.width, 1016, 'right edge should stay 8px within viewport (1024 - 8)')
}

// 6. Horizontal clamping on left edge (never runs off window left)
{
  const anchor = { top: 100, bottom: 130, left: -20, right: 10 }
  const pop = { width: 300, height: 200 }
  const viewport = { width: 1024, height: 768 }
  const pos = placeSheet(anchor, pop, viewport, 'start')

  assert.equal(pos.left, 8, 'left should clamp to min 8px')
}

// 7. End-alignment (controls at right end of a bar, e.g. search / activity)
{
  const anchor = { top: 10, bottom: 40, left: 900, right: 980 }
  const pop = { width: 300, height: 200 }
  const viewport = { width: 1024, height: 768 }
  const pos = placeSheet(anchor, pop, viewport, 'end')

  assert.equal(pos.right, 44, 'right should align with anchor right edge (1024 - 980 = 44)')
  assert.equal(pos.top, 46, 'top should be 6px below anchor bottom (40 + 6)')
  assert.equal(pos.up, false)
}

// 8. End-alignment clamping on left (never runs off window left)
{
  const anchor = { top: 10, bottom: 40, left: 50, right: 100 }
  const pop = { width: 300, height: 200 }
  const viewport = { width: 1024, height: 768 }
  const pos = placeSheet(anchor, pop, viewport, 'end')

  assert.equal(pos.right, 716, 'right should clamp to 1024 - 300 - 8 = 716 so left edge stays at 8px')
}

// 9. Narrow screen viewport (smaller than pop default)
{
  const anchor = { top: 100, bottom: 130, left: 20, right: 50 }
  const pop = { width: 350, height: 200 }
  const viewport = { width: 320, height: 600 }
  const pos = placeSheet(anchor, pop, viewport, 'start')

  assert.equal(pos.left, 8, 'left should clamp to 8px on narrow screens')
}

// 10. Default sizes when pop size is omitted
{
  const anchor = { top: 50, bottom: 80, left: 100, right: 180 }
  const viewport = { width: 1024, height: 768 }
  const pos = placeSheet(anchor, {}, viewport)

  assert.equal(pos.top, 86, 'default height 240 fits below (80 + 6 = 86)')
  assert.equal(pos.left, 100, 'default width 320 fits within viewport')
}

console.log('ok   fluid_sheet_placement_unit passed all assertions')
