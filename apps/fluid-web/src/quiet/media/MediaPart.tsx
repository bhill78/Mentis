/* PACKAGE F owns this module: a part that is a file, an image, an html
   mockup or anything else the record holds the bytes of.

   WHAT F CHANGED AT THE SPLIT. An image part renders as an image, not the
   bare `image.png ↗` link Quiet showed before. Images in a post form a
   gallery: clicking one opens the viewer with the post's other attachments
   gathered from the DOM at click time, since a part sees only itself, never
   its siblings. A non-image attachment states its name, type and size and
   names its originating post (#number), read the same way -- from the
   enclosing `.qc-post`'s own `aria-label`, which Post.tsx already carries.

   WHAT ROUND 4 CHANGES. THE PAGE IS NEVER LEFT TO READ AN ATTACHMENT. The
   file row was a plain `<a href="/api/artifacts/…">`, so reading a note, a
   mockup or a log meant navigating out of the conversation and coming back.
   Every row is now a control that opens it in the viewer beside the post
   (MediaLayer), with the download link inside the viewer: the bytes are one
   click further away, and the conversation is not lost to reach them. What a
   row SAYS is unchanged -- its name, what it is, how big, and which post it
   came from.

   ONE COLLECTION, EVERY KIND. `data-qc-view` marks every attachment in the
   body, so previous / next step through a post's mockup and its notes as
   well as its pictures. The whole of what the viewer needs is written on the
   row, because the row is all the opener can see. */
import { useEffect, useRef, useState } from 'react'
import type { Part } from '../../api'
import { openViewer } from './MediaLayer'
import { formatSize, isImage, itemOf, kindWords, type ViewerItem, type ViewKind } from './view'
import './media.css'

export { formatSize, isImage, viewKindOf } from './view'

/** The post a part sits in, read from the DOM once mounted: `scope` names
 *  the turn's id, not its number, and nothing passed to this module carries
 *  the number Post.tsx already put in its own `aria-label`. */
function useOriginatingPost<T extends HTMLElement>() {
  const ref = useRef<T>(null)
  const [number, setNumber] = useState<number | null>(null)
  useEffect(() => {
    const label = ref.current?.closest('.qc-post')?.getAttribute('aria-label') ?? ''
    const found = /^Post (\d+)/.exec(label)
    setNumber(found ? Number(found[1]) : null)
  }, [])
  return { ref, number }
}

/** What the viewer needs, written on the row it is opened from. */
const attrs = (item: ViewerItem) => ({
  'data-qc-view': '',
  'data-qc-url': item.url,
  'data-qc-name': item.name,
  'data-qc-alt': item.alt,
  'data-qc-kind': item.kind,
  'data-qc-ref': item.ref,
  'data-qc-type': item.mediaType,
  'data-qc-size': item.size == null ? '' : String(item.size),
})

const read = (el: HTMLElement): ViewerItem => ({
  url: el.getAttribute('data-qc-url') || '',
  name: el.getAttribute('data-qc-name') || '',
  alt: el.getAttribute('data-qc-alt') || '',
  kind: (el.getAttribute('data-qc-kind') || 'file') as ViewKind,
  ref: el.getAttribute('data-qc-ref') || '',
  mediaType: el.getAttribute('data-qc-type') || '',
  size: el.getAttribute('data-qc-size') ? Number(el.getAttribute('data-qc-size')) : null,
})

/** Open the viewer on this row, with everything else the post carries beside
 *  it, in the order the post carries them. */
function open(opener: HTMLElement) {
  const body = opener.closest('.qc-body')
  const nodes = body ? Array.from(body.querySelectorAll<HTMLElement>('[data-qc-view]')) : [opener]
  const items = (nodes.length ? nodes : [opener]).map(read)
  openViewer(items, Math.max(0, nodes.indexOf(opener)), opener)
}

export default function MediaPart({ part }: { part: Part; scope: string }) {
  const item = itemOf(part)
  const { ref, number } = useOriginatingPost<HTMLParagraphElement>()
  if (!item) return null

  /* `data-src-skip`: an attachment's own words are not the post's stored
     text, so the passage walk (`surfaces/passage.ts`) must not try to place
     them -- an annotation would otherwise be drawn over a file's name. */
  if (isImage(part)) {
    return (
      <p className="qc-media" ref={ref} data-src-skip="">
        <button type="button" className="qc-media-image" {...attrs(item)}
          aria-label={`Open ${item.name || item.alt}`}
          onClick={(e) => open(e.currentTarget)}>
          <img src={item.url} alt={item.alt} />
        </button>
      </p>
    )
  }

  const size = formatSize(item.size)
  const kind = item.mediaType || kindWords[item.kind]
  return (
    <p className="qc-media qc-media-file" ref={ref} data-src-skip="">
      <button type="button" className="qc-media-file-open" {...attrs(item)}
        aria-label={`Open ${item.name}`} onClick={(e) => open(e.currentTarget)}>
        <span className="qc-media-file-link">{item.name}</span>
        <span className="qc-media-meta">{kind}{size ? ` · ${size}` : ''}{number != null ? ` · from #${number}` : ''}</span>
      </button>
    </p>
  )
}
