/* WHAT A LINKED ID IS, BEFORE IT IS ROUTED (addendum §4).
 *
 * A chosen node comes with its kind, its layer and the Conversation the
 * record puts it in. A LINK off the reader it opens comes with an id and
 * nothing else, and an arbitrary id must not inherit the kind of the node the
 * reader started from. So it is resolved first, through reads the page
 * already has, and never guessed:
 *
 *   1. THE GRAPH'S OWN READ. The session already holds the settled
 *      `/api/space` answer, which states each thing's kind, layer and
 *      Conversation. Nothing is fetched for anything in it.
 *   2. THE ENTRY ITSELF (`/api/entries/<id>`, which EntryInspect reads), for
 *      something the graph did not return -- omitted by the cap, or not
 *      durable. Its kind is taken from the record; a Turn's Conversation is
 *      taken only from the act that recorded THAT turn, so it is the
 *      record's own placement rather than a nearby one.
 *   3. NOTHING. A Turn the record places nowhere stays unplaced: the
 *      read-only entry inspector reads it, and no root or post is invented.
 *
 * The decision is pure (`factsFrom`); only the fetching is not. */
import type { NodeFacts } from './routing'
import type { SpaceRead } from './contract'

/** As much as the graph's own settled read states about an id. */
export function factsInRead(entry: string, read: SpaceRead | null): NodeFacts | null {
  const n = read?.nodes.find((x) => x.entry === entry)
  return n ? { entry, kind: n.kind, layer: n.layer, conversation: n.conversation } : null
}

/** The shape `/api/entries/<id>` answers with, in the part used here. */
export interface EntryFacts {
  kind?: string | null
  missing?: boolean
  provenance?: { produced_by?: { conversation?: string | null; turn?: string | null }[] }
}

/** What an entry read states, routed as itself. A Turn's Conversation is the
 *  one the act recording THAT turn names, and nothing else. Pure. */
export function factsFrom(entry: string, d: EntryFacts | null): NodeFacts {
  if (!d || d.missing) return { entry, resolved: true }
  const kind = d.kind ?? null
  const own = (d.provenance?.produced_by ?? []).find((p) => p.turn === entry)
  return { entry, kind, layer: null, conversation: own?.conversation ?? null, resolved: true }
}
