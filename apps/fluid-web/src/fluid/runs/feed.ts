/* A RUN'S LIVE FEED, AS THIS SERVER HOLDS IT (`/api/runs/<run>/feed`).
 *
 * What MARS reports of a run Mentis is holding: the agent's messages and
 * thoughts, its tool calls with their status, its plan and its usage, what it
 * is doing now, a permission it waits on, and how it ended. Read only while
 * somebody is looking (an open run panel): every entry new or changed since
 * the last `seq` is merged by its stable `id`. Nothing here is the record --
 * the feed is transient and dies with the run's observation on the server.
 *
 * STOP is `POST /api/runs/<run>/stop`. It asks MARS to end the session; the
 * work the run was doing is not marked done, and the panel says so. */

import { useEffect, useState, useSyncExternalStore } from 'react'
import { post, read } from '../../api'

export interface FeedEntry {
  id: string
  seq: number
  kind: 'message' | 'thought' | 'tool' | 'plan' | 'usage' | 'permission'
  at: number
  text?: string
  title?: string
  tool_kind?: string
  status?: 'pending' | 'in_progress' | 'completed' | 'failed'
  locations?: string[]
  raw_input?: unknown
  raw_output?: unknown
  entries?: { content: string; status: string; priority?: string }[]
  usage?: Record<string, number | string>
  outcome?: string
  answered_by?: string
}

/** A permission the run waits on; `summary` is its operation in words
 *  (docs/run-consent.md §3), absent from an older server. */
export interface Permission { form: string; title?: string; summary?: string | null; kind?: string; asked_at: number; post?: string | null; conversation?: string | null }

export interface Feed {
  run: string
  held_here: boolean
  running?: boolean
  activity?: string | null
  activity_at?: number | null
  ended_at?: number | null
  stop?: { by: string; why: string; at: number } | null
  outcome?: { stop_reason: string | null; error_kind: string | null; error: string | null; stopped: boolean; session_ended: boolean } | null
  permission?: Permission | null
  events: FeedEntry[]
  next: number
  note?: string
}

export interface FeedState { feed: Feed | null; entries: FeedEntry[]; error: string | null }

/** How often an open panel asks for what is new. */
const EVERY_MS = 1000

const states = new Map<string, FeedState>()
const heard = new Map<string, Set<() => void>>()
const emit = (run: string) => { for (const fn of heard.get(run) ?? []) fn() }

/** Merge `got` into what is held for its run: entries by id, ordered by seq. */
export function merge(held: FeedEntry[], got: FeedEntry[]): FeedEntry[] {
  if (!got.length) return held
  const by = new Map(held.map((e) => [e.id, e]))
  for (const e of got) by.set(e.id, e)
  return [...by.values()].sort((a, b) => a.seq - b.seq)
}

async function step(run: string) {
  const was = states.get(run) ?? { feed: null, entries: [], error: null }
  try {
    const got = await read<Feed>(`/api/runs/${encodeURIComponent(run)}/feed?after=${was.feed?.next ?? 0}`)
    states.set(run, { feed: got, entries: merge(was.entries, got.events), error: null })
  } catch (e) {
    states.set(run, { ...was, error: e instanceof Error ? e.message : String(e) })
  }
  emit(run)
}

/** Follow one run while mounted. Stops asking once the run has ended here. */
export function useRunFeed(run: string | null): FeedState {
  const sub = (fn: () => void) => {
    if (!run) return () => {}
    const set = heard.get(run) ?? new Set()
    set.add(fn)
    heard.set(run, set)
    return () => { set.delete(fn) }
  }
  const got = useSyncExternalStore(sub, () => (run ? states.get(run) : undefined))
  useEffect(() => {
    if (!run) return
    let live = true
    let timer = 0
    let failures = 0
    const tick = async () => {
      await step(run)
      const s = states.get(run)
      const f = s?.feed
      /* A FAILED READ IS ASKED AGAIN, more slowly each time: a server that
         was briefly unreachable must not leave the panel "Reading…". */
      failures = s?.error ? failures + 1 : 0
      const wait = failures ? Math.min(EVERY_MS * 2 ** failures, 15000) : document.hidden ? EVERY_MS * 5 : EVERY_MS
      if (live && (failures || (f && f.held_here && !f.ended_at))) timer = window.setTimeout(tick, wait)
    }
    tick()
    return () => { live = false; window.clearTimeout(timer) }
  }, [run])
  return got ?? { feed: null, entries: [], error: null }
}

export interface StopAnswer { run: string; asked: boolean; state: 'stopping' | 'already-ended' | 'not-held-here' | 'not-running'; note: string }

/** Ask the server to stop the run's session. */
export async function stopRun(run: string, why = 'stopped from Fluid'): Promise<StopAnswer> {
  const got = await post<StopAnswer>(`/api/runs/${encodeURIComponent(run)}/stop`, { why })
  void step(run)
  return got
}

/** Stop, with the state a button needs: idle, asking, asked, or what failed. */
export function useStop(run: string) {
  const [state, setState] = useState<'idle' | 'asking' | 'asked' | 'refused'>('idle')
  const [why, setWhy] = useState<string | null>(null)
  const stop = async () => {
    if (state === 'asking') return
    setState('asking')
    try {
      const got = await stopRun(run)
      setState(got.asked ? 'asked' : 'refused')
      setWhy(got.asked ? null : got.state.replace(/-/g, ' '))
    } catch (e) {
      setState('refused')
      setWhy(e instanceof Error ? e.message : String(e))
    }
  }
  return { state, why, stop }
}

/** How a run ended, in the words the panel shows: a session's end, never a verdict on the work. */
export function endedWords(f: Feed | null): string | null {
  const o = f?.outcome
  if (!f || !f.ended_at || !o) return null
  if (o.stopped) return o.session_ended ? 'Stopped: the session was ended by force' : 'Stopped: the session ended cleanly'
  if (o.error_kind) return `Session ended: ${o.error_kind.replace(/_/g, ' ')}`
  if (o.stop_reason === 'end_turn') return 'Session finished its turn'
  return `Session ended: ${(o.stop_reason ?? 'unknown').replace(/_/g, ' ')}`
}
