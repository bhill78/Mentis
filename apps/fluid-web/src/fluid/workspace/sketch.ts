/* THE VISUAL LAYOUT SKETCHER (pure layout, cuts, erasure and zone assignment).
 *
 * Implements the prototype's interaction model (DESIGN.md section 5):
 *   - sketchLayout: computes bounding rectangles for every split and zone;
 *   - cut: dominant-axis stroke snapping to 24px grid or halves/thirds;
 *   - erase: removes a divider gutter and merges the sibling zones;
 *   - assign: maps new sketched regions to old zones by overlap area,
 *     keeping unplaced zones in `leftover` so they can float.
 */

import {
  GUTTER,
  MIN_W,
  MIN_H,
  type Node,
  type Zone,
  type Split,
  type Rect,
  zones,
  zone,
  findZone,
} from './tree'

export const SNAP = 24

export interface Point {
  x: number
  y: number
}

export interface Line {
  x1: number
  y1: number
  x2: number
  y2: number
}

export interface PlacedNode {
  node: Node
  r: Rect
}

export interface CutInspection {
  leaf: { node: Zone; r: Rect }
  dir: 'row' | 'col'
  frac: number
  line: Line
  bad?: string
  sizes: [number, number]
}

export interface SketchLine {
  split: Split
  index: number
  line: Line
  canErase: boolean
}

/** Flatten single-child splits and same-direction nesting. */
export function normalize(n: Node): Node {
  if (n.type === 'zone') return n
  const kids: Node[] = []
  const sizes: number[] = []
  n.kids.forEach((k, i) => {
    const c = normalize(k)
    if (c.type === 'split' && c.dir === n.dir) {
      const s = c.sizes.reduce((a, b) => a + b, 0) || 1
      c.kids.forEach((kk, j) => {
        kids.push(kk)
        sizes.push((n.sizes[i] * c.sizes[j]) / s)
      })
    } else {
      kids.push(c)
      sizes.push(n.sizes[i])
    }
  })
  if (kids.length === 1) return kids[0]
  const t = sizes.reduce((a, b) => a + b, 0) || 1
  return { type: 'split', dir: n.dir, kids, sizes: sizes.map((s) => s / t) }
}

function cloneNode(n: Node): Node {
  if (n.type === 'zone') return { ...n, slot: n.slot ? { ...n.slot, items: [...n.slot.items] } : undefined }
  return { ...n, sizes: [...n.sizes], kids: n.kids.map(cloneNode) }
}

/** Layout of a tree inside W x H, returning each split and leaf zone rectangle. */
export function sketchLayout(tree: Node, W: number, H: number): PlacedNode[] {
  const out: PlacedNode[] = []
  function place(n: Node, r: Rect) {
    out.push({ node: n, r })
    if (n.type === 'zone') return
    const row = n.dir === 'row'
    const along = (row ? r.w : r.h) - GUTTER * (n.kids.length - 1)
    let at = row ? r.x : r.y
    n.kids.forEach((k, i) => {
      const s = Math.max(0, along * n.sizes[i])
      place(k, row ? { x: at, y: r.y, w: s, h: r.h } : { x: r.x, y: at, w: r.w, h: s })
      at += s + GUTTER
    })
  }
  place(tree, { x: 0, y: 0, w: W, h: H })
  return out
}

/** Analyze a drawn stroke across the tree. */
export function inspectCut(tree: Node, W: number, H: number, stroke: Point[]): CutInspection | null {
  if (stroke.length < 2) return null
  const a = stroke[0]
  const b = stroke[stroke.length - 1]
  const dx = Math.abs(b.x - a.x)
  const dy = Math.abs(b.y - a.y)
  const mid = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }

  const placed = sketchLayout(tree, W, H)
  const leaves = placed.filter((p): p is { node: Zone; r: Rect } => p.node.type === 'zone')

  // Find leaf at midpoint, or fallback to any stroke point
  let leaf = leaves.find((p) => mid.x >= p.r.x && mid.x <= p.r.x + p.r.w && mid.y >= p.r.y && mid.y <= p.r.y + p.r.h)
  if (!leaf) {
    leaf = leaves.find((p) => stroke.some((pt) => pt.x >= p.r.x && pt.x <= p.r.x + p.r.w && pt.y >= p.r.y && pt.y <= p.r.y + p.r.h))
  }
  if (!leaf) return null

  const r = leaf.r
  const horiz = dx >= dy // horizontal stroke divides vertically (col); vertical stroke divides horizontally (row)
  const len = horiz ? dx : dy
  const span = horiz ? r.w : r.h
  let v = horiz ? stroke.reduce((s, p) => s + p.y, 0) / stroke.length : stroke.reduce((s, p) => s + p.x, 0) / stroke.length
  const lo = horiz ? r.y : r.x
  const size = horiz ? r.h : r.w

  let snapped = Math.round(v / SNAP) * SNAP
  for (const f of [1 / 2, 1 / 3, 2 / 3]) {
    if (Math.abs(v - (lo + size * f)) < 14) snapped = lo + size * f
  }
  v = snapped

  const min = horiz ? MIN_H : MIN_W
  const line: Line = horiz
    ? { x1: r.x, y1: v, x2: r.x + r.w, y2: v }
    : { x1: v, y1: r.y, x2: v, y2: r.y + r.h }

  let bad: string | undefined
  if (len < Math.max(60, span * 0.5)) {
    bad = 'Too short: a line must cross most of the region it divides.'
  } else if (v - lo - GUTTER / 2 < min || lo + size - v - GUTTER / 2 < min) {
    bad = `Too close to an edge: each part needs ${min} px.`
  }

  const sizes: [number, number] = [v - lo, lo + size - v]
  const frac = (v - lo) / size

  return {
    leaf,
    dir: horiz ? 'col' : 'row',
    frac,
    line,
    bad,
    sizes,
  }
}

