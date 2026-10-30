/* Surface Tension P6: wide-placement geometry.  This module deliberately
 * knows nothing about settings storage, actions or the Holder.  Callers give
 * it the capabilities and effective Make room value supplied by P1/P2. */

import type { Level, MakeRoom, Rect, SurfaceCapabilities, ZoneId } from '../surface/types'

export interface Body {
  id: ZoneId
  rect: Rect
  level: Level
  caps: Pick<SurfaceCapabilities, 'movement' | 'yield' | 'snap' | 'size'>
}

export type Guide = { axis: 'x' | 'y'; at: number }
export type Displacement = { dx: number; dy: number; w?: number; h?: number; fold?: true }
export type PlacementTrigger = 'drag' | 'expand'

const right = (r: Rect) => r.x + r.w
const bottom = (r: Rect) => r.y + r.h
const finiteRect = (r: Rect) => [r.x, r.y, r.w, r.h].every(Number.isFinite) && r.w >= 0 && r.h >= 0
const inside = (r: Rect, v: Rect) => r.x >= v.x && r.y >= v.y && right(r) <= right(v) && bottom(r) <= bottom(v)
const intersects = (a: Rect, b: Rect) => a.x < right(b) && right(a) > b.x && a.y < bottom(b) && bottom(a) > b.y

type Candidate = { delta: number; at: number; order: number }
function closest(candidates: Candidate[], threshold: number): Candidate | undefined {
  return candidates
    .filter((c) => Math.abs(c.delta) <= threshold)
    .sort((a, b) => Math.abs(a.delta) - Math.abs(b.delta) || a.order - b.order)[0]
}

/** Snap equal/opposing edges to float and viewport edges.  X and Y are
 * independent; a guide is returned only for an axis that actually snapped. */
export function snap(moving: Rect, others: Rect[], viewport: Rect, opts: { threshold?: number } = {}): { rect: Rect; guides: Guide[] } {
  if (!finiteRect(moving) || !finiteRect(viewport)) return { rect: moving, guides: [] }
  const threshold = Math.max(0, opts.threshold ?? 8)
  const vertical = [viewport.x, right(viewport), ...others.flatMap((r) => [r.x, right(r)])]
  const horizontal = [viewport.y, bottom(viewport), ...others.flatMap((r) => [r.y, bottom(r)])]
  const xs: Candidate[] = []
  const ys: Candidate[] = []
  let order = 0
  for (const at of vertical) {
    xs.push({ delta: at - moving.x, at, order: order++ })
    xs.push({ delta: at - right(moving), at, order: order++ })
  }
  for (const at of horizontal) {
    ys.push({ delta: at - moving.y, at, order: order++ })
    ys.push({ delta: at - bottom(moving), at, order: order++ })
  }
  const x = closest(xs, threshold), y = closest(ys, threshold)
  return {
    rect: { ...moving, x: moving.x + (x?.delta ?? 0), y: moving.y + (y?.delta ?? 0) },
    guides: [...(x ? [{ axis: 'x' as const, at: x.at }] : []), ...(y ? [{ axis: 'y' as const, at: y.at }] : [])],
  }
}

function allowedAxes(body: Body, viewport: Rect): ReadonlySet<'x' | 'y'> {
  if (body.caps.movement === 'fixed') return new Set()
  if (body.caps.movement === 'free') return new Set(['x', 'y'])
  if (body.caps.movement.anchored === 'zone') return new Set()
  const onHorizontalEdge = body.rect.y <= viewport.y || bottom(body.rect) >= bottom(viewport)
  const onVerticalEdge = body.rect.x <= viewport.x || right(body.rect) >= right(viewport)
  if (onHorizontalEdge && !onVerticalEdge) return new Set(['x'])
  if (onVerticalEdge && !onHorizontalEdge) return new Set(['y'])
  return new Set()
}

