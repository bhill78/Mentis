/* ONE CONTENT, DRAWN ONCE, MOVED BETWEEN PLACES (types.ts).
 *
 * A content that must keep its state wherever it goes -- the conversation,
 * with its scroll, its composer's draft, a sheet half filled in -- is drawn
 * once, into its own element (`Hosted`, a portal), and that element is moved
 * into whichever place shows it (`Mount`). React never unmounts it, so
 * nothing in it is lost; only where it sits in the page changes.
 *
 * Moving an element out of the page loses its scroll offsets, so every
 * scroll inside a host is noted as it happens and put back when the host
 * lands in its next place. */

import { useLayoutEffect, useRef, type ReactNode } from 'react'
import { createPortal } from 'react-dom'

const hosts = new Map<string, HTMLDivElement>()
/** the last scroll offsets of every scroller inside a host */
const offsets = new Map<string, Map<Element, [number, number]>>()
/** the Mounts asking for each host, in the order asked: the host is in the
 *  last one of the highest claim (the Focus lens claims above the places it
 *  covers), and when that one goes it returns to the one before it -- so the
 *  conversation focused in the lens is back in its column when Focus ends */
interface Claim { me: symbol; at: HTMLDivElement | null; claim: number }
const owners = new Map<string, Claim[]>()
const holder = (id: string): Claim | undefined => {
  const xs = owners.get(id) ?? []
  let best: Claim | undefined
  for (const x of xs) if (!best || x.claim >= best.claim) best = x
  return best
}
/** where a host waits while no place shows it: in the page, out of sight */
let park: HTMLDivElement | null = null
function parking(): HTMLDivElement {
  if (!park) {
    park = document.createElement('div')
    park.className = 'fq-park'
    park.setAttribute('aria-hidden', 'true')
    park.inert = true
    document.body.appendChild(park)
  }
  return park
}

export function hostOf(id: string): HTMLDivElement {
  let el = hosts.get(id)
  if (!el) {
    el = document.createElement('div')
    el.className = 'fq-host'
    el.dataset.content = id
    const seen = new Map<Element, [number, number]>()
    offsets.set(id, seen)
    el.addEventListener('scroll', (e) => {
      const t = e.target as Element
      if (t instanceof Element) seen.set(t, [t.scrollTop, t.scrollLeft])
    }, { capture: true, passive: true })
    parking().appendChild(el)
    hosts.set(id, el)
  }
  return el
}

/* SCROLL SURVIVES BEING LENT: content the Focus lens borrows (a higher
   claim) scrolls in its tile, where a smaller height clamps it; when the lens
   gives it back, it gets the scroll it had when it was borrowed. */
const lent = new Map<string, Map<Element, [number, number]>>()

function snapshot(id: string): Map<Element, [number, number]> {
  const snap = new Map<Element, [number, number]>()
  for (const t of offsets.get(id)?.keys() ?? []) if (t.isConnected) snap.set(t, [t.scrollTop, t.scrollLeft])
  return snap
}

function apply(id: string, snap: Map<Element, [number, number]>) {
  const seen = offsets.get(id)
  for (const [t, [top, left]] of snap) {
    if (!t.isConnected) continue
    t.scrollTop = top; t.scrollLeft = left
    seen?.set(t, [t.scrollTop, t.scrollLeft])
  }
}

function restore(id: string) {
  const seen = offsets.get(id)
  if (!seen) return
  for (const [t, [top, left]] of seen) {
    if (!t.isConnected) { seen.delete(t); continue }
    if (t.scrollTop !== top) t.scrollTop = top
    if (t.scrollLeft !== left) t.scrollLeft = left
  }
}

/** Draw `children` once, into content `id`'s own element. Render it where
 *  its props and context are (the Shell, for the conversation). */
export function Hosted({ id, children }: { id: string; children: ReactNode }) {
  return createPortal(children, hostOf(id))
}

/** The place that shows content `id` now: its element is moved in here, and
 *  back to the place before it (or the parking place) when this place goes.
 *  `claim`: a place drawn over the others (the Focus lens) claims above them. */
export function Mount({ id, className, claim = 0 }: { id: string; className?: string; claim?: number }) {
  const at = useRef<HTMLDivElement | null>(null)
  useLayoutEffect(() => {
    const me: Claim = { me: Symbol(id), at: at.current, claim }
    const host = hostOf(id)
    owners.set(id, [...(owners.get(id) ?? []), me])
    if (holder(id) === me) {
      if (claim > 0 && host.parentElement !== parking() && !lent.has(id)) lent.set(id, snapshot(id))
      me.at?.appendChild(host); restore(id)
    }
    return () => {
      const was = holder(id) === me
      const left = (owners.get(id) ?? []).filter((x) => x !== me)
      if (left.length) owners.set(id, left)
      else owners.delete(id)
      if (!was) return
      const next = holder(id)
      if (next?.at?.isConnected) {
        next.at.appendChild(host); restore(id)
        const snap = claim > 0 && next.claim < claim ? lent.get(id) : undefined
        if (snap) { lent.delete(id); apply(id, snap); requestAnimationFrame(() => apply(id, snap)) }
      }
      else if (host.parentElement === me.at) parking().appendChild(host)
    }
  }, [id, claim])
  return <div ref={at} className={'fq-mount' + (className ? ' ' + className : '')} data-mount={id} />
}

/** Is content `id` shown in a place now (not parked)? */
export const isMounted = (id: string) => owners.has(id)
