/* WHERE A POST WAS ON THE SCREEN, and which reading an arrival shows. Round
 * 5, package R.
 *
 * NOT `document.scrollTop`. Quiet's document scrolls at EVERY width --
 * `#qc-stream` carries no overflow of its own (layout.css) -- and a raw scroll
 * position means nothing once a font loads, an image settles or a margin
 * opens. What survives all of that is a POST and its OFFSET: the signed
 * distance from the visible reading viewport's top to that post's top, with a
 * pinned header accounted for.
 *
 * AN ACTUALLY VISIBLE POST, not an arbitrary loaded id: the one the reader can
 * see is the one they will look for when they come back. A thread pins its
 * parent post over the top of the reading, so what is behind that is not in
 * view either -- `blocked` is how much of the top is covered.
 *
 * THE OFFSET IS MEASURED FROM THE PINNED HEADER'S EDGE ALONE, never from the
 * covered edge: the header's height is a settled browser preference, while
 * what is stuck under it can grow and shrink while somebody reads (a parent
 * header's Show more), and an offset measured against something that moves
 * would not be the same offset when it was put back.
 *
 * EVERYTHING THAT DECIDES ANYTHING HERE IS PURE. `anchorIn`, `anchorDelta`,
 * `resumeReading` and `validReplyTarget` are given numbers and rows and answer
 * without touching a document, so the cases that matter -- a changed height, a
 * filtered-out anchor, a reply target that is no longer in its thread -- are
 * checked without a browser (`tests/quiet_r5_reading_unit.mjs`). The two
 * functions the contract names wrap them with the measurement.
 */
import type { Id } from '../../api'
import type { BatchCursor } from '../model'
import type { ReadingAnchor, ReadingBookmark } from '../workspace/types'

/** One post as it is drawn, in client coordinates. */
export interface DrawnPost {
  id: Id
  top: number
  bottom: number
}

/** THE VISIBLE READING VIEWPORT. `top` is the line below which the reading can
 *  be seen -- the pinned header's lower edge, 0 when nothing is pinned --
 *  `bottom` the lower edge of the window, and `blocked` how much of the top is
 *  covered by something stuck there. */
export interface ReadingFrame {
  top: number
  bottom: number
  blocked: number
  posts: DrawnPost[]
}

/** Hundredths of a pixel: enough that an offset round-trips inside the 4px the
 *  reading restoration promises, without recording a float's whole tail. */
const round = (px: number): number => Math.round(px * 100) / 100

/** A hair of tolerance, so a post whose last pixel is level with the covered
 *  edge is not called visible. */
const HAIR = 2

/** WHICH POST THE READER WAS LOOKING AT, and where it was.
 *
 *  The first post drawn below whatever covers the top of the reading. Failing
 *  that -- nothing is in view, which happens when a reading is paged while
 *  scrolled past its end -- the last one above it, so the answer still names
 *  something that is actually drawn. null only where no post is drawn at all,
 *  which is not a reading and is not remembered as one. */
export function anchorIn(frame: ReadingFrame): ReadingAnchor | null {
  const edge = frame.top + frame.blocked
  let above: DrawnPost | null = null
  for (const post of frame.posts) {
    if (post.bottom - HAIR > edge && post.top + HAIR < frame.bottom)
      return { post: post.id, offset: round(post.top - frame.top) }
    if (post.bottom <= edge) above = post
  }
  const fallback = above ?? frame.posts[0] ?? null
  return fallback ? { post: fallback.id, offset: round(fallback.top - frame.top) } : null
}

/** HOW FAR TO SCROLL to put `anchor` back where it was, or null when that post
 *  is not drawn -- filtered out, not loaded, or deleted, each of which is a
 *  recoverable state the reader is told about rather than a silent jump to
 *  something else.
 *
 *  Heights that changed in between do not matter: the answer is measured
 *  against what is drawn NOW, which is the whole reason the bookmark is a post
 *  and an offset. */
export function anchorDelta(frame: ReadingFrame, anchor: ReadingAnchor | null): number | null {
  if (!anchor) return null
  const found = frame.posts.find((p) => p.id === anchor.post)
  if (!found) return null
  return round(found.top - frame.top - anchor.offset)
}

/* -- the measurement ------------------------------------------------------- */

const PREFIX = 'qc-post-'

const idOf = (el: Element): Id | null =>
  el.id.startsWith(PREFIX) ? (el.id.slice(PREFIX.length) as Id) : null

/** The pinned header's lower edge. `--qc-pin-offset` is Quiet's own published
 *  value (layout.css), 0px unless the reader asked for a pinned header. */
function pinnedTop(): number {
  const qc = typeof document === 'undefined' ? null : document.querySelector('.qc')
  if (!qc) return 0
  const px = Number.parseFloat(getComputedStyle(qc).getPropertyValue('--qc-pin-offset'))
  return Number.isFinite(px) ? px : 0
}

/** What is stuck immediately under the pinned header. A thread draws its
 *  parent post there, and a post behind that is not in view. */
function blockedBy(viewport: HTMLElement, top: number): number {
  const stuck = viewport.querySelector<HTMLElement>('.qc-parent-header')
  if (!stuck) return 0
  const box = stuck.getBoundingClientRect()
  return box.top <= top + 1 ? box.height : 0
}