type Move = { dx: number; dy: number; rect: Rect; order: number }
function slide(body: Body, blocked: Rect, viewport: Rect): Move | undefined {
  const axes = allowedAxes(body, viewport)
  const r = body.rect
  const candidates: Move[] = [
    { dx: blocked.x - right(r), dy: 0, rect: { ...r, x: blocked.x - r.w }, order: 0 },
    { dx: right(blocked) - r.x, dy: 0, rect: { ...r, x: right(blocked) }, order: 1 },
    { dx: 0, dy: blocked.y - bottom(r), rect: { ...r, y: blocked.y - r.h }, order: 2 },
    { dx: 0, dy: bottom(blocked) - r.y, rect: { ...r, y: bottom(blocked) }, order: 3 },
  ]
  return candidates.filter((c) => (c.dx ? axes.has('x') : axes.has('y')) && inside(c.rect, viewport))
    .sort((a, b) => Math.abs(a.dx || a.dy) - Math.abs(b.dx || b.dy) || a.order - b.order)[0]
}

function shrink(body: Body, blocked: Rect, viewport: Rect): Displacement | undefined {
  if (body.caps.yield !== 'shrink' && body.caps.yield !== 'fold') return undefined
  const min = body.caps.size.min[body.level]
  if (!min) return undefined
  const r = body.rect
  const choices: Rect[] = [
    { ...r, w: Math.min(r.w, blocked.x - r.x) },
    { ...r, x: right(blocked), w: Math.min(r.w, right(viewport) - right(blocked)) },
    { ...r, h: Math.min(r.h, blocked.y - r.y) },
    { ...r, y: bottom(blocked), h: Math.min(r.h, bottom(viewport) - bottom(blocked)) },
  ]
  const chosen = choices.filter((x) => x.w >= min.w && x.h >= min.h && inside(x, viewport) && !intersects(x, blocked))
    .sort((a, b) => b.w * b.h - a.w * a.h)[0]
  return chosen ? { dx: chosen.x - r.x, dy: chosen.y - r.y, w: chosen.w, h: chosen.h } : undefined
}

/** Yield each intersecting float independently.  The expanded blocked rect
 * supplies the margin; an impossible body is simply left overlapping. */
export function makeRoom(incoming: Rect, bodies: Body[], viewport: Rect, opts: { margin?: number } = {}): Map<ZoneId, Displacement> {
  const out = new Map<ZoneId, Displacement>()
  if (!finiteRect(incoming) || !finiteRect(viewport)) return out
  const margin = Math.max(0, opts.margin ?? 8)
  const blocked = { x: incoming.x - margin, y: incoming.y - margin, w: incoming.w + 2 * margin, h: incoming.h + 2 * margin }
  for (const body of bodies) {
    if (!finiteRect(body.rect) || !intersects(body.rect, blocked) || body.caps.yield === 'never' || body.caps.movement === 'fixed') continue
    const moved = slide(body, blocked, viewport)
    if (moved) { out.set(body.id, { dx: moved.dx, dy: moved.dy }); continue }
    const smaller = shrink(body, blocked, viewport)
    if (smaller) { out.set(body.id, smaller); continue }
    if (body.caps.yield === 'fold') out.set(body.id, { dx: 0, dy: 0, fold: true })
  }
  return out
}

/** The policy seam used by drag and Expand.  P2 supplies the effective value;
 * P1 supplies bodies/capabilities.  With Off this is byte-for-byte inert. */
export function coordinatePlacement(incoming: Rect, bodies: Body[], viewport: Rect, opts: {
  snap?: boolean; makeRoom?: MakeRoom; trigger?: PlacementTrigger; threshold?: number; margin?: number
} = {}): { rect: Rect; guides: Guide[]; displacements: Map<ZoneId, Displacement> } {
  const snapped = opts.snap === false ? { rect: incoming, guides: [] as Guide[] }
    : snap(incoming, bodies.filter((b) => b.caps.snap).map((b) => b.rect), viewport, { threshold: opts.threshold })
  const mode = opts.makeRoom ?? 'off', trigger = opts.trigger ?? 'drag'
  const enabled = mode === 'expand' || (mode === 'drag' && trigger === 'drag')
  return { ...snapped, displacements: enabled ? makeRoom(snapped.rect, bodies, viewport, { margin: opts.margin }) : new Map() }
}

export function effectiveMakeRoom(arr: { spatial?: { makeRoom?: MakeRoom } }, global?: MakeRoom): MakeRoom {
  return arr.spatial?.makeRoom ?? global ?? 'off'
}
