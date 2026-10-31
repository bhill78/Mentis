/* SURFACE CHROME: ITS RULES (plan adm-b848fa881c8d §3.6, rev 3 §5.2; part P4).
 *
 * What SurfaceChrome.tsx draws is decided here, browser-free, so the chrome
 * test can read every rule without a DOM:
 *
 *   T1        the direct controls: registry.primary within the placement's
 *             budget, then cut by the width it has (from the end; ⋯ is never
 *             cut, it is not in T1)
 *   T2        ⋯ or ⚙: the registry's whole list, as a bottom sheet in compact
 *             and on coarse input in medium, an anchored popover otherwise
 *   ×         Close, where it is available; always on a stack card or sheet
 *             (the narrow defect: a card with no way to close it)
 *
 * CLOSE IS NOT REMOVE (I-1). × is only ever Close: this browser device stops
 * showing it. Remove from workspace is never a T1 control, is drawn apart in
 * T2 under its own word, and asks first on coarse input, where a stray tap
 * must not take a surface off every device.
 *
 * LONG-PRESS. On the title or the body, a press held 500 ms without moving
 * 8 px opens T2; on the grip the same hold is a drag (focus/drag.ts
 * armTouchDrag), never T2. A mouse has right-click instead.
 *
 * COMPOSITION (owner Turn #1512; plan ent-2d8422d49d7c). A frame is an
 * optional content header, a required body and an optional content footer
 * (layoutOf): which framework parts each visibility shows, where the header's
 * content goes, and which region actions leave T1 (regionActions) while
 * staying in T2 and the palette. Which presses open T2 (pressZone,
 * contextOpens) is decided here too, from what the press landed on. */

import { SURFACE_VERBS, type ChromeVisibility, type InputMode, type Level, type PlacementKind, type PresentationClass } from './types'
import type { ActionDef, ActionId } from './actions/types'

export type ChromePlacement = PlacementKind | 'page-bar'

/** T1's starting budget per placement (r3 §5.2; plan §3.6's table). An icon
 *  (a launcher tile, a minimised tab, a magnet disc) has none. */
export const T1_BUDGET: Record<ChromePlacement, number> = {
  launcher: 0,
  nested: 2,
  dock: 4,
  float: 3,
  stack: 2,
  sheet: 2,
  'page-root': 5,
  'page-bar': 5,
}

/** T1's budget for a surface drawn at `placement` and `level`. */
export function budgetOf(placement: ChromePlacement, level: Level): number {
  return level === 'icon' ? 0 : T1_BUDGET[placement]
}

/** The T2 opener's mark: ⚙ where the host's whole settings are (a section, a
 *  window, a page), ⋯ on everything smaller. */
export function t2Mark(placement: ChromePlacement): '⚙' | '⋯' {
  return placement === 'dock' || placement === 'float' || placement === 'page-root' || placement === 'page-bar' ? '⚙' : '⋯'
}

/** Never drawn in T1: × draws Close itself, and Remove is never one tap. */
export const NOT_T1: readonly ActionId[] = ['close', 'removeFromWorkspace']
/** Drawn apart at the end of T2, under their own word. */
export const T2_APART: readonly ActionId[] = ['removeFromWorkspace']
export const APART_WORD = 'Remove'

/** T1 from what the registry puts first: without Close and Remove, and
 *  without what a header or footer already draws (`drawn`), within `budget`. */
export function t1Of(primary: readonly ActionDef[], budget: number, drawn: readonly ActionId[] = []): ActionDef[] {
  return primary.filter((d) => !NOT_T1.includes(d.id) && !drawn.includes(d.id)).slice(0, Math.max(0, budget))
}

/** Each direct control's width, and the least room the title keeps. */
export const T1_WIDTH = { fine: 28, coarse: 44 } as const
export const TITLE_KEEPS = 72

/** How many of `t1` fit in `room` px: cut from the end, never added to. */
export function cutToWidth<T>(t1: readonly T[], room: number, per: number): T[] {
  if (!Number.isFinite(room)) return [...t1]
  return t1.slice(0, Math.max(0, Math.min(t1.length, Math.floor(room / per))))
}

/** The room T1 has in a bar `bar` px wide whose other parts take `fixed` px. */
export const t1Room = (bar: number, fixed: number): number => bar - fixed - TITLE_KEEPS

