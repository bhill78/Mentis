import assert from 'node:assert/strict'
import { coordinatePlacement, effectiveMakeRoom, makeRoom, snap, type Body } from '../src/fluid/focus/placement'
import type { Level, SurfaceCapabilities } from '../src/fluid/surface/types'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const viewport = { x: 0, y: 0, w: 500, h: 400 }
const caps = (yielding: SurfaceCapabilities['yield'] = 'slide', movement: SurfaceCapabilities['movement'] = 'free', min = { w: 40, h: 40 }) => ({
  movement, yield: yielding, snap: true, size: { min: { standard: min } },
})
const body = (id: string, rect: Body['rect'], yielding: SurfaceCapabilities['yield'] = 'slide', movement: SurfaceCapabilities['movement'] = 'free', level: Level = 'standard', min?: { w: number; h: number }): Body =>
  ({ id, rect, level, caps: caps(yielding, movement, min) })

/* Snap to viewport and peer edges, independently on both axes. */
eq(snap({ x: 6, y: 293, w: 100, h: 100 }, [{ x: 220, y: 100, w: 80, h: 200 }], viewport),
  { rect: { x: 0, y: 300, w: 100, h: 100 }, guides: [{ axis: 'x', at: 0 }, { axis: 'y', at: 400 }] }, 'viewport edges snap within eight pixels')
eq(snap({ x: 112, y: 112, w: 100, h: 100 }, [{ x: 20, y: 20, w: 100, h: 100 }], viewport).rect,
  { x: 120, y: 120, w: 100, h: 100 }, 'opposing peer edges snap')
eq(snap({ x: 109, y: 109, w: 100, h: 100 }, [{ x: 20, y: 20, w: 80, h: 80 }], viewport).rect,
  { x: 109, y: 109, w: 100, h: 100 }, 'nine pixels is past the threshold')

/* Shortest clearing move and deterministic viewport fallback. */
const incoming = { x: 100, y: 100, w: 100, h: 100 }
eq([...makeRoom(incoming, [body('near', { x: 180, y: 120, w: 80, h: 60 })], viewport, { margin: 0 })],
  [['near', { dx: 20, dy: 0 }]], 'shortest axis-aligned move wins')
eq([...makeRoom({ x: 400, y: 100, w: 100, h: 100 }, [body('edge', { x: 390, y: 120, w: 80, h: 60 })], viewport, { margin: 0 })],
  [['edge', { dx: -70, dy: 0 }]], 'an off-viewport shortest move yields to the viable side')

/* If sliding cannot fit, shrink above the level minimum, then fold. */
const boxedViewport = { x: 0, y: 0, w: 300, h: 200 }
const blocker = { x: 60, y: 0, w: 180, h: 200 }
eq([...makeRoom(blocker, [body('shrink', { x: 0, y: 50, w: 100, h: 100 }, 'shrink', 'free', 'standard', { w: 50, h: 80 })], boxedViewport, { margin: 0 })],
  [['shrink', { dx: 0, dy: 0, w: 60, h: 100 }]], 'shrink retains the largest viable rectangle above minimum')
eq([...makeRoom(blocker, [body('fold', { x: 0, y: 50, w: 100, h: 100 }, 'fold', 'free', 'standard', { w: 90, h: 100 })], boxedViewport, { margin: 0 })],
  [['fold', { dx: 0, dy: 0, fold: true }]], 'fold is the last fallback')

eq(makeRoom(incoming, [body('never', { x: 150, y: 150, w: 80, h: 80 }, 'never'), body('fixed', { x: 150, y: 150, w: 80, h: 80 }, 'slide', 'fixed')], viewport).size,
  0, 'never-yield and fixed/docked bodies stay ground')
eq([...makeRoom({ x: 100, y: 0, w: 100, h: 100 }, [body('edge', { x: 150, y: 0, w: 80, h: 60 }, 'slide', { anchored: 'edge' })], viewport, { margin: 0 })],
  [['edge', { dx: 50, dy: 0 }]], 'an edge anchor moves only along its edge')
eq(incoming, { x: 100, y: 100, w: 100, h: 100 }, 'incoming geometry is never changed')

eq(coordinatePlacement(incoming, [body('b', { x: 180, y: 120, w: 80, h: 60 })], viewport, { snap: false, makeRoom: 'off' }).displacements.size,
  0, 'Off is inert')
eq(coordinatePlacement(incoming, [body('b', { x: 180, y: 120, w: 80, h: 60 })], viewport, { snap: false, makeRoom: 'drag', trigger: 'expand' }).displacements.size,
  0, 'While dragging does not run on Expand')
eq(coordinatePlacement(incoming, [body('b', { x: 180, y: 120, w: 80, h: 60 })], viewport, { snap: false, makeRoom: 'expand', trigger: 'expand' }).displacements.size,
  1, 'Also on Expand runs for Expand')
eq(effectiveMakeRoom({ spatial: { makeRoom: 'drag' } }, 'expand'), 'drag', 'workspace override wins')
eq(effectiveMakeRoom({}, 'expand'), 'expand', 'global default is next')
eq(effectiveMakeRoom({}), 'off', 'built-in default is Off')

console.log(`fluid placement: ${checks} checks`)
