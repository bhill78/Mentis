/* ------------------------------------------------------------------------ *
 * WHICH INTERFACE AN ADDRESS OPENS.
 *
 * QUIET CHAT IS MENTIS'S INTERFACE (owner, 2026-11-20). Fluid is legacy: kept,
 * reachable at `/fluid`, and no longer what Mentis opens on.
 *
 * Every address is served the same page, and this decides what that page
 * mounts. It is one function of the address and nothing else, so it can be
 * read and tested whole:
 *
 *   /            Quiet Chat. The launcher opens this address.
 *   /quiet2      Quiet Chat, as before: every existing link keeps working.
 *   /quiet       Quiet Chat Mark 1 (archived), as before.
 *   /fluid       Fluid, the explicit legacy route.
 *   anything else  what it opened before this change (Fluid's shell, which
 *                also answers the retired `/lab`). An unknown address is NOT
 *                sent to Quiet Chat.
 *
 * ONE EXCEPTION AT `/`, so that no saved Fluid link loses where it pointed.
 * Before this change `/` was Fluid, and a link written there can name a place
 * only Fluid has an address for: a Topic (`t`), Governance (`gov`, `s`), Home,
 * the Stream, a workspace (`w`, `from`), the retired lab, or one of Fluid's
 * `#/...` places (Manage Sources, the 3D Brain, a scope). Such an address is
 * handed to `/fluid` with its query and hash untouched. `/?c=<conversation>`
 * is NOT one of them: both interfaces read `c`, and Quiet Chat opens that
 * Conversation.
 *
 * NO LOOPS: the only move is `/` to `/fluid`, and `/fluid` never moves.
 * ------------------------------------------------------------------------ */

export type Entry =
  | { mount: 'quiet2' | 'quiet' | 'fluid' }
  /** Go to this address instead (always `/fluid…`), replacing this entry. */
  | { to: string }

/** Query parameters only Fluid reads. `c` and `at` are not here: Quiet Chat reads them. */
const FLUID_ONLY = ['t', 'gov', 'home', 'stream', 'view', 's', 'w', 'from', 'lab']

/** True when an address written at `/` names a place only Fluid can open. */
export function namesAFluidPlace(search: string, hash: string): boolean {
  if (hash.startsWith('#/')) return true
  const q = new URLSearchParams(search)
  return FLUID_ONLY.some((k) => q.has(k))
}

export function entryFor(loc: { pathname: string; search: string; hash: string }): Entry {
  const p = loc.pathname
  if (/^\/quiet2\/?$/.test(p)) return { mount: 'quiet2' }
  if (/^\/quiet\/?$/.test(p)) return { mount: 'quiet' }
  if (p === '/') return namesAFluidPlace(loc.search, loc.hash) ? { to: '/fluid' + loc.search + loc.hash } : { mount: 'quiet2' }
  return { mount: 'fluid' }
}
