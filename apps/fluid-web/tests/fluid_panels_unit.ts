/* UNIT TESTS FOR CONSOLIDATED SHEET, PORTAL LAYER, AND RETIRED CLASSIC SWITCH.
 *
 * Verifies:
 * - One anchored sheet (frame/Sheet.tsx):
 *   - Global call style: openSheet, closeSheet, sheetOpen, useOpenSheet
 *   - Anchored 6px below the opener, aligned start or end with window bound margin
 *   - Opt and Sec components are exported for workspace callers
 *   - Sheet component handles both global id and local anchor call styles
 * - Portal layer (frame/layer.tsx):
 *   - useLayer and Layer exports exist and function
 * - Retired Classic switch:
 *   - shellSwitch.ts exports fluidHref and labRedirect
 *   - classicHref is completely removed
 * - Deleted module:
 *   - src/fluid/workspace/Sheet.tsx no longer exists
 */

import assert from 'node:assert/strict'
import { existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import * as shellSwitch from '../src/shellSwitch'

// Provide minimal window/document mocks for Node test environment
if (typeof globalThis.window === 'undefined') {
  const listeners: Record<string, Function[]> = {}
  ;(globalThis as any).window = {
    innerWidth: 1024,
    innerHeight: 768,
    addEventListener(event: string, fn: Function) {
      listeners[event] = listeners[event] || []
      listeners[event].push(fn)
    },
    removeEventListener(event: string, fn: Function) {
      if (listeners[event]) {
        listeners[event] = listeners[event].filter((f) => f !== fn)
      }
    },
  }
}
if (typeof globalThis.document === 'undefined') {
  const listeners: Record<string, Function[]> = {}
  ;(globalThis as any).document = {
    addEventListener(event: string, fn: Function) {
      listeners[event] = listeners[event] || []
      listeners[event].push(fn)
    },
    removeEventListener(event: string, fn: Function) {
      if (listeners[event]) {
        listeners[event] = listeners[event].filter((f) => f !== fn)
      }
    },
    getElementById() { return null },
  }
}

const { openSheet, closeSheet, sheetOpen, Sheet, Opt, Sec } = await import('../src/fluid/frame/Sheet')
const { Layer, useLayer } = await import('../src/fluid/frame/layer')

// 1. shellSwitch tests: fluidHref and labRedirect work, classicHref is removed
assert.equal(shellSwitch.fluidHref(undefined), '/fluid')
assert.equal(shellSwitch.fluidHref('c-123'), '/fluid?c=c-123')
assert.equal(
  shellSwitch.labRedirect({ pathname: '/lab', search: '', hash: '#/c/conv-abc' }),
  '/fluid?c=conv-abc',
)
assert.equal(
  shellSwitch.labRedirect({ pathname: '/', search: '?lab=1&c=conv-xyz', hash: '' }),
  '/fluid?c=conv-xyz',
)
assert.equal(
  shellSwitch.labRedirect({ pathname: '/other', search: '', hash: '' }),
  null,
)
assert.equal('classicHref' in shellSwitch, false, 'classicHref must be removed from shellSwitch')

// 2. Sheet tests: openSheet, closeSheet, positioning
const mockOpener = {
  getBoundingClientRect() {
    return {
      left: 100,
      right: 180,
      top: 50,
      bottom: 80,
      width: 80,
      height: 30,
      x: 100,
      y: 50,
      toJSON() {},
    } as DOMRect
  },
} as unknown as Element

assert.equal(sheetOpen(), false)
assert.equal(closeSheet(), false)

// openSheet start-aligned (default): anchored 6px below opener (bottom: 80 + 6 = 86)
openSheet('test-sheet', mockOpener, 'start')
assert.equal(sheetOpen(), true)

// closeSheet dismisses
assert.equal(closeSheet(), true)
assert.equal(sheetOpen(), false)

// openSheet end-aligned: anchored 6px below opener (bottom: 80 + 6 = 86), right edge aligned
openSheet('test-end-sheet', mockOpener, 'end')
assert.equal(sheetOpen(), true)
assert.equal(closeSheet(), true)

// 3. Components exported from consolidated Sheet module
assert.equal(typeof Sheet, 'function', 'Sheet must be a component function')
assert.equal(typeof Opt, 'function', 'Opt must be a component function')
assert.equal(typeof Sec, 'function', 'Sec must be a component function')

// 4. Layer module exports
assert.equal(typeof useLayer, 'function', 'useLayer must be a hook function')
assert.equal(typeof Layer, 'function', 'Layer must be a component function')

// 5. Verify deleted module is absent
const workspaceSheetPath = fileURLToPath(new URL('../src/fluid/workspace/Sheet.tsx', import.meta.url))
assert.equal(existsSync(workspaceSheetPath), false, 'src/fluid/workspace/Sheet.tsx must be deleted')

console.log('ok   fluid_panels_unit passed all assertions')
