/* GOVERNANCE FOLLOWS THE RECORD ON FLUID'S OWN PULSE.
 *
 * Governance's reads are Classic's `useApi` readers, and in the build they
 * register with Governance's own copy of api.ts (vite.config.ts,
 * `fluidOwnCopies`). Fluid's change loop (`store.follow`) never tells that
 * copy anything, so "Waiting on you", the list, the challenges and the
 * Record panel stayed as first read until a reload.
 *
 * Fluid already asks `/api/pulse` on its one beat (identity/activity.ts,
 * `hearPulse`), so this asks nothing of its own: it hears that beat and
 * passes what moved to that copy's readers, exactly as Classic's `usePulse`
 * would (`announceAdvance` with where it moved, `announceRunAdvance` for the
 * live half), each reader rereading its own path, narrowed by `concerns`.
 *
 * Shell keeps this mounted while anything of Governance is -- the Governance
 * page, or an item's tab beside its conversation -- and `on` only while that
 * content is ON SCREEN. Off screen (a restored tab nobody has looked at, or
 * one behind This post) nothing is reread; what moved meanwhile is kept, and
 * said once when it is shown again, so the kept tab catches up. */

import { useEffect, useRef } from 'react'
import { announceAdvance, announceRunAdvance, type Where } from '../../api'
import { hearPulse } from '../identity/activity'

/** What moved while off screen. `where` null: somewhere unsaid, so everything. */
interface Owed { durable: boolean; where: Where | null; live: boolean }
const nothing = (): Owed => ({ durable: false, where: null, live: false })

function widen(was: Owed, where: Where | null): Where | null {
  if (!was.durable) return where
  if (!was.where || !where) return null
  return {
    conversations: [...new Set([...was.where.conversations, ...where.conversations])],
    executions: [...new Set([...was.where.executions, ...where.executions])],
    governed: was.where.governed || where.governed,
    people: was.where.people || where.people,
    loose: was.where.loose || where.loose,
  }
}

export default function GovFollow({ on }: { on: boolean }) {
  const shown = useRef(on)
  const owed = useRef<Owed>(nothing())
  useEffect(() => hearPulse((moved, where) => {
    if (shown.current) {
      if (moved === 'durable') announceAdvance(where)
      else announceRunAdvance()
      return
    }
    if (moved === 'durable') owed.current = { ...owed.current, where: widen(owed.current, where), durable: true }
    else owed.current = { ...owed.current, live: true }
  }), [])
  useEffect(() => {
    shown.current = on
    if (!on) return
    const o = owed.current
    owed.current = nothing()
    if (o.durable) announceAdvance(o.where)
    else if (o.live) announceRunAdvance()
  }, [on])
  return null
}
