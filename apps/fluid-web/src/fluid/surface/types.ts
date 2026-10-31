/* SURFACE TENSION: THE SHARED CONTRACT (plan adm-15951b3daacc §3.1–§3.4,
 * §3.6, §3.7; part P0).
 *
 * The words, classes, capabilities, state and changes every surface part
 * builds against. Types only, word for word from the plan, plus each
 * literal union's list of values as its runtime companion. Behaviour
 * belongs to the named parts: a function the plan gives without a body is
 * written here as its signature type (`…Fn`), implemented by its owner. */

import type { ReactNode, PointerEvent } from 'react'
import type { Zone } from '../workspace/tree'          // Zone.id is the surface identity
import type { Arr } from '../workspace/place'
import type { Origin, Where } from '../focus/types'
import type { ActionId, ActionTarget } from './actions/types'
import type { MagnetConfig } from './magnet/types'

/** Every member of the union T, and nothing else, as a list. */
const all = <T,>() => <const A extends readonly T[]>(a: A & ([T] extends [A[number]] ? unknown : never)) => a

/* ---- §3.1 Words, classes and input ---- */

export type ZoneId = string
export type Rect = { x: number; y: number; w: number; h: number }

export type Level = 'icon' | 'compact' | 'standard' | 'expanded'      // 'workspace' only for a Page root (r4 §1.3)
export type PresentationClass = 'wide' | 'medium' | 'compact'        // > 1024 · 761–1024 · ≤ 760 px, from the viewport only
export type InputMode = 'fine' | 'coarse'                           // coarse = (pointer: coarse) or (hover: none)

export const LEVELS = all<Level>()(['icon', 'compact', 'standard', 'expanded'])
export const PRESENTATION_CLASSES = all<PresentationClass>()(['wide', 'medium', 'compact'])
export const INPUT_MODES = all<InputMode>()(['fine', 'coarse'])

// F/frame/narrow.ts: P0 implements the pure presentationClass; P5 implements hooks and inputMode
//   export function presentationClass(width: number): PresentationClass   (in narrow.ts)
export type UsePresentationClassFn = () => PresentationClass        // usePresentationClass, P5
export type InputModeFn = () => InputMode                           // inputMode, P5
export type UseInputModeFn = () => InputMode                        // useInputMode, P5
// isNarrow()/useNarrow() stay, defined as presentationClass !== 'wide', so every existing caller keeps its meaning

/* ---- §3.2 SurfaceCapabilities, SurfaceState, Binding ---- */

export type SurfaceKind =
  | 'section' | 'float' | 'conversation' | 'page-panel' | 'launcher-tile'
  | 'nested-card' | 'lens' | 'magnet' | 'brain'
export const SURFACE_KINDS = all<SurfaceKind>()([
  'section', 'float', 'conversation', 'page-panel', 'launcher-tile', 'nested-card', 'lens', 'magnet', 'brain',
])

export type PlacementKind = 'dock' | 'float' | 'launcher' | 'nested' | 'page-root' | 'stack' | 'sheet'
export const PLACEMENT_KINDS = all<PlacementKind>()(['dock', 'float', 'launcher', 'nested', 'page-root', 'stack', 'sheet'])
export type Placement =
  | { kind: 'dock'; in: 'tree' | 'column'; page: string | null }     // 'column' only for the conversation
  | { kind: 'float'; floatId: string; rect: Rect; origin?: Origin }
  | { kind: 'launcher' }
  | { kind: 'nested'; parent: ZoneId }
  | { kind: 'page-root'; page: string }
  | { kind: 'stack'; index: number }                                  // medium/compact only
  | { kind: 'sheet' }                                                 // medium/compact only

export interface ResourceCapabilities {          // r3 §3; extends SectionDef and object kinds
  levels: ReadonlySet<Level>
  minBy?: Partial<Record<Level, { w: number; h: number }>>
  searchable: boolean
  exportable: 'turn' | 'conversation' | 'item' | 'none'
  hasWorkspace: boolean
  holdsWorkingState: boolean
  selectable: boolean
  specificActions: readonly ActionId[]
}

