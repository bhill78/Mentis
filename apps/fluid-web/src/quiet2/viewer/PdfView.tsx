/* PDF documents (Builder: document viewer), drawn by pdf.js.
 *
 * Three presentations of one loaded document, switched without reloading:
 *   single  one page, centred, navigated page by page;
 *   spread  two adjacent pages side by side at one scale, navigated by
 *           spread. Page 1 sits alone as the cover, then 2–3, 4–5, … as in a
 *           printed book. state.page is any page of the spread shown (the
 *           page the reader was on is kept when switching modes); navigating
 *           sets it to the spread's left page.
 *   scroll  every page in a column with visible gaps, rendered lazily as it
 *           nears the viewport; state.page follows the scroll, and a change
 *           of state.page from elsewhere (page box, rail, keys) scrolls there.
 *
 * The document is loaded once per url for the life of the page (pdfDoc.ts),
 * so a remount (the frame moving the viewer) never refetches. Every canvas is
 * drawn at the device's pixel ratio and redrawn when its size changes. */
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import type { PDFDocumentProxy } from 'pdfjs-dist'
import { loadPdf, outlineOf, UNIT, type LoadedPdf, type OutlineEntry, type PageSize } from './pdfDoc'
import type { PdfMode, PdfState, RendererProps } from './types'
import './pdf.css'

const ZOOM_STEPS = [0.5, 0.67, 0.75, 0.9, 1, 1.1, 1.25, 1.5, 1.75, 2, 2.5, 3]
const GAP = 16 // between pages (spread and scroll)
/** Largest canvas we draw, in device pixels: beyond this browsers fail silently. */
const MAX_PIXELS = 16_000_000

type Props = RendererProps<PdfState> & { url: string; name: string }
type Load = { status: 'loading' } | { status: 'ready'; pdf: LoadedPdf } | { status: 'error'; message: string }

