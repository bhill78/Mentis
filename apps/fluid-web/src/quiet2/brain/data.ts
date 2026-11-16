/* THE BRAIN'S RECORDS, READ FOR QUIET CHAT MARK 2 (manage-brain round 2).
 *
 * SHARED INTERFACE between three concurrent worktrees (DESIGN-r2.md): the
 * Brain browser card (Workstream A), this record-reading view (Workstream B,
 * here), and the data layer proper (Workstream C). The exported names and
 * shapes below are the contract; whichever worktree's version is more
 * complete at integration is kept, but nobody may rename what the others
 * import.
 *
 * `fetchBrainRecord` is a REAL call to the Ladder's existing item-detail
 * route (`GET /api/ladder/items/<id>`, shape in investigation.md §6.2) --
 * not a placeholder -- so a record opened through it is never mock data.
 * `fetchBrainList` is left `[]` here: the Brain browser's own listing and
 * filtering is Workstream A's concern, not this view's.
 */
import { read } from '../../api'
import { formatStatusLabel } from '../../fluid/governance/ladderTypes'

export type BrainFilter = 'knowledge' | 'governing' | 'needs-you' | 'all'

export interface BrainRecordSummary {
  id: string
  kind: string
  text: string
  standingPlain: string
  standingLabel: string
  governs: boolean
  challenged: boolean
  conversation?: string | null
  turn?: string | null
  number?: number | null
}

export interface BrainRecordDetail extends BrainRecordSummary {
  basis: Array<{ ref: string; relation: string; kind: string; label: string; cite?: string | null }>
  outcomes: Array<{ id: string; result: string; attempted: boolean; text: string; in_context: string; recorded_at: number }>
  challenges: Array<{ link: string; objection: string; by: string; by_alias: string; because: string; at: number; resolution: 'open' | 'withdrawn' | 'set_aside' }>
  lineage: { up: Array<any>; down: Array<any> }
  history: Array<{ at: number; act: string; by: string; by_alias: string; because: string | null }>
  originating: { conversation?: string | null; conversation_name?: string | null; turn?: string | null; number?: number | null }
  adoption: { requests: Array<any>; declines: Array<any>; adopted: { by: string; at: number; because: string | null } | null }
  usage: { delivered: number; executions: number; cited: number; outcomes_after_delivery: { worked: number; failed: number; other: number } | null } | null
}

/** What `/api/ladder/items/<id>` actually sends (investigation.md §6.2),
 *  looser than `ladderTypes.ts`'s `LadderItemDetail`: the server's `usage`
 *  carries `executions` that type does not declare, and an outcome's
 *  `result` is free text until every outcome is a B7 verdict. Read here
 *  defensively; never trust a field this shape does not promise. */
interface RawDetail {
  id: string
  kind: string
  text: string
  fields?: Record<string, unknown>
  status: string
  governs: boolean
  challenged: number
  recorded_by?: { conversation?: string | null; turn?: string | null; number?: number | null } | null
  recorded_at?: number | null
  basis?: Array<{ ref: string; relation: string; kind: string | null; label: string; cite?: string | null }>
  outcomes?: Array<{ id: string; result: string | null; attempted: boolean | null; text: string | null; in_context: string | null; recorded_at: number | null }>
  challenges?: Array<{ link: string; objection: string | null; by: string | null; by_alias?: string | null; because: string; at: number | null; resolution?: string }>
  lineage?: { up: Array<unknown>; down: Array<unknown> }
  history?: Array<{ at: number | null; act: string; by: string | null; by_alias?: string | null; because: string | null }>
  originating?: { conversation?: string | null; conversation_name?: string | null; turn?: string | null; number?: number | null } | null
  adoption?: {
    requests?: Array<unknown>
    declines?: Array<unknown>
    adopted?: { by: string | null; at: number | null; because: string | null } | null
  } | null
  usage?: { delivered: number; executions?: number; cited: number; outcomes_after_delivery: { worked: number; failed: number; other: number } | null } | null
}

/** A record's own words, falling back to the first field that says
 *  something besides its name -- the same fallback `epistemic/Records.tsx`
 *  (`wordsOf`) uses, kept here too since this module has no React tree to
 *  share it through. */
function wordsOf(raw: RawDetail): string {
  if (raw.text && raw.text.trim()) return raw.text.trim()
  const extra = Object.entries(raw.fields ?? {}).find(([k, v]) => k !== 'name' && typeof v === 'string' && v.trim())
  return (extra?.[1] as string | undefined)?.trim() ?? ''
}

/** THE LADDER→PLAIN-WORDS TABLE (DESIGN-r2.md, "The record, at rest"), minus
 *  the asker's name for `adoption_requested`: a 2-argument pure mapping is
 *  what every reader of this record needs in common (a compact Brain browser
 *  row as much as the full reading view), and only the full view knows who
 *  asked. Said in full there (`recordWords.ts`'s `proposedSentence`). */
