/* SURFACE CHROME: ONE CHROME FOR EVERY SURFACE (plan adm-b848fa881c8d §3.6;
 * part P4).
 *
 *   grip · title · [binding chip, sections only] · extra · T1 · ⋯/⚙ (T2) · ×
 *
 * It replaces the six chromes that grew apart: a section's caption tools
 * (TreeView ZoneTools), the window header (FloatingHeader), the narrow
 * screen's card head (NarrowFloats), the Brain window's header (BrainFloat),
 * the launcher tile's ⋯ (Launcher) and the Page bar's tools (TopBar). Each
 * now draws this, with its own functions lent to the registry
 * (chromeHosts.ts); every control runs through registry.run (P3).
 *
 * T1 is ActionBar within the placement's budget, cut from the end by the
 * width the bar has; T2 is ActionMenu, an anchored popover, or a bottom sheet
 * in compact and on coarse input in medium; × is Close (this device only),
 * where Close is available, and always on a stack card or a sheet. Remove
 * from workspace is never in T1 and is drawn apart in T2 (chrome.ts).
 *
 * INPUT. On coarse input T1 is always shown and every target is 44 px
 * (--touch-target). A press held on the title, or on the surface's body,
 * opens T2; on the grip the same hold is the drag (armTouchDrag). With a
 * mouse, right-click on the chrome opens T2. */

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import type { ActionCtx, ActionTarget } from './actions/types'
import type { Availability, Level, SurfaceChromeProps, SurfaceKind } from './types'
import type { ZoneCtl } from '../workspace/TreeView'
import { chromeTarget, guarded, sectionHost, type SectionExtras } from './chromeHosts'
import { registry } from './actions/registry'
import { installProviders } from './actions/providers'
import { hostCtx } from './actions/targets'
import { pointAt } from './actions/paletteStore'
import { ActionBar, ActionMenu } from './actions/ActionMenu'
import { saysOf } from './actions/words'
import {
  APART_WORD, T1_WIDTH, T2_APART, budgetOf, closeShown, cutToWidth, pressOf, t1Of, t1Room, t1Shown, t2Form, t2Mark,
  type PressZone,
} from './chrome'
import { useClassNow, useInputMode } from './input'
import { workspace } from '../workspace/place'
import { Sheet } from '../frame/Sheet'
import { ESC, onEscape } from '../escape'
import './surfaceChrome.css'

/** The context the chrome runs actions in: this class and input, and
 *  workspace.apply for a verb no host lends (P1). */
export function chromeCtx(cls: ActionCtx['cls'], input: ActionCtx['input']): ActionCtx {
  return { ...hostCtx(cls, (id, c) => workspace.apply(id, c)), input }
}

/** What a press on `el` inside the chrome (or its surface) is. */
const zoneOf = (el: Element | null, inBar: boolean): PressZone => {
  if (!el) return 'control'
  if (el.closest('.sc-grip')) return 'grip'
  if (inBar && el.closest('.sc-title')) return 'title'
  if (el.closest('button, a, input, select, textarea, label, [contenteditable=""], [contenteditable="true"], [draggable="true"], [role="slider"], [role="separator"], .fl-resize')) return 'control'
  /* the conversation drawn in a surface keeps its own presses (its posts, its grip) */
  if (!inBar && el.closest('.fx-conv, .fq-conv-body')) return 'control'
  return inBar ? 'title' : 'body'
}

const nameOf = (t: ActionTarget) => t.surface?.state.id ?? t.resource?.address ?? 'here'

/** A section's chip: following what is read, or holding one thing. */
function Chip({ target }: { target: ActionTarget }) {
  const s = target.surface?.state
  if (s?.kind !== 'section') return null
  const following = s.binding.mode === 'following'
  return <span className={'sc-chip' + (following ? ' following' : ' held')} data-binding={s.binding.mode}
    title={following ? 'Following: it shows what you read, as it changes' : 'Holding: it keeps what it shows'}
    aria-label={following ? 'Following' : 'Holding'}>{following ? '⇢' : '⇥'}</span>
}

