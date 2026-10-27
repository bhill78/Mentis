/* A TIMER'S LEDGER, AS MENTIS KEEPS IT (timer build, package A; plan
 * adm-4fc92741cf96, A5-A6).
 *
 * A posted ```timer``` with a usable, unique name= is keyed
 * `Turn <id>[ part <i>]/@<name>:timer` (objects.ts, keyOf), as a form is.
 * Its runs are the owner's marks in their own ledger
 * (mentis/conversation/timers.py), read and written through
 *
 *   GET  /api/timers/<post>/<name>?part=&tz=&midnight=&utc_offset=   the state now
 *   POST /api/timers/<post>/<name>/marks                              one mark
 *   GET  /api/timers/about/<ref>?tz=&midnight=&utc_offset=            time spent
 *
 * "TODAY" IS THE VIEWER'S. Every read sends this tab's IANA zone, its own
 * local midnight and its offset; the server uses the zone, else the
 * midnight, else the offset, so a clock-change day is counted right.
 *
 * NOTHING IS COUNTED HERE. The server reads every total from the marks. This
 * tab only moves the clock on between reads: what was read, plus the time
 * since it was read. The state is read again when the timer is first drawn,
 * when the window comes back into focus or view, and after every mark, so a
 * closed tab or a machine that slept loses nothing.
 *
 * OP KEYS. Each mark carries an operation key made when it is first tried; a
 * retry sends the same key, so it is recorded once. A box-end or break-end
 * is keyed by its run and box number, so two tabs record it once.
 * ------------------------------------------------------------------------ */
import { useEffect, useState, useSyncExternalStore } from 'react'
import { fluidFetch } from '../fluid/http'

const API = '/api/timers'
const HEADERS = { 'X-Mentis-Client': '1', 'Content-Type': 'application/json' }

export type Action = 'start' | 'stop' | 'continue' | 'box-end' | 'break-end'

export interface Run {
  run: string
  start: string
  end: string | null
  counted_to: string
  state: 'running' | 'stopped' | 'forgotten'
  seconds: number
  by: string
  stops: string[]
  corrected: boolean
  conflict: string[] | null
  also_started: string[]
  continued: number
  check_in_at?: string
  says?: string
}

/** One about= reference, as the record holds it (or not: unresolved). */
export interface AboutRef {
  ref: string
  resolved: boolean
  kind: 'Topic' | 'Conversation' | 'post' | null
  label: string | null
  entry?: string
  why?: string
}

export interface TimerState {
  post: string
  block: string
  part: number
  holder: string
  set: string | null
  now: string
  utc_offset: number
  today_from: string
  title: string | null
  /** how an owner names this timer to an agent: ent-<post>#<name> */
  reference?: string
  about?: AboutRef[]
  today_by?: 'zone' | 'midnight' | 'offset'
  box_s: number | null
  break_s: number | null
  runs: Run[]
  today_s: number
  total_s: number
  boxes_today: number
  state: 'running' | 'stopped' | 'forgotten'
  running: boolean
  problems: { mark: string; action: string; at: string; problem: string }[]
  conflicts: string[]
  source_deleted: { record: string; at: number; by: string } | null
  box: { phase: 'box' | 'break'; number: number; remaining_s: number; length_s: number; ends_at: string } | null
  check_in: {
    due_at: string; asking: boolean; in_s?: number; question?: string; options?: string[]
    /** past the grace: counted only to the check-in, whatever is pressed */
    forgotten?: boolean; says?: string; primary?: string; labels?: Record<string, string>
    grace_s?: number; grace_until?: string; stopped_at_from?: string; stopped_at_to?: string
  } | null
  you?: string | null
  says?: string
  why_not?: string
}

export interface TimerEntry {
  post: string
  part: number
  block: string
  state?: TimerState
  /** this tab's clock (ms) when `state` was read */
  readAt?: number
  readError?: string
  /** a mark the server refused, in its words, or one that could not be sent */
  said?: { ok: boolean; text: string }
  busy?: Action
  /** the key of a mark being tried, kept for its retry */
  pending?: { op: string; body: Record<string, unknown> }
}

/** A posted named timer's key, read back into what it names; null otherwise. */
export function timerAddress(key: string): { post: string; part: number; block: string } | null {
  const m = /^Turn (\S+?)(?: part (\d+))?\/@(.+):timer$/.exec(key)
  return m ? { post: m[1], part: m[2] ? Number(m[2]) : 0, block: m[3] } : null
}

const entries = new Map<string, TimerEntry>()
const listeners = new Set<() => void>()
let v = 0
const tell = () => { v++; listeners.forEach((f) => f()) }
const subscribe = (f: () => void) => { listeners.add(f); return () => { listeners.delete(f) } }

export const newOp = () => 'ui-' + (globalThis.crypto?.randomUUID?.() ?? `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`)

/** The viewer's offset from UTC, minutes east, for "today". */
export const utcOffset = () => -new Date().getTimezoneOffset()

