import { useEffect, useId, useLayoutEffect, useRef, useState, useSyncExternalStore } from 'react'
import type { CSSProperties, PointerEvent as ReactPointerEvent, ReactNode } from 'react'
import type { MagnetPlaceKey, MagnetResource, MagnetSnapshot } from './contract'
import type { MagnetCollectionResource } from './state'
import { magnetIndicators, restingCount } from './indicators'
import { retainedFiles } from './Inspection'
import { MAGNET_PRIMARY_TABS, closeInspect, closeOverlay, collectionTabOf, goTab, inCollection, leaveSettings, openOverlay, place, placeKeyOf, registerViewScroll, remember, setOpen } from './places'
import { pendingScroll, reachedScroll, savesReportedScroll } from './position'
import './design.css'
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
export function cardGeometry(x: number, y: number, width: number, height: number, wide = false, dimensions?: { width: number; height: number }) {
  const want = dimensions?.width ?? (width <= NARROW ? width - GAP * 2 : wide ? WIDTHS.wide : WIDTHS.narrow)
  const cardWidth = Math.min(want, Math.max(0, width - GAP * 2))
  const right = x + 32 + cardWidth > width - GAP
  const left = right ? Math.max(GAP - x, PUCK - 32 - cardWidth) : Math.min(32, width - GAP - x - cardWidth)
  const maxHeight = Math.max(0, Math.min(dimensions?.height ?? (wide ? 740 : 650), height - GAP * 2))
  const top = Math.max(GAP - y, Math.min(0, height - GAP - y - maxHeight))
  return { left, top, width: cardWidth, maxHeight, flip: right }
}

/** HOW MUCH ROOM THE OPENED PANEL HAS, as two continuous 0–1 scalars.
 *
 *  The approved round-3 mockups show a compact panel (adm-abc995a3f832) and a
 *  larger working surface (adm-49555c498afb). Those are two points on one line,
 *  not two modes: the owner's §1 asks the layout to "adapt continuously to the
 *  available panel space … not fixed size presets". So nothing in the chrome
 *  branches on a size. Every measurement that changes with room is interpolated
 *  along these two numbers, which the frame publishes on the card as
 *  `--magnet-room` and `--magnet-room-h` (with the raw `--magnet-panel-w/h`),
 *  where the stylesheet -- and any view supplied into the frame -- reads them.
 *
 *  Panel width, not viewport width, is what the panel's own layout answers to:
 *  a 340 px panel dragged narrow on a 2560 px screen has exactly as little room
 *  as a phone, and a viewport media query cannot see that. */
export function panelRoom(width: number, height: number) {
  const along = (v: number, from: number, to: number) =>
    Number.isFinite(v) ? Math.max(0, Math.min(1, (v - from) / (to - from))) : 0
  return { w: along(width, 320, 900), h: along(height, 320, 740) }
}

/** The resting puck's name sits under it, shifted so it never leaves the canvas.
 *  Centred under the puck where there is room; pushed in at either edge. */
const REST_TITLE = 116
export function restTitleOffset(x: number, width: number) {
  return Math.round(Math.max(GAP - x, Math.min(-26, width - GAP - x - REST_TITLE)))
}

/** THE RESOURCE'S OWN NEW-ITEM READ, where the resource provides one. Declared
 *  here rather than in the shared contract: the count is a read of the record,
 *  taken by the frame, not snapshot state, and a resource that cannot take it
 *  simply leaves the badge's new-item total unknown. */
type Counting = MagnetResource & Partial<Pick<MagnetCollectionResource, 'markShown' | 'newItemCount'>>

/** WHICH BATCH TO RECORD AS SHOWN TO THIS VIEWER, or `null` for "record
 *  nothing".
 *
 *  The baseline the new-item count is taken from is the batch the card was
 *  showing when the viewer last opened it, so it is recorded once per opening:
 *  on the open transition, or on the first batch that lands during that opening
 *  when nothing was being shown yet. Deliberately NOT re-recorded while the
 *  card stays open -- a collection that lands during an opening is still new
 *  since the viewer opened the Magnet, and the badge says exactly that. A
 *  closed card records nothing: what it is not showing has not been seen. */
