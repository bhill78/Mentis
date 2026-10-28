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
import { locate, primaryOf } from './model'
import { CONVERSATION_SHOW, type Float } from './types'

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
 *  leaf of This post, or a float's panel; null: nowhere in this arrangement. */
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

/** The content Esc would swap back to (model.ts swapBack), or null. */
export function previousPrimary(a: Arr): string | null {
  const previous = a.focus?.previous ?? []
  for (let i = previous.length - 1; i >= 0; i--) {
    const id = previous[i]
    if (locate(a, id) && id !== primaryOf(a)) return id
  }
  return null
}