/** Where T2 opens. */
export function t2Form(cls: PresentationClass, input: InputMode): 'sheet' | 'popover' {
  return cls === 'compact' || (cls === 'medium' && input === 'coarse') ? 'sheet' : 'popover'
}

/** T1 at rest: on coarse input there is no hover to reveal it. */
export const t1Shown = (input: InputMode): 'always' | 'hover' => (input === 'coarse' ? 'always' : 'hover')

/** Whether × is drawn: where Close is offered, and always on a stack card or a
 *  sheet, disabled with its reason when Close is not offered there. */
export function closeShown(placement: ChromePlacement, close: 'available' | 'disabled' | 'absent'): boolean {
  return close !== 'absent' || placement === 'stack' || placement === 'sheet'
}

/** Whether running `id` from the chrome asks first. */
export const asksFirst = (id: ActionId, input: InputMode): boolean => id === 'removeFromWorkspace' && input === 'coarse'
export const removeQuestion = (name: string) =>
  `Remove ${name} from this workspace on every device? Close (×) only hides it here. Undo brings it back.`

/* -- composition: header, body, footer ---------------------------------------- */

/** Never content's to place: the surface mechanics (every verb that moves,
 *  sizes, focuses or puts away a surface, × drawing Close and T2 drawing Remove
 *  apart among them), the arrangement's own verbs, and Find an action…, T2's
 *  last row. A region that names one does not draw it; T2 and the palette
 *  still offer it wherever the registry does. */
export const FRAMEWORK_OWNED: readonly ActionId[] = [
  ...SURFACE_VERBS,
  'fit', 'split', 'merge', 'tidyAround', 'makeRoom', 'keepArrangement',
  'saveLayout', 'restoreLayout', 'undo', 'resetPlace', 'putAllAway', 'layouts', 'sketch',
  'findAction',
]

/** The region actions as drawn: header first, then footer, each id once, the
 *  framework's own left out. Every id stays in T2 and the palette. */
export function regionActions(header: readonly ActionId[] = [], footer: readonly ActionId[] = []): { header: ActionId[]; footer: ActionId[] } {
  const seen = new Set<ActionId>()
  const keep = (ids: readonly ActionId[]) => ids.filter((id) => {
    if (FRAMEWORK_OWNED.includes(id) || seen.has(id)) return false
    seen.add(id)
    return true
  })
  const h = keep(header)
  return { header: h, footer: keep(footer) }
}

/** How a frame offers the framework's actions: in its bar; revealed on frame
 *  hover or focus (hidden, fine input); from a compact trigger always shown
 *  (hidden, coarse input, where there is no hover). */
export type ChromeAccess = 'bar' | 'reveal' | 'trigger'

export interface LayoutIn {
  visibility: ChromeVisibility
  placement: ChromePlacement
  level: Level
  input: InputMode
  /** registry.primary for the target, asked with room for what is left out (primaryAsk) */
  primary: readonly ActionDef[]
  close: 'available' | 'disabled' | 'absent'
  grip: boolean
  headerContent: boolean
  header?: readonly ActionId[]
  footer?: readonly ActionId[]
}

export interface ChromeLayout {
  visibility: ChromeVisibility
  access: ChromeAccess
  /** a framework bar at rest */
  bar: boolean
  grip: boolean
  /** the rich title in the bar (in minimal, only where no header content stands for it) */
  title: boolean
  chip: boolean
  /** where the header region is drawn: in the bar, above the body, nowhere */
  headerAt: 'bar' | 'above' | 'none'
  headerActions: ActionId[]
  footerActions: ActionId[]
  /** the direct controls, before the width cut */
  t1: ActionDef[]
  /** × drawn directly (hidden leaves Close to T2) */
  close: boolean
}

/** What a frame draws, at each visibility. The footer always follows the body
 *  and no visibility changes it; T2, the palette and the body's right-click and
 *  long-press reach every action at every visibility. */
