/* PACKAGE D owns this module: what is running here, and what each run is
   on. Mounted in B's margin, under the Activity reading.

   TWO GROUPS, NEITHER DROPPED. `workingIn(all, here)` keeps the
   `working_on.conversation` fallback a plain `a.conversation === conversation`
   filter drops (ent-dffb798c7e65's `/api/activity` entries do not all carry
   their own `conversation`); what is left over is broader Mentis activity,
   shown under its own heading rather than discarded. `live()` -- the same
   module's -- narrows each entry to one row per run, which is what lets two
   runs of one participant show as two rows rather than folded into one.

   EACH ROW READS ITS OWN RUN. `/api/working`'s matching row carries the
   runtime and the requested model; `/api/runs/<run>/consent` the permission
   mode in force and the operations answered so far; `/api/runs/<run>/feed`
   -- the same reader the Fluid run panel follows -- the current activity's
   detail, the usage keys verbatim, and Stop. Nothing here duplicates that
   reading machinery; it is imported, not reinvented. */
import { useEffect, useState } from 'react'
import { read, useApi, type Activity, type ActivityEntry, type Id } from '../../api'
import { live, workingIn, type Activity as LiveRow } from '../../fluid/identity/activity'
import { useRunFeed, useStop, waitingPermissions, type FeedEntry } from '../../fluid/runs/feed'
import type { ConsentRead } from '../../fluid/runs/consent'
import { runnable, useExecution, type ExecutionInfo, type RunRow, type Working } from '../../composer/execution'
import { href } from '../model'
import { ReadState } from '../read'
import './activity.css'

/** `/api/activity`'s own `ActivityRun.working_on.since` is `number | null`
 *  (an older record may not have recorded when); Fluid's reader never met
 *  that case and declared it a plain `number`. A missing `since` here is
 *  not read as a false zero -- nothing here shows it -- so folding null to
 *  0 loses nothing this module draws. */
function toLiveRows(all: ActivityEntry[] | null): LiveRow[] {
  return (all ?? []).map((a) => ({
    ...a,
    runs: a.runs?.map((r) => ({
      ...r,
      working_on: r.working_on ? { ...r.working_on, since: r.working_on.since ?? 0 } : null,
    })),
  }))
}

const isHere = (conversation: Id) => (a: LiveRow) =>
  a.conversation === conversation || (!a.conversation && a.working_on?.conversation === conversation)

/** CONVERSATION ACTIVITY, TOLD APART FROM BROADER MENTIS ACTIVITY. `here` is
 *  `workingIn(all, conversation)` -- the fallback kept; `elsewhere` is every
 *  other live run, shown rather than dropped. Exported bare of hooks so the
 *  distinction can be asserted without a browser. */
export function groupActivity(all: ActivityEntry[] | null, conversation: Id): { here: LiveRow[]; elsewhere: LiveRow[] } {
  const rows = toLiveRows(all)
  return { here: workingIn(rows, conversation), elsewhere: live(rows).filter((a) => !isHere(conversation)(a)) }
}

/** Reread every 2s: the permission mode and the operations answered so far
 *  change on the server while the rail stays open, not just when a run
 *  starts. */
const CONSENT_EVERY_MS = 2000

function useConsentRead(run: Id | null): ConsentRead | null {
  const [got, setGot] = useState<ConsentRead | null>(null)
  useEffect(() => {
    setGot(null)
    if (!run) return
    let live_ = true
    const reread = () => read<ConsentRead>(`/api/runs/${encodeURIComponent(run)}/consent`)
      .then((r) => { if (live_) setGot(r) }).catch(() => {})
    reread()
    const timer = window.setInterval(reread, CONSENT_EVERY_MS)
    return () => { live_ = false; window.clearInterval(timer) }
  }, [run])
  return got
}

/** The model this run asked for, matched against what this machine's
 *  runtimes actually catalogue -- `context_window` travels only there. */
export function contextWindowFor(exec: ExecutionInfo | null, modelRequested: string | null): number | null {
  if (!modelRequested) return null
  for (const r of runnable(exec)) {
    for (const m of r.models) {
      if (m.slug === modelRequested || m.aliases?.includes(modelRequested)) return m.context_window
    }
  }
  return null
}

/** `entries` is `useRunFeed`'s accumulated merge, not a poll's own delta --
 *  a later `usage` entry reports only what changed, so its fields are
 *  folded onto the earlier ones rather than replacing them. Reading the
 *  delta's own `kind === 'usage'` entry instead is what made the figures
 *  vanish after the next poll. */
function mergedUsage(entries: FeedEntry[]): Record<string, number | string> | null {
  let merged: Record<string, number | string> | null = null
  for (const e of entries) {
    if (e.kind === 'usage' && e.usage) merged = { ...(merged ?? {}), ...e.usage }
  }
  return merged
}

/** Labelled, side by side, NEVER a ratio: a declared window and a consumed
 *  count answer different questions, and blending them would invent one
 *  neither reported. */
function UsageAndWindow({ entries, contextWindow }: { entries: FeedEntry[]; contextWindow: number | null }) {
  const usage = mergedUsage(entries)
  if (!usage) return null
  const outputTokens = typeof usage.output_tokens === 'number' ? usage.output_tokens : null
  return <p className="qc-run-usage">
    {contextWindow != null && <span>context window {contextWindow.toLocaleString()}</span>}
    {outputTokens != null && <span>output_tokens {outputTokens.toLocaleString()}</span>}
    {Object.entries(usage).filter(([k]) => k !== 'output_tokens').map(([k, v]) => <span key={k}>{k} {String(v)}</span>)}
  </p>
}

/** Exported for `quiet_activity_unit`'s rendered-markup checks (the narrow
 *  name/activity collision and the disclosure caret), not for another
 *  module to mount -- `Group` is still the only caller inside the app. */