/** The reading as it is drawn right now. null where there is nothing to
 *  measure -- no element, or no window, which is every call under node. */
export function readFrame(
  viewport: HTMLElement | null,
  posts?: Iterable<HTMLElement>,
): ReadingFrame | null {
  if (!viewport || typeof window === 'undefined') return null
  const top = pinnedTop()
  const drawn: DrawnPost[] = []
  for (const el of posts ?? viewport.querySelectorAll<HTMLElement>('.qc-post')) {
    const id = idOf(el)
    if (!id) continue
    const box = el.getBoundingClientRect()
    drawn.push({ id, top: box.top, bottom: box.bottom })
  }
  return { top, bottom: window.innerHeight, blocked: blockedBy(viewport, top), posts: drawn }
}

/** Capture the anchor for the post visible in `viewport`, measuring the posts
 *  drawn in it (or the ones named, which is how a caller that already has them
 *  avoids a second query). */
export function captureReadingAnchor(
  viewport: HTMLElement | null,
  posts?: Iterable<HTMLElement>,
): ReadingAnchor | null {
  const frame = readFrame(viewport, posts)
  return frame ? anchorIn(frame) : null
}

/** Put a captured anchor back, and say whether it could be. false means the
 *  post is not drawn -- filtered out, not loaded, or deleted -- which is a
 *  recoverable state the reader is told about, not a silent jump to something
 *  else.
 *
 *  THE DOCUMENT IS WHAT MOVES, at every width. */
export function restoreReadingAnchor(
  viewport: HTMLElement | null,
  anchor: ReadingAnchor | null,
): boolean {
  const frame = readFrame(viewport)
  if (!frame) return false
  const delta = anchorDelta(frame, anchor)
  if (delta === null) return false
  const scroller = document.scrollingElement
  if (!scroller) return false
  scroller.scrollTop = Math.max(0, scroller.scrollTop + delta)
  return true
}

/* -- which reading an arrival shows ---------------------------------------- */

/** WHAT AN ARRIVAL READS, and where that came from. */
export interface ResumedReading {
  topic: Id | null
  turn: Id | null
  batch: BatchCursor
  flowAnchor: ReadingAnchor | null
  threadAnchor: ReadingAnchor | null
  replyTo: Id | null
  from: 'address' | 'bookmark'
}

const nothing = (topic: Id | null, turn: Id | null): ResumedReading => ({
  topic,
  turn,
  batch: {},
  flowAnchor: null,
  threadAnchor: null,
  replyTo: null,
  from: 'address',
})

/** WHICH READING AN ARRIVAL SHOWS.
 *
 *  THE ADDRESS WINS WHEREVER IT SAYS ANYTHING. A link somebody sent, and a
 *  Back into an older entry, both land exactly where they name -- they are not
 *  redirected to the latest bookmark. `explicit` is that question already
 *  answered: an address naming a topic, a post or a Page is deliberate.
 *
 *  A BARE `#/c/<id>` IS A RESUME ENTRY, and then what this browser remembers
 *  about this Page is what is shown: the topic that was filtering it, the half
 *  of it that was loaded, the thread that was open, and the post that was
 *  being answered in it -- which is not the same choice as the post being
 *  read.
 *
 *  Nothing here reads or writes storage, and nothing here decides WHEN to
 *  resume: `saved` is null until the caller has an identity and a bookmark to
 *  resume from, and a caller who has taken control passes null for good. */
export function resumeReading(
  at: { topic: Id | null; turn: Id | null },
  saved: ReadingBookmark | null,
  explicit: boolean,
): ResumedReading {
  if (explicit || !saved) return nothing(at.topic, at.turn)
  return {
    topic: saved.flow.topic,
    turn: saved.thread?.target ?? null,
    batch: saved.flow.batch,
    flowAnchor: saved.flow.anchor,
    threadAnchor: saved.thread?.anchor ?? null,
    replyTo: saved.thread?.replyTo ?? null,
    from: 'bookmark',
  }
}

/** THE POST A RESTORED COMPOSER ANSWERS.
 *
 *  A saved target that is still in the thread is kept, because choosing it was
 *  deliberate and it is deliberately NOT the post being read. One that is not
 *  there any more -- deleted, or a thread that has changed under it -- falls
 *  back to the post being read and says so: an invalid reply target never
 *  becomes a silent reply to something else. */
export function validReplyTarget(
  rows: readonly { id: Id }[],
  saved: Id | null,
  target: Id,
): { reply: Id; lost: boolean } {
  if (!saved || saved === target) return { reply: target, lost: false }
  return rows.some((r) => r.id === saved)
    ? { reply: saved, lost: false }
    : { reply: target, lost: true }
}

/** The keys a reader scrolls with. Pressing one of them is taking control, and
 *  a restore that has not happened yet gives way to it. */
export const SCROLL_KEYS: ReadonlySet<string> = new Set([
  'ArrowUp', 'ArrowDown', 'PageUp', 'PageDown', 'Home', 'End', ' ', 'Spacebar',
])
