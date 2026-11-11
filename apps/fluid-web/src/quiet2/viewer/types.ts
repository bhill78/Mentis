/* THE VIEWER'S CONTRACT (Viewer round 1).
 *
 * One viewer frame, many renderers. The FRAME (Viewer.tsx, viewers.ts) owns
 * what is the same for every kind of content: what it is and where it came
 * from, where it is shown (maximised over the conversation, or in a working
 * column), moving between those, maximising and restoring, closing and
 * returning to the source. A RENDERER owns how its kind of content is drawn
 * and navigated: pages, spreads, thumbnails and zoom for a PDF; arrangements
 * of a picture collection; the Markdown renderer's own blocks.
 *
 * A renderer is a component given its content, its state and a way to
 * change that state. The state is the renderer's own, but HELD BY THE FRAME,
 * so moving the viewer between places (maximised, column 1, column 2) keeps
 * the page, the selected picture, the zoom: the same viewer, not a copy.
 * A renderer must never assume it stays mounted. */
import type { ViewerItem } from '../../quiet/media/view'
import type { Id } from '../sample'

/** Where a viewed thing came from: kept with every view of it. */
export interface ViewerSource {
  /** the conversation the post lives in; absent for the sample */
  conversation?: Id
  /** the post or reply the content belongs to */
  post: Id
}

/** One picture of a collection. */
export interface ViewImage { url: string; name: string; alt: string }

/** What can be viewed. Each kind has its own renderer. */
export type Viewable =
  /** a PDF document, drawn by PdfView (pdf.js) */
  | { kind: 'pdf'; url: string; name: string; size?: number | null }
  /** one picture or a post's pictures, drawn by GalleryView */
  | { kind: 'gallery'; images: ViewImage[]; start: number }
  /** any other file Mentis's existing viewer draws (Markdown, text, HTML
   *  mockups, video, audio), or offers as a download */
  | { kind: 'file'; item: ViewerItem }
  /** content the Markdown renderer drew inside a post (a table, code, a
   *  chart or other renderable block), shown by that renderer */
  | { kind: 'block'; post: Id; block: number; element: number; label: string }

/* -- each renderer's own state (held by the frame) ------------------------- */

export type PdfMode = 'single' | 'spread' | 'scroll'
export type PdfFit = 'page' | 'width'
export interface PdfState {
  mode: PdfMode
  /** 1-based; in a spread, the left page */
  page: number
  /** a fit, or a fixed zoom (1 = 100%) */
  zoom: PdfFit | number
  /** the collapsible side rail: nothing, page thumbnails, or the outline */
  rail: 'none' | 'thumbs' | 'outline'
}
export const PDF_START: PdfState = { mode: 'single', page: 1, zoom: 'page', rail: 'none' }

export type GalleryLayout = 'across' | 'grid' | 'focus' | 'mosaic'
export interface GalleryState {
  layout: GalleryLayout
  /** the selected picture, an index into the collection */
  index: number
  /** the selected picture shown enlarged within the viewer */
  enlarged: boolean
  /** zoom of the enlarged picture (1 = fitted) and its pan, in px */
  zoom: number
  pan: { x: number; y: number }
}
export const GALLERY_START = (start: number): GalleryState => ({ layout: 'focus', index: start, enlarged: false, zoom: 1, pan: { x: 0, y: 0 } })

/** What every renderer is given. `placement` lets a renderer pick sensible
 *  defaults for the room it has (a column is narrower than a maximised view);
 *  it must not change the content. */
export interface RendererProps<S> {
  state: S
  onState: (next: S) => void
  placement: 'max' | 'column'
}
