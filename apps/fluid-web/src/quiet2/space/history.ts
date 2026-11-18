/* THE GRAPH IN THE BROWSER'S OWN HISTORY (addendum §3).
 *
 * A graph entry and an inspect entry are INTENT, not another store: they carry
 * which Brain, which session, and -- while inspecting -- what is being read.
 * No graph, no read, no camera and no address is in them. They sit beside
 * Quiet Chat's existing brain/source entries in the one payload union
 * (Quiet2.tsx), so `centreHistory`'s own push, pop, replace and search are
 * exactly what they were (centreHistory.ts is unchanged by this work).
 *
 * WHAT CANNOT BE RESURRECTED. Nothing here ever recreates a session. A
 * reload, a closed graph or an entry made against another Brain is EXPIRED,
 * and `resumeSpace` says what to put in its place: an ordinary centre with a
 * plain notice for a graph intent; for an inspect intent, its target alone in
 * the same Brain, read by the ordinary reader with the graph origin stripped;
 * and for another Brain, nothing replayed at all.
 *
 * Pure, so every row of §3's expiry case is checkable without a browser
 * (`tests/quiet_space_nav_unit.ts`). */
import type { SpaceBrainKey, SpaceSessionId } from './contract'

/** Where a node, or a link off its reader, is read. */
export type SpaceDestination =
  | { kind: 'record'; entry: string }
  | { kind: 'entry'; entry: string }
  | { kind: 'post'; conversation: string; post: string }
  | { kind: 'conversation'; conversation: string }

export type SpaceIntent =
  | { brainKey: SpaceBrainKey; sessionId: SpaceSessionId; phase: 'graph' }
  | { brainKey: SpaceBrainKey; sessionId: SpaceSessionId; phase: 'inspect'; target: SpaceDestination }

/** One entry of the centre's history, as the page's payload union holds it. */
export type SpaceHistory = { space: SpaceIntent }

/* THE SAME ENTRY IS THE SAME DATA. `centreHistory.plan` compares entries by
   their JSON, so every entry is built here, in one key order, and a graph
   entry for a session is byte-identical however it was reached -- which is
   what lets its existing search walk BACK to the graph instead of pushing a
   second one (§3, "In-page Back to 3D Brain"). */
export const graphIntent = (brainKey: SpaceBrainKey, sessionId: SpaceSessionId): SpaceHistory =>
  ({ space: { brainKey, sessionId, phase: 'graph' } })
export const inspectIntent = (brainKey: SpaceBrainKey, sessionId: SpaceSessionId, target: SpaceDestination): SpaceHistory =>
  ({ space: { brainKey, sessionId, phase: 'inspect', target } })

/** Whether an entry of the centre is a graph one at all. */
export const isSpaceHistory = (to: unknown): to is SpaceHistory =>
  !!to && typeof to === 'object' && 'space' in (to as object) && !!(to as SpaceHistory).space

/** What the reader is told where the view an entry names has been closed. */
export const CLOSED_NOTICE = '3D Brain view was closed. Open a new view.'

export type SpaceResume =
  /** the session is this page's and still live: apply the intent */
  | { how: 'live'; space: SpaceIntent }
  /** a graph intent whose session is gone: ordinary centre, and say so */
  | { how: 'expired-graph'; notice: string }
  /** an inspect intent whose session is gone, in THIS Brain: its target
   *  alone, by the ordinary reader, with the graph origin stripped */
  | { how: 'expired-inspect'; target: SpaceDestination }
  /** made against another Brain: not replayed, in either phase */
  | { how: 'other-brain' }

/** What to do with a graph entry the browser has landed on. `live` is asked
 *  of the registry; `brainKey` is the Brain being served NOW, or null while
 *  its identity is unknown (which is never treated as a match). */
export function resumeSpace(h: SpaceHistory, now: { brainKey: SpaceBrainKey | null; live: (id: SpaceSessionId) => boolean }): SpaceResume {
  const s = h.space
  if (!now.brainKey || s.brainKey !== now.brainKey) return { how: 'other-brain' }
  if (now.live(s.sessionId)) return { how: 'live', space: s }
  if (s.phase === 'inspect') return { how: 'expired-inspect', target: s.target }
  return { how: 'expired-graph', notice: CLOSED_NOTICE }
}

/** THE ENTRY A CLOSE LEAVES BEHIND (§3, the two Close rows). Closing the
 *  graph never leaves an intent that points at it: the current entry is
 *  REPLACED -- with the ordinary conversation where the graph itself was
 *  shown, and with the target alone where a reader was. Nothing is pushed, so
 *  Back still goes where it went before. */
export function afterClose(h: SpaceHistory): { replaceWith: SpaceDestination | null } {
  return { replaceWith: h.space.phase === 'inspect' ? h.space.target : null }
}
