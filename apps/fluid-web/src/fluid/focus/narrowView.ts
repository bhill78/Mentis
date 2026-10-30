/* WHAT A NARROW SCREEN SHOWS OF A FOCUS ARRANGEMENT (frame/narrow.ts: at
 * 1024 px and below, one column and one sheet).
 *
 * The arrangement is the desktop's, and a narrow screen never rewrites it:
 * this only reads it. There, as before Fluid Focus, the column always shows
 * the conversation. The place the arrangement gives the conversation (a leaf,
 * or a float) shows instead what the column holds (`standIn`), so nothing
 * becomes unreachable -- or, when the column holds the conversation too, a
 * stub saying where it is. Floats have no rectangles there: they are listed
 * in the workspace pane, front first (`narrowFloats`). Presentation only. */

import { zones, type Zone } from '../workspace/tree'
import type { Arr } from '../workspace/place'
import type { DevicePlacement, DerivedView, Level, ZoneId } from '../surface/types'
import { LEVELS } from '../surface/types'
import { locate, primaryOf } from './model'
import { CONVERSATION_ID, CONVERSATION_SHOW, type Float } from './types'

/** Where the arrangement puts the conversation, other than the column. */
export type ConvPlace = { place: 'leaf'; zone: string } | { place: 'float'; float: string }
export function convPlace(a: Arr): ConvPlace | null {
  const leaf = zones(a.tree).find((z) => z.show === CONVERSATION_SHOW)
  if (leaf) return { place: 'leaf', zone: leaf.id }
  const fl = a.focus?.floats?.find((f) => f.zone.show === CONVERSATION_SHOW)
  return fl ? { place: 'float', float: fl.id } : null
}

/** What the conversation's own place shows when narrow: the column's content
 *  (which the column, showing the conversation, no longer does); null: the
 *  stub. */
export function standIn(a: Arr): Zone | null {
  const c = a.focus?.column
  if (!c || c.show === CONVERSATION_SHOW) return null
  return convPlace(a) ? c : null
}

/** The floats as a narrow screen lists them: the front one first. */
export const narrowFloats = (a: Arr): Float[] => [...(a.focus?.floats ?? [])].reverse()

/** Where content `id` is seen when narrow: the column (the conversation), a
 *  leaf of the page `a` is a view of (page.ts), or a float's panel; null:
 *  nowhere on it. */
export type Seen = { in: 'column' } | { in: 'leaf'; zone: string } | { in: 'float'; float: string }
export function seenAt(a: Arr, id: string): Seen | null {
  const at = locate(a, id)
  if (!at) return null
  if (at.zone.show === CONVERSATION_SHOW) return { in: 'column' }
  if (at.place === 'column') {
    const p = convPlace(a)
    if (!p) return { in: 'column' }
    return p.place === 'leaf' ? { in: 'leaf', zone: p.zone } : { in: 'float', float: p.float }
  }
  return at.place === 'leaf' ? { in: 'leaf', zone: at.zone.id } : { in: 'float', float: at.float.id }
}

/* -- derive(): a medium or compact screen's view of a page (Surface Tension
 * §3.7; part P5). Pure: it reads the page and the class's record and never
 * writes either. ---------------------------------------------------------- */

type DevicePlace = DevicePlacement['place'][ZoneId]
/** Where a surface goes in medium/compact when the class's record does not
 *  say, by where it is in wide. What today's narrow screen does: the
 *  conversation is the column; sections are docked in medium (the tree,
 *  side by side where it fits) and stacked in compact; a window opens in the
 *  workspace sheet in medium and is a stack card in compact; what is put away
 *  stays put away. HELD OPEN for the owner (Turn #1442): change it here. */
export const DEFAULT_PLACE: Record<'medium' | 'compact', Record<'column' | 'leaf' | 'float' | 'launcher', DevicePlace>> = {
  medium: { column: 'dock', leaf: 'dock', float: 'sheet', launcher: 'launcher' },
  compact: { column: 'stack', leaf: 'stack', float: 'stack', launcher: 'launcher' },
}

/** Each surface of the page in today's narrow order, with where it is in
 *  wide: the conversation first (the column; put away, the launcher), then
 *  the tree's leaves in tree order, then the windows front first -- the
 *  conversation's own leaf or window giving its place to what the column
 *  holds (`standIn`), or, with nothing there, to nothing (the column shows it). */
function narrowOrder(a: Arr): { id: ZoneId; from: 'column' | 'leaf' | 'float' | 'launcher' }[] {
  const out: { id: ZoneId; from: 'column' | 'leaf' | 'float' | 'launcher' }[] = []
  const stand = standIn(a)
  if (a.focus?.minimized || locate(a, CONVERSATION_ID)) out.push({ id: CONVERSATION_ID, from: a.focus?.minimized ? 'launcher' : 'column' })
  for (const z of zones(a.tree)) {
    if (z.show === CONVERSATION_SHOW) { if (stand) out.push({ id: stand.id, from: 'leaf' }) }
    else out.push({ id: z.id, from: 'leaf' })
  }
  for (const f of narrowFloats(a)) {
    if (f.zone.show === CONVERSATION_SHOW) { if (stand) out.push({ id: stand.id, from: 'float' }) }
    else out.push({ id: f.zone.id, from: 'float' })
  }
  const seen = new Set<ZoneId>()
  return out.filter((x) => (seen.has(x.id) ? false : (seen.add(x.id), true)))
}

/** The page `a` (a page view) as `cls` shows it, with `record` (the class's
 *  DevicePlacement) over today's narrow order:
 *   - order: the record's order for surfaces still on the page; one the
 *     record does not name goes in after the surface it follows in today's
 *     order (first, if none does); one the page no longer has is skipped;
 *   - place: the record's, where it is one this class has, else DEFAULT_PLACE;
 *   - level: the record's overrides for surfaces on the page;
 *   - column: the conversation, which the column shows, when on the page. */
export function derive(a: Arr, cls: 'medium' | 'compact', record?: DevicePlacement): DerivedView {
  const base = narrowOrder(a)
  const known = new Set(base.map((x) => x.id))
  const order = [...new Set((record?.order ?? []).filter((id) => known.has(id)))]
  for (let i = 0; i < base.length; i++) {
    const id = base[i].id
    if (order.includes(id)) continue
    let at = 0
    for (let j = i - 1; j >= 0; j--) { const k = order.indexOf(base[j].id); if (k >= 0) { at = k + 1; break } }
    order.splice(at, 0, id)
  }
  const place: DerivedView['place'] = {}
  const level: DerivedView['level'] = {}
  for (const { id, from } of base) {
    const mine = record?.place[id]
    place[id] = mine && !(cls === 'compact' && mine === 'dock') ? mine : DEFAULT_PLACE[cls][from]
    const l = record?.level[id]
    if (l && (LEVELS as readonly Level[]).includes(l)) level[id] = l
  }
  return { order, place, level, column: known.has(CONVERSATION_ID) && !a.focus?.minimized ? CONVERSATION_ID : null }
}

/** Where a surface whose wide placement is `from` goes in `cls` by default. */
export const defaultPlace = (from: 'column' | 'leaf' | 'float' | 'launcher', cls: 'medium' | 'compact'): DevicePlace => DEFAULT_PLACE[cls][from]

/** The content Esc would swap back to (model.ts swapBack), or null. */
export function previousPrimary(a: Arr): string | null {
  const previous = a.focus?.previous ?? []
  for (let i = previous.length - 1; i >= 0; i--) {
    const id = previous[i]
    if (locate(a, id) && id !== primaryOf(a)) return id
  }
  return null
}
