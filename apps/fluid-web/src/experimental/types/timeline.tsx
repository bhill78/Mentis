/* EXPERIMENTAL: timeline -- dated rows drawn on a time axis, one lane per group.

   The author writes CSV, like a chart, and names which column holds what:
   when (default "date"), what (default "event"), and optionally until, group
   and detail. Dates are written, never computed: YYYY, YYYY-MM, YYYY-MM-DD or
   YYYY-MM-DDTHH:MM, read as wall-clock times (no time zone, no "today"), so
   the drawing is the same on every machine. An `until` date is inclusive of
   the period it names: until 2026-03 runs to the end of March.            */
import './graph.css'
import { useId, useRef, useState } from 'react'
import type { RichProps, TypeDef } from '../api'
import { PALETTE, q } from '../util'
import { clamp, tidy, useWheel, useWidth } from './graph'
import { timelineSpec, type Ev, type TL } from '../spec/timeline'

interface TLState { sel?: string; notes?: Record<string, string> }

const MIN = 60e3, HOUR = 60 * MIN, DAY = 24 * HOUR
const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/* ---- axis ticks: the smallest calendar step that leaves room for a label ---- */

type Unit = 'min' | 'hour' | 'day' | 'week' | 'month' | 'year'
const APPROX: Record<Unit, number> = { min: MIN, hour: HOUR, day: DAY, week: 7 * DAY, month: 30.44 * DAY, year: 365.25 * DAY }
const STEPS: [Unit, number][] = [
  ['min', 1], ['min', 5], ['min', 15], ['min', 30], ['hour', 1], ['hour', 3], ['hour', 6], ['hour', 12],
  ['day', 1], ['day', 2], ['week', 1], ['month', 1], ['month', 3], ['month', 6],
  ['year', 1], ['year', 2], ['year', 5], ['year', 10], ['year', 25], ['year', 50], ['year', 100],
]

function ticks(t0: number, t1: number, W: number) {
  const perPx = (t1 - t0) / W
  const [u, n] = STEPS.find(([u0, n0]) => (APPROX[u0] * n0) / perPx >= 84) ?? STEPS[STEPS.length - 1]
  const ts: number[] = []
  if (u === 'month' || u === 'year') {
    const d = new Date(t0)
    const y = u === 'year' ? Math.floor(d.getUTCFullYear() / n) * n : d.getUTCFullYear()
    const m = u === 'year' ? 0 : Math.floor(d.getUTCMonth() / n) * n
    for (let k = 0; k < 400; k++) {
      const t = u === 'year' ? Date.UTC(y + k * n, 0, 1) : Date.UTC(y, m + k * n, 1)
      if (t > t1) break
      if (t >= t0) ts.push(t)
    }
  } else {
    const step = APPROX[u] * n, off = u === 'week' ? 4 * DAY : 0 // weeks start on Monday
    for (let t = Math.ceil((t0 - off) / step) * step + off; t <= t1 && ts.length < 400; t += step) ts.push(t)
  }
  const two = (v: number) => String(v).padStart(2, '0')
  let prev: Date | null = null
  return ts.map((t) => {
    const d = new Date(t)
    const [Y, M, D] = [d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()]
    let label: string, sub = ''
    if (u === 'min' || u === 'hour') {
      label = `${two(d.getUTCHours())}:${two(d.getUTCMinutes())}`
      if (!prev || prev.getUTCDate() !== D) sub = `${D} ${MON[M]} ${Y}`
    } else if (u === 'day' || u === 'week') {
      label = `${D} ${MON[M]}`
      if (!prev || prev.getUTCFullYear() !== Y) sub = String(Y)
    } else if (u === 'month') {
      label = MON[M]
      if (!prev || prev.getUTCFullYear() !== Y) sub = String(Y)
    } else label = String(Y)
    prev = d
    return { t, label, sub }
  })
}

const short = (t: number) => { const d = new Date(t); return `${d.getUTCDate()} ${MON[d.getUTCMonth()]} ${d.getUTCFullYear()}` }
const when = (e: Ev) => (e.until ? `${e.from} → ${e.until}` : e.from)

/* ---------------------------------------------------------------- the view */

