/* SURFACE TENSION: A SURFACE'S STATE, READ (plan §3.2; part P1).
 *
 * Nothing new is stored here: a surface's state is read from what the
 * arrangement already keeps -- the tree, the column, the floats and the
 * minimised conversation in wide; the class's DevicePlacement record in
 * medium and compact -- and from the browser device's closed set.
 *
 * Wide:
 *   - a leaf or the column is `dock`, a float is `float`, the conversation
 *     put away is `launcher`;
 *   - the level override is the zone's `level`, and a non-magnet float
 *     folded to its tab (`min`) is at `icon`.
 * Medium and compact: what derive() (focus/narrowView.ts, P5) makes of the
 * class's record -- its `place`, `level` and order, and where the record
 * says nothing, the place its wide placement suggests (DEFAULT_PLACE).
 *
 * Binding is read from the slot (`follow`, `pin`, `items`, `feed`); no new
 * field. Emphasis is per tab and not in the arrangement: `stateOf` gives
 * `none`, and transition.ts reads it from the context. */

import { CONVERSATION_ID, type Float } from '../focus/types'
import { locate } from '../focus/model'
import { defaultPlace, derive } from '../focus/narrowView'
import type { Arr } from '../workspace/place'
import { zones, type Zone } from '../workspace/tree'
import type { Binding, DeviceLocalState, DevicePlacement, Level, Placement, PresentationClass, SurfaceState, ZoneId } from './types'
import { MAGNET_SHOW, surfaceKindOf } from './capabilities'

/** A surface on the page `arr` shows (a page view): its zone, its wide
 *  placement and, floating, its float. */
export interface Found { zone: Zone; wide: Placement; float?: Float }

/** Where `id` is in wide, or null when the page has no such surface. */
export function findSurface(arr: Arr, id: ZoneId): Found | null {
  if (id === CONVERSATION_ID && arr.focus?.minimized)
    return { zone: { type: 'zone', id: CONVERSATION_ID, show: 'conversation', name: 'Conversation' }, wide: { kind: 'launcher' } }
  const at = locate(arr, id)
  if (!at) return null
  if (at.place === 'float') {
    const { x, y, w, h } = at.float
    return { zone: at.zone, float: at.float, wide: { kind: 'float', floatId: at.float.id, rect: { x, y, w, h }, ...(at.float.origin ? { origin: at.float.origin } : {}) } }
  }
  return { zone: at.zone, wide: { kind: 'dock', in: at.place === 'column' ? 'column' : 'tree', page: null } }
}

/** Every surface on the page, in reading order: the conversation (where it
 *  is, or put away), the tree's leaves, then the floats back to front. */
export function surfaceIds(arr: Arr): ZoneId[] {
  const ids = [
    ...(findSurface(arr, CONVERSATION_ID) ? [CONVERSATION_ID] : []),
    ...zones(arr.tree).map((z) => z.id),
    ...(arr.focus?.floats ?? []).map((f) => f.zone.id),
  ]
  return [...new Set(ids)]
}

/** The stack order in medium/compact: derive()'s -- the record's, for
 *  surfaces still on the page, the rest placed by today's narrow order --
 *  then any surface derive() does not list, in reading order. */
export function orderIn(arr: Arr, device?: DevicePlacement): ZoneId[] {
  return [...new Set([...derive(arr, 'compact', device).order, ...surfaceIds(arr)])]
}

type DevicePlace = DevicePlacement['place'][ZoneId]
/** Where a surface is in medium/compact when its record does not say, by
 *  its wide placement (narrowView.ts DEFAULT_PLACE). */
export function fallbackPlace(wide: Placement, cls: 'medium' | 'compact'): DevicePlace {
  if (wide.kind === 'launcher') return defaultPlace('launcher', cls)
  if (wide.kind === 'float') return defaultPlace('float', cls)
  return defaultPlace(wide.kind === 'dock' && wide.in === 'column' ? 'column' : 'leaf', cls)
}

/** The placement in `cls`. */
export function placementIn(arr: Arr, found: Found, cls: PresentationClass, device?: DevicePlacement): Placement {
  if (cls === 'wide') return found.wide
  const place = derive(arr, cls, device).place[found.zone.id] ?? device?.place[found.zone.id] ?? fallbackPlace(found.wide, cls)
  switch (place) {
    case 'stack': return { kind: 'stack', index: orderIn(arr, device).indexOf(found.zone.id) }
    case 'sheet': return { kind: 'sheet' }
    case 'launcher': return { kind: 'launcher' }
    default: return { kind: 'dock', in: found.wide.kind === 'dock' ? found.wide.in : 'tree', page: null }
  }
}

/** The automatic level where it is: an icon in the launcher, else standard
 *  (the box measured at draw time refines it, levels.ts levelOfWidth). */
export const autoLevel = (p: Placement): Level => (p.kind === 'launcher' ? 'icon' : 'standard')

/** The level override in `cls`, if any. */
export function overrideIn(found: Found, cls: PresentationClass, device?: DevicePlacement): Level | undefined {
  if (cls !== 'wide') return device?.level[found.zone.id]
  if (found.float?.min && found.zone.show !== MAGNET_SHOW) return 'icon'
  return found.zone.level
}

/** What a surface shows, read from its slot (r3 §1.1): following what is
 *  read, or held on a post (Hold), a feed, what was placed in it, or itself. */
export function bindingOf(zone: Zone): Binding {
  const s = zone.slot
  if (s) {
    if (s.follow && s.pin) return { mode: 'held', resource: { address: `post:${s.pin}`, kind: 'post' } }
    if (s.follow) return { mode: 'following', source: 'reading', facet: s.show }
    if (s.feed) return { mode: 'held', resource: { address: `feed:${s.feed.source}`, kind: 'feed' } }
    if (s.items.length === 1) return { mode: 'held', resource: { address: s.items[0], kind: 'object' } }
    return { mode: 'held', resource: { address: `zone:${zone.id}`, kind: 'section' } }
  }
  if (zone.show === 'conversation') return { mode: 'held', resource: { address: 'conversation', kind: 'conversation' } }
  const root = typeof zone.options?.root === 'string' ? zone.options.root : null
  if (zone.show === 'thread' && root) {
    const post = { address: `post:${root}`, kind: 'post' }
    return zone.options?.follow === true ? { mode: 'following', source: 'reading', facet: 'thread', current: post } : { mode: 'held', resource: post }
  }
  if (zone.show === MAGNET_SHOW && typeof zone.options?.magnet === 'string')
    return { mode: 'held', resource: { address: `magnet:${zone.options.magnet}`, kind: 'magnet' } }
  return { mode: 'held', resource: { address: `zone:${zone.id}`, kind: zone.show } }
}

/** A surface's state in `cls`, read from page view `arr` (pure). */
export function stateOf(arr: Arr, id: ZoneId, cls: PresentationClass, device?: DevicePlacement, deviceLocal?: DeviceLocalState): SurfaceState | null {
  const found = findSurface(arr, id)
  if (!found) return null
  const placement = placementIn(arr, found, cls, device)
  const override = overrideIn(found, cls, device)
  return {
    id,
    kind: surfaceKindOf(found.zone, placement),
    cls,
    placement,
    level: { auto: autoLevel(placement), ...(override ? { override } : {}) },
    emphasis: 'none',
    binding: bindingOf(found.zone),
    open: !deviceLocal?.closed.has(id),
  }
}
