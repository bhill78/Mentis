/* TARGETS AND CONTEXTS FOR TODAY'S HOSTS (part P3).
 *
 * A host that draws its own control today (a section's ⋯, a window's ⚙) asks
 * the registry about a target it builds here, with its own functions lent by
 * `hosted` (providers/ops.ts). The surface it names declares nothing yet:
 * what it offers is what its host offers. P1's stateOf/capabilitiesOf and
 * P4's chrome replace these with the surface's real state and capabilities.
 * Browser-free. */

import type { Outcome, PlacementKind, PresentationClass, SurfaceCapabilities, SurfaceKind, SurfaceState, ZoneId } from '../types'
import type { ActionCtx, ActionTarget, SurfaceRef } from './types'
import { ops } from './providers/ops'

const none = new Set<never>()

/** Capabilities that declare nothing: a host says what it offers. */
export const UNDECLARED: SurfaceCapabilities = {
  kind: 'section',
  placementsBy: { wide: none, medium: none, compact: none },
  levels: none, size: { min: {} }, resize: 'none', movement: 'fixed', yield: 'never', snap: false,
  focusable: false, fullscreen: false, closable: false, putAway: false, primaryable: false, canFollow: false, ownsLayout: false,
  primaryBudget: {},
}

/** A surface as its host knows it: its id, kind and where it is. */
export function hostSurface(id: ZoneId, kind: SurfaceKind, at: PlacementKind, cls: PresentationClass = 'wide'): SurfaceRef {
  const placement: SurfaceState['placement'] =
    at === 'float' ? { kind: 'float', floatId: id, rect: { x: 0, y: 0, w: 0, h: 0 } }
    : at === 'dock' ? { kind: 'dock', in: 'tree', page: null }
    : at === 'launcher' ? { kind: 'launcher' }
    : at === 'stack' ? { kind: 'stack', index: 0 }
    : at === 'sheet' ? { kind: 'sheet' }
    : at === 'nested' ? { kind: 'nested', parent: '' }
    : { kind: 'page-root', page: id }
  const state: SurfaceState = {
    id, kind, cls, placement, level: { auto: 'standard' }, emphasis: 'none',
    binding: { mode: 'held', resource: { address: 'zone:' + id, kind } }, open: true,
  }
  return { id, state, caps: { ...UNDECLARED, kind } }
}

/** The workspace of place `key`, for its bar's Arrange and the palette's fallback. */
export const workspaceTarget = (key: string): ActionTarget => ({ resource: { address: 'place:' + key, kind: 'workspace' } })
/** A post, for its toolbar and More menu. */
export const postTarget = (id: string): ActionTarget => ({ resource: { address: 'post:' + id, kind: 'post' } })

const notYet = (): Outcome => ({ ok: false, reason: 'This change arrives with the surface lifecycle (workspace.apply)' })

/** The context today's hosts run in: the viewport's class, fine input (P5
 *  adds coarse), and no workspace.apply until P1 provides it. */
export function hostCtx(cls: PresentationClass, apply: ActionCtx['apply'] = notYet): ActionCtx {
  return {
    cls, input: 'fine', apply,
    nav: { open: (a) => ops.object.open(a), openPlace: (key) => ops.openPlace(key), back: () => ops.back() },
  }
}