export function plainStandingLabel(status: string, governs: boolean): string {
  switch (status) {
    case 'adopted':
      return governs
        ? 'In effect — agents are given it as a rule.'
        : "In effect as knowledge — agents are told it when relevant; it doesn't bind them."
    case 'adoption_requested':
      return 'Not in effect — waiting for your decision.'
    case 'recorded':
      return 'Recorded, not adopted — reaches agents only as labelled past experience.'
    case 'declined':
      return 'Not in effect — declined.'
    case 'superseded':
      return 'Not in effect — replaced.'
    case 'ended':
    case 'retired':
      return 'Not in effect — ended.'
    default:
      return formatStatusLabel(status).label
  }
}

/** The Ladder's status pill, said beside the plain-language line (DESIGN-r2
 *  "Standing"): "Adopted · knowledge", "Adoption requested · rule". Every
 *  other status says only its own word -- the knowledge/rule distinction
 *  only matters once something is, or might become, in effect. */
export function standingPillLabel(status: string, governs: boolean): string {
  const base = formatStatusLabel(status).label
  if (status === 'adopted' || status === 'adoption_requested') return `${base} · ${governs ? 'rule' : 'knowledge'}`
  return base
}

/** "Effectiveness, in plain words" (DESIGN-r2.md): `worked`→Helped,
 *  `failed`→Didn't help, `inconclusive`→Unclear. Anything else (today's free
 *  text, until every outcome is a B7 verdict) passes through unchanged --
 *  never fabricated, never scored. */
export function verdictLabel(result: string): 'Helped' | "Didn't help" | 'Unclear' | string {
  switch (result) {
    case 'worked': return 'Helped'
    case 'failed': return "Didn't help"
    case 'inconclusive': return 'Unclear'
    default: return result
  }
}

/** `GET /api/ladder/items/<id>`, adapted to the shared `BrainRecordDetail`
 *  shape. The same route Governance's `GovItem` reads (`ladderRead` there);
 *  this is the hookless, one-shot form of the same read, for callers (the
 *  Brain browser's own previews, a copy-link check, …) that are not already
 *  inside this view's `useApi`. */
export async function fetchBrainRecord(id: string): Promise<BrainRecordDetail> {
  const raw = await read<RawDetail>('/api/ladder/items/' + encodeURIComponent(id))
  const governs = !!raw.governs
  const status = raw.status ?? 'recorded'
  const conversation = raw.recorded_by?.conversation ?? raw.originating?.conversation ?? null
  const turn = raw.recorded_by?.turn ?? raw.originating?.turn ?? null
  const number = raw.recorded_by?.number ?? raw.originating?.number ?? null
  const adopted = raw.adoption?.adopted
    ? { by: raw.adoption.adopted.by ?? '', at: raw.adoption.adopted.at ?? 0, because: raw.adoption.adopted.because ?? null }
    : null
  return {
    id: raw.id,
    kind: raw.kind,
    text: wordsOf(raw),
    standingPlain: plainStandingLabel(status, governs),
    standingLabel: standingPillLabel(status, governs),
    governs,
    challenged: (raw.challenged ?? 0) > 0,
    conversation,
    turn,
    number,
    basis: (raw.basis ?? []).map((b) => ({ ref: b.ref, relation: b.relation, kind: b.kind ?? '', label: b.label, cite: b.cite ?? null })),
    outcomes: (raw.outcomes ?? []).map((o) => ({
      id: o.id, result: o.result ?? '', attempted: o.attempted === true, text: o.text ?? '',
      in_context: o.in_context ?? '', recorded_at: o.recorded_at ?? 0,
    })),
    challenges: (raw.challenges ?? []).map((c) => ({
      link: c.link, objection: c.objection ?? '', by: c.by ?? '', by_alias: c.by_alias ?? '',
      because: c.because, at: c.at ?? 0, resolution: (c.resolution as 'open' | 'withdrawn' | 'set_aside') ?? 'open',
    })),
    lineage: { up: raw.lineage?.up ?? [], down: raw.lineage?.down ?? [] },
    history: (raw.history ?? []).map((h) => ({ at: h.at ?? 0, act: h.act, by: h.by ?? '', by_alias: h.by_alias ?? '', because: h.because ?? null })),
    originating: {
      conversation: raw.originating?.conversation ?? null,
      conversation_name: raw.originating?.conversation_name ?? null,
      turn: raw.originating?.turn ?? null,
      number: raw.originating?.number ?? null,
    },
    adoption: {
      requests: raw.adoption?.requests ?? [],
      declines: raw.adoption?.declines ?? [],
      adopted,
    },
    usage: raw.usage
      ? {
          delivered: raw.usage.delivered,
          executions: raw.usage.executions ?? raw.usage.delivered,
          cited: raw.usage.cited,
          outcomes_after_delivery: raw.usage.outcomes_after_delivery ?? null,
        }
      : null,
  }
}

/** THE BRAIN BROWSER'S OWN LISTING (Workstream A): search, the four filters,
 *  the compact rows. Left empty here on purpose -- this worktree needs only
 *  `fetchBrainRecord` -- and replaced wholesale at integration by whichever
 *  worktree's version the owner keeps. */
export async function fetchBrainList(_filter: BrainFilter, _query: string): Promise<BrainRecordSummary[]> {
  return []
}
