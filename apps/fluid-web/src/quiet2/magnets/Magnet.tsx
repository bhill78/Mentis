import { useEffect, useId, useLayoutEffect, useRef, useState, useSyncExternalStore } from 'react'
import type { CSSProperties, PointerEvent as ReactPointerEvent, ReactNode } from 'react'
import type { MagnetPlaceKey, MagnetResource, MagnetSnapshot, MagnetTab } from './contract'
import { MAGNET_TABS } from './contract'
import { magnetIndicators } from './indicators'
import { retainedFiles } from './Inspection'
import { closeInspect, closeOverlay, goTab, leaveSettings, openOverlay, place, placeKeyOf, registerViewScroll, remember, setOpen } from './places'
import { pendingScroll, reachedScroll, savesReportedScroll } from './position'
import { supportsManualCollection } from './configuration'
import './magnet.css'

const PUCK = 64
const GAP = 12
/** The approved card is 650 px, 900 px when expanded, and full width on a narrow screen. */
const NARROW = 700
const WIDTHS = { narrow: 650, wide: 900 }
export const DRAG_THRESHOLD = 7
/** Which place the card is showing. The frame has no compact content state. */
export const magnetView = (s: MagnetSnapshot): MagnetPlaceKey => placeKeyOf(s)
export const magnetScroll = (s: MagnetSnapshot) => { const p = place(s); return p.inspected ? p.inspectScroll : p.scroll }

/** Whether the saved reading position is written into the scroll container, and
 *  what is written. `null` is "leave the container alone".
 *
 *  The saved number moves for two different reasons and only one of them is a
 *  navigation. A reader scrolling moves the container first, and the scroll
 *  handler below writes the number from that same event -- so a number equal to
 *  what the container last reported is the reader's own, and writing it back is
 *  at best nothing and at worst a pull backwards out of a gesture still in
 *  flight. A navigation writes the number instead, while the container stays
 *  where it is: a tab, an inspection, and inside one view the search's typing,
 *  filtering, opening a result and Back to results, none of which change which
 *  place is shown. That is the one the frame has to apply.
 *
 *  `reported` is the position the container last reported, or `null` before it
 *  has reported one -- a mount or a remount always restores what was saved.
 *  Comparing against the container's own report rather than against its live
 *  offset matters because the offset moves without reporting: the browser's
 *  scroll anchoring shifts it when content above a result list changes, and a
 *  shorter view clamps it. */
export function scrollToApply(reported: number | null, live: number, want: number): number | null {
  const wanted = Number.isFinite(want) && want > 0 ? Math.round(want) : 0
  if (Math.abs(live - wanted) < 1) return null
  if (reported !== null && Math.abs(reported - wanted) < 1) return null
  return wanted
}

/** Puck coordinates belong to this canvas, never to a saved arrangement. */
export function clampPuck(x: number, y: number, width: number, height: number) {
  return { x: Math.max(GAP, Math.min(Number.isFinite(x) ? x : GAP, Math.max(GAP, width - PUCK - GAP))),
    y: Math.max(GAP, Math.min(Number.isFinite(y) ? y : GAP, Math.max(GAP, height - PUCK - GAP))) }
}

/** Keep the card joined to its puck, flipping at the edge rather than detaching.
 *  `wide` is a width only: the card's content never changes with it. */
export function cardGeometry(x: number, y: number, width: number, height: number, wide = false) {
  const want = width <= NARROW ? width - GAP * 2 : wide ? WIDTHS.wide : WIDTHS.narrow
  const cardWidth = Math.min(want, Math.max(0, width - GAP * 2))
  const right = x + 32 + cardWidth > width - GAP
  const left = right ? Math.max(GAP - x, PUCK - 32 - cardWidth) : Math.min(32, width - GAP - x - cardWidth)
  const maxHeight = Math.max(80, Math.min(wide ? 740 : 650, height - GAP * 2))
  const top = Math.max(GAP - y, Math.min(0, height - GAP - y - maxHeight))
  return { left, top, width: cardWidth, maxHeight, flip: right }
}

