/* ONE SURFACE CHANGE FROM A CONTROL (Surface Tension P4r; plan §3.3, §3.9).
 *
 * What a host's control does when it moves a surface: workspace.apply (the
 * Holder's transition(), P1), said in a toast -- with Undo where the change is
 * an arrangement step, with Reopen where it is this device's Close -- and the
 * reason where transition() refuses it. A control never edits the
 * arrangement around transition(), so a section, a window and a card float,
 * dock and close the same way, and a refusal is said, never silent.
 *
 * Close here is the device-local `close` verb ({prop:'open', to:false}):
 * this browser device stops showing it in this class; nothing shared
 * changes. It is never Remove from workspace. */

import * as nav from '../nav'
import { workspace, type SurfaceEnv } from '../workspace/place'
import type { HostOp } from './actions/providers/ops'
import { transition } from './transition'
import type { Change } from './types'

/** The surface verbs' one door for a control: `id` changes by `change`. */
export function applyHere(id: string, change: Change, env?: SurfaceEnv): boolean {
  const o = workspace.apply(id, change, env)
  if (!o.ok) { nav.toast({ text: o.reason }); return false }
  if (o.layer === 'shared' || (o.layer === 'device' && o.device)) nav.toast({ text: o.label, action: { label: 'Undo', run: () => workspace.undo() } })
  return true
}

/** Why `change` would be refused now, or null: transition() asked, nothing
 *  changed (it is pure), so a control can say why before it is pressed. */
export function refusedHere(id: string, change: Change, env?: SurfaceEnv): string | null {
  try {
    const o = transition(workspace.surfaceCtx(env), id, change)
    return o.ok ? null : o.reason
  } catch (e) {
    return (e as Error).message
  }
}

/** Reopen what this device closed. */
export function reopenHere(id: string): void {
  const o = workspace.apply(id, { prop: 'open', to: true })
  if (!o.ok) nav.toast({ text: o.reason })
}

/** × on a window or a card: Close, on this device only, with Reopen at hand. */
export const closeHere = (id: string): HostOp => ({
  run: () => {
    const o = workspace.apply(id, { prop: 'open', to: false })
    if (!o.ok) { nav.toast({ text: o.reason }); return }
    nav.toast({ text: o.label, action: { label: 'Reopen', run: () => reopenHere(id) } })
  },
  says: 'Close here: this device stops showing it; the workspace keeps it (Reopen brings it back)',
})