export function SurfaceChrome({ target, placement, level, title, grip, extra, className }: SurfaceChromeProps) {
  installProviders()
  const cls = useClassNow()
  const input = useInputMode()
  const ctx = useMemo(() => chromeCtx(cls, input), [cls, input])
  const bar = useRef<HTMLDivElement | null>(null)
  const opener = useRef<HTMLButtonElement | null>(null)
  const [menu, setMenu] = useState<HTMLElement | null>(null)
  const [room, setRoom] = useState(Number.POSITIVE_INFINITY)

  const budget = budgetOf(placement, level)
  const t1 = t1Of(registry.primary(target, ctx, budget), budget)
  const shown = cutToWidth(t1, room, T1_WIDTH[input])
  const close = registry.list(target, ctx).find((x) => x.def.id === 'close')?.availability ?? ({ state: 'absent' } as Availability)
  const form = t2Form(cls, input)
  const name = nameOf(target)

  /* WIDTH CUTS T1, never adds: the room left once the grip, the chip, the
     extra tools, T2 and × have theirs and the title its least. Read after
     every drawing; T1 is not counted, so cutting it cannot move the reading. */
  useLayoutEffect(() => {
    const el = bar.current
    if (!el || typeof ResizeObserver === 'undefined') return
    const read = () => {
      let fixed = 0
      for (const k of Array.from(el.children) as HTMLElement[]) {
        if (k.classList.contains('sc-t1') || k.classList.contains('sc-title') || k.classList.contains('sc-grow')) continue
        fixed += k.offsetWidth + 4
      }
      const next = t1Room(el.clientWidth, fixed)
      setRoom((r) => (Math.abs(r - next) < 2 ? r : next))
    }
    read()
    const ro = new ResizeObserver(read)
    ro.observe(el)
    return () => ro.disconnect()
  })

  const openMenu = () => setMenu(opener.current ?? bar.current)
  const closeMenu = () => setMenu(null)

  /* LONG-PRESS, on the chrome's title and on the surface's body. A press that
     opened T2 does not also click what it was held on. */
  const press = useRef<ReturnType<typeof pressOf> | null>(null)
  const swallowClick = () => {
    const eat = (e: Event) => { e.stopPropagation(); e.preventDefault() }
    window.addEventListener('click', eat, { capture: true, once: true })
    setTimeout(() => window.removeEventListener('click', eat, { capture: true }), 500)
  }
  const begin = (e: PointerEvent | React.PointerEvent, zone: PressZone) => {
    press.current?.cancel()
    if (zone === 'grip' || zone === 'control') return
    const p = pressOf(zone, e.pointerType, { x: e.clientX, y: e.clientY }, { menu: () => { swallowClick(); openMenu() }, drag: () => {} })
    if (!p.pending) return
    press.current = p
    const id = e.pointerId
    const move = (m: PointerEvent) => { if (m.pointerId === id) p.move(m.clientX, m.clientY) }
    const end = (m: PointerEvent) => {
      if (m.pointerId !== id) return
      p.up()
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', end)
      window.removeEventListener('pointercancel', end)
    }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', end)
    window.addEventListener('pointercancel', end)
  }
  const beginRef = useRef(begin)
  beginRef.current = begin
  useEffect(() => () => press.current?.cancel(), [])
  /* the body: the surface this chrome heads */
  useEffect(() => {
    const surface = bar.current?.parentElement?.closest('section')
    if (!surface) return
    const down = (e: PointerEvent) => {
      if (bar.current?.contains(e.target as Node)) return
      /* a nested surface has its own chrome */
      if ((e.target as Element).closest('section') !== surface) return
      beginRef.current(e, zoneOf(e.target as Element, false))
    }
    surface.addEventListener('pointerdown', down)
    return () => surface.removeEventListener('pointerdown', down)
  }, [])

  const t2 = menu && <ActionMenu target={target} ctx={ctx} label={`${name}: actions`} onDone={closeMenu} apart={T2_APART} apartWord={APART_WORD} />
  const closeTitle = close.state === 'disabled' ? `Close: ${close.reason.message}` : saysOf('close')

  return (
    <div ref={bar} className={'sc' + (className ? ' ' + className : '')} data-placement={placement} data-level={level}
      data-input={input} data-t1={t1Shown(input)} role="group" aria-label={`${name} chrome`}
      onFocusCapture={() => pointAt({ target, ctx, name })}
      onPointerDown={(e) => beginRef.current(e, zoneOf(e.target as Element, true))}
      onContextMenu={(e) => {
        if (zoneOf(e.target as Element, true) === 'control' && !(e.target as Element).closest('.sc-t1, .sc-t2, .sc-close')) return
        e.preventDefault()
        openMenu()
      }}>
      {grip && <span className="sc-grip fl-drag-grip" aria-hidden="true" title="Drag to move (hold, on touch)"
        onPointerDown={(e) => grip.onPointerDown(e)}>⠿</span>}
      <span className="sc-title">{title}</span>
      <Chip target={target} />
      {extra}
      <span className="sc-grow" />
      {shown.length > 0 && <span className="sc-t1"><ActionBar target={target} ctx={ctx} budget={shown.length} /></span>}
      <button ref={opener} type="button" className="sc-t2 wk-zmenu fl-btn" aria-haspopup="menu" aria-expanded={!!menu}
        aria-label={`${name}: actions`} title={`Every action here (${t2Mark(placement) === '⚙' ? 'settings, ' : ''}right-click or hold)`}
        onClick={(e) => (menu ? closeMenu() : setMenu(e.currentTarget))}>{t2Mark(placement)}</button>
      {closeShown(placement, close.state) && (
        <button type="button" className="sc-close fl-btn fl-close" aria-label={`Close ${name} here`} title={closeTitle}
          aria-disabled={close.state !== 'available' || undefined}
          onClick={(e) => { e.stopPropagation(); if (close.state === 'available') void registry.run('close', target, ctx).catch((x: Error) => console.warn(`close: ${x.message}`)) }}>×</button>
      )}
      {t2 && (form === 'sheet'
        ? <BottomSheet label={`${name}: actions`} onClose={closeMenu}>{t2}</BottomSheet>
        : <Sheet anchor={menu} onClose={closeMenu} label={`${name}: actions`} className="sc-pop">{t2}</Sheet>)}
    </div>
  )
}

