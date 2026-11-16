/* THE BRAIN BROWSER'S DATA LAYER: plain reads over the Ladder, writing
 * nothing and deciding nothing.
 *
 * ONE LIST, ONE VOCABULARY, FROM THE SERVER. `GET /api/ladder/browse` lists
 * the Brain's records newest first, a page at a time, each with the status
 * the record gives it now (`adoption_status`) and its Kind's `governs`. The
 * filters -- Knowledge · Governing · Needs you · All -- are VIEWS of that one
 * list (DESIGN-r2.md), never categories invented beside the Ladder's own.
 * Nothing here rebuilds standing from another read: round 2 did, and a
 * declined candidate read as Recorded (acceptance audit, finding 4).
 *
 *  - Knowledge:  Kinds whose knowing is `that`.
 *  - Governing:  Kinds whose knowing is `how` (they direct work).
 *  - Needs you:  the records the owner is asked about now, by the SAME rule
 *                the global dock's bell lists (`home.asking_owner`), resolved
 *                to records on the server. No second "needs you".
 *  - All:        the first two together, one row per record.
 *
 * ONE DETAIL NORMALISER (`mapBrainDetail`): every view of a record reads
 * `GET /api/ladder/items/<id>` through it, so words, standing, who and when
 * are said the same way everywhere. The server's shapes are followed, not
 * `ladderTypes.ts`'s wider ones (investigation.md §6.4). */
import { CLIENT_HEADERS } from '../../api'
import { formatStatusLabel } from '../../fluid/governance/ladderTypes'

export type BrainFilter = 'knowledge' | 'governing' | 'needs-you' | 'all'
export type SummarySource = 'written' | 'generated' | 'derived'
const sourceOf = (v: unknown): SummarySource => (v === 'written' || v === 'generated' ? v : 'derived')

export interface Where { conversation: string; conversation_name: string | null; turn: string; number: number | null }

export interface BrainRecordSummary {
  id: string
  kind: string
  text: string
  /** ONE SENTENCE A PERSON CAN SCAN: what a list row says. Presentation
   *  only -- the record's own wording is `text`, and is what its view shows */
  summary: string
  /** where the summary came from: somebody `written` it, a model `generated`
   *  it once, or it is `derived` from the record's own first sentence */
  summarySource: SummarySource
  /** the Ladder's own status word, as the server reads it now */
  status: string
  standingPlain: string // full sentence, per DESIGN-r2.md's table
  standingLabel: string // short pill, e.g. "Adopted · knowledge"
  governs: boolean
  adoptable: boolean
  /** OPEN challenges: a separate flag, never a status */
  challenged: number
  recordedAt: number | null
  by: string | null
  conversation: string | null
  conversationName: string | null
  turn: string | null
  number: number | null
}

export interface BrainKind { kind: string; count: number; governs: boolean }

export interface BrainPage {
  items: BrainRecordSummary[]
  /** how many records match, whatever page this is */
  total: number
  /** records left out because they were replaced or deleted (unless asked for) */
  past: number
  /** the Kinds present in this view, from the record itself */
  kinds: BrainKind[]
  /** Needs you: the record names no owner, so nothing can be said to ask them */
  unknown?: boolean
}

export interface BrainQuery {
  view: BrainFilter
  q?: string
  kind?: string
  status?: string
  /** include what was replaced or deleted */
  past?: boolean
  challenged?: boolean
  limit?: number
  offset?: number
}

/* -- words: the Ladder→plain-words table (DESIGN-r2.md, "The record, at rest") */

/** THE TABLE, EXACTLY. `status` is the Ladder's adoption vocabulary
 *  (`recorded | adoption_requested | adopted | declined | superseded |
 *  deleted`). `challenged` is never a status passed here: DESIGN-r2.md calls
 *  it "a separate quiet flag, never a status". A status this does not know is
 *  said as the least claim, "Not in effect", never as Recorded. */
