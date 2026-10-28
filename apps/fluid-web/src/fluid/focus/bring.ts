/* MAKE PRIMARY, AND ESC BACK, AT EVERY WIDTH (narrowView.ts). On the desktop
 * they swap places in the arrangement, as the prototype does. At a narrow
 * width there is one column and one sheet, so a swap would rewrite the
 * desktop's arrangement for nothing it could show: instead the content is
 * brought into view where the narrow screen shows it -- the column, or the
 * workspace pane scrolled to its section or float, which pulses. The
 * arrangement is not touched. Every ◎, 1-9 and Esc goes through here, and
 * acts on the page shown (page.ts). */

import * as nav from '../nav'
import { closeSheetPane, isNarrow, openPane, sheetPane } from '../frame/narrow'
import { workspace } from '../workspace/place'
import { makePrimary, swapBack } from './model'
import { previousPrimary, seenAt } from './narrowView'
import { onPage, pageIn, pageView, shownPage } from './page'

/** ◎ / 1-9: make `id` primary (desktop), or bring it into view (narrow).
 *  `then` runs after a desktop swap (a pulse where it arrived). */
export function bringPrimary(id: string, words?: string, then?: () => void) {
  if (isNarrow()) { reveal(id); return }
  workspace.edit(onPage((v) => makePrimary(v, id)), words)
  then?.()
}

/** Esc: back to the previous primary (desktop), or, narrow with the sheet
 *  closed, bring it into view; with the sheet (or a detail) open Esc is the
 *  Shell's, as it was before Fluid Focus. True when it did something. */
export function stepBack(): boolean {
  const a = workspace.arr
  if (isNarrow()) {
    if (sheetPane() || nav.snapshot().detail) return false
    const id = previousPrimary(pageView(a))
    if (!id) return false
    reveal(id)
    return true
  }
  const next = onPage(swapBack)(a)
  if (next === a) return false
  workspace.edit(() => next, 'Returned to the previous primary.')
  return true
}

/** Show content `id` where a narrow screen has it on the page shown, without
 *  moving it. Done on the next frame, so the key or click that asked has
 *  finished with the sheet first (Shell's Esc closes it). */
export function reveal(id: string) {
  const page = pageIn(workspace.arr, shownPage())
  const at = seenAt(pageView(workspace.arr, page), id)
  if (!at) return
  requestAnimationFrame(() => {
    if (at.in === 'column') { closeSheetPane(); return }
    if (nav.snapshot().page !== page) nav.showPage(page)
    openPane('workspace')
    /* the pane is drawn, and its tree laid out, before it is scrolled */
    setTimeout(() => {
      const el = at.in === 'leaf'
        ? document.querySelector<HTMLElement>(`.wk-page[data-page="${CSS.escape(page)}"] .wt-cell[data-zone-id="${CSS.escape(at.zone)}"]`)
        : document.querySelector<HTMLElement>(`.fq-nfloat[data-float-id="${CSS.escape(at.float)}"]`)
      if (!el) return
      const still = matchMedia('(prefers-reduced-motion: reduce)').matches
      el.scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: still ? 'auto' : 'smooth' })
      el.classList.remove('arrived'); void el.offsetWidth; el.classList.add('arrived')
    }, 80)
  })
}
