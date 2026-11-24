/** The saved reading position reaching -- and surviving -- the rendered view.
 *
 *  `places.ts` keeps the number; this decides what a scroll container that
 *  cannot yet reach it may do. The two are different problems. A view that has
 *  just been mounted, remounted after an inspection or restored from device
 *  storage renders before the posts it is reading have arrived, so the browser
 *  clamps whatever offset is written to the content's current height. Two things
 *  then go wrong unless they are handled here:
 *
 *    * the position the reader left is never rendered when the content does
 *      arrive -- one layout effect wrote it once, into a container that could
 *      not hold it; and
 *    * the clamped offset is reported back through the view's scroll handler,
 *      which saves it, so the number the reader left is destroyed as well as
 *      unrendered (re-review adm-6a1f95f203bf, finding R2).
 *
 *  Nothing here is on a timer and nothing polls: the frame keeps what could not
 *  be reached, the content's own growth re-applies it, and the reader's own
 *  gesture gives it up. */

/** Near enough: a container reports an integer, and a fractional device pixel
 *  ratio makes an exact comparison fail for a position that was reached. */
export const reachedScroll = (live: number, want: number) => Math.abs(live - want) < 1

/** What is still wanted after writing a saved position into a container that
 *  reported `live`: `null` when it was reached, or when nothing was wanted, and
 *  otherwise the position to apply once the content can hold it. */
export function pendingScroll(live: number, want: number): number | null {
  const wanted = Number.isFinite(want) && want > 0 ? Math.round(want) : 0
  if (wanted === 0) return null
  return reachedScroll(live, wanted) ? null : wanted
}

/** Whether a position the container reported may be saved as the reading
 *  position. While a wanted position has not been reached, a report short of it
 *  is the clamp of content that has not arrived -- not somewhere the reader
 *  chose -- and saving it would overwrite what they left. A report at or past
 *  the wanted position is the restore itself, or a reader who has gone further;
 *  both are theirs to keep. */
export function savesReportedScroll(pending: number | null, top: number): boolean {
  return pending === null || top >= pending
}
