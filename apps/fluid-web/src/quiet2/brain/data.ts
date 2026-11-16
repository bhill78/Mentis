/* THE BRAIN BROWSER'S DATA LAYER (Workstream C): plain async reads over the
 * Ladder and the governed register, read-only, writing nothing and deciding
 * nothing. No new storage and no second governance mechanism: every filter
 * here is a VIEW over material the record already keeps, exactly the views
 * DESIGN-r2.md draws (Knowledge · Governing · Needs you · All) -- never a
 * fourth category invented beside the Ladder's own.
 *
 * SOURCES, one per filter, and why:
 *  - Knowledge:  `/api/ladder/items` + `/api/ladder/adopted`, kept to
 *                `governs === false` (Contract: knowing `that`).
 *  - Governing:  `/api/governed`, kept to the Kinds `/api/governance/
 *                authoring` declares `placement_directs_work` (knowing
 *                `how`) -- the register also walks `lesson`/`hypothesis`
 *                (knowledge Kinds that happen to be `standing_apt`), and
 *                those are excluded here so they are not shown twice under
 *                two different filters that both claim them.
 *  - Needs you:  the SAME two reads the existing dock/column already make --
 *                `/api/ladder/adoption` (adoption requests) and `/api/owed`
 *                (owed asks, resolved to the material they name exactly as
 *                `surfaces/governance/askCoverage.ts`'s `useAskCoverage`
 *                does, minus the hook). No second "needs you" is computed.
 *  - All:        Knowledge ∪ Governing, de-duplicated by id -- a `lesson`
 *                (knowledge) that the register also lists as `standing_apt`
 *                authoring material must not appear twice.
 *
 * SERVER SHAPES, NOT ladderTypes.ts'S WIDER ONES. `LadderItemDetail` there
 * types `outcomes` and `cited_by` as unions wide enough to cover a shape the
 * detail endpoint never actually sends (`investigation.md` §6.4); this file
 * reads the detail endpoint's real, narrower shape (§6.2: `outcomes` always
 * an array, `cited_by` likewise) and is defensive, not permissive, about the
 * other shape. */
import { CLIENT_HEADERS } from '../../api'
import {
  atAlias,
  formatStatusLabel,
  resolutionOf,
  type BasisLink,
  type ChallengeItem,
  type HistoryRecord,
  type LadderAdoptionRequest,
  type LadderAdoptionResponse,
  type LadderAdoptedResponse,
  type LadderItem,
  type LadderItemsResponse,
  type RecordedBy,
} from '../../fluid/governance/ladderTypes'
import { store } from '../../fluid/store'
import type { KindAuthoring } from '../../surfaces/governance/r2Model'
import type { Row as GovernedRow } from '../../surfaces/Register'

export type BrainFilter = 'knowledge' | 'governing' | 'needs-you' | 'all'

export interface BrainRecordSummary {
  id: string
  kind: string
  text: string
  standingPlain: string // full sentence, per DESIGN-r2.md's table
  standingLabel: string // short pill, e.g. "Adopted · knowledge"
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
  lineage: { up: Array<unknown>; down: Array<unknown> }
  history: Array<{ at: number; act: string; by: string; by_alias: string; because: string | null }>
  originating: { conversation?: string | null; conversation_name?: string | null; turn?: string | null; number?: number | null }
  adoption: { requests: Array<unknown>; declines: Array<unknown>; adopted: { by: string; at: number; because: string | null } | null }
  usage: { delivered: number; executions: number; cited: number; outcomes_after_delivery: { worked: number; failed: number; other: number } | null } | null
}

/* -- words: the Ladder→plain-words table (DESIGN-r2.md, "The record, at rest") */

/** THE TABLE, EXACTLY. `kind`/`by` are optional context a list row does not
 *  always carry (a bare `LadderItem` never names who asked for adoption;
 *  `/api/ladder/adoption`'s own rows do, and pass it). `status` takes the
 *  Ladder's adoption vocabulary (`recorded | adoption_requested | adopted |
 *  declined | superseded | ended | retired`) or the register's `stands /
 *  candidate / replaced / ended` translated to it (`statusOfGovernedRow`).
 *  `challenged` is never a status passed here: DESIGN-r2.md calls it "a
 *  separate quiet flag, never a status", carried on `BrainRecordSummary.
 *  challenged` instead. */
