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
 * AND A READ THAT FAILED IS NOT A DETERMINATION (re-review finding F2-R1). The
 * first version ran the two together: anything the post read threw was caught
 * and read as "then it is not a post", so a 500 on the post route silently
 * became a record opening with nothing said about the fault. They are kept
 * apart now (`lookupExact`): a failed read is tried once more, forced, and
 * where it fails again the exact record is still opened -- the fallback is
 * genuinely readable, because the inspector draws what a field actually holds
 * (`../../surfaces/entryValue`) instead of `[object Object]` -- and the control
 * says that the post read failed.
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
import { useMemo, useState, type ReactNode } from 'react'
import { RefWordsContext, type RefWords } from '../../experimental/refWords'
import { BRAIN_REF } from '../brain/address'
import { store } from '../store'
import { inspect, POST_REF, useViewerHosted } from './viewer'

/** Said on the control, before it is pressed: what it opens, and that leaving
 *  the form for it costs nothing. */
export const OPENS_SAYS = 'Opens this exact record here. What you have chosen and typed is kept; Esc comes back to it.'

/** WHAT LOOKING THIS EXACT ID UP AS A POST CAME TO. The two are not the same
 *  answer and were run together before (re-review finding F2-R1): a read that
 *  ANSWERED and said this id is not a post is a determination, while a read
 *  that FAILED -- a 500, an unreachable server -- determined nothing at all.
 *  Treating the second as the first silently turns a read fault into "this is
 *  a record", and nothing says the post was never read. */
export interface ExactLookup {
  /** the read answered and this id is a post this page now holds */
  post: boolean
  /** the read itself failed, in its own words; null where it answered */
  failed: string | null
}

/** LOOK THIS EXACT ID UP AS A POST, SAYING WHICH OF THE TWO HAPPENED. A failed
 *  read is tried once more, forced, so a transient fault still opens the post
 *  it was always going to open; where it fails again the failure is said and
 *  the caller falls back to reading the exact record itself. One id throughout:
 *  nothing else is looked up, and nothing is substituted. */
export async function lookupExact(id: string): Promise<ExactLookup> {
  if (store.posts.has(id)) return { post: true, failed: null }
  let failed: string | null = null
  for (const force of [false, true]) {
    try {
      await store.loadPosts([id], force)
      /* THE READ ANSWERED. Whether this id is a post is now settled, either
         way, and a second read would settle it no differently. */
      return { post: store.posts.has(id), failed: null }
    } catch (e) {
      failed = String((e as Error)?.message ?? e)
    }
  }
  return { post: false, failed }
}

/** What is said where the post read failed twice and the exact record is read
 *  instead. It is the read that is reported, never the record: nothing here
 *  claims this id is not a post. */
export const POST_READ_FAILED = 'the post read failed, so this exact record is read as the record it is'

/** THIS EXACT ID, as the page can read it: a post in full where the read says
 *  the id is one, and otherwise the record's own inspector, which reads what
 *  the record holds (`../../surfaces/entryValue`). The lookup is of that id and
 *  no other; an id nothing answers for still opens as that id, and a post read
 *  that FAILED is said as a failed read rather than taken for a determination
 *  that this is not a post (re-review finding F2-R1). */
export async function openExact(id: string, from: HTMLElement | null): Promise<string | null> {
  const got = await lookupExact(id)
  inspect((got.post ? POST_REF : BRAIN_REF) + id, from)
  return got.failed
}

/** A control that opens ONE EXACT RECORD by the id the question declared, AND
 *  SAYS SO WHERE THE POST READ FAILED. The record still opens -- the inspector
 *  reads what it holds -- and the owner is told that what was read of it as a
 *  post failed, so "read as a record" is not mistaken for "this is not a post"
 *  (re-review finding F2-R1). Presentation only: the chosen option and the
 *  typed words are untouched by any of it. */
export function OpenExactRecord({ id, words }: { id: string; words: string }) {
  const [failed, setFailed] = useState<string | null>(null)
  return (
    <span className="rb-dec-openref">
      <button type="button" className="rb-link rb-dec-open" data-open-record={id} data-ref-id={id}
        title={`${OPENS_SAYS}\nExact reference: ${id}`} aria-label={`${words}: ${id}`}
        onClick={(ev) => {
          ev.stopPropagation()
          void openExact(id, ev.currentTarget).then(setFailed)
        }}>
        {words}
      </button>
      {failed !== null && (
        <span className="rb-dec-openwhy" data-open-record-read="post-failed">{POST_READ_FAILED} ({failed})</span>
      )}
    </span>
  )
}

/** The same control, as a host supplies one (`experimental/refWords` `open`). */
export function openExactRecord(id: string, words: string): ReactNode {
  return <OpenExactRecord key={id} id={id} words={words} />
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
