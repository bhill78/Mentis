/* WHO IS WORKING, AND ON WHICH POST: ONE READER FOR ALL OF FLUID (A4; #568
 * 4.6; FW #1, UX #548).
 *
 * It replaces the two readers the column and the zones each kept
 * (conversation/working.ts, workspace/working.ts, which now only shape this
 * one's rows for their callers). Production's Presence logic
 * (surfaces/Presence.tsx): `/api/activity`, the participants with a live
 * execution, and what each is working on from the record only (`working_on`,
 * the post its acts were recorded against) -- never guessed from prose, never
 * inferred from silence.
 *
 * WOKEN THE WAY PRESENCE IS. Presence reads `/api/activity` as a `runs`
 * reader: it rereads when the pulse's live half moves (a run the record has
 * not heard about yet started, or moved), at most every 4 s, and whenever
 * the record itself moves. This asks the same `/api/pulse` on the same 1.2 s
 * beat, so a run that starts is shown within about 5 s, as in Classic. The
 * pulse is compared here, not through production's `usePulse`: asking
 * production's shared chunk for exports it was not asked for before renames
 * them (vite.config.ts), and production must not move.
 *
 * Read only while something listens; a hidden tab asks nothing and reads
 * again when it is looked at. One question out at a time. */

import { useEffect, useSyncExternalStore } from 'react'
import { CLIENT_HEADERS } from '../../api'
import { fluidFetch } from '../http'
import type { Id } from '../store'

/** One participant's row of `/api/activity`, as far as Fluid uses it. */
export interface Activity {
  participant: Id
  alias: string
  about?: string
  has_live_execution: boolean
  runtime?: string | null
  conversation: Id | null
  conversations: Id[]
  scope: string | null
  working_on: { turn: Id; number: number | null; conversation: Id | null; since: number } | null
  working_on_gap?: string | null
  /** its open runs, as `/api/working` words them; a run this server holds
   *  says what it is doing now, whether it is stopping, and a permission it
   *  waits on (runs/feed.ts reads the rest). In a row `live` hands out (one
   *  entry per run), exactly that one run. */
  runs?: ActivityRun[]
  /** the run this entry is, in a row `live` hands out; null for a live
   *  execution no held run accounts for */
  run?: Id | null
}

export interface ActivityRun {
  run: Id
  state: string
  words?: string
  held_here: boolean
  activity?: string | null
  stopping?: boolean
  permission?: { form: string; decision?: string; title?: string; post?: string | null; conversation?: string | null } | null
  permissions?: { form: string; decision?: string; title?: string; post?: string | null; conversation?: string | null }[]
  /** where THIS run runs, by its own start act */
  conversation?: Id | null
  turn?: Id | null
  /** open and held by this server: somebody working right now */
  live?: boolean
  /** the post it was dispatched on */
  working_on?: Activity['working_on']
}

const BEAT = 1200          // usePulse's own
const BEAT_HIDDEN = 5000   // usePulse's, for a tab nobody is looking at
const LIVE_SPACING = 4000  // Presence's runsSpacing
const DURABLE_SPACING = 1000
const STALE = 30000        // read anyway, so a missed beat cannot leave it wrong for long

let rows: Activity[] | null = null
let shape = ''
let lastRead = 0
let reading = false
let again = false
let token: string | null = null
let beatTimer: number | null = null
let looping = false
let readTimer: number | null = null
let missed = 0
const heard = new Set<() => void>()

const json = async <T,>(path: string): Promise<T> => {
  const res = await fluidFetch(path, { headers: { ...CLIENT_HEADERS } })
  const body = await res.json().catch(() => null)
  if (!res.ok || !body || body.error) throw new Error(body?.error ?? res.statusText)
  return body as T
}

const hidden = () => typeof document !== 'undefined' && document.visibilityState === 'hidden'

async function read() {
  if (reading) { again = true; return }
  if (hidden()) return
  reading = true
  lastRead = Date.now()
  try {
    const d = await json<{ activity: Activity[] }>('/api/activity')
    const got = (d.activity ?? []).map((a) => ({
      participant: a.participant, alias: a.alias, about: a.about, has_live_execution: !!a.has_live_execution,
      runtime: a.runtime ?? null, conversation: a.conversation ?? null, conversations: a.conversations ?? [],
      scope: a.scope ?? null, working_on_gap: a.working_on_gap ?? null,
      runs: (a.runs ?? []).map((r) => ({ run: r.run, state: r.state, words: r.words, held_here: !!r.held_here,
        activity: r.activity ?? null, stopping: !!r.stopping, permission: r.permission ?? null,
        permissions: r.permissions ?? (r.permission ? [r.permission] : []),
        conversation: r.conversation ?? null, turn: r.turn ?? null, live: !!r.live,
        working_on: r.working_on ? { turn: r.working_on.turn, number: r.working_on.number ?? null,
          conversation: r.working_on.conversation ?? null, since: r.working_on.since } : null })),
      working_on: a.working_on ? { turn: a.working_on.turn, number: a.working_on.number ?? null,
        conversation: a.working_on.conversation ?? null, since: a.working_on.since } : null,
    }))
    const next = JSON.stringify(got)
    /* A reread that says the same changes nothing: no card re-renders. */
    if (next !== shape || rows === null) {
      shape = next
      rows = got
      heard.forEach((fn) => fn())
    }
  } catch {
    /* unreachable for a moment: what was last read stands */
  } finally {
    reading = false
    if (again) { again = false; soon(0) }
  }
}