export function plainStandingLabel(status: string, governs: boolean, opts?: { by?: string | null; kind?: string | null; replacedBy?: string | null }): string {
  const by = (opts?.by ?? '').trim()
  const kind = opts?.kind ?? null
  switch (status) {
    case 'adopted':
      return governs
        ? 'In effect — agents are given it as a rule'
        : "In effect as knowledge — agents are told it when relevant; it doesn't bind them"
    case 'adoption_requested':
      return by
        ? `Not in effect — proposed by ${by}, waiting for your decision`
        : 'Not in effect — proposed, waiting for your decision'
    case 'recorded':
      // hypothesis, recorded -> "Not settled" is its own row of the table
      if (kind === 'hypothesis') return 'Not settled'
      // a governing Kind that nobody adopted governs nothing; it is not
      // "experience" either: it reaches only a run that names it
      return governs ? 'Not in effect — recorded, not adopted; it governs nothing and reaches only runs that name it'
        : 'Recorded, not adopted (reaches agents only as labelled past experience)'
    case 'declined':
      return 'Not in effect — declined'
    case 'superseded':
      return opts?.replacedBy ? `Not in effect — replaced by ${opts.replacedBy}` : 'Not in effect — replaced by a later version'
    case 'deleted':
    case 'ended':
    case 'retired':
      return 'Not in effect — ended'
    default:
      return 'Not in effect'
  }
}

/** The Ladder's status word for the pill. A status the Ladder does not name
 *  is shown as "Unknown", never as "Recorded" (acceptance audit, finding 4). */
export function statusWord(status: string): string {
  switch (status) {
    case 'recorded': case 'adoption_requested': case 'adopted': case 'declined': case 'superseded':
      return formatStatusLabel(status).label
    case 'deleted': case 'ended': case 'retired':
      return 'Ended'
    default:
      return 'Unknown'
  }
}

/** THE SHORT PILL beside the plain-language line (DESIGN-r2.md "Standing"):
 *  the Ladder's own status word, plus "knowledge" for a working position or
 *  the Kind's own name for governing material -- e.g. "Adopted · knowledge",
 *  "Adoption requested · rule". */
export function standingPillLabel(status: string, kind: string, governs: boolean): string {
  return `${statusWord(status)} · ${governs ? kind.replace(/[-_]/g, ' ') : 'knowledge'}`
}

/** The few plain words a compact row shows after the Ladder word: read from
 *  the status itself. "not settled" only for a hypothesis that is merely
 *  recorded -- an adopted or replaced hypothesis is said as what it is. */
export function compactWords(status: string, kind: string): { words: string; off: boolean } {
  switch (status) {
    case 'adopted': return { words: 'in effect', off: false }
    case 'adoption_requested': return { words: 'not in effect', off: false }
    case 'recorded': return { words: kind === 'hypothesis' ? 'not settled' : 'not in effect', off: false }
    case 'declined': return { words: 'declined', off: true }
    case 'superseded': return { words: 'replaced', off: true }
    case 'deleted': case 'ended': case 'retired': return { words: 'ended', off: true }
    default: return { words: 'not in effect', off: false }
  }
}

/** `worked`→"Helped", `failed`→"Didn't help", `inconclusive`→"Unclear".
 *  Live `result` is free text today (investigation.md §6.4): anything else
 *  passes through unchanged rather than crashing or showing "undefined". */
export function verdictLabel(result: string | null | undefined): 'Helped' | "Didn't help" | 'Unclear' | string {
  const r = (result ?? '').trim().toLowerCase()
  if (r === 'worked') return 'Helped'
  if (r === 'failed') return "Didn't help"
  if (r === 'inconclusive') return 'Unclear'
  return result == null ? '' : result
}

/** Whether a result is one of the three verdicts an effectiveness evaluation
 *  records; anything else is somebody's own words and is shown as written. */
export function isVerdict(result: string | null | undefined): boolean {
  return ['worked', 'failed', 'inconclusive'].includes((result ?? '').trim().toLowerCase())
}