export interface SurfaceCapabilities {           // r4 §1.1 as amended by r5 D2
  kind: SurfaceKind
  placementsBy: Record<PresentationClass, ReadonlySet<PlacementKind>>
  levels: ReadonlySet<Level>                     // already ∩ ResourceCapabilities.levels
  size: { min: Partial<Record<Level, { w: number; h: number }>>; maxUseful?: { w: number; h: number }; fit?: boolean }
  resize: 'free' | 'aspect' | 'none'
  movement: 'free' | { anchored: 'edge' | 'zone' } | 'fixed'      // read in wide only
  yield: 'never' | 'slide' | 'shrink' | 'fold'                     // read in wide only
  snap: boolean                                                     // read in wide only
  focusable: boolean
  fullscreen: boolean
  closable: boolean
  putAway: boolean
  primaryable: boolean
  canFollow: boolean
  ownsLayout: boolean
  maxInstances?: number
  primaryBudget: Partial<Record<PlacementKind | 'icon', number>>    // r3 §5.2 starting values, §3.6 below
  // depth and group are deliberately absent in this build (§7). They are added later as optional fields.
}
export type CapabilitiesOfFn = (zone: Zone, where: Placement) => SurfaceCapabilities   // capabilitiesOf: P1; pure; intersection rule

export type ResourceRef = { address: string; kind: string }   // 'conversation:<id>', 'post:<id>', 'live:…', …
export type SelectionSource = 'reading' | { zone: ZoneId }
export type Binding =
  | { mode: 'held'; resource: ResourceRef }
  | { mode: 'following'; source: SelectionSource; facet?: string; current?: ResourceRef }
// Read from today's slot.follow / slot.pin / slot.items; no new field in this build (r3 step 3 is not in scope beyond reading)

export interface DeviceLocalState {                       // browser-device local; never sent to the server
  closed: ReadonlySet<ZoneId>                             // one set per brain/place/presentation class
}
export interface SurfaceState {
  id: ZoneId
  kind: SurfaceKind
  cls: PresentationClass                         // which record this state was read from
  placement: Placement                           // wide: tree/focus/floats; other classes: DevicePlacement or derived
  level: { auto: Level; override?: Level }       // override wins until Reset size
  emphasis: 'none' | 'lens' | 'fullscreen'       // transient per tab, never saved
  binding: Binding
  open: boolean                                   // !deviceLocal.closed.has(id); shared by tabs on this browser device
}
export type StateOfFn = (arr: Arr, id: ZoneId, cls: PresentationClass, device?: DevicePlacement, deviceLocal?: DeviceLocalState) => SurfaceState | null  // stateOf: P1

/* ---- §3.3 transition() and the change union ---- */

export type PlacementTarget =
  | { kind: 'float'; rect?: Rect }                         // absent rect = coordinator picks (beside origin, snapped)
  | { kind: 'dock'; near?: ZoneId; where?: Where }         // absent = origin if it still exists, else the dock pads' default
  | { kind: 'column' }                                     // conversation only
  | { kind: 'launcher' }                                   // Put away
  | { kind: 'back' }                                       // Bring back to where it was put away from
  | { kind: 'stack'; index?: number } | { kind: 'sheet' }  // medium/compact

export type Change =
  | { prop: 'placement'; to: PlacementTarget }
  | { prop: 'rect'; rect: Rect }                           // move/resize inside float placement (moveFloat)
  | { prop: 'front' }                                      // toFront
  | { prop: 'level'; to: Level | 'reset' }
  | { prop: 'level'; step: 1 | -1 }                        // Expand / Collapse
  | { prop: 'emphasis'; to: 'none' | 'lens' | 'fullscreen' } // Focus / Full screen / exit either
  | { prop: 'binding'; to: 'follow' | 'hold'; source?: SelectionSource; facet?: string }
  | { prop: 'primary'; on: boolean }                       // Make primary / Back: the workspace's primary pointer
  | { prop: 'order'; to: number }                          // Move up/down in a stack (medium/compact)
  | { prop: 'open'; to: false | true }                     // Close / Reopen in this browser device's current class
  | { prop: 'exists'; to: false }                          // Remove from workspace; explicit shared change
export const CHANGE_PROPS = all<Change['prop']>()([
  'placement', 'rect', 'front', 'level', 'emphasis', 'binding', 'primary', 'order', 'open', 'exists',
])

