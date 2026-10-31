import { useRef, type HTMLAttributes, type ReactNode } from 'react'
import type { Appearance } from '../present'
import type { Slot } from '../workspace/tree'
import type { WindowActs } from '../workspace/zoneMenu'
import { SurfaceChrome, t2Opener } from '../surface/SurfaceChrome'
import { chromeTarget, guarded, windowHost } from '../surface/chromeHosts'
import { useInputMode } from '../frame/narrow'
import type { HostOp } from '../surface/actions/providers/ops'
import type { ChromeVisibility, SurfaceRegion } from '../surface/types'

/** What a floating surface's host lends its frame: the window's own
 *  functions (the registry's host), where it is drawn, and how its head is
 *  dragged and handled with a mouse and the keyboard. */
export interface FloatingZoneHead {
  /** where an object float came from (FromPost), said after its name */
  from?: ReactNode
  beforeMenu?: ReactNode
  afterMenu?: ReactNode
  tidy?: () => void
  /** the head's mouse drag, double-click and keys (Floats.tsx headProps) */
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

/** The registry target a floating surface's chrome runs: the window's own
 *  functions lent as its host, its settings opened at `settingsAt()`. */
function useFloatingTarget(name: string, floating: FloatingZoneHead, settingsAt: () => HTMLElement | null, onMenu: (el: HTMLElement) => void) {
  const input = useInputMode()
  const at = floating.placement ?? 'float'
  const host = guarded(windowHost(floating.window ?? {}, {
    ...(floating.window || floating.setSlot ? { settings: () => { const el = settingsAt(); if (el) onMenu(el) } } : {}),
    closeHere: floating.closeHere, moveUp: floating.moveUp, moveDown: floating.moveDown,
  }), name, input)
  return { at, target: chromeTarget(floating.id ?? 'window:' + name, 'float', at, host) }
}

/** Whether an event on a frame's wrapper (`.fl-host`, whose one child is the
 *  frame) landed on that frame's own bar: not a nested surface's, nor the
 *  body, header region or footer. */
export const onBar = (e: { target: EventTarget; currentTarget: HTMLElement }): boolean => {
  const bar = (e.target as Element).closest?.('.sc')
  return !!bar && bar.parentElement === e.currentTarget.firstElementChild
}

/** A press on the bar that is not the grip's (it drags itself) nor a control's. */
export const barDrag = (e: { target: EventTarget; currentTarget: HTMLElement }): boolean =>
  onBar(e) && !(e.target as Element).closest('.sc-grip, button, input, [draggable="true"]')

/** THE FRAME OF EVERY FLOATING SURFACE (surface composition package 2): the
 *  conversation's window, a run's, a section's, a thread's -- SurfaceChrome
 *  with the window's own functions lent as its host and what it shows as its
 *  body. Its ⚙ lists every action; the window's settings (Pin, Look, what it
 *  shows) open from its Look row, as `onMenu` draws them, at ⚙. Where it
 *  came from (`floating.from`) leads its header content.
 *
 *  THE HEAD. On touch only the grip drags, so a hold on the title opens the
 *  actions; with a mouse the whole head drags, a double-click and the head's
 *  keys are the host's (`floating.props`). Those reach only presses on this
 *  frame's own bar: the body, the header content's controls and the
 *  framework's buttons keep theirs. The wrapper draws nothing
 *  (display: contents). */
export function FloatingFrame({ name, title = name, floating, body, header, footer, visibility, onMenu }: {
  name: string
  title?: string
  floating: FloatingZoneHead
  body: ReactNode
  header?: SurfaceRegion
  footer?: SurfaceRegion
  visibility?: ChromeVisibility
  onMenu: (el: HTMLElement) => void
}) {
  const host = useRef<HTMLDivElement | null>(null)
  const { at, target } = useFloatingTarget(name, floating, () => t2Opener(host.current), onMenu)
  const { onPointerDown, onDoubleClick, onKeyDown } = floating.props ?? {}
  const content = floating.from != null || header?.content != null ? <>{floating.from}{header?.content}</> : undefined
  return <div ref={host} className="fl-host"
    onPointerDown={(e) => {
      if (barDrag(e) && e.pointerType === 'mouse') onPointerDown?.(e)
    }}
    onDoubleClick={(e) => { if (onBar(e)) onDoubleClick?.(e) }}
    onKeyDown={(e) => { if (onBar(e)) onKeyDown?.(e) }}>
    <SurfaceChrome target={target} placement={at} level="standard" label={name} className="fl-frame"
      title={<span className="zc-name" title={title}>{title}</span>}
      header={content !== undefined || header?.actions ? { content, actions: header?.actions } : undefined}
      body={body} footer={footer} visibility={visibility}
      grip={onPointerDown ? { onPointerDown: (e) => onPointerDown(e as React.PointerEvent<HTMLDivElement>) } : undefined} />
  </div>
}
