/* EPISTEMIC LADDER IN FLUID GOVERNANCE: Contract §4, §5, §6 shapes and pure helpers.
 *
 * Every Ladder view in Fluid Governance (`Learning`, `For adoption`, `Adopted`,
 * the Stage `GovItem` evidence/lineage view, `Waiting on you`, and the Compose
 * preview with `The work`) consumes these exact Contract §4 and §5 shapes. */

import type { Id } from '../../api'
import type { KindAuthoring } from '../../surfaces/governance/r2Model'
import { itemTitle, type OpenHint } from './model'

export type AdoptionStatus =
  | 'recorded'
  | 'adoption_requested'
  | 'adopted'
  | 'declined'
  | 'superseded'
  | 'ended'
  | 'retired'

export interface RecordedBy {
  participant: Id | null
  alias: string | null
  runtime: string | null
  model: string | null
  /** the Persona entry the run wore, and its name */
  persona: string | null
  persona_name?: string | null
  conversation: Id | null
  conversation_name: string | null
  turn: Id | null
  number: number | null
  execution: Id | null
  at: number | null
  /** a migrated request names its original proposer above, and who moved it here */
  migrated_by?: Id | null
  migrated_by_alias?: string | null
}

/** What the record says about held bytes an `adm-` basis row points at. */
export interface ArtifactInfo {
  name: string | null
  size?: number | null
  media_type?: string | null
}

/** The fields a basis row of an `adm-` carries (null where not an artifact):
 *  the artifact, the cited byte `range`, and the decoded `excerpt` of that
 *  range where the artifact is text and the range small. */
export interface ArtifactCite {
  artifact?: ArtifactInfo | null
  range?: [number, number] | null
  excerpt?: string | null
}

export interface BasisLink extends ArtifactCite {
  ref: Id
  relation: 'extracted-from' | 'derived-from' | 'outcome-of' | 'in-context' | string
  kind: string | null
  label: string
  cite: string | null
}

/** `ladder.outcomes_of` (Contract §4): newest first, never tallied. */
export interface OutcomeSummary {
  id: Id
  text: string | null
  result: 'worked' | 'failed' | 'mixed' | 'observed' | string | null
  attempted: boolean | null
  in_context: Id | null
  recorded_at: number | null
}

export interface LadderItem {
  id: Id
  kind: string
  text: string
  fields: Record<string, unknown>
  limits: string | null
  status: AdoptionStatus
  challenged: number
  recorded_by: RecordedBy
  recorded_at: number | null
  basis: BasisLink[]
  outcomes: {
    count: number
    latest: OutcomeSummary[]
  }
  delivered_to: number
  cited_by: number
  governs: boolean
  adoptable: boolean
}

export interface LadderCounts {
  /** items matching every filter except status and challenged */
  all?: number
  recorded: number
  adoption_requested: number
  adopted: number
  declined: number
  challenged: number
  delivered: number
  without_basis: number
}

export interface LadderItemsResponse {
  items: LadderItem[]
  total: number
  counts: LadderCounts
}

export interface LineageNode extends ArtifactCite {
  id: Id
  /** null for an artifact or anything that is not an entry of a Kind */
  kind: string | null
  relation: string
  label: string
  via?: Id
  depth?: number
  result?: string | null
  attempted?: boolean | null
  status?: AdoptionStatus | string
}

/** How a challenge was answered: still open, withdrawn by the participant
 *  who made it, or set aside by the owner (addendum 1, D7). */
export type ChallengeResolution = 'open' | 'withdrawn' | 'set_aside'

export interface ChallengeAnswer {
  link?: Id
  /** participant id */
  by: string | null
  by_alias?: string | null
  because: string | null
  at: number | null
}

/** `ladder.challenges_of` (Contract §4 + addendum 1 D7). `by` is the
 *  challenger's participant id, `by_alias` the name to show. */
