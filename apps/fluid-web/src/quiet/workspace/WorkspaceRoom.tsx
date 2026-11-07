/* THE ROOM THE CONVERSATION AND ITS WORKING AREA SHARE. Round 5, package L,
 * over S's bootstrap (F11).
 *
 * THE OWNER'S DECISION IS THE SHAPE OF THIS FILE (ent-ecba3f3dcf3c): the
 * working area opens on the RIGHT and the conversation slides LEFT. Three
 * rooms, chosen by one control and remembered per Page:
 *
 *    Single chat      the conversation alone, in round four's own tracks
 *    Chat and panes   the conversation beside a working area, reading ~640px
 *    Workspace board  the working area given the room, reading at its floor
 *
 * THE FOUR SLOTS AND THEIR MOUNT IDENTITIES ARE S'S, UNCHANGED (F11/F27).
 * conversation, tools, working and pageControls are all still here, all still
 * mounted unconditionally, and CSS -- never a conditional mount and never a
 * reparent -- is what moves them between the three rooms. ConversationNav and
 * RailTools now arrive in the `tools` slot, which is where the owner's room
 * puts them: one consolidated tools column immediately left of the work area,
 * carrying the navigation and the contextual readings together. S's bootstrap
 * rendered `conversation` before `tools`, which left R no way to hand them
 * over without reordering the frozen ARIA baseline; this file renders `tools`
 * FIRST, so "Conversation tools" and "Conversations by recency" still precede
 * `main` exactly as the baseline holds them (ent-55cfd945a1b6).
 *
 * ONE SHARED COLUMN TEMPLATE, STILL. `--qc-columns` is used by the header, the
 * heading and this room, so the reading column continues through the header to
 * within a pixel with the tools in their own slot (room.css; layout.css). The
 * heading goes WITH that column: expanded, the conversation slides left and the
 * heading's own tracks follow the room it stands over (layout.css, keyed off
 * this room's `data-mode` / `data-one`), rather than naming a column 318px to
 * its left.
 *
 * WHEN THREE SURFACES DO NOT FIT (F12). Reading >= 330, tools >= 240 and the
 * working area >= 300 are minima, not suggestions, and the gaps, the dragged
 * gutter and a pinned toolbar are real width that has to come off the top
 * before they are checked -- which is why the room MEASURES itself rather than
 * trusting a breakpoint. Below what the three need, and at every width at or
 * under 900px, the room draws ONE surface with an explicit switch and a named
 * Return to conversation. Nothing is squeezed under its minimum instead.
 *
 * THE NARROW CHOICE IS DRAWING STATE (F9), held here and never written to the
 * bookmark: the desktop room survives a phone being turned sideways. What IS
 * written is the mode and the dragged reading width, per Page.
 *
 * THE CONVERSATION KEEPS ITS OWN MARGINS AT NARROW WIDTHS. The conversation
 * surface is round four's narrow column -- the tools, the open margin, the
 * reading and its one composer, stacked -- because that is what the margin
 * and layout regressions of round four assert at 390px, and the round is not
 * meant to take the margins off a phone. The tools surface is those same
 * tools given the whole height with the reading parked; the workspace surface
 * is the working area alone.
 */
import { lazy, Suspense, useCallback, useEffect, useRef, useState, type CSSProperties } from 'react'
import { READABLE } from '../../fluid/nav'
import type { BoundaryScope } from '../../fluid/workspace/Boundary'
import type { WorkspaceRoomView } from '../contract'
import { captureReadingAnchor, restoreReadingAnchor, SCROLL_KEYS } from '../reader/scroll'
import type { ReadingAnchor, RoomMode } from './types'
import './room.css'

/** THE THREE MINIMA, IN CSS PIXELS. The reading's floor is Fluid's own
 *  READABLE; its ceiling is Quiet's measure (`--qc-measure`). The tools keep
 *  240 (F12) and the working area Fluid's own least width. */