export interface SurfaceCtx {
  arr: Arr
  page: string | null
  cls: PresentationClass
  device?: DevicePlacement                    // the current class's record (undefined in wide, or when derived)
  deviceLocal: DeviceLocalState                 // from localStorage for this brain/place/class
  session: { emphasis: Record<ZoneId, 'none'|'lens'|'fullscreen'> } // per tab
  viewport: { w: number; h: number }
  caps: (id: ZoneId) => SurfaceCapabilities
}
export type Outcome =
  | { ok: true; arr: Arr; device?: DevicePlacement; deviceLocal?: DeviceLocalState; session?: SurfaceCtx['session']; label: string; layer: 'shared' | 'device' | 'session' }
  | { ok: false; reason: string }

export type TransitionFn = (ctx: SurfaceCtx, id: ZoneId, change: Change) => Outcome   // transition: PURE; P1 (stub in ./transition)
// Holder seam (P1, place.ts):
//   workspace.apply(id, change): Outcome — runs transition and commits ONE undo step labelled outcome.label

/* ---- §3.4 available(), and view state ---- */

export type SurfaceVerb =
  | 'expand' | 'collapse' | 'resetSize' | 'dock' | 'float' | 'focus' | 'exitFocus'
  | 'fullscreen' | 'exitFullscreen'
  | 'putAway' | 'bringBack' | 'makePrimary' | 'back' | 'close' | 'reopen' | 'removeFromWorkspace' | 'follow' | 'hold'
  | 'keepAsWindow' | 'newFollower' | 'bringToFront' | 'tidy' | 'moveUp' | 'moveDown' | 'showAsSheet'
export const SURFACE_VERBS = all<SurfaceVerb>()([
  'expand', 'collapse', 'resetSize', 'dock', 'float', 'focus', 'exitFocus',
  'fullscreen', 'exitFullscreen',
  'putAway', 'bringBack', 'makePrimary', 'back', 'close', 'reopen', 'removeFromWorkspace', 'follow', 'hold',
  'keepAsWindow', 'newFollower', 'bringToFront', 'tidy', 'moveUp', 'moveDown', 'showAsSheet',
])
export type Availability =
  | { state: 'available' }
  | { state: 'disabled'; reason: CapabilityUnavailable }      // always machine-readable and explainable
  | { state: 'absent' }
export type CapabilityUnavailable = {
  code: 'source' | 'permission' | 'connector' | 'runtime' | 'scope' | 'limit' | 'state'
  message: string
  sourceId?: string
  connectorId?: string
  permission?: string
  retryable: boolean
}
export const UNAVAILABLE_CODES = all<CapabilityUnavailable['code']>()([
  'source', 'permission', 'connector', 'runtime', 'scope', 'limit', 'state',
])
export type AvailableFn = (verb: SurfaceVerb, s: SurfaceState, caps: SurfaceCapabilities, ctx: SurfaceCtx) => Availability  // available: P1
// absent  = the verb's target value is not in caps for ctx.cls
// disabled = the shared capability exists, but sources, permissions, connectors, runtime support, bounds or current
// state forbid it now. A reason object is mandatory. SurfaceChrome shows reason.message beside the disabled T2/palette
// item and in an explanatory popover from the direct control; configuration editors show it inline by the affected facet.
// View state: ./viewState

/* ---- §3.6 SurfaceChrome ---- */

// F/surface/SurfaceChrome.tsx (P4; surface composition, owner Turn #1512, plan ent-2d8422d49d7c)
//
// A body-bearing surface is a FRAME: an optional content header, a required
// body, an optional content footer. Mechanics (grip, T1, T2, ×, palette aim,
// long-press, right-click) are the framework's; content supplies what its
// regions show and which registry actions they carry, never another window
// system. The Page bar is the one surface without a body (SurfaceBar).

/** How much framework chrome a frame shows at rest (chrome.ts layoutOf):
 *  full     grip · rich title · chip · header content · header actions · T1 · T2 · ×
 *  minimal  grip where it moves · header content (or the title) · header actions · T2 · ×
 *  hidden   no framework bar: header content above the body; T2 revealed on frame
 *           focus/hover (fine) or from a compact trigger (coarse); Close is in T2. */