export default function PdfView({ url, name, state, onState, placement }: Props) {
  /* -- the document ------------------------------------------------------- */
  const [load, setLoad] = useState<Load>({ status: 'loading' })
  useEffect(() => {
    let live = true
    setLoad({ status: 'loading' })
    loadPdf(url).then(
      (pdf) => { if (live) setLoad({ status: 'ready', pdf }) },
      (e: unknown) => { if (live) setLoad({ status: 'error', message: e instanceof Error ? e.message : String(e) }) },
    )
    return () => { live = false }
  }, [url])
  const pdf = load.status === 'ready' ? load.pdf : null
  const count = pdf?.doc.numPages ?? 0

  /* the latest state, for handlers that outlive a render */
  const stateRef = useRef(state)
  stateRef.current = state
  const set = useCallback((patch: Partial<PdfState>) => onState({ ...stateRef.current, ...patch }), [onState])

  const page = count ? clamp(state.page, 1, count) : 1

  /* -- room ---------------------------------------------------------------- */
  const rootRef = useRef<HTMLDivElement>(null)
  const [stage, setStage] = useState<HTMLDivElement | null>(null)
  const [room, setRoom] = useState({ w: 0, h: 0, rootW: 0 })
  useEffect(() => {
    const root = rootRef.current
    if (!stage || !root) return
    const measure = () => setRoom((r) => {
      const n = { w: stage.clientWidth, h: stage.clientHeight, rootW: root.clientWidth }
      return n.w === r.w && n.h === r.h && n.rootW === r.rootW ? r : n
    })
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(stage)
    ro.observe(root)
    return () => ro.disconnect()
  }, [stage])
  const dpr = useDpr()
  const compact = placement === 'column' || (room.rootW > 0 && room.rootW < 700)
  const pad = compact ? 12 : 24

  /* -- layout: what is shown, at what scale (CSS px per PDF point) --------- */
  const spreadPages = pdf && state.mode === 'spread' ? spreadOf(page, count) : [page]
  const layout = useMemo(() => {
    if (!pdf || room.w === 0) return null
    const availW = Math.max(40, room.w - 2 * pad - 1)
    const availH = Math.max(40, room.h - 2 * pad - 1)
    let boxW: number, boxH: number, gaps = 0
    if (state.mode === 'scroll') {
      boxW = Math.max(...pdf.sizes.map((s) => s.w))
      boxH = Math.max(...pdf.sizes.map((s) => s.h))
    } else {
      const shown = (state.mode === 'spread' ? spreadPages : [page]).map((n) => pdf.sizes[n - 1])
      boxW = shown.reduce((a, s) => a + s.w, 0)
      boxH = Math.max(...shown.map((s) => s.h))
      gaps = GAP * (shown.length - 1) // the gap between pages stays fixed in px
    }
    const fitW = (availW - gaps) / boxW
    const fitP = Math.min(fitW, availH / boxH)
    const scale = state.zoom === 'width' ? fitW : state.zoom === 'page' ? fitP : state.zoom * UNIT
    return { scale, percent: Math.round((scale / UNIT) * 100) }
    // spreadPages is derived from page and count
  }, [pdf, room.w, room.h, pad, state.mode, state.zoom, page, count])

  /* -- navigation ----------------------------------------------------------- */
  const prevPage = state.mode === 'spread' ? (spreadPages[0] <= 1 ? null : spreadOf(spreadPages[0] - 1, count)[0]) : page > 1 ? page - 1 : null
  const nextPage = state.mode === 'spread' ? (spreadPages[spreadPages.length - 1] >= count ? null : spreadPages[spreadPages.length - 1] + 1) : page < count ? page + 1 : null
  const go = useCallback((n: number) => { if (count) set({ page: clamp(n, 1, count) }) }, [count, set])
  /* a new page or spread in single/spread mode starts at its top */
  const shownKey = state.mode === 'scroll' ? 'scroll' : `${state.mode}:${spreadPages[0]}`
  useLayoutEffect(() => {
    if (stage && shownKey !== 'scroll') stage.scrollTop = 0
  }, [stage, shownKey])

  const zoomBy = (dir: 1 | -1) => {
    const cur = layout ? layout.scale / UNIT : 1
    const next = dir > 0 ? ZOOM_STEPS.find((z) => z > cur + 0.005) ?? 3 : [...ZOOM_STEPS].reverse().find((z) => z < cur - 0.005) ?? 0.5
    set({ zoom: next })
  }

  const onKeyDown = (e: React.KeyboardEvent) => {
    const t = e.target as HTMLElement
    if (t.closest('input, textarea, select, [contenteditable="true"]') || e.altKey || e.ctrlKey || e.metaKey) return
    let to: number | null = null
    switch (e.key) {
      case 'ArrowLeft': case 'PageUp': to = prevPage; break
      case 'ArrowRight': case 'PageDown': to = nextPage; break
      case 'Home': to = 1; break
      case 'End': to = state.mode === 'spread' ? spreadOf(count, count)[0] : count; break
      default: return
    }
    e.preventDefault()
    if (to != null) go(to)
  }

  /* -- render --------------------------------------------------------------- */
  const shownLabel = state.mode === 'spread' && spreadPages.length > 1 ? `Pages ${spreadPages[0]}–${spreadPages[1]} of ${count}` : `Page ${page} of ${count}`
  return (
    <div ref={rootRef} className={'q2v-pdf' + (compact ? ' is-compact' : '')} onKeyDown={onKeyDown}>
      <div className="q2v-bar" role="toolbar" aria-label="Document">
        <div className="q2v-seg" role="group" aria-label="Presentation">
          <ModeBtn mode="single" cur={state.mode} set={set} compact={compact} icon={<IconSingle />} label="Single" />
          <ModeBtn mode="spread" cur={state.mode} set={set} compact={compact} icon={<IconSpread />} label="Spread" />
          <ModeBtn mode="scroll" cur={state.mode} set={set} compact={compact} icon={<IconScroll />} label="Scroll" />
        </div>
        <span className="q2v-sep" />
        <div className="q2v-group" role="group" aria-label="Pages">
          <button type="button" className="q2v-btn" aria-label={state.mode === 'spread' ? 'Previous spread' : 'Previous page'} title="Previous (←)" disabled={prevPage == null} onClick={() => prevPage != null && go(prevPage)}><IconChevron dir={-1} /></button>
          <PageBox page={spreadPages[0]} last={spreadPages.length > 1 ? spreadPages[1] : null} count={count} go={go} />
          <button type="button" className="q2v-btn" aria-label={state.mode === 'spread' ? 'Next spread' : 'Next page'} title="Next (→)" disabled={nextPage == null} onClick={() => nextPage != null && go(nextPage)}><IconChevron dir={1} /></button>
        </div>
        <span className="q2v-grow" />
        <div className="q2v-group" role="group" aria-label="Zoom">
          <button type="button" className="q2v-btn" aria-pressed={state.zoom === 'page'} aria-label="Fit page" title="Fit page" onClick={() => set({ zoom: 'page' })}><IconFitPage />{!compact && 'Page'}</button>
          <button type="button" className="q2v-btn" aria-pressed={state.zoom === 'width'} aria-label="Fit width" title="Fit width" onClick={() => set({ zoom: 'width' })}><IconFitWidth />{!compact && 'Width'}</button>
          <button type="button" className="q2v-btn" aria-label="Zoom out" title="Zoom out" disabled={!layout || layout.scale / UNIT <= 0.5 + 0.005} onClick={() => zoomBy(-1)}><IconMinus /></button>
          <span className="q2v-num q2v-pdf-pct" aria-live="polite" aria-label={`Zoom ${layout?.percent ?? 100}%`}>{layout ? `${layout.percent}%` : '–'}</span>
          <button type="button" className="q2v-btn" aria-label="Zoom in" title="Zoom in" disabled={!layout || layout.scale / UNIT >= 3 - 0.005} onClick={() => zoomBy(1)}><IconPlus /></button>
        </div>
        <span className="q2v-sep" />
        <div className="q2v-group" role="group" aria-label="Side rail">
          <button type="button" className="q2v-btn" aria-pressed={state.rail === 'thumbs'} aria-label="Page thumbnails" title="Page thumbnails" onClick={() => set({ rail: state.rail === 'thumbs' ? 'none' : 'thumbs' })}><IconThumbs /></button>
          <button type="button" className="q2v-btn" aria-pressed={state.rail === 'outline'} aria-label="Outline" title="Outline" onClick={() => set({ rail: state.rail === 'outline' ? 'none' : 'outline' })}><IconOutline /></button>
        </div>
      </div>
      <div className="q2v-body">
        {pdf && state.rail === 'thumbs' && <Thumbs pdf={pdf} shown={state.mode === 'spread' ? spreadPages : [page]} go={go} dpr={dpr} compact={compact} />}
        {pdf && state.rail === 'outline' && <Outline doc={pdf.doc} page={page} go={go} />}
        <div ref={setStage} className={'q2v-stage q2v-pdf-stage is-' + state.mode} tabIndex={0} aria-label={`${name}, ${count ? shownLabel : 'loading'}`}>
          {load.status === 'loading' && <p className="q2v-pdf-note">Reading the document…</p>}
          {load.status === 'error' && (
            <div className="q2v-pdf-note is-error" role="alert">
              <p><strong>{name || 'This PDF'}</strong> could not be opened.</p>
              <p className="q2v-pdf-detail">pdf.js could not read it{load.message ? `: ${load.message}` : '.'}</p>
            </div>
          )}
          {pdf && layout && state.mode !== 'scroll' && (
            <div className="q2v-pdf-center" style={{ padding: pad }}>
              <div className="q2v-pdf-spread" style={{ gap: GAP }}>
                {(state.mode === 'spread' ? spreadPages : [page]).map((n) => (
                  <PageCanvas key={n} doc={pdf.doc} n={n} count={count} size={pdf.sizes[n - 1]} scale={layout.scale} dpr={dpr} active />
                ))}
              </div>
            </div>
          )}
          {pdf && layout && state.mode === 'scroll' && stage && (
            <ScrollColumn pdf={pdf} page={page} scale={layout.scale} pad={pad} dpr={dpr} stage={stage} set={set} />
          )}
        </div>
      </div>
      <p className="q2v-pdf-sr" aria-live="polite">{count ? shownLabel : ''}</p>
    </div>
  )
}