export const READING_MIN = READABLE
export const READING_MAX = 760
export const TOOLS_MIN = 240
/** Fluid's own least workspace width (`Boundary.WORKSPACE_MIN`), repeated
 *  rather than imported: a value import of that module would pull Fluid's
 *  whole workspace into the Quiet entry chunk, which is exactly what the
 *  deferred import below exists to avoid. The unit suite asserts the two
 *  still agree. */
export const WORK_MIN = 300

/* THE SEPARATOR IS FETCHED WHEN THERE IS SOMETHING TO SEPARATE. Fluid's
   Boundary statically imports the Holder's place, so importing it for value
   would add Fluid's workspace to every Single chat load that will never draw
   a separator. Deferred, Single chat's payload is the one it was. */
const Boundary = lazy(() => import('../../fluid/workspace/Boundary'))

/** Where each room opens when it is chosen: panes roomy enough to read in,
 *  the board at the readable floor so the work has the rest. */
export const PANES_READING = 640

/** The width the room has for its columns, and what it costs to draw them. */
export interface RoomFit {
  /** the room's own content box: gutters and any pinned-toolbar reserve gone */
  available: number
  /** one column gap (`--qc-gap`), read from the shared template */
  gap: number
  /** the dragged separator's own width (`--qw-gutter`) */
  gutter: number
}

/** WHAT THREE SURFACES COST: the three minima, the three gaps between four
 *  columns, and the separator between the first two. */
export const requiredWidth = ({ gap, gutter }: RoomFit): number =>
  READING_MIN + TOOLS_MIN + WORK_MIN + gap * 3 + gutter

/** Whether the reading, the tools and the working area all fit at once. */
export const roomFits = (fit: RoomFit): boolean => fit.available >= requiredWidth(fit)

/** THE WIDEST THE READING MAY BE DRAGGED: what is left once the tools and the
 *  working area have their minima, never past Quiet's measure. */
export const readingCeiling = (fit: RoomFit): number =>
  Math.max(READING_MIN, Math.min(READING_MAX, fit.available - TOOLS_MIN - WORK_MIN - fit.gap * 3 - fit.gutter))

export const clampReading = (px: number, ceiling: number): number =>
  Math.round(Math.max(READING_MIN, Math.min(Math.max(READING_MIN, ceiling), px)))

/** The width a room opens at, clamped against the room actually available. */
export const initialReading = (mode: RoomMode, ceiling: number): number =>
  clampReading(mode === 'board' ? READING_MIN : PANES_READING, ceiling)

/** How many frames a reading that has just been given the room again is
 *  waited for before the restoration gives up on it. Generous enough for a
 *  long conversation re-flowing on a phone (ten frames, measured), short
 *  enough to be over before anybody could have read anything. */
const SETTLE = 40

/** Which surface a narrow room is showing. Drawing state, not a bookmark. */
export type Showing = 'conversation' | 'tools' | 'workspace'

/** The room's own controls, named so focus can be given back to one of them
 *  after the change that replaced it. */
type Invoker = 'return' | 'mode' | 'tools' | 'workspace'
const INVOKER: Record<Invoker, string> = {
  return: '.qw-return',
  mode: '.qw-modes input:checked',
  tools: '.qw-switch [data-for="tools"]',
  workspace: '.qw-switch [data-for="workspace"]',
}

const MODES: { id: RoomMode; name: string }[] = [
  { id: 'single', name: 'Single chat' },
  { id: 'panes', name: 'Chat and panes' },
  { id: 'board', name: 'Workspace board' },
]

const shows = (mode: RoomMode): boolean => mode !== 'single'

/** The width the room has, MEASURED rather than assumed: the room's padding
 *  carries the frame's gutters and the pinned toolbar's reserve, so its
 *  content box is the honest answer to "is there room for all three?", and a
 *  breakpoint would not be.
 *
 *  WHAT IS WATCHED IS A RULE, NOT THE ROOM. A ResizeObserver on the room is
 *  an observer on an ANCESTOR of the reading: every time the reading reflows
 *  -- parked, given back, re-wrapped by a dragged separator -- the room grows
 *  or shrinks by thousands of pixels under it, and a shallow observation
 *  delivered after the deep ones that caused it is what WebKit reports as
 *  "ResizeObserver loop completed with undelivered notifications". And
 *  measuring after every render instead costs a forced layout on every scroll
 *  the reader makes, because a scroll writes the reading down.
 *
 *  So the room draws one empty rule across its columns -- `.qw-measure`, no
 *  height, no content, no name -- and watches THAT. Its width is the room's
 *  own content box, gutters and any pinned-toolbar reserve already gone; its
 *  height is zero and stays zero, so a reading reflowing beside it reports
 *  nothing at all. Only a width that really changed is reported, and it is
 *  applied on the next frame rather than inside the notification. */
