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
import type { SpaceBrainKey, SpaceSessionId } from '../space/contract'
import type { Id } from '../sample'

/** Where a viewed thing came from: kept with every view of it.
 *
 *  MOST THINGS COME FROM A POST, and their frame returns to it. THE BRAIN
 *  ITSELF DOES NOT: the 3D Brain is the whole Brain this page serves, and it
 *  has no post. It says so, rather than being given one (addendum §1): there
 *  is no synthetic post anywhere, and every consumer of a source asks which
 *  kind it is. */
export type ViewerSource =
  | {
      kind: 'post'
      /** the conversation the post lives in; absent for the sample */
      conversation?: Id
      /** the post or reply the content belongs to */
      post: Id
    }
  | { kind: 'brain'; brainKey: SpaceBrainKey }
  | { kind: 'magnet-item'; brainKey: string; resourceId: string; conversation: string; post: string }

/** The post a source came from, or null where it came from the Brain. */
export const postSource = (s: ViewerSource): { conversation?: Id; post: Id } | null =>
  s.kind === 'post' || s.kind === 'magnet-item' ? s : null

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
  /** THE 3D BRAIN, the existing graph drawn in this frame. Its own state is
   *  only which session it is bound to (`SpaceState`): the camera, selection,
   *  filters, time and read live in that session, which outlives the frame
   *  being drawn anew in another column (addendum §1). */
  | { kind: 'brain-space' }
  | { kind: 'magnet'; resourceId: string; magnetId: string; brainKey: string }

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

/** THE GRAPH'S FRAME STATE IS AN ID, AND NOTHING ELSE (addendum §1): never
 *  the session object, and never a copy of its camera or its read. */
export interface SpaceState { sessionId: SpaceSessionId }

/** What every renderer is given. `placement` lets a renderer pick sensible
 *  defaults for the room it has (a column is narrower than a maximised view);
 *  it must not change the content. */
export interface RendererProps<S> {
  state: S
  onState: (next: S) => void
  placement: 'max' | 'column'
}
