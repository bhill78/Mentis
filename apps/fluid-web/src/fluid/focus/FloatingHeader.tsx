import type { HTMLAttributes, ReactNode } from 'react'
import { GearMark } from '../frame/IconMenu'
import type { Appearance } from '../present'
import type { Slot } from '../workspace/tree'
import type { WindowActs } from '../workspace/zoneMenu'

export interface FloatingZoneHead {
  /** Kept for the separate narrow-screen panel representation. */
  from?: ReactNode
  beforeMenu?: ReactNode
  afterMenu?: ReactNode
  tidy?: () => void
  props?: HTMLAttributes<HTMLDivElement>
  setSlot?: (fn: (slot: Slot) => Slot, words?: string) => void
  useLookForPlace?: (look: Appearance) => void
  window?: WindowActs
}

/** The one desktop header used by every floating content kind. Window-level
 * actions beyond these controls stay in the settings menu. */
export function FloatingHeader({ name, title = name, floating, menuAt, onMenu, settingsTitle }: {
  name: string
  title?: string
  floating: FloatingZoneHead
  menuAt: HTMLElement | null
  onMenu: (el: HTMLElement) => void
  settingsTitle: string
}) {
  const minimise = floating.window?.minimise
  const close = floating.window?.close
  return <div className="fl-head" {...floating.props}>
    <span className="fl-drag-grip" aria-hidden="true">⋮⋮</span>
    <span className="zc-name" title={title}>{title}</span>
    <span className="grow" />
    <span className="fl-tools">
      {minimise && <button className="fl-btn fl-minimise" onClick={minimise.run}
        aria-label={`${minimise.on ? 'Restore' : 'Minimise'} ${name}`}
        title={minimise.on ? 'Restore: open the window again where it was' : 'Minimise to a named tab at the bottom'}>{minimise.on ? '□' : '−'}</button>}
      <button className="wk-zmenu fl-btn" aria-label={`${name} settings`} title={settingsTitle}
        aria-expanded={!!menuAt} onClick={(e) => onMenu(e.currentTarget)}><GearMark /></button>
      {close && <button className="fl-btn fl-close" onClick={close} aria-label={`Close ${name}`} title="Close">×</button>}
    </span>
  </div>
}