export function plainStandingLabel(status: string, governs: boolean, opts?: { by?: string | null; kind?: string | null }): string {
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
      return kind === 'hypothesis' ? 'Not settled' : 'Recorded, not adopted (reaches agents only as labelled past experience)'
    case 'declined':
      return 'Not in effect — declined'
    case 'superseded':
      return 'Not in effect — replaced by a later version'
    case 'ended':
    case 'retired':
      return 'Not in effect — ended'
    default:
      return 'Not in effect'
  }
}

/** THE SHORT PILL beside the plain-language line (DESIGN-r2.md "Standing"):
 *  the Ladder's own status word, plus "knowledge" for a working position or
 *  the Kind's own name for governing material -- e.g. "Adopted · knowledge",
 *  "Adoption requested · rule". Reuses `formatStatusLabel` (ladderTypes.ts)
 *  rather than redeclaring the status vocabulary's words. */
export function standingPillLabel(status: string, kind: string, governs: boolean): string {
  return `${formatStatusLabel(status).label} · ${governs ? kind : 'knowledge'}`
}

/** `worked`→"Helped", `failed`→"Didn't help", `inconclusive`→"Unclear".
 *  Live `result` is free text today (investigation.md §6.4): anything else
 *  passes through unchanged rather than crashing or showing "undefined". */
export function verdictLabel(result: string): 'Helped' | "Didn't help" | 'Unclear' | string {
  if (result === 'worked') return 'Helped'
  if (result === 'failed') return "Didn't help"
  if (result === 'inconclusive') return 'Unclear'
  return result == null ? '' : result
}

/* -- merging two list sources without ever doubling a record -------------- */

/** THE 'ALL' FILTER'S UNION: every list, in order, kept to the first record
 *  with each id -- a `lesson` the register also lists as authoring material
 *  is one row, not two. Pure, so the dedup itself is checkable without a
 *  server. */
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

/* -- shape normalizers: the detail endpoint's real arrays, never a count -- */

/** `ladder.outcomes_of`: the LIST endpoint sends `{count, latest}` (≤3); the
 *  DETAIL endpoint (`/api/ladder/items/<id>`, §6.2) sends the whole array.
 *  `BrainRecordDetail.outcomes` is always the flat array `fetchBrainRecord`
 *  reads today; this stays defensive about the other shape rather than
 *  assuming the narrower one always arrives. */
export function normalizeOutcomes(raw: unknown): BrainRecordDetail['outcomes'] {
  const rows: unknown[] = Array.isArray(raw)
    ? raw
    : raw && typeof raw === 'object' && Array.isArray((raw as { all?: unknown[] }).all)
      ? (raw as { all: unknown[] }).all
      : raw && typeof raw === 'object' && Array.isArray((raw as { latest?: unknown[] }).latest)
        ? (raw as { latest: unknown[] }).latest
        : []
  return rows.map((row) => {
    const o = (row ?? {}) as Record<string, unknown>
    return {
      id: o.id == null ? '' : String(o.id),
      result: o.result == null ? '' : String(o.result),
      attempted: o.attempted === true,
      text: o.text == null ? '' : String(o.text),
      in_context: o.in_context == null ? '' : String(o.in_context),
      recorded_at: typeof o.recorded_at === 'number' ? o.recorded_at : 0,
    }
  })
}

/** `cited_by`: a COUNT on the list endpoint, an ARRAY on the detail endpoint
 *  (§6.1 vs §6.2) -- never both read the same way. Used only as a fallback
 *  for `usage.cited` when the server's own count is missing. */
export function countOf(raw: unknown): number {
  if (Array.isArray(raw)) return raw.length
  if (typeof raw === 'number') return raw
  return 0
}

/* -- the record as the Ladder's `governs` flag already splits it ---------- */

function baseSummary(row: {
  id: string
  kind: string
  text: string
  governs: boolean
  challenged?: number | null
  status: string
  recorded_by?: { conversation?: string | null; turn?: string | null; number?: number | null } | null
}): BrainRecordSummary {
  return {
    id: row.id,
    kind: row.kind,
    text: row.text,
    governs: row.governs,
    challenged: (row.challenged ?? 0) > 0,
    conversation: row.recorded_by?.conversation ?? null,
    turn: row.recorded_by?.turn ?? null,
    number: row.recorded_by?.number ?? null,
    standingPlain: plainStandingLabel(row.status, row.governs, { kind: row.kind }),
    standingLabel: standingPillLabel(row.status, row.kind, row.governs),
  }
}

