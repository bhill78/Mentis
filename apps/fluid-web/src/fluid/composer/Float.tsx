/* A COMPOSER PANEL, ANCHORED TO WHAT OPENED IT, DRAWN IN THE FRAME'S LAYER.
 *
 * Not inside the composer: the conversation panel's backdrop blur would
 * become a fixed panel's containing block, and a thread's 400px sheet clips
 * whatever overflows it. Not a react-dom portal either (frame/layer.tsx says
 * why). Placed above the anchor when there is room, below otherwise, and
 * kept inside the window; Esc and a press outside close it. */

import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { useLayer } from '../frame/layer'

/** The tallest a panel is drawn, as `.fx-float`'s own rule says: min(60vh, 28rem). */
const CAP = () => Math.min(window.innerHeight * 0.6, 28 * (parseFloat(getComputedStyle(document.documentElement).fontSize) || 16))

export function Float({ at, width = 320, align = 'start', onClose, label, className, children, keepOpenOn }: {
  at: HTMLElement | null
  width?: number
  /** which of the anchor's edges the panel lines up with */
  align?: 'start' | 'end'
  onClose: () => void
  label: string
  className?: string
  children: ReactNode
  /** presses inside this element do not close the panel (its own field) */
  keepOpenOn?: HTMLElement | null
}) {
  const box = useRef<HTMLDivElement | null>(null)
  const [pos, setPos] = useState<{ left: number; top: number; up: boolean; room: number } | null>(null)
  /* IT ALWAYS FITS THE WINDOW: above the anchor when all of it fits there,
     else on whichever side has more room, never taller than that side --
     what then does not fit scrolls inside it, never off the screen. */
  const place = () => {
    if (!at) return
    const r = at.getBoundingClientRect()
    const above = Math.floor(r.top - 14), below = Math.floor(window.innerHeight - r.bottom - 14)
    const natural = Math.min(box.current?.scrollHeight ?? 240, CAP())
    const up = natural <= above || (natural > below && above >= below)
    const room = Math.max(80, up ? above : below)
    const h = Math.min(natural, room)
    const w = Math.min(width, window.innerWidth - 16)
    const left = Math.round(Math.max(8, Math.min(align === 'end' ? r.right - w : r.left, window.innerWidth - w - 8)))
    const top = Math.round(up ? Math.max(8, r.top - h - 6) : r.bottom + 6)
    /* Only a real move re-renders: this runs after every render. */
    setPos((p) => (p && p.left === left && p.top === top && p.room === room ? p : { left, top, up, room }))
  }
  useLayoutEffect(place)
  useEffect(() => {
    const away = (e: MouseEvent) => {
      const t = e.target as Node
      if (box.current?.contains(t) || at?.contains(t) || keepOpenOn?.contains(t)) return
      onClose()
    }
    const key = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      e.preventDefault()
      e.stopPropagation()
      onClose()
    }
    document.addEventListener('mousedown', away, true)
    document.addEventListener('keydown', key, true)
    window.addEventListener('resize', place)
    return () => {
      document.removeEventListener('mousedown', away, true)
      document.removeEventListener('keydown', key, true)
      window.removeEventListener('resize', place)
    }
  })
  /* The layer draws after this renders, so the box is measured once it is
     there, and again whenever its contents change its height. */
  const watch = useRef<ResizeObserver | null>(null)
  useEffect(() => () => watch.current?.disconnect(), [])
  const hold = (el: HTMLDivElement | null) => {
    if (el === box.current) return
    box.current = el
    watch.current?.disconnect()
    if (el) {
      watch.current = new ResizeObserver(() => place())
      watch.current.observe(el)
    }
  }
  useLayer(
    <div ref={hold} className={'fx-float' + (className ? ' ' + className : '')} role="dialog" aria-label={label}
      style={{ width: `min(${width}px, calc(100vw - 16px))`, left: pos?.left ?? -9999, top: pos?.top ?? -9999,
        maxHeight: pos ? Math.min(pos.room, CAP()) : undefined }}>
      {children}
    </div>,
  )
  return null
}
