/* ---------------------------------------------------------------------- *
 * THE APPLICABILITY ENGINE'S ANSWER, mirrored and not interpreted.
 *
 * `/api/context` is `compose()` asked a question rather than asked to
 * deliver: it says what WOULD reach an execution from where the material
 * sits now. Three surfaces read it -- the In use lens, Where meets Who and
 * the Preview sheet -- so the shapes and the handful of readings over them
 * live here once, in a file those three own.
 *
 * APPLIES IS NOT DELIVERED, AND DELIVERED IS NOT READ OR FOLLOWED. Nothing
 * in this file may be given delivery language. Whether anything ever
 * actually crossed is a different question, answered from delivery records
 * by `/api/governance/execution` and the history questions, and it is asked
 * separately and on purpose.
 * ---------------------------------------------------------------------- */

/** One thing composition would put in the payload, with its own origin. */
export interface ContextComponent {
  source_kind: string
  /** null where the component has no durable identity: there is nothing to
   *  open and nothing to quote, and that is said rather than implied. */
  source_id: string | null
  /** `invocation:persona` | `invocation:named` | `conversation:<id>` |
   *  `invocation` | `brain` -- HOW it would reach, in the composer's own
   *  vocabulary. The way something applies is read from here and never
   *  from a Kind name. */
  scope: string
  text: string
  /** the composer's own sentence for why this would be included. */
  why: string
  /** the subject two items may both speak to. Currently written by no
   *  authoring path, so it is legitimately empty -- see `ContextConflict`. */
  about: string
}

/** Two standing items on one subject. SURFACED, NEVER RESOLVED.
 *
 *  Grouped on `about`. No authoring path populates `about` yet, so this
 *  list is honestly empty in real data -- which is an empty answer about
 *  what could be grouped, and is NOT the claim that nothing overlaps. Every
 *  reader here has to render that distinction rather than say "none". */
export interface ContextConflict {
  about: string
  /** source ids, or the source kind where a component has no id. */
  components: string[]
}

/** Named, with the machine's reason, because Mark III dropped things
 *  without being able to say which. `why` is the engine's word --
 *  `not established`, `superseded`, or a sentence about what an orientation
 *  left out -- and is shown as the engine wrote it, never re-worded. */
export interface ContextWithheld {
  source_kind: string
  source_id: string | null
  why: string
}

export interface ContextAnswer {
  scope: 'conversation' | 'brain'
  components: ContextComponent[]
  conflicts: ContextConflict[]
  withheld: ContextWithheld[]
  payload_chars: number
}

/* -- the composer's scope vocabulary, not this interface's ---------------- */

export const PERSONA_SCOPE = 'invocation:persona'
export const NAMED_SCOPE = 'invocation:named'
export const SUPPLIED_SCOPE = 'invocation'
export const CONVERSATION_PREFIX = 'conversation:'

/** Which way a component would reach, from its scope alone.
 *
 *  NO KIND NAME IS BRANCHED ON. A Persona is not recognised by being called
 *  one; it is recognised by the composer having scoped it to the invocation
 *  that selected it. */
export type Path = 'placed' | 'persona' | 'named' | 'supplied' | 'other'

export function pathOf(scope: string): Path {
  if (scope === PERSONA_SCOPE) return 'persona'
  if (scope === NAMED_SCOPE) return 'named'
  if (scope.startsWith(CONVERSATION_PREFIX)) return 'placed'
  if (scope === SUPPLIED_SCOPE) return 'supplied'
  return 'other'
}

/** Components that are GOVERNED MATERIAL, as against the other things a
 *  payload carries.
 *
 *  Orientation and the request are in every payload and are governed by
 *  nobody: orientation is computed at the time and the request is what was
 *  being asked. The composer names them with their own source kinds and the
 *  execution sheet reads them the same way, so this mirrors the engine
 *  rather than inventing a second classification. Material supplied for one
 *  invocation has no durable identity at all and is excluded with them. */
const NOT_GOVERNED = new Set(['orientation', 'brain-orientation', 'request'])

export function isGovernedMaterial(c: ContextComponent): boolean {
  return c.source_id !== null && !NOT_GOVERNED.has(c.source_kind)
}

/* -- the Applies facet ---------------------------------------------------- */

/** One row of `/api/governance/applies`: which way this standing item could
 *  reach an execution at all. Read from placement links and the composition
 *  vocabulary, never from a Kind name. */
export interface AppliesRow {
  entry: string
  kind: string | null
  applies: 'placed' | 'by_persona' | 'when_named'
  why: string
  placed_at: string[]
  /** Placed on the whole Brain: it reaches every Conversation and Brain-scope work. */
  whole_brain?: boolean
  /** Which of `placed_at` is the Whole Brain destination (not a Conversation). */
  whole_brain_at?: string[]
  /** ABSENT STAYS ABSENT: null is the Kind declaring nothing about whether
   *  its entries can be true or false, and is not `false`. */
  truth_apt: boolean | null
}

export interface AppliesAnswer {
  rows: AppliesRow[]
  facets: { any_way: number; placed: number; by_persona: number; when_named: number }
  limit: string
}

/** `reachNow()` -- how a standing item reaches work, said in one phrase.
 *
 *  `names` maps a Conversation id to its name where the caller has one; a
 *  placement whose name is not to hand is still counted, never dropped. */
export function reachLabel(row: AppliesRow, names: Record<string, string>): string {
  if (row.applies === 'placed') {
    if (row.whole_brain) {
      const local = row.placed_at.length - 1
      return `Placed · Whole Brain${local > 0 ? ` and ${local} Conversation${local === 1 ? '' : 's'}` : ''}`
    }
    if (row.placed_at.length === 1) {
      const n = names[row.placed_at[0]]
      return `Placed · ${n ?? row.placed_at[0]}`
    }
    return `Placed · ${row.placed_at.length} Conversations`
  }
  if (row.applies === 'by_persona') return 'Only when an execution is started as it'
  if (row.truth_apt === true) return 'Can be right or wrong · reaches work only if named'
  return 'Only when an execution names it'
}

/* -- the register, read for the words that name a piece of material -------- */

export interface GovernedRow {
  entry: string
  kind: string
  standing_apt: boolean | null
  state: 'candidate' | 'stands' | 'ended' | 'replaced' | null
  group: 'proposed' | 'standing' | 'history' | 'unknown'
  summary: string
  secondary: string
  superseded_by?: string[]
  placed_at: { conversation: string; name: string | null }[]
}

export interface GovernedAnswer {
  groups: Record<'proposed' | 'standing' | 'history' | 'unknown', GovernedRow[]>
  totals: Record<string, number>
}

export function allRows(g: GovernedAnswer | null): GovernedRow[] {
  if (!g) return []
  return [...g.groups.standing, ...g.groups.proposed, ...g.groups.history, ...g.groups.unknown]
}

export function indexBy(rows: GovernedRow[]): Record<string, GovernedRow> {
  const out: Record<string, GovernedRow> = {}
  for (const r of rows) out[r.entry] = r
  return out
}

/** What to call a piece of material on screen. The register's summary where
 *  there is one, the id otherwise -- an id is a true name, and a
 *  placeholder would not be. */
export function nameOf(entry: string, index: Record<string, GovernedRow>): string {
  const row = index[entry]
  return row && row.summary ? row.summary : entry
}

/** Ended material stays selectable and is TAGGED, because a trace about
 *  something that has ended is a legitimate question. */
export function endedTag(row: GovernedRow): string {
  if (row.state === 'ended') return ' · ended'
  if (row.state === 'replaced') return ' · replaced before establishment'
  return ''
}
