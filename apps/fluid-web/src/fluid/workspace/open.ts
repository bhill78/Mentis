/* Opening an object's detail out of the card it was opened from.
 *
 * The Mixed rule (spec 6.1): conversation material opens beside, workspace
 * objects open OVER the arrangement. The owner may choose "beside This post"
 * instead (Arrange > Preferences); that choice is presentation only and is
 * held in this browser. */

import * as nav from '../nav'
import type { DetailMode } from '../nav'

/** The card the shown detail grew from, to shrink back into and flash. */
export const opener: { el: HTMLElement | null } = { el: null }

const PREF = 'mentis.fluid.objects-open'
const listeners = new Set<() => void>()
let mode: DetailMode = (() => {
  try { return localStorage.getItem(PREF) === 'aside' ? 'aside' : 'over' } catch { return 'over' }
})()
export const objectsOpen = () => mode
export function setObjectsOpen(m: DetailMode) {
  mode = m
  try { localStorage.setItem(PREF, m) } catch { /* private mode: this page only */ }
  listeners.forEach((fn) => fn())
}
export const onObjectsOpen = (fn: () => void) => { listeners.add(fn); return () => { listeners.delete(fn) } }

export function openObject(address: string, from: HTMLElement | null) {
  opener.el = from
  nav.openDetail({ kind: 'object', address, anchor: { kind: 'object', address }, mode })
}

/** FOCUS (B2): the object on its own, over everything, for a moment. It is
 *  not the preference: Over and Beside stay how objects open; Esc, the
 *  scrim or ✕ return into the card it came from. */
export function focusObject(address: string, from: HTMLElement | null) {
  opener.el = from
  nav.openDetail({ kind: 'object', address, anchor: { kind: 'object', address }, mode: 'focus' })
}
