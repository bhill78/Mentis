/* ONE ARRANGEMENT CHANGE FROM A CONTROL (Surface Tension P4r; plan §3.3).
 *
 * What a host's control does when it moves a surface: workspace.apply (the
 * Holder's transition(), P1), said in a toast -- with Undo where the change is
 * an arrangement step -- and the reason where transition() refuses it. A
 * control never edits the arrangement around transition(), so a section, a
 * window and a card float and dock the same way, and a refusal is said, never
 * silent. Close and Reopen on this device are ClosedHere.tsx's. */

import * as nav from '../nav'
import { workspace, type SurfaceEnv } from '../workspace/place'
import { transition } from './transition'
import type { Change } from './types'

/** A control's one door for a surface change: `id` changes by `change`. */
export function applyControlChange(id: string, change: Change, env?: SurfaceEnv): boolean {
  const o = workspace.apply(id, change, env)
  if (!o.ok) { nav.toast({ text: o.reason }); return false }
  if (o.layer === 'shared' || (o.layer === 'device' && o.device)) nav.toast({ text: o.label, action: { label: 'Undo', run: () => workspace.undo() } })
  return true
}

/** Why `change` would be refused now, or null: transition() asked, nothing
 *  changed (it is pure), so a control can say why before it is pressed. */
export function refusedControlChange(id: string, change: Change, env?: SurfaceEnv): string | null {
  try {
    const o = transition(workspace.surfaceCtx(env), id, change)
    return o.ok ? null : o.reason
  } catch (e) {
    return (e as Error).message
  }
}
