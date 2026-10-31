/* SURFACE CHROME: ONE CHROME FOR EVERY SURFACE (plan adm-b848fa881c8d §3.6;
 * part P4; surface composition, owner Turn #1512, plan ent-2d8422d49d7c).
 *
 * A body-bearing surface is a FRAME (SurfaceChrome):
 *
 *   [ grip · title · chip · header content · header actions · T1 · ⋯/⚙ (T2) · × ]
 *   body
 *   [ footer content · footer actions ]
 *
 * The body is required; the header and footer are content's, optional, and
 * the framework's mechanics are never content's. What each visibility (full,
 * minimal, hidden) draws is decided in chrome.ts (layoutOf); this file draws
 * it. The Page bar is the one bar-only surface (SurfaceBar); every other
 * surface is a frame (surface composition package 5 removed P4's header-only
 * chrome).
 *
 * T1 is ActionBar within the placement's budget, without the region actions,
 * cut from the end by the width the bar has; T2 is ActionMenu, an anchored
 * popover, or a bottom sheet in compact and on coarse input in medium; × is
 * Close (this device only), where Close is available, and always on a stack
 * card or a sheet. Remove from workspace is never in T1 and is drawn apart in
 * T2 (chrome.ts).
 *
 * INPUT. On coarse input T1 is always shown and every target is 44 px
 * (--touch-target). A press held on the title, or on the surface's body,
 * opens T2; on the grip the same hold is the drag (armTouchDrag). With a
 * mouse, right-click on the chrome or the body opens T2. In the body, every
 * interactive element, conversation content and a text selection keep their
 * own presses (chrome.ts pressZone), except the body's own button
 * (bodyIsControl), whose hold and right-click are the frame's. Focus or a
 * press anywhere in the frame aims Ctrl/⌘+K at it. */

import { useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode, type RefObject } from 'react'
import { createPortal } from 'react-dom'
import type { ActionCtx, ActionDef, ActionTarget } from './actions/types'
import type {
  Availability, ChromeVisibility, Level, SurfaceBarProps, SurfaceChromeProps, SurfaceKind, SurfaceRegion,
} from './types'
import type { ZoneCtl } from '../workspace/TreeView'
import { chromeTarget, guarded, sectionHost, type SectionExtras } from './chromeHosts'
import { registry } from './actions/registry'
import { installProviders } from './actions/providers'
import { hostCtx } from './actions/targets'
import { pointAt } from './actions/paletteStore'
import { ActionBar, ActionMenu, RegionActions } from './actions/ActionMenu'
import { saysOf } from './actions/words'
import {
  APART_WORD, T1_WIDTH, T2_APART, budgetOf, closeShown, contextOpens, cutToWidth, layoutOf, pressOf, pressZone, primaryAsk,
  regionActions, t1Of, t1Room, t1Shown, t2Form, t2Mark,
  type ChromePlacement, type PressHit, type PressZone,
} from './chrome'
import { useInputMode, usePresentationClass } from '../frame/narrow'
import { workspace } from '../workspace/place'
import { Sheet } from '../frame/Sheet'
import { ESC, onEscape } from '../escape'
import './surfaceChrome.css'

/** The context the chrome runs actions in: this class and input, and
 *  workspace.apply for a verb no host lends (P1). */
export function chromeCtx(cls: ActionCtx['cls'], input: ActionCtx['input']): ActionCtx {
  return { ...hostCtx(cls, (id, c) => workspace.apply(id, c)), input }
}

const CONTROL = 'button, a, input, select, textarea, label, [contenteditable=""], [contenteditable="true"], [draggable="true"], [role="slider"], [role="separator"], .fl-resize'
/** The framework's own buttons: a right-click on them opens T2. */
const FRAMEWORK_CONTROL = '.sc-t1, .sc-t2, .sc-close, .am-region'

/** What a press on `el` landed on (chrome.ts PressHit). `body` is the frame
 *  region pressed in, for the body's own button and a live text selection. */
