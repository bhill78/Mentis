/* ONE SURFACE OVER THE 3D BRAIN: Fluid's float (focus/Floats.tsx), the same
 * markup and classes -- `.wk-float`, its frame's head, its `fl-resize` -- so it
 * looks and handles as every Fluid float does, and its touch arming
 * (focus/drag.ts), and the one surface frame (surface/SurfaceChrome.tsx)
 * with its own functions lent: Put away, Dock / Float, and × Close; where it
 * is from and its own tools are the header's content, what it shows the
 * body. With a mouse its whole head drags, as a Fluid window's does. What is
 * different is only where it is kept: in this place's view state
 * (overlays.ts), never in a conversation's arrangement, so it is moved and
 * sized here rather than through the workspace. */

import { useRef, type ReactNode } from 'react'
import { armTouchDrag } from '../focus/drag'
import { MIN_FLOAT_W } from '../focus/types'
import { DOCK_W, shownRect, type Overlay } from './overlays'
import { SurfaceChrome } from '../surface/SurfaceChrome'
import { barDrag, onBar } from '../focus/FloatingHeader'
import { chromeTarget } from '../surface/chromeHosts'
import type { SurfaceHost } from '../surface/actions/providers/ops'
import '../focus/floats.css'

type Rect = { x: number; y: number; w: number; h: number }

export default function BrainFloat({ o, front, room, name, head, tools, bodyClass, onFront, onPlace, onMin, onClose, onDock, children }: {
  o: Overlay
  front: boolean
  room: { w: number; h: number }
  /** what it is called, for the head and for assistive technology */
  name: string
  /** said after its name in the head: where it is from */
  head?: ReactNode
  /** more of the head's tools, before its actions */
  tools?: ReactNode
  /** dock it as a column at a side, or float it again (null) */
  onDock?: (side: 'left' | 'right' | null) => void
  /** the body's own class, besides Fluid's float body */
  bodyClass?: string
  onFront: () => void
  onPlace: (r: Rect) => void
  onMin: () => void
  onClose: () => void
  children: ReactNode
}) {
  const el = useRef<HTMLElement | null>(null)
  /* DOCKED, it is a column the height of the field at one side: still a
     Fluid surface, only not moved or sized by hand. */
  const docked = !!o.dock
  const shown = docked ? { x: 0, y: 0, w: Math.min(DOCK_W, Math.max(MIN_FLOAT_W, room.w * 0.5)), h: room.h } : shownRect(o, room)

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
    if (e.button !== 0 || docked) return
    if (armTouchDrag(e, e.currentTarget as HTMLElement, () => follow(e, size))) return
    follow(e, size)
  }

  /* Its actions, lent to the registry: Put away (it waits in the tray),
     Dock at the nearer side or Float again, and × Close, which only this
     place's view of the Brain keeps (overlays.ts). */
  const host: SurfaceHost = {
    putAway: { run: onMin, says: 'Put away: it waits in the tray below' },
    close: { run: onClose, says: 'Close: it leaves the Brain view; nothing else changes' },
  }
  if (onDock) {
    if (docked) host.float = { run: () => onDock(null), says: 'Float it over the Brain' }
    else host.dock = { run: () => onDock(shown.x + shown.w / 2 < room.w / 2 ? 'left' : 'right'), says: 'Dock as a column at the nearer side' }
  }
  const target = chromeTarget(o.id, 'brain', docked ? 'dock' : 'float', host)

  return (
    <section ref={el} data-float-id={o.id} data-brain-overlay={o.shows.type}
      className={'wk-float bz-float' + (docked ? ' bz-docked' : '') + (front ? ' front' : '')} data-dock={o.dock}
      style={docked ? { [o.dock === 'left' ? 'left' : 'right']: 0, top: 0, bottom: 0, width: shown.w } : { left: shown.x, top: shown.y, width: shown.w, height: shown.h }}
      onPointerDown={() => { if (!front) onFront() }}
      role="dialog" aria-label={`Floating ${name}`}>
      <div className="fl-host"
        onPointerDown={(e) => { if (e.pointerType === 'mouse' && barDrag(e)) grab(e, false) }}
        onKeyDown={(e) => {
          if (!onBar(e)) return
          const d = e.shiftKey ? 40 : 10, delta: Record<string, [number, number]> = { ArrowLeft: [-d, 0], ArrowRight: [d, 0], ArrowUp: [0, -d], ArrowDown: [0, d] }
          if (e.altKey && delta[e.key]) { e.preventDefault(); const [dx, dy] = delta[e.key]; onPlace({ ...shown, x: shown.x + dx, y: shown.y + dy }) }
          if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); onClose() }
        }}>
        <SurfaceChrome target={target} placement={docked ? 'dock' : 'float'} level="standard" label={name} className="fl-frame"
          title={<span className="zc-name">{name}</span>}
          header={head != null || tools != null ? { content: <>{head}{tools}</> } : undefined}
          body={<div className={'fl-body bz-body' + (bodyClass ? ' ' + bodyClass : '')}>{children}</div>}
          grip={docked ? undefined : { onPointerDown: (e) => grab(e as React.PointerEvent, false) }} />
      </div>
      {!docked && <span className="fl-resize" aria-hidden="true" onPointerDown={(e) => grab(e, true)} />}
    </section>
  )
}
