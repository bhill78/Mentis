/* READING A REFERENCE AGAIN ON THE PRESS, THROUGH THE READER THAT ALREADY
 * EXISTS (contract A4/P4; re-review adm-263df1ccb512, F19).
 *
 * WHAT WAS WRONG. The hand-off told the integrator to wire `OpenerHost.read`
 * to `inspectRef(ref)` in `needs/inspect.ts`, "the page's existing single-
 * reference inspection read". There is no such function anywhere in this
 * source, and no route behind it: `fluid/inspect.py` resolves references only
 * as part of what a REQUEST is about, and `GET /fluid/api/needs-you/about?ids=`
 * takes request ids (`opr-`) and answers `{"id","error"}` for anything else.
 * So the documented composition could not run at all.
 *
 * WHAT IS HERE INSTEAD. The read that actually exists, used as it is: the row
 * the reader pressed was drawn from one request's `about` answer, so this reads
 * THAT REQUEST again and takes the reference out of the fresh answer. Same
 * route, same client (`fluidFetch`), same grant, one request's worth of data.
 * Nothing new is added to the server, no byte is fetched, and no second reader
 * is invented.
 *
 * WHAT IT CANNOT DO, SAID PLAINLY. A press with no request behind it -- the
 * result chooser, a Brain record's file, the Latest list -- has nothing to read
 * by, and this answers `null` for it rather than guessing. The opener reads
 * that as `unchecked`, which is the behaviour before this contract existed, and
 * A4/P4 stays open for those paths. */
import { fluidFetch } from '../../fluid/http'
import type { ResolvedRef } from './targets'

/** The existing route, exactly as `needs/about.ts` reads it for the list. */
export const ABOUT_PATH = '/fluid/api/needs-you/about'

/** The arrays `fluid/inspect.py` `_about` answers with, each a `Ref`. */
const WHERE_REFS_ARE = ['subject', 'evidence', 'context', 'referenced'] as const

/** One request's answer, read structurally: this module never depends on the
 *  decision adapter's own schema (which is its owner's, not this round's). */
interface AboutAnswer {
  about?: { id?: string; error?: string; [k: string]: unknown }[]
}

/** THE REFERENCE AS THE SERVER STATES IT NOW, or null where this press has no
 *  request to read by, the read failed, or the fresh answer no longer names it.
 *
 *  `ask` is the request the row was drawn by (`needs/about.ts` `askOf`, which
 *  is what a launch's `decision.question` holds). */
export async function refNow(ask: string | null | undefined, ref: string, fetch_ = fluidFetch): Promise<ResolvedRef | null> {
  if (!ask || !ref) return null
  const res = await fetch_(`${ABOUT_PATH}?ids=${encodeURIComponent(ask)}`, { headers: { 'X-Mentis-Client': '1' }, cache: 'no-store' })
  if (!res.ok) return null
  const body = await res.json().catch(() => null) as AboutAnswer | null
  const one = body?.about?.find((a) => a && a.id === ask) ?? body?.about?.[0]
  if (!one || one.error) return null
  return refIn(one, ref)
}

/** The reference by its exact id, wherever in the answer it is stated. */
export function refIn(about: Record<string, unknown>, ref: string): ResolvedRef | null {
  for (const key of WHERE_REFS_ARE) {
    const rows = about[key]
    if (!Array.isArray(rows)) continue
    for (const r of rows) {
      if (r && typeof r === 'object' && (r as ResolvedRef).id === ref) return r as ResolvedRef
    }
  }
  return null
}
