/* PACKAGE F owns this module: a part that is a file or an image.

   WHAT F CHANGES. An image part renders as an image, not the bare
   `image.png ↗` link Quiet showed before the split. Images in a post form a
   gallery: clicking one opens MediaLayer's lightbox with the post's other
   images gathered from the DOM at click time, since a part sees only itself,
   never its siblings. A non-image attachment states its name, type and size
   and names its originating post (#number), read the same way -- from the
   enclosing `.qc-post`'s own `aria-label`, which Post.tsx (E) already
   carries -- and still reaches `part.artifact.url` as a plain link. */
import { useEffect, useRef, useState } from 'react'
import type { Part } from '../../api'
import { openGallery } from './MediaLayer'
import './media.css'

/** `treatment.view` is the server's own verified word for what the bytes
 *  are (`mentis/artifacts.py` `treatment`); a claimed media type is a
 *  fallback only when neither treatment nor part type classifies it. */
export function isImage(part: Part): boolean {
  if (part.artifact?.treatment?.view) return part.artifact.treatment.view === 'image'
  if (part.type === 'image') return true
  if (part.type === 'file') return false
  const claimed = part.artifact?.claimed_media_type || part.media_type || ''
  return claimed.toLowerCase().startsWith('image/')
}

export function formatSize(bytes: number | null | undefined): string | null {
  if (bytes == null) return null
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

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

export default function MediaPart({ part }: { part: Part; scope: string }) {
  const artifact = part.artifact
  const { ref, number } = useOriginatingPost<HTMLParagraphElement>()
  if (!artifact?.url) return null

  if (isImage(part)) {
    const alt = part.alt || artifact.name || 'image'
    return (
      <p className="qc-media" ref={ref}>
        <button
          type="button"
          className="qc-media-image"
          data-qc-gallery
          data-qc-url={artifact.url}
          data-qc-alt={alt}
          data-qc-name={artifact.name || ''}
          onClick={(e) => {
            const opener = e.currentTarget
            const body = opener.closest('.qc-body')
            const nodes = body ? Array.from(body.querySelectorAll<HTMLElement>('[data-qc-gallery]')) : [opener]
            const images = nodes.map((n) => ({
              url: n.getAttribute('data-qc-url') || '',
              alt: n.getAttribute('data-qc-alt') || '',
              name: n.getAttribute('data-qc-name') || '',
            }))
            openGallery(images, Math.max(0, nodes.indexOf(opener)), opener)
          }}
        >
          <img src={artifact.url} alt={alt} />
        </button>
      </p>
    )
  }

  const size = formatSize(artifact.size)
  const kind = artifact.claimed_media_type || part.media_type || 'file'
  return (
    <p className="qc-media qc-media-file" ref={ref}>
      <a href={artifact.url} className="qc-media-file-link">{part.alt || artifact.name || part.ref}</a>
      <span className="qc-media-meta">{kind}{size ? ` · ${size}` : ''}{number != null ? ` · from #${number}` : ''}</span>
    </p>
  )
}