function useFit(el: React.RefObject<HTMLDivElement | null>): RoomFit | null {
  const [fit, setFit] = useState<RoomFit | null>(null)
  useEffect(() => {
    const node = el.current
    if (!node || typeof ResizeObserver === 'undefined') return
    /* `--qc-gap` and `--qw-gutter` (inherited down to the rule), NOT the
       resolved column-gap: the fallback room is a flex column with a gap of
       its own, and reading that one back would make the answer depend on the
       answer. */
    const style = getComputedStyle(node)
    const read = () => ({
      gap: parseFloat(style.getPropertyValue('--qc-gap')) || 0,
      gutter: parseFloat(style.getPropertyValue('--qw-gutter')) || 0,
    })
    let cost = read()
    let last = -1
    let due = 0
    const set = (available: number) => {
      last = available
      setFit((was) => {
        const next: RoomFit = { available: Math.max(0, available), ...cost }
        return was && was.available === next.available && was.gap === next.gap
          && was.gutter === next.gutter ? was : next
      })
    }
    // The observer reports once when it starts: that is the first measurement.
    const watch = new ResizeObserver((entries) => {
      const box = entries[entries.length - 1]?.contentRect
      if (!box || box.width === last) return
      const width = box.width
      cancelAnimationFrame(due)
      due = requestAnimationFrame(() => set(width))
    })
    watch.observe(node, { box: 'content-box' })
    /* A window resize can change the shared template's own numbers without
       changing the room's width at all, and then the observer has nothing to
       report: the costs are re-read here and the last width re-applied. */
    const resized = () => { cost = read(); if (last >= 0) set(last) }
    window.addEventListener('resize', resized)
    return () => {
      watch.disconnect()
      cancelAnimationFrame(due)
      window.removeEventListener('resize', resized)
    }
  }, [el])
  return fit
}

/** Fluid's own global breakpoint, which this round does not move. */
function useNarrow(): boolean {
  const [narrow, setNarrow] = useState(false)
  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return
    const query = window.matchMedia('(max-width: 900px)')
    const read = () => setNarrow(query.matches)
    read()
    query.addEventListener('change', read)
    return () => query.removeEventListener('change', read)
  }, [])
  return narrow
}