/** The resting puck's name sits under it, shifted so it never leaves the canvas.
 *  Centred under the puck where there is room; pushed in at either edge. */
const REST_TITLE = 116
export function restTitleOffset(x: number, width: number) {
  return Math.round(Math.max(GAP - x, Math.min(-26, width - GAP - x - REST_TITLE)))
}

export function activityWords(activity: unknown, previousOpen?: number) {
  if (typeof activity !== 'number' || !Number.isFinite(activity) || activity < 0) return 'Source activity unavailable.'
  if (!previousOpen) return 'Source activity reported; no last-open baseline in this tab yet.'
  return activity * 1000 > previousOpen ? 'Source activity is newer than this tab’s last-open time.' : 'No newer source activity reported since this tab last opened it.'
}

/** One component per place. Other parts supply these; they do not edit the frame. */
export type MagnetViews = Partial<Record<MagnetPlaceKey, ReactNode>>

export interface MagnetProps {
  resource: MagnetResource
  views?: MagnetViews
  /** H2's persistent composer. Present on every tab and in search; never in settings. */
  footerComposer?: ReactNode
  /** H4's search line. The frame renders its own when none is supplied. */
  searchToolbar?: ReactNode
  canCollect?: boolean
  onExpand: () => void
  onCollapse: () => void
}

/** The frame: the puck, the card geometry, the view-state spine and six slots --
 *  header, tabs, searchToolbar, view (the only scroll container), footerComposer
 *  and foot. Nothing else lives here; every view is supplied. */