export function shownBaseline(open: boolean, alreadyRecorded: boolean, batch: string | null): string | null {
  return open && !alreadyRecorded && batch ? batch : null
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
  /** The persistent composer, rendered on the Conversation place only.
   *
   *  No approved round-3 mockup shows a standing composer under Collection,
   *  Summary or Perspectives: the compose box in `02`, `05`, `09` and `10` is
   *  in the body of Perspectives and belongs to that view. The prop stays a
   *  slot -- the frame decides where it appears, and it still never appears in
   *  settings. */
  footerComposer?: ReactNode
  onExpand: () => void
  onCollapse: () => void
}

/** THE FRAME, to the approved round-3 design: a quiet header, a tab row, a
 *  generous body and one footer line. Four slots and nothing else -- header,
 *  tabs, view (the only scroll container) and the Conversation composer.
 *
 *  It draws no control that belongs to a view. The search line and the type
 *  pills are inside Collected items in the approved design (`04-browse.png`),
 *  the question search inside Past questions (`08-history.png`), and collecting
 *  is the "Collect manually" row of Sources (`03-sources.png`) -- so the frame
 *  renders none of them. The lens places and the collection's filter list in
 *  `places.ts` are unchanged: only who draws the controls moved.
 *
 *  The tabs slot is the owner's hierarchy (ent-3191baeb33d2 §1): Summary,
 *  Perspectives and Conversation are primary, and the collection is one
 *  secondary place carrying its own count. The header carries no second count
 *  line and no standing collection status sentence (§3, §6).
 *
 *  Measurements are the mockups' own (`magnet-design-round2/render.py` `style`,
 *  with round 3's overrides): head `20px 24px 15px` over a 1px #514541 rule,
 *  tabs `0 24px` with each tab `13px 0 11px` and a 3px #e6bc50 underline on the
 *  one in force, the body `design.css`'s `.mgd-body`, and one footer line at
 *  `13px 24px`. */