/** Keeps the first record with each id. */
export function dedupeById<T extends { id: string }>(lists: T[][]): T[] {
  const seen = new Set<string>()
  const out: T[] = []
  for (const list of lists) {
    for (const row of list) {
      if (seen.has(row.id)) continue
      seen.add(row.id)
      out.push(row)
    }
  }
  return out
}

/* -- the plain fetch ------------------------------------------------------ */

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const r = await fetch(path, { headers: { ...CLIENT_HEADERS }, signal })
  const body = (await r.json().catch(() => null)) as (T & { error?: string }) | null
  if (!r.ok || !body || body.error) throw new Error(body?.error ?? r.statusText ?? 'the record did not answer')
  return body
}

/* -- the list ------------------------------------------------------------- */

interface RawRow {
  id: string; kind: string; text?: string | null; status: string; governs: boolean; adoptable?: boolean
  summary?: string | null; summary_source?: string | null
  challenged?: number | null; recorded_at?: number | null
  recorded_by?: { alias?: string | null; participant?: string | null; conversation?: string | null; conversation_name?: string | null; turn?: string | null; number?: number | null } | null
}

export function mapBrainRow(row: RawRow): BrainRecordSummary {
  const by = row.recorded_by?.alias ?? null
  return {
    id: row.id,
    kind: row.kind || 'record',
    text: row.text ?? '',
    summary: (row.summary ?? '').trim() || (row.text ?? ''),
    summarySource: sourceOf(row.summary_source),
    status: row.status,
    governs: !!row.governs,
    adoptable: !!row.adoptable,
    challenged: row.challenged ?? 0,
    recordedAt: row.recorded_at ?? null,
    by,
    conversation: row.recorded_by?.conversation ?? null,
    conversationName: row.recorded_by?.conversation_name ?? null,
    turn: row.recorded_by?.turn ?? null,
    number: row.recorded_by?.number ?? null,
    standingPlain: plainStandingLabel(row.status, !!row.governs, { kind: row.kind }),
    standingLabel: standingPillLabel(row.status, row.kind || 'record', !!row.governs),
  }
}

export const BRAIN_PAGE = 50

/** The browse read's address: only what was asked is sent. Pure, so the
 *  paging and the filters are checkable without a server. */
export function browseUrl(query: BrainQuery): string {
  const p = new URLSearchParams({ view: query.view, limit: String(query.limit ?? BRAIN_PAGE) })
  if (query.offset) p.set('offset', String(query.offset))
  if (query.q?.trim()) p.set('q', query.q.trim())
  if (query.kind) p.set('kind', query.kind)
  if (query.status) p.set('status', query.status)
  if (query.past) p.set('past', '1')
  if (query.challenged) p.set('challenged', '1')
  return `/api/ladder/browse?${p.toString()}`
}

export async function fetchBrainPage(query: BrainQuery, signal?: AbortSignal): Promise<BrainPage> {
  const raw = await getJson<{ items: RawRow[]; total: number; past?: number; kinds?: BrainKind[]; unknown?: boolean }>(browseUrl(query), signal)
  return { items: raw.items.map(mapBrainRow), total: raw.total, past: raw.past ?? 0, kinds: raw.kinds ?? [], unknown: raw.unknown }
}

/** How many records have an open adoption request, whether or not anybody is
 *  asked about them now: said beside Needs you, so a request that never
 *  reached the bell is not lost from view. */
export async function countAdoptionRequested(signal?: AbortSignal): Promise<number> {
  const got = await getJson<{ total: number }>(browseUrl({ view: 'all', status: 'adoption_requested', limit: 1 }), signal)
  return got.total
}

/* -- the record, inspected: `/api/ladder/items/<id>` ----------------------- */