/* -- scroll mode ------------------------------------------------------------ */

function ScrollColumn({ pdf, page, scale, pad, dpr, stage, set }: {
  pdf: LoadedPdf; page: number; scale: number; pad: number; dpr: number; stage: HTMLDivElement; set: (p: Partial<PdfState>) => void
}) {
  const count = pdf.sizes.length
  /* each page's top and height in the column, in CSS px */
  const geo = useMemo(() => {
    let y = pad
    return pdf.sizes.map((s) => { const h = Math.round(s.h * scale); const g = { top: y, h }; y += h + GAP; return g })
  }, [pdf.sizes, scale, pad])
  /* the page the stage is showing, and how far into it: kept so a change of
   * scale (zoom, resize) keeps the reader's place, and so a change of
   * state.page from elsewhere can be told apart from one the scroll made */
  const where = useRef<{ page: number; frac: number } | null>(null)
  const pageRef = useRef(page)
  pageRef.current = page

  const pageAt = useCallback((y: number) => {
    let n = 0
    while (n < count - 1 && geo[n + 1].top - GAP / 2 <= y) n++
    return n + 1
  }, [geo, count])

  const onScroll = useCallback(() => {
    const probe = stage.scrollTop + Math.min(stage.clientHeight * 0.35, 240)
    const n = pageAt(probe)
    const g = geo[n - 1]
    where.current = { page: n, frac: clamp((stage.scrollTop - g.top) / Math.max(1, g.h), -0.5, 1) }
    if (n !== pageRef.current) set({ page: n })
  }, [stage, pageAt, geo, set])

  useEffect(() => {
    stage.addEventListener('scroll', onScroll, { passive: true })
    return () => stage.removeEventListener('scroll', onScroll)
  }, [stage, onScroll])

  /* scale changed: put the reader back where they were */
  useLayoutEffect(() => {
    const w = where.current
    if (!w) return
    const g = geo[w.page - 1]
    if (g) stage.scrollTop = g.top + w.frac * g.h
  }, [geo, stage])

  /* state.page changed from elsewhere (or on entering scroll mode): go there */
  useLayoutEffect(() => {
    if (where.current?.page === page) return
    const g = geo[page - 1]
    if (!g) return
    stage.scrollTop = Math.max(0, g.top - pad / 2)
    where.current = { page, frac: 0 }
  }, [page, geo, stage, pad])

  const width = Math.max(...pdf.sizes.map((s) => Math.round(s.w * scale)))
  const height = geo.length ? geo[geo.length - 1].top + geo[geo.length - 1].h + pad : 0
  return (
    <div className="q2v-pdf-column" style={{ height, minWidth: width + 2 * pad, padding: `0 ${pad}px` }}>
      {pdf.sizes.map((s, i) => (
        <LazyPage key={i} root={stage} top={geo[i].top}>
          {(near) => <PageCanvas doc={pdf.doc} n={i + 1} count={count} size={s} scale={scale} dpr={dpr} active={near} current={i + 1 === page} />}
        </LazyPage>
      ))}
    </div>
  )
}