export interface ChallengeItem {
  link: Id
  objection: Id | null
  by: string | null
  by_alias?: string | null
  because: string
  at: number | null
  resolution?: ChallengeResolution
  withdrawn?: ChallengeAnswer | null
  set_aside: ChallengeAnswer | null
}

/** A challenge's resolution, read from the record shape whichever server
 *  produced it (one without `resolution` knows only open / set aside). */
export function resolutionOf(ch: ChallengeItem): ChallengeResolution {
  if (ch.resolution) return ch.resolution
  return ch.set_aside ? 'set_aside' : 'open'
}

/** A participant as the UI names them: the alias with one `@`. */
export function whoOf(x: { by?: string | null; by_alias?: string | null } | null | undefined,
  fallback = 'participant'): string {
  return atAlias(x?.by_alias ?? x?.by ?? null, fallback)
}

export interface DeliveredRecord {
  execution: Id
  participant: string | null
  runtime: string | null
  conversation: Id | null
  conversation_name?: string | null
  turn?: Id | null
  number?: number | null
  at: number | null
  tier: 'governing' | 'adopted' | 'experience' | string
}

export interface CitedByRecord {
  entry: Id
  kind: string
  relation: string
  by: string | null
  conversation?: Id | null
  conversation_name?: string | null
  turn?: Id | null
  number?: number | null
  text?: string
  at: number | null
}

export interface UsageSummary {
  delivered: number
  cited: number
  outcomes_after_delivery: {
    worked: number
    failed: number
    other: number
  }
}

export interface HistoryRecord {
  at: number | null
  act: string
  by: string | null
  because: string | null
}

export interface AdoptionRequestSummary {
  request: Id
  ask: Id | null
  by: string | null
  by_alias?: string | null
  at: number | null
  because: string | null
  scope: string | { whole_brain?: boolean; conversation?: Id; conversation_name?: string; persona?: Id; persona_name?: string } | null
  replaces: { id: Id; text: string; since?: number | null }[]
  /** true once answered: adopted or declined (`closed_by` says which) */
  closed: boolean
  closed_by?: 'adopted' | 'declined' | null
  migrated_by?: Id | null
  migrated_by_alias?: string | null
}

export interface AdoptionDeclineSummary {
  by: string | null
  by_alias?: string | null
  at: number | null
  because: string
  request: Id | null
}

export interface LadderItemDetail extends Omit<LadderItem, 'outcomes' | 'cited_by'> {
  outcomes: OutcomeSummary[] | { count: number; latest: OutcomeSummary[]; all?: OutcomeSummary[] }
  lineage: {
    up: LineageNode[]
    down: LineageNode[]
  }
  challenges: ChallengeItem[]
  delivered: DeliveredRecord[]
  cited_by: CitedByRecord[] | number
  usage: UsageSummary
  history: HistoryRecord[]
  originating: {
    conversation: Id | null
    conversation_name: string | null
    turn: Id | null
    number: number | null
  } | null
  adoption: {
    requests: AdoptionRequestSummary[]
    declines: AdoptionDeclineSummary[]
    adopted: {
      by: string | null
      at: number | null
      because: string | null
      scope?: string | null
    } | null
  }
}

export interface LadderAdoptionRequest {
  request: Id
  ask: Id | null
  entry: Id
  kind: string
  governs: boolean
  /** the Kind owes a falsifier: adopting it needs `payload.falsifier` */
  expects_falsifier?: boolean
  wording: {
    proposed: string
    current: string | null
    proposed_body?: Record<string, unknown>
    current_body?: Record<string, unknown> | null
  }
  replaces: {
    id: Id
    text: string
    since: number | null
  }[]
  scope: {
    whole_brain?: boolean
    conversation?: Id | null
    conversation_name?: string | null
    persona?: Id | null
    persona_name?: string | null
    label?: string
  } | string | null
  limits: string | null
  evidence: (ArtifactCite & {
    id: Id
    kind: string | null
    relation: string
    text: string
    label: string
    cite?: string | null
    conversation?: Id | null
    conversation_name?: string | null
    turn?: Id | null
    number?: number | null
  })[]
  challenges: ChallengeItem[]
  asked_by: RecordedBy
  asked_at: number | null
  because?: string | null
  conversation: Id | null
  conversation_name?: string | null
  turn: Id | null
  number: number | null
}

