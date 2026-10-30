/* CLOSED HERE: WHAT THIS DEVICE DOES NOT SHOW, AND THE WAY BACK (plan §3.9;
 * part P5, taking over P4's NarrowFloats line).
 *
 * × on a surface is Close on this browser device, in this presentation class
 * (workspace.apply {prop:'open', to:false}); nothing shared changes. What is
 * closed is listed after the page's surfaces, each with Reopen, in every
 * class: the projection (projection.ts) leaves it out of the tree and the
 * windows, so this line is how it comes back. */

import { useSyncExternalStore } from 'react'
import * as nav from '../nav'
import { workspace } from '../workspace/place'
import { usePresentationClass } from '../frame/narrow'
import { standIn } from '../focus/narrowView'
import { closedHere } from './projection'
import type { Arr } from '../workspace/place'
import type { HostOp } from './actions/providers/ops'
import type { ZoneId } from './types'

/** What is closed on this device in the class the window is in now. */
export function useClosedHere(): ReadonlySet<ZoneId> {
  const cls = usePresentationClass()
  return useSyncExternalStore(workspace.subscribe, () => workspace.closed[cls])
}

const said = (o: { ok: boolean; reason?: string }) => { if (!o.ok && o.reason) nav.toast({ text: o.reason }) }

/** × on a surface: Close on this device (workspace.apply, P1), never the surface itself. */
export const closeHere = (id: ZoneId): HostOp => ({
  run: () => said(workspace.apply(id, { prop: 'open', to: false })),
  says: 'Close here: this device stops showing it; the workspace keeps it (Reopen brings it back)',
})
export const reopenHere = (id: ZoneId) => said(workspace.apply(id, { prop: 'open', to: true }))

/** The line after a page's surfaces: each closed here, with Reopen. */
export function ClosedHere({ view }: { view: Arr }) {
  const closed = useClosedHere()
  const gone = closedHere(view, closed, standIn(view))
  if (!gone.length) return null
  return (
    <p className="fq-nclosed" aria-label="Closed on this device">
      <span className="fq-nclosed-word">Closed here</span>
      {gone.map((g) => (
        <button key={g.id} type="button" className="fq-nreopen" data-reopen={g.id} title={`Reopen ${g.name} on this device`}
          onClick={() => reopenHere(g.id)}>↺ {g.name}</button>
      ))}
    </p>
  )
}