/** A page slot that knows whether it is near the visible part of `root`. */
function LazyPage({ root, top, children }: { root: HTMLElement; top: number; children: (near: boolean) => ReactNode }) {
  const ref = useRef<HTMLDivElement>(null)
  const near = useNear(ref, root, '800px 200px')
  return <div ref={ref} className="q2v-pdf-slot" style={{ top }}>{children(near)}</div>
}

/* -- one page ----------------------------------------------------------------- */

function PageCanvas({ doc, n, count, size, scale, dpr, active, current, thumb }: {
  doc: PDFDocumentProxy; n: number; count: number; size: PageSize; scale: number; dpr: number; active: boolean; current?: boolean; thumb?: boolean
}) {
  const host = useRef<HTMLDivElement>(null)
  const w = Math.max(1, Math.round(size.w * scale))
  const h = Math.max(1, Math.round(size.h * scale))
  const label = `Page ${n} of ${count}`
  useEffect(() => {
    const el = host.current
    if (!el) return
    if (!active) { el.replaceChildren(); return }
    let cancelled = false
    let task: { cancel: () => void } | null = null
    doc.getPage(n).then((pg) => {
      if (cancelled) return
      const base = pg.getViewport({ scale: 1 })
      let s = (w * dpr) / base.width
      const area = base.width * base.height * s * s
      if (area > MAX_PIXELS) s *= Math.sqrt(MAX_PIXELS / area)
      const vp = pg.getViewport({ scale: s })
      const canvas = document.createElement('canvas')
      canvas.width = Math.max(1, Math.floor(vp.width))
      canvas.height = Math.max(1, Math.floor(vp.height))
      canvas.setAttribute('role', 'img')
      canvas.setAttribute('aria-label', label)
      const ctx = canvas.getContext('2d')
      if (!ctx) return
      const t = pg.render({ canvasContext: ctx, viewport: vp })
      task = t
      t.promise.then(() => { if (!cancelled) el.replaceChildren(canvas) }, () => { /* cancelled or failed: keep what is shown */ })
    }, () => { /* page could not be read */ })
    return () => { cancelled = true; task?.cancel() }
  }, [doc, n, w, h, dpr, active, label])
  return (
    <div ref={host} className={'q2v-pdf-page' + (thumb ? ' is-thumb' : '') + (current ? ' is-current' : '')}
      style={{ width: w, height: h }} data-page={n} aria-label={thumb ? undefined : label} role={thumb ? undefined : 'img'} />
  )
}

