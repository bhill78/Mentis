/* AN OBJECT TAKEN OUT OF ITS POST (Fluid Focus; MIUI in every presentation).
 *
 * Every object a post carries -- a chart, a table, a form, a picture, a
 * source card, what an agent returned -- is the same object wherever it is
 * drawn: in the post, a docked section, a float, the primary place. It is
 * taken out of the post by a GRIP, a small handle shown on hover or focus,
 * not by the whole object, so its text can still be selected, its links
 * followed, its form filled and its chart read. Dragged, it is the
 * workspace's own native drag (workspace/keep.tsx `DRAG`) with the payload
 * flick.ts carries, and where it came from ("Tidewater survey · #12"): what
 * takes it -- a float, a dock, a keep -- is the drop side's. From the
 * keyboard, Enter on the grip asks where it goes (the Keep chooser).
 *
 * Nothing is copied: the address is a reference to the object in its post.
 * Presentation only: nothing here writes to the record. */

import type { ReactNode } from 'react'
import { store, type Id, type Post } from '../store'
import { askKeep, DRAG } from '../workspace/keep'
import './grip.css'

/** What an object's drag carries: its live address and where it came from. */
export interface ObjectDrag { address: string; from?: string }

/** Where a post's objects come from, said: its conversation and its number. */
export function fromOf(post: Post): string {
  const conv = post.home_name || (post.home ? store.conversations.get(post.home)?.name : null)
  const num = post.number != null ? `#${post.number}` : null
  return [conv, num].filter(Boolean).join(' · ') || 'a post'
}

/** Start the native drag of one object (`d`), the element `image` drawn
 *  under the pointer while it goes. */
export function dragObject(e: React.DragEvent, d: ObjectDrag, image?: Element | null) {
  e.stopPropagation()
  e.dataTransfer.setData(DRAG, JSON.stringify(d))
  e.dataTransfer.setData('text/plain', d.address)
  e.dataTransfer.effectAllowed = 'copyMove'
  if (image) {
    const r = image.getBoundingClientRect()
    e.dataTransfer.setDragImage(image, Math.max(0, Math.min(r.width, e.clientX - r.left)), Math.max(0, Math.min(r.height, e.clientY - r.top)))
  }
}

const GRIP = <svg width="10" height="14" viewBox="0 0 10 14" fill="currentColor" aria-hidden="true"><circle cx="3" cy="3" r="1.2" /><circle cx="7" cy="3" r="1.2" /><circle cx="3" cy="7" r="1.2" /><circle cx="7" cy="7" r="1.2" /><circle cx="3" cy="11" r="1.2" /><circle cx="7" cy="11" r="1.2" /></svg>

/** A grip for one object. `address`: known, or found when it is wanted
 *  (null: not read yet -- the drag does not start). `want`: read what it
 *  needs, on the first hover or focus. `image`: what the drag shows. */
export function Grip({ label, address, from, want, image, className }: {
  label: string
  address: string | (() => string | null)
  from?: string
  want?: () => void
  image?: (el: HTMLElement) => Element | null
  className?: string
}) {
  const now = () => (typeof address === 'string' ? address : address())
  return (
    <button type="button" className={'fx-grip' + (className ? ' ' + className : '')} draggable data-act="drag-out"
      aria-label={`Move ${label} out of the post: drag it onto a section or the page; Enter chooses where it goes`}
      title={`Drag ${label} out: onto a section, or anywhere to float it${from ? ` (from ${from})` : ''}`}
      onPointerEnter={want} onFocus={want}
      onClick={(e) => {
        e.stopPropagation()
        const a = now()
        if (a) askKeep({ address: a }, e.currentTarget)
      }}
      onDragStart={(e) => {
        const a = now()
        if (!a) { e.preventDefault(); return }
        dragObject(e, { address: a, ...(from ? { from } : {}) }, image?.(e.currentTarget) ?? null)
      }}>
      {GRIP}
    </button>
  )
}

/* -- a block drawn in a post's words ------------------------------------------ */

/** The live address of the object under block key `key` in post `root`,
 *  once its objects are read: the post's object of that key. */
export function addressOf(root: Id, key: string): string | null {
  for (const a of store.postObjects.get(root)?.addresses ?? []) {
    const st = store.objects.get(a)
    if (st && 'object' in st && st.object.key === key) return st.object.address.live
  }
  return null
}
const wantObjects = (root: Id) => { if (!store.postObjects.has(root)) void store.loadObjects(root).catch(() => {}) }

/** What a post's words give each block they draw (renderable.tsx
 *  `BlockGripContext`): its grip, carrying the post's object of that key. */
export function gripsFor(post: Post): (key: string, label: string) => ReactNode {
  const from = fromOf(post)
  return (key, label) => (
    <Grip label={label} from={from} address={() => addressOf(post.id, key)} want={() => wantObjects(post.id)}
      image={(el) => el.closest('.rb-card')} />
  )
}
