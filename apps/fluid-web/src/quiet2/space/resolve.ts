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
 *      durable -- and for the field the graph left empty. Its kind AND the
 *      height its Kind declares are taken from the record.
 *   3. THE TURN'S OWN PLACEMENT (`/api/turns/<id>`, which the governance
 *      surfaces already read), for a Turn the entry read did not place.
 *   4. NOTHING. A Turn the record places nowhere stays unplaced: the
 *      read-only entry inspector reads it, and no root or post is invented.
 *
 * TWO FIELDS THE ENTRY READ DOES NOT ANSWER THE WAY THIS ONCE ASSUMED
 * (independent review R3), and both sent valid records and Turns to the
 * read-only inspector:
 *
 *   THE HEIGHT. `/api/entries/<id>` states no `layer`: it reports the Kind's
 *   own declaration (`properties.knowing`), which is exactly what
 *   `/api/space` turns into `how` or `that` (`mentis.operational.space`
 *   `layer_of`). Reading it as absent meant every governing or known record
 *   omitted from the capped graph read -- which is what the cap is for --
 *   opened read-only instead of in Manage Brain's record presentation.
 *
 *   THE PLACEMENT. `provenance.produced_by` lists only the acts that claim to
 *   have PRODUCED an entry (`mentis.operational.products.provenance_of`), and
 *   an ordinary Turn somebody wrote has none. It is placed by its own
 *   `in-conversation` link, which `/api/turns/<id>` answers as
 *   `inspector.conversation` -- the record's own placement, the same link
 *   `/api/space` reads for a contribution -- so a perfectly placed Turn was
 *   being read as unplaced.
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
import { isTurnKind, type NodeFacts } from './routing'
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
  /** the Kind's own declaration, as the record was written against it */
  properties?: { knowing?: string | null }
  provenance?: { produced_by?: { conversation?: string | null; turn?: string | null }[] }
}

/** The shape `/api/turns/<id>` answers with, in the part used here. */
export interface TurnFacts {
  inspector?: { conversation?: string | null }
}

/** THE HEIGHT A RECORD IS DRAWN AT, from the Kind's own declaration, exactly
 *  as the graph derives it (`mentis.operational.space.layer_of`): `how` for
 *  what directs work, `that` for what is known. A Kind that declares no
 *  `knowing` has no height HERE -- the graph calls that `other`, and the
 *  routing fallback treats a missing height and `other` the same way, so
 *  nothing is dressed as governance on a silence. Pure. */
export function layerOf(d: EntryFacts | null): string | null {
  const knowing = d?.properties?.knowing
  return knowing === 'how' ? 'how' : knowing === 'that' ? 'that' : null
}

/** What an entry read states, routed as itself: its kind, the height its Kind
 *  declares, and -- where an act claims to have produced THAT turn -- the
 *  Conversation that act names. A Turn with no such act is not placed here;
 *  `placedBy` reads its own placement. Pure. */
export function factsFrom(entry: string, d: EntryFacts | null): NodeFacts {
  if (!d || d.missing) return { entry, resolved: true }
  const kind = d.kind ?? null
  const own = (d.provenance?.produced_by ?? []).find((p) => p.turn === entry)
  return { entry, kind, layer: layerOf(d), conversation: own?.conversation ?? null, resolved: true }
}

/** WHERE THE RECORD ITSELF PUTS A TURN: its `in-conversation` link, which the
 *  Turn read answers as `inspector.conversation`. The record's own placement,
 *  never a nearby one. Pure. */
export function placedBy(d: TurnFacts | null): string | null {
  return d?.inspector?.conversation ?? null
}

/** The entry read, as EntryInspect itself addresses it. */
export const entryFactsPath = (entry: string) => `/api/entries/${encodeURIComponent(entry)}`
/** The Turn read, as the governance surfaces already address it. */
export const turnFactsPath = (entry: string) => `/api/turns/${encodeURIComponent(entry)}`

/** THE READS THIS MAKES, through the client it is given -- `api.ts`'s own
 *  `read`, which carries the interface header the server requires of every
 *  JSON route. A refusal or a failure is not a verdict about the record: it
 *  leaves exactly the honest fallback, and the reader that opens shows its own
 *  error.
 *
 *  AT MOST TWO, AND THE SECOND ONLY FOR A TURN THE FIRST DID NOT PLACE. Where
 *  the kind is already known to be a Turn and only its Conversation is being
 *  asked for, the entry read is skipped and its placement read directly. */
export async function resolveEntryFacts(
  entry: string,
  client: <T>(path: string) => Promise<T>,
  known?: NodeFacts | null,
): Promise<NodeFacts> {
  const askingOnlyWhere = isTurnKind(known?.kind) && !known?.conversation
  const base: NodeFacts = askingOnlyWhere
    ? { entry, kind: known!.kind ?? null, layer: known!.layer ?? null, conversation: null, resolved: true }
    : await client<EntryFacts>(entryFactsPath(entry)).then(
      (d) => factsFrom(entry, d),
      () => factsFrom(entry, null),
    )
  if (!isTurnKind(base.kind) || base.conversation) return base
  const where = await client<TurnFacts>(turnFactsPath(entry)).then(placedBy, () => null)
  return where ? { ...base, conversation: where } : base
}