export interface BrainBasis {
  ref: string; relation: string; kind: string; label: string; cite: string | null
  artifact: { name?: string | null; size?: number | null; media_type?: string | null } | null
  excerpt: string | null
  where: Where | null
}
export interface BrainOutcome { id: string; result: string; attempted: boolean | null; text: string; in_context: string | null; recorded_at: number; where: Where | null }
export interface BrainChallenge {
  link: string; objection: string; by: string; by_alias: string; because: string; evidence: string[]; at: number
  resolution: 'open' | 'withdrawn' | 'set_aside'
  answer: { by: string; by_alias: string; because: string; at: number } | null
}
export interface BrainLineageNode { id: string; kind: string; label: string; relation: string; depth: number; result?: string | null; where: Where | null }
export interface BrainRequest {
  request: string; ask: string | null; by: string; by_alias: string; migrated_by_alias: string | null; at: number
  because: string | null; scope: unknown; replaces: Array<{ id: string; text: string }>; closed: boolean; closed_by: string | null
}
export interface BrainDecline { by: string; by_alias: string; at: number; because: string; request: string | null }
export interface BrainDelivery { execution: string; participant_alias: string | null; runtime: string | null; conversation: string | null; at: number; tier: string | null }
export interface BrainCitation { entry: string; kind: string; relation: string; by_alias: string | null; at: number; label: string }

/** A summary's provenance, as the record's own view says it. */
export interface BrainSummaryInfo { by: string | null; byAlias: string | null; at: number | null; model: string | null; earlier: number }

export interface BrainRecordDetail extends BrainRecordSummary {
  summaryInfo: BrainSummaryInfo
  /** every declared field but the principal words, as the record holds them */
  fields: Array<{ name: string; value: string }>
  limits: string | null
  recordedBy: { alias: string | null; runtime: string | null; model: string | null; personaName: string | null }
  basis: BrainBasis[]
  outcomes: BrainOutcome[]
  challenges: BrainChallenge[]
  lineage: { up: BrainLineageNode[]; down: BrainLineageNode[] }
  history: Array<{ at: number; act: string; by: string; by_alias: string; because: string | null }>
  originating: { conversation: string | null; conversation_name: string | null; turn: string | null; number: number | null }
  adoption: {
    requests: BrainRequest[]
    declines: BrainDecline[]
    adopted: { by: string; by_alias: string | null; at: number; because: string | null; scopeLabel: string | null } | null
  }
  supersededBy: Array<{ id: string | null; kind: string | null; label: string | null; deleted: boolean }>
  delivered: BrainDelivery[]
  deliveredTotal: number
  citedBy: BrainCitation[]
  citedTotal: number
  usage: { delivered: number; executions: number; cited: number; after: { worked: number; failed: number; inconclusive: number; other: number } | null } | null
  /** the Brain's owner, so owner-only acts are offered only to them (the
   *  server decides every act whatever is offered) */
  owner: string | null
}

const str = (v: unknown, fallback = ''): string => (v == null ? fallback : String(v))
const num = (v: unknown): number => (typeof v === 'number' ? v : 0)
const obj = (v: unknown): Record<string, unknown> => (v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : {})
const arr = (v: unknown): unknown[] => (Array.isArray(v) ? v : [])

function whereOf(raw: unknown): Where | null {
  const w = obj(raw)
  return w.conversation && w.turn
    ? { conversation: str(w.conversation), conversation_name: w.conversation_name == null ? null : str(w.conversation_name), turn: str(w.turn), number: typeof w.number === 'number' ? w.number : null }
    : null
}

/** A field's value as words: a string as it is, a list one item per line,
 *  anything else as the JSON the record holds. */
export function fieldWords(value: unknown): string {
  if (value == null) return ''
  if (typeof value === 'string') return value
  if (Array.isArray(value) && value.every((v) => typeof v === 'string')) return value.join('\n')
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  try { return JSON.stringify(value, null, 1) } catch { return String(value) }
}

/** THE WORDS OF A RECORD: its `text`, else what the server says is its
 *  principal statement (`said`: a Persona's or a Workflow's own first field),
 *  else its first stated field. Only a record with no words at all is said
 *  to have none (acceptance audit, finding 5: "No words recorded" on records
 *  whose Kind keeps its words in another field). */
