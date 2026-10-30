/* SURFACE TENSION: transition() (plan adm-15951b3daacc §3.3).
 *
 * The one pure change a surface goes through. P0 gives the signature only;
 * P1 implements it by wrapping focus/model.ts, and adds the Holder seam
 * workspace.apply(id, change) in place.ts. */

import type { Change, Outcome, SurfaceCtx, TransitionFn, ZoneId } from './types'

export function transition(ctx: SurfaceCtx, id: ZoneId, change: Change): Outcome {   // PURE; P1
  void ctx; void id; void change
  throw new Error('not implemented')
}
transition satisfies TransitionFn