function replaceLeaf(root: Node, leafId: string, replacement: Node): Node {
  if (root.type === 'zone') {
    return root.id === leafId ? replacement : root
  }
  return {
    ...root,
    kids: root.kids.map((k) => replaceLeaf(k, leafId, replacement)),
  }
}

/** Cut a region across a stroke into two parts along its dominant axis. */
export function cut(
  tree: Node,
  W: number,
  H: number,
  stroke: Point[],
): { tree: Node } | { reject: string; line?: Line } {
  const info = inspectCut(tree, W, H, stroke)
  if (!info) {
    return { reject: 'Draw inside a region.' }
  }
  if (info.bad) {
    return { reject: info.bad, line: info.line }
  }

  const { leaf, dir, frac } = info
  const keepFirst = frac >= 0.5
  const fresh = zone(tree)
  const a: Node = keepFirst ? leaf.node : fresh
  const b: Node = keepFirst ? fresh : leaf.node
  const splitNode: Split = {
    type: 'split',
    dir,
    kids: [a, b],
    sizes: [frac, 1 - frac],
  }

  const cloned = cloneNode(tree)
  const replaced = replaceLeaf(cloned, leaf.node.id, splitNode)
  return { tree: normalize(replaced) }
}

/** Collect all gutter dividers in a tree as line coordinates. */
export function sketchLines(tree: Node, W: number, H: number): SketchLine[] {
  const placed = sketchLayout(tree, W, H)
  const lines: SketchLine[] = []

  placed.forEach(({ node, r }) => {
    if (node.type === 'zone') return
    const row = node.dir === 'row'
    const along = (row ? r.w : r.h) - GUTTER * (node.kids.length - 1)
    let at = row ? r.x : r.y
    for (let i = 0; i < node.kids.length - 1; i++) {
      at += along * node.sizes[i] + GUTTER / 2
      const line: Line = row
        ? { x1: at, y1: r.y, x2: at, y2: r.y + r.h }
        : { x1: r.x, y1: at, x2: r.x + r.w, y2: at }
      const A = node.kids[i]
      const B = node.kids[i + 1]
      const canErase = A.type === 'zone' && B.type === 'zone'
      lines.push({ split: node, index: i, line, canErase })
      at += GUTTER / 2
    }
  })
  return lines
}

function distanceToLine(pt: Point, line: Line): number {
  if (line.x1 === line.x2) {
    const minY = Math.min(line.y1, line.y2)
    const maxY = Math.max(line.y1, line.y2)
    const dx = Math.abs(pt.x - line.x1)
    if (pt.y >= minY - 8 && pt.y <= maxY + 8) return dx
    const dy = pt.y < minY ? minY - pt.y : pt.y - maxY
    return Math.hypot(dx, dy)
  } else {
    const minX = Math.min(line.x1, line.x2)
    const maxX = Math.max(line.x1, line.x2)
    const dy = Math.abs(pt.y - line.y1)
    if (pt.x >= minX - 8 && pt.x <= maxX + 8) return dy
    const dx = pt.x < minX ? minX - pt.x : pt.x - maxX
    return Math.hypot(dx, dy)
  }
}

function findSplitPath(root: Node, target: Split, path: number[] = []): number[] | null {
  if (root === target) return path
  if (root.type === 'zone') return null
  for (let i = 0; i < root.kids.length; i++) {
    const p = findSplitPath(root.kids[i], target, [...path, i])
    if (p) return p
  }
  return null
}

/** Erase the divider line at `at`, merging its adjacent regions. */
export function erase(tree: Node, at: Point, W: number, H: number): Node | null {
  const lines = sketchLines(tree, W, H)
  if (!lines.length) return null

  let best: SketchLine | null = null
  let bestDist = Infinity

  for (const sl of lines) {
    const d = distanceToLine(at, sl.line)
    if (d < bestDist) {
      bestDist = d
      best = sl
    }
  }

  if (!best || bestDist > 20) return null
  if (!best.canErase) return null

  const path = findSplitPath(tree, best.split)
  if (!path) return null

  const cloned = cloneNode(tree)
  let current: Node = cloned
  for (let i = 0; i < path.length; i++) {
    current = (current as Split).kids[path[i]]
  }
  const s = current as Split
  const targetIndex = best.index
  const A = s.kids[targetIndex]
  const B = s.kids[targetIndex + 1]
  const keep = (A.type === 'zone' && A.id && findZone(tree, A.id)) ? A : B
  s.sizes.splice(targetIndex, 2, s.sizes[targetIndex] + s.sizes[targetIndex + 1])
  s.kids.splice(targetIndex, 2, keep)

  return normalize(cloned)
}

