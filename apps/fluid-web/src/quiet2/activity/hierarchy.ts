/* WHO IS DOING WHAT, AND UNDER WHOM (owner, 2026-11-16: execution visibility).
 *
 * Two different relations, never drawn as one:
 *
 * - A MENTIS DELEGATION is an independent execution: its own run, runtime,
 *   authority and consent, dispatched by Mentis for somebody's `delegate`. The
 *   record links it to the work it came from (`delegated_from`, read by the
 *   server from the `work-delegated` act). `orderWork` puts such a run under
 *   the open run it came from, as its own row with its own controls.
 *
 * - A RUNTIME-NATIVE WORKER (a Claude sub-agent) lives inside one run. It is a
 *   tool call of that run, under that run's identity and consent, and is not a
 *   participant, a Work item or a holder of authority. MARS reports which of
 *   the run's tool calls and permission requests belong to it (`parent`) and
 *   what the runtime said of it (`worker`). `feedTree` nests them.
 *
 * Everything here is a view over what the server sent. Nothing is inferred: a
 * runtime that exposes no workers yields a flat list, and a fact the runtime
 * did not report is left out, never filled in. Pure functions, no React. */
import type { FeedEntry } from '../../fluid/runs/feed'

/** What the runtime reported of a native worker (`mars/tool.worker`). */
export interface WorkerFacts {
  description?: string
  requested_model?: string
  agent_type?: string
  agent_id?: string
  model?: string
  elapsed_s?: number
  duration_ms?: number
  tool_calls?: number
  /** the size its context reached, NOT what it consumed */
  context_tokens?: number
  /** a runtime that reports only events of a worker says which this is */
  event?: string
  /** how many workers one report started, where more than one */
  count?: number
}

/** A run's native worker as `/api/activity` summarises it for the run's row. */
export interface WorkerSummary extends WorkerFacts {
  id: string
  title?: string | null
  status?: string | null
  started_at?: number | null
  at?: number | null
  calls_seen?: number
  now?: string
}

/** Whose Mentis delegation a run is, as the record says. */
export interface DelegatedFrom { by?: string | null; by_name?: string | null; expectation?: string | null; at?: number | null; run?: string | null }

export interface FeedNode {
  entry: FeedEntry
  /** its native worker's own tool calls and permission requests, oldest first */
  children: FeedNode[]
  /** it names a parent the feed no longer holds (a long run's oldest entries go) */
  orphan: boolean
}

const OPEN = new Set([undefined, null, 'pending', 'in_progress'])

/** The feed as a tree: an entry that names a parent goes under it. Order is
 *  the feed's own (by `seq`), so a parent that changed after its children
 *  still lists them oldest first. */
export function feedTree(entries: FeedEntry[]): FeedNode[] {
  const nodes = new Map<string, FeedNode>(entries.map((e) => [e.id, { entry: e, children: [], orphan: false }]))
  const top: FeedNode[] = []
  for (const e of entries) {
    const node = nodes.get(e.id)!
    const parent = e.parent && e.parent !== e.id ? nodes.get(e.parent) : undefined
    if (parent && !under(nodes, parent, e.id)) parent.children.push(node)
    else { node.orphan = !!e.parent; top.push(node) }
  }
  const first = (n: FeedNode) => n.entry.started_at ?? n.entry.at
  for (const n of nodes.values()) n.children.sort((a, b) => first(a) - first(b) || a.entry.seq - b.entry.seq)
  return top
}

/** Whether `id` is `node` or one of its ancestors: a cycle is never drawn. */
function under(nodes: Map<string, FeedNode>, node: FeedNode, id: string): boolean {
  let at: FeedNode | undefined = node
  for (let i = 0; at && i < 32; i++) {
    if (at.entry.id === id) return true
    at = at.entry.parent ? nodes.get(at.entry.parent) : undefined
  }
  return false
}

/** How the run this feed belongs to ended, for calls it left open. */
export interface RunEnd { ended: boolean; cancelled: boolean }

/** A tool call's state in words. The runtime's own status where it gave one;
 *  a call left open by a run that has ended is said as that, never as still
 *  pending: a cancelled or killed turn reports no end for what it was doing. */
export function callState(status: string | null | undefined, end: RunEnd, openAtEnd = false): string {
  if (status === 'completed') return 'completed'
  if (status === 'failed') return 'failed'
  if ((end.ended || openAtEnd) && OPEN.has(status as undefined)) return end.cancelled ? 'cancelled with its run' : 'no end reported'
  return status === 'in_progress' ? 'running' : 'pending'
}

/** The runtime reported only that this worker was launched, and never
 *  reports more: what it is doing now is not known. */
export const launchOnly = (w: WorkerFacts | undefined | null) => w?.event === 'launched'

