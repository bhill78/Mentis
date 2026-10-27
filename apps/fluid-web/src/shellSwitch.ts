/* ------------------------------------------------------------------------ *
 * FLUID SHELL SWITCH
 *
 * Fluid is the interface for Mentis at `/fluid`.
 *
 * THE WORKSPACE LAB IS RETIRED FROM REACH (ent-5bfed2a54cda): `/lab` and
 * `?lab` were its address, and now open the real Fluid over the same
 * Conversation. Its code (ui/src/lab) stays; removing it is the owner's
 * later decision.
 * ------------------------------------------------------------------------ */

import { readAddress } from './address'

/** Fluid, at this Conversation when one is named. */
export function fluidHref(conversation: string | null | undefined): string {
  return '/fluid' + (conversation ? '?c=' + encodeURIComponent(conversation) : '')
}

/** Where an old Workspace Lab address goes now, or null if this is not one. */
export function labRedirect(loc: { pathname: string; search: string; hash: string } = window.location): string | null {
  const q = new URLSearchParams(loc.search)
  if (!/^\/lab\/?$/.test(loc.pathname) && !q.has('lab')) return null
  return fluidHref(readAddress(loc.hash).conversation ?? q.get('c'))
}