function summaryFromLadderItem(item: LadderItem): BrainRecordSummary {
  return baseSummary({
    id: item.id,
    kind: item.kind,
    text: item.text,
    governs: item.governs,
    challenged: item.challenged,
    status: item.status,
    recorded_by: item.recorded_by,
  })
}

/* -- client-side search, where the endpoint read here does not take `q` --- */

function matchesQuery(r: BrainRecordSummary, q: string): boolean {
  const needle = q.trim().toLowerCase()
  if (!needle) return true
  return [r.id, r.kind, r.text].some((s) => s.toLowerCase().includes(needle))
}

/* -- the plain fetch, `getJson`-style (quiet2/epistemic/read.ts), not useApi */

async function getJson<T>(path: string): Promise<T> {
  const r = await fetch(path, { headers: { ...CLIENT_HEADERS } })
  const body = (await r.json().catch(() => null)) as (T & { error?: string }) | null
  if (!r.ok || !body || body.error) throw new Error(body?.error ?? r.statusText ?? 'the record did not answer')
  return body
}

/** `/api/ladder/items` and `/api/ladder/adopted` both take `limit` 1..1000
 *  (default 50). `/api/ladder/adopted` missing `limit` is a documented,
 *  silent cap at 50 (investigation.md §3); every call here states it. */
const LADDER_LIMIT = 1000
/** `/api/governed`'s `limit` bounds EACH group it returns, max 1000. */
const GOVERNED_LIMIT = 1000

/* -- Knowledge: governs === false, from the Ladder's own two lists -------- */

async function fetchKnowledge(q: string): Promise<BrainRecordSummary[]> {
  const qs = q.trim() ? `&q=${encodeURIComponent(q.trim())}` : ''
  const [items, adopted] = await Promise.all([
    getJson<LadderItemsResponse>(`/api/ladder/items?limit=${LADDER_LIMIT}${qs}`),
    getJson<LadderAdoptedResponse>(`/api/ladder/adopted?limit=${LADDER_LIMIT}${qs}`),
  ])
  const knowledge = [...items.items, ...adopted.items].filter((it) => !it.governs).map(summaryFromLadderItem)
  return dedupeById([knowledge])
}

/* -- Governing: `/api/governed`, kept to Kinds that direct work ------------ */

/** A register row's `state`/`group` translated to the Ladder's own adoption
 *  words, so `plainStandingLabel` never needs a second vocabulary. `stands`
 *  -> adopted; a `candidate` the register itself grouped as `proposed` (an
 *  open ask exists) -> adoption_requested, else -> recorded (DESIGN-r2.md's
 *  "Proposed, nobody asked you"); `replaced` -> superseded; `ended` ->
 *  ended; unknown standing (`state: null`) -> recorded, the least claim. */
function statusOfGovernedRow(row: GovernedRow): string {
  if (row.state === 'stands') return 'adopted'
  if (row.state === 'candidate') return row.group === 'proposed' ? 'adoption_requested' : 'recorded'
  if (row.state === 'replaced') return 'superseded'
  if (row.state === 'ended') return 'ended'
  return 'recorded'
}

function summaryFromGovernedRow(row: GovernedRow): BrainRecordSummary {
  const status = statusOfGovernedRow(row)
  const challenged = (row.open_disputes?.length ?? row.disputed_by.length) > 0
  const proposal = row.proposed_by[0]
  const placement = row.placed_at[0]
  return {
    id: row.entry,
    kind: row.kind,
    text: row.summary,
    governs: true,
    challenged,
    conversation: proposal?.conversation ?? placement?.conversation ?? null,
    turn: proposal?.turn ?? null,
    number: null,
    standingPlain: plainStandingLabel(status, true, { kind: row.kind }),
    standingLabel: standingPillLabel(status, row.kind, true),
  }
}