/* -- the rail ----------------------------------------------------------------- */

function Thumbs({ pdf, shown, go, dpr, compact }: { pdf: LoadedPdf; shown: number[]; go: (n: number) => void; dpr: number; compact: boolean }) {
  const [rail, setRail] = useState<HTMLElement | null>(null)
  const tw = compact ? 76 : 112
  const first = shown[0]
  useEffect(() => {
    rail?.querySelector(`[data-thumb="${first}"]`)?.scrollIntoView({ block: 'nearest' })
  }, [rail, first])
  return (
    <nav ref={setRail} className="q2v-rail q2v-pdf-rail" aria-label="Page thumbnails">
      {rail && pdf.sizes.map((s, i) => {
        const n = i + 1
        const on = shown.includes(n)
        return (
          <button key={n} type="button" data-thumb={n} className={'q2v-pdf-thumb' + (on ? ' is-on' : '')} aria-current={on ? 'page' : undefined}
            aria-label={`Go to page ${n}`} onClick={() => go(n)}>
            <LazyThumb root={rail}>{(near) => <PageCanvas doc={pdf.doc} n={n} count={pdf.sizes.length} size={s} scale={tw / s.w} dpr={dpr} active={near} thumb />}</LazyThumb>
            <span className="q2v-pdf-thumb-n">{n}</span>
          </button>
        )
      })}
    </nav>
  )
}

function LazyThumb({ root, children }: { root: HTMLElement; children: (near: boolean) => ReactNode }) {
  const ref = useRef<HTMLSpanElement>(null)
  const near = useNear(ref, root, '400px 0px')
  return <span ref={ref} className="q2v-pdf-thumb-img">{children(near)}</span>
}

function Outline({ doc, page, go }: { doc: PDFDocumentProxy; page: number; go: (n: number) => void }) {
  const [items, setItems] = useState<OutlineEntry[] | null>(null)
  useEffect(() => {
    let live = true
    outlineOf(doc).then((o) => { if (live) setItems(o) })
    return () => { live = false }
  }, [doc])
  /* the section being read: the last entry starting at or before the page */
  let cur = -1
  items?.forEach((it, i) => { if (it.page != null && it.page <= page) cur = i })
  return (
    <nav className="q2v-rail q2v-pdf-rail q2v-pdf-outline" aria-label="Outline">
      {items == null ? <p className="q2v-pdf-empty">Reading the outline…</p>
        : items.length === 0 ? <p className="q2v-pdf-empty">No outline in this document</p>
          : (
            <ul>
              {items.map((it, i) => (
                <li key={i} style={{ paddingLeft: Math.min(it.depth, 4) * 12 }}>
                  <button type="button" disabled={it.page == null} aria-current={i === cur ? 'location' : undefined}
                    className={i === cur ? 'is-on' : undefined} onClick={() => it.page != null && go(it.page)}
                    title={it.page != null ? `${it.title} — page ${it.page}` : it.title}>
                    <span className="q2v-pdf-outline-t">{it.title}</span>
                    {it.page != null && <span className="q2v-pdf-outline-p">{it.page}</span>}
                  </button>
                </li>
              ))}
            </ul>
          )}
    </nav>
  )
}

/* -- toolbar pieces ------------------------------------------------------------ */

function ModeBtn({ mode, cur, set, compact, icon, label }: { mode: PdfMode; cur: PdfMode; set: (p: Partial<PdfState>) => void; compact: boolean; icon: ReactNode; label: string }) {
  return (
    <button type="button" className="q2v-btn" aria-pressed={cur === mode} aria-label={`${label} page${mode === 'scroll' ? 's, scrolling' : mode === 'spread' ? 's side by side' : ''}`}
      title={label} onClick={() => set({ mode })}>
      {icon}{!compact && label}
    </button>
  )
}