export interface LadderAdoptionResponse {
  requests: LadderAdoptionRequest[]
}

export interface LadderAdoptedItem extends LadderItem {
  /** participant id; `adopted_by_alias` is the name to show */
  adopted_by: string | null
  adopted_by_alias?: string | null
  adopted_at: number | null
  because: string | null
  scope: {
    whole_brain?: boolean
    conversation?: Id | null
    conversation_name?: string | null
    persona?: Id | null
    persona_name?: string | null
    label?: string
    places?: Id[]
  } | string | null
  replaces?: { id: Id; text: string; since?: number | null }[]
  history: HistoryRecord[]
  challenges: ChallengeItem[]
}

export interface LadderAdoptedResponse {
  items: LadderAdoptedItem[]
}

/** `ladder.trailer` for adopted and experience components; for governing
 *  components the server sends `ladder.why_this_holds` instead
 *  (`why`, `supports`, `basis`, `outcomes`, open `challenges`). Challenges
 *  here are OPEN ones only: delivery quotes nothing withdrawn or set aside. */
export interface LadderTrailer {
  recorded_by?: RecordedBy | null
  basis?: BasisLink[]
  limits?: string | null
  outcomes?: OutcomeSummary[]
  outcomes_total?: number
  challenges?: ChallengeItem[]
  status?: AdoptionStatus | string
  why?: string | null
  supports?: Id[]
  why_holds?: string | null
}

/** One component of `GET /api/context` (Contract §4): the composition's
 *  component as it always was, plus `tier` and, for ladder material, its
 *  `trailer`. Orientation and the request are on no tier (`tier: null`). */
export interface LadderContextComponent {
  source_kind: string
  source_id: Id | null
  scope: string
  text: string
  why: string
  about?: string
  title?: string
  also?: Id[]
  tier: 'governing' | 'adopted' | 'experience' | null
  trailer?: LadderTrailer | null
}

/** What the composition left out, with the reason; a bound's cut also
 *  names its `tier` and `rank`. */
export interface LadderWithheldComponent {
  source_kind: string
  source_id: Id | null
  why: string
  tier?: 'governing' | 'adopted' | 'experience' | string | null
  rank?: number | null
}

export interface LadderContextAnswer {
  scope: 'conversation' | 'brain' | string
  work?: string | null
  components: LadderContextComponent[]
  conflicts?: { about: string; components: Id[] }[]
  withheld: LadderWithheldComponent[]
  payload_chars?: number
}

export interface LearningFilters {
  q: string
  kind: string
  conversation: string
  agent: string
  runtime: string
  since: string
  status: string
  challenged: boolean
}

export const DEFAULT_LEARNING_FILTERS: LearningFilters = {
  q: '',
  kind: '',
  conversation: '',
  agent: '',
  runtime: '',
  since: '',
  status: '',
  challenged: false,
}

/** Contract §6 GovPage tabs order:
 *  Start · Learning · For adoption · Adopted · Instructions · Personas · Rules & decisions · Disciplines · Workflows */
export const FLUID_KNOWN_TABS: readonly [string, string][] = [
  ['start', 'Start'],
  ['learning', 'Learning'],
  ['adoption', 'For adoption'],
  ['adopted', 'Adopted'],
  ['instructions', 'Instructions'],
  ['personas', 'Personas'],
  ['rules', 'Rules & decisions'],
  ['import', 'Import Archive'],
]