/** Read no sooner than `spacing` after the last read; a later ask joins it. */
function soon(spacing: number) {
  const at = Math.max(Date.now(), lastRead + spacing)
  if (readTimer !== null) return
  readTimer = window.setTimeout(() => { readTimer = null; void read() }, at - Date.now())
}

/** The pulse token's two halves: `<durable>/<live>` (production's `pulseChange`). */
/** The live half of a pulse token (`<durable>/<live>`), '' for none. */
function livePart(t: string | null): string {
  if (!t) return ''
  const i = t.indexOf('/')
  return i < 0 ? '' : t.slice(i + 1)
}

function moved(prev: string | null, next: string): 'durable' | 'live' | null {
  if (prev === null || prev === next) return null
  const cut = (t: string) => { const i = t.indexOf('/'); return i < 0 ? [t, ''] : [t.slice(0, i), t.slice(i + 1)] }
  const [d0, l0] = cut(prev)
  const [d1, l1] = cut(next)
  if (d0 !== d1) return 'durable'
  return l0 !== l1 ? 'live' : null
}

/* THE PULSE, heard by whatever in Fluid rereads on it: this reader, and the
 * frame's notifications (frame/notifications.ts). One beat for all of them,
 * running only while one listens. */
export type Moved = 'durable' | 'live'
/** Where the record moved, as `/api/pulse?since=` says (production's `Where`);
 *  null when it could not say. */
export interface Where { conversations: Id[]; executions: string[]; governed: boolean; people: boolean; loose: boolean }
/* `liveToo`: a durable move whose beat ALSO moved the live half -- a reader
 * that skips the durable move still owes the live one its reread. */
const pulseHeard = new Set<(m: Moved, where: Where | null, liveToo: boolean) => void>()
const beatHeard = new Set<() => void>()

async function beat() {
  beatTimer = null
  if (!pulseHeard.size && !beatHeard.size) { looping = false; return }
  if (!hidden()) {
    try {
      /* Saying what was last seen, so the answer can say where it moved. */
      const since = token ? token.split('/')[0] : null
      const r = await json<{ token: string; moved?: Where | null }>('/api/pulse' + (since ? '?since=' + encodeURIComponent(since) : ''))
      const m = moved(token, r.token)
      const liveToo = m === 'durable' && livePart(token) !== livePart(r.token)
      token = r.token
      missed = 0
      if (m) pulseHeard.forEach((fn) => fn(m, m === 'durable' ? r.moved ?? null : null, liveToo))
      beatHeard.forEach((fn) => fn())
    } catch {
      missed = Math.min(missed + 1, 5)
    }
  }
  if (pulseHeard.size || beatHeard.size) beatTimer = window.setTimeout(beat, hidden() ? BEAT_HIDDEN : BEAT * (1 + missed))
  else looping = false
}

/** Hear the record (`durable`) or live execution (`live`) move. Returns the
 *  way to stop hearing. */
export function hearPulse(fn: (m: Moved, where: Where | null, liveToo: boolean) => void): () => void {
  pulseHeard.add(fn)
  /* One loop: a beat already out schedules the next itself. */
  if (!looping) { looping = true; beatTimer = window.setTimeout(beat, 0) }
  return () => {
    pulseHeard.delete(fn)
    if (!pulseHeard.size && !beatHeard.size && beatTimer !== null) { clearTimeout(beatTimer); beatTimer = null; looping = false }
  }
}

/** Hear each successful pulse answer. Stale fallbacks use this same loop
 * instead of starting another timer which asks the server independently. */
export function hearPulseBeat(fn: () => void): () => void {
  beatHeard.add(fn)
  if (!looping) { looping = true; beatTimer = window.setTimeout(beat, 0) }
  return () => {
    beatHeard.delete(fn)
    if (!pulseHeard.size && !beatHeard.size && beatTimer !== null) {
      clearTimeout(beatTimer); beatTimer = null; looping = false
    }
  }
}

/** WHETHER A DURABLE MOVE CAN CHANGE WHAT A READER SHOWS, from where the
 *  pulse says it moved (`mentis/web/moved.py`). That answer only ever narrows
 *  what is certain, so: no `where`, or a `loose` one, is always a yes; so is
 *  anything named in `concerned` (Brain-wide material, people, any run's
 *  acts, any Conversation's). A move that names none of them cannot change
 *  this reader's answer, and asking again for it was only load: on DAY-TO-DAY
 *  most moves are a run's own acts and deliveries, and every open page reread
 *  `/api/activity` and `/api/owed` on each. The reader's own STALE read still
 *  runs either way. */
