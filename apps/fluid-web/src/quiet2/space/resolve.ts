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
 *      Conversation. Nothing is fetched for what it ANSWERS -- but its
 *      summary is not the record: a field the read itself leaves empty (a
 *      Turn it returned without a Conversation) is still unanswered, and is
 *      asked of the record rather than taken as the record's silence.
 *   2. THE ENTRY ITSELF (`/api/entries/<id>`, which EntryInspect reads), for
 *      something the graph did not return -- omitted by the cap, or not
 *      durable -- and for the field the graph left empty. Its kind is taken
 *      from the record; a Turn's Conversation is taken only from the act that
 *      recorded THAT turn, so it is the record's own placement rather than a
 *      nearby one.
 *   3. NOTHING. A Turn the record places nowhere stays unplaced: the
 *      read-only entry inspector reads it, and no root or post is invented.
 *
 * THE READ IS THE PAGE'S OWN CLIENT, not a bare `fetch`. Every JSON route of
 * the server refuses a request that does not say it is this interface
 * (`X-Mentis-Client`; mentis/web `_missing_client` answers 403), and that
 * refusal would be indistinguishable here from an id the Brain does not hold
 * -- so a link would silently open in the wrong reader. The client is passed
 * in (`resolveEntryFacts`), so the one Quiet Chat hands it is checkable and
 * nothing here reaches the network itself.
 *
 * Every decision is pure (`knownOf`, `answers`, `factsFrom`). */
import type { NodeFacts } from './routing'
import type { SpaceRead } from './contract'

/** As much as the graph's own settled read states about an id. */
export function factsInRead(entry: string, read: SpaceRead | null): NodeFacts | null {
  const n = read?.nodes.find((x) => x.entry === entry)
  return n ? { entry, kind: n.kind, layer: n.layer, conversation: n.conversation } : null
}

/** WHAT IS KNOWN NOW: what the chosen node or the link carried, with each
 *  field it lacks filled in from the graph's own settled read. Nothing already
 *  known is overwritten, and nothing is marked resolved: this is the graph's
 *  summary, not the record. Pure. */
export function knownOf(facts: NodeFacts, read: SpaceRead | null): NodeFacts {
  const n = factsInRead(facts.entry, read)
  if (!n) return facts
  return {
    ...facts,
    kind: facts.kind ?? n.kind ?? null,
    layer: facts.layer ?? n.layer ?? null,
    conversation: facts.conversation ?? n.conversation ?? null,
  }
}

/** Whether what is known now ANSWERS the question the dispatcher asked. It
 *  does not when the graph returned the thing but left that field empty --
 *  the Turn it knows of but did not place -- and then the record itself is
 *  read before the honest fallback is taken. Pure. */
export function answers(want: 'kind' | 'conversation', f: NodeFacts): boolean {
  return want === 'kind' ? !!f.kind : !!f.conversation
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

/** The entry read, as EntryInspect itself addresses it. */
export const entryFactsPath = (entry: string) => `/api/entries/${encodeURIComponent(entry)}`

/** THE ONE READ THIS MAKES, through the client it is given -- `api.ts`'s own
 *  `read`, which carries the interface header the server requires of every
 *  JSON route. A refusal or a failure is not a verdict about the record: it
 *  leaves exactly the honest fallback, and the reader that opens shows its own
 *  error. */
export function resolveEntryFacts(
  entry: string,
  client: (path: string) => Promise<EntryFacts>,
): Promise<NodeFacts> {
  return client(entryFactsPath(entry)).then(
    (d) => factsFrom(entry, d),
    () => factsFrom(entry, null),
  )
}