function PageBox({ page, last, count, go }: { page: number; last: number | null; count: number; go: (n: number) => void }) {
  const [text, setText] = useState(String(page))
  useEffect(() => setText(String(page)), [page])
  const commit = () => {
    const n = parseInt(text, 10)
    if (Number.isFinite(n)) go(n)
    else setText(String(page))
  }
  return (
    <span className="q2v-num">
      <input aria-label={`Page number, ${count} pages`} inputMode="numeric" value={text} disabled={!count}
        onChange={(e) => setText(e.target.value.replace(/[^0-9]/g, ''))}
        onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); commit() } else if (e.key === 'Escape') setText(String(page)) }}
        onBlur={commit} onFocus={(e) => e.target.select()} />
      {last != null ? `–${last}` : ''} / {count || '–'}
    </span>
  )
}

const svg = { width: 15, height: 15, viewBox: '0 0 16 16', fill: 'none', stroke: 'currentColor', strokeWidth: 1.4, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const, 'aria-hidden': true }
const IconSingle = () => <svg {...svg}><rect x="4" y="2" width="8" height="12" rx="1" /></svg>
const IconSpread = () => <svg {...svg}><rect x="1.5" y="3" width="6" height="10" rx="1" /><rect x="8.5" y="3" width="6" height="10" rx="1" /></svg>
const IconScroll = () => <svg {...svg}><rect x="4" y="1" width="8" height="6" rx="1" /><rect x="4" y="9" width="8" height="6" rx="1" /></svg>
const IconChevron = ({ dir }: { dir: 1 | -1 }) => <svg {...svg}><path d={dir < 0 ? 'M10 3 5 8l5 5' : 'M6 3l5 5-5 5'} /></svg>
const IconFitPage = () => <svg {...svg}><rect x="4" y="2" width="8" height="12" rx="1" /><path d="M2 5V2h3M14 5V2h-3M2 11v3h3M14 11v3h-3" strokeWidth={1.1} /></svg>
const IconFitWidth = () => <svg {...svg}><path d="M1.5 8h13M4 5.5 1.5 8 4 10.5M12 5.5l2.5 2.5-2.5 2.5" /></svg>
const IconMinus = () => <svg {...svg}><path d="M3.5 8h9" /></svg>
const IconPlus = () => <svg {...svg}><path d="M3.5 8h9M8 3.5v9" /></svg>
const IconThumbs = () => <svg {...svg}><rect x="2" y="1.5" width="5" height="6" rx=".8" /><rect x="2" y="9" width="5" height="5.5" rx=".8" /><path d="M9.5 3h4.5M9.5 5.5h3M9.5 11h4.5M9.5 13.5h3" /></svg>
const IconOutline = () => <svg {...svg}><path d="M2 3h12M4.5 6.5H14M4.5 10H14M2 13.5h12" /></svg>

/* -- helpers -------------------------------------------------------------------- */

function clamp(n: number, lo: number, hi: number) { return Math.min(hi, Math.max(lo, n)) }

/** The pages shown together with page n in a spread: 1 alone (the cover),
 *  then 2–3, 4–5, …; a last even page stands alone. */
function spreadOf(n: number, count: number): number[] {
  if (count <= 1 || n <= 1) return [1]
  const left = n % 2 === 0 ? n : n - 1
  return left + 1 <= count ? [left, left + 1] : [left]
}

function useNear(ref: React.RefObject<HTMLElement | null>, root: HTMLElement, margin: string) {
  const [near, setNear] = useState(false)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const io = new IntersectionObserver((es) => setNear(es[es.length - 1].isIntersecting), { root, rootMargin: margin })
    io.observe(el)
    return () => io.disconnect()
  }, [ref, root, margin])
  return near
}

function useDpr() {
  const [dpr, setDpr] = useState(() => window.devicePixelRatio || 1)
  useEffect(() => {
    const on = () => setDpr(window.devicePixelRatio || 1)
    window.addEventListener('resize', on)
    return () => window.removeEventListener('resize', on)
  }, [])
  return dpr
}
