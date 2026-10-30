/* SURFACE TENSION: WHAT EACH SURFACE MAY DO (plan §3.2; r4 §1.1; part P1).
 *
 * Each kind of surface DECLARES what its placement allows; each resource
 * declares what its content allows; a surface's capabilities are the
 * INTERSECTION of the two. Nothing is decided per component: availability
 * (available.ts) and transitions (transition.ts) read these declarations.
 *
 * The kind follows the content first (the conversation, a magnet, the Brain
 * are themselves wherever they are) and otherwise the placement: a section
 * docked is a `section`, the same zone floating is a `float`.
 *
 * Movement, yield and snap are spatial, and only wide arranges surfaces in
 * space; medium and compact stack them. They are declared once and read
 * through `spatialIn`, which neutralises them outside wide. */

import { CONVERSATION_SHOW } from '../focus/types'
import type { Zone } from '../workspace/tree'
import type {
  Level, Placement, PlacementKind, PresentationClass, ResourceCapabilities, SurfaceCapabilities, SurfaceKind,
} from './types'

export const MAGNET_SHOW = 'magnet'
export const BRAIN_SHOW = 'brain'

const set = <T,>(...xs: T[]): ReadonlySet<T> => new Set(xs)
const ALL_LEVELS = set<Level>('icon', 'compact', 'standard', 'expanded')

/** Where a kind may be, by class: wide floats; medium docks or stacks with a
 *  sheet over; compact stacks, with a sheet over. Never float outside wide. */
const BY_CLASS = (wide: PlacementKind[], medium: PlacementKind[], compact: PlacementKind[]) =>
  ({ wide: set(...wide), medium: set(...medium), compact: set(...compact) })
const MOVABLE = BY_CLASS(['dock', 'float'], ['dock', 'stack', 'sheet', 'launcher'], ['stack', 'sheet', 'launcher'])

/* r3 §5.2 starting values (plan §3.6). */
const BUDGET: SurfaceCapabilities['primaryBudget'] = { icon: 0, launcher: 0, nested: 2, dock: 4, float: 3, stack: 2, sheet: 2, 'page-root': 5 }

const base: Omit<SurfaceCapabilities, 'kind'> = {
  placementsBy: MOVABLE,
  levels: ALL_LEVELS,
  size: { min: { icon: { w: 44, h: 44 }, compact: { w: 220, h: 120 }, standard: { w: 240, h: 140 }, expanded: { w: 360, h: 240 } } },
  resize: 'none',
  movement: { anchored: 'zone' },
  yield: 'never',
  snap: false,
  focusable: true,
  fullscreen: true,
  closable: true,
  putAway: true,                 // where its class has a launcher (wide: the conversation's only)
  primaryable: true,
  canFollow: false,
  ownsLayout: false,
  primaryBudget: BUDGET,
}

/** Every kind's declaration, before its resource is taken into account. */
export const DECLARED: Readonly<Record<SurfaceKind, SurfaceCapabilities>> = {
  /* A docked section: ground. It never yields to floats (r4 §4). */
  section: { ...base, kind: 'section', canFollow: true },
  /* A floating window: moves, resizes, snaps and slides aside. Sections
     float with their binding; Follow on floats is deferred (§3.5), so a
     float does not follow. */
  float: { ...base, kind: 'float', resize: 'free', movement: 'free', yield: 'slide', snap: true },
  /* The conversation: one instance (its composer), never displaced, and put
     away to the launcher in every class (r4 §1.4). */
  conversation: {
    ...base, kind: 'conversation',
    placementsBy: BY_CLASS(['dock', 'float', 'launcher'], ['dock', 'stack', 'sheet', 'launcher'], ['stack', 'sheet', 'launcher']),
    resize: 'free', movement: 'free', yield: 'never', snap: true, maxInstances: 1,
  },
  /* A Page's root: the Page itself; it is where it is. */
  'page-panel': {
    ...base, kind: 'page-panel', placementsBy: BY_CLASS(['page-root'], ['page-root'], ['page-root']),
    levels: set<Level>('standard', 'expanded'), movement: 'fixed', closable: false, putAway: false, primaryable: false, ownsLayout: true,
  },
  /* A tile in the launcher: an icon whose verbs bring it back. */
  'launcher-tile': {
    ...base, kind: 'launcher-tile', levels: set<Level>('icon'), movement: 'fixed', fullscreen: false, focusable: false,
    primaryable: false,
  },
  /* A card in a collection: bounded by its parent, moves with it (r4 §1.3). */
  'nested-card': {
    ...base, kind: 'nested-card', placementsBy: BY_CLASS(['nested'], ['nested'], ['nested']),
    levels: set<Level>('icon', 'compact', 'standard'), closable: false, putAway: false, primaryable: false,
  },
  /* The lens is emphasis, not a place (r4 §0); declared so a host can ask. */
  lens: {
    ...base, kind: 'lens', placementsBy: BY_CLASS([], [], []), levels: set<Level>('expanded'), movement: 'fixed',
    closable: false, putAway: false, primaryable: false,
  },
  /* A magnet: docks or floats; its icon is a disc where it is, so wide has
     no launcher for it. It folds to that disc when displaced. */
  magnet: {
    ...base, kind: 'magnet',
    placementsBy: BY_CLASS(['dock', 'float'], ['dock', 'stack', 'sheet', 'launcher'], ['stack', 'sheet', 'launcher']),
    resize: 'free', movement: 'free', yield: 'fold', snap: true,
  },
  /* The Brain's window: floats in wide, a sheet elsewhere. */
  brain: {
    ...base, kind: 'brain', placementsBy: BY_CLASS(['float'], ['sheet', 'launcher'], ['sheet', 'launcher']),
    levels: set<Level>('standard', 'expanded'), resize: 'free', movement: 'free', yield: 'slide', snap: true,
    primaryable: false,
  },
}

