/* NARROW WIDTHS: ONE COLUMN AND A SHEET (adm-c93a 5.6, L7; stream D).
 *
 * At 1024 px and below the conversation is the one column, as production's
 * is. What would sit beside it -- the workspace's pages, a thread, a post's
 * details -- opens in ONE full-viewport sheet under the bar, a pane at a
 * time, with pills to move between them and Back to conversation. Nothing
 * lies over anything else, so an object opened from a zone is never drawn
 * under a thread (opr-33d9fd63ae3b): the object opens in the workspace pane,
 * and closing it returns to the pane it came from.
 *
 * The sheet follows what the reader does: a thread or details opened shows
 * the thread pane; an object opened, or a page chosen, the workspace pane.
 * Presentation only, this page's only. */

import { useSyncExternalStore } from 'react'
import * as nav from '../nav'
import { onShown, pinsOf } from '../conversation/threads'
import type { PresentationClass } from '../surface/types'

/** The presentation class of a viewport width (Surface Tension §3.1):
 *  wide above 1024 px, medium 761–1024, compact 760 and below. */
export function presentationClass(width: number): PresentationClass {
  return width > 1024 ? 'wide' : width > 760 ? 'medium' : 'compact'
}

export const NARROW = '(max-width: 1024px)'
export type Pane = 'thread' | 'workspace'

const query = typeof matchMedia !== 'undefined' ? matchMedia(NARROW) : null
let narrow = !!query?.matches
let pane: Pane | null = null
const fns = new Set<() => void>()
const emit = () => fns.forEach((fn) => fn())
query?.addEventListener('change', (e) => { narrow = e.matches; if (!narrow) pane = null; emit() })

const subscribe = (fn: () => void) => { fns.add(fn); return () => { fns.delete(fn) } }
export const isNarrow = () => narrow
export const useNarrow = () => useSyncExternalStore(subscribe, isNarrow)
/** The pane the sheet shows; null: the sheet is closed. */
export const sheetPane = () => (narrow ? pane : null)
export const useSheetPane = () => useSyncExternalStore(subscribe, sheetPane)

export function openPane(p: Pane) {
  if (!narrow || pane === p) return
  pane = p
  emit()
}
/** Show the workspace's page shown (a tab or a pill chosen). */
export const showWorkspace = () => openPane('workspace')

/** Back to conversation: every temporary detail closes, and the sheet. */
export function closeSheetPane(): boolean {
  if (!narrow || !pane) return false
  pane = null
  emit()
  if (nav.snapshot().detail) nav.closeAll()
  return true
}

/* The sheet follows what the reader opens and closes. */
let was = nav.snapshot()
nav.subscribe(() => {
  const s = nav.snapshot()
  const prev = was
  was = s
  if (!narrow) return
  /* With no thread open, the thread pane still holds the pinned ones. */
  const keepThreadPane = () => pinsOf(s.conversation).pinned.length > 0
  const objectNow = s.detail?.kind === 'object'
  const objectThen = prev.detail?.kind === 'object'
  const sheetNow = nav.sheetOf(s)
  const sheetThen = nav.sheetOf(prev)
  if (objectNow && !objectThen) { openPane('workspace'); return }
  if (!objectNow && objectThen) { if (sheetNow) openPane('thread'); return }
  if (sheetNow && (!sheetThen || sheetNow !== sheetThen) && !objectNow) { openPane('thread'); return }
  if (!sheetNow && sheetThen && pane === 'thread' && !keepThreadPane()) { pane = null; emit(); return }
  if (s.page !== prev.page && s.conversation === prev.conversation) openPane('workspace')
  if (s.conversation !== prev.conversation && pane) { pane = null; emit() }
})

/* A pinned thread asked for is shown in the thread pane. */
onShown(() => openPane('thread'))
