/* WHERE A POST WAS ON THE SCREEN. Round 5 bootstrap by S; package R owns the
 * body.
 *
 * NOT `document.scrollTop`. Quiet's document scrolls at EVERY width -- there
 * is no desktop stream scroller, whatever the shell's older comments say --
 * and a raw scroll position means nothing once a font loads, an image settles
 * or a margin opens. What survives all of that is a POST and its OFFSET: the
 * signed distance from the visible reading viewport's top to that post's top,
 * with a pinned header accounted for.
 *
 * AN ACTUALLY VISIBLE POST, not an arbitrary loaded id: the one the reader
 * can see is the one they will look for when they come back.
 */
import type { ReadingAnchor } from '../workspace/types'

/** Capture the anchor for the post visible in `viewport`. The bootstrap
 *  captures nothing: R measures the drawn posts, and a bootstrap that
 *  returned a guess would be remembered as if it were a reading. */
export function captureReadingAnchor(
  _viewport: HTMLElement | null,
  _posts?: Iterable<HTMLElement>,
): ReadingAnchor | null {
  return null
}

/** Put a captured anchor back, and say whether it could be. false means the
 *  post is not drawn -- filtered out, not loaded, or deleted -- which is a
 *  recoverable state the reader is told about, not a silent jump to
 *  something else. */
export function restoreReadingAnchor(
  _viewport: HTMLElement | null,
  _anchor: ReadingAnchor | null,
): boolean {
  return false
}