export function wordsOf(raw: { text?: unknown; said?: unknown; fields?: unknown }): { words: string; field: string | null } {
  const fields = obj(raw.fields)
  const text = str(raw.text).trim()
  if (text) return { words: text, field: 'text' in fields ? 'text' : null }
  const said = str(raw.said).trim()
  const named = Object.keys(fields).find((k) => typeof fields[k] === 'string' && String(fields[k]).trim() === said) ?? null
  if (said) return { words: said, field: named }
  const first = Object.keys(fields).find((k) => typeof fields[k] === 'string' && String(fields[k]).trim())
  return first ? { words: String(fields[first]).trim(), field: first } : { words: '', field: null }
}

/** `ladder.outcomes_of`: the LIST endpoint sends `{count, latest}`; the
 *  DETAIL endpoint sends the whole array. Defensive about the other shape. */
export function normalizeOutcomes(raw: unknown): BrainOutcome[] {
  const rows: unknown[] = Array.isArray(raw) ? raw : arr(obj(raw).all).length ? arr(obj(raw).all) : arr(obj(raw).latest)
  return rows.map((row) => {
    const o = obj(row)
    return {
      id: str(o.id),
      result: str(o.result),
      attempted: typeof o.attempted === 'boolean' ? o.attempted : null,
      text: str(o.text),
      in_context: o.in_context == null ? null : str(o.in_context),
      recorded_at: num(o.recorded_at),
      where: whereOf(o.where),
    }
  })
}

/** `cited_by`: a COUNT on the list endpoint, an ARRAY on the detail endpoint. */
export function countOf(raw: unknown): number {
  if (Array.isArray(raw)) return raw.length
  if (typeof raw === 'number') return raw
  return 0
}

function resolution(c: Record<string, unknown>): 'open' | 'withdrawn' | 'set_aside' {
  const r = str(c.resolution)
  if (r === 'withdrawn' || r === 'set_aside') return r
  if (c.withdrawn) return 'withdrawn'
  if (c.set_aside) return 'set_aside'
  return 'open'
}

function lineageNodes(raw: unknown): BrainLineageNode[] {
  return arr(raw).map((n) => {
    const o = obj(n)
    return { id: str(o.id), kind: str(o.kind), label: str(o.label), relation: str(o.relation), depth: typeof o.depth === 'number' ? o.depth : 1, result: o.result == null ? null : str(o.result), where: whereOf(o.where) }
  })
}

