/* THE BOUNDARIES BESIDE THE CONVERSATION (Fluid completion, stream A; #187
 * #6: "panels should resize by dragging their boundaries ... no predefined
 * Narrow/Wide modes"; #188: "every boundary drags ... drag the rail narrow").
 *
 * Two gutters the frame draws between its panels, each a separator to drag
 * or move with the arrow keys, saying the width it gives as it moves:
 *   - the conversation's: from the rail (its narrowest, post numbers only)
 *     to as wide as the workspace allows; it replaces the three fixed
 *     widths and the ] [ steps;
 *   - the replies panel's outer edge, while replies are open.
 * Where they were left is the place's (place.ts): it comes back with the
 * place, and is saved with its arrangement.
 *
 * IN CONVERSATION FOCUS (A2, a defect). Focus gives the conversation the
 * room and steps the workspace back to nothing, so the conversation's own
 * width is not a width any more. Dragging still wrote it, and the column's
 * class -- read from that width -- clamped every post to two small lines
 * while the area stayed where it was; and the room to grow was measured on
 * the workspace, 0 wide in Focus, so a boundary could only shrink. In Focus
 * both boundaries move the edge between the conversation and the replies:
 * what one gains the other gives, the conversation never below FOCUS_MIN,
 * and its words keep their size. */

import { useEffect, useRef, useState } from 'react'
import * as nav from '../nav'
import { CONV_MIN, PRESET, READABLE, THREAD_MIN, railPx } from '../nav'
import { useNav } from './hooks'
import { workspace } from './place'
import './boundaries.css'

/** the workspace's least width (workspace.css `.wk`) */
export const WORKSPACE_MIN = 300
/** The least a focused conversation keeps beside its replies: as wide as
 *  the column is before it draws itself narrow (`nav.classOf`). */
export const FOCUS_MIN = 380

/** How much wider a panel may grow: what the workspace has beyond the
 *  least its page needs (its zones' minimums, never under WORKSPACE_MIN);
 *  in Focus, what the conversation has beyond FOCUS_MIN. */
const room = (focus = false) => {
  if (focus) {
    const conv = document.querySelector('.fx-main > .fx-conv') as HTMLElement | null
    return conv ? Math.max(0, conv.getBoundingClientRect().width - FOCUS_MIN) : 0
  }
  const wk = document.querySelector('.fx-main .wk') as HTMLElement | null
  if (!wk) return 0
  const least = Math.max(WORKSPACE_MIN, Number(wk.dataset.min) || 0)
  return Math.max(0, wk.getBoundingClientRect().width - least)
}

export default function Boundary({ which, focus = false }: { which: 'conversation' | 'replies'; focus?: boolean }) {
  if (focus) return <FocusBoundary which={which} />
  return <Dragged which={which} />
}

/** In Focus: either boundary moves the replies' edge; the conversation takes the rest. */
function FocusBoundary({ which }: { which: 'conversation' | 'replies' }) {
  const n = useNav()
  const now = n.threadPx
  /* The conversation's boundary is the replies' left edge: dragging it right
     gives the conversation room, so the replies narrow. */
  const sign = which === 'conversation' ? -1 : 1
  const [say, setSay] = useState<string | null>(null)
  const [drag, setDrag] = useState(false)
  useEffect(() => { if (!say || drag) return; const t = setTimeout(() => setSay(null), 1600); return () => clearTimeout(t) }, [say, drag])
  const set = (px: number, max: number) => {
    const v = Math.round(Math.max(THREAD_MIN, Math.min(max, px)))
    nav.setThreadPx(v)
    setSay(`Replies ${v} px`)
  }
  const keep = () => workspace.quiet((a) => ({ ...a, conversation: { ...a.conversation, replies: nav.snapshot().threadPx } }))
  const endDrag = useRef<(() => void) | null>(null)
  useEffect(() => () => endDrag.current?.(), [])
  const down = (e: React.PointerEvent) => {
    if (e.button !== 0) return
    e.preventDefault()
    endDrag.current?.()
    const x0 = e.clientX
    const t0 = now
    const max = t0 + room(true)
    setDrag(true)
    document.body.classList.add('fx-dragging')
    const mv = (ev: PointerEvent) => set(t0 + sign * (ev.clientX - x0), max)
    const stop = () => {
      window.removeEventListener('pointermove', mv)
      window.removeEventListener('pointerup', up)
      window.removeEventListener('pointercancel', cancel)
      document.body.classList.remove('fx-dragging')
      endDrag.current = null
      setDrag(false)
    }
    const up = () => { stop(); keep() }
    const cancel = () => { stop(); nav.setThreadPx(t0) }
    window.addEventListener('pointermove', mv)
    window.addEventListener('pointerup', up)
    window.addEventListener('pointercancel', cancel)
    endDrag.current = cancel
  }
  const key = (e: React.KeyboardEvent) => {
    const step = (e.shiftKey ? 64 : 16) * sign
    const max = now + room(true)
    const to = e.key === 'ArrowLeft' ? now - step
      : e.key === 'ArrowRight' ? now + step
        : e.key === 'Home' ? (sign > 0 ? THREAD_MIN : max)
          : e.key === 'End' ? (sign > 0 ? max : THREAD_MIN)
            : null
    if (to === null) return
    e.preventDefault()
    set(to, max)
    keep()
  }
  return (
    <div className={'fx-gutter' + (drag ? ' drag' : '')} data-boundary={which} data-focus=""
      role="separator" tabIndex={0} aria-orientation="vertical"
      aria-valuenow={now} aria-valuemin={THREAD_MIN}
      aria-label={which === 'conversation' ? 'Between the conversation and its replies: drag, or arrow keys' : 'Replies width: drag, or arrow keys'}
      title="Drag to share the room between the conversation and its replies (arrow keys; double-click: back to the replies' usual width)"
      onPointerDown={down} onKeyDown={key}
      onFocus={() => setSay(`Replies ${now} px`)}
      onDoubleClick={() => { set(400, now + room(true)); keep() }}>
      <i />
      {say && <span className="fx-readout" role="status">{say}</span>}
    </div>
  )
}