export default function Magnet({ resource, views, footerComposer, searchToolbar, canCollect = false, onExpand, onCollapse }: MagnetProps) {
  const s = useSyncExternalStore(resource.subscribe, resource.snapshot, resource.snapshot)
  const root = useRef<HTMLDivElement>(null)
  const view = useRef<HTMLDivElement>(null)
  /** The view's content box, watched only so that a saved reading position the
   *  container could not reach is applied when the content arrives. */
  const content = useRef<HTMLDivElement>(null)
  /** A saved reading position that was written into the view and clamped,
   *  because the content it belongs to had not arrived yet. Kept with its own
   *  element, so a remounted card never measures itself against a container it
   *  no longer has. */
  const waiting = useRef<{ el: HTMLDivElement; want: number } | null>(null)
  const puck = useRef<HTMLButtonElement>(null)
  const drag = useRef<{ pointer: number; x: number; y: number; startX: number; startY: number; moved: boolean } | null>(null)
  const suppress = useRef(false)
  /** The position the view container last reported through its scroll handler,
   *  kept with the element so a remounted card restores its saved position
   *  rather than measuring itself against the container it no longer has. */
  const reported = useRef<{ el: HTMLDivElement; top: number } | null>(null)
  const [dragging, setDragging] = useState(false)
  const [size, setSize] = useState({ width: 1024, height: 768 })
  const cardId = useId()
  const viewId = useId()
  const settingsId = useId()
  // The card is open because it was clicked open. Hover and focus change nothing.
  const open = s.open
  const saved = resource.saved
  const title = s.title || saved.name || 'Magnet'
  const posts = s.results.filter((r) => r.kind === 'post')
  const files = retainedFiles(s.results)
  const tally = s.summary?.summary?.posts
  const postCount = typeof tally === 'number' && Number.isFinite(tally) && tally >= 0 ? tally : null
  const partial = !!s.next || (s.status != null && s.status !== 'ok')
  const filesKnown = files.length > 0 || s.status === 'ok' || s.status === 'partial'
  const indicators = magnetIndicators({ retained: true, postsSourceTally: postCount, filesLoaded: files.length, filesKnown, filesPartial: partial })
  const collectable = !!saved.config && supportsManualCollection(saved.config)
  // Never fabricate a count: unknown until a retained read has returned.
  const counted = s.activation !== undefined ? posts.length + files.length : null
  const here = place(s)
  const geometry = cardGeometry(s.x, s.y, size.width, size.height, s.wide)
  const placeKey = placeKeyOf(s)
  const wantScroll = magnetScroll(s)
  /** The opened search result is a surface of its own inside the search place,
   *  so a change of target is a change of what is being read. Kept as a scalar
   *  so the reconciliation below runs on the target changing, not on the
   *  snapshot handing out a new object for the same target. */
  const targetKey = s.searchTarget ? `${s.searchTarget.kind}/${s.searchTarget.item ?? ''}/${s.searchTarget.lens ?? ''}/${s.searchTarget.message ?? ''}` : ''

  useEffect(() => registerViewScroll(resource, () => view.current?.scrollTop ?? 0), [resource])
  // The one place the saved reading position reaches the DOM. It follows the
  // saved number itself, not only a change of place: navigation inside one view
  // moves that number while `placeKey` and the inspection stay as they are. And
  // what the container could not take -- a view that renders before its posts
  // have been read clamps the offset to its short content -- is kept, not lost.
  useLayoutEffect(() => {
    const el = view.current
    if (!el) { waiting.current = null; return }
    const apply = scrollToApply(reported.current?.el === el ? reported.current.top : null, el.scrollTop, wantScroll)
    if (apply === null) { waiting.current = null; return }
    el.scrollTop = apply
    const want = pendingScroll(el.scrollTop, apply)
    waiting.current = want === null ? null : { el, want }
  }, [open, placeKey, here.inspected, targetKey, s.loading, wantScroll])
  /** The content's own growth is what applies a kept position -- no timer, no
   *  polling, and it ends with the card. */
  useEffect(() => {
    const el = view.current, inner = content.current
    if (!open || !el || !inner || typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(() => {
      const kept = waiting.current
      if (!kept || kept.el !== el) return
      el.scrollTop = kept.want
      if (reachedScroll(el.scrollTop, kept.want)) waiting.current = null
    })
    observer.observe(inner)
    return () => observer.disconnect()
  }, [open])
  /** A reader who scrolls, drags or types in the view while a position is still
   *  being waited for has chosen where they are: the kept position is given up
   *  rather than pulling them out of it when the content grows. */
  const readerMoved = () => { waiting.current = null }

  useEffect(() => {
    const parent = root.current?.parentElement
    if (!parent) return
    const resized = () => {
      const r = parent.getBoundingClientRect()
      setSize({ width: r.width, height: r.height })
      const now = resource.snapshot(), p = clampPuck(now.x, now.y, r.width, r.height)
      if (p.x !== now.x || p.y !== now.y) resource.update(p)
    }
    resized()
    const observer = new ResizeObserver(resized)
    observer.observe(parent)
    return () => observer.disconnect()
  }, [resource])

  // The retained read fires on the open transition, not on a pointer entering.
  useEffect(() => {
    if (open) void resource.read()
    else resource.cancel()
  }, [open, resource])

  useEffect(() => {
    const blur = () => { drag.current = null; setDragging(false); suppress.current = true }
    window.addEventListener('blur', blur)
    return () => window.removeEventListener('blur', blur)
  }, [])

  const focusPuck = () => requestAnimationFrame(() => puck.current?.focus({ preventScroll: true }))
  /** The header × closes the card. It never removes the Magnet. */
  const closeCard = () => {
    remember(resource)
    resource.cancel()
    setOpen(resource, false)
    onCollapse()
    focusPuck()
  }
  const toggle = () => {
    if (suppress.current) { suppress.current = false; return }
    if (s.open) { closeCard(); return }
    setOpen(resource, true)
    onExpand()
  }
  const down = (e: ReactPointerEvent<HTMLButtonElement>) => {
    if (e.button !== 0) return
    drag.current = { pointer: e.pointerId, x: e.clientX, y: e.clientY, startX: s.x, startY: s.y, moved: false }
    suppress.current = false
    e.currentTarget.setPointerCapture(e.pointerId)
  }
  const move = (e: ReactPointerEvent<HTMLButtonElement>) => {
    const d = drag.current
    if (!d || d.pointer !== e.pointerId) return
    const dx = e.clientX - d.x, dy = e.clientY - d.y
    if (!d.moved && Math.hypot(dx, dy) < DRAG_THRESHOLD) return
    d.moved = true
    setDragging(true)
    suppress.current = true
    resource.update(clampPuck(d.startX + dx, d.startY + dy, size.width, size.height))
  }
  const end = (e: ReactPointerEvent<HTMLButtonElement>, cancel = false) => {
    const d = drag.current
    if (!d || d.pointer !== e.pointerId) return
    drag.current = null
    setDragging(false)
    suppress.current = d.moved || cancel
    if (e.currentTarget.hasPointerCapture(e.pointerId)) e.currentTarget.releasePointerCapture(e.pointerId)
  }
  /** Escape, innermost first. H2's send menu and H5's editor stop it earlier. */
  const escape = () => {
    if (s.searchTarget) { resource.update({ searchTarget: null }); return }
    if (s.overlay === 'settings') { leaveSettings(resource); return }
    if (s.overlay === 'search') { closeOverlay(resource); return }
    if (here.inspected) { closeInspect(resource); return }
    closeCard()
  }
  const tabs: MagnetTab[] = [...MAGNET_TABS]

  return <div ref={root} className={`q2-magnet${open ? ' q2-magnet-expanded' : ''}${s.wide ? ' q2-magnet-wide' : ''}${geometry.flip ? ' q2-magnet-flipped' : ''}${s.y > size.height - 126 ? ' q2-magnet-low' : ''}`}
    data-magnet={saved.id} style={{ left: s.x, top: s.y }}
    onKeyDown={(e) => { if (e.key === 'Escape') { e.stopPropagation(); escape() } }}>
    <div className="q2-magnet-puck-wrap">
      <button ref={puck} type="button" className="q2-magnet-puck" title={title} aria-label={`${open ? 'Close' : 'Open'} ${title} Magnet. Drag or use arrow keys to move.`} aria-expanded={open} aria-controls={cardId}
        onClick={toggle} onPointerDown={down} onPointerMove={move} onPointerUp={(e) => end(e)} onPointerCancel={(e) => end(e, true)}
        onKeyDown={(e) => {
          const delta = e.shiftKey ? 40 : 12
          const directions: Record<string, [number, number]> = { ArrowLeft: [-delta, 0], ArrowRight: [delta, 0], ArrowUp: [0, -delta], ArrowDown: [0, delta] }
          const d = directions[e.key]
          if (d) { e.preventDefault(); resource.update(clampPuck(s.x + d[0], s.y + d[1], size.width, size.height)) }
        }}><span aria-hidden="true">{title.trim().charAt(0).toUpperCase() || 'M'}</span><i aria-hidden="true">▤</i></button>
      {open && !dragging && <div className="q2-magnet-indicators" role="group" aria-label={`${title} quick indicators`}>
        {indicators.map((ind) => <button key={ind.key} type="button" className={`q2-magnet-indicator q2-magnet-indicator-${ind.key}`} title={ind.detail} aria-label={`${ind.label}: ${ind.detail}`} onClick={() => goTab(resource, ind.tab)}>
          <span aria-hidden="true">{ind.glyph}</span>{ind.value !== null && <b aria-hidden="true">{ind.value}</b>}
        </button>)}
      </div>}
    </div>
    {!open && <span className="q2-magnet-rest-title" title={title} style={{ marginLeft: restTitleOffset(s.x, size.width) }}>{title}{counted !== null && <><br /><small>{counted} collected items</small></>}</span>}
    {open && <section id={cardId} role="region" aria-label={`${title} Magnet`} className="q2-magnet-card"
      style={{ left: geometry.left, top: geometry.top, width: geometry.width, maxHeight: geometry.maxHeight } as CSSProperties}>
      <header>
        <div className="q2-magnet-head-text">
          <h2 title={title} tabIndex={0}>{title}</h2>
          <div className="q2-magnet-head-sub">{counted === null ? 'Collected items unavailable until this collection is read' : `${counted} collected items`}</div>
        </div>
        <div className="q2-magnet-collection">
          <span title={s.activation?.at ? `Collected ${new Date(s.activation.at * 1000).toLocaleString()}` : collectable ? 'Not collected yet' : 'Manual collection is not configured'}>
            {s.activation?.at ? 'Collected' : collectable ? 'Not yet' : 'Unavailable'}
          </span>
          <button type="button" className={`q2-magnet-primary${s.collecting ? ' collecting' : ''}`} disabled={!canCollect || !collectable || s.collecting || s.overlay === 'settings'} onClick={() => void resource.collect?.()}>{s.collecting ? 'Collecting…' : 'Collect now'}</button>
        </div>
        <button type="button" className="q2-magnet-icon" aria-label="Magnet settings" title="Sources and collection settings" aria-expanded={s.overlay === 'settings'} aria-controls={settingsId}
          onClick={() => s.overlay === 'settings' ? leaveSettings(resource) : openOverlay(resource, 'settings')}><span aria-hidden="true">⚙</span></button>
        <button type="button" className="q2-magnet-icon" aria-label={s.wide ? 'Compact Magnet' : 'Expand Magnet'} title={s.wide ? 'Compact Magnet' : 'Expand Magnet'}
          onClick={() => { remember(resource); resource.update({ wide: !s.wide }) }}><span aria-hidden="true">⤢</span></button>
        <button type="button" className="q2-magnet-icon q2-magnet-dismiss" aria-label="Close Magnet" title="Close Magnet" onClick={closeCard}>×</button>
      </header>
      <nav className="q2-magnet-tabs" role="tablist" aria-label="Magnet views">
        {tabs.map((t) => <button type="button" key={t} role="tab" aria-selected={!s.overlay && s.tab === t} aria-controls={viewId} onClick={() => goTab(resource, t)}>{t}</button>)}
      </nav>
      {s.overlay !== 'settings' && <div className="q2-magnet-toolbar">
        {searchToolbar ?? <label className="q2-magnet-search"><span className="q2-sr-only">Search all Magnet information</span>
          <input type="search" value={s.query} placeholder="Search this Magnet…" autoComplete="off"
            onChange={(e) => { remember(resource); resource.update({ query: e.target.value, overlay: e.target.value ? 'search' : s.overlay === 'search' ? null : s.overlay, searchTarget: null }) }} />
          {s.query && <button type="button" className="q2-magnet-icon" aria-label="Clear search" onClick={() => { resource.update({ query: '', searchTarget: null }); closeOverlay(resource) }}>×</button>}
        </label>}
      </div>}
      <div ref={view} id={viewId} className="q2-magnet-view" role={s.overlay ? undefined : 'tabpanel'} aria-label={s.overlay ? undefined : s.tab} tabIndex={-1}
        onWheel={readerMoved} onPointerDown={readerMoved} onKeyDown={readerMoved} onTouchStart={readerMoved}
        onScroll={(e) => { const top = e.currentTarget.scrollTop; const now = resource.snapshot(); const p = place(now)
          // A clamp is not a reading position: while a saved position is still
          // waited for, a report short of it is the short content, not the
          // reader, and it is neither saved nor taken as what the container said.
          const kept = waiting.current
          if (!savesReportedScroll(kept && kept.el === e.currentTarget ? kept.want : null, top)) return
          // What the container reports is what the saved number is written from,
          // so the reconciliation above can tell that number from a navigation's.
          reported.current = { el: e.currentTarget, top }
          resource.update({ places: { ...now.places, [placeKeyOf(now)]: p.inspected ? { ...p, inspectScroll: top } : { ...p, scroll: top } } }) }}>
        <div ref={content} id={s.overlay === 'settings' ? settingsId : undefined}>{views?.[placeKey] ?? <p className="q2-magnet-muted">This view is not available in this build.</p>}</div>
      </div>
      {s.overlay !== 'settings' && footerComposer}
      {s.collectionMessage && <p role="status" className="q2-magnet-read-status">{s.collectionMessage}</p>}
    </section>}
  </div>
}
