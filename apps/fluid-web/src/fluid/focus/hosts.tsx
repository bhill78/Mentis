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
/** the Mount that holds each host now, so only the last one asked keeps it */
const owner = new Map<string, symbol>()
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
 *  back to the parking place when this place goes. */
export function Mount({ id, className }: { id: string; className?: string }) {
  const at = useRef<HTMLDivElement | null>(null)
  useLayoutEffect(() => {
    const me = Symbol(id)
    const host = hostOf(id)
    owner.set(id, me)
    at.current?.appendChild(host)
    restore(id)
    return () => {
      if (owner.get(id) !== me) return
      owner.delete(id)
      if (host.parentElement === at.current) { parking().appendChild(host); }
    }
  }, [id])
  return <div ref={at} className={'fq-mount' + (className ? ' ' + className : '')} data-mount={id} />
}

/** Is content `id` shown in a place now (not parked)? */
export const isMounted = (id: string) => owner.has(id)
