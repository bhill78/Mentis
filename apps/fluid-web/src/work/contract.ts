/* ------------------------------------------------------------------------ *
 * WORK OVERVIEW CONTRACT (v1). Shared by the API, the Daily Briefing Ledger
 * and the conversation work pill. Added VERBATIM by each track; change it
 * only through the contract owner, for all of them at once.
 *
 * A READ-ONLY PROJECTION of records Mentis already holds: trunk
 * expectations, their delegations, runs and decisions. Nothing here is
 * stored. Every word is the server's; the UI draws it and decides nothing.
 *
 * WORK COMPLETION IS NOT EXECUTION COMPLETION. `objective_met` is true only
 * when the work itself was claimed met. Finished executions never make it so.
 * UNKNOWN IS SAID: a field the server could not determine is null with a
 * `why`, never a guess.
 * ------------------------------------------------------------------------ */
import type { Id, WorkflowProgress } from '../api'

export type Source = 'recorded' | 'computed' | 'runtime' | 'unknown'

/** Which Ledger group a work item belongs to. Exclusive: most urgent wins.
 *  `returned` (its runs ended today, nobody claimed the objective met; the
 *  Ledger's "Ended · not marked complete" line) is
 *  only ever used by a read scoped with `active_since`: today's Ledger. An
 *  unscoped read -- the conversation pill's -- never returns it. */
export type WorkGroup = 'needs_you' | 'in_flight' | 'completed' | 'returned' | 'unknown'

/** WHERE THE WORK STANDS, derived by the server from the commits, reviews
 *  and runs under it and from git (`mentis/operational/stage.py`). First
 *  match wins in this order. An execution ending is not completion: work
 *  whose runs ended with commits nobody reviewed is `awaiting_review`. */
export type WorkStage = 'blocked' | 'awaiting_owner' | 'building' | 'awaiting_review'
  | 'parked' | 'ready_to_deploy' | 'deployed' | 'ended' | 'not_started' | 'unknown'

/** How a stage was established: from the record and git, from a review's
 *  own words (no structured verdict was recorded), or from a recorded
 *  `review-verdict` act. */
export type StageSource = 'computed' | 'computed-from-prose' | 'recorded' | 'unknown'

export interface StageEvidence {
  /** The newest commit of the work (on the trunk, else under it). */
  head: string | null
  /** Whether the head is in the integration target (e.g. main). */
  merged: boolean | null
  /** The commit this server runs, as /api/server reports it. */
  deployed_commit: string | null
  review: { expectation: Id | null; verdict: 'pass' | 'block' | 'incomplete' | null;
            source: StageSource | null; commit?: string | null } | null
  blocked: { why: string; act: Id | null } | null
  target?: string
  why?: string | null
}

/** One execution's state in words. There is no queue in Mark IV, so there
 *  is no "queued": a run that was asked for and never launched is not_started. */
export type ExecutionState = 'finished' | 'failed' | 'running' | 'not_started' | 'unknown'

export interface TurnLink {
  turn: Id
  /** Turn number within its conversation; null if it could not be read. */
  number: number | null
  conversation: Id
  conversation_name: string | null
}

export interface WorkItem {
  /** The trunk expectation (opr-…). Stable key. */
  expectation: Id
  /** First line of the originating Turn, plain text, ≤ 90 chars; null if unknown. */
  title: string | null
  group: WorkGroup
  /** Short status in words, e.g. "In flight · 1 decision for you". Never empty. */
  status_words: string
  /** The trunk_status state value, passed through for tooltips and tests. */
  state: string
  state_source: Source
  /** True only when the objective itself was claimed met. null = unknown. */
  objective_met: boolean | null
  /** When it was claimed met (ISO), if it was. */
  met_at: string | null
  /** Unanswered decisions under this work that the viewer owes. */
  decisions_open: number
  /** Execution counts: words and counts only, never drawn as bars. */
  executions: Record<ExecutionState, number> & { total: number }
  /** Display names of contributing agents, carrier first. */
  agents: string[]
  origin: TurnLink
  /** Replies to the originating Turn; null if unknown. */
  replies: number | null
  /** ISO time of the newest act under this work. */
  last_activity_at: string | null
  /** Why something above is unknown, if anything is. */
  why_unknown: string | null
  /** Where the work stands, and in words: "Building", "Awaiting review",
   *  "Repaired · re-review needed", "Needs your decision", "Ready to deploy
   *  · merged, not deployed", "Deployed", "Blocked: <why>", "Answered ·
   *  nothing committed". Optional only so older servers and fixtures still
   *  type; this server always sends them. */
  stage?: WorkStage
  stage_words?: string
  stage_source?: StageSource
  stage_evidence?: StageEvidence
}