export type ChromeVisibility = 'full' | 'minimal' | 'hidden'
export const CHROME_VISIBILITIES = all<ChromeVisibility>()(['full', 'minimal', 'hidden'])

export type FrameworkGrip = { onPointerDown(e: PointerEvent): void }   // T0 drag; long-press on grip = drag (armTouchDrag)

/** What content puts in a header or footer. `content` is local behaviour (a
 *  field, tabs, a pager that is not an action): it gets no ActionId and may
 *  not implement Float, Dock, Focus, Close, drag, resize, T1 or T2. `actions`
 *  are registry ids: drawn here, run by registry.run, kept in T2 and the
 *  palette, and left out of T1 so none is drawn twice. */
export interface SurfaceRegion {
  content?: ReactNode
  actions?: readonly ActionId[]
}

/** Shared by every presenter of the framework's chrome. */
interface ChromeBase {
  target: ActionTarget
  level: Level
  title: ReactNode            // rich: what the bar draws (a Magnet's switcher, a caption with its count)
  label: string               // plain: the accessible, menu and toast name
  className?: string
}

export interface SurfaceChromeProps extends ChromeBase {
  placement: PlacementKind
  body: ReactNode             // required: a surface is its body; the launcher's icon button is its body
  /** The body is the surface's own button (the launcher icon, a Magnet disc):
   *  a hold or right-click on that button opens the frame's T2. Other
   *  interactive elements in the body keep their own presses. */
  bodyIsControl?: boolean
  header?: SurfaceRegion
  footer?: SurfaceRegion
  visibility?: ChromeVisibility                       // default 'full'
  grip?: FrameworkGrip
  /** A surface that folds away rather than closes (a Magnet's slide-out,
   *  back to its disc): its × runs this; Close stays in T2. */
  dismiss?: { label: string; title: string; run: () => void }
}

/** THE ONE BAR-ONLY SURFACE: the Page bar's tools. Restricted on purpose, so
 *  it cannot grow into a second general window contract. */
export interface SurfaceBarProps extends ChromeBase {
  variant: 'page-bar'
  extra?: ReactNode                                   // content tools that are NOT actions
  body?: never
  header?: never
  footer?: never
  visibility?: never
  grip?: never
}

// Long-press (500 ms, cancelled by 8 px movement) on title/body opens T2; right-click opens T2 (fine input).

/* ---- §3.7 DevicePlacement, arrangement v3 ---- */

export interface DevicePlacement {
  order: ZoneId[]                                              // stack order; ids not present are placed by derive()
  place: Record<ZoneId, 'stack' | 'sheet' | 'launcher' | 'dock'>   // 'dock' only in medium (shown in the tree area)
  level: Record<ZoneId, Level>                                  // overrides only
  updatedAt: number
  at?: Record<ZoneId, { x: number; y: number }>                 // a free disc's place on this class (px from the page's corner); absent until moved
}
export const DEVICE_PLACES = all<DevicePlacement['place'][ZoneId]>()(['stack', 'sheet', 'launcher', 'dock'])
export type MakeRoom = 'off' | 'drag' | 'expand'                // 'expand' = while dragging and also on Expand
export const MAKE_ROOM = all<MakeRoom>()(['off', 'drag', 'expand'])
export interface ArrV3Additions {
  version: 3
  presentations?: { medium?: DevicePlacement; compact?: DevicePlacement }
  spatial?: { makeRoom?: MakeRoom }                              // the workspace override; absent = use the global default
  magnets?: Record<string, MagnetConfig>                         // keyed by stable magnet id; shared schema in §3.10
}
// Zone (workspace/tree.ts) gains: level?: Level                 // wide level override. On a non-magnet float, icon stays `min: true`.
export type DeriveFn = (arr: Arr, cls: 'medium' | 'compact', record?: DevicePlacement) => DerivedView   // derive: P5; pure; never writes
export interface DerivedView { order: ZoneId[]; place: Record<ZoneId, 'stack' | 'sheet' | 'launcher' | 'dock'>; level: Record<ZoneId, Level>; column: ZoneId | null }
