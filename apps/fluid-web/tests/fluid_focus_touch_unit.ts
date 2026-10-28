import assert from 'node:assert/strict'
import { PAD_HIT_RADIUS, TOUCH_HOLD_MS, TOUCH_MOVE_PX, padsFor, pointerDragDecision } from '../src/fluid/focus/drag'
import { drawnFloatRect } from '../src/fluid/focus/model'
import type { Float } from '../src/fluid/focus/types'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }

eq(pointerDragDecision('touch', TOUCH_HOLD_MS - 1, 0), 'wait', 'touch waits for the hold')
eq(pointerDragDecision('pen', TOUCH_HOLD_MS, TOUCH_MOVE_PX), 'start', 'pen starts after holding within the movement allowance')
eq(pointerDragDecision('touch', 20, TOUCH_MOVE_PX + 0.1), 'cancel', 'a swipe cancels before the hold')
eq(pointerDragDecision('mouse', 0, 100), 'start', 'mouse remains immediate')

const f: Float = { id: 'float', zone: { type: 'zone', id: 'zone', show: 'objects' }, x: 1400, y: 900, w: 320, h: 240 }
eq(drawnFloatRect(f, 800, 600), { x: 480, y: 360, w: 320, h: 240 }, 'a restored float that fits is drawn wholly inside the smaller room')
eq(drawnFloatRect({ ...f, w: 1000, h: 800 }, 800, 600), { x: 756, y: 556, w: 1000, h: 800 }, 'one larger than the room keeps 44 px of it reachable')
eq([f.x, f.y, f.w, f.h], [1400, 900, 320, 240], 'draw clamping does not mutate the saved rectangle')

const visible = { x: 100, y: 50, w: 80, h: 70 }
const pads = padsFor(visible, true)
ok(PAD_HIT_RADIUS >= 22, 'dock hit radius is finger-sized')
ok(pads.every((p) => p.x >= visible.x && p.x <= visible.x + visible.w && p.y >= visible.y && p.y <= visible.y + visible.h), 'dock pads stay inside the visible target')

console.log(`fluid focus touch: ${checks} checks passed`)
