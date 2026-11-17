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
  /* SETTING ONE UP, ANOTHER KIND. The page stays, but the FLOW in it does not:
     AddSourcePage draws `<FolderFlow key={descriptor.id}>`, so a different kind
     unmounts the flow with the name, the place and the preview in it.
     This was read the other way at dac52ce -- as the reader saying what they
     want, like the form's own Cancel -- and the re-review (ent-c7013fe14e59)
     was right that it is not. The live path to it is not the kind cards, which
     a preview in hand disables: it is the preview's own offer, "Add the
     repository as its own collection", which reads as an addition rather than
     a discard and carried the unapplied preview away with it. Cancel says what
     it does; this does not, so it asks. */
  if (a.page === 'add' && b.page === 'add') return a.connector === b.connector
  /* a source's page for Add a source, or Add a source for a source: whichever
     was there is unmounted, and goes with everything in it */
  return false
}