function TimelineView({ data, state, set, mode }: RichProps<TL | null, TLState>) {
  const d = data!
  const marker = useId().replace(/[^A-Za-z0-9_-]/g, '')
  const [ref, cw] = useWidth<HTMLDivElement>()
  const [win, setWin] = useState<[number, number] | null>(null)
  const drag = useRef<{ x: number; w: [number, number]; moved: boolean } | null>(null)
  const st = state ?? {}
  const byId = Object.fromEntries(d.events.map((e) => [e.id, e]))
  const sel = st.sel && byId[st.sel] ? st.sel : undefined
  const put = (s: TLState) => set(tidy(s))

  const W = Math.max(280, cw || 640)
  const pad = Math.max((d.max - d.min) * 0.06, 12 * HOUR)
  const full: [number, number] = [d.min - pad, d.max + pad]
  const [t0, t1] = win ?? full
  const span = t1 - t0
  const MINSPAN = 2 * HOUR, MAXSPAN = Math.max((full[1] - full[0]) * 4, 2 * DAY)
  const px = (t: number) => ((t - t0) / span) * W
  const zoom = (f: number, at = t0 + span / 2) => {
    const ns = clamp(span * f, MINSPAN, MAXSPAN)
    const a = at - (at - t0) * (ns / span)
    setWin([a, a + ns])
  }
  const shift = (frac: number) => setWin([t0 + span * frac, t1 + span * frac])
  const show = (e: Ev) => {
    const end = e.end ?? e.start
    if (e.start < t0 || end > t1) {
      const ns = Math.max(span, Math.min(MAXSPAN, (end - e.start) * 1.3))
      const c = (e.start + end) / 2
      setWin([c - ns / 2, c + ns / 2])
    }
  }
  useWheel(ref, (e) => {
    if (!(e.ctrlKey || e.metaKey)) return
    e.preventDefault()
    const r = ref.current!.getBoundingClientRect()
    zoom(e.deltaY < 0 ? 1 / 1.2 : 1.2, t0 + ((e.clientX - r.left) / W) * span)
  })

  // Lanes: events packed into rows so labels never overlap at this zoom.
  const noLanes = d.lanes.length === 1 && d.lanes[0] === ''
  const AXIS = 34, ROW = 22, LHEAD = noLanes ? 4 : 18
  let y = AXIS
  const lanes = d.lanes.map((lane, li) => {
    const ends: number[] = []
    // In the window [t0, t1]: a moment inside it, or a span [start, end) overlapping it; spans are clipped to [0, W].
    const placed = d.events.filter((e) => e.lane === lane && e.start <= t1 && (e.end === null ? e.start >= t0 : e.end > t0)).map((e) => {
      const x0 = Math.max(0, px(e.start)), xe = e.end !== null ? Math.min(W, px(e.end)) : x0
      const lw = e.label.length * 6.4 + 14
      const inside = e.end !== null && xe - x0 >= lw
      const right = e.end === null ? x0 + 8 + lw : inside ? xe : xe + lw
      let r = ends.findIndex((v) => v < x0 - 10)
      if (r < 0) { r = ends.length; ends.push(0) }
      ends[r] = right
      return { e, x0, xe, r, inside }
    })
    const top = y
    const h = LHEAD + Math.max(1, ends.length) * ROW + 6
    y += h
    return { lane, li, top, h, placed }
  })
  // Only in-window marks may reserve extra space for their labels; Fit is unchanged.
  const drawingWidth = Math.max(W, ...lanes.flatMap((l) => l.placed.map(({ e, x0, xe, inside }) =>
    (e.end === null ? x0 + 9 : inside ? x0 + 5 : xe + 5) + (e.label.length + 2) * 12 + 8)))
  const H = y + 4

  const cur = sel ? byId[sel] : undefined
  const idx = cur ? d.events.indexOf(cur) : -1
  const step = (k: number) => {
    const e = d.events[idx < 0 ? (k > 0 ? 0 : d.events.length - 1) : clamp(idx + k, 0, d.events.length - 1)]
    put({ ...st, sel: e.id })
    show(e)
  }

  const posById: Record<string, { x: number; y: number }> = {}
  lanes.forEach((l) => {
    l.placed.forEach(({ e, x0, xe, r }) => {
      const cy = l.top + LHEAD + r * ROW + ROW / 2
      const pos = { x: e.end === null ? x0 : (x0 + xe) / 2, y: cy }
      posById[e.id] = pos
    })
  })

  const depSvg: React.ReactNode[] = []
  d.events.forEach((e) => {
    if (!e.parents) return
    const curPos = posById[e.id]
    if (!curPos) return
    e.parents.forEach((pid, pidx) => {
      const targetEv = d.events.find((ev) => ev.id === pid)
      const parentPos = posById[pid] || (targetEv ? posById[targetEv.id] : undefined)
      if (!parentPos) return
      const isHl = sel !== undefined && (sel === e.id || sel === (targetEv?.id ?? pid))
      const midX = (parentPos.x + curPos.x) / 2
      const dPath = `M ${parentPos.x} ${parentPos.y} C ${midX} ${parentPos.y}, ${midX} ${curPos.y}, ${curPos.x} ${curPos.y}`
      depSvg.push(
        <path
          key={`dep_${e.id}_${pidx}`}
          className="rb-tl-dep"
          markerEnd={`url(#${marker})`}
          d={dPath}
          fill="none"
          stroke={isHl ? 'var(--accent)' : 'var(--text-dim)'}
          strokeWidth={isHl ? 2.5 : 1.5}
          strokeDasharray="3 3"
          opacity={isHl ? 1 : 0.65}
        />,
      )
    })
  })

  return (
    <div className="rb-tl">
      <div className="rb-row rb-dg-tools">
        <button className="btn quiet" title="Earlier" onClick={() => shift(-0.4)}>◂</button>
        <button className="btn quiet" title="Zoom out" onClick={() => zoom(1.6)}>−</button>
        <button className="btn quiet" title="Zoom in" onClick={() => zoom(1 / 1.6)}>+</button>
        <button className="btn quiet" title="Later" onClick={() => shift(0.4)}>▸</button>
        <button className="btn quiet" onClick={() => setWin(null)}>Fit</button>
        <span className="rb-muted">{short(t0)} – {short(t1)}{mode === 'pin' ? '' : ' · drag to pan · Ctrl+wheel zooms'}</span>
      </div>
      <div ref={ref} className="rb-tl-pane" tabIndex={0} role="region" aria-label="Timeline, scroll horizontally for event labels">
        <svg
          width={drawingWidth}
          height={H}
          className="rb-tl-svg"
          onPointerDown={(e) => {
            if (e.pointerType === 'touch' || e.button !== 0 || (e.target as Element).closest('[data-item]')) return
            drag.current = { x: e.clientX, w: [t0, t1], moved: false }
            e.currentTarget.setPointerCapture(e.pointerId)
          }}
          onPointerMove={(e) => {
            const g = drag.current
            if (!g) return
            const dx = e.clientX - g.x
            if (!g.moved && Math.abs(dx) < 4) return
            g.moved = true
            const dt = (-dx / W) * (g.w[1] - g.w[0])
            setWin([g.w[0] + dt, g.w[1] + dt])
          }}
          onPointerUp={() => {
            const g = drag.current
            drag.current = null
            if (g && !g.moved && sel) put({ ...st, sel: undefined })
          }}
        >
          {lanes.map((l) => (
            <rect key={'band' + l.li} x={0} y={l.top} width={W} height={l.h} className={l.li % 2 ? 'rb-tl-band2' : 'rb-tl-band'} />
          ))}
          {ticks(t0, t1, W).map((k) => (
            <g key={k.t} className="rb-tl-tick">
              <line x1={px(k.t)} x2={px(k.t)} y1={AXIS - 6} y2={H} />
              <text x={px(k.t) + 3} y={13}>{k.label}</text>
              {k.sub && <text x={px(k.t) + 3} y={26} className="rb-tl-sub">{k.sub}</text>}
            </g>
          ))}
          <defs><marker id={marker} viewBox="0 0 10 10" refX="10" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 Z" fill="var(--text-dim)" /></marker></defs>
          {depSvg}
          {lanes.map((l) => {
            const c = PALETTE[l.li % PALETTE.length]
            return (
              <g key={'lane' + l.li}>
                {!noLanes && <text x={6} y={l.top + 13} className="rb-tl-lane" style={{ fill: c }}>{l.lane}</text>}
                {l.placed.map(({ e, x0, xe, r, inside }) => {
                  const cy = l.top + LHEAD + r * ROW + ROW / 2
                  const on = e.id === sel
                  const tx = e.end === null ? x0 + 9 : inside ? x0 + 5 : xe + 5
                  return (
                    <g
                      key={e.id}
                      data-item=""
                      className={'rb-tl-ev' + (on ? ' rb-tl-sel' : '')}
                      onClick={() => put({ ...st, sel: on ? undefined : e.id })}
                    >
                      <title>{`${when(e)}  ${e.label}${e.detail ? '\n' + e.detail : ''}`}</title>
                      {e.end === null ? (
                        <circle cx={x0} cy={cy} r={5} style={{ fill: e.prec === 'month' || e.prec === 'year' ? 'var(--surface)' : c, stroke: c }} />
                      ) : (
                        <rect x={x0} y={cy - 7} width={Math.max(2, xe - x0)} height={14} rx={3} style={{ fill: c, stroke: c }} className="rb-tl-span" />
                      )}
                      <text x={tx} y={cy + 4}>{e.label}{st.notes?.[e.id] ? ' ✎' : ''}</text>
                    </g>
                  )
                })}
              </g>
            )
          })}
        </svg>
      </div>
      <div className="rb-row">
        <button className="btn quiet" onClick={() => step(-1)}>‹ Previous</button>
        <button className="btn quiet" onClick={() => step(1)}>Next ›</button>
        <span className="rb-muted">{cur ? `${idx + 1} of ${d.events.length}` : `${d.events.length} events`}</span>
      </div>
      {cur ? (
        <div className="rb-dg-detail">
          <div><b>{cur.label}</b> <span className="rb-muted">{when(cur)}{cur.lane ? ` · ${cur.lane}` : ''}</span></div>
          {cur.detail && <p>{cur.detail}</p>}
          {cur.extra.length > 0 && (
            <p className="rb-muted">{cur.extra.map(([k, v]) => `${k}: ${v}`).join(' · ')}</p>
          )}
          <div className="rb-lbl">Your note (state; the Markdown is unchanged)</div>
          <textarea
            className="rb-dg-note"
            value={st.notes?.[cur.id] ?? ''}
            onChange={(e) => {
              const notes = { ...(st.notes ?? {}) }
              if (e.target.value) notes[cur.id] = e.target.value
              else delete notes[cur.id]
              put({ ...st, notes })
            }}
          />
        </div>
      ) : (
        <p className="rb-muted">Click an event for its detail, or step through them in order.</p>
      )}
    </div>
  )
}