/** 1234 -> "1.2k", 1000000 -> "1M". */
export function tokens(n: number): string {
  if (!Number.isFinite(n)) return String(n)
  const abs = Math.abs(n)
  const short = (v: number, unit: string) => `${v >= 100 ? Math.round(v) : Math.round(v * 10) / 10}${unit}`
  if (abs >= 1e6) return short(n / 1e6, 'M')
  if (abs >= 1e3) return short(n / 1e3, 'k')
  return String(Math.round(n))
}

const seconds = (s: number) => (s >= 90 ? `${Math.round(s / 60)} min` : `${Math.round(s)} s`)

/** A native worker in one line, from what the runtime reported of it. The
 *  words "native sub-agent" are the relation: inside its run, not a
 *  delegation. */
export function workerLine(title: string | null | undefined, w: WorkerFacts, state: string, seen?: number): string {
  const model = w.model ?? (w.requested_model ? `${w.requested_model} asked for` : null)
  const time = w.duration_ms != null ? `took ${seconds(w.duration_ms / 1000)}`
    : w.elapsed_s != null && (state === 'running' || state === 'pending') ? `${seconds(w.elapsed_s)} so far` : null
  const calls = w.tool_calls != null ? `${w.tool_calls} tool ${w.tool_calls === 1 ? 'call' : 'calls'}`
    : seen ? `${seen} tool ${seen === 1 ? 'call' : 'calls'} seen` : null
  const context = w.context_tokens != null ? `context reached ${tokens(w.context_tokens)}` : null
  /* A RUNTIME THAT ONLY SAYS A WORKER WAS LAUNCHED (Antigravity): nothing
     after the launch is reported, so it is never said as running, pending,
     cancelled or lost -- only as launched. */
  const said = launchOnly(w) && state !== 'completed' && state !== 'failed' ? 'launched · its progress and end are not reported by this runtime' : state
  const what = w.count && w.count > 1 ? `${w.count} native sub-agents` : 'Native sub-agent'
  return [what, title || w.description || null, model, said, time, calls, context].filter(Boolean).join(' · ')
}

interface Counts { input?: number; output?: number; cached_read?: number; cached_write?: number; reasoning?: number; total?: number }
/** `mars/usage` as the server passes it on. */
export interface TurnUsage {
  tokens?: Counts
  tokens_cover?: string
  by_model?: { model: string; tokens: Counts }[]
  cost?: { amount: number; currency?: string }
  context?: { used: number; size?: number }
}

const money = (amount: number, currency?: string) =>
  currency === 'USD' || !currency ? `$${amount < 0.1 ? amount.toFixed(3) : amount.toFixed(2)}` : `${amount.toFixed(2)} ${currency}`

/** What the run used, each figure named for what it is. The context reading
 *  says how full the window is; only the runtime's own turn report is called
 *  consumption. A figure nobody reported is not listed. */
export function usageLines(entries: FeedEntry[]): string[] {
  const out: string[] = []
  const usage = entries.find((e) => e.kind === 'usage')?.usage
  const turn = entries.find((e) => e.kind === 'turn_usage')?.turn as TurnUsage | undefined
  const used = turn?.context?.used ?? (typeof usage?.used === 'number' ? usage.used : undefined)
  const size = turn?.context?.size ?? (typeof usage?.size === 'number' ? usage.size : undefined)
  if (used != null) out.push(`Context window: ${tokens(used)}${size ? ` of ${tokens(size)}` : ''} full (its size now, not what was spent)`)
  if (turn?.tokens?.total != null) {
    const cover = turn.tokens_cover === 'main-loop' ? ' in its main conversation (native sub-agents not counted)' : ''
    out.push(`Tokens this turn, as the runtime reported: ${tokens(turn.tokens.total)}${cover}`)
  }
  if (turn?.by_model?.length) {
    const rows = turn.by_model.filter((r) => r.tokens?.total != null).map((r) => `${r.model} ${tokens(r.tokens.total!)}`)
    if (rows.length) out.push(`By model, native sub-agents included: ${rows.join(' · ')}`)
  }
  const amount = turn?.cost?.amount ?? (typeof usage?.cost_amount === 'number' ? usage.cost_amount : undefined)
  const currency = turn?.cost?.currency ?? (typeof usage?.cost_currency === 'string' ? usage.cost_currency : undefined)
  if (amount != null) out.push(`Cost, the runtime's own figure: ${money(amount, currency)}`)
  return out
}

/** What a run's END ACT recorded, independently of memory residency
 *  (`feed.recorded`): its tool calls with their place in the run, and what it
 *  used. */
