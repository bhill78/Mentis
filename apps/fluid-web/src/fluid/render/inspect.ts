/* ONE WAY TO INSPECT AN OBJECT, whatever it is.
 *
 * A picture, a film, a sound, a chart, a table, a document, a link: each is
 * enlarged the same way, by `inspect(address, from)` (present/viewer.tsx),
 * which grows out of the card or plate it came from over the workspace and
 * returns into it. It has one head, one close (‹, ✕, Esc, the bar's Back),
 * one set of keys, and draws the object through the present seam: a picture
 * zoomable, a film or sound with its player, anything else whole by
 * ObjectBody, as a detail and a page draw it.
 *
 * What is decided here, with no DOM, is what the keys do and what the
 * arrows step through; the viewer does the rest. */

/** What a key does while an object is inspected; null: not the inspector's. */
export type InspectAction = 'close' | 'leave-full' | 'full' | 'next' | 'prev' | 'zoom-in' | 'zoom-out' | 'fit' | null

export interface InspectKey { key: string; ctrlKey?: boolean; metaKey?: boolean; altKey?: boolean }

export interface InspectAt {
  /** the inspector fills the screen */
  full: boolean
  /** what is shown is a picture: it zooms */
  picture: boolean
  /** the key was typed into a field, anywhere: it is the field's */
  typing: boolean
  /** the key was pressed inside the drawn object (a chart's, a table's own
   *  controls): only Esc is the inspector's there, the rest is the object's */
  inObject: boolean
}

/** THE INSPECTOR'S KEYS, the same for every object:
 *    Esc         leave full screen, else return into where it was opened
 *    Alt+←       return, as the bar's Back does
 *    ← →         the previous and next thing in its post
 *    F           full screen, and back
 *    + − 0       zoom in, out, and fit (a picture)
 *  A field keeps every key typed into it, Esc too. */
export function inspectKey(e: InspectKey, at: InspectAt): InspectAction {
  if (at.typing) return null
  if (e.key === 'Escape') return at.full ? 'leave-full' : 'close'
  if (e.altKey) return e.key === 'ArrowLeft' && !e.ctrlKey && !e.metaKey ? 'close' : null
  if (e.ctrlKey || e.metaKey || at.inObject) return null
  if (e.key === 'ArrowRight') return 'next'
  if (e.key === 'ArrowLeft') return 'prev'
  if (e.key === 'f' || e.key === 'F') return at.full ? 'leave-full' : 'full'
  if (!at.picture) return null
  if (e.key === '+' || e.key === '=') return 'zoom-in'
  if (e.key === '-') return 'zoom-out'
  if (e.key === '0') return 'fit'
  return null
}

/** One of a post's objects, as the inspector's scope sees it. */
export interface Listed {
  address: string
  /** a picture, a film or a sound file (present/size.ts `isViewable`) */
  viewable: boolean
  /** a top-level object other than a span of the post's own words */
  inspectable: boolean
}

/** WHAT THE ARROWS STEP THROUGH: the post's own things of the same family as
 *  the one opened, in the post's order. A picture steps through the post's
 *  pictures, films and sound -- as the media viewer always has ("3 of 7") --
 *  and a chart or a table through the post's other objects; never the
 *  conversation's. */
export function inspectScope(listed: Listed[], viewable: boolean): string[] {
  return listed.filter((x) => x.inspectable && x.viewable === viewable).map((x) => x.address)
}

/** The address `d` steps from `at` in `scope`, round the ends; null where
 *  there is nothing else to step to. One not in the scope steps to its first. */
export function stepIn(scope: string[], at: string, d: number): string | null {
  if (scope.length < 2) return null
  const i = scope.indexOf(at)
  if (i < 0) return scope[0]
  return scope[(((i + d) % scope.length) + scope.length) % scope.length]
}