export function layoutOf(i: LayoutIn): ChromeLayout {
  const regions = regionActions(i.header, i.footer)
  const drawn = [...regions.header, ...regions.footer]
  const hasHeader = i.headerContent || regions.header.length > 0
  const base = { visibility: i.visibility, headerActions: regions.header, footerActions: regions.footer }
  if (i.visibility === 'hidden') {
    return { ...base, access: i.input === 'coarse' ? 'trigger' : 'reveal', bar: false, grip: false, title: false, chip: false,
      headerAt: hasHeader ? 'above' : 'none', t1: [], close: false }
  }
  const closeIt = closeShown(i.placement, i.close)
  if (i.visibility === 'minimal') {
    return { ...base, access: 'bar', bar: true, grip: i.grip, title: !i.headerContent, chip: false,
      headerAt: hasHeader ? 'bar' : 'none', t1: [], close: closeIt }
  }
  return { ...base, access: 'bar', bar: true, grip: i.grip, title: true, chip: true,
    headerAt: hasHeader ? 'bar' : 'none', t1: t1Of(i.primary, budgetOf(i.placement, i.level), drawn), close: closeIt }
}

/** How many to ask registry.primary for, so that leaving out Close, Remove and
 *  `drawn` region actions still leaves T1 its whole budget. */
export function primaryAsk(placement: ChromePlacement, level: Level, drawn: number): number {
  const b = budgetOf(placement, level)
  return b <= 0 ? 0 : b + NOT_T1.length + drawn
}

/* -- long-press ------------------------------------------------------------- */

export const LONG_PRESS_MS = 500
export const LONG_PRESS_SLOP = 8

/** Where a press landed: the grip drags, the title or body opens T2, a
 *  control is its own. */
export type PressZone = 'grip' | 'title' | 'body' | 'control'

/** What a press landed on, read from the DOM by SurfaceChrome.tsx. */
export interface PressHit {
  grip: boolean
  /** inside the bar's title */
  title: boolean
  /** an interactive element: button, link, field, label, editable, draggable, slider, resize handle */
  control: boolean
  /** that control is the body's own button (bodyIsControl: the launcher icon, a Magnet disc) */
  own?: boolean
  /** conversation content (.fx-conv, .fq-conv-body), which keeps its own presses */
  conversation: boolean
  /** a text selection that is not collapsed: copying it is the person's */
  selection?: boolean
}

/** Which zone a press is. In the bar: the grip, the title, a control, or the
 *  bar itself (as the title). In the body, header or footer: the body's own
 *  button and plain content open T2; every other interactive element,
 *  conversation content and a live text selection keep their own behaviour. */
export function pressZone(hit: PressHit, where: 'bar' | 'body'): PressZone {
  if (hit.grip) return 'grip'
  if (where === 'bar' && hit.title) return 'title'
  if (where === 'body' && hit.own) return 'body'
  if (hit.control) return 'control'
  if (where === 'body' && (hit.conversation || hit.selection)) return 'control'
  return where === 'bar' ? 'title' : 'body'
}

/** Whether a right-click opens T2 (and so prevents the browser's menu). In
 *  the bar every zone does but an unrelated control; the framework's own
 *  buttons (T1, T2, ×) do. In the body only what pressZone calls 'body'
 *  does: an exempt target keeps the browser's menu (copy, paste, open link). */
export function contextOpens(zone: PressZone, where: 'bar' | 'body', frameworkControl = false): boolean {
  if (where === 'bar') return zone !== 'control' || frameworkControl
  return zone === 'body'
}

export interface Timers { set(fn: () => void, ms: number): unknown; clear(t: unknown): void }
const realTimers: Timers = { set: (fn, ms) => setTimeout(fn, ms), clear: (t) => clearTimeout(t as ReturnType<typeof setTimeout>) }

/** One press, from pointer down to up: opens T2 after a still hold on the
 *  title or body; on the grip hands the press to the drag at once (its own
 *  hold, armTouchDrag, decides when it starts). A mouse's press is never a
 *  long-press. */
export function pressOf(zone: PressZone, pointer: string, at: { x: number; y: number },
  on: { menu(): void; drag(): void }, timers: Timers = realTimers) {
  let timer: unknown = null
  let done = false
  const stop = () => { if (timer !== null) timers.clear(timer); timer = null; done = true }
  if (zone === 'grip') { done = true; on.drag() }
  else if (zone !== 'control' && pointer !== 'mouse') timer = timers.set(() => { timer = null; if (!done) { done = true; on.menu() } }, LONG_PRESS_MS)
  else done = true
  return {
    move(x: number, y: number) { if (!done && Math.hypot(x - at.x, y - at.y) > LONG_PRESS_SLOP) stop() },
    up: stop,
    cancel: stop,
    get pending() { return !done },
  }
}
