/* Picture collections (Builder: gallery).
 *
 * One collection, four presentations of it: Across (a sideways row of large
 * pictures), Grid (compact thumbnails), Focus (one prominent picture over a
 * thumbnail strip) and Mosaic (variable tiles sized from each picture's own
 * shape). The selected picture can be enlarged within the gallery's own stage,
 * zoomed and panned. Everything that matters (arrangement, selection, enlarged,
 * zoom, pan) lives in the frame-held state, so a remount restores it; only the
 * pictures' natural shapes, learned as they load, are kept locally. */
import { useCallback, useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent, type PointerEvent as RPointerEvent, type CSSProperties, type ReactNode, type SyntheticEvent } from 'react'
import type { GalleryLayout, GalleryState, RendererProps, ViewImage } from './types'
import './gallery.css'

const ZOOM_MIN = 1
const ZOOM_MAX = 8
const ZOOM_STEP = 1.25

const LAYOUTS: { id: GalleryLayout; label: string; icon: ReactNode }[] = [
  { id: 'across', label: 'Across', icon: <path d="M1.5 4.5h4v7h-4zM6.5 3.5h5v9h-5zM12.5 4.5h2v7h-2z" /> },
  { id: 'grid', label: 'Grid', icon: <path d="M2 2h5v5H2zM9 2h5v5H9zM2 9h5v5H2zM9 9h5v5H9z" /> },
  { id: 'focus', label: 'Focus', icon: <path d="M2 2h12v8H2zM2 12h3v2H2zM6.5 12h3v2h-3zM11 12h3v2h-3z" /> },
  { id: 'mosaic', label: 'Mosaic', icon: <path d="M2 2h7v6H2zM10.5 2h3.5v3h-3.5zM10.5 6.5h3.5v7.5h-3.5zM2 9.5h3v4.5H2zM6.5 9.5H9v4.5H6.5z" /> },
]

function Icon({ children }: { children: ReactNode }) {
  return <svg className="q2g-icon" viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" strokeLinecap="round">{children}</svg>
}
const I = {
  prev: <path d="M10 3.5 5.5 8l4.5 4.5" />,
  next: <path d="M6 3.5 10.5 8 6 12.5" />,
  enlarge: <path d="M9.5 2.5h4v4M13.5 2.5 9 7M6.5 13.5h-4v-4M2.5 13.5 7 9" />,
  shrink: <path d="M13 3 9.5 6.5M9.5 3v3.5H13M3 13l3.5-3.5M6.5 13V9.5H3" />,
  minus: <path d="M3.5 8h9" />,
  plus: <path d="M3.5 8h9M8 3.5v9" />,
}

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v))

/** Mosaic spans from a picture's natural width/height (unknown until it loads). */
function spanOf(ratio: number | undefined, i: number): string {
  if (!ratio) return ''
  if (ratio >= 1.65) return 'q2g-wide'
  if (ratio <= 0.72) return 'q2g-tall'
  if (i % 7 === 0) return 'q2g-big'
  return ''
}

/** Scroll `el` into the middle of `box` along one axis, without moving anything outside `box`. */
function centreIn(box: HTMLElement | null, el: HTMLElement | null, axis: 'x' | 'y', smooth: boolean) {
  if (!box || !el) return
  const b = box.getBoundingClientRect()
  const r = el.getBoundingClientRect()
  const behavior: ScrollBehavior = smooth ? 'smooth' : 'auto'
  if (axis === 'x') {
    if (r.left >= b.left && r.right <= b.right && !smooth) return
    box.scrollTo({ left: box.scrollLeft + (r.left - b.left) - (b.width - r.width) / 2, behavior })
  } else {
    if (r.top >= b.top && r.bottom <= b.bottom) return
    box.scrollTo({ top: box.scrollTop + (r.top - b.top) - (b.height - r.height) / 2, behavior })
  }
}

