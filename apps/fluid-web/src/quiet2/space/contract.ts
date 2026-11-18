/* THE AGREED GRAPH-SESSION CONTRACT, as Quiet Chat consumes it.
 *
 * §1 of the B1 addendum (adm-9f12e8153ca3). Part A implements it in
 * `surfaces/space/session.ts` (`createSpaceSession`, `SpaceSessionReader`),
 * and now that A is merged there is ONE declaration of it: this file is the
 * name Quiet Chat imports it under, re-exported from A's module. While B was
 * built in parallel these were a verbatim copy of §1, so the host could be
 * written and checked before A's file existed; keeping the copy afterwards
 * would be two declarations free to drift apart.
 *
 * Nothing in Quiet Chat implements a session, a reader, a camera or a read
 * (addendum §5, "it must not create an alternative session or reader"), and
 * `tests/quiet_space_nav_unit.ts` checks that the names Quiet Chat calls are
 * exactly these. Only types cross this seam, so none of the pure decision
 * modules that import it gains a runtime dependency on the renderer.
 *
 * The graph model itself is the existing one: `Eye`, `Palette`, `SpaceRead`
 * and `SpaceNode` are imported from where they already live. */
import type { Eye, SpaceNode, SpaceRead } from '../../surfaces/space/layout'
import type {
  SpaceBrainKey, SpaceSession, SpaceSessionId,
} from '../../surfaces/space/session'

export type {
  Palette, SpaceSessionId, SpaceBrainKey, SpaceMaterialKey, SpaceView,
  SpaceCamera, SpaceReadState, SpaceSnapshot, SpaceSession,
} from '../../surfaces/space/session'
export type { Eye, SpaceNode, SpaceRead }

export type CreateSpaceSession = (input: {
  id: SpaceSessionId; brainKey: SpaceBrainKey;
}) => SpaceSession

/** The props A's reader takes a session through (§1, "Public props"). The
 *  surface's own optional `session` is declared on `SpaceSurfaceProps`, so
 *  Quiet Chat passes it like any other prop and needs no binding type. */
export type { SpaceSessionReaderProps } from '../../surfaces/space/SpaceSessionReader'

/** The method names Quiet Chat calls on a session. Named here so a check can
 *  assert the contract has not drifted without a running graph. */
export const SESSION_CALLS = [
  'getSnapshot', 'subscribe', 'getCamera', 'saveCamera', 'setView',
  'select', 'setVisible', 'attachRenderer', 'dispose',
] as const