export interface WorkOverview {
  viewer: Id | null
  /** Exclusive counts over the returned set: all = sum of the groups. */
  counts: Record<WorkGroup, number> & { all: number }
  /** Items ordered: needs_you, in_flight, completed, returned, unknown; newest first within each group. */
  items: WorkItem[]
  /** Counts by stage over the same items as `counts` (before `limit`). */
  stage_counts?: Record<WorkStage, number>
  /** Items not returned because of `limit`, per group. */
  omitted: Record<WorkGroup, number>
  /** True when nobody is looking (no viewer named, no owner recorded): Needs
   *  you is then UNKNOWN, never 0, and `needs_you_why` says why. Optional
   *  only so older fixtures still type; the server always sends both. */
  needs_you_unknown?: boolean
  needs_you_why?: string | null
  /** Set on a read scoped with `active_since`: the moment, and how many
   *  objectives were left out (not moving, nothing since, nothing for you).
   *  `left_out_by` is the same count by reason and sums to `left_out`:
   *  not started (nothing has run for it, and it does not need you), inactive
   *  (nothing under it since then), completed before then, and unassigned
   *  discovered work. In flight is moving work only (owner decision #548),
   *  so not-started work is counted here, never In flight. Optional so older
   *  servers and fixtures still type. */
  scope?: {
    active_since: string; left_out: number; why: string
    left_out_by?: { not_started: number; inactive: number;
                    completed_earlier: number; discovered_unassigned: number }
  } | null
  /** Why the runtime could not be observed (running then comes from the record only). */
  runtime_why_not: string | null
}

export interface Execution {
  /** The expectation this run worked on (trunk or a delegated child). */
  expectation: Id
  execution: Id | null
  runtime: string | null
  /** What the run was for, one line, e.g. "Review combined release". */
  task: string | null
  state: ExecutionState
  /** One line on the outcome or why, e.g. "PASS, minor non-blocking findings". */
  summary: string | null
  started_at: string | null
  ended_at: string | null
  /** Recorded exit code for an ended run, if any. */
  exit_code: number | null
  origin: TurnLink | null
}

export interface Agent {
  participant: Id
  alias: string | null
  /** Overall word for this agent under this work, e.g. "finished", "running · 1 not started". */
  state_words: string
  executions: Execution[]
}

export interface Decision {
  /** The decision expectation (opr-…). */
  expectation: Id
  /** The question as asked. */
  question: string | null
  options: string[]
  answered: boolean
  owed_by: Id | null
  owed_by_alias: string | null
  /** The Turn that asks it; the UI opens this to answer. */
  origin: TurnLink | null
}

export interface WorkDetail extends WorkItem {
  /** Drawer heading, from the work's state: "OBJECTIVE MET", "STOPPED — NOT COMPLETE",
   *  "ENDED — NOT MARKED COMPLETE", "NOT STARTED — UNASSIGNED",
   *  "WORK IN FLIGHT — NOT COMPLETE" or "WORK STATE UNKNOWN". */
  heading: string
  /** The recorded `expects` of the request; null + why when it did not say. */
  completes_when: string | null
  completes_when_why: string | null
  /** e.g. "3 of 6 finished · 1 failed · 1 running · 1 not started". */
  executions_words: string
  agents_detail: Agent[]
  decisions: Decision[]
  /** Latest returned result for this work, one or two sentences; null if none. */
  outcome: string | null
  started_at: string | null
  /** Which Workflow governs this work, how it came to, its activity progress
   *  and every change with its reason. Absent from an older server. */
  workflow?: WorkflowView
}

export interface WorkflowRef { entry: Id; name: string | null }

/** One entry in a request's Workflow history, oldest first: how it was asked,
 *  then each change (`change_workflow` or the owner's Fluid command). */
export type WorkflowEvent =
  | { kind: 'asked'; at: number | null; by: Id | null; by_alias: string | null
      workflows: WorkflowRef[]
      /** "named" (asked with it), "continued" (carried from the request it continues), or null */
      from: string | null; continues: Id | null }
  | { kind: 'changed'; act: Id; at: number; by: Id; by_alias: string | null
      role: 'owner' | 'carrier' | string; because: string | null
      from: WorkflowRef[]; to: WorkflowRef[]
      evidence: { ref: Id; turn?: Id | null; number?: number | null; act?: string | null; conversation?: Id | null }[]
      runtime: string | null; execution: Id | null }

export interface WorkflowView {
  current: WorkflowRef[]
  /** named | continued | changed | placed | none | unknown */
  origin: string
  history: WorkflowEvent[]
  /** The server-computed activity progress (`trunk_status.workflow`). */
  progress: WorkflowProgress[]
  progress_source: string | null
  progress_why?: string | null
  why_unknown?: string
}
