/* A choice sheet anchored 6px below the control that opened it (spec 7):
 * Esc or a click outside dismisses it, and that click does nothing else. */

import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { useLayer } from '../frame/layer'

export function Sheet({ anchor, onClose, children, label }: {
  anchor: HTMLElement | null; onClose: () => void; children: ReactNode; label: string
}) {
  const ref = useRef<HTMLDivElement | null>(null)
  const [at, setAt] = useState<{ left: number; top: number } | null>(null)
  const [open, setOpen] = useState(false)
  useLayoutEffect(() => {
    if (!anchor) return
    const r = anchor.getBoundingClientRect()
    setAt({ left: Math.max(8, Math.min(r.left, innerWidth - 320)), top: r.bottom + 6 })
    const raf = requestAnimationFrame(() => setOpen(true))
    return () => cancelAnimationFrame(raf)
  }, [anchor])
  /* IT STAYS ON SCREEN (integration): a zone's sheet now holds Show as and
     Appearance too, so opened from a low zone it ran off the window's foot.
     Once drawn (in the frame's layer, a frame later), it opens above its
     control when there is more room there, and scrolls within the window
     when it is taller than either side. */
  const [fit, setFit] = useState<{ top: number; max?: number } | null>(null)
  useEffect(() => {
    if (!at || !anchor) return
    const raf = requestAnimationFrame(() => {
      const el = ref.current
      if (!el) return
      const r = anchor.getBoundingClientRect()
      const h = el.scrollHeight
      const below = innerHeight - r.bottom - 14
      const above = r.top - 14
      if (h <= below) { setFit(null); return }
      if (h <= above || above > below) setFit({ top: Math.max(8, r.top - 6 - Math.min(h, above)), max: h > above ? above : undefined })
      else setFit({ top: r.bottom + 6, max: below })
    })
    return () => cancelAnimationFrame(raf)
  }, [at, anchor])
  useEffect(() => {
    const outside = (e: MouseEvent) => {
      if (ref.current?.contains(e.target as Node)) return
      e.stopPropagation()
      e.preventDefault()
      onClose()
    }
    const esc = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      e.stopPropagation()
      e.preventDefault()
      onClose()
    }
    /* Captured on the window, so nothing under the click or the key acts. */
    const t = setTimeout(() => window.addEventListener('click', outside, true), 0)
    window.addEventListener('keydown', esc, true)
    return () => {
      clearTimeout(t)
      window.removeEventListener('click', outside, true)
      window.removeEventListener('keydown', esc, true)
    }
  }, [onClose])
  useLayer(
    <div ref={ref} className={'wk-pop' + (open ? ' open' : '')} role="menu" aria-label={label}
      style={at ? { left: at.left, top: fit?.top ?? at.top, ...(fit?.max ? { maxHeight: fit.max, overflowY: 'auto' } : {}) } : { visibility: 'hidden' }}>
      {children}
    </div>,
  )
  return null
}

export const Sec = ({ children }: { children: ReactNode }) => <div className="wk-sec">{children}</div>

/** A choice; one that is `off` says `why`, under its words, when given. */
export function Opt({ children, onPick, on, off, title, why, onHover, says }: {
  children: ReactNode; onPick?: () => void; on?: boolean; off?: boolean; title?: string; why?: string | null
  /** a short line under it saying what it does (the Lab's FOLLOWS `says`) */
  says?: string
  /** pointed at or focused (true), or left (false): what it would act on can show itself */
  onHover?: (on: boolean) => void
}) {
  const said = off && why ? why : null
  return (
    <button className={'wk-opt' + (on ? ' on' : '') + (off ? ' off' : '') + (said ? ' wk-why' : '')} role="menuitem" disabled={off} title={title ?? said ?? undefined}
      aria-checked={on === undefined ? undefined : on} onClick={onPick}
      onMouseEnter={onHover && (() => onHover(true))} onMouseLeave={onHover && (() => onHover(false))}
      onFocus={onHover && (() => onHover(true))} onBlur={onHover && (() => onHover(false))}>
      {on !== undefined && <span className="wk-tick" aria-hidden="true">{on ? '✓' : ''}</span>}
      <span>{children}{says && <small className="wk-says">{says}</small>}{said && <small className="wk-whynot">{said}</small>}</span>
    </button>
  )
}