/* ---------------------------------------------------------------- the type */

export const timeline: TypeDef<TL | null, TLState> = {
  ...timelineSpec,
  Rich: (p) => <TimelineView {...p} />,
  readable(data, a, s) {
    const d = data!
    const out: string[] = []
    if ('title' in a) out.push(`title: ${q(a.title)}`)
    out.push(`columns: ${Object.entries(d.cols).map(([k, v]) => `${k}=${q(v)}${k in a ? '' : ' (default)'}`).join(', ')}`)
    for (const lane of d.lanes) {
      out.push(lane ? `lane ${q(lane)}, in order:` : 'events, in order:')
      for (const e of d.events.filter((x) => x.lane === lane)) {
        const extra = e.extra.map(([k, v]) => `${k}=${q(v)}`).join(' ')
        out.push(`- ${d.cols.id ? `id=${q(e.id)}  ` : ''}${when(e)}  ${e.label}${e.detail ? ` — ${e.detail}` : ''}${extra ? `  (${extra})` : ''}`)
        if (e.parents) out.push(`  prerequisite ids: ${e.parents.join(', ')}`)
        if (s?.notes?.[e.id] !== undefined) out.push(`  note by the person (not in the source): ${q(s.notes[e.id])}`)
      }
    }
    const ids = new Set(d.events.map((e) => e.id))
    for (const [id, note] of Object.entries(s?.notes ?? {}))
      if (!ids.has(id)) out.push(`note on “${id}”, which is no longer in the source: ${q(note)}`)
    if (s?.sel) out.push(`selected by the person: ${s.sel}`)
    return out.join('\n')
  },
  handoff(data, _a, s) {
    const d = data!
    const e = d.events.find((x) => x.id === s?.sel)
    const brief = (x: Ev) => ({ id: x.id, when: when(x), event: x.label, lane: x.lane || null })
    return {
      selected_event: e ? { ...brief(e), detail: e.detail || null, parents: e.parents ?? [], dependency_key: d.cols.id ?? null, other_columns: Object.fromEntries(e.extra), note: s?.notes?.[e.id] ?? null } : null,
      notes_by_person: Object.entries(s?.notes ?? {}).map(([id, note]) => {
        const x = d.events.find((y) => y.id === id)
        return x ? { ...brief(x), note } : { id, note, no_longer_in_source: true }
      }),
    }
  },
}