export function RunRowView({ a, run, working, contextWindow, conversation, topic }: {
  a: LiveRow; run: Id; working: RunRow | undefined; contextWindow: number | null
  conversation: Id; topic: Id | null
}) {
  const { feed, entries } = useRunFeed(run)
  const consent = useConsentRead(run)
  const { state, why, stop } = useStop(run)
  const [open, setOpen] = useState(false)
  const r = a.runs?.[0]
  const stopping = !!r?.stopping || state === 'asking' || state === 'asked'
  /* The server's own `stopping` flag says Stop was already asked -- told
   * apart from `refused`, the one local state it cannot report, so a run
   * stopping before this row ever mounted still reads as "Stopping…"
   * rather than an inert "Stop". */
  const stopWords = state === 'refused' ? `Could not stop${why ? ': ' + why : ''}`
    : stopping ? 'Stopping…' : 'Stop'
  const permissions = waitingPermissions(feed)
  const operations = consent?.operations ?? []
  const workingOn = a.working_on
  const detailId = `qc-run-detail-${run}`
  /* ACCORDION: the row's head is the whole list entry -- the agent, its
   * current activity (so the closed list still reads as a list of what is
   * running), and anything waiting on the owner. Stop is a sibling of the
   * disclosure button, never inside it, so it stays reachable (and its own
   * click never also toggles the row) whether the row is open or closed. */
  return <div className={'qc-run' + (stopping ? ' qc-run-stopping' : '')}>
    <div className="qc-run-head">
      <button type="button" className="qc-run-disclosure" aria-expanded={open} aria-controls={detailId} onClick={() => setOpen(!open)}>
        <span className="qc-run-disclosure-head">
          <strong>{a.alias}</strong>
          <span className="qc-run-caret" aria-hidden="true">▾</span>
        </span>
        <span className="qc-run-activity">{r?.activity || 'Reading…'}</span>
        {!!permissions.length && <span className="qc-run-permission" role="status">Waiting for you: {permissions[0].summary ?? permissions[0].title ?? 'a permission'}</span>}
      </button>
      <div className="qc-run-controls">
        {a.run && !stopping && <button type="button" className="qc-run-stop" title={`Stop ${a.alias}`} onClick={() => void stop()}>Stop</button>}
        {stopping && <span className="qc-run-stop-words" role="status">{stopWords}</span>}
      </div>
    </div>
    {/* A refused Stop is reported on the row itself, not in the detail: the
      * owner can press Stop on a closed row, so the answer to that press has
      * to be visible on a closed row too. */}
    {state === 'refused' && <p role="alert" className="qc-error">{stopWords}</p>}
    {open && <div className="qc-run-detail" id={detailId}>
      <p className="qc-run-meta">
        {working?.runtime && <span>{working.runtime}</span>}
        {working?.model_requested && <span>{working.model_requested}</span>}
        {consent?.consent?.mode && <span>{consent.consent.mode}</span>}
      </p>
      {workingOn && <a href={href(conversation, topic, workingOn.turn)}>Working on #{workingOn.number ?? 'post'} →</a>}
      <UsageAndWindow entries={entries} contextWindow={contextWindow} />
      <section aria-label="Operations">
        <h4>Operations</h4>
        {entries.filter((e) => e.kind !== 'usage' && e.kind !== 'plan').map((e) => (
          <p key={e.id}>{e.kind}{e.title ? `: ${e.title}` : ''}{e.text ? ` ${e.text}` : ''}{e.status ? ` (${e.status})` : ''}</p>
        ))}
        {!entries.length && <p className="qc-muted">Nothing reported yet.</p>}
      </section>
      <section aria-label="Permission history">
        <h4>Permission history</h4>
        {operations.map((o, i) => (
          <p key={i}>{o.operation.summary ?? o.operation.tool ?? 'an operation'} · {o.answer} · {o.by}</p>
        ))}
        {!operations.length && <p className="qc-muted">Nothing answered yet.</p>}
      </section>
    </div>}
  </div>
}

function Group({ title, rows, working, exec, conversation, topic }: {
  title: string; rows: LiveRow[]; working: Working | null; exec: ExecutionInfo | null
  conversation: Id; topic: Id | null
}) {
  if (!rows.length) return null
  return <div className="qc-activity-group">
    <h3>{title}</h3>
    {rows.map((a) => {
      const run = a.run
      const w = run ? working?.open.find((o) => o.run === run) : undefined
      const contextWindow = contextWindowFor(exec, w?.model_requested ?? null)
      return run
        ? <RunRowView key={run} a={a} run={run} working={w} contextWindow={contextWindow} conversation={conversation} topic={topic} />
        : <div className="qc-run" key={a.participant}><strong>{a.alias}</strong><p className="qc-run-activity">{a.working_on_gap || 'Working, with no post named for it.'}</p></div>
    })}
  </div>
}

export default function ActivityPanel({ conversation, topic }: { conversation: Id; topic: Id | null }) {
  const read_ = useApi<Activity>('/api/activity', { runs: true })
  const working = useApi<Working>('/api/working', { runs: true })
  const exec = useExecution()
  const { here, elsewhere } = groupActivity(read_.data?.activity ?? null, conversation)
  return <>
    <ReadState loading={read_.loading} error={read_.error} reload={read_.reload} />
    {read_.data && !here.length && !elsewhere.length && <p className="qc-muted">No active agents reported here.</p>}
    <Group title="In this conversation" rows={here} working={working.data ?? null} exec={exec.data ?? null} conversation={conversation} topic={topic} />
    <Group title="Elsewhere in Mentis" rows={elsewhere} working={working.data ?? null} exec={exec.data ?? null} conversation={conversation} topic={topic} />
  </>
}