/** A docked section's chrome: its ZoneCtl (workspace/TreeView.tsx) lent as
 *  the host, the grip its drag. */
export function SectionChrome({ id, name, ctl, title, extra, also, binding, kind = 'section', level = 'standard', className }: {
  id: string
  name: string
  ctl: ZoneCtl
  title: React.ReactNode
  extra?: React.ReactNode
  also?: SectionExtras
  binding?: { following: boolean; resource?: string }
  kind?: SurfaceKind
  level?: Level
  className?: string
}) {
  const input = useInputMode()
  const target = chromeTarget(id, kind, 'dock', guarded(sectionHost(ctl, also), name, input), binding)
  const drag = ctl.drag
  return <SurfaceChrome target={target} placement="dock" level={level} title={title} extra={extra} className={className}
    grip={drag ? { onPointerDown: (e) => drag(e as React.PointerEvent<HTMLElement>) } : undefined} />
}

/** Where a host's own settings sheet opens: at its chrome's T2 opener. */
export const t2Opener = (inside: Element | null): HTMLElement | null => inside?.querySelector<HTMLElement>('.sc-t2') ?? (inside as HTMLElement | null)

/** T2 as a sheet from the bottom of the screen (compact, coarse medium). */
function BottomSheet({ label, onClose, children }: { label: string; onClose: () => void; children: React.ReactNode }) {
  useEffect(() => onEscape(ESC.sheet, () => { onClose(); return true }), [onClose])
  return createPortal(
    <div className="sc-scrim" onPointerDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="sc-bottom" role="dialog" aria-label={label}>
        <span className="sc-handle" aria-hidden="true" />
        {children}
      </div>
    </div>,
    document.body,
  )
}