export function concerns(where: Where | null,
  concerned: { conversations?: boolean; executions?: boolean; governed?: boolean; people?: boolean }): boolean {
  if (!where || where.loose) return true
  return (!!concerned.people && where.people)
    || (!!concerned.governed && where.governed)
    || (!!concerned.executions && where.executions.length > 0)
    || (!!concerned.conversations && where.conversations.length > 0)
}

/* WHO IS WORKING moves with runs (an execution's acts and deliveries: started,
 * ended, a permission it waits on, the post its acts are on) and with people
 * (a participant's alias, what they are in). A post nobody's run wrote moves
 * neither. */
const ACTIVITY_CONCERNS = { executions: true, people: true }
/** How soon who-is-working is read again for a pulse move, or null for not
 *  at all: a durable move that concerns it rereads at DURABLE_SPACING, a
 *  live one -- or a skipped durable one whose beat also moved the live half,
 *  a run starting or ending as somebody posts -- at LIVE_SPACING. */
export function activityReread(m: Moved, where: Where | null, liveToo = false): number | null {
  if (m === 'live') return LIVE_SPACING
  if (concerns(where, ACTIVITY_CONCERNS)) return DURABLE_SPACING
  return liveToo ? LIVE_SPACING : null
}
const onPulse = (m: Moved, where: Where | null, liveToo = false) => {
  const spacing = activityReread(m, where, liveToo)
  if (spacing !== null) soon(spacing)
}
const staleCheck = () => { if (heard.size && Date.now() - lastRead > STALE) soon(0) }
const shown = () => { if (!hidden() && heard.size) soon(0) }
let stopPulse: (() => void) | null = null
let stopBeat: (() => void) | null = null

function subscribe(fn: () => void) {
  heard.add(fn)
  if (heard.size === 1) {
    soon(0)
    stopPulse = hearPulse(onPulse)
    stopBeat = hearPulseBeat(staleCheck)
    document.addEventListener('visibilitychange', shown)
  }
  return () => {
    heard.delete(fn)
    if (!heard.size) {
      stopPulse?.(); stopPulse = null
      stopBeat?.(); stopBeat = null
      document.removeEventListener('visibilitychange', shown)
    }
  }
}

/** Ask again now: something here says work moved (a conversation's own
 *  count of work changed on the change feed). */
export function activityNow() { if (heard.size) soon(DURABLE_SPACING) }

/** Every participant's row, or null before the first answer. */
export function useActivity(): Activity[] | null {
  return useSyncExternalStore(subscribe, () => rows)
}

/** WHO IS WORKING RIGHT NOW, ONE ENTRY PER RUN. A participant's row is
 *  per participant; this hands out one entry for each of its live runs
 *  (`live` on the run: open and held here), narrowed to that run -- its
 *  conversation, the post it is on, `runs: [that run]` -- so two runs of
 *  one participant are two entries, each where ITS run is. A live execution
 *  no live run accounts for (one begun without a dispatch) is one entry,
 *  where that execution is. Membership of a conversation is never where
 *  somebody is working. */
export function live(all: Activity[] | null): Activity[] {
  const out: Activity[] = []
  for (const a of all ?? []) {
    const runs = (a.runs ?? []).filter((r) => r.live)
    if (runs.length) {
      for (const r of runs) {
        out.push({ ...a, has_live_execution: true, run: r.run, runs: [r], conversation: r.conversation ?? null,
          conversations: r.conversation ? [r.conversation] : [], scope: r.conversation ? 'conversation' : 'brain',
          working_on: r.working_on ?? null })
      }
    } else if (a.has_live_execution) {
      out.push({ ...a, run: null, runs: [], conversations: a.conversation ? [a.conversation] : [] })
    }
  }
  return out
}

/** What tells two entries of `live` apart: the run, else the participant. */
export const workKey = (a: Activity) => a.run ?? a.participant

/** Whether `participant` has a live execution now. Given no participant it
 *  listens to nothing, so a face that does not ask starts no reading. */
const none = () => () => {}
export function useIsWorking(participant: Id | null | undefined): boolean {
  const all = useSyncExternalStore(participant ? subscribe : none, () => (participant ? rows : null))
  return !!participant && live(all).some((a) => a.participant === participant)
}

/** Who is working in conversation `here`, one entry per run: the runs
 *  whose own conversation is `here`. Not a participant's every run because
 *  it is a member here -- that showed work from other conversations in this
 *  one's working line. */
export function workingIn(all: Activity[] | null, here: Id): Activity[] {
  return live(all).filter((a) => a.conversation === here || (!a.conversation && a.working_on?.conversation === here))
}

/** Who is working on one of `posts`, by the record. */
export function workingOnPosts(all: Activity[] | null, posts: Iterable<Id>): Activity[] {
  const these = new Set(posts)
  if (!these.size) return []
  return live(all).filter((a) => !!a.working_on && these.has(a.working_on.turn))
}

/** Re-read when `n` (a count of work the store already follows) moves. */
export function useActivityPoke(n: number | undefined) {
  useEffect(() => { if (n !== undefined) activityNow() }, [n])
}

export const atAlias = (alias: string) => '@' + alias.replace(/^@/, '')
