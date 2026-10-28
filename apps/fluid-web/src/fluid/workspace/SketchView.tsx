/* THE VISUAL LAYOUT SKETCHER OVERLAY (DESIGN.md section 5)
 *
 * Starts from the current layout, draws regions and lines on SVG.
 * Pointer strokes draw a dividing line (red with reason when rejected).
 * Clicking a line erases it and merges the two adjacent sides.
 * Enter applies; Escape cancels; Undo line steps back.
 */

import { useState, useRef, useEffect, useMemo, type ReactElement } from 'react'
import { createRoot } from 'react-dom/client'
import type { Node, Zone, Rect } from './tree'
import { freshId, zones, findZone } from './tree'
import {
  sketchLayout,
  sketchLines,
  inspectCut,
  cut,
  erase,
  assign,
  type Point,
  type Line,
} from './sketch'
import './sketch.css'

export interface SketchProps {
  tree: Node
  W: number
  H: number
  onApply: (tree: Node, leftover: Zone[]) => void
  onClose: () => void
}

export default function Sketch({
  tree,
  W,
  H,
  onApply,
  onClose,
}: SketchProps): ReactElement {
  const containerRef = useRef<HTMLDivElement>(null)
  const [currentTree, setCurrentTree] = useState<Node>(() => tree)
  const [history, setHistory] = useState<Node[]>([])
  const [msg, setMsg] = useState<string>('')
  const [stroke, setStroke] = useState<Point[] | null>(null)
  const [guide, setGuide] = useState<(Line & { bad?: string; sizes?: [number, number] }) | null>(null)
  const [readoutPos, setReadoutPos] = useState<Point | null>(null)

  const activeW = W > 0 ? W : 1200
  const activeH = H > 0 ? H : 800

  // Snapshot original zone rectangles for geometric matching
  const oldRects = useMemo(() => {
    const orig = sketchLayout(tree, activeW, activeH)
    return new Map<string, Rect>(
      orig.filter((p) => p.node.type === 'zone').map((p) => [(p.node as Zone).id, p.r]),
    )
  }, [tree, activeW, activeH])

  const layout = useMemo(
    () => sketchLayout(currentTree, activeW, activeH),
    [currentTree, activeW, activeH],
  )

  const lines = useMemo(
    () => sketchLines(currentTree, activeW, activeH),
    [currentTree, activeW, activeH],
  )

  // Live preview of what each region will show
  const preview = useMemo(
    () => assign(tree, oldRects, currentTree, layout),
    [tree, oldRects, currentTree, layout],
  )

  const previewZoneMap = useMemo(() => {
    const map = new Map<string, Zone>()
    zones(preview.tree).forEach((z) => map.set(z.id, z))
    return map
  }, [preview])

  const handleUndo = () => {
    if (history.length === 0) return
    const prev = history[history.length - 1]
    setHistory((h) => h.slice(0, -1))
    setCurrentTree(prev)
    setMsg('')
    setGuide(null)
  }

  const handleBlank = () => {
    setHistory((h) => [...h, currentTree])
    const firstZone = zones(tree)[0]
    setCurrentTree({
      type: 'zone',
      id: freshId('z'),
      show: firstZone?.show ?? 'objects',
      name: firstZone?.name ?? 'Stage',
    })
    setMsg('')
    setGuide(null)
  }

  const handleApply = () => {
    const { tree: finalTree, leftover } = assign(tree, oldRects, currentTree, layout)
    onApply(finalTree, leftover)
    onClose()
  }

  const handleErase = (line: Line) => {
    const mid: Point = { x: (line.x1 + line.x2) / 2, y: (line.y1 + line.y2) / 2 }
    const res = erase(currentTree, mid, activeW, activeH)
    if (res) {
      setHistory((h) => [...h, currentTree])
      setCurrentTree(res)
      setMsg('')
      setGuide(null)
    } else {
      setMsg('Erase the lines inside first: one line at a time.')
      setTimeout(() => setMsg(''), 1200)
    }
  }

  // Keyboard navigation: Enter applies, Escape cancels, Ctrl+Z undoes
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        e.stopPropagation()
        onClose()
      } else if (e.key === 'Enter') {
        e.preventDefault()
        e.stopPropagation()
        handleApply()
      } else if ((e.ctrlKey || e.metaKey) && e.key === 'z') {
        e.preventDefault()
        handleUndo()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [currentTree, history, layout, tree, oldRects])

  const getPt = (e: React.PointerEvent): Point => {
    if (!containerRef.current) return { x: e.clientX, y: e.clientY }
    const rect = containerRef.current.getBoundingClientRect()
    return { x: e.clientX - rect.left, y: e.clientY - rect.top }
  }

  const onPointerDown = (e: React.PointerEvent) => {
    if (e.button !== 0) return
    const pt = getPt(e)
    setStroke([pt])
    setReadoutPos(pt)
    try {
      ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
    } catch (_) {
      /* synthetic or test */
    }
  }

  const onPointerMove = (e: React.PointerEvent) => {
    if (!stroke) return
    const pt = getPt(e)
    const next = [...stroke, pt]
    setStroke(next)
    setReadoutPos(pt)

    if (next.length > 3) {
      const insp = inspectCut(currentTree, activeW, activeH, next)
      if (insp) {
        setGuide({ ...insp.line, bad: insp.bad, sizes: insp.sizes })
      } else {
        setGuide(null)
      }
    }
  }

  const onPointerUp = () => {
    if (!stroke) return
    if (stroke.length > 3) {
      const res = cut(currentTree, activeW, activeH, stroke)
      if ('tree' in res) {
        setHistory((h) => [...h, currentTree])
        setCurrentTree(res.tree)
        setMsg('')
        setGuide(null)
      } else {
        setMsg(res.reject)
        if (res.line) {
          setGuide({ ...res.line, bad: res.reject })
          setTimeout(() => {
            setGuide(null)
            setMsg('')
          }, 800)
        }
      }
    } else {
      setMsg('')
      setGuide(null)
    }
    setStroke(null)
    setReadoutPos(null)
  }

  const leafNodes = layout.filter((p): p is { node: Zone; r: Rect } => p.node.type === 'zone')

  return (
    <div
      ref={containerRef}
      className="sketch"
      role="application"
      aria-label="Layout sketcher: draw straight lines to divide; Enter applies; Escape cancels"
      tabIndex={0}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      style={{ width: activeW, height: activeH }}
    >
      <div className="sk-hud" onPointerDown={(e) => e.stopPropagation()}>
        <b>Sketch</b>
        <span>Draw a straight line across a region · click a line to erase</span>
        {msg && <span className="msg">{msg}</span>}
        <button type="button" onClick={handleUndo} disabled={history.length === 0}>
          Undo line
        </button>
        <button type="button" onClick={handleBlank}>
          Start blank
        </button>
        <button type="button" onClick={onClose}>
          Cancel
        </button>
        <button type="button" className="apply" onClick={handleApply}>
          Apply
        </button>
      </div>

      <svg width={activeW} height={activeH}>
        {/* Sketched regions */}
        {leafNodes.map((p) => {
          const z = previewZoneMap.get(p.node.id) ?? findZone(tree, p.node.id)
          const name = z ? z.name ?? z.show : 'New section'
          return (
            <g key={p.node.id}>
              <rect
                className="sk-region"
                x={p.r.x + 1}
                y={p.r.y + 1}
                width={Math.max(0, p.r.w - 2)}
                height={Math.max(0, p.r.h - 2)}
                rx={10}
              />
              <text className="sk-label" x={p.r.x + 14} y={p.r.y + 24}>
                {name}
              </text>
              <text className="sk-sub" x={p.r.x + 14} y={p.r.y + 42}>
                {`${Math.round(p.r.w)} × ${Math.round(p.r.h)}`}
              </text>
            </g>
          )
        })}

        {/* Divider lines (erasable) */}
        {lines.map((sl, i) => (
          <g key={`line-group-${i}`}>
            <line
              className="sk-hit"
              x1={sl.line.x1}
              y1={sl.line.y1}
              x2={sl.line.x2}
              y2={sl.line.y2}
              onPointerDown={(e) => {
                e.stopPropagation()
                handleErase(sl.line)
              }}
            >
              <title>Click to erase this line</title>
            </line>
            <line
              className="sk-line"
              x1={sl.line.x1}
              y1={sl.line.y1}
              x2={sl.line.x2}
              y2={sl.line.y2}
            />
          </g>
        ))}

        {/* Dynamic stroke ink */}
        {stroke && stroke.length > 1 && (
          <polyline
            className="sk-ink"
            points={stroke.map((p) => `${p.x},${p.y}`).join(' ')}
          />
        )}

        {/* Snapped guide line */}
        {guide && (
          <line
            className={`sk-guide${guide.bad ? ' bad' : ''}`}
            x1={guide.x1}
            y1={guide.y1}
            x2={guide.x2}
            y2={guide.y2}
          />
        )}
      </svg>

      {/* Floating readout tooltip while cutting */}
      {guide && !guide.bad && guide.sizes && readoutPos && (
        <div
          className="sk-readout"
          style={{ left: `${readoutPos.x}px`, top: `${readoutPos.y}px` }}
        >
          {`${Math.round(guide.sizes[0])} px | ${Math.round(guide.sizes[1])} px`}
        </div>
      )}
    </div>
  )
}

/** Open the sketch overlay dynamically in the workspace container. */
export function openSketch(opts: {
  tree: Node
  W?: number
  H?: number
  onApply: (tree: Node, leftover: Zone[]) => void
  onClose?: () => void
}): () => void {
  const host =
    document.querySelector('.wt[data-page-tree="this-post"]') ??
    document.querySelector('.wt') ??
    document.querySelector('.fx-main') ??
    document.body

  const rect = host.getBoundingClientRect()
  const W = opts.W ?? (rect.width || window.innerWidth)
  const H = opts.H ?? (rect.height || window.innerHeight)

  const container = document.createElement('div')
  container.className = 'sketch-host'
  host.appendChild(container)
  const root = createRoot(container)

  let closed = false
  const cleanup = () => {
    if (closed) return
    closed = true
    root.unmount()
    container.remove()
    opts.onClose?.()
  }

  root.render(
    <Sketch
      tree={opts.tree}
      W={W}
      H={H}
      onApply={(newTree, leftover) => {
        opts.onApply(newTree, leftover)
        cleanup()
      }}
      onClose={cleanup}
    />,
  )

  return cleanup
}
