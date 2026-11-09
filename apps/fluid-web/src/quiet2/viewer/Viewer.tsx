/* THE VIEWER FRAME (Viewer round 1): one compact header for every kind of
 * content, and the renderer for that kind below it.
 *
 * The header says what the content is and where it came from (the source
 * conversation and post, which return to it), and offers what is the same
 * everywhere: move to a working column, maximise or restore, close. What the
 * renderer draws, and its own toolbar, are the renderer's:
 *   PDF          PdfView (pdf.js): pages, spreads, scrolling, rail, zoom
 *   pictures     GalleryView: across, grid, focus, mosaic; enlarge, zoom, pan
 *   other files  Mark 1's viewer body (Markdown, text, HTML mockups, film,
 *                sound; anything else offered as a download)
 *   rendered     the Markdown renderer's own block (a table, code, a chart),
 *   blocks       drawn by Prose at the room the viewer has
 * A renderer that cannot be loaded leaves the frame standing and says so. */
import { lazy, Suspense, useEffect, useRef, type ReactNode } from 'react'
import { ViewerBody } from '../../quiet/media/MediaLayer'
import { TextBlock } from '../Post'
import { postOf, usePosts } from '../real'
import { useConversationName } from '../Surface'
import GalleryView from './GalleryView'
import type { GalleryState, PdfState } from './types'
import { kindOf, setViewerState, useViewers, viewerOf, type OpenViewer } from './viewers'
import './viewer.css'

/* pdf.js is large: loaded when a PDF is first viewed */
const PdfView = lazy(() => import('./PdfView'))

export interface ViewerActions {
  /** the columns it could move to now, with what each holds (null: empty) */
  columns: { s: 's1' | 's2'; label: string; holds: string | null; draft?: boolean }[]
  moveTo: (s: 's1' | 's2') => void
  maximise: (() => void) | null
  restore: (() => void) | null
  close: () => void
  /** back to the post it came from */
  toSource: () => void
  /** the source's conversation name, for the header */
  sourceName: string | null
}

const I = ({ d }: { d: ReactNode }) => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{d}</svg>
)
const MAX = <I d={<><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5" /></>} />
const RESTORE = <I d={<><path d="M9 4v5H4M15 4v5h5M9 20v-5H4M15 20v-5h5" /></>} />
const DOWNLOAD = <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><path d="M12 4v11M7 10l5 5 5-5M5 20h14" /></svg>
const MOVE = <I d={<><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M13 4v16" /><path d="m7 10 2 2-2 2" /></>} />

function Body({ v, placement }: { v: OpenViewer; placement: 'max' | 'column' }) {
  usePosts()
  const c = v.content
  const on = (s: unknown) => setViewerState(v.id, s)
  switch (c.kind) {
    case 'pdf':
      return (
        <Suspense fallback={<p className="q2v-wait">Loading the document viewer…</p>}>
          <PdfView url={c.url} name={c.name} state={v.state as PdfState} onState={on} placement={placement} />
        </Suspense>
      )
    case 'gallery':
      return <GalleryView images={c.images} state={v.state as GalleryState} onState={on} placement={placement} />
    case 'file':
      return <div className="q2v-stage q2v-file"><div className="q2v-file-inner"><ViewerBody item={c.item} /></div></div>
    case 'block': {
      const p = postOf(c.post)
      const b = p?.blocks[c.block]
      return (
        <div className="q2v-stage q2v-block">
          {b?.kind === 'text'
            ? <div className="q2v-block-inner"><TextBlock md={b.md} scope={`q2v:${c.post}:${c.block}`} focus={c.element} /></div>
            : <p className="q2v-wait">That content is no longer held here.</p>}
        </div>
      )
    }
  }
}

export default function Viewer({ id, placement, actions }: { id: string; placement: 'max' | 'column'; actions: ViewerActions }) {
  useViewers()
  const v = viewerOf(id)
  /* the source conversation's name, read if this page has not read it yet */
  const named = useConversationName(v?.source.conversation)
  /* moved (maximised, restored, to a column), the viewer is drawn anew:
     focus comes with it rather than falling to the page */
  const self = useRef<HTMLElement>(null)
  useEffect(() => {
    if (document.activeElement === document.body) self.current?.querySelector<HTMLElement>('.q2v-head button')?.focus()
  }, [placement])
  if (!v) return null
  const p = postOf(v.source.post)
  const from = [actions.sourceName ?? named, p?.number ? `#${p.number}` : null, p ? `by ${p.by.name.replace(/^@/, '')}` : null].filter(Boolean).join(' · ')
  const free = actions.columns.filter((c) => c.holds === null)
  return (
    <section ref={self} className={`q2v q2v-${placement}`} aria-label={`${kindOf(v.content)}: ${v.title}`} data-viewer={v.id}>
      <header className="q2v-head">
        <div className="q2v-id">
          <span className="q2v-title" title={v.title}>{v.title}</span>
          <span className="q2v-meta">
            <span className="q2v-kind">{kindOf(v.content)}</span>
            {from && <> · <button className="q2v-source" onClick={actions.toSource} title="Back to the post it came from">from {from}</button></>}
          </span>
        </div>
        {/* THE BYTES STAY REACHABLE, as in Mentis's own viewer: the file
            itself, from the artifact address it was read from */}
        {(() => {
          const c = v.content
          const d = c.kind === 'pdf' ? { url: c.url, name: c.name } : c.kind === 'file' ? { url: c.item.url, name: c.item.name }
            : c.kind === 'gallery' ? (() => { const im = c.images[(v.state as GalleryState).index] ?? c.images[0]; return im && { url: im.url, name: im.name } })() : null
          return d ? <a className="q2v-btn q2v-download" href={d.url} download={d.name} title={`Download ${d.name}`} aria-label={`Download ${d.name}`}>{DOWNLOAD}<span className="q2v-hide-narrow">Download</span></a> : null
        })()}
        {actions.columns.length > 0 && (
          <details className="q2v-move">
            <summary className="q2v-btn" title="Move to a working column" aria-label="Move to a working column">{MOVE}<span className="q2v-hide-narrow">Move</span></summary>
            <div className="q2v-menu" role="menu">
              {actions.columns.map((c) => (
                <button key={c.s} role="menuitem" onClick={(e) => { (e.currentTarget.closest('details') as HTMLDetailsElement).open = false; actions.moveTo(c.s) }}>
                  <span>{c.label}</span><span className="q2v-menu-sub">{c.holds === null ? 'empty' : `replaces ${c.holds}${c.draft ? ' (its unsent draft stays saved with its place)' : ''}`}</span>
                </button>
              ))}
              {free.length === 0 && <p className="q2v-menu-note">Every column is in use: choosing one replaces what it shows.</p>}
            </div>
          </details>
        )}
        {actions.restore
          ? <button className="q2v-btn" onClick={actions.restore} title="Restore" aria-label="Restore">{RESTORE}</button>
          : actions.maximise && <button className="q2v-btn" onClick={actions.maximise} title="Maximise" aria-label="Maximise">{MAX}</button>}
        <button className="q2v-btn q2v-close" onClick={actions.close} title="Close and return to the conversation" aria-label="Close viewer">×</button>
      </header>
      <div className="q2v-content"><Body v={v} placement={placement} /></div>
    </section>
  )
}
