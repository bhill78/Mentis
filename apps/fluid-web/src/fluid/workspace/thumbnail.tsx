/* Mini SVG diagram thumbnails of layout trees (Fluid Arrange sheet).
 * Pure geometry calculation and compact SVG renderer. */

export interface ThumbRect {
  x: number
  y: number
  w: number
  h: number
  name?: string
  id?: string
}

/** Compute rectangles for a layout tree inside given bounds. Pure function. */
export function layoutThumbRects(
  input: unknown,
  bounds: { w: number; h: number } = { w: 60, h: 40 },
  gap = 2,
): ThumbRect[] {
  const { w, h } = bounds
  if (!input || typeof input !== 'object') {
    return [{ x: 0, y: 0, w, h }]
  }

  // If a layout object was passed with .tree
  const rawNode = ('tree' in input && (input as { tree: unknown }).tree) ? (input as { tree: unknown }).tree : input
  if (!rawNode || typeof rawNode !== 'object') {
    return [{ x: 0, y: 0, w, h }]
  }

  function walk(node: unknown, rx: number, ry: number, rw: number, rh: number): ThumbRect[] {
    if (!node || typeof node !== 'object') {
      return [{ x: rx, y: ry, w: rw, h: rh }]
    }
    const o = node as Record<string, unknown>
    const isSplit = o.type === 'split' || ('kids' in o && Array.isArray(o.kids))
    if (!isSplit) {
      return [{
        x: Math.round(rx),
        y: Math.round(ry),
        w: Math.max(1, Math.round(rw)),
        h: Math.max(1, Math.round(rh)),
        ...(typeof o.name === 'string' ? { name: o.name } : {}),
        ...(typeof o.id === 'string' ? { id: o.id } : {}),
      }]
    }

    const dir = o.dir === 'col' ? 'col' : 'row'
    const kids = Array.isArray(o.kids) ? o.kids : []
    if (kids.length === 0) {
      return [{ x: rx, y: ry, w: rw, h: rh }]
    }
    if (kids.length === 1) {
      return walk(kids[0], rx, ry, rw, rh)
    }

    const sizes = Array.isArray(o.sizes) && o.sizes.length === kids.length && o.sizes.every((s: unknown) => typeof s === 'number' && s > 0)
      ? (o.sizes as number[])
      : kids.map(() => 1 / kids.length)

    const sum = sizes.reduce((a, b) => a + b, 0) || 1
    const norm = sizes.map((s) => s / sum)

    const totalGaps = gap * (kids.length - 1)
    const out: ThumbRect[] = []

    if (dir === 'row') {
      const availW = Math.max(0, rw - totalGaps)
      let curX = rx
      for (let i = 0; i < kids.length; i++) {
        const kidW = i === kids.length - 1 ? (rx + rw - curX) : availW * norm[i]
        out.push(...walk(kids[i], curX, ry, kidW, rh))
        curX += kidW + gap
      }
    } else {
      const availH = Math.max(0, rh - totalGaps)
      let curY = ry
      for (let i = 0; i < kids.length; i++) {
        const kidH = i === kids.length - 1 ? (ry + rh - curY) : availH * norm[i]
        out.push(...walk(kids[i], rx, curY, rw, kidH))
        curY += kidH + gap
      }
    }
    return out
  }

  return walk(rawNode, 0, 0, w, h)
}

/** Mini SVG diagram thumbnail of a layout's tree. */
export function LayoutThumb({ tree, width = 56, height = 36 }: { tree: unknown; width?: number; height?: number }) {
  const rects = layoutThumbRects(tree, { w: width, h: height }, 2)
  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className="wk-thumb-svg"
      aria-hidden="true"
    >
      {rects.map((r, i) => (
        <rect
          key={i}
          x={r.x + 0.5}
          y={r.y + 0.5}
          width={Math.max(1, r.w - 1)}
          height={Math.max(1, r.h - 1)}
          rx={2}
          className="wk-thumb-rect"
        />
      ))}
    </svg>
  )
}
