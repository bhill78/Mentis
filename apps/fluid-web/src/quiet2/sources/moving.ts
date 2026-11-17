/* MOVING BETWEEN THE SOURCE PAGES: which moves keep the page, and which take
 * it away.
 *
 * THE DEFECT THIS ANSWERS (independent review ent-d960d458078c, S1): a
 * changed selection and an unapplied preview disappeared without a word
 * through three real presses -- "Add the repository as its own collection" in
 * a preview, "Back to the conversation", and Add a source's own header Back.
 * Those presses went straight to the browser's history, around the one
 * question (`leaving.ts`) every other way out goes through.
 *
 * ASKING ABOUT ALL OF THEM WOULD BE WORSE THAN ASKING ABOUT NONE. Reading a
 * held file in place keeps the source's page mounted underneath, with its
 * open sections, its search and its scope draft exactly as they were; so does
 * coming back from it. Those lose nothing, and a question there is a refusal
 * with nothing behind it. The move itself has to say which it is, and that is
 * all this decides -- apart from React and the browser, so it is checkable
 * (`tests/quiet_nav_unit.ts`). */
import type { SourceMainState } from './SourceMain'

/** Whether moving from `from` to `to` KEEPS the page that holds what was
 *  typed into it. Only the centre's source pages: anywhere else -- the
 *  conversation, the Brain, the Sources browser -- takes it away. */
export function keepsSetup(from: SourceMainState | null | undefined, to: SourceMainState): boolean {
  if (!from) return true
  const a = from.view, b = to.view
  /* THE SAME SOURCE: its page stays mounted while a file of it is read in
     place, and is still there on the way back. */
  if (a.page === 'source' && b.page === 'source') return a.col === b.col
  /* SETTING ONE UP: the kind is chosen on the page itself and choosing
     another is the reader saying what they want, as its own Cancel is. */
  if (a.page === 'add' && b.page === 'add') return true
  /* a source's page for Add a source, or Add a source for a source: whichever
     was there is unmounted, and goes with everything in it */
  return false
}
