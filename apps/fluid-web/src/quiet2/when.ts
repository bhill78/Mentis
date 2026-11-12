/* WHEN A POST WAS WRITTEN, AS QUIET CHAT SAYS IT.
 *
 * Relative while it is recent -- "just now", "5m ago", "2h ago" -- for the
 * first twelve hours; after that a date and time a reader can place without
 * arithmetic: "Today, 9:14 AM", "Yesterday, 9:14 AM", "Nov 3, 9:14 AM", and
 * the year once it is not this one. The exact moment (weekday, date, time to
 * the second, time zone) is always available beside it (Byline's `<time>`,
 * on hover and on keyboard focus).
 *
 * KEPT CURRENT BY THE PAGE ALONE. `useNow` is one client-side clock shared by
 * every timestamp drawn: it ticks while at least one is drawn and stops when
 * none is. Nothing is asked of the server. */
import { useSyncExternalStore } from 'react'

/** How long a time is said relatively, in seconds. */
export const RELATIVE_FOR = 12 * 3600
/** Under this many seconds, "just now". */
export const JUST_NOW = 45

const sameDay = (a: Date, b: Date) => a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate()

/** `at` said for a reader at `now` (both epoch seconds). `locale` is for tests. */
export function whenSaid(at: number, now: number, locale?: string): string {
  const ago = now - at
  /* a clock a little ahead of this one: still just now, never "in 2m" */
  if (ago < JUST_NOW && ago > -5 * 60) return 'just now'
  if (ago >= 0 && ago < 3600) return `${Math.max(1, Math.floor(ago / 60))}m ago`
  if (ago >= 0 && ago < RELATIVE_FOR) return `${Math.floor(ago / 3600)}h ago`
  const d = new Date(at * 1000)
  const today = new Date(now * 1000)
  const yesterday = new Date(today.getFullYear(), today.getMonth(), today.getDate() - 1)
  const time = d.toLocaleTimeString(locale ?? [], { hour: 'numeric', minute: '2-digit' })
  if (sameDay(d, today)) return `Today, ${time}`
  if (sameDay(d, yesterday)) return `Yesterday, ${time}`
  const date = d.toLocaleDateString(locale ?? [], d.getFullYear() === today.getFullYear()
    ? { month: 'short', day: 'numeric' } : { month: 'short', day: 'numeric', year: 'numeric' })
  return `${date}, ${time}`
}

/** The exact moment, in full: what hover and focus show. */
export function whenExact(at: number, locale?: string): string {
  return new Date(at * 1000).toLocaleString(locale ?? [], {
    weekday: 'long', year: 'numeric', month: 'long', day: 'numeric',
    hour: 'numeric', minute: '2-digit', second: '2-digit', timeZoneName: 'short',
  })
}

/* -- the shared clock ----------------------------------------------------- */

/** How often the clock moves while a timestamp is drawn (ms). */
export const TICK_MS = 30_000
let now = Math.floor(Date.now() / 1000)
let timer: ReturnType<typeof setInterval> | null = null
const heard = new Set<() => void>()

function subscribe(fn: () => void) {
  heard.add(fn)
  if (!timer) {
    now = Math.floor(Date.now() / 1000)
    timer = setInterval(() => { now = Math.floor(Date.now() / 1000); heard.forEach((f) => f()) }, TICK_MS)
  }
  return () => {
    heard.delete(fn)
    if (!heard.size && timer) { clearInterval(timer); timer = null }
  }
}

/** The page's clock in epoch seconds, moving every TICK_MS while anything
 *  that uses it is drawn. */
export const useNow = () => useSyncExternalStore(subscribe, () => now)

/** Whether the shared clock is running (for tests). */
export const clockRunning = () => timer !== null