const WorkspaceRoom: WorkspaceRoomView = ({
  page,
  room,
  onRoom,
  conversation,
  tools,
  working,
  pageControls,
}) => {
  const roomEl = useRef<HTMLDivElement>(null)
  const workEl = useRef<HTMLDivElement>(null)
  const ruleEl = useRef<HTMLDivElement>(null)
  const fit = useFit(ruleEl)
  const narrow = useNarrow()
  const expanded = shows(room.mode)
  const ceiling = fit ? readingCeiling(fit) : READING_MAX
  const one = narrow || (expanded && !!fit && !roomFits(fit))
  const [showing, setShowing] = useState<Showing>('conversation')

  /* -- THE DRAGGED WIDTH. The preview is controlled here and the committed
     width is the bookmark's; nothing else is written, by any path (F3). */
  const [preview, setPreview] = useState<number | null>(null)
  useEffect(() => { setPreview(null) }, [room.readingPx])
  const readingPx = clampReading(preview ?? room.readingPx, ceiling)

  /* -- WHAT WAS BEING READ, ACROSS A CHANGE OF ROOM. Expanding, collapsing
     and parking the reading all reflow the column it is in, so the post that
     was visible is measured BEFORE the change and put back after it, through
     R's own anchor rather than a scroll position. Focus goes back to whatever
     asked for the change. */
  const held = useRef<ReadingAnchor | null>(null)
  const wanted = useRef<Invoker | null>(null)
  const stream = () => document.getElementById('qc-stream')
  /* FOCUS COMES BACK TO THE CONTROL, NOT TO AN ELEMENT. The control that
     asked for the change is the one the change itself replaces -- Show tools
     becomes Return to conversation and back again -- so a remembered node
     would be a detached one by the time focus was given to it. What is
     remembered is WHICH control, found again in the room once it is drawn. */
  /* `held` IS THE PLACE THE READING WAS WHEN IT WAS LAST DRAWN, and a change
     made while it is parked does not overwrite it.
     A PARKED READING STILL ANSWERS A MEASUREMENT, with every box at zero:
     `display: none` takes the posts out of the layout but leaves them in the
     document, so asking for the anchor there comes back with the first post
     at offset 0 -- a confident answer about a reading nobody could see, and
     exactly the answer that would be put back over the place somebody left.
     So the reading is measured only when it has a height. */
  const keep = useCallback((asked: Invoker | null) => {
    const el = stream()
    const measured = el && el.getBoundingClientRect().height > 0 ? captureReadingAnchor(el) : null
    if (measured) held.current = measured
    wanted.current = asked
  }, [])
  useEffect(() => {
    const anchor = held.current
    const want = wanted.current
    if (!anchor && !want) return
    wanted.current = null
    const asked = want ? roomEl.current?.querySelector<HTMLElement>(INVOKER[want]) ?? null : null
    /* IT IS PUT BACK ONCE THE READING IS DRAWN, which is not after a count of
       frames. A column given the room again, or taken out of a parked
       surface, can be ten frames away from being laid out -- measured on
       WebKit at 390px, where the reading comes back only once nine thousand
       pixels of posts have been re-flowed -- and `restoreReadingAnchor` asked
       before then measures boxes that are all zero and moves the reader
       somewhere nobody was. So the restoration WAITS FOR A DRAWN READING, for
       a bounded number of frames, and gives way at once to a reader who
       scrolls meanwhile. It is not a retry loop: it ends on the first frame
       the reading has a height, or when its frames run out. */
    let live = true
    let frames = 0
    const stop = () => { live = false }
    const keyed = (e: KeyboardEvent) => { if (SCROLL_KEYS.has(e.key)) live = false }
    let next = 0
    const drawn = () => (stream()?.getBoundingClientRect().height ?? 0) > 0
    const look = () => {
      if (!live) return
      if (drawn()) { if (anchor) restoreReadingAnchor(stream(), anchor); return }
      if (++frames > SETTLE) { live = false; return }
      next = requestAnimationFrame(look)
    }
    /* FOCUS GOES BACK AT ONCE, AND WITHOUT SCROLLING -- it does not wait for
       a reading, because parking one is exactly when there is none to wait
       for. Giving focus back is also not a reason to move the reading: left
       to itself the browser scrolls the control into view, and a control this
       room draws at the top of a stack it is the last child of is one some
       engines scroll all the way down to. */
    next = requestAnimationFrame(() => {
      if (!live) return
      asked?.focus({ preventScroll: true })
      look()
    })
    window.addEventListener('wheel', stop, { passive: true })
    window.addEventListener('touchmove', stop, { passive: true })
    window.addEventListener('keydown', keyed)
    return () => {
      live = false
      cancelAnimationFrame(next)
      window.removeEventListener('wheel', stop)
      window.removeEventListener('touchmove', stop)
      window.removeEventListener('keydown', keyed)
    }
  }, [showing, room.mode])

  const choose = (mode: RoomMode) => {
    if (mode === room.mode) return
    keep('mode')
    setShowing('conversation')
    onRoom(mode === 'single' ? { mode } : { mode, readingPx: initialReading(mode, ceiling) })
  }

  /** Return to conversation. In an expanded room it collapses the room; in a
   *  one-surface room it brings the reading back, and either way focus goes
   *  to the control that asked for the surface being left. */
  const back = () => {
    if (one && showing !== 'conversation') {
      keep(showing)
      setShowing('conversation')
      return
    }
    keep('mode')
    onRoom({ mode: 'single' })
  }

  /** Park the reading and show another surface, with focus on the way back. */
  const park = (next: Showing) => () => {
    keep('return')
    setShowing(next)
  }

  /* -- THE SEPARATOR (F3). Drawn only where there are two surfaces to share
     room between; its scope is controlled, and cancelling it commits nothing.
     The refs it needs exist from the first measurement onwards, which is also
     when the room knows whether all three fit.

     WHAT IS REMEMBERED IS WHAT IS DRAWN (the review's finding 1). The
     separator works out how far it may TRAVEL from the room beside it -- the
     spare width the working area has above its own minimum -- and that spare
     room can reach past Quiet's measure: at 1600px it carried End to 770px
     while the reading was drawn at 760. The width is the caller's in this
     scope (F3), so the clamp belongs here, on BOTH callbacks: the pointer and
     the arrow keys are the same two channels, so a bookmark can no longer
     hold a width the reading has never had. */
  const scope: BoundaryScope | null = fit && roomEl.current && workEl.current ? {
    root: roomEl.current,
    workspace: workEl.current,
    minConversation: READING_MIN,
    allowRail: false,
    value: readingPx,
    onDrag: (px: number) => setPreview(clampReading(px, ceiling)),
    commit: (px: number) => onRoom({ readingPx: clampReading(px, ceiling) }),
    label: 'Conversation width: drag or use arrow keys to resize',
    announce: (px: number) => `Conversation ${px} px; working area ${
      Math.round(workEl.current?.getBoundingClientRect().width ?? 0)} px`,
  } : null

  const parked = (surface: Showing) => one && showing !== surface
  return (
    <div ref={roomEl} className="qw-room" data-mode={room.mode} data-page={page}
      data-one={one ? '' : undefined} data-showing={one ? showing : undefined}
      style={{ '--qw-reading': `${readingPx}px` } as CSSProperties}>
      {/* THE RULE THE ROOM MEASURES ITSELF BY: no height, no content, no
          accessible name, and exactly the width the columns have to share. */}
      <div ref={ruleEl} className="qw-measure" aria-hidden="true" />
      {/* THE TOOLS COME FIRST, so the baseline's ARIA order is the one it
          already holds, and so the consolidated column can be placed
          immediately left of the work area by CSS alone. */}
      <div className="qw-slot qw-tools" data-slot="tools">
        <div className="qw-modes" role="group" aria-label="Workspace layout">
          {MODES.map((m) => (
            <label key={m.id} className="qw-mode">
              <input type="radio" name={`qw-mode-${page}`} value={m.id}
                checked={room.mode === m.id} onChange={() => choose(m.id)} />
              {m.name}
            </label>
          ))}
        </div>
        {/* AT THE TOP OF THE TOOLS COLUMN, beside the control that opened the
            room: a way back that has to be scrolled to is not a way back. */}
        {expanded && !one
          ? <button type="button" className="qw-return" onClick={back}>Return to conversation</button>
          : null}
        {tools}
      </div>
      <div className="qw-slot qw-conversation" data-slot="conversation">
        {conversation}
      </div>
      {scope && expanded && !one
        ? <Suspense fallback={null}><Boundary which="conversation" scope={scope} /></Suspense>
        : null}
      <div ref={workEl} className="qw-slot qw-working" data-slot="working"
        hidden={!expanded || parked('workspace')}>
        {working}
      </div>
      {/* REACHABLE IN EVERY ROOM (F11): the Page sequence is never parked. */}
      <div className="qw-slot qw-page-controls" data-slot="pageControls">
        {pageControls}
      </div>
      {one ? (
        <div className="qw-switch" role="group" aria-label="Which surface is shown">
          {showing !== 'conversation'
            ? <button type="button" className="qw-return" onClick={back}>Return to conversation</button>
            : <>
              <button type="button" data-for="tools" onClick={park('tools')}>Show tools</button>
              {expanded ? <button type="button" data-for="workspace"
                onClick={park('workspace')}>Show the workspace</button> : null}
            </>}
        </div>
      ) : null}
    </div>
  )
}

export default WorkspaceRoom
