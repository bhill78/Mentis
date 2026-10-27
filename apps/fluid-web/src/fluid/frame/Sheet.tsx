/* CHOICE SHEETS (spec section 7): anchored 6px below the button that opened
 * them, one open at a time, dismissed by Esc or by a click outside -- and a
 * click outside ONLY dismisses: it does not also act. Clicking the opener
 * again while its sheet is open is such a click, so it just closes it.
 *
 * Sheets are drawn into the frame's layer (layer.tsx), not inside the bar:
 * the bar's backdrop blur would otherwise become their containing block. */

import { useEffect, useLayoutEffect, useState, useSyncExternalStore, type ReactNode } from 'react'
import { useLayer } from './layer'

interface Open { id: string; left: number; top: number; right?: number }

let open: Open | null = null
const listeners = new Set<() => void>()
const emit = () => { for (const fn of [...listeners]) fn() }
const subscribe = (fn: () => void) => { listeners.add(fn); return () => { listeners.delete(fn) } }

/** `end`: the sheet's right edge under the opener's, for a control at the
 *  bar's right end, so the sheet never runs off the window. */
export function openSheet(id: string, opener: Element, align: 'start' | 'end' = 'start') {
  const r = opener.getBoundingClientRect()
  open = align === 'end'
    ? { id, left: 0, right: Math.max(8, window.innerWidth - r.right), top: r.bottom + 6 }
    : { id, left: Math.max(8, Math.min(r.left, window.innerWidth - 320)), top: r.bottom + 6 }
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
  if (installed) return
  installed = true
  document.addEventListener('click', (e) => {
    if (!open) return
    if ((e.target as Element | null)?.closest?.('.fx-pop')) return
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

export function Sheet({ id, label, className, children }: {
  id: string
  label: string
  className?: string
  children: ReactNode
}) {
  install()
  const at = useOpenSheet()
  const [shown, setShown] = useState(false)
  const mine = at?.id === id
  useEffect(() => {
    if (!mine) { setShown(false); return }
    const r = requestAnimationFrame(() => setShown(true))
    return () => cancelAnimationFrame(r)
  }, [mine])
  /* IT STAYS IN THE WINDOW. Its anchor is the opener, but a sheet wider than
     the room on the opener's side -- search at 430px, where the bar folds and
     search is no longer at its end, or search widening for a preview -- is
     moved in until its far edge is 8px from the window's. */
  const [el, setEl] = useState<HTMLDivElement | null>(null)
  const [shift, setShift] = useState(0)
  useLayoutEffect(() => {
    setShift(0)
    if (!el || !at) return
    const fit = () => {
      const w = el.offsetWidth
      const room = at.right != null ? window.innerWidth - at.right - 8 : window.innerWidth - at.left - 8
      setShift(Math.max(0, w - room))
    }
    fit()
    const ro = new ResizeObserver(fit)
    ro.observe(el)
    window.addEventListener('resize', fit)
    return () => { ro.disconnect(); window.removeEventListener('resize', fit) }
  }, [el, at])
  useLayer(!mine || !at ? null : (
    <div ref={setEl} className={'fx-pop' + (shown ? ' open' : '') + (className ? ' ' + className : '')} role="dialog" aria-label={label}
      style={at.right != null ? { right: Math.max(8, at.right - shift), top: at.top } : { left: Math.max(8, at.left - shift), top: at.top }}>
      {children}
    </div>
  ))
  return null
}