async function fetchGoverning(q: string): Promise<BrainRecordSummary[]> {
  const qs = q.trim() ? `&q=${encodeURIComponent(q.trim())}` : ''
  const [authoring, governed] = await Promise.all([
    getJson<{ kinds: KindAuthoring[] }>('/api/governance/authoring'),
    getJson<{ groups: Record<string, GovernedRow[]> }>(`/api/governed?limit=${GOVERNED_LIMIT}${qs}`),
  ])
  // THE KIND SET, FROM THE BRAIN'S OWN DECLARATION, not a hard-coded list
  // (investigation.md §3: the Learning Kind filter omits `note`/
  // `source-material`, and Adopted's `instruction` never matches the real
  // `conversation-instruction`). A Kind `/api/governance/authoring` does not
  // mention is simply not governing.
  const directsWork = new Map(authoring.kinds.map((k) => [k.kind, k.authoring?.placement_directs_work === true]))
  const rows = Object.values(governed.groups ?? {}).flat()
  // The register also walks `lesson`/`hypothesis` (knowledge Kinds that
  // declare `standing_apt`); those surface under Knowledge, not here.
  const governing = rows.filter((row) => directsWork.get(row.kind) === true).map(summaryFromGovernedRow)
  return dedupeById([governing])
}

/* -- Needs you: the SAME data the dock/column already read ---------------- */

function summaryFromAdoptionRequest(req: LadderAdoptionRequest): BrainRecordSummary {
  const alias = req.asked_by?.alias ?? null
  const by = alias ? atAlias(alias) : ''
  return {
    id: req.entry,
    kind: req.kind,
    text: req.wording.proposed,
    governs: req.governs,
    challenged: (req.challenges ?? []).some((c) => resolutionOf(c) === 'open'),
    conversation: req.conversation ?? null,
    turn: req.turn ?? null,
    number: req.number ?? null,
    standingPlain: plainStandingLabel('adoption_requested', req.governs, { by, kind: req.kind }),
    standingLabel: standingPillLabel('adoption_requested', req.kind, req.governs),
  }
}

/** The governed material an owed ask names, exactly as `surfaces/governance/
 *  askCoverage.ts`'s `useAskCoverage` resolves it -- the owed asks, then the
 *  Turns they hang on, then each open expectation's own `material[]` -- with
 *  no hook and no second "needs you" invented. A Turn that cannot be read
 *  contributes nothing rather than failing the whole read. */
async function namedByOwedAsks(owed: Array<{ expectation: string; turn: string | null }>): Promise<Set<string>> {
  const open = new Set(owed.map((r) => r.expectation))
  const turns = [...new Set(owed.map((r) => r.turn).filter((t): t is string => !!t))]
  const named = new Set<string>()
  if (!turns.length) return named
  const read = await Promise.all(
    turns.map((t) =>
      getJson<{ expectations?: Array<{ id: string; material?: string[] }> }>(`/api/turns/${encodeURIComponent(t)}`).catch(() => null),
    ),
  )
  for (const turn of read) {
    for (const e of turn?.expectations ?? []) {
      if (!open.has(e.id)) continue
      for (const m of e.material ?? []) named.add(m)
    }
  }
  return named
}

async function fetchNeedsYou(q: string): Promise<BrainRecordSummary[]> {
  const me = await store.loadMe()
  const [adoption, owed] = await Promise.all([
    getJson<LadderAdoptionResponse>('/api/ladder/adoption'),
    getJson<{ owed: Array<{ expectation: string; turn: string | null }> | null }>(
      `/api/owed?participant=${encodeURIComponent(me)}&limit=50`,
    ),
  ])
  const requests = adoption.requests.map(summaryFromAdoptionRequest)
  const already = new Set(requests.map((r) => r.id))
  const named = [...(await namedByOwedAsks(owed.owed ?? []))].filter((id) => !already.has(id))
  const extra = named.length
    ? (
        await Promise.all(
          named.map((id) =>
            fetchBrainRecord(id).then(
              (d): BrainRecordSummary => d,
              () => null,
            ),
          ),
        )
      ).filter((r): r is BrainRecordSummary => r !== null)
    : []
  const all = dedupeById([requests, extra])
  return q.trim() ? all.filter((r) => matchesQuery(r, q)) : all
}

/* -- the one list read, dispatched by filter ------------------------------- */