export default function GalleryView({ images, state, onState, placement }: RendererProps<GalleryState> & { images: ViewImage[] }) {
  const n = images.length
  const single = n === 1
  const index = clamp(state.index, 0, Math.max(0, n - 1))
  const layout: GalleryLayout = single ? 'focus' : state.layout
  const enlarged = single || state.enlarged
  const zoom = enlarged ? clamp(state.zoom || 1, ZOOM_MIN, ZOOM_MAX) : 1
  const pan = enlarged && zoom > 1 ? state.pan : { x: 0, y: 0 }
  const current = images[index]
  const column = placement === 'column'

  /* the latest state, for native listeners and drags */
  const live = useRef(state)
  live.current = state
  const set = useCallback((patch: Partial<GalleryState>) => onState({ ...live.current, ...patch }), [onState])

  const [ratios, setRatios] = useState<Record<string, number>>({})
  const learn = (url: string) => (e: SyntheticEvent<HTMLImageElement>) => {
    const im = e.currentTarget
    if (im.naturalWidth && im.naturalHeight && !ratios[url]) setRatios((r) => ({ ...r, [url]: im.naturalWidth / im.naturalHeight }))
  }

  const select = (i: number) => {
    const next = clamp(i, 0, n - 1)
    if (next === live.current.index) return
    set({ index: next, zoom: 1, pan: { x: 0, y: 0 } })
  }
  const toggleEnlarge = (on = !live.current.enlarged) => {
    if (single) return
    set({ enlarged: on, zoom: 1, pan: { x: 0, y: 0 } })
  }

  /* -- zoom & pan of the enlarged picture -------------------------------- */
  const stageRef = useRef<HTMLDivElement>(null)
  const panLimit = (z: number) => {
    const s = stageRef.current
    if (!s) return { x: 0, y: 0 }
    return { x: (s.clientWidth * (z - 1)) / 2, y: (s.clientHeight * (z - 1)) / 2 }
  }
  const clampPan = (p: { x: number; y: number }, z: number) => {
    const lim = panLimit(z)
    return { x: clamp(p.x, -lim.x, lim.x), y: clamp(p.y, -lim.y, lim.y) }
  }
  const zoomTo = useCallback((z: number) => {
    const s = live.current
    const old = clamp(s.zoom || 1, ZOOM_MIN, ZOOM_MAX)
    const nz = clamp(Math.round(z * 100) / 100, ZOOM_MIN, ZOOM_MAX)
    if (nz === old) return
    const k = nz / old
    onState({ ...s, zoom: nz, pan: nz <= 1 ? { x: 0, y: 0 } : clampPan({ x: s.pan.x * k, y: s.pan.y * k }, nz) })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [onState])

  useEffect(() => {
    const el = stageRef.current
    if (!el || !enlarged) return
    const onWheel = (e: WheelEvent) => {
      if (!(e.ctrlKey || e.metaKey)) return
      e.preventDefault()
      const z = clamp(live.current.zoom || 1, ZOOM_MIN, ZOOM_MAX)
      zoomTo(e.deltaY < 0 ? z * ZOOM_STEP : z / ZOOM_STEP)
    }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
  }, [enlarged, zoomTo])

  const drag = useRef<{ id: number; x: number; y: number; px: number; py: number } | null>(null)
  const [dragging, setDragging] = useState(false)
  const onDown = (e: RPointerEvent<HTMLDivElement>) => {
    if (zoom <= 1 || e.button !== 0) return
    e.preventDefault()
    e.currentTarget.setPointerCapture(e.pointerId)
    drag.current = { id: e.pointerId, x: e.clientX, y: e.clientY, px: pan.x, py: pan.y }
    setDragging(true)
  }
  const onMove = (e: RPointerEvent<HTMLDivElement>) => {
    const d = drag.current
    if (!d || d.id !== e.pointerId) return
    const p = clampPan({ x: d.px + e.clientX - d.x, y: d.py + e.clientY - d.y }, zoom)
    if (p.x !== live.current.pan.x || p.y !== live.current.pan.y) set({ pan: p })
  }
  const onUp = (e: RPointerEvent<HTMLDivElement>) => {
    if (drag.current?.id !== e.pointerId) return
    drag.current = null
    setDragging(false)
  }

  /* -- keyboard ---------------------------------------------------------- */
  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.altKey || (e.target as HTMLElement).closest('input, textarea, select')) return
    let handled = true
    switch (e.key) {
      case 'ArrowLeft': if (enlarged && zoom > 1) { set({ pan: clampPan({ x: pan.x + 60, y: pan.y }, zoom) }) } else select(index - 1); break
      case 'ArrowRight': if (enlarged && zoom > 1) { set({ pan: clampPan({ x: pan.x - 60, y: pan.y }, zoom) }) } else select(index + 1); break
      case 'Home': select(0); break
      case 'End': select(n - 1); break
      case 'Escape': if (state.enlarged && !single) toggleEnlarge(false); else handled = false; break
      case '+': case '=': if (enlarged) zoomTo(zoom * ZOOM_STEP); else handled = false; break
      case '-': case '_': if (enlarged) zoomTo(zoom / ZOOM_STEP); else handled = false; break
      case '0': if (enlarged) set({ zoom: 1, pan: { x: 0, y: 0 } }); else handled = false; break
      default: handled = false
    }
    if (handled) { e.preventDefault(); e.stopPropagation() }
  }

  /* -- keep the selected picture in view in whatever arrangement ---------- */
  const scrollRef = useRef<HTMLDivElement>(null)
  const stripRef = useRef<HTMLDivElement>(null)
  const firstScroll = useRef(true)
  useLayoutEffect(() => {
    if (enlarged) return
    const smooth = !firstScroll.current
    firstScroll.current = false
    const box = layout === 'focus' ? stripRef.current : scrollRef.current
    const el = box?.querySelector<HTMLElement>('[aria-current="true"]') ?? null
    centreIn(box, el, layout === 'across' || layout === 'focus' ? 'x' : 'y', smooth && layout === 'across')
  }, [index, layout, enlarged])
  useEffect(() => { firstScroll.current = true }, [layout])

  if (!current) return <div className="q2v-gallery"><div className="q2v-stage q2g-empty">No pictures.</div></div>

  /* -- the pieces -------------------------------------------------------- */
  const tile = (im: ViewImage, i: number, cls: string, fit: 'cover' | 'contain' = 'cover') => (
    <button
      key={i}
      type="button"
      className={`q2g-tile ${cls}`}
      aria-current={i === index ? 'true' : undefined}
      aria-label={`${im.name} (${i + 1} of ${n})`}
      title={im.name}
      onClick={() => select(i)}
      onDoubleClick={() => { select(i); if (!single) set({ index: i, enlarged: true, zoom: 1, pan: { x: 0, y: 0 } }) }}
    >
      <img src={im.url} alt={im.alt || im.name} loading="lazy" decoding="async" draggable={false} onLoad={learn(im.url)} style={{ objectFit: fit }} />
    </button>
  )

  let body: ReactNode
  if (enlarged) {
    body = (
      <div
        ref={stageRef}
        className={`q2v-stage q2g-enlarged${zoom > 1 ? ' is-zoomed' : ''}${dragging ? ' is-dragging' : ''}`}
        onPointerDown={onDown}
        onPointerMove={onMove}
        onPointerUp={onUp}
        onPointerCancel={onUp}
        onDoubleClick={() => (single ? set({ zoom: zoom > 1 ? 1 : 2, pan: { x: 0, y: 0 } }) : toggleEnlarge(false))}
      >
        <img
          key={current.url}
          src={current.url}
          alt={current.alt || current.name}
          draggable={false}
          onLoad={learn(current.url)}
          style={{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})` }}
        />
      </div>
    )
  } else if (layout === 'across') {
    body = (
      <div ref={scrollRef} className="q2v-stage q2g-across" role="list">
        {images.map((im, i) => {
          const r = ratios[im.url]
          return <div key={i} role="listitem" className="q2g-slide" style={r ? ({ '--r': String(r) } as CSSProperties) : undefined}>{tile(im, i, '', 'contain')}</div>
        })}
      </div>
    )
  } else if (layout === 'grid') {
    body = <div ref={scrollRef} className="q2v-stage q2g-grid">{images.map((im, i) => tile(im, i, ''))}</div>
  } else if (layout === 'mosaic') {
    body = <div ref={scrollRef} className="q2v-stage q2g-mosaic">{images.map((im, i) => tile(im, i, spanOf(ratios[im.url], i)))}</div>
  } else {
    body = (
      <div className="q2g-focus">
        <div className="q2g-main" onDoubleClick={() => toggleEnlarge(true)}>
          <img key={current.url} src={current.url} alt={current.alt || current.name} draggable={false} onLoad={learn(current.url)} />
        </div>
        {!single && <div ref={stripRef} className="q2g-strip">{images.map((im, i) => tile(im, i, 'q2g-thumb'))}</div>}
      </div>
    )
  }

  return (
    <div className={`q2v-gallery${column ? ' is-column' : ''}`} tabIndex={0} onKeyDown={onKey} aria-label="Pictures" role="region">
      <div className="q2v-bar">
        {!single && (
          <div className="q2v-seg" role="group" aria-label="Arrangement">
            {LAYOUTS.map((l) => (
              <button
                key={l.id}
                type="button"
                className="q2v-btn"
                aria-pressed={layout === l.id && !state.enlarged}
                aria-label={l.label}
                title={l.label}
                onClick={() => set({ layout: l.id, enlarged: false, zoom: 1, pan: { x: 0, y: 0 } })}
              >
                <Icon>{l.icon}</Icon>{!column && <span>{l.label}</span>}
              </button>
            ))}
          </div>
        )}
        {!single && <span className="q2v-sep" />}
        {!single && (
          <div className="q2v-group">
            <button type="button" className="q2v-btn" aria-label="Previous picture" title="Previous (←)" disabled={index <= 0} onClick={() => select(index - 1)}><Icon>{I.prev}</Icon></button>
            <span className="q2v-num" aria-live="polite">{index + 1} / {n}</span>
            <button type="button" className="q2v-btn" aria-label="Next picture" title="Next (→)" disabled={index >= n - 1} onClick={() => select(index + 1)}><Icon>{I.next}</Icon></button>
          </div>
        )}
        <span className="q2g-name" title={current.name}>{current.name}</span>
        <span className="q2v-grow" />
        {enlarged && (
          <div className="q2v-group" role="group" aria-label="Zoom">
            <button type="button" className="q2v-btn" aria-label="Zoom out" title="Zoom out (−)" disabled={zoom <= ZOOM_MIN} onClick={() => zoomTo(zoom / ZOOM_STEP)}><Icon>{I.minus}</Icon></button>
            <button type="button" className="q2v-btn q2g-pct" aria-label="Fit picture" title="Fit (0)" onClick={() => set({ zoom: 1, pan: { x: 0, y: 0 } })}>{Math.round(zoom * 100)}%</button>
            <button type="button" className="q2v-btn" aria-label="Zoom in" title="Zoom in (+)" disabled={zoom >= ZOOM_MAX} onClick={() => zoomTo(zoom * ZOOM_STEP)}><Icon>{I.plus}</Icon></button>
          </div>
        )}
        {!single && (
          <button type="button" className="q2v-btn" aria-pressed={state.enlarged} aria-label={state.enlarged ? 'Leave enlarged view' : 'Enlarge picture'} title={state.enlarged ? 'Leave enlarged view (Esc)' : 'Enlarge (double-click)'} onClick={() => toggleEnlarge()}>
            <Icon>{state.enlarged ? I.shrink : I.enlarge}</Icon>{!column && <span>{state.enlarged ? 'Back' : 'Enlarge'}</span>}
          </button>
        )}
      </div>
      <div className="q2v-body">{body}</div>
    </div>
  )
}
