/* EXPERIMENTAL: diagram and whiteboard -- two surfaces over ONE body grammar.

   The author writes nodes and edges, never positions:

     order: "Order received" kind=start
     check: "In stock?" kind=decision detail="Look in the stock table"
     order -> check
     check -> ship "yes"

   A diagram lays those lines out (layered, automatic) for a person to READ:
   select a box, follow what leads to it and from it, leave a note. A
   whiteboard seeds a board from the very same lines for a person to RESHAPE:
   drag cards, edit their text, add cards and links. The reader (parseGraph)
   and the layering (layered) are shared on purpose, so the gallery can show
   one body both ways. What differs is what state MEANS: notes on a fixed
   structure, versus changes to the structure itself.                       */
import './graph.css'
import { useEffect, useId, useLayoutEffect, useRef, useState, type ReactNode, type RefObject } from 'react'
import type { RichProps, Size, TypeDef } from '../api'
import { PALETTE, q } from '../util'
import { diagramSpec, whiteboardSpec, type GEdge, type GNode, type Graph } from '../spec/graph'

export { GRAMMAR, KINDS, parseGraph, type GEdge, type GNode, type Graph, type Kind } from '../spec/graph'

/* ------------------------------------------------------ shared small tools */

/** The width of an element, kept current. */
export function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null)
  const [w, setW] = useState(0)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    setW(el.clientWidth)
    const ro = new ResizeObserver((es) => setW(es[0].contentRect.width))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  return [ref, w] as const
}

/** A wheel listener allowed to preventDefault (React's onWheel is passive). */
export function useWheel(ref: RefObject<HTMLElement | null>, fn: (e: WheelEvent) => void) {
  const f = useRef(fn)
  useLayoutEffect(() => { f.current = fn })
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const h = (e: WheelEvent) => f.current(e)
    el.addEventListener('wheel', h, { passive: false })
    return () => el.removeEventListener('wheel', h)
  }, [ref])
}

export const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v))

/** Drop empty parts of a state object; nothing left means "back to the source". */
export function tidy<S extends object>(s: S): S | undefined {
  const o: Record<string, unknown> = {}
  for (const [k, v] of Object.entries(s as Record<string, unknown>)) {
    if (v === undefined || v === null) continue
    if (Array.isArray(v) ? !v.length : typeof v === 'object' && !Object.keys(v as object).length) continue
    o[k] = v
  }
  return Object.keys(o).length ? (o as S) : undefined
}

/** Split a label into at most `lines` lines of about `width` characters. */
function wrap(s: string, width: number, lines: number): string[] {
  const out: string[] = []
  let cur = ''
  for (const word of s.split(/\s+/).filter(Boolean)) {
    if (cur && (cur + ' ' + word).length > width) { out.push(cur); cur = word }
    else cur = cur ? cur + ' ' + word : word
  }
  if (cur) out.push(cur)
  if (out.length > lines) { out.length = lines; out[lines - 1] = out[lines - 1].slice(0, width - 1) + '…' }
  return out.map((l) => (l.length > width ? l.slice(0, width - 1) + '…' : l))
}

/* ------------------------------------------------------ zoom and pan pane */

export interface View { k: number; x: number; y: number }

/** A fixed-height window onto a larger drawing: drag the background to pan,
    Ctrl/⌘+wheel or the buttons to zoom, Fit to see it all. `null` = fitted. */
export function Pane({ w, h, max, view, setView, onBackground, children }: {
  w: number; h: number; max: number
  view: View | null; setView(v: View | null): void
  onBackground?(): void
  children: (k: number) => ReactNode
}) {
  const [ref, cw] = useWidth<HTMLDivElement>()
  const byWidth = cw ? clamp((cw - 16) / w, 0.2, 1) : 1
  const height = clamp(h * byWidth + 16, 140, max)
  const fitK = clamp(Math.min(byWidth, (height - 16) / h), 0.2, 1)
  const fit: View = { k: fitK, x: Math.max(8, (cw - w * fitK) / 2), y: 8 }
  const v = view ?? fit
  const drag = useRef<{ x: number; y: number; vx: number; vy: number; moved: boolean } | null>(null)
  const zoomAt = (f: number, px: number, py: number) => {
    const k = clamp(v.k * f, 0.2, 3)
    setView({ k, x: px - (px - v.x) * (k / v.k), y: py - (py - v.y) * (k / v.k) })
  }
  useWheel(ref, (e) => {
    if (!(e.ctrlKey || e.metaKey)) return
    e.preventDefault()
    const r = ref.current!.getBoundingClientRect()
    zoomAt(e.deltaY < 0 ? 1.15 : 1 / 1.15, e.clientX - r.left, e.clientY - r.top)
  })
  return (
    <div className="rb-dg-wrap">
      <div className="rb-row rb-dg-tools">
        <button className="btn quiet" title="Zoom out" onClick={() => zoomAt(1 / 1.25, cw / 2, height / 2)}>−</button>
        <button className="btn quiet" title="Zoom in" onClick={() => zoomAt(1.25, cw / 2, height / 2)}>+</button>
        <button className="btn quiet" onClick={() => setView(null)}>Fit</button>
        <span className="rb-muted">{Math.round(v.k * 100)}% · drag the background to pan · Ctrl+wheel zooms</span>
      </div>
      <div
        ref={ref}
        className="rb-dg-pane"
        style={{ height }}
        onPointerDown={(e) => {
          if (e.button !== 0 || (e.target as Element).closest('[data-item]')) return
          drag.current = { x: e.clientX, y: e.clientY, vx: v.x, vy: v.y, moved: false }
          e.currentTarget.setPointerCapture(e.pointerId)
        }}
        onPointerMove={(e) => {
          const d = drag.current
          if (!d) return
          const dx = e.clientX - d.x, dy = e.clientY - d.y
          if (!d.moved && Math.hypot(dx, dy) < 4) return
          d.moved = true
          setView({ k: v.k, x: d.vx + dx, y: d.vy + dy })
        }}
        onPointerUp={() => {
          const d = drag.current
          drag.current = null
          if (d && !d.moved) onBackground?.()
        }}
      >
        <div className="rb-dg-stage" style={{ width: w, height: h, transform: `translate(${v.x}px, ${v.y}px) scale(${v.k})` }}>
          {children(v.k)}
        </div>
      </div>
    </div>
  )
}

/* ------------------------------------------------ the shared body grammar */

const nodeLine = (n: GNode) =>
  `${n.id}: ${q(n.label)} kind=${n.kind}${n.group !== undefined ? ` group=${q(n.group)}` : ''}${n.detail !== undefined ? ` detail=${q(n.detail)}` : ''}${n.date !== undefined ? ` date=${q(n.date)}` : ''}${n.author !== undefined ? ` author=${q(n.author)}` : ''}${n.tag !== undefined ? ` tag=${q(n.tag)}` : ''}`
const edgeLine = (e: { from: string; to: string; label?: string }) => `${e.from} -> ${e.to}${e.label ? ' ' + q(e.label) : ''}`

/* ------------------------------------------------------- automatic layout */

export interface Layout {
  layer: Record<string, number>
  /** Position across the flow, in node widths (may be fractional). */
  slot: Record<string, number>
  /** Edges that point back against the flow (they close a cycle). */
  back: Record<string, true>
  lanes: { name: string; at: number; span: number }[]
  order: string[][]
  layers: number
  slots: number
}

