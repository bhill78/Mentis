import { useCallback, useEffect, useRef } from 'react'
import { handsOn } from './hands'

/* ------------------------------------------------------------------------ *
 * A PRESS COUNTS ONLY ON THE THING THAT WAS AIMED AT (opr-e87efe7171a7).
 *
 * The owner chose the wrong decision more than once because the options
 * moved between aiming and tapping: a refresh landed, the list under the
 * finger slid, and the tap went to the neighbour. A wrong decision is a
 * recorded act, so this is correctness, not comfort.
 *
 * For a group of controls (a decision's options, a list's rows) a pointer
 * press is accepted only when
 *   - the pointer went down and came up on the same control,
 *   - that control is still the same element and has not moved since, and
 *   - it was not moving just before the pointer went down (the reader aimed
 *     at where it was, and it was somewhere else by the time they arrived).
 * Otherwise the press does nothing at all: it is never passed on to
 * whatever is now under the finger. Keyboard activation (`detail === 0`) is
 * not aimed by position and is always accepted.
 *
 * "Moving" is measured, every frame, while the group is on screen -- and
 * only movement the reader did not make: their own scrolling (a finger, a
 * wheel, a glide) moves things too, and they can see it coming.
 * ------------------------------------------------------------------------ */

/** how long a control must have held still before a press on it counts */
export const STILL_MS = 350
const SLACK = 1.5

type Down = { el: HTMLElement; x: number; y: number; t: number }

export function useSteadyPress(group: React.RefObject<HTMLElement | null>, sel = 'button') {
  const movedAt = useRef(-1e9)
  const down = useRef<Down | null>(null)

  useEffect(() => {
    const el = group.current
    if (!el || typeof IntersectionObserver === 'undefined') return
    let raf = 0
    let last: string | null = null
    const sample = () => {
      const now = performance.now()
      /* each control's position, so a control moving inside a group that
         holds still (one above it changing size) is caught as well */
      const key = Array.from(el.querySelectorAll<HTMLElement>(sel))
        .map((c) => {
          const r = c.getBoundingClientRect()
          return `${Math.round(r.left)},${Math.round(r.top)},${Math.round(r.height)}`
        })
        .join('|')
      if (last !== null && key !== last && !handsOn()) movedAt.current = now
      last = key
      raf = requestAnimationFrame(sample)
    }
    const io = new IntersectionObserver(([e]) => {
      cancelAnimationFrame(raf)
      last = null
      if (e?.isIntersecting) raf = requestAnimationFrame(sample)
    })
    io.observe(el)
    return () => {
      io.disconnect()
      cancelAnimationFrame(raf)
    }
  }, [group, sel])

  /** on the group, in the capture phase: which control the pointer went down on */
  const onPointerDownCapture = useCallback((e: React.PointerEvent) => {
    const c = (e.target as Element).closest<HTMLElement>(sel)
    if (!c || !e.currentTarget.contains(c)) {
      down.current = null
      return
    }
    const r = c.getBoundingClientRect()
    down.current = { el: c, x: r.left, y: r.top, t: performance.now() }
  }, [sel])

  /** in a control's click handler: false means do nothing */
  const accept = useCallback((e: React.MouseEvent<HTMLElement>): boolean => {
    if (e.detail === 0) return true
    const d = down.current
    down.current = null
    const c = e.currentTarget
    if (!d || d.el !== c || !c.isConnected) return false
    const r = c.getBoundingClientRect()
    if (Math.abs(r.left - d.x) > SLACK || Math.abs(r.top - d.y) > SLACK) return false
    // it moved while the finger was down, or had only just stopped moving
    if (movedAt.current >= d.t - STILL_MS) return false
    return true
  }, [])

  return { onPointerDownCapture, accept }
}

/** Whether an ask owed by the reader -- a decision with its options, or a
 *  question with its answer box -- is at least partly in view in `box`. While
 *  one is, nothing follows the newest away from it (opr-e87efe7171a7). */
export function owedInView(box: HTMLElement): boolean {
  const b = box.getBoundingClientRect()
  for (const p of Array.from(box.querySelectorAll<HTMLElement>('.rb-decision:not([data-state="closed"]):not(.rb-dec-left)'))) {
    const r = p.getBoundingClientRect()
    if (r.bottom > b.top && r.top < b.bottom) return true
  }
  return false
}