export async function fetchBrainList(filter: BrainFilter, query: string): Promise<BrainRecordSummary[]> {
  if (filter === 'knowledge') return fetchKnowledge(query)
  if (filter === 'governing') return fetchGoverning(query)
  if (filter === 'needs-you') return fetchNeedsYou(query)
  // 'all': Knowledge ∪ Governing, never a third source and never a new
  // category (DESIGN-r2.md tradeoff #4: these are views, not a taxonomy).
  const [knowledge, governing] = await Promise.all([fetchKnowledge(query), fetchGoverning(query)])
  return dedupeById([knowledge, governing])
}

/* -- the record, inspected: `/api/ladder/items/<id>` ----------------------- */

/** The DETAIL endpoint's real shape (§6.2), not `LadderItemDetail`'s wider
 *  one: `outcomes` is always the array (never `{count,latest}`), `cited_by`
 *  is always the array (never the list endpoint's count), and `history` rows
 *  carry `by_alias` that `HistoryRecord` does not declare. */
interface RawDetail {
  id: string
  kind: string
  text: string
  status: string
  challenged: number
  governs: boolean
  recorded_by?: RecordedBy | null
  basis?: BasisLink[]
  outcomes?: unknown
  cited_by?: unknown
  challenges?: ChallengeItem[]
  lineage?: { up?: unknown[]; down?: unknown[] }
  history?: Array<HistoryRecord & { by_alias?: string | null }>
  originating?: { conversation?: string | null; conversation_name?: string | null; turn?: string | null; number?: number | null } | null
  adoption?: {
    requests?: unknown[]
    declines?: unknown[]
    adopted?: { by?: string | null; at?: number | null; because?: string | null } | null
  }
  usage?: {
    delivered?: number
    executions?: number
    cited?: number
    outcomes_after_delivery?: { worked?: number; failed?: number; other?: number } | null
  } | null
}

export function mapBrainDetail(raw: RawDetail): BrainRecordDetail {
  const base = baseSummary({
    id: raw.id,
    kind: raw.kind,
    text: raw.text,
    governs: raw.governs,
    challenged: raw.challenged,
    status: raw.status,
    recorded_by: raw.recorded_by,
  })
  return {
    ...base,
    basis: (raw.basis ?? []).map((b) => ({ ref: b.ref, relation: b.relation, kind: b.kind ?? '', label: b.label, cite: b.cite ?? null })),
    outcomes: normalizeOutcomes(raw.outcomes),
    challenges: (raw.challenges ?? []).map((c) => ({
      link: c.link,
      objection: c.objection ?? '',
      by: c.by ?? '',
      by_alias: c.by_alias ?? '',
      because: c.because ?? '',
      at: c.at ?? 0,
      resolution: resolutionOf(c),
    })),
    lineage: { up: raw.lineage?.up ?? [], down: raw.lineage?.down ?? [] },
    history: (raw.history ?? []).map((h) => ({ at: h.at ?? 0, act: h.act, by: h.by ?? '', by_alias: h.by_alias ?? '', because: h.because })),
    originating: raw.originating ?? {},
    adoption: {
      requests: raw.adoption?.requests ?? [],
      declines: raw.adoption?.declines ?? [],
      adopted: raw.adoption?.adopted
        ? { by: raw.adoption.adopted.by ?? '', at: raw.adoption.adopted.at ?? 0, because: raw.adoption.adopted.because ?? null }
        : null,
    },
    usage: raw.usage
      ? {
          delivered: raw.usage.delivered ?? 0,
          executions: raw.usage.executions ?? 0,
          cited: typeof raw.usage.cited === 'number' ? raw.usage.cited : countOf(raw.cited_by),
          outcomes_after_delivery: raw.usage.outcomes_after_delivery
            ? {
                worked: raw.usage.outcomes_after_delivery.worked ?? 0,
                failed: raw.usage.outcomes_after_delivery.failed ?? 0,
                other: raw.usage.outcomes_after_delivery.other ?? 0,
              }
            : null,
        }
      : null,
  }
}

export async function fetchBrainRecord(id: string): Promise<BrainRecordDetail> {
  const raw = await getJson<RawDetail>(`/api/ladder/items/${encodeURIComponent(id)}`)
  return mapBrainDetail(raw)
}