export function mapBrainDetail(raw: Record<string, unknown>): BrainRecordDetail {
  const rb = obj(raw.recorded_by)
  const { words, field } = wordsOf(raw)
  const fields = obj(raw.fields)
  const sum = obj(raw.summary)
  const base = mapBrainRow({
    summary: sum.text == null ? null : str(sum.text), summary_source: sum.source == null ? null : str(sum.source),
    id: str(raw.id), kind: str(raw.kind), text: words, status: str(raw.status), governs: raw.governs === true,
    adoptable: raw.adoptable === true, challenged: num(raw.challenged), recorded_at: typeof raw.recorded_at === 'number' ? raw.recorded_at : null,
    recorded_by: rb as RawRow['recorded_by'],
  })
  const adoption = obj(raw.adoption)
  const adopted = adoption.adopted ? obj(adoption.adopted) : null
  const usage = raw.usage ? obj(raw.usage) : null
  const after = usage?.outcomes_after_delivery ? obj(usage.outcomes_after_delivery) : null
  const superseded = arr(raw.superseded_by).map((s) => {
    const o = obj(s)
    return { id: o.id == null ? null : str(o.id), kind: o.kind == null ? null : str(o.kind), label: o.label == null ? null : str(o.label), deleted: o.deleted === true }
  })
  const successor = superseded.find((s) => !s.deleted && s.label)
  const requests: BrainRequest[] = arr(adoption.requests).map((r) => {
    const o = obj(r)
    return {
      request: str(o.request), ask: o.ask == null ? null : str(o.ask), by: str(o.by), by_alias: str(o.by_alias),
      migrated_by_alias: o.migrated_by_alias == null ? null : str(o.migrated_by_alias), at: num(o.at),
      because: o.because == null ? null : str(o.because), scope: o.scope ?? null,
      replaces: arr(o.replaces).map((x) => ({ id: str(obj(x).id), text: str(obj(x).text) })),
      closed: o.closed === true, closed_by: o.closed_by == null ? null : str(o.closed_by),
    }
  })
  const open = requests.find((r) => !r.closed)
  const status = base.status
  return {
    ...base,
    summaryInfo: {
      by: sum.by == null ? null : str(sum.by), byAlias: sum.by_alias == null ? null : str(sum.by_alias),
      at: typeof sum.at === 'number' ? sum.at : null, model: sum.model == null ? null : str(sum.model), earlier: num(sum.earlier),
    },
    // who asked is known here, and so is what replaced it: the sentence says so
    standingPlain: plainStandingLabel(status, base.governs, {
      kind: base.kind,
      by: status === 'adoption_requested' && open ? (open.by_alias || open.by).replace(/^@/, '') : null,
      replacedBy: successor?.label ? `“${successor.label.length > 80 ? successor.label.slice(0, 79).trimEnd() + '…' : successor.label}”` : null,
    }),
    fields: Object.keys(fields).filter((k) => k !== field && k !== 'limits' && fieldWords(fields[k]).trim()).map((k) => ({ name: k, value: fieldWords(fields[k]) })),
    limits: raw.limits == null || !str(raw.limits).trim() ? null : fieldWords(raw.limits),
    recordedBy: {
      alias: rb.alias == null ? null : str(rb.alias), runtime: rb.runtime == null ? null : str(rb.runtime),
      model: rb.model == null ? null : str(rb.model), personaName: rb.persona_name == null ? null : str(rb.persona_name),
    },
    basis: arr(raw.basis).map((b) => {
      const o = obj(b)
      return {
        ref: str(o.ref), relation: str(o.relation), kind: str(o.kind), label: str(o.label), cite: o.cite == null ? null : fieldWords(o.cite),
        artifact: o.artifact ? (obj(o.artifact) as BrainBasis['artifact']) : null,
        excerpt: o.excerpt == null ? null : str(o.excerpt), where: whereOf(o.where),
      }
    }),
    outcomes: normalizeOutcomes(raw.outcomes),
    challenges: arr(raw.challenges).map((c) => {
      const o = obj(c)
      const res = resolution(o)
      const ans = res === 'withdrawn' ? obj(o.withdrawn) : res === 'set_aside' ? obj(o.set_aside) : null
      return {
        link: str(o.link), objection: str(o.objection), by: str(o.by), by_alias: str(o.by_alias), because: str(o.because),
        evidence: arr(o.evidence).map((e) => str(e)), at: num(o.at), resolution: res,
        answer: ans ? { by: str(ans.by), by_alias: str(ans.by_alias), because: str(ans.because), at: num(ans.at) } : null,
      }
    }),
    lineage: { up: lineageNodes(obj(raw.lineage).up), down: lineageNodes(obj(raw.lineage).down) },
    history: arr(raw.history).map((h) => {
      const o = obj(h)
      return { at: num(o.at), act: str(o.act), by: str(o.by), by_alias: str(o.by_alias), because: o.because == null ? null : str(o.because) }
    }),
    originating: (() => {
      const o = obj(raw.originating)
      return {
        conversation: o.conversation == null ? base.conversation : str(o.conversation),
        conversation_name: o.conversation_name == null ? base.conversationName : str(o.conversation_name),
        turn: o.turn == null ? base.turn : str(o.turn),
        number: typeof o.number === 'number' ? o.number : base.number,
      }
    })(),
    adoption: {
      requests,
      declines: arr(adoption.declines).map((d) => {
        const o = obj(d)
        return { by: str(o.by), by_alias: str(o.by_alias), at: num(o.at), because: str(o.because), request: o.request == null ? null : str(o.request) }
      }),
      adopted: adopted
        ? { by: str(adopted.by), by_alias: adopted.by_alias == null ? null : str(adopted.by_alias), at: num(adopted.at), because: adopted.because == null ? null : str(adopted.because), scopeLabel: adopted.scope_label == null ? null : str(adopted.scope_label) }
        : null,
    },
    supersededBy: superseded,
    delivered: arr(raw.delivered).map((d) => {
      const o = obj(d)
      return { execution: str(o.execution), participant_alias: o.participant_alias == null ? null : str(o.participant_alias), runtime: o.runtime == null ? null : str(o.runtime), conversation: o.conversation == null ? null : str(o.conversation), at: num(o.at), tier: o.tier == null ? null : str(o.tier) }
    }),
    deliveredTotal: typeof raw.delivered_total === 'number' ? raw.delivered_total : arr(raw.delivered).length,
    citedBy: arr(raw.cited_by).map((c) => {
      const o = obj(c)
      return { entry: str(o.entry), kind: str(o.kind), relation: str(o.relation), by_alias: o.by_alias == null ? null : str(o.by_alias), at: num(o.at), label: str(o.label) }
    }),
    citedTotal: typeof raw.cited_total === 'number' ? raw.cited_total : countOf(raw.cited_by),
    usage: usage
      ? {
          delivered: num(usage.delivered),
          executions: num(usage.executions),
          cited: typeof usage.cited === 'number' ? usage.cited : countOf(raw.cited_by),
          after: after
            ? (() => {
                const inconclusive = num(after.inconclusive)
                // the server counts an inconclusive verdict in `other` AND by
                // its own name; here each outcome is said once
                return { worked: num(after.worked), failed: num(after.failed), inconclusive, other: Math.max(0, num(after.other) - inconclusive) }
              })()
            : null,
        }
      : null,
    owner: raw.owner == null ? null : str(raw.owner),
  }
}

