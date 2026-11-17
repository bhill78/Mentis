/* WHAT IMPORTING AN ARCHIVE HOLDS, for somebody about to leave it.
 *
 * THE DEFECT THIS ANSWERS (independent review ent-d960d458078c, I1): an
 * archive chosen and read -- its itemised plan on the screen, nothing staged
 * -- lived only in the page. A conversation press, a Back, or any other way
 * out took it with no word said, and the reader chose the file and waited for
 * the reading again. The owner's rule is explicit: "A completed but unapplied
 * preview counts as unfinished setup."
 *
 * WHAT IS STAGED IS NOT HELD HERE. A confirmed import is written to the Brain
 * folder (`.import-staged.zip`) and read back from there whenever the page is
 * opened again, so leaving it loses nothing and must never ask: that is a
 * no-loss transition, and the review was explicit about it too.
 *
 * The rule is here, apart from React, so it is checkable
 * (`tests/quiet_nav_unit.ts`). */
import type { Standing } from '../leaving'

/** What the import page holds, in the plainest terms it can give. */
export interface Importing {
  /** an archive chosen whose plan has not been staged */
  chosen: boolean
  /** its itemised plan in hand, unstaged */
  preview: boolean
  /** reading the archive (answers this page), or staging it (answers the
   *  Brain folder, and so is never lost by leaving) */
  run: 'reading' | 'staging' | null
  /** this archive has been staged: nothing here is unfinished any more */
  done: boolean
}

export const PAGE = 'this import'
export const READING = 'Reading the archive'
export const STAGING = 'Staging the archive'
/** where staging lands, whether or not the reader stays for it */
export const LANDS = 'It is staged for the next restart either way.'
/** what is lost by leaving an archive chosen and read but not staged */
export const LOST = 'The archive you chose has not been imported: nothing of it is in the Brain, and it would have to be chosen and read again.'

/** What importing an archive holds now, for `leaving`. */
export function importing(h: Importing): Standing | null {
  if (h.done) return null
  const staging = h.run === 'staging'
  return {
    what: PAGE,
    dirty: !staging && (h.chosen || h.preview),
    lost: LOST,
    run: h.run
      ? (staging
          ? { what: STAGING, interrupted: false, lands: LANDS }
          : { what: READING, interrupted: true })
      : null,
  }
}
