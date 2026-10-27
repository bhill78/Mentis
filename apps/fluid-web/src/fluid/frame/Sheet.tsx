/* CHOICE SHEETS (spec section 7): anchored 6px below the button that opened
 * them, one open at a time (or anchored per-element), dismissed by Esc or by a
 * click outside -- and a click outside ONLY dismisses: it does not also act.
 * Clicking the opener again while its sheet is open is such a click, so it just
 * closes it.
 *
 * Better fitting: opens above its control when there is more room there, shifts
 * to stay in the window horizontally (min 8px), and scrolls within the window
 * when it is taller than either side.
 *
 * Drawn into the frame's layer (layer.tsx), outside every panel. */

import { useEffect, useLayoutEffect, useState, useSyncExternalStore, type ReactNode } from 'react'
import { useLayer } from './layer'

export interface Open {
  id: string
  opener?: Element | null
  align?: 'start' | 'end'
  left: number
  top: number
  right?: number
}

let open: Open | null = null
const listeners = new Set<() => void>()
const emit = () => { for (const fn of [...listeners]) fn() }
const subscribe = (fn: () => void) => { listeners.add(fn); return () => { listeners.delete(fn) } }

/** `end`: the sheet's right edge under the opener's, for a control at the
 *  bar's right end, so the sheet never runs off the window. */
export function openSheet(id: string, opener: Element, align: 'start' | 'end' = 'start') {
  const r = opener.getBoundingClientRect()
  open = align === 'end'
    ? { id, opener, align, left: 0, right: Math.max(8, window.innerWidth - r.right), top: r.bottom + 6 }
    : { id, opener, align, left: Math.max(8, Math.min(r.left, window.innerWidth - 320)), top: r.bottom + 6 }
  emit()
}

export function closeSheet(): boolean {
  if (!open) return false
  open = null
  emit()
  return true
}

export const sheetOpen = () => open !== null
export const useOpenSheet = () => useSyncExternalStore(subscribe, () => open)

/* WHAT IS OPEN INSIDE A SHEET TAKES THE FIRST Esc (#568 1.3: a search
   result's preview closes before the search does). A sheet's body says so
   while it has something to close: `true` from it means Esc was used. */
let inner: (() => boolean) | null = null
export function useSheetEscape(fn: (() => boolean) | null) {
  useEffect(() => {
    if (!fn) return
    inner = fn
    return () => { if (inner === fn) inner = null }
  }, [fn])
}

let installed = false
function install() {
  if (installed || typeof document === 'undefined') return
  installed = true
  document.addEventListener('click', (e) => {
    if (!open) return
    if ((e.target as Element | null)?.closest?.('.fx-pop, .wk-pop')) return
    e.preventDefault()
    e.stopPropagation()
    closeSheet()
  }, true)
  document.addEventListener('keydown', (e) => {
    if (open && e.key === 'Escape') {
      e.preventDefault()
      e.stopPropagation()
      if (inner?.()) return
      closeSheet()
    }
  }, true)
}

export interface SheetByIdProps {
  id: string
  anchor?: undefined
  onClose?: () => void
  label: string
  className?: string
  role?: string
  children: ReactNode
}

export interface SheetByAnchorProps {
  id?: undefined
  anchor: HTMLElement | null
  onClose: () => void
  label: string
  className?: string
  role?: string
  children: ReactNode
}

export type SheetProps = SheetByIdProps | SheetByAnchorProps

