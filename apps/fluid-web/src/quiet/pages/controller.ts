/* THE PAGE SEQUENCE, READ AND CHANGED. Round 5 bootstrap by S; package P owns
 * the body.
 *
 * THERE IS ONE PAGE LIST AND IT IS `nav.pages` -- the origin Holder's own,
 * ordered, with `this-post` first. This controller reads it and asks the
 * existing operations to change it; it does not keep a second list, a second
 * order or a second history, and Quiet's Page changes push nothing onto
 * Fluid's nav stack (F8): the browser hash is the destination history.
 *
 * `title` IS THE LABEL THE SEQUENCE DRAWS: Conversation for the first Page,
 * and each other Page's own title -- including a Deep dive's "Deep dive:
 * <name>", which `fluid/nav.ts` composes when the Page is made (F14) rather
 * than this controller re-deriving it.
 */
import { useSyncExternalStore } from 'react'
import { showPage, snapshot, subscribe } from '../../fluid/nav'
import type { QuietSequencePage } from '../workspace/types'
import { CONVERSATION_PAGE } from './location'

/** What the first Page is called in Quiet. The id is Fluid's `this-post`. */
export const CONVERSATION_TITLE = 'Conversation'

export interface PageSequence {
  pages: QuietSequencePage[]
  current: string
  /** 1-based, for "Page N of M" */
  position: number
  previous: QuietSequencePage | null
  next: QuietSequencePage | null
  select: (page: string) => void
}

/** THE SEQUENCE AS IT STANDS. The bootstrap reads the existing store and
 *  selects through the existing `showPage`, which already refuses a Page this
 *  place does not have; P adds the drawn controls and the `+`. */
export function usePageController(): PageSequence {
  const nav = useSyncExternalStore(subscribe, snapshot, snapshot)
  const pages: QuietSequencePage[] = nav.pages.map((p) => ({
    id: p.id,
    title: p.id === CONVERSATION_PAGE ? CONVERSATION_TITLE : 'title' in p ? p.title : p.id,
  }))
  const at = Math.max(0, pages.findIndex((p) => p.id === nav.page))
  return {
    pages,
    current: pages[at]?.id ?? CONVERSATION_PAGE,
    position: at + 1,
    previous: at > 0 ? pages[at - 1] : null,
    next: at + 1 < pages.length ? pages[at + 1] : null,
    select: showPage,
  }
}