export default function Magnet({ resource, views, footerComposer, onExpand, onCollapse }: MagnetProps) {
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
  const resizing = useRef<{ pointer: number; x: number; y: number; left: number; top: number; width: number; height: number; edge: string } | null>(null)
  const [resizePosition, setResizePosition] = useState<{ left: number; top: number } | null>(null)
  const suppress = useRef(false)
  /** The position the view container last reported through its scroll handler,
   *  kept with the element so a remounted card restores its saved position
   *  rather than measuring itself against the container it no longer has. */
  const reported = useRef<{ el: HTMLDivElement; top: number } | null>(null)
  const [dragging, setDragging] = useState(false)
  const [size, setSize] = useState({ width: 1024, height: 768 })
  /** What is new since this viewer last opened this Magnet, read from the record
   *  (`collection/new`) by the effects below. `null` is unknown, never zero. */
  const [newItems, setNewItems] = useState<number | null>(null)
  /** Whether this opening of the card has already recorded its baseline. */
  const baselined = useRef(false)
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
  const counting: Counting = resource
  const latestBatch = s.activation?.artifact?.ref ?? null
  const indicators = magnetIndicators({ retained: true, postsSourceTally: postCount, filesLoaded: files.length, filesKnown, filesPartial: partial, newItems })
  // Never fabricate a count: unknown until a retained read has returned.
  const counted = s.activation !== undefined ? posts.length + files.length : null
  /** The resting puck's one number: what is actually new since this viewer last
   *  opened this Magnet, read from the record below. `null` is unknown, and the
   *  badge then says what is held and which of the two it is showing. */
  const resting = restingCount(newItems, counted)
  const here = place(s)
  const geometry = cardGeometry(s.x, s.y, size.width, size.height, s.wide, s.dimensions)
  const room = panelRoom(geometry.width, geometry.maxHeight)
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
      setResizePosition(null)
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

  /** The baseline this viewer's new-item count is taken from: recorded once per
   *  opening, and cleared on close so the next opening records its own. */
  useEffect(() => {
    if (!open) { baselined.current = false; return }
    const record = shownBaseline(open, baselined.current, latestBatch)
    if (!record) return
    baselined.current = true
    counting.markShown?.(record)
  }, [open, latestBatch, counting])
  /** The one number the resting puck carries, taken from the record: the rows
   *  in the latest batch whose identity is absent from that baseline. Read when
   *  the card opens or closes and when a new batch lands -- a collection
   *  updates the snapshot whether the card is open or not -- and at no other
   *  time: no timer, no polling, nothing waking on its own. An unknown count
   *  stays unknown; the badge then reports what is held, never calling it new. */
  useEffect(() => {
    let live = true
    void (async () => {
      const count = await counting.newItemCount?.()
      if (live) setNewItems(count ?? null)
    })()
    return () => { live = false }
  }, [open, latestBatch, counting])

  useEffect(() => {
    const blur = () => { drag.current = null; setDragging(false); suppress.current = true }
    window.addEventListener('blur', blur)
    return () => window.removeEventListener('blur', blur)
  }, [])

  const focusPuck = () => requestAnimationFrame(() => puck.current?.focus({ preventScroll: true }))
  /** The header × closes the card. It never removes the Magnet. */
  const closeCard = () => {
    setResizePosition(null)
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
    setResizePosition(null)
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
  const collectionTab = collectionTabOf(s)
  const inCollectionNow = inCollection(s)

  const resizeDown = (e: ReactPointerEvent<HTMLDivElement>, edge: string) => {
    if (e.button !== 0) return
    e.preventDefault(); e.stopPropagation()
    resizing.current = { pointer: e.pointerId, x: e.clientX, y: e.clientY,
      left: s.x + (resizePosition?.left ?? geometry.left), top: s.y + (resizePosition?.top ?? geometry.top),
      width: geometry.width, height: geometry.maxHeight, edge }
    e.currentTarget.setPointerCapture(e.pointerId)
  }
  const resizeMove = (e: ReactPointerEvent<HTMLDivElement>) => {
    const d = resizing.current
    if (!d || d.pointer !== e.pointerId) return
    const dx = e.clientX - d.x, dy = e.clientY - d.y
    const minWidth = Math.min(300, Math.max(0, size.width - GAP * 2))
    const minHeight = Math.min(320, Math.max(0, size.height - GAP * 2))
    let left = d.left, top = d.top, right = d.left + d.width, bottom = d.top + d.height
    if (d.edge.includes('w')) left = Math.max(GAP, Math.min(right - minWidth, d.left + dx))
    if (d.edge.includes('e')) right = Math.min(size.width - GAP, Math.max(left + minWidth, right + dx))
    if (d.edge.includes('n')) top = Math.max(GAP, Math.min(bottom - minHeight, d.top + dy))
    if (d.edge.includes('s')) bottom = Math.min(size.height - GAP, Math.max(top + minHeight, bottom + dy))
    setResizePosition({ left: left - s.x, top: top - s.y })
    resource.update({ dimensions: { width: right - left, height: bottom - top } })
  }
  const resizeEnd = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (resizing.current?.pointer !== e.pointerId) return
    resizing.current = null
    if (e.currentTarget.hasPointerCapture(e.pointerId)) e.currentTarget.releasePointerCapture(e.pointerId)
  }
  /** The mockups' header ⤢ (adm-abc995a3f832, adm-49555c498afb): one step
   *  between a compact panel and a larger working surface, for a reader who does
   *  not want to drag an edge. It writes `dimensions` -- the very thing a drag
   *  writes, remembered by the same working state -- so there is no second size
   *  mechanism and nothing of direct resizing changes. `wide` stays the legacy
   *  preference it already was, and is what the next step reads. */
  const stepSize = () => {
    const next = !s.wide
    const want = cardGeometry(s.x, s.y, size.width, size.height, next)
    setResizePosition(null)
    resource.update({ wide: next, dimensions: { width: want.width, height: want.maxHeight } })
  }

  return <div ref={root} className={`q2-magnet${open ? ' q2-magnet-expanded' : ''}${s.wide ? ' q2-magnet-wide' : ''}${geometry.flip ? ' q2-magnet-flipped' : ''}${s.y > size.height - 126 ? ' q2-magnet-low' : ''}`}
    data-magnet={saved.id} style={{ left: s.x, top: s.y }}
    onKeyDown={(e) => { if (e.key === 'Escape') { e.stopPropagation(); escape() } }}>
    <div className="q2-magnet-puck-wrap">
      <button ref={puck} type="button" className="q2-magnet-puck" title={title} aria-label={`${open ? 'Close' : 'Open'} ${title} Magnet. ${open ? '' : `${resting.detail}. `}Drag or use arrow keys to move.`} aria-expanded={open} aria-controls={cardId}
        onClick={toggle} onPointerDown={down} onPointerMove={move} onPointerUp={(e) => end(e)} onPointerCancel={(e) => end(e, true)}
        onKeyDown={(e) => {
          const delta = e.shiftKey ? 40 : 12
          const directions: Record<string, [number, number]> = { ArrowLeft: [-delta, 0], ArrowRight: [delta, 0], ArrowUp: [0, -delta], ArrowDown: [0, delta] }
          const d = directions[e.key]
          if (d) { e.preventDefault(); resource.update(clampPuck(s.x + d[0], s.y + d[1], size.width, size.height)) }
        }}><span aria-hidden="true">{title.trim().charAt(0).toUpperCase() || 'M'}</span><i aria-hidden="true">▤</i></button>
      {/* One count at rest, not the mockup's ring: the puck stays compact and
          out of the way, and the number is already said in the puck's own
          accessible name above, so the badge itself is decoration. */}
      {!open && !dragging && resting.value !== null && <span className={`q2-magnet-count q2-magnet-count-${resting.kind}`} aria-hidden="true">{resting.value}</span>}
      {open && !dragging && <div className="q2-magnet-indicators" role="group" aria-label={`${title} quick indicators`}>
        {indicators.map((ind) => <button key={ind.key} type="button" className={`q2-magnet-indicator q2-magnet-indicator-${ind.key}`} title={ind.detail} aria-label={`${ind.label}: ${ind.detail}`} onClick={() => goTab(resource, ind.tab)}>
          <span aria-hidden="true">{ind.glyph}</span>{ind.value !== null && <b aria-hidden="true">{ind.value}</b>}
        </button>)}
      </div>}
    </div>
    {!open && <span className="q2-magnet-rest-title" title={title} style={{ marginLeft: restTitleOffset(s.x, size.width) }}>{title}</span>}
    {open && <section id={cardId} role="region" aria-label={`${title} Magnet`} className="q2-magnet-card"
      style={{ left: resizePosition?.left ?? geometry.left, top: resizePosition?.top ?? geometry.top, width: geometry.width, height: geometry.maxHeight,
        // The one place the panel's own room reaches the stylesheet. Published
        // on the card, so every view inside it inherits the same two numbers.
        '--magnet-panel-w': `${Math.round(geometry.width)}px`, '--magnet-panel-h': `${Math.round(geometry.maxHeight)}px`,
        '--magnet-room': room.w.toFixed(3), '--magnet-room-h': room.h.toFixed(3) } as CSSProperties}>
      {['n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw'].map((edge) => <div key={edge} className={`q2-magnet-resize q2-magnet-resize-${edge}`}
        aria-hidden="true" onPointerDown={(e) => resizeDown(e, edge)} onPointerMove={resizeMove} onPointerUp={resizeEnd} onPointerCancel={resizeEnd} />)}
      {/* The mockups' header (`02-compact-current.png`, `03-sources.png`): the
          Magnet's name, then `⤢ ⚙ ×` at the far edge. Nothing else is on the
          line -- no Collect now, no second count, no status sentence. Collecting
          is the "Collect manually" row of Sources, which Collection draws.
          The ⚙ is kept although the mockups show two icons: it is the only way
          to rename or remove a Magnet (plan seam 3, carrier's decision). */}
      <header>
        <div className="q2-magnet-head-text">
          <h2 title={title} tabIndex={0}>{title}</h2>
        </div>
        <button type="button" className="q2-magnet-icon q2-magnet-step" aria-label={s.wide ? 'Use a smaller panel' : 'Use a larger panel'}
          title={s.wide ? 'Smaller panel' : 'Larger panel'} aria-pressed={s.wide} onClick={stepSize}><span aria-hidden="true">⤢</span></button>
        <button type="button" className="q2-magnet-icon" aria-label="Magnet settings" title="Settings" aria-expanded={s.overlay === 'settings'} aria-controls={settingsId}
          onClick={() => s.overlay === 'settings' ? leaveSettings(resource) : openOverlay(resource, 'settings')}><span aria-hidden="true">⚙</span></button>
        <button type="button" className="q2-magnet-icon q2-magnet-dismiss" aria-label="Close Magnet" title="Close Magnet" onClick={closeCard}>×</button>
      </header>
      <nav className="q2-magnet-tabs" role="tablist" aria-label="Magnet views">
        {/* The approved order (owner request ent-1e82a8786c37): Summary, then
            Collection as the second place, then the remaining primary tabs.
            `MAGNET_PRIMARY_TABS` stays the underlying model -- Summary first,
            Collection is inserted after it rather than appended at the end. */}
        {(() => { const [firstTab, ...restTabs] = MAGNET_PRIMARY_TABS; return <>
          <button type="button" key={firstTab} role="tab" aria-selected={!s.overlay && s.tab === firstTab} aria-controls={viewId} onClick={() => goTab(resource, firstTab)}>{firstTab}</button>
          <button type="button" key="Collection" role="tab" className="q2-magnet-tab-collection" aria-selected={inCollectionNow} aria-controls={viewId}
            title={counted === null ? 'Collected information, once this collection has been read' : `${counted} collected ${counted === 1 ? 'item' : 'items'}`}
            onClick={() => goTab(resource, collectionTab)}>Collection{counted !== null && <small> {counted}</small>}</button>
          {restTabs.map((t) => <button type="button" key={t} role="tab" aria-selected={!s.overlay && s.tab === t} aria-controls={viewId} onClick={() => goTab(resource, t)}>{t}</button>)}
        </> })()}
      </nav>
      {/* No filter row and no search line here. The approved design puts the
          type pills and the search inside Collected items, under its heading,
          and the Sources link on that heading's own row -- so the frame spends
          no line on either and the body begins directly under the tabs. */}
      <div ref={view} id={viewId} className="q2-magnet-view mgd-body" role={s.overlay ? undefined : 'tabpanel'} aria-label={s.overlay ? undefined : s.tab} tabIndex={-1}
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
      {/* The composer stands under the Conversation place and nowhere else:
          that is the only surface the approved design gives a standing compose
          box. An overlay is a place of its own, so search and settings are not
          the Conversation place and draw no composer -- settings as before. */}
      {placeKey === 'Conversation' && <div className="q2-magnet-footer-slot">{footerComposer}</div>}
      {s.collectionMessage && <p role="status" className="q2-magnet-read-status">{s.collectionMessage}</p>}
      {/* The mockups' one footer line, in their own six words. It is the only
          thing in the panel that says the edges can be dragged. */}
    </section>}
  </div>
}