export async function fetchBrainRecord(id: string, signal?: AbortSignal): Promise<BrainRecordDetail> {
  return mapBrainDetail(await getJson<Record<string, unknown>>(`/api/ladder/items/${encodeURIComponent(id)}`, signal))
}

/** Where a summary came from, in a few plain words for the record's view. */
export function summarySourceWords(source: SummarySource, info?: Partial<BrainSummaryInfo> | null): string {
  if (source === 'written') return `Summary written by ${(info?.byAlias ?? '').replace(/^@/, '') || 'the owner'}`
  if (source === 'generated') return `Summary generated${info?.model ? ` by ${info.model}` : ''}, not reviewed`
  return 'Summary taken from its first sentence'
}

/** The longest a summary may be: one sentence a row can show whole. */
export const SUMMARY_MAX = 200

/** Keeps the owner's summary of one record, or forgets it (`null`). Writes
 *  presentation metadata only: the record is not touched. */
export async function saveSummary(id: string, me: string, summary: string | null): Promise<void> {
  const r = await fetch(`/api/ladder/summaries/${encodeURIComponent(id)}`, {
    method: 'POST', headers: { ...CLIENT_HEADERS, 'Content-Type': 'application/json' },
    body: JSON.stringify(summary === null ? { attributed_to: me, remove: true } : { attributed_to: me, summary }),
  })
  const body = (await r.json().catch(() => null)) as { error?: string } | null
  if (!r.ok || !body || body.error) throw new Error(body?.error ?? r.statusText ?? 'the summary was not kept')
}

/** A record's own address in Quiet Chat: what "Copy link" copies, and what
 *  opening the page with it shows. */
export function recordUrl(id: string, origin = typeof location === 'undefined' ? '' : location.origin + location.pathname): string {
  return `${origin}?record=${encodeURIComponent(id)}`
}
