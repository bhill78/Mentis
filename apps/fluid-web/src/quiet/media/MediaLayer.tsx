/* PACKAGE F owns this module: the gallery overlay, mounted once beside the
   shell so it can sit above everything without any package being inside
   another's markup. `MediaLayerView` is declared with no props at all, so
   what it shows comes from a module-level store here -- the way
   `composer/drafts.ts` lifts the drafts record out of the tree -- and
   `MediaPart` (F's own other module) opens it by calling `openGallery`
   rather than by being given it.

   WHAT F CHANGES. Before F, Quiet had no lightbox and this rendered nothing.
   Now: previous / next / Escape, focus trapped inside the dialog while it is
   open and returned to whichever thumbnail opened it on close. */
import { useEffect, useRef, useState } from 'react'
import { inspectKey, stepIn } from '../../fluid/render/inspect'
import './media.css'

export interface GalleryImage { url: string; alt: string; name: string }
interface GalleryState { images: GalleryImage[]; index: number; opener: HTMLElement | null }

let state: GalleryState | null = null
const listeners = new Set<() => void>()
const announce = () => { for (const fn of [...listeners]) fn() }

/** Opens the gallery on `images[index]`. `opener` is the element focus
 *  returns to on close -- the thumbnail that was clicked. */
export function openGallery(images: GalleryImage[], index: number, opener: HTMLElement | null) {
  if (!images.length) return
  const n = images.length
  state = { images, index: ((index % n) + n) % n, opener }
  announce()
}

function closeGallery() {
  const opener = state?.opener
  state = null
  announce()
  opener?.focus()
}

function step(d: number) {
  if (!state) return
  const scope = state.images.map((_, index) => String(index))
  const next = stepIn(scope, String(state.index), d)
  if (next === null) return
  state = { ...state, index: Number(next) }
  announce()
}

/** Thrown away between suites, so one case's open gallery is not the
 *  next's. Nothing in the interface calls it. */
export function clearGallery() {
  state = null
  announce()
}

function useGallery() {
  const [, redraw] = useState(0)
  useEffect(() => {
    const fn = () => redraw((n) => n + 1)
    listeners.add(fn)
    return () => { listeners.delete(fn) }
  }, [])
  return state
}

const FOCUSABLE = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'

export default function MediaLayer() {
  const current = useGallery()
  const ref = useRef<HTMLDivElement>(null)
  const wasOpen = useRef(false)

  useEffect(() => {
    if (current && !wasOpen.current) {
      wasOpen.current = true
      ref.current?.querySelector<HTMLElement>(FOCUSABLE)?.focus()
    } else if (!current) {
      wasOpen.current = false
    }
  }, [current])

  useEffect(() => {
    if (!current) return
    const onKey = (e: KeyboardEvent) => {
      const action = inspectKey(e, { full: false, picture: false, typing: false, inObject: false })
      if (action === 'close') { e.preventDefault(); closeGallery(); return }
      if (action === 'next' || action === 'prev') { e.preventDefault(); step(action === 'next' ? 1 : -1); return }
      if (e.key !== 'Tab') return
      const el = ref.current
      const focusables = el ? Array.from(el.querySelectorAll<HTMLElement>(FOCUSABLE)) : []
      if (!focusables.length) return
      const first = focusables[0], last = focusables[focusables.length - 1]
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus() }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus() }
    }
    const onFocus = (e: FocusEvent) => {
      const el = ref.current
      if (state && el && e.target instanceof Node && !el.contains(e.target)) {
        el.querySelector<HTMLElement>(FOCUSABLE)?.focus()
      }
    }
    document.addEventListener('keydown', onKey)
    document.addEventListener('focusin', onFocus, true)
    return () => {
      document.removeEventListener('keydown', onKey)
      document.removeEventListener('focusin', onFocus, true)
    }
  }, [current])

  if (!current) return null
  const { images, index } = current
  const image = images[index]
  return (
    <div className="qc-media-lightbox" role="dialog" aria-modal="true" aria-label={image.alt || image.name || 'Image'} ref={ref} onMouseDown={(e) => { if (e.target === e.currentTarget) e.preventDefault() }}>
      <button type="button" className="qc-media-lightbox-close" onClick={closeGallery} aria-label="Close">✕</button>
      {images.length > 1 && (
        <button type="button" className="qc-media-lightbox-prev" onClick={() => step(-1)} aria-label="Previous image">‹</button>
      )}
      <img src={image.url} alt={image.alt} className="qc-media-lightbox-image" />
      {images.length > 1 && (
        <button type="button" className="qc-media-lightbox-next" onClick={() => step(1)} aria-label="Next image">›</button>
      )}
      {images.length > 1 && <p className="qc-media-lightbox-count">{index + 1} of {images.length}</p>}
    </div>
  )
}