function hitOf(el: Element | null, body?: Element | null, bodyIsControl = false): PressHit {
  if (!el) return { grip: false, title: false, control: true, conversation: false }
  const control = el.closest(CONTROL)
  let own = false
  if (control && bodyIsControl && body?.contains(control)) {
    const outer = control.parentElement?.closest(CONTROL)
    own = !outer || !body.contains(outer)
  }
  const sel = body && typeof window !== 'undefined' ? window.getSelection() : null
  return {
    grip: !!el.closest('.sc-grip'),
    title: !!el.closest('.sc-title'),
    control: !!control,
    own,
    conversation: !!el.closest('.fx-conv, .fq-conv-body'),
    selection: !!(sel && !sel.isCollapsed && sel.anchorNode && body?.contains(sel.anchorNode)),
  }
}

/** What a press on `el` inside the chrome (or its surface) is. */
const zoneOf = (el: Element | null, inBar: boolean): PressZone => pressZone(hitOf(el), inBar ? 'bar' : 'body')

const closeOf = (t: ActionTarget, ctx: ActionCtx): Availability =>
  registry.list(t, ctx).find((x) => x.def.id === 'close')?.availability ?? ({ state: 'absent' } as Availability)

/** A section's chip: following what is read, or holding one thing. */
function Chip({ target }: { target: ActionTarget }) {
  const s = target.surface?.state
  if (s?.kind !== 'section') return null
  const following = s.binding.mode === 'following'
  return <span className={'sc-chip' + (following ? ' following' : ' held')} data-binding={s.binding.mode}
    title={following ? 'Following: it shows what you read, as it changes' : 'Holding: it keeps what it shows'}
    aria-label={following ? 'Following' : 'Holding'}>{following ? '⇢' : '⇥'}</span>
}

/* -- what every presenter shares: the context, T2, the long-press ------------- */

type Core = ReturnType<typeof useChromeCore>

function useChromeCore(target: ActionTarget, name: string, anchor: RefObject<HTMLElement | null>) {
  installProviders()
  const cls = usePresentationClass()
  const input = useInputMode()
  const ctx = useMemo(() => chromeCtx(cls, input), [cls, input])
  const opener = useRef<HTMLButtonElement | null>(null)
  const [menu, setMenu] = useState<HTMLElement | null>(null)
  const openMenu = () => setMenu(opener.current ?? anchor.current)
  const closeMenu = () => setMenu(null)

  /* LONG-PRESS. A press that opened T2 does not also click what it was held on. */
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

  const form = t2Form(cls, input)
  const t2 = menu && <ActionMenu target={target} ctx={ctx} label={`${name}: actions`} onDone={closeMenu} apart={T2_APART} apartWord={APART_WORD} />
  const popup = t2 && (form === 'sheet'
    ? <BottomSheet label={`${name}: actions`} onClose={closeMenu}>{t2}</BottomSheet>
    : <Sheet anchor={menu} onClose={closeMenu} label={`${name}: actions`} className="sc-pop">{t2}</Sheet>)
  const aim = () => pointAt({ target, ctx, name })
  return { cls, input, ctx, name, target, opener, menu, setMenu, openMenu, closeMenu, beginRef, popup, aim }
}

/** ⋯ or ⚙: every action here. Drawn outside T1, so no width cut removes it. */
function T2Button({ core, placement }: { core: Core; placement: ChromePlacement }) {
  const { menu, name } = core
  return <button ref={core.opener} type="button" className="sc-t2 wk-zmenu fl-btn" aria-haspopup="menu" aria-expanded={!!menu}
    aria-label={`${name}: actions`} title={`Every action here (${t2Mark(placement) === '⚙' ? 'settings, ' : ''}right-click or hold)`}
    onClick={(e) => (menu ? core.closeMenu() : core.setMenu(e.currentTarget))}>{t2Mark(placement)}</button>
}