export function govTabsOf(kinds: KindAuthoring[]): [string, string][] {
  const tabs: [string, string][] = [...FLUID_KNOWN_TABS]
  const seen = new Set(tabs.map(([s]) => s))
  for (const k of kinds) {
    const s = k.authoring?.section
    if (s && !seen.has(s)) {
      seen.add(s)
      const label = s === 'disciplines' ? 'Disciplines'
        : s === 'workflows' ? 'Workflows'
          : s[0].toUpperCase() + s.slice(1) + 's'
      tabs.push([s, label])
    }
  }
  if (!seen.has('disciplines')) {
    seen.add('disciplines')
    tabs.push(['disciplines', 'Disciplines'])
  }
  if (!seen.has('workflows')) {
    seen.add('workflows')
    tabs.push(['workflows', 'Workflows'])
  }
  return tabs
}

/** Normalize section query parameter (`?gov=1&s=for-adoption` or `adoption`). */
export function normalizeGovSection(s: string): string {
  if (s === 'for-adoption') return 'adoption'
  return s || 'start'
}

/** Build the query string for `GET /api/ladder/items`. */
export function buildLadderItemsUrl(filters: LearningFilters, limit = 200, offset = 0): string {
  const params: string[] = []
  if (filters.kind) params.push(`kind=${encodeURIComponent(filters.kind)}`)
  if (filters.conversation) params.push(`conversation=${encodeURIComponent(filters.conversation)}`)
  if (filters.agent) params.push(`agent=${encodeURIComponent(filters.agent)}`)
  if (filters.runtime) params.push(`runtime=${encodeURIComponent(filters.runtime)}`)
  if (filters.since) {
    const epoch = recencyToEpoch(filters.since)
    if (epoch !== null) params.push(`since=${encodeURIComponent(String(epoch))}`)
  }
  if (filters.status) params.push(`status=${encodeURIComponent(filters.status)}`)
  if (filters.challenged) params.push('challenged=1')
  if (filters.q.trim()) params.push(`q=${encodeURIComponent(filters.q.trim())}`)
  params.push(`limit=${limit}`)
  if (offset > 0) params.push(`offset=${offset}`)
  return `/api/ladder/items?${params.join('&')}`
}

export function recencyToEpoch(since: string, nowSec: number = Math.floor(Date.now() / 1000)): number | null {
  if (!since) return null
  if (/^\d+$/.test(since)) return Number(since)
  if (since === '24h') return nowSec - 86400
  if (since === '7d') return nowSec - 7 * 86400
  if (since === '30d') return nowSec - 30 * 86400
  return null
}

/** Client-side filtering fallback so filters stay responsive against any backend or fixture response. */
export function filterLadderItems(
  items: LadderItem[],
  filters: LearningFilters,
  nowSec: number = Math.floor(Date.now() / 1000),
): LadderItem[] {
  const q = filters.q.trim().toLowerCase()
  const sinceEpoch = recencyToEpoch(filters.since, nowSec)
  return items.filter((item) => {
    if (filters.kind && item.kind !== filters.kind) return false
    if (filters.conversation && item.recorded_by?.conversation !== filters.conversation && item.recorded_by?.conversation_name !== filters.conversation) {
      return false
    }
    if (filters.agent) {
      const ag = filters.agent.toLowerCase().replace(/^@/, '')
      const alias = (item.recorded_by?.alias ?? '').toLowerCase().replace(/^@/, '')
      const part = (item.recorded_by?.participant ?? '').toLowerCase()
      const rt = (item.recorded_by?.runtime ?? '').toLowerCase()
      const persona = (item.recorded_by?.persona ?? '').toLowerCase()
      const personaName = (item.recorded_by?.persona_name ?? '').toLowerCase()
      if (alias !== ag && part !== ag && rt !== ag && persona !== ag && personaName !== ag
        && !`${alias} · ${rt}`.includes(ag)) return false
    }
    if (filters.runtime) {
      const rt = (item.recorded_by?.runtime ?? '').toLowerCase()
      if (rt !== filters.runtime.toLowerCase()) return false
    }
    if (sinceEpoch !== null && item.recorded_at != null && item.recorded_at < sinceEpoch) {
      return false
    }
    if (filters.status) {
      if (filters.status === 'without_basis') {
        if (item.basis && item.basis.length > 0) return false
      } else if (item.status !== filters.status) {
        return false
      }
    }
    if (filters.challenged && !(item.challenged > 0)) return false
    if (q) {
      const hay = [
        item.id,
        item.kind,
        item.text,
        item.limits ?? '',
        item.recorded_by?.alias ?? '',
        item.recorded_by?.runtime ?? '',
        item.recorded_by?.conversation_name ?? '',
        ...item.basis.map((b) => `${b.ref} ${b.label} ${b.cite ?? ''}`),
      ].join(' ').toLowerCase()
      if (!hay.includes(q)) return false
    }
    return true
  })
}