/** The kind of surface a zone is, where it is. */
export function surfaceKindOf(zone: Zone, where: Placement): SurfaceKind {
  if (zone.show === CONVERSATION_SHOW) return 'conversation'
  if (zone.show === MAGNET_SHOW) return 'magnet'
  if (zone.show === BRAIN_SHOW) return 'brain'
  switch (where.kind) {
    case 'float': return 'float'
    case 'launcher': return 'launcher-tile'
    case 'nested': return 'nested-card'
    case 'page-root': return 'page-panel'
    default: return 'section'
  }
}

/** What a zone's content allows, whatever surface shows it (r3 §3). */
export function resourceCapabilitiesOf(zone: Zone): ResourceCapabilities {
  const conversation = zone.show === CONVERSATION_SHOW
  const thread = zone.show === 'thread'
  const one = zone.show === 'object' && zone.slot?.items.length === 1
  return {
    levels: ALL_LEVELS,
    searchable: !one,
    exportable: conversation ? 'conversation' : thread ? 'turn' : one ? 'item' : 'none',
    hasWorkspace: conversation || zone.show === MAGNET_SHOW,
    /* its composer: a draft lives with the conversation or the thread */
    holdsWorkingState: conversation || thread,
    selectable: !conversation,
    specificActions: [],
  }
}

/** The larger of two minimum sizes per level. */
function largest(a: SurfaceCapabilities['size']['min'], b: ResourceCapabilities['minBy']): SurfaceCapabilities['size']['min'] {
  if (!b) return a
  const out: SurfaceCapabilities['size']['min'] = { ...a }
  for (const [l, m] of Object.entries(b) as [Level, { w: number; h: number }][]) {
    const had = out[l]
    out[l] = had ? { w: Math.max(had.w, m.w), h: Math.max(had.h, m.h) } : m
  }
  return out
}

/** The intersection rule: the kind's declaration narrowed by its resource.
 *  Levels are those both allow; each level's minimum is the larger of the
 *  two; a surface follows only what has a slot to follow with. */
export function intersect(decl: SurfaceCapabilities, res: ResourceCapabilities): SurfaceCapabilities {
  return {
    ...decl,
    levels: new Set([...decl.levels].filter((l) => res.levels.has(l))),
    size: { ...decl.size, min: largest(decl.size.min, res.minBy) },
  }
}

/** A zone's capabilities where it is (pure). */
export function capabilitiesOf(zone: Zone, where: Placement): SurfaceCapabilities {
  const decl = DECLARED[surfaceKindOf(zone, where)]
  const caps = intersect(decl, resourceCapabilitiesOf(zone))
  return decl.canFollow && !zone.slot ? { ...caps, canFollow: false } : caps
}

/** Where it may be in a class. */
export const placementsIn = (caps: SurfaceCapabilities, cls: PresentationClass): ReadonlySet<PlacementKind> => caps.placementsBy[cls]

/** Movement, yield and snap as a class reads them: as declared in wide;
 *  outside wide nothing is arranged in space, so nothing moves freely,
 *  yields or snaps. */
export function spatialIn(caps: SurfaceCapabilities, cls: PresentationClass): Pick<SurfaceCapabilities, 'movement' | 'yield' | 'snap'> {
  return cls === 'wide' ? { movement: caps.movement, yield: caps.yield, snap: caps.snap } : { movement: 'fixed', yield: 'never', snap: false }
}
