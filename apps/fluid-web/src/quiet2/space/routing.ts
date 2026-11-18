/* WHERE A THING IN THE GRAPH IS READ (addendum §4).
 *
 * One dispatcher for the FIRST open of a chosen node and for every link off
 * the reader it opens, so a related record, a provenance Turn or a
 * replacement is routed by what IT is -- never by the kind of the node the
 * reader started from. Every destination is a reader Quiet Chat already has:
 *
 *   conversation   the conversation itself
 *   post           the Turn in the conversation the record declares, the
 *                  exact reply focused
 *   record         Manage Brain's own record presentation (BrainRecord),
 *                  with its existing management actions and read-only gating
 *   entry          the read-only entry inspector (surfaces/EntryInspect),
 *                  for topics, participants, substrate and acquired material
 *
 * NOTHING IS GUESSED. A kind that is not known yet, and a Turn whose
 * conversation the graph did not give, are RESOLVED through the read clients
 * the page already has; a Turn still placed nowhere is read by the entry
 * inspector rather than by a made-up root. Deletion and replacement do not
 * change the family: the family's own reader has the tombstone, version and
 * standing behaviour, and it keeps it.
 *
 * Pure, so every row of §4 is checkable (`tests/quiet_space_nav_unit.ts`). */
import type { SpaceDestination } from './history'

/** What the dispatcher knows about a thing. A bare id from a link knows only
 *  `entry`; a chosen node knows its kind, layer and conversation. */
export interface NodeFacts {
  entry: string
  kind?: string | null
  layer?: string | null
  conversation?: string | null
  /** its metadata has been asked for already: what is still missing is
   *  missing in the record, so the honest fallback is taken rather than
   *  another read */
  resolved?: boolean
}

export type SpaceRouting =
  | { how: 'go'; to: SpaceDestination }
  /** read this much first, through the existing clients, then route again */
  | { how: 'resolve'; entry: string; want: 'kind' | 'conversation' }

/** THE SUBSTRATE OF THE RECORD: things that are recorded but are not a
 *  governed or known record, and have no record presentation of their own.
 *  They are read, read-only, by the entry inspector -- and this takes
 *  precedence over the how/that fallback, so a substrate thing that happens
 *  to sit in an upper layer is still not dressed as governance (§4). */
export const SUBSTRATE = new Set([
  'anchor', 'reaction', 'observation', 'deletion', 'timer-mark', 'marked-ready',
  'own-words', 'interpretation', 'interpretation-reply', 'response-set', 'answer',
  'source-material', 'whole-brain',
])

/** The layers whose things Manage Brain presents as records. */
const RECORD_LAYERS = new Set(['how', 'that'])

/** Acquired material: Mentis's own address for a held admission. */
export const isAdmission = (entry: string) => /^adm-[0-9a-z]+$/i.test(entry)

/** A Turn is a `contribution` -- the record's own word, as Fluid already
 *  reads it (fluid/brain/address.ts). */
export const isTurnKind = (kind: string | null | undefined) => kind === 'contribution'

export function routeNode(f: NodeFacts): SpaceRouting {
  /* ACQUIRED MATERIAL is recognisable from the address itself, so it never
     waits on a read: the inspector shows it, and the existing held-artifact
     opener shows its bytes where the Brain holds them. */
  if (isAdmission(f.entry)) return { how: 'go', to: { kind: 'entry', entry: f.entry } }
  const kind = f.kind ?? null
  /* A LINK CARRIES AN ID, NOT A KIND. Until this id's own kind is read, there
     is nothing to route by, and inheriting the chosen node's kind would send
     an arbitrary entry to the wrong reader. */
  if (!kind && !f.resolved) return { how: 'resolve', entry: f.entry, want: 'kind' }
  if (kind && SUBSTRATE.has(kind)) return { how: 'go', to: { kind: 'entry', entry: f.entry } }
  if (kind === 'conversation') return { how: 'go', to: { kind: 'conversation', conversation: f.entry } }
  if (isTurnKind(kind)) {
    const c = f.conversation ?? null
    if (c) return { how: 'go', to: { kind: 'post', conversation: c, post: f.entry } }
    /* the graph's summary did not place it: its own metadata is asked for
       once, and a Turn the record still places nowhere is read as an entry */
    if (!f.resolved) return { how: 'resolve', entry: f.entry, want: 'conversation' }
    return { how: 'go', to: { kind: 'entry', entry: f.entry } }
  }
  if (kind === 'topic' || kind === 'participant') return { how: 'go', to: { kind: 'entry', entry: f.entry } }
  if (f.layer && RECORD_LAYERS.has(f.layer)) return { how: 'go', to: { kind: 'record', entry: f.entry } }
  return { how: 'go', to: { kind: 'entry', entry: f.entry } }
}

/** What a reader is called in the header beside the graph's return. */
export function destinationWords(to: SpaceDestination): string {
  switch (to.kind) {
    case 'record': return 'Brain record'
    case 'entry': return 'Entry'
    case 'post': return 'Turn'
    case 'conversation': return 'Conversation'
  }
}
