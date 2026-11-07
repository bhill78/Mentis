/* PACKAGE F owns this module: THE IN-APP VIEWER, mounted once beside the
   shell so it can sit above everything without any package being inside
   another's markup. `MediaLayerView` is declared with no props at all, so
   what it shows comes from a module-level store here -- the way
   `composer/drafts.ts` lifts the drafts record out of the tree -- and
   `MediaPart` (F's own other module) opens it by calling `openViewer`
   rather than by being given it.

   WHAT ROUND 4 CHANGES. It was a lightbox for images only, and every other
   attachment was a plain link that LEFT THE PAGE. Now a file row and an html
   mockup open here too, drawn the way Fluid's own viewer draws them, and
   nothing in Quiet navigates away to read an attachment:

     image     the picture
     film      the browser's own player, from the artifact URL
     sound     the same
     html      the sandboxed, policy-guarded frame Fluid draws written HTML
               in (`prose.tsx` HtmlFrame) over the BOUNDED document read
     document  its words -- Markdown through the shared reader, plain text
               as written -- from the same bounded read (`doc.ts`)
     file      what it is and how big, and the way to the bytes

   THE BYTES STAY REACHABLE. Every reading carries a download link INSIDE the
   viewer, so "open it in the app" never costs the reader the file itself.
   Keys, the focus trap and previous / next are the lightbox's own, unchanged:
   previous / next now step through everything the post carries, not only its
   pictures. Nothing here is a Fluid float or a Page: it is one overlay with
   one close. */
import { useEffect, useRef, useState } from 'react'
import { HtmlFrame, Prose } from '../../prose'
import { inspectKey, stepIn } from '../../fluid/render/inspect'
import { useDocument } from './doc'
import { formatSize, isDrawn, kindWords, type ViewerItem } from './view'
import './media.css'

interface ViewerState { items: ViewerItem[]; index: number; opener: HTMLElement | null }

let state: ViewerState | null = null
const listeners = new Set<() => void>()
const announce = () => { for (const fn of [...listeners]) fn() }

/** Opens the viewer on `items[index]`. `opener` is the element focus returns
 *  to on close -- the thumbnail or the row that was activated. */
export function openViewer(items: ViewerItem[], index: number, opener: HTMLElement | null) {
  if (!items.length) return
  const n = items.length
  state = { items, index: ((index % n) + n) % n, opener }
  announce()
}

/** Whether the viewer is showing anything (the margin asks, to avoid
 *  stacking a box's own overlay under this one). */
export const viewerOpen = () => state !== null

function closeViewer() {
  const opener = state?.opener
  state = null
  announce()
  opener?.focus()
}

function step(d: number) {
  if (!state) return
  const scope = state.items.map((_, index) => String(index))
  const next = stepIn(scope, String(state.index), d)
  if (next === null) return
  state = { ...state, index: Number(next) }
  announce()
}

/** Thrown away between suites, so one case's open viewer is not the
 *  next's. Nothing in the interface calls it. */
export function clearViewer() {
  state = null
  announce()
}

function useViewer() {
  const [, redraw] = useState(0)
  useEffect(() => {
    const fn = () => redraw((n) => n + 1)
    listeners.add(fn)
    return () => { listeners.delete(fn) }
  }, [])
  return state
}

const FOCUSABLE = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'

/* -- what each kind is drawn as -------------------------------------------- */

/** An html mockup or a document: its bytes, read bounded, drawn in place. */
function Written({ item }: { item: ViewerItem }) {
  const doc = useDocument(item.ref)
  if (!item.ref) return <Offered item={item} why="There is no artifact behind it to read." />
  if (!doc) return <p className="qc-viewer-wait" aria-busy="true">Reading it…</p>
  if ('error' in doc) return <Offered item={item} why={`Could not read it here (${doc.error}).`} />
  if (item.kind === 'html')
    return (
      <>
        <HtmlFrame className="qc-viewer-frame" title={`preview of ${item.name}`} html={doc.text} />
        <p className="qc-viewer-note">
          Preview only · nothing is loaded from the network, and scripts and forms do not
          run. Following a link can still leave the preview.
        </p>
      </>
    )
  return (
    <div className="qc-viewer-doc qc-body">
      {/* `untrusted`: a stored file is text nobody in this Brain wrote, so
          its fences are shown as source and nothing more -- the same rule
          Prose states for a stored note. */}
      {item.kind === 'markdown'
        ? <Prose src={doc.text} scope={`viewer:${item.ref}`} untrusted />
        : <pre className="qc-viewer-plain">{doc.text}</pre>}
      {doc.cut && <p className="qc-muted">This document is longer than Quiet draws; download it for the rest.</p>}
    </div>
  )
}

/** A file nothing here draws, and anything whose bytes could not be read:
 *  what it is, and the way to it. */
function Offered({ item, why }: { item: ViewerItem; why?: string }) {
  return (
    <div className="qc-viewer-file">
      <p className="qc-viewer-filename">{item.name}</p>
      <p className="qc-muted">{why ?? [kindWords[item.kind], item.mediaType].filter(Boolean).join(' · ')}</p>
    </div>
  )
}

function Body({ item }: { item: ViewerItem }) {
  if (item.kind === 'image') return <img src={item.url} alt={item.alt} className="qc-media-lightbox-image" />
  if (item.kind === 'video')
    return <video className="qc-viewer-player" src={item.url} controls preload="metadata" aria-label={item.name} />
  if (item.kind === 'audio')
    return <audio className="qc-viewer-player" src={item.url} controls preload="metadata" aria-label={item.name} />
  if (isDrawn(item.kind)) return <Written item={item} />
  return <Offered item={item} />
}

export default function MediaLayer() {
  const current = useViewer()
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
      if (action === 'close') { e.preventDefault(); closeViewer(); return }
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
  const { items, index } = current
  const item = items[index]
  /* An image keeps the bare lightbox it has always had; everything else is
     read inside a bounded sheet, because a document is read, not looked at. */
  const framed = item.kind !== 'image'
  return (
    <div className="qc-media-lightbox" data-framed={framed || undefined} role="dialog" aria-modal="true"
      aria-label={item.alt || item.name || 'Attachment'} ref={ref}
      onMouseDown={(e) => { if (e.target === e.currentTarget) e.preventDefault() }}>
      <button type="button" className="qc-media-lightbox-close" onClick={closeViewer} aria-label="Close">✕</button>
      {items.length > 1 && (
        <button type="button" className="qc-media-lightbox-prev" onClick={() => step(-1)} aria-label="Previous attachment">‹</button>
      )}
      {framed ? (
        <div className="qc-viewer" data-kind={item.kind}>
          <div className="qc-viewer-head">
            <h2 className="qc-viewer-title">{item.name}</h2>
            <p className="qc-viewer-what">{[kindWords[item.kind], item.mediaType, formatSize(item.size)].filter(Boolean).join(' · ')}</p>
            <a className="qc-viewer-download" href={item.url} download={item.name}
              aria-label={`Download ${item.name}`}>Download ↓</a>
          </div>
          <div className="qc-viewer-content"><Body item={item} /></div>
        </div>
      ) : (
        <>
          <Body item={item} />
          <a className="qc-viewer-download qc-viewer-download-bare" href={item.url} download={item.name}
            aria-label={`Download ${item.name}`}>Download ↓</a>
        </>
      )}
      {items.length > 1 && (
        <button type="button" className="qc-media-lightbox-next" onClick={() => step(1)} aria-label="Next attachment">›</button>
      )}
      {items.length > 1 && <p className="qc-media-lightbox-count">{index + 1} of {items.length}</p>}
    </div>
  )
}
