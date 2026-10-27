/* FLICK AN OBJECT TOWARD A ZONE (#1: "drag or flick rendered content between
 * differently sized zones"; stream D). Alongside dragging a card onto a zone
 * (keep.tsx), a short, quick throw of a card keeps it in the zone it was
 * thrown toward, on the same page: a followed card is kept there, a kept one
 * MOVES there (Ctrl keeps a copy), exactly as a drop would -- with the same
 * words and Undo.
 *
 * With a mouse a flick is a native drag that ends quickly: released within
 * FLICK_MS of starting, at least FLICK_PX away, and not over another zone
 * (let go over another zone, it is that zone's drop). With a finger or a pen
 * it is the same throw by pointer. The zone chosen is the first the throw's
 * path enters, carried on from where it was let go; with none on that line,
 * the one whose middle lies closest to it, within 45 degrees; with none that
 * way, it says so and nothing moves.
 *
 * A THROW BELONGS TO WHERE IT STARTED (opr-bbc7c032e3b4). It is bound to the
 * place, the page and the card it was started from. Leave that place or page,
 * or let its card go (another post read, the zone closed), and the throw is
 * dropped: its window handlers are removed then and there, and nothing it
 * would have done is done to what is shown now. */

import * as nav from '../nav'
import type { ObjectRef } from '../present'
import { useEffect, useRef } from 'react'
import { DRAG, keepInZone } from './keep'
import { fly } from './motion'
import { workspace } from './place'

const FLICK_MS = 450
const FLICK_PX = 30
const WIDEST = Math.PI / 4

interface Throw {
  item: ObjectRef; el: HTMLElement; x: number; y: number; t: number; done: boolean
  /** where it started: the place, and the page shown */
  place: string; page: string
  /** the card that started it (one per mounted card) */
  owner: object
  /** a finger's or pen's throw: its window handlers, removed */
  stop?: () => void
}
/** The throw under way: a native drag, or a finger's or pen's. */
let throwing: Throw | null = null

const placeNow = () => `${workspace.kind}:${workspace.key ?? ''}:${nav.snapshot().conversation ?? ''}`

/** Is `th` still where it started: the same place and page, its card shown? */
const holds = (th: Throw) =>
  th.el.isConnected && placeNow() === th.place && nav.snapshot().page === th.page

/** Drop the throw under way (if it is `th`, or any when not named). */
function drop(th?: Throw | null) {
  const cur = throwing
  if (!cur || (th && cur !== th)) return
  throwing = null
  cur.done = true
  cur.stop?.()
  unwatch()
}

/* While a throw is under way, a change of place or page drops it at once,
   rather than when it is let go. */
let unwatch: () => void = () => {}
function watch() {
  unwatch()
  const check = () => { if (throwing && !holds(throwing)) drop() }
  const offNav = nav.subscribe(check)
  const offPlace = workspace.subscribe(check)
  unwatch = () => { offNav(); offPlace(); unwatch = () => {} }
}

function start(th: Throw) {
  drop()
  throwing = th
  watch()
}

/** Is the drag that ends at (x, y) now a flick? */
function isFlick(th: Throw, x: number, y: number): boolean {
  return performance.now() - th.t <= FLICK_MS && Math.hypot(x - th.x, y - th.y) >= FLICK_PX
}

/** How far along the ray from (x, y) by (dx, dy) it enters `r` (0 when it
 *  starts inside), or null when it never does. */
function entersAt(r: DOMRect, x: number, y: number, dx: number, dy: number): number | null {
  let lo = 0, hi = Infinity
  for (const [p, d, min, max] of [[x, dx, r.left, r.right], [y, dy, r.top, r.bottom]]) {
    if (!d) { if (p < min || p > max) return null; continue }
    const a = (min - p) / d, b = (max - p) / d
    lo = Math.max(lo, Math.min(a, b)); hi = Math.min(hi, Math.max(a, b))
  }
  return lo <= hi ? lo : null
}

/** The zone a throw from (x0, y0) to (x, y) goes toward, on its page: the
 *  first its path enters, carried on from where it was let go
 *  (opr-b40ba4c6d80c); with none on that line, the one whose middle lies
 *  closest to it, within 45 degrees. */