/** ×: Close, this device only. */
function CloseButton({ core, close }: { core: Core; close: Availability }) {
  const closeTitle = close.state === 'disabled' ? `Close: ${close.reason.message}` : saysOf('close')
  return <button type="button" className="sc-close fl-btn fl-close" aria-label={`Close ${core.name} here`} title={closeTitle}
    aria-disabled={close.state !== 'available' || undefined}
    onClick={(e) => { e.stopPropagation(); if (close.state === 'available') void registry.run('close', core.target, core.ctx).catch((x: Error) => console.warn(`close: ${x.message}`)) }}>×</button>
}

/** The framework's bar: grip · title · chip · extra · T1 · T2 · ×. */
function Bar({ core, barRef, placement, level, grip, title, showTitle = true, chip = true, extra, t1, close, showClose, aimOnFocus, children, className }: {
  core: Core
  barRef: RefObject<HTMLDivElement | null>
  placement: ChromePlacement
  level: Level
  grip?: SurfaceChromeProps['grip']
  title: ReactNode
  showTitle?: boolean
  chip?: boolean
  extra?: ReactNode
  t1: ActionDef[]
  close: Availability
  showClose: boolean
  aimOnFocus: boolean
  children?: ReactNode
  className?: string
}) {
  const { input, target, ctx, name } = core
  const [room, setRoom] = useState(Number.POSITIVE_INFINITY)
  const shown = cutToWidth(t1, room, T1_WIDTH[input])

  /* WIDTH CUTS T1, never adds: the room left once the grip, the chip, the
     extra tools, T2 and × have theirs and the title its least. Read after
     every drawing; T1 is not counted, so cutting it cannot move the reading. */
  useLayoutEffect(() => {
    const el = barRef.current
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

  return (
    <div ref={barRef} className={'sc' + (className ? ' ' + className : '')} data-placement={placement} data-level={level}
      data-input={input} data-t1={t1Shown(input)} role="group" aria-label={`${name} chrome`}
      onFocusCapture={aimOnFocus ? core.aim : undefined}
      onPointerDown={(e) => core.beginRef.current(e, zoneOf(e.target as Element, true))}
      onContextMenu={(e) => {
        if (!contextOpens(zoneOf(e.target as Element, true), 'bar', !!(e.target as Element).closest(FRAMEWORK_CONTROL))) return
        e.preventDefault()
        core.openMenu()
      }}>
      {grip && <span className="sc-grip fl-drag-grip" aria-hidden="true" title="Drag to move (hold, on touch)"
        onPointerDown={(e) => grip.onPointerDown(e)}>⠿</span>}
      {showTitle && <span className="sc-title">{title}</span>}
      {chip && <Chip target={target} />}
      {extra}
      <span className="sc-grow" />
      {shown.length > 0 && <span className="sc-t1"><ActionBar target={target} ctx={ctx} budget={shown.length} defs={shown} /></span>}
      <T2Button core={core} placement={placement} />
      {showClose && <CloseButton core={core} close={close} />}
      {children}
    </div>
  )
}

/* -- the frame ----------------------------------------------------------------- */

/** A body-bearing surface: content's header and footer around its required
 *  body, the framework's mechanics around both. */
export function SurfaceChrome({ target, placement, level, title, label, body, bodyIsControl = false, header, footer, visibility = 'full', grip, className }: SurfaceChromeProps) {
  const frame = useRef<HTMLDivElement | null>(null)
  const bar = useRef<HTMLDivElement | null>(null)
  const core = useChromeCore(target, label, frame)
  const { ctx, input } = core
  const regions = regionActions(header?.actions, footer?.actions)
  const close = closeOf(target, ctx)
  const lay = layoutOf({
    visibility, placement, level, input, close: close.state, grip: !!grip, headerContent: header?.content != null,
    primary: registry.primary(target, ctx, primaryAsk(placement, level, regions.header.length + regions.footer.length)),
    header: header?.actions, footer: footer?.actions,
  })

  /* PRESSES ON THE BODY, HEADER AND FOOTER: this frame's own only. A nested
     surface (a section, another frame) in the body has its own chrome. */
  const mine = (t: EventTarget | null) => {
    const inner = (t as Element | null)?.closest?.('section, .sc-frame')
    return !!frame.current && (inner === frame.current || !inner || !frame.current.contains(inner))
  }
  const zoneIn = (e: { target: EventTarget | null; currentTarget: Element }) =>
    pressZone(hitOf(e.target as Element, e.currentTarget, bodyIsControl && e.currentTarget.classList.contains('sc-body')), 'body')
  const region = {
    onPointerDown: (e: React.PointerEvent<HTMLDivElement>) => { if (mine(e.target)) core.beginRef.current(e, zoneIn(e)) },
    onContextMenu: (e: React.MouseEvent<HTMLDivElement>) => {
      if (!mine(e.target) || !contextOpens(zoneIn(e), 'body')) return
      e.preventDefault()
      core.openMenu()
    },
  }

  const headerRegion = lay.headerAt !== 'none' && <>
    {header?.content}
    <RegionActions ids={lay.headerActions} target={target} ctx={ctx} region="header" />
  </>
  const hasFooter = footer?.content != null || lay.footerActions.length > 0

  return (
    <div ref={frame} className={'sc-frame' + (className ? ' ' + className : '')} data-visibility={lay.visibility} data-access={lay.access}
      data-placement={placement} data-level={level} data-input={input} role="group" aria-label={label}
      onFocusCapture={core.aim} onPointerDownCapture={core.aim}>
      {lay.bar && <Bar core={core} barRef={bar} placement={placement} level={level} grip={lay.grip ? grip : undefined}
        title={title} showTitle={lay.title} chip={lay.chip} extra={lay.headerAt === 'bar' ? headerRegion : null}
        t1={lay.t1} close={close} showClose={lay.close} aimOnFocus={false} />}
      {!lay.bar && <span className="sc-access" data-access={lay.access}><T2Button core={core} placement={placement} /></span>}
      {lay.headerAt === 'above' && <div className="sc-region sc-header" {...region}>{headerRegion}</div>}
      <div className="sc-body" data-own={bodyIsControl || undefined} {...region}>{body}</div>
      {hasFooter && <div className="sc-region sc-footer" {...region}>
        {footer?.content}
        <RegionActions ids={lay.footerActions} target={target} ctx={ctx} region="footer" />
      </div>}
      {core.popup}
    </div>
  )
}

/* -- the one bar-only surface ---------------------------------------------------- */

/** The Page bar's tools: a bar and nothing else (SurfaceBarProps). */
export function SurfaceBar({ target, level, title, label, extra, className }: SurfaceBarProps) {
  const bar = useRef<HTMLDivElement | null>(null)
  const core = useChromeCore(target, label, bar)
  const budget = budgetOf('page-bar', level)
  const t1 = t1Of(registry.primary(target, core.ctx, primaryAsk('page-bar', level, 0)), budget)
  const close = closeOf(target, core.ctx)
  return <Bar core={core} barRef={bar} placement="page-bar" level={level} title={title} extra={extra} t1={t1}
    close={close} showClose={closeShown('page-bar', close.state)} aimOnFocus className={className}>{core.popup}</Bar>
}

/** A docked section's frame: its ZoneCtl (workspace/TreeView.tsx) lent as
 *  the host, the grip its drag, the section's own caption tools its header
 *  content, what it shows its body (surface composition package 2). */
export function SectionChrome({ id, name, ctl, title, body, header, footer, visibility, also, binding, kind = 'section', level = 'standard', className }: {
  id: string
  name: string
  ctl: ZoneCtl
  title: React.ReactNode
  body: React.ReactNode
  header?: SurfaceRegion
  footer?: SurfaceRegion
  visibility?: ChromeVisibility
  also?: SectionExtras
  binding?: { following: boolean; resource?: string }
  kind?: SurfaceKind
  level?: Level
  className?: string
}) {
  const input = useInputMode()
  const target = chromeTarget(id, kind, 'dock', guarded(sectionHost(ctl, also), name, input), binding)
  const drag = ctl.drag
  return <SurfaceChrome target={target} placement="dock" level={level} title={title} label={name} body={body}
    header={header} footer={footer} visibility={visibility} className={'wk-zframe' + (className ? ' ' + className : '')}
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
