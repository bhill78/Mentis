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
import { confirmBrain, guarding, page, useBrainMoved } from '../../brainBinding'

export interface FeedEntry {
  id: string
  seq: number
  kind: 'message' | 'thought' | 'tool' | 'plan' | 'usage' | 'turn_usage' | 'permission'
  at: number
  /** when a tool call was first seen */
  started_at?: number
  /** THE RUNTIME-NATIVE WORKER THIS BELONGS TO (a Claude sub-agent): the feed
   *  id of that worker's own tool call, as MARS reported it. Absent for the
   *  run's own calls and for a runtime that exposes no workers. */
  parent?: string
  /** THIS TOOL CALL STARTS A NATIVE WORKER: what the runtime reported of it so
   *  far (possibly nothing yet). A tool call of this run, never an execution. */
  worker?: { description?: string; requested_model?: string; agent_type?: string; agent_id?: string; model?: string
    elapsed_s?: number; duration_ms?: number; tool_calls?: number; context_tokens?: number; event?: string; count?: number }
  /** the run ended without the runtime reporting this call finished */
  open_at_end?: boolean
  /** `turn_usage`: what the runtime reported the turn consumed (`mars/usage`) */
  turn?: unknown
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
export interface Permission { form: string; decision?: string; title?: string; summary?: string | null; kind?: string; asked_at: number; post?: string | null; conversation?: string | null }

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
  /** every permission still waiting; `permission` above is the legacy first */
  permissions?: Permission[]
  events: FeedEntry[]
  next: number
  note?: string
  /** Independent of memory residency: what its END ACT recorded (its
   *  tool calls with their place in the run, and what it used). */
  recorded?: unknown
}

export interface FeedState { feed: Feed | null; entries: FeedEntry[]; error: string | null }

/** Every request still waiting, preserving the server's order. */
export function waitingPermissions(feed: Feed | null): Permission[] {
  return feed?.permissions ?? (feed?.permission ? [feed.permission] : [])
}

/** How often an open panel asks for what is new. */
const EVERY_MS = 1000

const states = new Map<string, FeedState>()
const heard = new Map<string, Set<() => void>>()
const emit = (run: string) => { for (const fn of heard.get(run) ?? []) fn() }
const keyOf = (run: string) => `${page.bound() ?? ''}/${run}`
const EMPTY: FeedState = { feed: null, entries: [], error: null }

/** Merge `got` into what is held for its run: entries by id, ordered by seq. */
export function merge(held: FeedEntry[], got: FeedEntry[]): FeedEntry[] {
  if (!got.length) return held
  const by = new Map(held.map((e) => [e.id, e]))
  for (const e of got) by.set(e.id, e)
  return [...by.values()].sort((a, b) => a.seq - b.seq)
}

/** One explicit read, also used when Activity reopens. It never starts a timer. */
export async function rereadRunFeed(run: string) {
  const key = keyOf(run)
  const brain = page.bound()
  if (page.moved()) return
  const was = states.get(key) ?? EMPTY
  try {
    const got = await read<Feed>(`/api/runs/${encodeURIComponent(run)}/feed?after=${was.feed?.next ?? 0}`)
    if (guarding() && await confirmBrain() !== true) throw new Error('Could not confirm this activity belongs to this Brain. Reload to read it.')
    if (page.moved() || (brain !== null && brain !== page.bound())) return
    states.set(keyOf(run), { feed: got, entries: merge(was.entries, got.events), error: null })
  } catch (e) {
    if (page.moved() || (brain !== null && brain !== page.bound())) return
    states.set(keyOf(run), { ...was, error: e instanceof Error ? e.message : String(e) })
  }
  emit(keyOf(run))
}

/** Follow one run while mounted. Stops asking once the run has ended here. */
export function useRunFeed(run: string | null): FeedState {
  const moved = useBrainMoved()
  useSyncExternalStore(page.subscribe, page.bound, page.bound)
  const key = run ? keyOf(run) : null
  const sub = (fn: () => void) => {
    if (!key) return () => {}
    const set = heard.get(key) ?? new Set()
    set.add(fn)
    heard.set(key, set)
    return () => { set.delete(fn) }
  }
  const got = useSyncExternalStore(sub, () => (key ? states.get(key) : undefined))
  useEffect(() => {
    if (!run || moved) return
    let live = true
    let timer = 0
    let failures = 0
    const tick = async () => {
      await rereadRunFeed(run)
      const s = states.get(keyOf(run))
      const f = s?.feed
      /* A FAILED READ IS ASKED AGAIN, more slowly each time: a server that
         was briefly unreachable must not leave the panel "Reading…". */
      failures = s?.error ? failures + 1 : 0
      const wait = failures ? Math.min(EVERY_MS * 2 ** failures, 15000) : document.hidden ? EVERY_MS * 5 : EVERY_MS
      if (live && !page.moved() && !f?.ended_at && !f?.recorded && (failures || f?.held_here)) timer = window.setTimeout(tick, wait)
    }
    tick()
    return () => { live = false; window.clearTimeout(timer) }
  }, [run, moved])
  return moved ? { ...EMPTY, error: 'This page belongs to another Brain. Reload to read its activity.' } : got ?? EMPTY
}

export interface StopAnswer { run: string; asked: boolean; state: 'stopping' | 'already-ended' | 'not-held-here' | 'not-running'; note: string }

/** Ask the server to stop the run's session. */
export async function stopRun(run: string, why = 'stopped from Fluid'): Promise<StopAnswer> {
  const got = await post<StopAnswer>(`/api/runs/${encodeURIComponent(run)}/stop`, { why })
  void rereadRunFeed(run)
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
