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
 * Presentation only, this page's only.
 *
 * PRESENTATION CLASS AND INPUT (Surface Tension §3.1; part P5). The class is
 * read from the viewport only (wide > 1024 px, medium 761–1024, compact
 * ≤ 760); "narrow" is every class but wide, so each caller of isNarrow and
 * useNarrow keeps its meaning. Input is coarse where the pointer is coarse or
 * nothing hovers. Both are read when asked (matchMedia), so a test can stand
 * in its own media queries. */

import { useSyncExternalStore } from 'react'
import * as nav from '../nav'
import { onShown, pinsOf } from '../conversation/threads'
import type { InputMode, PresentationClass } from '../surface/types'

/** The presentation class of a viewport width (Surface Tension §3.1):
 *  wide above 1024 px, medium 761–1024, compact 760 and below. */
export function presentationClass(width: number): PresentationClass {
  return width > 1024 ? 'wide' : width > 760 ? 'medium' : 'compact'
}

export const NARROW = '(max-width: 1024px)'
/** The two class boundaries, as media queries: crossing either is a class switch. */
export const CLASS_QUERIES = [NARROW, '(max-width: 760px)'] as const
/** Coarse input: a coarse pointer, or none that hovers. */
export const COARSE = '(pointer: coarse), (hover: none)'
export type Pane = 'thread' | 'workspace'

type Media = (q: string) => boolean
const media: Media = (q) => (typeof matchMedia !== 'undefined' ? matchMedia(q).matches : false)

/** The class from media queries alone (the viewport width is not read). */
export const classOf = (m: Media): PresentationClass => (!m(NARROW) ? 'wide' : m(CLASS_QUERIES[1]) ? 'compact' : 'medium')
/** The input mode from media queries. */
export const inputModeOf = (m: Media): InputMode => (m(COARSE) ? 'coarse' : 'fine')

/** The window's class now. */
export const classNow = (): PresentationClass => (typeof matchMedia !== 'undefined' ? classOf(media)
  : presentationClass(typeof innerWidth === 'number' ? innerWidth : 1280))
/** This device's input now. */
export const inputMode = (): InputMode => inputModeOf(media)

let cls: PresentationClass = classNow()
let input: InputMode = inputMode()
let pane: Pane | null = null
const fns = new Set<() => void>()
const emit = () => fns.forEach((fn) => fn())
/** Read the class and input again; tell who listens when either changed. */
export function remeasure() {
  const c = classNow(), i = inputMode()
  if (c === cls && i === input) return
  const narrowed = c !== 'wide'
  cls = c
  input = i
  if (!narrowed) pane = null
  emit()
}
if (typeof matchMedia !== 'undefined') for (const q of [...CLASS_QUERIES, COARSE]) matchMedia(q).addEventListener?.('change', remeasure)

const subscribe = (fn: () => void) => { fns.add(fn); return () => { fns.delete(fn) } }
const narrow = () => cls !== 'wide'
export const usePresentationClass = (): PresentationClass => useSyncExternalStore(subscribe, () => cls)
export const useInputMode = (): InputMode => useSyncExternalStore(subscribe, () => input)
export const isNarrow = () => narrow()
export const useNarrow = () => useSyncExternalStore(subscribe, isNarrow)
/** The pane the sheet shows; null: the sheet is closed. */
export const sheetPane = () => (narrow() ? pane : null)
export const useSheetPane = () => useSyncExternalStore(subscribe, sheetPane)

export function openPane(p: Pane) {
  if (!narrow() || pane === p) return
  pane = p
  emit()
}
/** Show the workspace's page shown (a tab or a pill chosen). */
export const showWorkspace = () => openPane('workspace')

/** Back to conversation: every temporary detail closes, and the sheet. */
export function closeSheetPane(): boolean {
  if (!narrow() || !pane) return false
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
  if (!narrow()) return
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
