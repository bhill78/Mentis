/* QUIET'S DESTINATION, IN THE ADDRESS BAR. Round 5, package S.
 *
 * THE BROWSER HASH IS QUIET'S ONLY DESTINATION HISTORY (F8). Quiet's Page
 * changes push nothing onto Fluid's nav stack; one movement is one hash
 * entry, and Back and Forward restore the entry they name rather than
 * redirecting to the latest bookmark.
 *
 * THE SUFFIX GOES AFTER THE SCOPE, NEVER INSIDE IT. The shared reading of an
 * address (`src/address.ts`) is UNCHANGED and cannot emit this suffix:
 * `scopeEnd` already consumes every `/t/<topic>` and `/turn/<target>` pair
 * before governance is looked for, and an unrecognised pair after them is
 * skipped. So `/qpage/<page>` is appended and parsed HERE, after all of those
 * pairs:
 *
 *     #/c/<origin>/t/<topic>/turn/<target>/qpage/<page>
 *
 * with absent topic and turn pairs omitted, and `qpage` omitted altogether
 * for the Conversation Page -- an address that names no Page is the same
 * address it has always been, so every link already sent still works.
 *
 * THE CONVERSATION IN THE HASH IS THE ORIGIN, always: the Holder's owner. A
 * Deep dive's own conversation is named by its Page's destination, not by the
 * address, which is why `#/c/<origin>/.../qpage/<page>` is enough to restore
 * a child reading.
 */
import { NOWHERE, writeAddress } from '../../address'
import type { QuietLocation, QuietResume, WorkspaceEnvelope } from '../workspace/types'

/** The Fluid Page that is always first and is labelled Conversation in Quiet.
 *  Its id is `nav.ts`'s own and is never replaced by a Quiet implementation. */
export const CONVERSATION_PAGE = 'this-post'

const SUFFIX = 'qpage'

const dec = (s: string): string => {
  try {
    return decodeURIComponent(s)
  } catch {
    /* A hand-edited address can hold half an escape: it names something odd
       rather than nothing, so it is taken literally -- as `address.ts` does. */
    return s
  }
}

/** WHERE THE PAIRS END. The same rule as the shared `scopeEnd`, read here so
 *  that the suffix is only ever looked for in the one position it can be in:
 *  a Topic or a Turn whose id is spelled `qpage` is an id, not a suffix,
 *  because it stands in a pair's VALUE position and is stepped over. */
function pairsEnd(bits: string[]): number {
  let i = 2
  while (bits[i] === 't' || bits[i] === 'turn') i += 2
  return i
}

/** Read Quiet's destination out of a hash, or null when the hash names no
 *  conversation at all (Brain scope, a bare file, governance on nothing). */
export function readQuietLocation(hash = window.location.hash): QuietLocation | null {
  const bits = hash.replace(/^#\/?/, '').split('/').filter(Boolean)
  if (bits[0] !== 'c' || !bits[1]) return null
  const out: QuietLocation = {
    originConversation: dec(bits[1]),
    topic: null,
    turn: null,
    page: CONVERSATION_PAGE,
  }
  const end = pairsEnd(bits)
  for (let i = 2; i < end && i + 1 < bits.length; i += 2) {
    if (bits[i] === 't') out.topic = dec(bits[i + 1])
    if (bits[i] === 'turn') out.turn = dec(bits[i + 1])
  }
  if (bits[end] === SUFFIX && bits[end + 1]) out.page = dec(bits[end + 1])
  return out
}

/** Write Quiet's destination as a hash. The scope is the shared writer's own
 *  output, so one reading of the address exists and this only ever appends. */
export function writeQuietLocation(at: QuietLocation): string {
  const scope = writeAddress({
    ...NOWHERE,
    conversation: at.originConversation,
    topic: at.topic,
    turn: at.turn,
  })
  return at.page && at.page !== CONVERSATION_PAGE
    ? `${scope}/${SUFFIX}/${encodeURIComponent(at.page)}`
    : scope
}

/** Is this address a bare resume entry -- `#/c/<id>` and nothing more? Then
 *  the saved selection is what the reader left, and it is restored. Anything
 *  explicit in the address is deliberate and overrides it. */
export const isResumeEntry = (at: QuietLocation): boolean =>
  at.topic === null && at.turn === null && at.page === CONVERSATION_PAGE

/** WHICH PAGE A RESUMED ARRIVAL OPENS, and why it opened that one.
 *
 *  An explicit Page in the address wins -- including over a newer bookmark,
 *  so a link somebody sent and a Back into an older entry both land where
 *  they say. A Page this browser does not have (another browser's local
 *  arrangement, or one since closed) falls back to Conversation VISIBLY:
 *  `unknownPage` names it so the controller can say so rather than opening
 *  something the address did not ask for in silence. */
export function resumeLocation(
  at: QuietLocation,
  envelope: WorkspaceEnvelope | null,
  pages: readonly string[],
): QuietResume {
  const has = (id: string) => id === CONVERSATION_PAGE || pages.includes(id)
  if (!isResumeEntry(at)) {
    if (at.page === CONVERSATION_PAGE || has(at.page))
      return { location: at, from: 'address', unknownPage: null }
    return {
      location: { ...at, page: CONVERSATION_PAGE },
      from: 'address',
      unknownPage: at.page,
    }
  }
  const saved = envelope?.selectedPage
  if (saved && saved !== CONVERSATION_PAGE && has(saved))
    return { location: { ...at, page: saved }, from: 'bookmark', unknownPage: null }
  return { location: at, from: 'default', unknownPage: null }
}