export function Sheet(props: SheetProps) {
  const isById = 'id' in props && props.id != null
  if (isById) {
    install()
  }

  const at = useOpenSheet()
  const mine = isById ? at?.id === props.id : !!props.anchor
  const [shown, setShown] = useState(false)

  useEffect(() => {
    if (!mine) { setShown(false); return }
    const r = requestAnimationFrame(() => setShown(true))
    return () => cancelAnimationFrame(r)
  }, [mine])

  const [el, setEl] = useState<HTMLDivElement | null>(null)

  const opener = isById ? (at?.opener ?? null) : props.anchor
  const align = isById ? (at?.align ?? 'start') : 'start'

  const [layout, setLayout] = useState<{ left?: number; right?: number; top: number; max?: number } | null>(null)

  useLayoutEffect(() => {
    if (!mine) { setLayout(null); return }

    const fit = () => {
      const winW = typeof window !== 'undefined' ? window.innerWidth : 1024
      const winH = typeof window !== 'undefined' ? window.innerHeight : 768

      const r = opener?.getBoundingClientRect() ?? null

      // Horizontal
      let left: number | undefined
      let right: number | undefined

      if (align === 'end') {
        const baseRight = r ? Math.max(8, winW - r.right) : (at?.right ?? 8)
        const w = el ? el.offsetWidth : 320
        const room = winW - baseRight - 8
        const shift = Math.max(0, w - room)
        right = Math.max(8, baseRight - shift)
      } else {
        const baseLeft = r ? Math.max(8, Math.min(r.left, winW - 320)) : (at?.left ?? 8)
        const w = el ? el.offsetWidth : 320
        const room = winW - baseLeft - 8
        const shift = Math.max(0, w - room)
        left = Math.max(8, baseLeft - shift)
      }

      // Vertical (opens above when there is more room, scrolls when taller)
      let top = r ? r.bottom + 6 : (at?.top ?? 8)
      let max: number | undefined

      if (r && el) {
        const h = el.scrollHeight
        const below = winH - r.bottom - 14
        const above = r.top - 14
        if (h <= below) {
          top = r.bottom + 6
          max = undefined
        } else if (h <= above || above > below) {
          top = Math.max(8, r.top - 6 - Math.min(h, above))
          max = h > above ? above : undefined
        } else {
          top = r.bottom + 6
          max = below
        }
      }

      setLayout({ left, right, top, max })
    }

    fit()

    if (!el) return
    const ro = new ResizeObserver(fit)
    ro.observe(el)
    window.addEventListener('resize', fit)
    return () => {
      ro.disconnect()
      window.removeEventListener('resize', fit)
    }
  }, [mine, el, opener, align, at])

  // Window dismiss listeners for anchor call style
  useEffect(() => {
    if (isById || !props.anchor) return
    const outside = (e: MouseEvent) => {
      if (el?.contains(e.target as Node)) return
      if ((e.target as Element | null)?.closest?.('.fx-pop, .wk-pop')) return
      e.stopPropagation()
      e.preventDefault()
      props.onClose?.()
    }
    const esc = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      e.stopPropagation()
      e.preventDefault()
      if (inner?.()) return
      props.onClose?.()
    }
    const t = setTimeout(() => window.addEventListener('click', outside, true), 0)
    window.addEventListener('keydown', esc, true)
    return () => {
      clearTimeout(t)
      window.removeEventListener('click', outside, true)
      window.removeEventListener('keydown', esc, true)
    }
  }, [isById, props.anchor, (props as SheetByAnchorProps).onClose, el])

  const baseClass = isById ? 'fx-pop' : 'wk-pop'
  const role = props.role ?? (isById ? 'dialog' : 'menu')

  const initialStyle = isById
    ? (at?.right != null ? { right: at.right, top: at.top } : { left: at?.left ?? 8, top: at?.top ?? 8 })
    : (opener ? (() => {
        const r = opener.getBoundingClientRect()
        return { left: Math.max(8, Math.min(r.left, window.innerWidth - 320)), top: r.bottom + 6 }
      })() : { visibility: 'hidden' as const })

  const computedStyle = layout
    ? {
        ...(layout.right != null ? { right: layout.right } : { left: layout.left ?? 8 }),
        top: layout.top,
        ...(layout.max != null ? { maxHeight: layout.max, overflowY: 'auto' as const } : {}),
      }
    : initialStyle

  useLayer(
    !mine ? null : (
      <div
        ref={setEl}
        className={`${baseClass}${shown ? ' open' : ''}${props.className ? ' ' + props.className : ''}`}
        role={role}
        aria-label={props.label}
        style={computedStyle}
      >
        {props.children}
      </div>
    ),
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
