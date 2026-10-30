import { useRef, type HTMLAttributes, type ReactNode } from 'react'
import type { Appearance } from '../present'
import type { Slot } from '../workspace/tree'
import type { WindowActs } from '../workspace/zoneMenu'
import { LegacySurfaceChromeBar, t2Opener } from '../surface/SurfaceChrome'
import { chromeTarget, guarded, windowHost } from '../surface/chromeHosts'
import { useInputMode } from '../frame/narrow'
import type { HostOp } from '../surface/actions/providers/ops'

export interface FloatingZoneHead {
  /** where an object float came from (FromPost), said after its name */
  from?: ReactNode
  beforeMenu?: ReactNode
  afterMenu?: ReactNode
  tidy?: () => void
  props?: HTMLAttributes<HTMLDivElement>
  setSlot?: (fn: (slot: Slot) => Slot, words?: string) => void
  useLookForPlace?: (look: Appearance) => void
  window?: WindowActs
  /** the surface's id (its zone's), for the palette and Close */
  id?: string
  /** a window over the page, a card in the narrow screen's stack, or one in
   *  the medium screen's workspace sheet */
  placement?: 'float' | 'stack' | 'sheet'
  /** × here: Close on this device only (Surface Tension I-1) */
  closeHere?: HostOp
  /** a card's place in this class's stack order (P5) */
  moveUp?: HostOp
  moveDown?: HostOp
}

/** The one header of every floating content kind: SurfaceChrome (surface/
 *  SurfaceChrome.tsx) with the window's own functions lent as its host.
 *  Its ⚙ lists every action; the window's settings (Pin, Look, what it
 *  shows) open from its Look row, as `onMenu` draws them. With a mouse the
 *  whole head drags; on touch only the grip does, so a hold on the title
 *  opens the actions. */
export function FloatingHeader({ name, title = name, floating, onMenu }: {
  name: string
  title?: string
  floating: FloatingZoneHead
  menuAt: HTMLElement | null
  onMenu: (el: HTMLElement) => void
  settingsTitle: string
}) {
  const head = useRef<HTMLDivElement | null>(null)
  const input = useInputMode()
  const at = floating.placement ?? 'float'
  const host = guarded(windowHost(floating.window ?? {}, {
    ...(floating.window || floating.setSlot ? { settings: () => { const el = t2Opener(head.current); if (el) onMenu(el) } } : {}),
    closeHere: floating.closeHere, moveUp: floating.moveUp, moveDown: floating.moveDown,
  }), name, input)
  const target = chromeTarget(floating.id ?? 'window:' + name, 'float', at, host)
  const { onPointerDown, ...props } = floating.props ?? {}
  return <div ref={head} className="fl-head" {...props}
    onPointerDown={(e) => {
      if ((e.target as Element).closest('.sc-grip')) return
      if (e.pointerType === 'mouse') onPointerDown?.(e)
    }}>
    <LegacySurfaceChromeBar target={target} placement={at} level="standard"
      title={<span className="zc-name" title={title}>{title}</span>}
      extra={floating.from}
      grip={onPointerDown ? { onPointerDown: (e) => onPointerDown(e as React.PointerEvent<HTMLDivElement>) } : undefined} />
  </div>
}
