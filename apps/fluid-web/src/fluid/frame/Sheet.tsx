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

export interface RectLike {
  top: number
  bottom: number
  left: number
  right: number
  width?: number
  height?: number
}

export interface SizeLike {
  width?: number
  height?: number
}

export interface ViewportLike {
  width: number
  height: number
}

export interface SheetPosition {
  left?: number
  right?: number
  top: number
  max?: number
  up: boolean
}

/** Pure placement maths: fits a sheet adjacent to its anchor inside the viewport.
 *  Opens 6px below by default; flips 6px above when there is no room below and
 *  room above; clamps horizontally with 8px margin; caps max-height so it
 *  scrolls inside itself if taller than the room (like composer/Float.tsx). */
export function placeSheet(
  anchor: RectLike,
  pop: SizeLike,
  viewport: ViewportLike,
  align: 'start' | 'end' = 'start',
): SheetPosition {
  const winW = viewport.width
  const winH = viewport.height

  const w = Math.max(1, pop.width ?? 320)
  const natural = Math.max(1, pop.height ?? 240)

  // 6px gap from anchor, 8px margin from viewport edges (14px total)
  const above = Math.floor(anchor.top - 14)
  const below = Math.floor(winH - anchor.bottom - 14)

  // Flip above when there is no room below, and either room above or more room above than below
  const up = natural > below && (natural <= above || above >= below)
  const room = Math.max(80, up ? above : below)
  const h = Math.min(natural, room)

  const top = Math.round(up ? Math.max(8, anchor.top - h - 6) : Math.max(8, Math.min(anchor.bottom + 6, winH - h - 8)))
  const max = natural > room ? room : undefined

  if (align === 'end') {
    const baseRight = winW - anchor.right
    const right = Math.round(Math.max(8, Math.min(baseRight, winW - w - 8)))
    return { right, top, max, up }
  } else {
    const left = Math.round(Math.max(8, Math.min(anchor.left, winW - w - 8)))
    return { left, top, max, up }
  }
}

/** `end`: the sheet's right edge under the opener's, for a control at the
 *  bar's right end, so the sheet never runs off the window. */
export function openSheet(id: string, opener: Element, align: 'start' | 'end' = 'start') {
  const r = opener.getBoundingClientRect()
  const winW = typeof window !== 'undefined' ? window.innerWidth : 1024
  const winH = typeof window !== 'undefined' ? window.innerHeight : 768
  const pos = placeSheet(r, { width: 320, height: 240 }, { width: winW, height: winH }, align)
  open = {
    id,
    opener,
    align,
    left: pos.left ?? 0,
    right: pos.right,
    top: pos.top,
  }
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

  const [layout, setLayout] = useState<SheetPosition | null>(null)

  useLayoutEffect(() => {
    if (!mine) { setLayout(null); return }

    const fit = () => {
      const winW = typeof window !== 'undefined' ? window.innerWidth : 1024
      const winH = typeof window !== 'undefined' ? window.innerHeight : 768

      if (opener && 'isConnected' in opener && !opener.isConnected) {
        if (isById) closeSheet()
        else (props as SheetByAnchorProps).onClose?.()
        return
      }

      const r = opener?.getBoundingClientRect() ?? null
      if (!r) { setLayout(null); return }

      const w = el ? el.offsetWidth : 320
      const h = el ? el.scrollHeight : 240

      const pos = placeSheet(r, { width: w, height: h }, { width: winW, height: winH }, align)
      setLayout((prev) => {
        if (
          prev &&
          prev.left === pos.left &&
          prev.right === pos.right &&
          prev.top === pos.top &&
          prev.max === pos.max &&
          prev.up === pos.up
        ) {
          return prev
        }
        return pos
      })
    }

    fit()

    if (!el) return
    const ro = new ResizeObserver(fit)
    ro.observe(el)
    if (opener && typeof Node !== 'undefined' && opener instanceof Element) {
      ro.observe(opener)
    }
    window.addEventListener('resize', fit)
    window.addEventListener('scroll', fit, true)
    return () => {
      ro.disconnect()
      window.removeEventListener('resize', fit)
      window.removeEventListener('scroll', fit, true)
    }
  }, [mine, el, opener, align, isById, props])

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
        const winW = typeof window !== 'undefined' ? window.innerWidth : 1024
        const winH = typeof window !== 'undefined' ? window.innerHeight : 768
        const pos = placeSheet(r, { width: 320, height: 240 }, { width: winW, height: winH }, 'start')
        return {
          ...(pos.right != null ? { right: pos.right } : { left: pos.left ?? 8 }),
          top: pos.top,
          ...(pos.max != null ? { maxHeight: pos.max, overflowY: 'auto' as const } : {}),
        }
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