/** This tab's IANA zone ('' when the browser does not say). */
export const timeZone = (): string => {
  try { return Intl.DateTimeFormat().resolvedOptions().timeZone ?? '' } catch { return '' }
}

/** This tab's own local midnight today, as ISO-8601 UTC. */
export const localMidnight = (): string => {
  const d = new Date()
  d.setHours(0, 0, 0, 0)
  return d.toISOString().replace(/\.\d{3}Z$/, 'Z')
}

/** What every read sends so the server knows the viewer's "today". */
export const dayParams = (): string =>
  `tz=${encodeURIComponent(timeZone())}&midnight=${encodeURIComponent(localMidnight())}&utc_offset=${utcOffset()}`

export function timerEntry(key: string): TimerEntry | null {
  const hit = entries.get(key)
  if (hit) return hit
  const at = timerAddress(key)
  if (!at) return null
  const e: TimerEntry = { ...at }
  entries.set(key, e)
  return e
}

const base = (e: TimerEntry) => `${API}/${encodeURIComponent(e.post)}/${encodeURIComponent(e.block)}`

async function call(path: string, body?: unknown): Promise<{ status: number; body: any }> {
  const res = await fluidFetch(path, body === undefined ? { headers: HEADERS } : { method: 'POST', headers: HEADERS, body: JSON.stringify(body) })
  const text = await res.text()
  try { return { status: res.status, body: text ? JSON.parse(text) : {} } } catch { return { status: res.status, body: { error: `${res.status}: ${text.slice(0, 200)}` } } }
}

const inFlight = new Map<string, Promise<void>>()

/** Read the timer's state now. */
export function readTimer(key: string): Promise<void> {
  const e = timerEntry(key)
  if (!e) return Promise.resolve()
  const going = inFlight.get(key)
  if (going) return going
  const p = (async () => {
    try {
      const got = await call(`${base(e)}?part=${e.part}&${dayParams()}`)
      if (got.status !== 200 || got.body.error) e.readError = got.body.error ?? `the timer could not be read (${got.status})`
      else { e.state = got.body; e.readAt = Date.now(); e.readError = undefined }
    } catch (err) {
      e.readError = `the timer could not be read: ${(err as Error).message}`
    } finally {
      inFlight.delete(key)
      tell()
    }
  })()
  inFlight.set(key, p)
  return p
}

/** Write one mark, then read the state again. `op` names a mark that two
    tabs must record once (a box-end); otherwise one is made. */
export async function markTimer(key: string, action: Action, extra: Record<string, unknown> = {}, op?: string): Promise<boolean> {
  const e = timerEntry(key)
  if (!e) return false
  const body = { action, part: e.part, tz: timeZone(), midnight: localMidnight(), utc_offset: utcOffset(), ...extra }
  const pending = e.pending && JSON.stringify(e.pending.body) === JSON.stringify(body) ? e.pending : { op: op ?? newOp(), body }
  e.pending = pending
  e.busy = action
  e.said = undefined
  tell()
  try {
    const got = await call(`${base(e)}/marks`, { ...body, op: pending.op })
    e.pending = undefined
    if (got.status !== 200 || got.body.refused || got.body.error) {
      e.said = { ok: false, text: got.body.error ?? `Mentis did not record it (${got.status})` }
      return false
    }
    if (got.body.state) { e.state = got.body.state; e.readAt = Date.now() }
    const problems: string[] = got.body.problems ?? []
    if (problems.length) e.said = { ok: true, text: problems.join(' ') }
    return true
  } catch (err) {
    /* Not reached: kept, with its key, so Try again is the same mark. */
    e.said = { ok: false, text: `could not reach Mentis: ${(err as Error).message}` }
    return false
  } finally {
    e.busy = undefined
    tell()
    void readTimer(key)
  }
}

/** Send the mark that could not be sent, with its own key. */
export function retryMark(key: string) {
  const e = timerEntry(key)
  const p = e?.pending
  if (!e || !p) return
  const { action, ...rest } = p.body as { action: Action }
  return markTimer(key, action, rest, p.op)
}

/** The entry for this key, read when first drawn and again on focus. */
export function useTimer(key: string): TimerEntry | null {
  useSyncExternalStore(subscribe, () => v)
  const e = timerEntry(key)
  useEffect(() => {
    if (!timerAddress(key)) return
    void readTimer(key)
    const again = () => { if (document.visibilityState !== 'hidden') void readTimer(key) }
    window.addEventListener('focus', again)
    document.addEventListener('visibilitychange', again)
    return () => { window.removeEventListener('focus', again); document.removeEventListener('visibilitychange', again) }
  }, [key])
  return e
}

/* ------------------------------------------------------------ the clock */

/** Seconds as the clock shows them: 0:07, 12:03, 1:02:09. */
export function clock(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds))
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), r = s % 60
  return h ? `${h}:${String(m).padStart(2, '0')}:${String(r).padStart(2, '0')}` : `${m}:${String(r).padStart(2, '0')}`
}

