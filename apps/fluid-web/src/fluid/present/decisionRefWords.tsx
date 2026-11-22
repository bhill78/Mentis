/* FLUID'S OWN WAY OF OPENING THE EXACT RECORD A DECISION NAMES (review
 * finding F2 of the combined review, ent-b45998589533).
 *
 * The shared decision form draws its one primary source as the host opens one
 * (`experimental/refWords` `open`). Quiet Chat's Needs you supplies that, so a
 * question there is inspected before it is answered. THE SAME SHARED FORM
 * DRAWN IN FLUID -- the conversation column, a post, the thread sheet, full
 * screen, the Needs You zone and governance's asks -- supplied no host at all,
 * so a present, declared, resolved exact record printed "it cannot be opened
 * from here; the asking post has it" and offered no control. The requirement
 * the form answers to is that the specific material can be inspected, so that
 * sentence was a limitation, not an answer.
 *
 * WHAT THIS OPENS, AND WHAT IT NEVER OPENS. THE EXACT ID THE QUESTION DECLARED
 * (`decisionPresentation` `refOpens`), and only that id. Nothing is inferred:
 * not the asking post, not the first reference, not the nearest similarly
 * named thing, and no title is matched.
 *
 * READ AS WHAT IT IS. A declared record may be a post somebody wrote or a
 * durable record, and the question's own declaration says only `record`. So
 * the id is looked up as itself, through the read Fluid already makes for a
 * post (`../store` `loadPosts`, which answers an error for an id that is not
 * one), and Peek draws it the way that page draws it: `post:<id>` reads the
 * post in full, `brain:<entry>` reads the record's own inspector. ONE id
 * either way, and a lookup that answers nothing still opens THAT id in the
 * record inspector, which says what the record holds of it.
 *
 * Where this page has no viewer to draw it in (`useViewerHosted`), no opener
 * is offered and the form says what it said before -- an opener that opens
 * nothing would be worse than the sentence.
 *
 * AND COMING BACK KEEPS THE HALF-MADE ANSWER. Peek is drawn OVER the
 * workspace: the form it was opened from is never unmounted, so what was
 * chosen and typed is exactly as it was left, and Esc (or Peek's own ‹) is
 * the way back. Nothing here sends anything, and nothing here resolves how a
 * reference stands -- `standing` is deliberately absent, so the form reads the
 * material for itself through the one server read, as it does today
 * (`experimental/materialStanding`).
 *
 * Presentation only. */
import { useMemo, type ReactNode } from 'react'
import { RefWordsContext, type RefWords } from '../../experimental/refWords'
import { BRAIN_REF } from '../brain/address'
import { store } from '../store'
import { inspect, POST_REF, useViewerHosted } from './viewer'

/** Said on the control, before it is pressed: what it opens, and that leaving
 *  the form for it costs nothing. */
export const OPENS_SAYS = 'Opens this exact record here. What you have chosen and typed is kept; Esc comes back to it.'

/** THIS EXACT ID, as the page can read it: a post in full where the id is one,
 *  and otherwise the record's own inspector. The lookup is of that id and no
 *  other, and an id nothing answers for still opens as that id. */
export async function openExact(id: string, from: HTMLElement | null): Promise<void> {
  let post = store.posts.has(id)
  if (!post) {
    try {
      await store.loadPosts([id])
      post = store.posts.has(id)
    } catch {
      post = false
    }
  }
  inspect((post ? POST_REF : BRAIN_REF) + id, from)
}

/** A control that opens ONE EXACT RECORD by the id the question declared. */
export function openExactRecord(id: string, words: string): ReactNode {
  return (
    <span className="rb-dec-openref">
      <button type="button" className="rb-link rb-dec-open" data-open-record={id} data-ref-id={id}
        title={`${OPENS_SAYS}\nExact reference: ${id}`} aria-label={`${words}: ${id}`}
        onClick={(ev) => { ev.stopPropagation(); void openExact(id, ev.currentTarget) }}>
        {words}
      </button>
    </span>
  )
}

/** THE HOST FLUID GIVES THE SHARED DECISION FORM. Words are drawn exactly as
 *  they were written, as they were with no host at all; what is added is the
 *  one thing that was missing -- a way to open the exact record a question
 *  names. No resolution of how anything stands is supplied here. */
export function FluidRefWords({ children }: { children: ReactNode }) {
  const viewer = useViewerHosted()
  const words = useMemo<RefWords | null>(
    () => (viewer ? { links: (t) => t, names: (t) => t, open: openExactRecord } : null),
    [viewer],
  )
  return <RefWordsContext.Provider value={words}>{children}</RefWordsContext.Provider>
}