/** Layered layout, small and deterministic: break cycles by depth-first
    search, give each node the longest path to it as its layer, then order
    each layer by the average position of its neighbours a few times, keeping
    each group's nodes together in its own lane. Never loops forever. */
export function layered(g: Graph): Layout {
  const ids = g.nodes.map((n) => n.id)
  const decl: Record<string, number> = {}
  ids.forEach((id, i) => (decl[id] = i))
  const out: Record<string, GEdge[]> = {}
  const indeg: Record<string, number> = {}
  ids.forEach((id) => { out[id] = []; indeg[id] = 0 })
  for (const e of g.edges) if (e.from !== e.to) { out[e.from].push(e); indeg[e.to]++ }

  // 1. Cycles: an edge to a node still on the search path points back.
  const back: Record<string, true> = {}
  const mark: Record<string, number> = {}
  const visit = (u: string) => {
    mark[u] = 1
    for (const e of out[u]) {
      if (mark[e.to] === 1) back[e.key] = true
      else if (!mark[e.to]) visit(e.to)
    }
    mark[u] = 2
  }
  const roots = [
    ...g.nodes.filter((n) => n.kind === 'start'),
    ...g.nodes.filter((n) => n.kind !== 'start' && indeg[n.id] === 0),
    ...g.nodes,
  ]
  for (const r of roots) if (!mark[r.id]) visit(r.id)

  // 2. Layers: longest path over the forward edges (now acyclic).
  const fwd = g.edges.filter((e) => e.from !== e.to && !back[e.key])
  const din: Record<string, number> = {}, layer: Record<string, number> = {}
  ids.forEach((id) => { din[id] = 0; layer[id] = 0 })
  fwd.forEach((e) => din[e.to]++)
  const queue = ids.filter((id) => din[id] === 0)
  while (queue.length) {
    const u = queue.shift()!
    for (const e of fwd) if (e.from === u) {
      layer[e.to] = Math.max(layer[e.to], layer[u] + 1)
      if (--din[e.to] === 0) queue.push(e.to)
    }
  }
  const layers = ids.length ? Math.max(...ids.map((id) => layer[id])) + 1 : 1

  // 3. Order within layers: lanes first, then neighbours' average position.
  const laneNames = g.groups.length ? [...g.groups, ...(g.nodes.some((n) => n.group === undefined) ? [''] : [])] : ['']
  const laneOf = (id: string) => Math.max(0, laneNames.indexOf(g.byId[id].group ?? ''))
  const order: string[][] = Array.from({ length: layers }, () => [])
  ids.forEach((id) => order[layer[id]].push(id))
  const pos: Record<string, number> = {}
  const place = () => order.forEach((row) => row.forEach((id, i) => (pos[id] = i)))
  order.forEach((row) => row.sort((x, y) => laneOf(x) - laneOf(y) || decl[x] - decl[y]))
  place()
  for (let it = 0; it < 8; it++) {
    const down = it % 2 === 0
    const seq = down ? order.map((_, i) => i).slice(1) : order.map((_, i) => i).reverse().slice(1)
    for (const li of seq) {
      const bary: Record<string, number> = {}
      for (const id of order[li]) {
        const nb = fwd.filter((e) => (down ? e.to === id : e.from === id)).map((e) => pos[down ? e.from : e.to])
        bary[id] = nb.length ? nb.reduce((s, v) => s + v, 0) / nb.length : pos[id]
      }
      order[li].sort((x, y) => laneOf(x) - laneOf(y) || bary[x] - bary[y] || decl[x] - decl[y])
      place()
    }
  }

  // 4. Slots: each lane is as wide as its busiest layer; rows are centred in it.
  const slot: Record<string, number> = {}
  const lanes: Layout['lanes'] = []
  let at = 0
  laneNames.forEach((name, li) => {
    const per = order.map((row) => row.filter((id) => laneOf(id) === li))
    const span = Math.max(1, ...per.map((r) => r.length))
    per.forEach((r) => r.forEach((id, i) => (slot[id] = at + (span - r.length) / 2 + i)))
    lanes.push({ name, at, span })
    at += span
  })
  return { layer, slot, back, lanes, order, layers, slots: at }
}

/* ------------------------------------------------------------------ diagram */

interface DgState { sel?: string; notes?: Record<string, string> }

const neighbours = (g: Graph, id: string) => ({
  inc: g.edges.filter((e) => e.to === id),
  outg: g.edges.filter((e) => e.from === id),
})

/** Everything upstream (dir=-1) or downstream (dir=1) of a node. */
function reach(g: Graph, id: string, dir: 1 | -1): Set<string> {
  const seen = new Set<string>([id]), todo = [id]
  while (todo.length) {
    const u = todo.pop()!
    for (const e of g.edges) {
      const [a, b] = dir === 1 ? [e.from, e.to] : [e.to, e.from]
      if (a === u && !seen.has(b)) { seen.add(b); todo.push(b) }
    }
  }
  return seen
}