/* THE CONVERSATION IS READABLE OR THE RAIL (the owner's decision). Dragged
   narrower than READABLE it stays at READABLE; dragged on past it by more
   than SNAP the edge says that letting go minimizes it, and letting go
   does -- dragging back first keeps it at READABLE. Dragged out of the rail
   (by more than a nudge) or clicked there, it opens at the last readable
   width, never a sliver. The arrow keys do the same a step at a time: one
   step left from READABLE is the rail, one right from the rail opens it;
   Enter opens or minimizes it. */
const SNAP = 24
const NUDGE = 4

function Dragged({ which }: { which: 'conversation' | 'replies' }) {
  const n = useNav()
  const conv = which === 'conversation'
  /* the width it is drawn at: an object aside may hold it narrower than
     convPx, or want of room draw it as the rail */
  const now = conv ? nav.drawnConvPx(n) : n.threadPx
  const [say, setSay] = useState<string | null>(null)
  const [drag, setDrag] = useState(false)
  const [snap, setSnap] = useState(false)
  useEffect(() => { if (!say || drag) return; const t = setTimeout(() => setSay(null), 1600); return () => clearTimeout(t) }, [say, drag])
  const NO_ROOM = 'No room to open it beside these: close the replies or the object'
  const words = (px: number) => conv
    ? (railPx(px) ? (nav.squeezed(nav.snapshot()) ? NO_ROOM : 'Conversation: rail') : `Conversation ${px} px`)
    : `Replies ${px} px`
  const set = (px: number) => {
    const v = conv ? (railPx(px) ? CONV_MIN : Math.round(px)) : Math.round(Math.max(THREAD_MIN, px))
    if (conv) nav.sizeConvPx(v)
    else nav.setThreadPx(v)
    setSay(words(v))
    return v
  }
  /** Minimized: the rail, opening again at `back` (the last readable width). */
  const toRail = (back: number) => {
    nav.sizeConvPx(CONV_MIN, undefined, back)
    setSay('Conversation: rail')
  }
  /** Opened out of the rail, as far as `max` allows: its last readable width. */
  const open = (max: number) => {
    const want = nav.snapshot().openPx ?? PRESET.wide
    if (max < READABLE || nav.squeezed(nav.snapshot())) { setSay(NO_ROOM); return }
    set(Math.min(max, Math.max(READABLE, want)))
  }
  const keep = () => workspace.quiet((a) => ({
    ...a, conversation: { ...a.conversation, [conv ? 'width' : 'replies']: conv ? nav.snapshot().convPx : nav.snapshot().threadPx },
  }))
  /* A drag under way ends when the pointer is cancelled or the boundary
     goes, and takes the body's drag class with it (opr-52e4899752df). */
  const endDrag = useRef<(() => void) | null>(null)
  useEffect(() => () => endDrag.current?.(), [])
  const down = (e: React.PointerEvent) => {
    if (e.button !== 0) return
    e.preventDefault()
    endDrag.current?.()
    const x0 = e.clientX
    const s0 = now
    const was = nav.snapshot()
    const max = s0 + room()
    const fromRail = conv && railPx(s0)
    /* the readable width the rail opens to again if this drag minimizes it */
    const back = fromRail ? (was.openPx ?? PRESET.wide) : s0
    let moved = false, armed = false
    setDrag(true)
    document.body.classList.add('fx-dragging')
    const arm = (on: boolean) => { if (on !== armed) { armed = on; setSnap(on) } }
    const mv = (ev: PointerEvent) => {
      const dx = ev.clientX - x0
      if (Math.abs(dx) > NUDGE) moved = true
      const to = s0 + dx
      if (!conv) { set(Math.min(max, to)); return }
      if (fromRail) {
        if (dx <= NUDGE) { if (!railPx(nav.snapshot().convPx)) set(CONV_MIN); else setSay(words(CONV_MIN)); return }
        if (max < READABLE || nav.squeezed(was)) { setSay(NO_ROOM); return }
        set(Math.min(max, Math.max(back, to)))
        return
      }
      if (to >= READABLE) { arm(false); set(Math.min(max, to)); return }
      set(READABLE)
      arm(to < READABLE - SNAP)
      setSay(armed ? 'Let go to minimize it to the rail' : `Conversation ${READABLE} px: as narrow as it reads`)
    }
    const stop = () => {
      window.removeEventListener('pointermove', mv)
      window.removeEventListener('pointerup', up)
      window.removeEventListener('pointercancel', cancel)
      document.body.classList.remove('fx-dragging')
      endDrag.current = null
      setDrag(false)
      arm(false)
    }
    const up = () => {
      const minimize = armed
      stop()
      if (minimize) toRail(back)
      else if (fromRail && !moved) open(max)     // the rail clicked
      keep()
    }
    /* Cancelled: back where it was. A width never sized under anything is
       passed as null, not undefined -- undefined would take sizeConvPx's
       default (the open object) and draw the width hidden behind it. */
    const cancel = () => {
      stop()
      if (conv) nav.sizeConvPx(was.convPx, was.sizedUnder ?? null, was.openPx)
      else nav.setThreadPx(s0)
    }
    window.addEventListener('pointermove', mv)
    window.addEventListener('pointerup', up)
    window.addEventListener('pointercancel', cancel)
    endDrag.current = cancel
  }
  const key = (e: React.KeyboardEvent) => {
    const step = e.shiftKey ? 64 : 16
    const max = now + room()
    if (conv) {
      const rail = railPx(now)
      const k = e.key
      if (!['ArrowLeft', 'ArrowRight', 'Home', 'End', 'Enter', ' '].includes(k)) return
      e.preventDefault()
      if (rail) {
        if (k === 'ArrowRight' || k === 'End' || k === 'Enter' || k === ' ') {
          open(max)
          if (k === 'End' && !railPx(nav.snapshot().convPx) && !nav.squeezed(nav.snapshot())) set(Math.max(READABLE, max))
        } else setSay(words(now))
      } else if (k === 'ArrowLeft') {
        if (now - step >= READABLE) set(now - step)
        else if (now > READABLE) set(READABLE)
        else toRail(now)
      } else if (k === 'ArrowRight') set(Math.min(max, now + step))
      else if (k === 'End') set(Math.max(now, max))
      else toRail(now)                                 // Home, Enter, Space: minimize
      keep()
      return
    }
    const to = e.key === 'ArrowLeft' ? now - step
      : e.key === 'ArrowRight' ? Math.min(max, now + step)
        : e.key === 'Home' ? THREAD_MIN
          : e.key === 'End' ? max
            : null
    if (to === null) return
    e.preventDefault()
    set(to)
    keep()
  }
  return (
    <div className={'fx-gutter' + (drag ? ' drag' : '') + (snap ? ' snap' : '')} data-boundary={which}
      data-rail={conv && railPx(now) ? '' : undefined}
      role="separator" tabIndex={0} aria-orientation="vertical"
      aria-valuenow={now} aria-valuemin={conv ? CONV_MIN : THREAD_MIN}
      aria-valuetext={conv ? (railPx(now) ? 'minimized to the rail' : `${now} pixels`) : undefined}
      aria-label={conv ? `Conversation width: drag, or arrow keys; narrower than ${READABLE} px it is minimized to the rail. Enter opens or minimizes it` : 'Replies width: drag, or arrow keys'}
      title={conv
        ? (railPx(now) ? 'Click or drag out to open the conversation again (Enter, or the right arrow)'
          : `Drag to give the conversation more or less room; past ${READABLE} px it minimizes to the rail (arrow keys; double-click: back to its usual width)`)
        : 'Drag to make the replies wider or narrower (arrow keys)'}
      onPointerDown={down} onKeyDown={key}
      onFocus={() => setSay(words(now))}
      onDoubleClick={() => { set(conv ? PRESET.wide : 400); keep() }}>
      <i />
      {say && <span className="fx-readout" role="status">{say}</span>}
    </div>
  )
}
