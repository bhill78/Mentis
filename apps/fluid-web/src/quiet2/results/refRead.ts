/* READING THE ARTIFACT AGAIN ON THE PRESS, THROUGH THE ROUTE THAT ALREADY
 * EXISTS -- AND FAILING CLOSED (contract A4/P4; re-review adm-d84456fd4c3c,
 * B4.1).
 *
 * WHAT WAS WRONG, TWICE OVER.
 *
 * The FIRST version named `inspectRef(ref)` in `needs/inspect.ts`: no such
 * function, no such route, so the documented composition could not run at all
 * (re-review adm-263df1ccb512, F19).
 *
 * The SECOND version read the request a Needs you row was drawn from
 * (`GET /fluid/api/needs-you/about?ids=<ask>`) and took the reference out of
 * that answer. That read EXISTS, but it answered the wrong question in two
 * ways. A press with no request behind it -- the result chooser, a Brain
 * record's file, the Latest list -- had nothing to read by, so it was
 * `unchecked`: the old held descriptor was placed with no check at all, and a
 * purged Admission opened as though it were there. And where there WAS a
 * request, a refusal (401), a failure (offline) or a fresh answer that no
 * longer named the reference were all read as `unchecked` too -- absence
 * treated as authority to reuse what was in hand. Either way the reader was
 * told `opened` about something this server had not said was openable.
 *
 * WHAT IS HERE INSTEAD. The artifact's own description, on the artifact's own
 * route, for every explicit artifact open and whatever the press came from:
 *
 *     GET /api/artifacts/<exact ref>?describe=1      (no-store)
 *
 * It is the route this build already serves (`mentis/web/__init__.py`
 * `_artifact`, `?describe=1`), through the client this app already uses
 * (`fluid/http.ts` `fluidFetch`, so an owner-auth 401 is handled where it
 * always was), under the grant the page already has -- a worker grant is
 * refused there, as it is for the bytes. `quiet/media/view.ts` already
 * documents it as where the VERIFIED word lives, and Fluid's Composer already
 * consumes it (`fluid/Composer.tsx` `attachHeld`). Nothing new is added to the
 * server, no byte is fetched, and no second reader is invented.
 *
 * AND IT FAILS CLOSED. Every answer that is not "this exact reference is held
 * here now" is `gone`, with the server's own word for why: an HTTP refusal, a
 * body that is not a description, a description of another reference, A
 * DESCRIPTION THAT NAMES NO REFERENCE AT ALL (re-review adm-efb406a34e7a,
 * N5), any state but `held`, and a network failure. The opener opens nothing
 * on a `gone`, and never reports `opened` from the descriptor in hand.
 *
 * WHAT IT STILL DOES NOT DO, SAID PLAINLY. It answers about availability, not
 * about authority: no permission is granted or checked here beyond what the
 * route itself refuses, and the bytes are still read -- and still refusable --
 * when the viewer asks for them. A renderer that fails afterwards does not
 * make this answer wrong. Non-artifact targets (a post, a record, a
 * conversation) keep their own guarded readers and are not read here. */
import { fluidFetch } from '../../fluid/http'
import type { HeldBytes } from '../../quiet/media/view'
import { availabilityOf, goneWords, type Availability } from './targets'

/** The existing route, exactly as `Composer.tsx` and `quiet/media/view.ts`
 *  name it: the artifact's own address, described rather than sent. */
export const ARTIFACT_PATH = '/api/artifacts/'
export const DESCRIBE = 'describe=1'

/** The words for an answer that was not an answer about these bytes. It is
 *  deliberately not a "gone" word: nothing says the result is not there, only
 *  that this reader could not be told that it is. */
export const COULD_NOT_CHECK = 'Whether that is still here could not be checked just now, so nothing was opened.'
export const ANOTHER_THING = 'That read answered about something else, so nothing was opened.'

/** WHAT THE SERVER SAYS STANDS BEHIND THE REFERENCE NOW.
 *
 *    held   THIS exact reference is held here, with its verified description
 *    gone   anything else, with the reason in the server's own words: not
 *           held, purged, missing, corrupt, unknown, refused, unreachable */
export type FreshArtifact =
  | { how: 'held'; file: HeldBytes }
  | { how: 'gone'; availability: Availability; why: string }

const gone = (availability: Availability, why?: string): FreshArtifact =>
  ({ how: 'gone', availability, why: why ?? goneWords(availability) })

/** The description's own fields, read structurally: this module never depends
 *  on anything the route does not already answer with (`mentis/artifacts.py`
 *  `describe` through `public`, with `source` dropped by the route). */
interface Described {
  ref?: unknown
  state?: unknown
  name?: unknown
  size?: unknown
  claimed_media_type?: unknown
  treatment?: { view?: string | null } | null
  error?: unknown
}

const words = (body: Described | null): string | null => {
  const e = body?.error
  return typeof e === 'string' && e.trim() ? e.trim() : null
}

/** THE ARTIFACT AS THE SERVER STATES IT NOW, OR WHY NOT.
 *
 *  `fetch_` is the app's own client by default and is injected only by the
 *  checks, so what runs in the page is `fluidFetch` over the real route. */
export async function artifactNow(ref: string, fetch_ = fluidFetch): Promise<FreshArtifact> {
  if (!ref) return gone('unreadable', 'That file has no reference to read: nothing was opened.')
  let res: Response
  try {
    res = await fetch_(`${ARTIFACT_PATH}${encodeURIComponent(ref)}?${DESCRIBE}`, {
      headers: { 'X-Mentis-Client': '1' }, cache: 'no-store',
    })
  } catch {
    /* OFFLINE, OR THE SERVER GONE: not an authority to open what is in hand */
    return gone('unreadable', COULD_NOT_CHECK)
  }
  const body = await res.json().catch(() => null) as Described | null
  /* A REFUSAL IS A REFUSAL (401, 403, 404, 500): the server's own words where
     it gave any, and never the descriptor the row was drawn with. */
  if (!res.ok) return gone('unreadable', words(body) ?? COULD_NOT_CHECK)
  if (!body || typeof body !== 'object') return gone('unreadable', COULD_NOT_CHECK)
  if (words(body)) return gone('unreadable', words(body)!)
  /* THE SAME REFERENCE, SAID, OR NOTHING (re-review adm-efb406a34e7a, N5).
     The route answers with the ref it read on EVERY state it answers --
     unknown, not-an-artifact, not-held, purged, held, missing and corrupt all
     carry it (`mentis/artifacts.py` `describe`, and the route only drops
     `source`). So the identity is REQUIRED, not merely checked when it
     happens to be there: a body with no `ref`, or one whose `ref` is not a
     string, does not identify these bytes, and "it did not say" is not
     authority to open what is in hand. */
  if (body.ref !== ref) return gone('unreadable', ANOTHER_THING)
  /* `?describe=1` ANSWERS 200 FOR EVERY STATE, unknown and purged included, so
     the STATE is the check and the status code alone is not (B4.1). */
  const availability = availabilityOf(typeof body.state === 'string' ? body.state : null)
  if (availability !== 'ok') return gone(availability)
  return {
    how: 'held',
    file: {
      ref,
      state: 'held',
      name: typeof body.name === 'string' ? body.name : null,
      size: typeof body.size === 'number' ? body.size : null,
      claimed_media_type: typeof body.claimed_media_type === 'string' ? body.claimed_media_type : null,
      /* THE SERVER'S OWN VERIFIED WORD for what the bytes are, which is the
         one thing this route has and a conversation read does not. */
      treatment: body.treatment && typeof body.treatment === 'object' ? { view: body.treatment.view ?? null } : null,
    },
  }
}