/** Build `/api/context` path including `work` parameter (Contract §4 & §6). */
export function buildLadderContextPath(
  base: { conversation: Id | null; participant: Id | null; persona: Id | null },
  named: Id[],
  work: string,
): string | null {
  const q: string[] = []
  if (base.conversation) q.push('conversation=' + encodeURIComponent(base.conversation))
  if (base.participant) q.push('participant=' + encodeURIComponent(base.participant))
  if (base.persona) q.push('persona=' + encodeURIComponent(base.persona))
  if (!q.length && !work.trim()) return null
  if (named.length) q.push('entries=' + named.map(encodeURIComponent).join(','))
  if (work.trim()) q.push('work=' + encodeURIComponent(work.trim()))
  return '/api/context?' + q.join('&')
}

/** Word-level diff between `current` (replaced wording) and `proposed` wording
 *  for `For adoption` cards (Contract §6: diff when `wording.current` exists). */
export interface WordDiffResult {
  prefix: string
  removed: string
  added: string
  suffix: string
  hasDiff: boolean
}

export function computeWordDiff(current: string | null | undefined, proposed: string): WordDiffResult {
  if (!current || !current.trim() || current.trim() === proposed.trim()) {
    return { prefix: proposed, removed: '', added: '', suffix: '', hasDiff: false }
  }
  const a = current.trim().split(/(\s+)/)
  const b = proposed.trim().split(/(\s+)/)
  let p = 0
  while (p < a.length && p < b.length && a[p] === b[p]) p++
  let s = 0
  while (
    s < a.length - p &&
    s < b.length - p &&
    a[a.length - 1 - s] === b[b.length - 1 - s]
  ) {
    s++
  }
  const prefix = a.slice(0, p).join('')
  const removed = a.slice(p, a.length - s).join('')
  const added = b.slice(p, b.length - s).join('')
  const suffix = a.slice(a.length - s).join('')
  return { prefix, removed, added, suffix, hasDiff: Boolean(removed || added) }
}

/** OpenHint from a LadderItem or LadderItemDetail so clicking any item opens it
 *  in the Stage beside its originating conversation with that Turn highlighted. */
export function hintOfLadderItem(item: {
  id: Id
  kind: string
  text: string
  recorded_by?: RecordedBy | null
  originating?: { conversation: Id | null; conversation_name: string | null; turn: Id | null; number: number | null } | null
}): OpenHint {
  const orig = item.originating?.conversation
    ? item.originating
    : item.recorded_by?.conversation
      ? {
          conversation: item.recorded_by.conversation,
          conversation_name: item.recorded_by.conversation_name,
          turn: item.recorded_by.turn,
          number: item.recorded_by.number,
        }
      : null
  return {
    title: itemTitle(item.kind, item.text),
    source: orig && orig.conversation
      ? {
          conversation: orig.conversation,
          conversationName: orig.conversation_name,
          turn: orig.turn,
          why: 'proposed',
        }
      : null,
  }
}