function GitDiagramView(props: RichProps<Graph, DgState>) {
  const { data: g, attrs: a, state, set } = props
  const st = state ?? {}
  const sel = st.sel && g.byId[st.sel] ? st.sel : undefined
  const select = (id: string | undefined) => set(tidy({ ...st, sel: id }))
  const cur = sel ? g.byId[sel] : null
  const [wrap, avail] = useWidth<HTMLDivElement>()

  const declaredGroups = a.groups ? a.groups.split(',').map((s) => s.trim()).filter(Boolean) : []
  const branchSet = new Set<string>()
  declaredGroups.forEach((b) => branchSet.add(b))
  g.nodes.forEach((n) => branchSet.add(n.group || ''))
  const branches = [...branchSet]
  const trackOf: Record<string, number> = {}
  branches.forEach((b, i) => { trackOf[b] = i })

  const commits = [...g.nodes]
  const rowOf: Record<string, number> = {}
  commits.forEach((c, i) => { rowOf[c.id] = i })

  const trackW = 22
  const startX = 20
  const numTracks = Math.max(1, branches.length)
  const graphW = startX + numTracks * trackW + 12

  const listRef = useRef<HTMLDivElement>(null)
  const [rowYs, setRowYs] = useState<number[]>([])

  useLayoutEffect(() => {
    const listEl = listRef.current
    if (!listEl) return
    const measure = () => {
      const listTop = listEl.getBoundingClientRect().top
      const rowEls = listEl.querySelectorAll<HTMLElement>('.rb-git-row')
      if (!rowEls.length) return
      const ys: number[] = []
      rowEls.forEach((el) => {
        const hashEl = el.querySelector<HTMLElement>('.rb-git-hash')
        if (hashEl) {
          const hr = hashEl.getBoundingClientRect()
          ys.push(hr.top + hr.height / 2 - listTop)
        } else {
          const er = el.getBoundingClientRect()
          ys.push(er.top + 16 - listTop)
        }
      })
      setRowYs((prev) => {
        if (prev.length === ys.length && prev.every((v, i) => Math.abs(v - ys[i]) < 0.5)) return prev
        return ys
      })
    }
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(listEl)
    return () => ro.disconnect()
  }, [commits, branches])

  const listColW = Math.max(100, (avail || 640) - graphW - 16)
  const initialYs: number[] = []
  let accumY = 16
  for (const c of commits) {
    const charsPerLine = Math.max(12, Math.floor(listColW / 7.5))
    const msgLines = Math.ceil(c.label.length / charsPerLine)
    const estH = Math.max(52, 24 + msgLines * 18 + 18)
    initialYs.push(accumY + 12)
    accumY += estH
  }

  const getY = (r: number) => rowYs[r] ?? (initialYs[r] ?? (24 + r * 56))
  const lastY = rowYs.length ? rowYs[rowYs.length - 1] : (initialYs[initialYs.length - 1] ?? 60)
  const totalH = Math.max(80, lastY + 36)

  const parentsOf: Record<string, string[]> = {}
  const childrenOf: Record<string, string[]> = {}
  commits.forEach((c) => { parentsOf[c.id] = []; childrenOf[c.id] = [] })
  g.edges.forEach((e) => {
    if (parentsOf[e.to]) parentsOf[e.to].push(e.from)
    if (childrenOf[e.from]) childrenOf[e.from].push(e.to)
  })

  const colour = (t: number) => (branches[t] === '' ? 'var(--text-dim)' : t < 4 ? `var(--rb-chart-${t + 1})` : PALETTE[t % PALETTE.length])

  const trackSpans: { track: number; minRow: number; maxRow: number }[] = branches.map((b, t) => {
    const inTrack = commits.filter((c) => (c.group || '') === b)
    if (!inTrack.length) return { track: t, minRow: 0, maxRow: 0 }
    const rows = inTrack.map((c) => rowOf[c.id])
    return { track: t, minRow: Math.min(...rows), maxRow: Math.max(...rows) }
  })

  const edgeSvg: React.ReactNode[] = []
  g.edges.forEach((e, idx) => {
    const fromNode = g.byId[e.from]
    const toNode = g.byId[e.to]
    if (!fromNode || !toNode) return
    const r1 = rowOf[e.from] ?? 0
    const r2 = rowOf[e.to] ?? 0
    const t1 = trackOf[fromNode.group || ''] ?? 0
    const t2 = trackOf[toNode.group || ''] ?? 0
    const x1 = startX + t1 * trackW
    const y1 = getY(r1)
    const x2 = startX + t2 * trackW
    const y2 = getY(r2)
    const col = colour(t2)
    const isHl = sel !== undefined && (sel === e.from || sel === e.to)

    if (x1 === x2) {
      edgeSvg.push(
        <line
          key={`ge_${idx}`}
          x1={x1}
          y1={y1}
          x2={x2}
          y2={y2}
          stroke={isHl ? 'var(--accent)' : col}
          strokeWidth={isHl ? 3 : 2}
          opacity={isHl ? 1 : 0.75}
        />,
      )
    } else {
      const midY = (y1 + y2) / 2
      const d = `M ${x1} ${y1} C ${x1} ${midY}, ${x2} ${midY}, ${x2} ${y2}`
      edgeSvg.push(
        <path
          key={`ge_${idx}`}
          d={d}
          fill="none"
          stroke={isHl ? 'var(--accent)' : col}
          strokeWidth={isHl ? 3 : 2}
          opacity={isHl ? 1 : 0.75}
        />,
      )
    }
  })

  return (
    <div className="rb-dg rb-git-diagram" ref={wrap}>
      {a.title && <b>{a.title}</b>}
      <div className="rb-git-container" style={{ display: 'flex', flexDirection: 'row', minHeight: totalH }}>
        <div className="rb-git-graph" style={{ width: graphW, flexShrink: 0 }}>
          <svg width={graphW} height={totalH} style={{ display: 'block', overflow: 'visible' }}>
            {trackSpans.map((ts) => {
              if (ts.minRow === ts.maxRow) return null
              const x = startX + ts.track * trackW
              const y1 = getY(ts.minRow)
              const y2 = getY(ts.maxRow)
              return (
                <line
                  key={`track_${ts.track}`}
                  x1={x}
                  y1={y1}
                  x2={x}
                  y2={y2}
                  stroke={colour(ts.track)}
                  strokeWidth={1.5}
                  strokeDasharray="3 3"
                  opacity={0.35}
                />
              )
            })}
            {edgeSvg}
            {commits.map((c) => {
              const r = rowOf[c.id] ?? 0
              const t = trackOf[c.group || ''] ?? 0
              const x = startX + t * trackW
              const y = getY(r)
              const isSel = sel === c.id
              const col = colour(t)
              return (
                <circle
                  key={`dot_${c.id}`}
                  cx={x}
                  cy={y}
                  r={isSel ? 7 : 5}
                  fill={col}
                  stroke={isSel ? 'var(--accent)' : 'var(--surface-raised, #fff)'}
                  strokeWidth={isSel ? 3 : 1.5}
                  style={{ cursor: 'pointer' }}
                  onClick={() => select(isSel ? undefined : c.id)}
                />
              )
            })}
          </svg>
        </div>

        <div ref={listRef} className="rb-git-list" style={{ flexGrow: 1, display: 'flex', flexDirection: 'column' }}>
          {commits.map((c) => {
            const isSel = sel === c.id
            const t = trackOf[c.group || ''] ?? 0
            const col = colour(t)
            const br = c.group || ''
            return (
              <div
                key={`row_${c.id}`}
                className={`rb-git-row ${isSel ? 'rb-git-sel' : ''}`}
                style={{
                  minHeight: 48,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  padding: '4px 8px',
                  borderRadius: 'var(--radius)',
                  cursor: 'pointer',
                  background: isSel ? 'var(--wash)' : undefined,
                }}
                tabIndex={0}
                role="button"
                aria-pressed={isSel}
                aria-label={`Commit ${c.id}: ${c.label}${br ? ` on ${br}` : ' (ungrouped)'}${c.author ? ` by ${c.author}` : ''}`}
                onClick={() => select(isSel ? undefined : c.id)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault()
                    select(isSel ? undefined : c.id)
                  }
                }}
              >
                <code className="rb-git-hash" style={{ fontWeight: 600, fontSize: 12, color: col }}>
                  {c.id}
                </code>
                {c.tag && (
                  <span className="rb-git-tag" style={{ fontSize: 11, padding: '1px 5px', borderRadius: 3, background: 'var(--attention-soft)', border: '1px solid var(--line-strong)' }}>
                    🏷 {c.tag}
                  </span>
                )}
                {br && (
                  <span className="rb-git-branch" style={{ fontSize: 11, padding: '1px 5px', borderRadius: 3, border: `1px solid ${col}`, color: col }}>
                    {br}
                  </span>
                )}
                <span className="rb-git-msg" style={{ fontWeight: isSel ? 600 : 'normal', fontSize: 13, flexGrow: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {c.label}
                </span>
                <span className="rb-git-meta" style={{ fontSize: 11, color: 'var(--text-dim)', flexShrink: 0 }}>
                  {c.author ? `${c.author} · ` : ''}{c.date ?? ''}
                </span>
              </div>
            )
          })}
        </div>
      </div>

      {cur && (
        <div className="rb-dg-detail rb-git-detail" style={{ marginTop: 8 }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
            <b>{cur.label}</b>
            <code style={{ fontSize: 12, color: colour(trackOf[cur.group || ''] ?? 0) }}>{cur.id}</code>
            <span className="rb-muted">({cur.group || 'ungrouped'})</span>
          </div>
          {cur.author && <p className="rb-muted">Author: {cur.author}</p>}
          {cur.date && <p className="rb-muted">Date: {cur.date}</p>}
          {cur.detail && <p>{cur.detail}</p>}
          <div className="rb-dg-cols" style={{ marginTop: 6 }}>
            <div>
              <div className="rb-lbl">Parents</div>
              {parentsOf[cur.id]?.length ? (
                <ul>
                  {parentsOf[cur.id].map((pid) => (
                    <li key={pid}>
                      <button className="rb-link" onClick={() => select(pid)}>
                        {pid} {g.byId[pid] ? `— “${g.byId[pid].label}”` : ''}
                      </button>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="rb-muted">no parent declared</p>
              )}
            </div>
            <div>
              <div className="rb-lbl">Children</div>
              {childrenOf[cur.id]?.length ? (
                <ul>
                  {childrenOf[cur.id].map((cid) => (
                    <li key={cid}>
                      <button className="rb-link" onClick={() => select(cid)}>
                        {cid} {g.byId[cid] ? `— “${g.byId[cid].label}”` : ''}
                      </button>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="rb-muted">no child declared</p>
              )}
            </div>
          </div>
          <div className="rb-lbl" style={{ marginTop: 8 }}>Your note (state; the Markdown is unchanged)</div>
          <textarea
            className="rb-dg-note"
            value={st.notes?.[cur.id] ?? ''}
            onChange={(e) => {
              const notes = { ...(st.notes ?? {}) }
              if (e.target.value) notes[cur.id] = e.target.value
              else delete notes[cur.id]
              set(tidy({ ...st, notes }))
            }}
          />
        </div>
      )}
    </div>
  )
}

/* SIZED (L5). A workspace says what size a copy is drawn at, and the pane's
   height follows it: compact a short window onto the drawing, large a tall
   one, medium the conversation's own. Without a size it is exactly today's. */
const paneMax = (mode: 'inline' | 'pin', size: Size | undefined, inline: number) =>
  mode === 'pin' ? inline - 200 : size === 'compact' ? 280 : size === 'large' ? 760 : inline

function DiagramView(props: RichProps<Graph, DgState>) {
  const v = props.attrs.view === 'git' ? <GitDiagramView {...props} /> : <FlowDiagramView {...props} />
  return props.size ? <div className="rb-dg-sized" data-size={props.size}>{v}</div> : v
}

function FlowDiagramView(props: RichProps<Graph, DgState>) {
  const { data: g, attrs: a, state, set, mode } = props
  const [view, setView] = useState<View | null>(null)
  const [path, setPath] = useState(false)
  const uid = useId().replace(/[^A-Za-z0-9_-]/g, '')
  const L = layered(g)
  const st = state ?? {}
  const sel = st.sel && g.byId[st.sel] ? st.sel : undefined
  const select = (id: string | undefined) => set(tidy({ ...st, sel: id }))

  // Geometry: p runs along the flow, s across it; `xy` turns them into x, y.
  const down = a.direction !== 'right'
  const NW = 150, NH = 48, PAD = 24
  const lanesShown = g.groups.length > 0
  const HEAD = lanesShown ? (down ? 28 : 110) : 0
  const P = down ? NH + 56 : NW + 70, S = down ? NW + 36 : NH + 32
  const lp = down ? NH : NW, ls = down ? NW : NH
  const pOf = (id: string) => PAD + HEAD + L.layer[id] * P
  const sOf = (id: string) => PAD + L.slot[id] * S
  const xy = (p: number, s: number): [number, number] => (down ? [s, p] : [p, s])
  const lenP = PAD * 2 + HEAD + (L.layers - 1) * P + lp
  const lenS = PAD * 2 + (L.slots - 1) * S + ls + 70
  const [w, h] = down ? [lenS, lenP] : [lenP, lenS]

  // What to light up around the selection.
  let lit: Set<string> | null = null
  const litE = new Set<string>()
  if (sel) {
    if (!path) {
      lit = new Set([sel])
      for (const e of g.edges) if (e.from === sel || e.to === sel) { lit.add(e.from); lit.add(e.to); litE.add(e.key) }
    } else {
      const up = reach(g, sel, -1), dn = reach(g, sel, 1)
      lit = new Set([...up, ...dn])
      for (const e of g.edges) if ((up.has(e.from) && up.has(e.to)) || (dn.has(e.from) && dn.has(e.to))) litE.add(e.key)
    }
  }

  const bez = (pts: [number, number][], t: number): [number, number] => {
    const m = 1 - t
    const c = [m * m * m, 3 * m * m * t, 3 * m * t * t, t * t * t]
    return [0, 1].map((k) => pts.reduce((s, p, i) => s + p[k] * c[i], 0)) as [number, number]
  }
  let backN = 0
  const edges = g.edges.map((e) => {
    const p0 = pOf(e.from), s0 = sOf(e.from), p1 = pOf(e.to), s1 = sOf(e.to)
    let ps: [number, number][] // four control points in (p, s)
    if (e.from === e.to) {
      ps = [[p0 + lp * 0.3, s0 + ls], [p0 + lp * 0.1, s0 + ls + 40], [p0 + lp * 0.9, s0 + ls + 40], [p0 + lp * 0.7, s0 + ls]]
    } else if (L.layer[e.to] > L.layer[e.from]) {
      const mid = (p0 + lp + p1) / 2
      ps = [[p0 + lp, s0 + ls / 2], [mid, s0 + ls / 2], [mid, s1 + ls / 2], [p1, s1 + ls / 2]]
    } else if (L.layer[e.to] === L.layer[e.from] && !L.back[e.key]) {
      const [a0, a1] = s1 > s0 ? [s0 + ls, s1] : [s0, s1 + ls]
      ps = [[p0 + lp / 2, a0], [p0 + lp / 2 - 24, (a0 + a1) / 2], [p1 + lp / 2 - 24, (a0 + a1) / 2], [p1 + lp / 2, a1]]
    } else {
      const out = Math.max(s0, s1) + ls + 30 + 12 * (backN++ % 3)
      ps = [[p0 + lp / 2, s0 + ls], [p0 + lp / 2, out], [p1 + lp / 2, out], [p1 + lp / 2, s1 + ls]]
    }
    const pts = ps.map(([p, s]) => xy(p, s))
    const d = `M${pts[0]} C${pts[1]} ${pts[2]} ${pts[3]}`
    const [lx, ly] = bez(pts, 0.5)
    const on = litE.has(e.key)
    const note = g.byId[e.from].kind === 'note' || g.byId[e.to].kind === 'note'
    const cls = 'rb-dg-edge' + (on ? ' rb-dg-hl' : lit ? ' rb-dg-dim' : '') + (note ? ' rb-dg-dash' : '')
    return (
      <g key={e.key} className={cls}>
        <path d={d} markerEnd={`url(#${uid}-${on ? 'h' : 'a'})`} />
        {e.label && <text x={lx} y={ly + 4} textAnchor="middle" className="rb-dg-elabel">{e.label}</text>}
      </g>
    )
  })

  const nodes = g.nodes.map((n) => {
    const [x, y] = xy(pOf(n.id), sOf(n.id))
    const lines = wrap(n.label, n.kind === 'decision' ? 16 : 20, 2)
    const cls = `rb-dg-node rb-dg-k-${n.kind}` + (n.id === sel ? ' rb-dg-sel' : lit && !lit.has(n.id) ? ' rb-dg-dim' : '')
    let shape: ReactNode
    if (n.kind === 'decision') shape = <polygon points={`${NW / 2},0 ${NW},${NH / 2} ${NW / 2},${NH} 0,${NH / 2}`} />
    else if (n.kind === 'note') shape = <path d={`M0,0 H${NW - 12} L${NW},12 V${NH} H0 Z`} />
    else if (n.kind === 'end') shape = <><rect width={NW} height={NH} rx={NH / 2} /><rect x={4} y={4} width={NW - 8} height={NH - 8} rx={NH / 2 - 4} className="rb-dg-inner" /></>
    else shape = <rect width={NW} height={NH} rx={n.kind === 'start' ? NH / 2 : 6} />
    return (
      <g key={n.id} data-item="" className={cls} transform={`translate(${x} ${y})`} onClick={() => select(n.id === sel ? undefined : n.id)}>
        <title>{n.label + (n.detail ? '\n' + n.detail : '')}</title>
        {shape}
        {lines.map((l, i) => (
          <text key={i} x={NW / 2} y={NH / 2 + 4 + (i - (lines.length - 1) / 2) * 14} textAnchor="middle">{l}</text>
        ))}
        {st.notes?.[n.id] && <text x={NW - 6} y={14} textAnchor="end" className="rb-dg-mark">✎</text>}
      </g>
    )
  })

  const lanes = lanesShown
    ? L.lanes.map((ln, i) => {
        const s0 = PAD + ln.at * S - (S - ls) / 2, len = ln.span * S
        const [x, y] = xy(0, s0), [lw, lh] = down ? [len, h] : [w, len]
        return (
          <g key={i} className="rb-dg-lane">
            <rect x={x} y={y} width={lw} height={lh} style={{ fill: PALETTE[i % PALETTE.length] }} />
            <text x={down ? x + 8 : 8} y={down ? 18 : y + 18}>{wrap(ln.name || '(no group)', down ? Math.floor(len / 8) : 13, 1)[0]}</text>
          </g>
        )
      })
    : null

  const cur = sel ? g.byId[sel] : undefined
  const nb = cur ? neighbours(g, cur.id) : null
  const hop = (e: GEdge, id: string) => (
    <li key={e.key}>
      <button className="btn quiet" onClick={() => select(id)}>{g.byId[id].label}</button>
      {e.label && <span className="rb-muted"> — “{e.label}”</span>}
    </li>
  )
  return (
    <div className="rb-dg">
      <Pane w={w} h={h} max={paneMax(mode, props.size, 520)} view={view} setView={setView} onBackground={() => sel && select(undefined)}>
        {() => (
          <svg width={w} height={h} className="rb-dg-svg">
            <defs>
              {(['a', 'h'] as const).map((m) => (
                <marker key={m} id={`${uid}-${m}`} viewBox="0 0 10 10" refX={9} refY={5} markerWidth={7} markerHeight={7} orient="auto">
                  <path d="M0,0 L10,5 L0,10 z" className={m === 'h' ? 'rb-dg-arrow-hl' : 'rb-dg-arrow'} />
                </marker>
              ))}
            </defs>
            {lanes}
            {edges}
            {nodes}
          </svg>
        )}
      </Pane>
      <div className="rb-row">
        <select value={sel ?? ''} onChange={(e) => select(e.target.value || undefined)} aria-label="Select a box">
          <option value="">Select a box…</option>
          {g.nodes.map((n) => <option key={n.id} value={n.id}>{n.label}</option>)}
        </select>
        <label className="rb-muted">
          <input type="checkbox" checked={path} onChange={(e) => setPath(e.target.checked)} /> light the whole path, not just neighbours
        </label>
      </div>
      {!cur || !nb ? (
        <p className="rb-muted">Click a box to see what leads to it and what follows, and to leave a note on it.</p>
      ) : (
        <div className="rb-dg-detail">
          <div><b>{cur.label}</b> <span className="rb-muted">({cur.kind}{cur.group ? ` · ${cur.group}` : ''} · id {cur.id})</span></div>
          {cur.detail && <p>{cur.detail}</p>}
          <div className="rb-dg-cols">
            <div><div className="rb-lbl">Comes from</div>{nb.inc.length ? <ul>{nb.inc.map((e) => hop(e, e.from))}</ul> : <p className="rb-muted">nothing</p>}</div>
            <div><div className="rb-lbl">Goes to</div>{nb.outg.length ? <ul>{nb.outg.map((e) => hop(e, e.to))}</ul> : <p className="rb-muted">nothing</p>}</div>
          </div>
          <div className="rb-lbl">Your note (state; the Markdown is unchanged)</div>
          <textarea
            className="rb-dg-note"
            value={st.notes?.[cur.id] ?? ''}
            onChange={(e) => {
              const notes = { ...(st.notes ?? {}) }
              if (e.target.value) notes[cur.id] = e.target.value
              else delete notes[cur.id]
              set(tidy({ ...st, notes }))
            }}
          />
        </div>
      )}
    </div>
  )
}

export const diagram: TypeDef<Graph, DgState> = {
  ...diagramSpec,
  Rich: (p) => <DiagramView {...p} />,
  readable(g, a, s) {
    const out: string[] = []
    if ('title' in a) out.push(`title: ${q(a.title)}`)
    if (a.view === 'git') {
      out.push('view=git; commits in declaration order; edges declare parent -> child')
      g.nodes.forEach((n) => out.push(`- commit ${n.id}: ${q(n.label)}${n.group ? ` branch=${q(n.group)}` : ' (ungrouped)'}${n.author ? ` author=${q(n.author)}` : ''}${n.date ? ` date=${q(n.date)}` : ''}${n.tag ? ` tag=${q(n.tag)}` : ''}${n.detail ? ` detail=${q(n.detail)}` : ''}; parents: ${g.edges.filter((e) => e.to === n.id).map((e) => e.from).join(', ') || 'no parent declared'}${s?.notes?.[n.id] ? `; note: ${q(s.notes[n.id])}` : ''}`))
      out.push('declared parent edges:')
      g.edges.forEach((e) => out.push(`- ${edgeLine(e)}`))
      for (const [id, note] of Object.entries(s?.notes ?? {}))
        if (!g.byId[id]) out.push(`note on ${id}, no longer in source: ${q(note)}`)
      if (s?.sel) out.push(`selected: ${s.sel}`)
      return out.join('\n')
    }
    out.push(`direction: ${a.direction ?? 'down (not stated; the default)'}`)
    if (g.groups.length) out.push(`groups: ${g.groups.map(q).join(', ')}`)
    out.push('nodes:')
    for (const n of g.nodes) {
      out.push(`- ${nodeLine(n)}`)
      if (s?.notes?.[n.id] !== undefined) out.push(`  note by the person (not in the source): ${q(s.notes[n.id])}`)
    }
    out.push('edges:')
    if (!g.edges.length) out.push('- (none)')
    g.edges.forEach((e) => out.push(`- ${edgeLine(e)}`))
    const L = layered(g)
    out.push('reading order (step by step, as laid out):')
    L.order.forEach((row, i) => out.push(`${i + 1}. ${row.map((id) => q(g.byId[id].label)).join(', ')}`))
    const back = g.edges.filter((e) => L.back[e.key] || e.from === e.to)
    if (back.length) out.push(`edges that loop back: ${back.map(edgeLine).join('; ')}`)
    for (const [id, note] of Object.entries(s?.notes ?? {}))
      if (!g.byId[id]) out.push(`note on “${id}”, which is no longer in the source: ${q(note)}`)
    if (s?.sel) out.push(`selected by the person: ${s.sel}${g.byId[s.sel] ? ` (${q(g.byId[s.sel].label)})` : ' (no longer in the source)'}`)
    return out.join('\n')
  },
  handoff(g, a, s) {
    const cur = s?.sel ? g.byId[s.sel] : undefined
    const nb = cur ? neighbours(g, cur.id) : null
    if (a.view === 'git') {
      const parents = cur ? g.edges.filter((e) => e.to === cur.id).map((e) => e.from) : []
      return {
        selected: cur
          ? {
              view: 'git',
              id: cur.id,
              label: cur.label,
              parents,
              ...(cur.group ? { branch: cur.group, group: cur.group } : {}),
              ...(cur.detail ? { detail: cur.detail } : {}),
              ...(cur.date ? { date: cur.date } : {}),
              ...(cur.author ? { author: cur.author } : {}),
              ...(cur.tag ? { tag: cur.tag } : {}),
              note: s?.notes?.[cur.id] ?? null,
            }
          : null,
        notes_by_person: Object.entries(s?.notes ?? {}).map(([id, note]) => ({ id, label: g.byId[id]?.label ?? null, note })),
      }
    }
    return {
      selected: cur && nb
        ? { ...cur, n: undefined, comes_from: nb.inc.map(edgeLine), goes_to: nb.outg.map(edgeLine), note: s?.notes?.[cur.id] ?? null }
        : null,
      notes_by_person: Object.entries(s?.notes ?? {}).map(([id, note]) => ({ id, label: g.byId[id]?.label ?? null, note })),
    }
  },
}

/* --------------------------------------------------------------- whiteboard */

/* Board units: one card slot across (x) and one down (y). Positions in state
   are in these units, never in pixels, so another renderer can honour them.
   With groups, each group is a zone two slots wide, left to right, in order. */
const ZW = 2
const UX = 180, UY = 96, CW = 160, CH = 72

interface Pos { x: number; y: number }
interface WbState {
  sel?: string
  /** Source cards the person moved; zone is where they were dropped (null = board has no zones). */
  moved?: Record<string, Pos & { zone: string | null }>
  /** Source cards whose text the person changed. */
  text?: Record<string, string>
  added?: (Pos & { id: string; text: string; zone: string | null })[]
  links?: { from: string; to: string; label?: string }[]
}
interface Seats { at: Record<string, Pos>; zones: { name: string; x: number }[] }
interface Card { id: string; text: string; src: GNode | null; pos: Pos; zone: string | null; srcZone: string | null; moved: boolean; edited: boolean }

/** Where every source card starts. Without groups, the diagram's own layout
    (in slots); with groups, zone columns filled in flow order. */
function seatsOf(g: Graph, dir: string | undefined): Seats {
  const flow = layered(g)
  const at: Record<string, Pos> = {}
  if (!g.groups.length) {
    for (const n of g.nodes) {
      const p = flow.layer[n.id], s = flow.slot[n.id]
      at[n.id] = dir === 'right' ? { x: p, y: s } : { x: s, y: p }
    }
    return { at, zones: [] }
  }
  const names = [...g.groups, ...(g.nodes.some((n) => n.group === undefined) ? [''] : [])]
  const zones = names.map((name, i) => ({ name, x: i * ZW }))
  for (const z of zones)
    g.nodes
      .filter((n) => (n.group ?? '') === z.name)
      .sort((x, y) => flow.layer[x.id] - flow.layer[y.id] || x.n - y.n)
      .forEach((n, j) => (at[n.id] = { x: z.x + (j % ZW), y: Math.floor(j / ZW) }))
  return { at, zones }
}

const zoneAt = (zones: Seats['zones'], x: number): string | null => {
  if (!zones.length) return null
  const i = clamp(Math.floor((x + 0.5) / ZW), 0, zones.length - 1)
  return zones[i].name
}
const zoneName = (z: string | null) => (z === null ? '(board)' : z === '' ? '(no group)' : z)
const at2 = (p: Pos) => `x=${p.x}, y=${p.y}`

function cardsNow(g: Graph, seats: Seats, st: WbState): Card[] {
  const out: Card[] = g.nodes.map((n) => {
    const m = st.moved?.[n.id]
    const srcZone = seats.zones.length ? n.group ?? '' : null
    return {
      id: n.id, src: n, text: st.text?.[n.id] ?? n.label,
      pos: m ? { x: m.x, y: m.y } : seats.at[n.id], zone: m ? m.zone : srcZone, srcZone,
      moved: !!m, edited: st.text?.[n.id] !== undefined,
    }
  })
  for (const c of st.added ?? [])
    out.push({ id: c.id, src: null, text: c.text, pos: { x: c.x, y: c.y }, zone: c.zone, srcZone: null, moved: false, edited: false })
  return out
}

function WhiteboardView({ data: g, attrs: a, state, set, mode }: RichProps<Graph, WbState>) {
  const [view, setView] = useState<View | null>(null)
  const [editing, setEditing] = useState<string | null>(null)
  const [connect, setConnect] = useState<null | { from?: string }>(null)
  const [drag, setDrag] = useState<{ id: string; dx: number; dy: number } | null>(null)
  const dragRef = useRef<{ id: string; sx: number; sy: number; k: number; moved: boolean } | null>(null)
  const cancelEdit = useRef(false)
  const uid = useId().replace(/[^A-Za-z0-9_-]/g, '')
  const st: WbState = state ?? {}
  const seats = seatsOf(g, a.direction)
  const cards = cardsNow(g, seats, st)
  const byId: Record<string, Card> = Object.fromEntries(cards.map((c) => [c.id, c]))
  const sel = st.sel && byId[st.sel] ? st.sel : undefined
  const put = (s: WbState) => set(tidy(s))
  const HEAD = seats.zones.length ? 30 : 0
  const zonesW = seats.zones.length * ZW
  const posOf = (c: Card): Pos => (drag?.id === c.id ? { x: c.pos.x + drag.dx / UX, y: c.pos.y + drag.dy / UY } : c.pos)
  const wU = Math.max(zonesW, ...cards.map((c) => Math.ceil(c.pos.x) + (seats.zones.length ? 1 : 2)), 3)
  const hU = Math.max(3, ...cards.map((c) => Math.ceil(c.pos.y) + 2))
  const w = wU * UX, h = HEAD + hU * UY

  const moveTo = (c: Card, x: number, y: number) => {
    const r = (v: number) => Math.round(v * 4) / 4
    x = r(clamp(x, 0, seats.zones.length ? zonesW - 1 : 1e4))
    y = r(Math.max(0, y))
    const zone = zoneAt(seats.zones, x)
    if (!c.src) {
      put({ ...st, added: (st.added ?? []).map((x0) => (x0.id === c.id ? { ...x0, x, y, zone } : x0)) })
      return
    }
    const moved = { ...(st.moved ?? {}) }
    const home = seats.at[c.id]
    if (home.x === x && home.y === y) delete moved[c.id]
    else moved[c.id] = { x, y, zone }
    put({ ...st, moved })
  }
  const commitText = (c: Card, text: string) => {
    setEditing(null)
    if (!c.src) { put({ ...st, added: (st.added ?? []).map((x) => (x.id === c.id ? { ...x, text } : x)) }); return }
    const t = { ...(st.text ?? {}) }
    if (!text.trim() || text === c.src.label) delete t[c.id]
    else t[c.id] = text
    put({ ...st, text: t })
  }
  const click = (id: string) => {
    if (!connect) { put({ ...st, sel: id }); return }
    if (!connect.from) { setConnect({ from: id }); return }
    if (connect.from !== id) {
      const dup = [...g.edges, ...(st.links ?? [])].some((e) => e.from === connect.from && e.to === id)
      if (!dup) put({ ...st, links: [...(st.links ?? []), { from: connect.from, to: id }] })
    }
    setConnect(null)
  }
  const addCard = () => {
    const z = seats.zones.find((z0) => z0.name === (sel ? byId[sel].zone : undefined)) ?? seats.zones[0]
    const xs = z ? [z.x, z.x + 1] : Array.from({ length: Math.max(4, wU - 1) }, (_, i) => i)
    let spot: Pos = { x: 0, y: 0 }
    search: for (let y = 0; y < 500; y++)
      for (const x of xs)
        if (!cards.some((c) => Math.abs(c.pos.x - x) < 0.75 && Math.abs(c.pos.y - y) < 0.75)) { spot = { x, y }; break search }
    let n = 1
    while (byId[`added-${n}`]) n++
    const id = `added-${n}`
    put({ ...st, sel: id, added: [...(st.added ?? []), { id, text: 'New card', ...spot, zone: zoneAt(seats.zones, spot.x) }] })
    setEditing(id)
  }
  const removeAdded = (id: string) =>
    put({
      ...st,
      sel: st.sel === id ? undefined : st.sel,
      added: (st.added ?? []).filter((c) => c.id !== id),
      links: (st.links ?? []).filter((l) => l.from !== id && l.to !== id),
    })
  const setLinks = (links: NonNullable<WbState['links']>) => put({ ...st, links })

  // Links: source ones solid, the person's dashed.
  const center = (p: Pos): [number, number] => [p.x * UX + UX / 2, HEAD + p.y * UY + UY / 2]
  const edgePt = ([cx, cy]: [number, number], [tx, ty]: [number, number]): [number, number] => {
    const dx = tx - cx, dy = ty - cy
    const s = Math.min((CW / 2 + 4) / Math.abs(dx || 1e-9), (CH / 2 + 4) / Math.abs(dy || 1e-9), 1)
    return [cx + dx * s, cy + dy * s]
  }
  const allLinks = [
    ...g.edges.map((e) => ({ ...e, mine: false })),
    ...(st.links ?? []).map((l, i) => ({ ...l, key: `mine-${i}`, mine: true })),
  ].filter((l) => byId[l.from] && byId[l.to])
  const links = allLinks.map((l) => {
    const A = center(posOf(byId[l.from])), B = center(posOf(byId[l.to]))
    const on = sel && (l.from === sel || l.to === sel)
    const cls = 'rb-wb-link' + (l.mine ? ' rb-wb-mine' : '') + (on ? ' rb-dg-hl' : '')
    if (l.from === l.to) {
      const [x, y] = [A[0] + CW / 2, A[1]]
      return <path key={l.key} className={cls} d={`M${x},${y - 10} c30,-20 30,40 0,20`} markerEnd={`url(#${uid})`} />
    }
    const p = edgePt(A, B), r = edgePt(B, A)
    return (
      <g key={l.key} className={cls}>
        <line x1={p[0]} y1={p[1]} x2={r[0]} y2={r[1]} markerEnd={`url(#${uid})`} />
        {l.label && <text x={(p[0] + r[0]) / 2} y={(p[1] + r[1]) / 2 - 4} textAnchor="middle" className="rb-dg-elabel">{l.label}</text>}
      </g>
    )
  })

  const cur = sel ? byId[sel] : undefined
  const changes = cards.filter((c) => !c.src || c.moved || c.edited).length + (st.links?.length ?? 0)
  return (
    <div className="rb-wb">
      <div className="rb-row">
        <button className="btn" onClick={addCard}>+ Card</button>
        <button className="btn" aria-pressed={!!connect} onClick={() => setConnect(connect ? null : {})}>
          {connect ? 'Cancel connect' : 'Connect two cards'}
        </button>
        {connect && <span className="rb-tag">{connect.from ? `from “${byId[connect.from]?.text}”: now click the card it points to` : 'click the first card'}</span>}
        <span className="rb-muted">Drag cards · double-click to edit text</span>
      </div>
      <Pane w={w} h={h} max={mode === 'pin' ? 340 : 540} view={view} setView={setView} onBackground={() => sel && put({ ...st, sel: undefined })}>
        {(k) => (
          <div className="rb-wb-board" style={{ width: w, height: h }}>
            {seats.zones.map((z, i) => (
              <div key={i} className="rb-wb-zone" style={{ left: z.x * UX, width: ZW * UX, height: h }}>
                <div className="rb-wb-zhead">{zoneName(z.name)}</div>
              </div>
            ))}
            <svg className="rb-wb-links" width={w} height={h}>
              <defs>
                <marker id={uid} viewBox="0 0 10 10" refX={9} refY={5} markerWidth={7} markerHeight={7} orient="auto">
                  <path d="M0,0 L10,5 L0,10 z" className="rb-dg-arrow" />
                </marker>
              </defs>
              {links}
            </svg>
            {cards.map((c) => {
              const p = posOf(c)
              const cls = 'rb-wb-card' + (c.src ? '' : ' rb-wb-added') + (c.src?.kind === 'note' ? ' rb-wb-note' : '')
                + (c.id === sel ? ' rb-wb-sel' : '') + (connect?.from === c.id ? ' rb-wb-from' : '') + (drag?.id === c.id ? ' rb-wb-dragging' : '')
              return (
                <div
                  key={c.id}
                  data-item=""
                  className={cls}
                  style={{ left: p.x * UX + (UX - CW) / 2, top: HEAD + p.y * UY + (UY - CH) / 2, width: CW, height: CH }}
                  title={c.src?.detail}
                  onPointerDown={(e) => {
                    if (editing === c.id || e.button !== 0) return
                    e.currentTarget.setPointerCapture(e.pointerId)
                    dragRef.current = { id: c.id, sx: e.clientX, sy: e.clientY, k, moved: false }
                  }}
                  onPointerMove={(e) => {
                    const d = dragRef.current
                    if (!d || d.id !== c.id || connect) return
                    const dx = (e.clientX - d.sx) / d.k, dy = (e.clientY - d.sy) / d.k
                    if (!d.moved && Math.hypot(dx, dy) < 4) return
                    d.moved = true
                    setDrag({ id: c.id, dx, dy })
                  }}
                  onPointerUp={(e) => {
                    const d = dragRef.current
                    dragRef.current = null
                    setDrag(null)
                    if (!d || d.id !== c.id) return
                    if (!d.moved) click(c.id)
                    else moveTo(c, c.pos.x + (e.clientX - d.sx) / d.k / UX, c.pos.y + (e.clientY - d.sy) / d.k / UY)
                  }}
                  onDoubleClick={() => { setConnect(null); setEditing(c.id) }}
                >
                  {editing === c.id ? (
                    <textarea
                      autoFocus
                      defaultValue={c.text}
                      onFocus={(e) => e.currentTarget.select()}
                      onKeyDown={(e) => {
                        if (e.key === 'Escape') { cancelEdit.current = true; setEditing(null) }
                        else if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); e.currentTarget.blur() }
                      }}
                      onBlur={(e) => {
                        if (cancelEdit.current) { cancelEdit.current = false; return }
                        commitText(c, e.currentTarget.value)
                      }}
                    />
                  ) : (
                    <span className="rb-wb-text">{c.text || '(empty)'}</span>
                  )}
                  <span className="rb-wb-badges">
                    {!c.src && <span>added</span>}
                    {c.moved && <span>moved</span>}
                    {c.edited && <span>edited</span>}
                    {c.src && c.src.kind !== 'step' && <span className="rb-wb-kind">{c.src.kind}</span>}
                  </span>
                </div>
              )
            })}
          </div>
        )}
      </Pane>
      {cur ? (
        <div className="rb-dg-detail">
          <div>
            <b>{cur.text}</b>{' '}
            <span className="rb-muted">
              (id {cur.id} · {cur.src ? 'from the source' : 'added by you'}{cur.zone !== null ? ` · in ${zoneName(cur.zone)}` : ''})
            </span>
          </div>
          {cur.src?.detail && <p>{cur.src.detail}</p>}
          {cur.edited && cur.src && <p className="rb-muted">Source text: “{cur.src.label}”</p>}
          {cur.moved && cur.srcZone !== null && cur.srcZone !== cur.zone && <p className="rb-muted">Source zone: {zoneName(cur.srcZone)}</p>}
          <div className="rb-row">
            <button className="btn quiet" onClick={() => setEditing(cur.id)}>Edit text</button>
            {cur.moved && <button className="btn quiet" onClick={() => { const m = { ...st.moved }; delete m[cur.id]; put({ ...st, moved: m }) }}>Put back</button>}
            {cur.edited && <button className="btn quiet" onClick={() => { const t = { ...st.text }; delete t[cur.id]; put({ ...st, text: t }) }}>Undo text edit</button>}
            {!cur.src && <button className="btn quiet" onClick={() => removeAdded(cur.id)}>Delete card</button>}
          </div>
        </div>
      ) : (
        <p className="rb-muted">Click a card to see where it came from. Source cards can be moved and re-worded; cards you add can also be deleted.</p>
      )}
      {changes > 0 && (
        <details className="rb-wb-changes" open={mode !== 'pin'}>
          <summary>Your changes ({changes}) — state only; the Markdown is unchanged</summary>
          <ul>
            {cards.filter((c) => c.moved).map((c) => (
              <li key={'m' + c.id}>
                Moved “{c.text}”{c.srcZone !== null && c.srcZone !== c.zone ? ` from ${zoneName(c.srcZone)} to ${zoneName(c.zone)}` : ''}{' '}
                <button className="btn quiet" onClick={() => { const m = { ...st.moved }; delete m[c.id]; put({ ...st, moved: m }) }}>put back</button>
              </li>
            ))}
            {cards.filter((c) => c.edited).map((c) => (
              <li key={'e' + c.id}>
                Re-worded {c.id}: “{c.src!.label}” → “{c.text}”{' '}
                <button className="btn quiet" onClick={() => { const t = { ...st.text }; delete t[c.id]; put({ ...st, text: t }) }}>undo</button>
              </li>
            ))}
            {cards.filter((c) => !c.src).map((c) => (
              <li key={'a' + c.id}>
                Added “{c.text}”{c.zone !== null ? ` in ${zoneName(c.zone)}` : ''} <button className="btn quiet" onClick={() => removeAdded(c.id)}>delete</button>
              </li>
            ))}
            {(st.links ?? []).map((l, i) => (
              <li key={'l' + i}>
                Link “{byId[l.from]?.text ?? l.from}” → “{byId[l.to]?.text ?? l.to}”{' '}
                <input
                  className="rb-wb-lbl"
                  placeholder="label (optional)"
                  value={l.label ?? ''}
                  onChange={(e) => setLinks((st.links ?? []).map((x, j) => (j === i ? { from: x.from, to: x.to, ...(e.target.value ? { label: e.target.value } : {}) } : x)))}
                />{' '}
                <button className="btn quiet" onClick={() => setLinks((st.links ?? []).filter((_, j) => j !== i))}>delete</button>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  )
}

export const whiteboard: TypeDef<Graph, WbState> = {
  ...whiteboardSpec,
  Rich: (p) => <WhiteboardView {...p} />,
  readable(g, a, s) {
    const st = s ?? {}
    const seats = seatsOf(g, a.direction)
    const cards = cardsNow(g, seats, st)
    const out: string[] = []
    if ('title' in a) out.push(`title: ${q(a.title)}`)
    if (seats.zones.length) out.push(`zones, left to right: ${seats.zones.map((z) => q(zoneName(z.name))).join(', ')}`)
    else out.push(`zones: none; cards start where the flow puts them (direction ${a.direction ?? 'down, the default'})`)
    const line = (c: Card) => {
      const bits: string[] = []
      if (c.src) {
        bits.push('from the source')
        if (c.src.kind !== 'step') bits.push(`kind=${c.src.kind}`)
        if (c.src.detail !== undefined) bits.push(`detail=${q(c.src.detail)}`)
        if (c.edited) bits.push(`text edited by the person; source text ${q(c.src.label)}`)
        if (c.moved)
          bits.push(c.srcZone !== null && c.srcZone !== c.zone
            ? `moved by the person from ${q(zoneName(c.srcZone))} (to ${at2(c.pos)} in board slots)`
            : `moved by the person (to ${at2(c.pos)} in board slots)`)
      } else bits.push(`added by the person, at ${at2(c.pos)} in board slots`)
      return `- ${c.id}: ${q(c.text)}  [${bits.join('; ')}]`
    }
    const reading = (x: Card, y: Card) => x.pos.y - y.pos.y || x.pos.x - y.pos.x || (x.id < y.id ? -1 : 1)
    if (seats.zones.length) {
      const names = [...seats.zones.map((z) => z.name), ...new Set(cards.map((c) => c.zone ?? '').filter((z) => !seats.zones.some((x) => x.name === z)))]
      out.push('cards, zone by zone as they stand now (top to bottom):')
      for (const z of names) {
        const known = seats.zones.some((x) => x.name === z)
        out.push(`${zoneName(z)}:${known ? '' : ' (a zone no longer in the source)'}`)
        const inZ = cards.filter((c) => (c.zone ?? '') === z).sort(reading)
        if (!inZ.length) out.push('- (empty)')
        inZ.forEach((c) => out.push(line(c)))
      }
    } else {
      out.push('cards, as they stand now (top to bottom, left to right):')
      if (!cards.length) out.push('- (none)')
      cards.slice().sort(reading).forEach((c) => out.push(line(c)))
    }
    out.push('links:')
    if (!g.edges.length && !st.links?.length) out.push('- (none)')
    g.edges.forEach((e) => out.push(`- ${edgeLine(e)}  [from the source]`))
    ;(st.links ?? []).forEach((l) => out.push(`- ${edgeLine(l)}  [added by the person]`))
    const ids = new Set(cards.map((c) => c.id))
    const stale = [...Object.keys(st.moved ?? {}), ...Object.keys(st.text ?? {}), ...(st.links ?? []).flatMap((l) => [l.from, l.to])].filter((id) => !ids.has(id))
    if (stale.length) out.push(`changes about cards no longer in the source (kept, not shown): ${[...new Set(stale)].join(', ')}`)
    if (st.sel) out.push(`selected by the person: ${st.sel}`)
    return out.join('\n')
  },
  handoff(g, a, s) {
    const st = s ?? {}
    const cards = cardsNow(g, seatsOf(g, a.direction), st)
    return {
      selected: st.sel ?? null,
      changes_by_person: {
        moved: cards.filter((c) => c.moved).map((c) => ({ id: c.id, text: c.text, from_zone: c.srcZone, to_zone: c.zone, at: c.pos })),
        text_edited: cards.filter((c) => c.edited).map((c) => ({ id: c.id, source_text: c.src!.label, text_now: c.text })),
        cards_added: cards.filter((c) => !c.src).map((c) => ({ id: c.id, text: c.text, zone: c.zone, at: c.pos })),
        links_added: st.links ?? [],
      },
    }
  },
}
