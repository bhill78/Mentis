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
 * armTouchDrag), never T2. A mouse has right-click instead. */

import type { InputMode, Level, PlacementKind, PresentationClass } from './types'
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

/** T1 from what the registry puts first: without Close and Remove, within `budget`. */
export function t1Of(primary: readonly ActionDef[], budget: number): ActionDef[] {
  return primary.filter((d) => !NOT_T1.includes(d.id)).slice(0, Math.max(0, budget))
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

/* -- long-press ------------------------------------------------------------- */

export const LONG_PRESS_MS = 500
export const LONG_PRESS_SLOP = 8

/** Where a press landed: the grip drags, the title or body opens T2, a
 *  control is its own. */
export type PressZone = 'grip' | 'title' | 'body' | 'control'

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