function resolveRect(rects: unknown, node: Node, id: string): Rect | undefined {
  if (!rects) return undefined
  if (rects instanceof Map) {
    if (rects.has(id)) return rects.get(id)
    if (rects.has(node)) return rects.get(node)
    for (const [k, v] of rects.entries()) {
      if (k && typeof k === 'object' && (k as Zone).id === id) return v
    }
  } else if (Array.isArray(rects)) {
    const item = rects.find((p) => p && ((p.node as Zone)?.id === id || p.node === node || p.n?.id === id || p.n === node))
    if (item) return item.r ?? item.rect
  } else if (typeof rects === 'object') {
    return (rects as Record<string, Rect>)[id]
  }
  return undefined
}

function overlapArea(r1?: Rect, r2?: Rect): number {
  if (!r1 || !r2) return 0
  const ox = Math.max(0, Math.min(r1.x + r1.w, r2.x + r2.w) - Math.max(r1.x, r2.x))
  const oy = Math.max(0, Math.min(r1.y + r1.h, r2.y + r2.h) - Math.max(r1.y, r2.y))
  return ox * oy
}

/** Assign content to new layout regions based on geometric overlap with old zones. */
export function assign(
  oldTree: Node,
  oldRects: unknown,
  newTree: Node,
  newRects?: unknown,
): { tree: Node; leftover: Zone[] } {
  const oldZones = zones(oldTree)
  const oldZoneMap = new Map(oldZones.map((z) => [z.id, z]))

  const oldRectMap = new Map<string, Rect | undefined>()
  oldZones.forEach((z) => {
    oldRectMap.set(z.id, resolveRect(oldRects, z, z.id))
  })

  let placedNew: { node: Zone; r?: Rect }[]
  if (Array.isArray(newRects) && newRects.length && (newRects[0].node || newRects[0].n)) {
    placedNew = newRects
      .filter((p) => (p.node ?? p.n)?.type === 'zone')
      .map((p) => ({ node: p.node ?? p.n, r: p.r ?? p.rect }))
  } else {
    const newZonesList = zones(newTree)
    placedNew = newZonesList.map((z) => ({
      node: z,
      r: resolveRect(newRects, z, z.id),
    }))
    if (placedNew.some((p) => !p.r)) {
      let maxW = 0
      let maxH = 0
      for (const r of oldRectMap.values()) {
        if (r) {
          maxW = Math.max(maxW, r.x + r.w)
          maxH = Math.max(maxH, r.y + r.h)
        }
      }
      const layout = sketchLayout(newTree, maxW || 1200, maxH || 800)
      placedNew = layout
        .filter((p): p is { node: Zone; r: Rect } => p.node.type === 'zone')
        .map((p) => ({ node: p.node, r: p.r }))
    }
  }

  const used = new Set<string>()
  const assigned = new Map<string, Zone | null>()

  // Pass 1: Retain content if the region carried an old zone's id and overlaps it
  placedNew.forEach((p) => {
    if (p.node.id && oldZoneMap.has(p.node.id) && !used.has(p.node.id)) {
      const oz = oldZoneMap.get(p.node.id)!
      const ozR = oldRectMap.get(oz.id)
      if (overlapArea(p.r, ozR) > 0) {
        used.add(oz.id)
        assigned.set(p.node.id, oz)
      }
    }
  })

  // Pass 2: Remaining regions matched to free old zones by maximum overlap area
  const unassigned = placedNew.filter((p) => !assigned.has(p.node.id))
  unassigned.sort((a, b) => ((b.r?.w ?? 0) * (b.r?.h ?? 0)) - ((a.r?.w ?? 0) * (a.r?.h ?? 0)))

  unassigned.forEach((p) => {
    let bestZone: Zone | null = null
    let maxOverlap = 0

    for (const oz of oldZones) {
      if (used.has(oz.id)) continue
      const ozR = oldRectMap.get(oz.id)
      const ov = overlapArea(p.r, ozR)
      if (ov > maxOverlap) {
        maxOverlap = ov
        bestZone = oz
      }
    }

    if (bestZone && maxOverlap > 0) {
      used.add(bestZone.id)
      assigned.set(p.node.id, bestZone)
    } else {
      assigned.set(p.node.id, null)
    }
  })

  const leftover = oldZones.filter((oz) => !used.has(oz.id))

  function rebuild(n: Node): Node {
    if (n.type === 'zone') {
      const match = assigned.get(n.id)
      if (match) {
        return { ...match }
      }
      return zone(oldTree)
    }
    return {
      ...n,
      kids: n.kids.map(rebuild),
      sizes: [...n.sizes],
    }
  }

  const rebuilt = rebuild(newTree)
  return { tree: normalize(rebuilt), leftover }
}
