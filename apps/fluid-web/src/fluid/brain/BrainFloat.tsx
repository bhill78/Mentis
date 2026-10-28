/* ONE SURFACE OVER THE 3D BRAIN: Fluid's float (focus/Floats.tsx), the same
 * markup and classes -- `.wk-float`, its `fl-head`, its `fl-resize` -- so it
 * looks and handles as every Fluid float does, and its touch arming
 * (focus/drag.ts). What is different is only where it is kept: in this
 * place's view state (overlays.ts), never in a conversation's arrangement,
 * so it is moved and sized here rather than through the workspace. */

import { useRef, type ReactNode } from 'react'
import { armTouchDrag } from '../focus/drag'
import { shownRect, type Overlay } from './overlays'
import '../focus/floats.css'

type Rect = { x: number; y: number; w: number; h: number }

export default function BrainFloat({ o, front, room, name, head, tools, onFront, onPlace, onMin, onClose, children }: {
  o: Overlay
  front: boolean
  room: { w: number; h: number }
  /** what it is called, for the head and for assistive technology */
  name: string
  /** said after its name in the head: where it is from */
  head?: ReactNode
  /** more of the head's tools, before minimise and close */
  tools?: ReactNode
  onFront: () => void
  onPlace: (r: Rect) => void
  onMin: () => void
  onClose: () => void
  children: ReactNode
}) {
  const el = useRef<HTMLElement | null>(null)
  const shown = shownRect(o, room)

  /** Follow the pointer from where it went down, moving or sizing. */
  const follow = (e: React.PointerEvent, size: boolean) => {
    e.preventDefault(); e.stopPropagation()
    const x0 = e.clientX, y0 = e.clientY, from = { ...shown }
    const move = (m: PointerEvent) => {
      if (m.pointerType !== 'mouse') m.preventDefault()
      const dx = m.clientX - x0, dy = m.clientY - y0
      onPlace(size ? { ...from, w: from.w + dx, h: from.h + dy } : { ...from, x: from.x + dx, y: from.y + dy })
    }
    const stop = () => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', stop)
      window.removeEventListener('pointercancel', stop)
    }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', stop)
    window.addEventListener('pointercancel', stop)
  }
  const grab = (e: React.PointerEvent, size: boolean) => {
    if (e.button !== 0) return
    if (armTouchDrag(e, e.currentTarget as HTMLElement, () => follow(e, size))) return
    follow(e, size)
  }

  return (
    <section ref={el} data-float-id={o.id} data-brain-overlay={o.shows.type}
      className={'wk-float bz-float' + (front ? ' front' : '')}
      style={{ left: shown.x, top: shown.y, width: shown.w, height: shown.h }}
      onPointerDown={() => { if (!front) onFront() }}
      role="dialog" aria-label={`Floating ${name}`}>
      <header className="fl-head" tabIndex={0} title="Drag to move"
        onPointerDown={(e) => { if (!(e.target as HTMLElement).closest('button, [draggable="true"]')) grab(e, false) }}
        onKeyDown={(e) => {
          const d = e.shiftKey ? 40 : 10, delta: Record<string, [number, number]> = { ArrowLeft: [-d, 0], ArrowRight: [d, 0], ArrowUp: [0, -d], ArrowDown: [0, d] }
          if (e.altKey && delta[e.key]) { e.preventDefault(); const [dx, dy] = delta[e.key]; onPlace({ ...shown, x: shown.x + dx, y: shown.y + dy }) }
          if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); onClose() }
        }}>
        <span className="zc-name">{name}</span>{head}<span className="grow" />
        <span className="fl-tools">
          {tools}
          <button className="fl-btn" onClick={onMin} aria-label={`Put ${name} away`} title="Put away (it stays open below)">–</button>
          <button className="fl-btn fl-close" onClick={onClose} aria-label={`Close ${name}`} title="Close">×</button>
        </span>
      </header>
      <div className="fl-body bz-body">{children}</div>
      <span className="fl-resize" aria-hidden="true" onPointerDown={(e) => grab(e, true)} />
    </section>
  )
}
