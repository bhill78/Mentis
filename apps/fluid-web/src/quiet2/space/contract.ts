/* THE AGREED GRAPH-SESSION CONTRACT, as Quiet Chat consumes it.
 *
 * These declarations are §1 of the B1 addendum (adm-9f12e8153ca3), copied
 * VERBATIM. The implementation is Part A's `surfaces/space/session.ts`
 * (`createSpaceSession`, `SpaceSessionReader`); this file is only the shape
 * Quiet Chat was built against, so this branch type-checks and its navigation
 * decisions are checkable before A's file exists.
 *
 * AT INTEGRATION this file becomes one line -- the types re-exported from
 * A's module:
 *
 *     export type { SpaceSessionId, SpaceBrainKey, SpaceMaterialKey, SpaceView,
 *       SpaceCamera, SpaceReadState, SpaceSnapshot, SpaceSession } from '../../surfaces/space/session'
 *
 * and `provideSpaceSessions` (provider.ts) is called once with A's module.
 * Nothing in Quiet Chat implements a session, a reader, a camera or a read:
 * this branch creates no alternative to either (addendum §5, "B may scaffold
 * against declarations while A builds; it must not create an alternative
 * session or reader"). `tests/quiet_space_nav_unit.ts` checks that the names
 * Quiet Chat calls are exactly these.
 *
 * The graph model itself is the existing one: `Eye`, `Palette`, `SpaceRead`
 * and `SpaceNode` are imported from where they already live. */
import type { Palette } from '../../surfaces/space/BrainSpace'
import type { Eye, SpaceNode, SpaceRead } from '../../surfaces/space/layout'

export type { Palette, Eye, SpaceNode, SpaceRead }

export type SpaceSessionId = string
export type SpaceBrainKey = string
export type SpaceMaterialKey = 'records' | 'material'
export interface SpaceView {
  selected: string | null
  material: boolean
  palette: Palette
  allStrands: boolean
  turns: boolean
  options: boolean
  asOf: number | null
  playing: boolean
}
export interface SpaceCamera {
  initialized: boolean
  framing: 'auto' | 'held'
  zoomed: boolean
  eye: Eye
  walk: readonly string[]
  selectionRevision: number
}
export interface SpaceReadState {
  key: SpaceMaterialKey
  data: SpaceRead | null
  loading: boolean
  error: string | null
}
export interface SpaceSnapshot {
  view: Readonly<SpaceView>
  read: Readonly<SpaceReadState>
  visible: boolean
  disposed: boolean
}
export interface SpaceSession {
  readonly id: SpaceSessionId
  readonly brainKey: SpaceBrainKey
  getSnapshot(): SpaceSnapshot
  subscribe(listener: () => void): () => void
  getCamera(): SpaceCamera
  saveCamera(camera: SpaceCamera): void
  setView(patch: Partial<Omit<SpaceView, 'selected'>>): void
  select(entry: string | null, intent: 'user' | 'reconcile'): void
  setVisible(visible: boolean): void
  attachRenderer(): () => void
  dispose(): void
}
export type CreateSpaceSession = (input: {
  id: SpaceSessionId; brainKey: SpaceBrainKey;
}) => SpaceSession

/** The props A's components take a session through (§1, "Public props"). */
export interface SpaceSessionBinding { session?: SpaceSession }
export interface SpaceSessionReaderProps { session: SpaceSession }

/** The method names Quiet Chat calls on a session. Named here so a check can
 *  assert the contract has not drifted without a running graph. */
export const SESSION_CALLS = [
  'getSnapshot', 'subscribe', 'getCamera', 'saveCamera', 'setView',
  'select', 'setVisible', 'attachRenderer', 'dispose',
] as const
