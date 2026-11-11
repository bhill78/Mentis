/* TIDY, AS AN OPERATION. Round 5 bootstrap by S; package T owns the body.
 *
 * T lines the ordinary detached windows up with the existing
 * `focus/model.ts` `tidyFloats`, and fits the Magnet discs into a wrapping
 * grid using the existing `DISC_FOOT`/`DISC_CELL` and `settledDiscs` --
 * verifying that the saved disc coordinates are a FIXED POINT of what is
 * drawn at these bounds (F13), rather than launcher-grid coordinates that
 * `settledDiscs` would replace on the next draw.
 *
 * The resulting positions persist through the Holder and S's envelope like
 * any other arrangement; the toggle's memory of where things were is
 * transient and belongs to the press, not to the bookmark.
 */

/** Tidy what is drawn in this area, and say whether anything moved. The
 *  bootstrap moves nothing and answers false, which is also what the control
 *  reads as "nothing here to tidy" -- an honest disabled state rather than a
 *  button that appears to work. */
export function tidyInArea(_area: HTMLElement | null, _page: string): boolean {
  return false
}
