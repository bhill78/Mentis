/* TRACK C owns this module: WHAT EACH POST CARRIES, HELD OUTSIDE THE TREE.

   THE PROBLEM. A post's rendered blocks, its attachments and its annotations
   are drawn inside the post, by `post/parts.tsx`; the margin that presents
   them beside the stream is `rail/Rail.tsx`, in another cell of the shell's
   grid entirely. Neither is inside the other and the shell between them is
   frozen (P0 owns `QuietChat.tsx`), so there is no prop that could carry one
   to the other. This is the same answer `composer/drafts.ts` gives for the
   same shape of problem: one module-level record, written by whoever knows
   and read by whoever shows, with React subscribing to it rather than owning
   it.

   WHAT IS HELD, AND WHAT IS NOT. A descriptor, never a React element: the
   block and the KEY IT IS DRAWN UNDER IN THE POST (`keyOf`), the viewer's
   reading of an attachment, the anchor as the record answers it. That is what
   makes a block in the margin the SAME block as the one in the post -- one
   checklist with one set of ticks, not a copy whose state drifts -- because
   `RenderableBlock` keys its state by `blockKey` and both draw it under the
   same one.

   A GROUP IS ONE REGISTRAR'S WHOLE CONTRIBUTION. `register(group, items)`
   replaces everything that group said before, so a post whose words changed
   does not leave its old blocks behind, and a post that scrolls out of the
   read (a new page, another topic) takes its boxes with it when its effect
   is cleaned up. Registration order is the order posts mounted, which is the
   order they are read in.

   SIDES. The mockup's margins put media, the timeline, the chart and the flow
   chart on the right and documents, the table and the form on the left. Quiet
   has ONE margin cell (the work row's third); the first cell is the
   conversation navigation and is not this package's to fill. So a side is
   RECORDED on every box, and drawn as `data-side`, where the concept says
   which side it belongs to -- it is the authority's reading kept, ready for
   the day the left cell can hold boxes, and it is never a second column
   invented here. */
import { useSyncExternalStore } from 'react'
import type { Names } from '../../experimental/objects'
import type { RBlock } from '../../experimental/renderable'
import type { PostAnchor } from '../../fluid/actions'
import type { ViewerItem } from '../media/view'

export type Side = 'left' | 'right'

interface Held {
  /** stable across re-registrations: the same box keeps its place and its
   *  put-away state when the post it belongs to is drawn again */
  id: string
  /** the Turn it is carried by */
  post: string
  /** what it is called in the box's head */
  title: string
  side: Side
}

export type Carried =
  | (Held & { kind: 'block'; type: string; block: RBlock; blockKey: string; where: string; names?: Names })
  | (Held & { kind: 'media'; item: ViewerItem })
  | (Held & { kind: 'annotation'; anchor: PostAnchor; excerpt: string | null })

/** Which side of the stream the concept HTML puts this block type on. */
const LEFT = new Set(['table', 'form', 'pad', 'ref', 'checklist', 'decide', 'problems'])
export const sideOf = (type: string): Side => (LEFT.has(type) ? 'left' : 'right')

const groups = new Map<string, Carried[]>()
const away = new Set<string>()
let opened: string | null = null
/** Bumped whenever something asks the margin to show what is carried. */
let asked = 0
let version = 0

const heard = new Set<() => void>()
const tell = () => { version++; for (const fn of [...heard]) fn() }
const subscribe = (fn: () => void) => { heard.add(fn); return () => { heard.delete(fn) } }

let flat: Carried[] = []
let flatAt = -1
/** Every box now shown, in the order its post was read. Cached per version so
 *  `useSyncExternalStore` is handed the same array until something changes. */
function shown(): Carried[] {
  if (flatAt === version) return flat
  flat = [...groups.values()].flat().filter((c) => !away.has(c.id))
  flatAt = version
  return flat
}

/** Everything one registrar carries now; `[]` withdraws what it said. */
export function register(group: string, items: Carried[]) {
  if (!items.length) {
    if (!groups.delete(group)) return
    tell()
    return
  }
  groups.set(group, items)
  tell()
}

/** Put a box away. It comes back when its post is read again. */
export function putAway(id: string) {
  away.add(id)
  if (opened === id) opened = null
  tell()
}

/** Collect it: ask the margin to show what is carried, with this box marked.
 *  Called from a post's own gutter (an annotation's icon) and from the box's
 *  own head. */
export function present(id: string | null) {
  opened = id
  asked++
  tell()
}

/** The box the margin should mark and scroll to, if any. */
export const useOpened = () => useSyncExternalStore(subscribe, () => opened)

/** How many times the margin has been asked to show what is carried. `useRail`
 *  watches this: a new number means switch the reading. */
export const useAsked = () => useSyncExternalStore(subscribe, () => asked)

/** Every box the margin presents now. */
export const useCarried = () => useSyncExternalStore(subscribe, shown)

/** Thrown away between suites. Nothing in the interface calls it. */
export function clearCarried() {
  groups.clear()
  away.clear()
  opened = null
  tell()
}

/* -- where a box came from -------------------------------------------------- */

/** The number of the post a box belongs to, read from the post's own
 *  `aria-label` (`Post.tsx` carries it), or null before it is drawn. A box
 *  says which post it came from, and goes back to it. */
export function postNumber(post: string): number | null {
  if (typeof document === 'undefined') return null
  const label = document.getElementById('qc-post-' + post)?.getAttribute('aria-label') ?? ''
  const found = /^Post (\d+)/.exec(label)
  return found ? Number(found[1]) : null
}

/** Take the reader back to the post a box came from. */
export function goToPost(post: string) {
  document.getElementById('qc-post-' + post)?.scrollIntoView({ block: 'start' })
}