export function formatStatusLabel(status: AdoptionStatus | string): { label: string; className: string } {
  switch (status) {
    case 'adopted':
      return { label: 'Adopted', className: 'fg-pill adopted' }
    case 'adoption_requested':
      return { label: 'Adoption requested', className: 'fg-pill req' }
    case 'declined':
      return { label: 'Adoption declined', className: 'fg-pill declined' }
    case 'superseded':
      return { label: 'Superseded', className: 'fg-pill declined' }
    case 'ended':
    case 'retired':
      return { label: status === 'retired' ? 'Retired' : 'Ended', className: 'fg-pill declined' }
    case 'recorded':
    default:
      return { label: 'Recorded', className: 'fg-pill recorded' }
  }
}

export function atAlias(alias: string | null | undefined, fallback = 'unattributed'): string {
  const raw = (alias || fallback).trim()
  return raw.startsWith('@') ? raw : '@' + raw
}

export function formatScopeLabel(
  scope: LadderAdoptionRequest['scope'],
  governs?: boolean,
): string {
  if (!scope) return governs ? 'All conversations (Brain-wide)' : 'Brain-wide working position'
  if (typeof scope === 'string') return scope
  if (scope.label) return scope.label
  if (scope.persona_name || scope.persona) return `Persona: ${scope.persona_name ?? scope.persona}`
  if (scope.conversation_name || scope.conversation) return `Conversation: ${scope.conversation_name ?? scope.conversation}`
  if (scope.whole_brain) return governs ? 'All conversations (Brain-wide)' : 'Brain-wide working position'
  return governs ? 'All conversations (Brain-wide)' : 'Brain-wide working position'
}

/* -- what a basis row, an outcome and a challenge say --------------------- */

/** A basis relation as words: the backend's `extracted-from` /
 *  `derived-from`, and an outcome's own grounds `outcome-of` / `in-context`. */
export function basisVerb(rel: string | null | undefined): string {
  switch (rel) {
    case 'extracted-from':
    case 'evidenced_by':
      return 'extracted from'
    case 'derived-from':
    case 'grounded_in':
      return 'derived from'
    case 'outcome-of':
    case 'tests':
      return 'outcome of'
    case 'in-context':
      return 'in context'
    case 'Prompted-by':
      return 'prompted by'
    case 'addresses':
      return 'addresses'
    default:
      return (rel || 'basis').replace(/[_-]/g, ' ').toLowerCase()
  }
}

/** Whether an outcome was tried, said only where the record says. */
export function attemptedLabel(attempted: boolean | null | undefined): string {
  return attempted === true ? ' · attempted' : attempted === false ? ' · not attempted' : ''
}

