import { useSyncExternalStore } from 'react'

/* ------------------------------------------------------------------------ *
 * RECENCY HEAT (uiux/turn item 6).
 *
 * How recently a Turn was said, in five steps, so a person scanning a busy
 * Conversation can see what just happened without reading every time.
 *
 * IT IS READ FROM THE TURN'S OWN TIME AND NOTHING ELSE. No "seen" state, no
 * "new since you last looked", nothing stored: the same Turn is equally warm
 * for everybody looking at it, and it cools because the clock moved, never
 * because somebody did.
 *
 * Five-minute bands, newest strongest: 0-5 minutes is 5, 5-10 is 4, and so on
 * down to 20-25 minutes at 1. From 25 minutes a Turn is ordinary. A Turn
 * stamped a little in the future (a skewed clock) counts as just said.
 * ------------------------------------------------------------------------ */

export const HEAT_BAND_S = 5 * 60
export const HEAT_LEVELS = 5

export function heatOf(at: number | null | undefined, nowMs: number): number {
  if (!at) return 0
  const age = Math.max(0, nowMs / 1000 - at)
  return Math.max(0, HEAT_LEVELS - Math.floor(age / HEAT_BAND_S))
}

/* ONE CLOCK FOR EVERY TURN. It runs only while some Turn is still warm, and a
   Turn listens only while it is: an hour-old Conversation subscribes nothing
   and re-renders nothing. A Turn re-renders when its own step changes, not on
   every tick, because what it reads is the step. */
const TICK_MS = 20_000
const listeners = new Set<() => void>()
let timer: number | null = null

function subscribe(fn: () => void): () => void {
  listeners.add(fn)
  if (timer === null) timer = window.setInterval(() => listeners.forEach((l) => l()), TICK_MS)
  return () => {
    listeners.delete(fn)
    if (listeners.size === 0 && timer !== null) {
      window.clearInterval(timer)
      timer = null
    }
  }
}
const still = () => () => {}

export function useHeat(at: number | null | undefined): number {
  const warm = heatOf(at, Date.now()) > 0
  return useSyncExternalStore(warm ? subscribe : still, () => heatOf(at, Date.now()))
}
