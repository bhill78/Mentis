/* THE CONVERSATION IS PART OF EVERY ENTRY (owner, 2026-11-20, navigation A2).
 *
 * THE DEFECT THIS ANSWERS: choosing another conversation recorded nothing in
 * the browser's history. Back did not return to the conversation before it:
 * it left Quiet Chat. And the address went on naming the conversation the
 * page was first opened on.
 *
 * `centreHistory` already keeps what is OVER the conversation in the
 * browser's history. This puts the conversation itself in each of those
 * entries (`Place`, address.ts), and nothing else changes hands: the centre's
 * own callers still say only what takes the centre (`go`, `replace`), the
 * conversation they are over is added here, and the one walk through the
 * entries is `centreHistory`'s, unchanged.
 *
 *   - ANOTHER CONVERSATION is a new entry, every time it is chosen (`open`),
 *     so Back returns to where it was chosen from. The one already shown adds
 *     nothing; where something is over it, that is left the way it always was
 *     (one step back where the conversation is behind).
 *   - THE BROWSER'S BACK AND FORWARD land on an entry that says which
 *     conversation it is, and the page is told to show it (`show`).
 *   - A CONVERSATION THE PAGE SETTLED ON BY ITSELF (the most recent one where
 *     the address named none; the one a link from the 3D Brain led to) is not
 *     a move: the entry the reader is on is corrected in place (`settle`), so
 *     the address is true and nothing is added. */
import { useRef } from 'react'
import { placeOf, type CentreAt, type Place } from './address'
import { useCentreHistory, type AskFirst, type How, type Unask } from './centreHistory'

export function usePlaces(first: Place, on: {
  /** what takes the centre, exactly as `useCentreHistory`'s own `apply` */
  apply: (to: CentreAt, from: CentreAt, how: How, asked: boolean) => void
  /** the entry landed on is of another conversation: show that one */
  show: (c: string, how: How) => void
  ask?: AskFirst
  unask?: Unask
  /** the address of a place (address.ts `addressOf`) */
  address: (to: Place) => string | null
}) {
  /** the conversation of the entry the page is on */
  const c = useRef(first.c)
  /** what is over it there */
  const over = useRef<CentreAt>(first.at)
  /** an entry being corrected in place: nothing on the page is to change */
  const quiet = useRef(false)
  const h = useCentreHistory<Place>((to, from, how, asked) => {
    const p = placeOf(to, c.current)
    const was = placeOf(from, c.current)
    over.current = p.at
    if (quiet.current) { c.current = p.c; return }
    const moved = p.c !== c.current
    c.current = p.c
    on.apply(p.at, was.at, how, asked)
    if (moved && p.c) on.show(p.c, how)
  }, on.ask, on.unask, { first, address: (to) => on.address(placeOf(to, c.current)) })
  return {
    /** A feature reader uses this same history, including its Conversation. */
    navigate: (k: string, at: CentreAt, then?: () => void) => h.push({ c: k, at }, then),
    returnTo: (place: Place, then?: () => void) => h.go(place, then),
    /** somewhere else in the centre, over the conversation shown */
    go: (to: CentreAt, then?: () => void) => h.go({ c: c.current, at: to }, then),
    /** what is in the centre becomes this, with no new entry */
    replace: (to: CentreAt) => h.replace({ c: c.current, at: to }),
    /** out of something closed: one step back where that is `to`, else in place */
    back: (to: CentreAt, then?: () => void) => h.back({ c: c.current, at: to }, then),
    /** conversation `k` itself, with nothing over it */
    open: (k: string, then?: () => void) => {
      if (k === c.current) h.go({ c: k, at: null }, then)
      else h.push({ c: k, at: null }, then)
    },
    /** the conversation shown is `k`, by the page's own doing: this entry says so */
    settle: (k: string | null) => {
      if (k === c.current) return
      quiet.current = true
      try { h.replace({ c: k, at: over.current }) } finally { quiet.current = false }
      /* a walk the browser has not finished refuses a replace: the entry it
         lands on then says which conversation it is, and the page follows */
    },
  }
}