/** A span in words: 0m, under a minute, 25m, 1h 05m. */
export function spanWords(seconds: number): string {
  if (seconds < 1) return '0m'
  const m = Math.floor(seconds / 60)
  if (m < 1) return 'under a minute'
  const h = Math.floor(m / 60)
  return h ? `${h}h ${String(m % 60).padStart(2, '0')}m` : `${m}m`
}

/** What the state says now, moved on by the time since it was read. Pure. */
export function project(s: TimerState, readAt: number, nowMs: number) {
  const since = Math.max(0, (nowMs - readAt) / 1000)
  const running = s.running
  const server = Date.parse(s.now) / 1000 + since
  const dueAt = s.check_in ? Date.parse(s.check_in.due_at) / 1000 : null
  const graceEnd = dueAt !== null ? dueAt + (s.check_in?.grace_s ?? 0) : null
  /* The check-in comes due in this tab before the next read says so. Within
     the grace an answer is in time, and the run still counts; past it the
     run is forgotten, counted only to the check-in (as the server reads it). */
  const lapsed = running && graceEnd !== null && server >= graceEnd
  const asking = !!s.check_in?.asking || (running && dueAt !== null && server >= dueAt)
  const forgotten = s.state === 'forgotten' || lapsed
  const moving = running && !lapsed ? since : running && dueAt !== null ? Math.max(0, dueAt - (server - since)) : 0
  const current = s.runs.length ? s.runs[s.runs.length - 1] : null
  let box = s.box
  let boxEnded: { phase: 'box' | 'break'; number: number } | null = null
  if (box && running && !asking) {
    const left = box.remaining_s - since
    if (left <= 0) boxEnded = { phase: box.phase, number: box.number }
    box = { ...box, remaining_s: Math.max(0, left) }
  }
  return {
    now: server,
    asking,
    forgotten,
    lapsed,
    today: s.today_s + moving,
    total: s.total_s + moving,
    run: current && current.state !== 'stopped' ? current.seconds + moving : 0,
    current,
    box,
    boxEnded,
  }
}

/** Every second while `on`, the time now (ms). */
export function useTick(on: boolean): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!on) return
    setNow(Date.now())
    const id = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(id)
  }, [on])
  return now
}

/* ------------------------------------------------------------ a box ends */

/** Tell the person a box or break ended: a browser notification when they
    allowed it, else false (the caller shows its own banner). */
export function notify(title: string, text: string): boolean {
  try {
    if (typeof Notification !== 'undefined' && Notification.permission === 'granted') {
      new Notification(title, { body: text, tag: 'mentis-timer' })
      return true
    }
  } catch { /* a page that may not notify shows the banner */ }
  return false
}

/** Ask once for permission to notify; resolves to whether it was given. */
export async function askToNotify(): Promise<boolean> {
  if (typeof Notification === 'undefined') return false
  if (Notification.permission === 'granted') return true
  try { return (await Notification.requestPermission()) === 'granted' } catch { return false }
}

/** An ISO-8601 time as `datetime-local` writes it, in this tab's zone. */
export function localInput(iso: string): string {
  const d = new Date(iso)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`
}

/** What `datetime-local` gave, as ISO-8601 UTC (null when empty or unreadable). */
export function fromLocalInput(value: string): string | null {
  if (!value) return null
  const t = new Date(value)
  return Number.isNaN(t.getTime()) ? null : t.toISOString().replace(/\.\d{3}Z$/, 'Z')
}

/* ------------------------------------------------------------ time spent */

/** One person's time spent on a Topic, Conversation or post: their runs
    across every timer whose post names it in about= (the server's
    `time_spent`). Read, never stored. */
export interface TimeSpent {
  about: AboutRef
  holder: string
  holder_alias?: string | null
  total_s: number
  today_s: number
  timers: { post: string; block: string; part: number; title: string | null; conversation: string | null; reference: string; total_s: number; today_s: number; running: boolean; state: string }[]
}

/** Read the time spent on `ref` when drawn and again on focus; null until
    read, or when there is no `ref`. */
export function useTimeSpent(ref: string | null | undefined): TimeSpent | null {
  const [got, setGot] = useState<TimeSpent | null>(null)
  useEffect(() => {
    setGot(null)
    if (!ref) return
    let live = true
    const read = async () => {
      try {
        const r = await call(`${API}/about/${encodeURIComponent(ref)}?${dayParams()}`)
        if (live && r.status === 200 && !r.body.error && !r.body.refused) setGot(r.body as TimeSpent)
      } catch { /* a line that cannot be read is not drawn */ }
    }
    void read()
    const again = () => { if (document.visibilityState !== 'hidden') void read() }
    window.addEventListener('focus', again)
    document.addEventListener('visibilitychange', again)
    return () => { live = false; window.removeEventListener('focus', again); document.removeEventListener('visibilitychange', again) }
  }, [ref])
  return got
}