export interface Recorded {
  run?: string
  end?: string
  act?: string
  terminal?: string | null
  because?: string | null
  error?: string | null
  error_kind?: string | null
  notes?: string[]
  /** C1a WorkOutcome collector contract (work-outcome-reported-v1). */
  collected_text?: string | null
  collected_text_chars?: number | null
  collected_text_format?: string
  returned_artifacts?: string[]
  reply_turn?: string | null
  response_owner?: string | null
  request?: string | null
  request_turn?: string | null
  timed_out?: boolean
  runtime_evidence?: { stop_reason?: string | null; error_kind?: string | null }
  outcome_unclaimed?: { kind?: string; why?: string }
  availability?: Record<string, boolean>
  tool_calls?: { id?: string; title?: string; kind?: string; status?: string; parent?: string; worker?: WorkerFacts; open_at_end?: boolean }[]
  tokens?: Counts
  tokens_cover?: string
  tokens_by_model?: { model: string; tokens: Counts }[]
  cost?: { amount: number; currency?: string }
  context_used?: number
  context_size?: number
  ended_at?: number
  stop_reason?: string | null
}

/** The recorded end as feed entries, so one drawing serves a live run and an
 *  ended one. Order is the record's. */
export function recordedEntries(r: Recorded): FeedEntry[] {
  const at = r.ended_at ?? 0
  const out: FeedEntry[] = (r.tool_calls ?? []).filter((c) => c.id).map((c, i) => ({
    id: 'tool-' + c.id, seq: i + 1, kind: 'tool' as const, at, started_at: i, title: c.title, tool_kind: c.kind,
    status: c.status as FeedEntry['status'], open_at_end: c.open_at_end,
    ...(c.parent ? { parent: 'tool-' + c.parent } : {}), ...(c.worker ? { worker: c.worker } : {}),
  }))
  const n = out.length
  if (r.context_used != null) out.push({ id: 'usage', seq: n + 1, kind: 'usage', at, usage: { used: r.context_used, ...(r.context_size != null ? { size: r.context_size } : {}) } })
  if (r.tokens || r.tokens_by_model || r.cost) {
    out.push({ id: 'turn-usage', seq: n + 2, kind: 'turn_usage', at,
      turn: { tokens: r.tokens, tokens_cover: r.tokens_cover, by_model: r.tokens_by_model, cost: r.cost } })
  }
  return out
}

/** Open runs in the order they are drawn: a Mentis delegation whose
 *  originating run is open follows that run, one level in; everything else
 *  keeps the order it came in. `depth` is how many delegations deep; a run
 *  whose origin is not open stays at the top and says who delegated it. */
export function orderWork<T extends { key: string; run: { run: string; delegated_from?: DelegatedFrom | null } | null }>(entries: T[]): { e: T; depth: number }[] {
  const byRun = new Map(entries.filter((e) => e.run).map((e) => [e.run!.run, e]))
  const kids = new Map<string, T[]>()
  const top: T[] = []
  for (const e of entries) {
    const origin = e.run?.delegated_from?.run
    if (origin && origin !== e.run!.run && byRun.has(origin)) kids.set(origin, [...(kids.get(origin) ?? []), e])
    else top.push(e)
  }
  const out: { e: T; depth: number }[] = []
  const seen = new Set<string>()
  const walk = (e: T, depth: number) => {
    if (seen.has(e.key)) return
    seen.add(e.key)
    out.push({ e, depth })
    for (const k of e.run ? kids.get(e.run.run) ?? [] : []) walk(k, Math.min(depth + 1, 3))
  }
  for (const e of top) walk(e, 0)
  for (const e of entries) walk(e, 0)   // a cycle in the record leaves nobody out
  return out
}

/** WHAT EACH RUNTIME EXPOSES OF ITS NATIVE WORKERS, measured through MARS on
 *  2026-11-16 (docs/execution-visibility.md), as the sentence a run's activity
 *  ends with. null: nothing is missing that needs saying (Claude Code reports
 *  its workers, their tool calls and what each reported). Every other runtime
 *  says its limit rather than leaving a reader to assume the same detail. */
export function nativeWorkerLimit(runtime: string | null | undefined): string | null {
  const r = (runtime ?? '').toLowerCase()
  if (!r || r === 'claude') return null
  if (r === 'codex') return 'Codex reports only that a native sub-agent started and completed: its own tool calls, model and usage are not exposed.'
  if (r === 'antigravity' || r === 'agy') return 'Antigravity reports only that a native sub-agent was started: what it does, when it ends and what it uses are not exposed, and the usage shown is the parent conversation only.'
  if (r === 'local') return 'The local worker has no native sub-agents: everything it does is listed here.'
  return `${runtime} reports only this run's own activity: any workers it runs inside the run are not exposed.`
}

/** Whether MARS reports this runtime's native workers with their activity. */
export const reportsNativeWorkers = (runtime: string | null | undefined) => runtime === 'claude'