function zoneToward(th: Throw, x: number, y: number): HTMLElement | null {
  const dx = x - th.x, dy = y - th.y
  const len = Math.hypot(dx, dy) || 1
  const cells = [...document.querySelectorAll<HTMLElement>(`[data-page-tree="${CSS.escape(th.page)}"] [data-zone-id]`)]
    .filter(el => el.dataset.zoneId !== th.item.zone)
    .map(el => ({ el, r: el.getBoundingClientRect() }))
    .filter(({ r }) => r.width && r.height)
  let hit: { el: HTMLElement; at: number } | null = null
  for (const { el, r } of cells) {
    const at = entersAt(r, x, y, dx / len, dy / len)
    if (at !== null && (!hit || at < hit.at)) hit = { el, at }
  }
  if (hit) return hit.el
  let best: { el: HTMLElement; score: number } | null = null
  for (const { el, r } of cells) {
    const cx = r.left + r.width / 2 - th.x, cy = r.top + r.height / 2 - th.y
    const dist = Math.hypot(cx, cy) || 1
    const angle = Math.acos(Math.max(-1, Math.min(1, (cx * dx + cy * dy) / (dist * len))))
    if (angle > WIDEST) continue
    const score = angle + dist / 4000
    if (!best || score < best.score) best = { el, score }
  }
  return best?.el ?? null
}

/** Land the throw: keep (or move) the object in the zone it went toward --
 *  only where it started, its card still there. */
function land(th: Throw, x: number, y: number, copy: boolean) {
  const here = holds(th)
  drop(th)
  if (!here) return
  const target = zoneToward(th, x, y)
  if (!target?.dataset.zoneId) {
    nav.toast({ text: 'No zone that way: flick an object toward another zone to keep it there.' })
    return
  }
  fly(th.el, target)
  const from = th.item.kept && th.item.zone ? { page: th.page, zone: th.item.zone } : undefined
  keepInZone(th.item.address, th.page, target.dataset.zoneId, copy ? undefined : from)
}

/** A drop on zone `zoneId` while a card is thrown: is it a flick to land
 *  elsewhere rather than a drop here? (A quick release over the zone it came
 *  from is a throw; over another zone, it is that zone's drop.) */
export function flickOnDrop(e: React.DragEvent, zoneId: string): boolean {
  const th = throwing
  if (!th || th.done || th.stop || zoneId !== th.item.zone || !isFlick(th, e.clientX, e.clientY)) return false
  land(th, e.clientX, e.clientY, e.ctrlKey)
  return true
}

/** What a card, plate or row does to be dragged and flicked. A hook: the
 *  card that goes takes any throw it started with it. */
export function useFlickable(item: ObjectRef) {
  const owner = useRef<object>({}).current
  useEffect(() => () => { if (throwing?.owner === owner) drop() }, [owner])
  const begin = (el: HTMLElement, x: number, y: number): Throw => ({
    item, el, x, y, t: performance.now(), done: false, owner,
    place: placeNow(), page: item.page ?? nav.snapshot().page,
  })
  return {
    draggable: true,
    onDragStart: (e: React.DragEvent<HTMLElement>) => {
      e.dataTransfer.setData(DRAG, JSON.stringify(item))
      e.dataTransfer.setData('text/plain', item.address)
      e.dataTransfer.effectAllowed = 'copyMove'
      start(begin(e.currentTarget, e.clientX, e.clientY))
    },
    onDragEnd: (e: React.DragEvent<HTMLElement>) => {
      const th = throwing
      if (!th || th.owner !== owner || th.stop) return
      /* Let go nowhere that takes it (a gutter, outside the workspace): a
         quick throw lands in the zone it went toward. Chrome reports where
         it was let go; a browser that says (0, 0) has made no throw. */
      if (th.done || e.dataTransfer.dropEffect !== 'none' || (!e.clientX && !e.clientY) || !isFlick(th, e.clientX, e.clientY)) { drop(th); return }
      land(th, e.clientX, e.clientY, e.ctrlKey)
    },
    /* A finger or a pen throws by pointer: no native drag starts for them. */
    onPointerDown: (e: React.PointerEvent<HTMLElement>) => {
      if (e.pointerType === 'mouse' || !e.isPrimary) return
      const th = begin(e.currentTarget, e.clientX, e.clientY)
      const up = (ev: PointerEvent) => {
        if (throwing !== th) return
        if (!isFlick(th, ev.clientX, ev.clientY) || !holds(th)) { drop(th); return }
        /* the tap that ends a throw does not also open the object */
        const swallow = (c: MouseEvent) => { c.stopPropagation(); c.preventDefault() }
        window.addEventListener('click', swallow, { capture: true, once: true })
        setTimeout(() => window.removeEventListener('click', swallow, { capture: true }), 400)
        land(th, ev.clientX, ev.clientY, false)
      }
      const cancel = () => drop(th)
      th.stop = () => { window.removeEventListener('pointerup', up); window.removeEventListener('pointercancel', cancel) }
      start(th)
      window.addEventListener('pointerup', up)
      window.addEventListener('pointercancel', cancel)
    },
  }
}
