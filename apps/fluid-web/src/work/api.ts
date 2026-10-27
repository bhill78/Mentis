/* Work Overview reads (contract v1). Added VERBATIM by each track.
 *
 * BACKWARD-COMPATIBLE ADDITIONS (fix round, Ledger track): `activeSince`,
 * `runs` and `spacing` on `useWorkOverview`, and `opts` on `useWorkDetail`.
 * Left out, each behaves exactly as before: every read follows the live
 * pulse, which since the performance work (eb19c99) moves a work read at
 * most every WORK_LIVE_SPACING; durable moves still reread at once. */
import { useApi, type Id } from '../api'
import type { WorkDetail, WorkOverview } from './contract'

const q = (o: Record<string, string | number | null | undefined>) => {
  const s = Object.entries(o)
    .filter(([, v]) => v !== null && v !== undefined && v !== '')
    .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`)
    .join('&')
  return s ? `?${s}` : ''
}

/** How often live movement alone may reread a work read (ms). */
export const WORK_LIVE_SPACING = 10_000

/** Local midnight today, ISO: the Ledger's "Completed today" window. */
export const startOfToday = (): string => {
  const d = new Date()
  d.setHours(0, 0, 0, 0)
  return d.toISOString()
}

export interface WorkOverviewQuery {
  viewer: Id | null
  conversation?: Id | null
  completedSince?: string | null
  /** TODAY'S LEDGER: what needs the viewer, what is moving, and what was
   *  active since this moment. The only read that fills `returned`. */
  activeSince?: string | null
  limit?: number
}

/** The path `useWorkOverview` reads. */
export const workOverviewPath = (opts: WorkOverviewQuery): string =>
  `/api/work${q({
    viewer: opts.viewer,
    conversation: opts.conversation ?? null,
    completed_since: opts.completedSince ?? null,
    active_since: opts.activeSince ?? null,
    limit: opts.limit ?? null,
  })}`

/** Brain-wide work for the Daily Briefing Ledger, or one conversation's
 *  work for its footer pills when `conversation` is given.
 *
 *  `runs: false` for a reader that shows no live run words: it then rereads
 *  only when the record moves, not on every live pulse (about every 1.2 s
 *  while an agent works). `spacing` (ms) bounds how often it rereads at all. */
export function useWorkOverview(opts: WorkOverviewQuery & {
  on?: boolean
  runs?: boolean
  spacing?: number
}) {
  const path = opts.on === false ? null : workOverviewPath(opts)
  // LIVE MOVEMENT AT MOST EVERY 10 s, as a Conversation's `/work` (see
  // WorkStatus): work state moves on live movement only when a run's observed
  // liveness changes, and every recorded act is a durable move that still
  // rereads at once. Brain-wide, this read is the Ledger's whole picture.
  return useApi<WorkOverview>(path, { runs: opts.runs ?? true, runsSpacing: WORK_LIVE_SPACING, spacing: opts.spacing })
}

/** One work item's detail for the hover card and drawer. `null` asks nothing.
 *  The open drawer follows live runs; a passing glance (the hover card) can
 *  say `{ runs: false }`. */
export function useWorkDetail(expectation: Id | null, viewer: Id | null,
                              opts: { runs?: boolean } = {}) {
  return useApi<WorkDetail>(
    expectation ? `/api/work/${encodeURIComponent(expectation)}${q({ viewer })}` : null,
    { runs: opts.runs ?? true, runsSpacing: WORK_LIVE_SPACING },
  )
}