/** `adm-<hex>`, optionally `@<digest>` and `[a:b]`: a direct citation token. */
const CITE_TOKEN = /^(adm-[0-9a-f]+)(?:@[^[\s]*)?(?:\[(\d+):(\d+)\])?$/i

export const isArtifactRef = (ref: string | null | undefined): boolean => !!ref && /^adm-/i.test(ref)

/** The bare `adm-` of a citation token (or the ref itself). */
export function artifactIdOf(ref: string): Id {
  return CITE_TOKEN.exec(ref.trim())?.[1] ?? ref
}

/** Where held bytes open: the verified route, in a tab of their own. */
export function artifactUrl(ref: string): string {
  return `/api/artifacts/${encodeURIComponent(artifactIdOf(ref))}`
}

export interface CiteView {
  /** the clickable words */
  link: string
  /** the passage to show in quotes -- never a raw `adm-…@digest[a:b]` token */
  quote: string | null
  /** said, not quoted: an entry's citation of bytes with no excerpt */
  note: string | null
  /** clicking opens held bytes (`artifactUrl`), not an entry */
  artifact: boolean
}

/** HOW A CITED ROW IS SHOWN (basis, lineage, For adoption evidence). An
 *  `adm-` row is its excerpt in quotes where the server decoded one, else
 *  "bytes a–b of <artifact name>", or just the name with no range. */
export function citeView(row: ArtifactCite & {
  ref?: Id
  id?: Id
  label?: string | null
  cite?: string | null
}): CiteView {
  const ref = row.ref ?? row.id ?? ''
  const token = (s: string | null | undefined) => (s ? CITE_TOKEN.exec(s.trim()) : null)
  const rangeOf = (t: RegExpExecArray | null): [number, number] | null =>
    t && t[2] != null ? [Number(t[2]), Number(t[3])] : null
  if (isArtifactRef(ref)) {
    const range = row.range ?? rangeOf(token(row.cite) ?? token(ref) ?? token(row.label))
    const name = row.artifact?.name || (!row.label || token(row.label) ? artifactIdOf(ref) : row.label)
    if (row.excerpt) return { link: name, quote: row.excerpt, note: null, artifact: true }
    return { link: range ? `bytes ${range[0]}–${range[1]} of ${name}` : name, quote: null, note: null, artifact: true }
  }
  const t = token(row.cite)
  if (t) {
    const range = rangeOf(t)
    return {
      link: row.label || ref,
      quote: row.excerpt ?? null,
      note: row.excerpt ? null : `cites ${range ? `bytes ${range[0]}–${range[1]} of ` : ''}${row.artifact?.name || t[1]}`,
      artifact: false,
    }
  }
  return { link: row.label || ref, quote: row.cite || null, note: null, artifact: false }
}

/** One line for a Learning row's basis: grouped by relation, a single row by
 *  its label, several by how many of each Kind. */
export function summarizeBasis(basis: BasisLink[] | null | undefined): string {
  if (!basis || basis.length === 0) return 'no basis recorded'
  const groups = new Map<string, BasisLink[]>()
  for (const b of basis) {
    const v = basisVerb(b.relation)
    groups.set(v, [...(groups.get(v) ?? []), b])
  }
  const kindOf = (b: BasisLink) => isArtifactRef(b.ref) ? 'artifact'
    : b.kind === 'contribution' ? 'turn' : b.kind || 'source'
  return [...groups.entries()].map(([verb, rows]) => {
    if (rows.length === 1) return `${verb} ${citeView(rows[0]).link}`
    const byKind: Record<string, number> = {}
    for (const b of rows) byKind[kindOf(b)] = (byKind[kindOf(b)] ?? 0) + 1
    return `${verb} ${Object.entries(byKind).map(([k, n]) => `${n} ${n === 1 ? k : k + 's'}`).join(', ')}`
  }).join(' · ')
}

/** Evidence words beside its label, unless they only repeat it. */
export function evidenceText(ev: { text?: string | null; label?: string | null }): string | null {
  const text = (ev.text ?? '').trim()
  const label = (ev.label ?? '').trim()
  if (!text) return null
  if (label && (text === label || label.startsWith(text) || text.startsWith(label))) return null
  return text
}

/** A challenge answered, as one muted line: who answered it and why. */
export function challengeResolvedLine(ch: ChallengeItem): string | null {
  const res = resolutionOf(ch)
  if (res === 'open') return null
  const ans = res === 'withdrawn' ? ch.withdrawn : ch.set_aside
  const verb = res === 'withdrawn' ? 'withdrawn' : 'set aside'
  const who = ans && (ans.by || ans.by_alias) ? ` by ${whoOf(ans)}` : ''
  return `${verb}${who}${ans?.because ? `: ${ans.because}` : ''}`
}

/** Open challenges, and the answered ones beside them (kept, never hidden). */
export function splitChallenges(chs: ChallengeItem[] | null | undefined): { open: ChallengeItem[]; resolved: ChallengeItem[] } {
  const all = chs ?? []
  return {
    open: all.filter((c) => resolutionOf(c) === 'open'),
    resolved: all.filter((c) => resolutionOf(c) !== 'open'),
  }
}

/** SET ASIDE IS THE OWNER'S ACT, on somebody else's open challenge; Withdraw
 *  is the challenger's own. Neither is offered on an answered challenge. */
export function challengeActsFor(ch: ChallengeItem, viewer: Id | null, owner: Id | null): { withdraw: boolean; setAside: boolean } {
  if (resolutionOf(ch) !== 'open' || !viewer) return { withdraw: false, setAside: false }
  const mine = ch.by === viewer
  return { withdraw: mine, setAside: !mine && !!owner && viewer === owner }
}

/** WHO ASKED, as a card says it: the original proposer and, where the
 *  request was migrated, who moved it. */
export function askedByOf(x: {
  alias?: string | null
  by?: string | null
  by_alias?: string | null
  migrated_by?: Id | null
  migrated_by_alias?: string | null
} | null | undefined, fallback = 'Agent'): { who: string; migratedBy: string | null } {
  const who = atAlias(x?.alias ?? x?.by_alias ?? x?.by ?? null, fallback)
  const m = x?.migrated_by_alias ?? x?.migrated_by ?? null
  return { who, migratedBy: m ? atAlias(m) : null }
}

/** THE AGENT FILTER'S CHOICES: aliases, runtimes and persona names that occur
 *  in the UNFILTERED items, so each is one the server's filter can match. */
export function agentOptionsOf(items: LadderItem[] | null | undefined, selected = ''): string[] {
  const seen = new Map<string, string>()
  const add = (v: string | null | undefined) => {
    const t = (v ?? '').trim()
    const key = t.toLowerCase().replace(/^@/, '')
    if (key && !seen.has(key)) seen.set(key, t)
  }
  for (const it of items ?? []) {
    add(it.recorded_by?.alias)
    add(it.recorded_by?.runtime)
    add(it.recorded_by?.persona_name)
  }
  add(selected)
  return [...seen.values()]
}

/** LADDER MATERIAL is everything except what both stands and governs
 *  (adopted governing material), which keeps its existing affordances. */
export function isLadderMaterial(item: { governs: boolean; status: AdoptionStatus | string } | null | undefined): boolean {
  return !!item && !(item.governs && item.status === 'adopted')
}

/** THE ADOPT ACT'S PAYLOAD. Edited wording replaces only the principal field
 *  (`text`) of the proposed body; every other field goes as proposed, and no
 *  field the Kind does not declare (never `summary`): the server holds body
 *  keys to the Kind's declared fields. A falsifier rides as `falsifier`. */
export function buildAdoptPayload(req: LadderAdoptionRequest, opts: {
  me: Id
  because: string
  editedText?: string | null
  scope?: string | null
  falsifier?: string | null
}): Record<string, unknown> {
  const payload: Record<string, unknown> = { attributed_to: opts.me, because: opts.because }
  const edited = opts.editedText?.trim() || null
  if (edited && edited !== req.wording.proposed.trim()) {
    const proposed = req.wording.proposed_body ?? null
    if (proposed) {
      const key = 'text' in proposed ? 'text'
        : Object.keys(proposed).find((k) => typeof proposed[k] === 'string'
          && String(proposed[k]).trim() === req.wording.proposed.trim()) ?? 'text'
      payload.body = { ...proposed, [key]: edited }
    } else {
      payload.body = { text: edited }
    }
  }
  if (opts.scope) {
    payload.scope = opts.scope === 'whole_brain' ? { whole_brain: true }
      : opts.scope === 'when_named' ? { whole_brain: false }
        : { conversation: opts.scope }
  } else if (req.scope) {
    payload.scope = req.scope
  }
  if (req.replaces && req.replaces.length > 0) payload.replaces = req.replaces.map((r) => r.id)
  const falsifier = opts.falsifier?.trim()
  if (falsifier) payload.falsifier = falsifier
  return payload
}

/** WHAT THE STAGE HOLDS ONCE GOVERNANCE IS OPENED. Naming a section asks for
 *  that section: the item open on Stage closes, so the tab renders, and the
 *  adoption card named (if any) is the one focused. Opened with no section --
 *  an item opening on Stage -- leaves both as they are. */
export function stageAfterOpenGov(prev: { focus: Id | null; card: Id | null },
  section?: string, card?: Id | null): { focus: Id | null; card: Id | null } {
  if (!section) return prev
  return { focus: null, card: card ?? null }
}
