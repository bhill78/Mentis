/* THE OPEN VIEWERS, each held once (Viewer round 1).
 *
 * A viewer is one thing being looked at: its content, where it came from,
 * its renderer's state (page, selected picture, zoom), and where it is shown
 * now -- maximised over the conversation, or in working column 1 or 2.
 * Moving it changes only `place`; the renderer's state stays here, so the
 * viewer in a column and the same viewer maximised are one viewer, never a
 * copy. Closing removes the viewer and nothing else: its source is untouched.
 *
 * Placement decisions that need the page (is a column free? is it holding a
 * draft?) are the page's; this store only holds what is open. */
import { useSyncExternalStore } from 'react'
import type { ParkedFrom } from '../space/placement'
import { readPrefs, savePrefs } from '../prefs'
import { GALLERY_START, PDF_START, type GalleryState, type PdfState, type Viewable, type ViewerSource } from './types'

export type Place = 'max' | 's1' | 's2'
/** PARKED (addendum §3): open, holding its id and its session, shown nowhere.
 *  Only the 3D Brain may be parked -- everything else here is drawn where it
 *  is or not open at all. A parked viewer is excluded from `maximised`,
 *  `inColumn`, eviction and column settlement, and occupies no column and no
 *  maximised reservation. */
export type Where = Place | 'parked'

export interface OpenViewer {
  id: string
  content: Viewable
  source: ViewerSource
  /** what it is called, for its header */
  title: string
  /** its renderer's own state, kept across moves */
  state: unknown
  place: Where
  /** maximised from a column: the column Restore returns it to */
  from: 's1' | 's2' | null
  /** parked: where it was, so coming back can ask for the same place */
  parkedFrom?: ParkedFrom
}

/** Whether this viewer may be parked rather than closed. */
export const parkable = (v: OpenViewer) => v.content.kind === 'brain-space'
/** Shown somewhere now. */
export const shownViewer = (v: OpenViewer) => v.place !== 'parked'

const open = new Map<string, OpenViewer>()
let version = 0
/* PLACEMENT apart from STATE: the page re-renders when a viewer opens, closes
   or moves; only the viewer itself re-renders for a page turn or a pan */
let layout = 0
const heard = new Set<() => void>()
const changed = (moved = true) => { version++; if (moved) layout++; heard.forEach((fn) => fn()) }
const subscribe = (fn: () => void) => { heard.add(fn); return () => { heard.delete(fn) } }
/** Every change, for a viewer drawing its own state. */
export const useViewers = () => { useSyncExternalStore(subscribe, () => version); return open }
/** Only what is open where, for the page. */
export const useViewerLayout = () => { useSyncExternalStore(subscribe, () => layout); return open }
export const viewerOf = (id: string) => open.get(id)

let seq = 0
/* A NEW VIEWER STARTS as the reader last chose to be shown that kind of
   thing (prefs.ts): a PDF's mode and fit, a picture viewer's layout. Its
   page, zoom and selected picture are its own, never carried over. */
const startOf = (c: Viewable): unknown => {
  const p = readPrefs()
  return c.kind === 'pdf' ? { ...PDF_START, mode: p.pdf.mode, zoom: p.pdf.fit } satisfies PdfState
    : c.kind === 'gallery' ? { ...GALLERY_START(c.start), layout: p.gallery.layout } satisfies GalleryState
    : null
}

/** The reader's choice of presentation, kept as the default for viewers
 *  opened after it; a fixed zoom or a page turn is not a preference. */
function rememberPresentation(c: Viewable, was: unknown, now: unknown) {
  if (c.kind === 'pdf') {
    const a = was as PdfState, b = now as PdfState
    const fit = b.zoom === 'page' || b.zoom === 'width' ? b.zoom : null
    if (a.mode !== b.mode || (fit && a.zoom !== b.zoom)) {
      const p = readPrefs()
      savePrefs({ pdf: { mode: b.mode, fit: fit ?? p.pdf.fit } })
    }
  } else if (c.kind === 'gallery') {
    const a = was as GalleryState, b = now as GalleryState
    if (a.layout !== b.layout) savePrefs({ gallery: { layout: b.layout } })
  }
}

export function titleOf(c: Viewable): string {
  switch (c.kind) {
    case 'pdf': return c.name
    case 'gallery': return c.images.length > 1 ? `${c.images.length} pictures` : c.images[0]?.name ?? 'Picture'
    case 'file': return c.item.name
    case 'block': return c.label
    case 'brain-space': return '3D Brain'
  }
}

export function kindOf(c: Viewable): string {
  switch (c.kind) {
    case 'pdf': return 'PDF'
    case 'gallery': return c.images.length > 1 ? 'Pictures' : 'Picture'
    case 'file': return c.item.kind === 'markdown' ? 'Document' : c.item.kind === 'html' ? 'HTML mockup' : c.item.kind === 'text' ? 'Text' : c.item.kind === 'video' ? 'Film' : c.item.kind === 'audio' ? 'Sound' : 'File'
    case 'block': return c.label
    case 'brain-space': return 'Brain'
  }
}

/** A MAXIMISED VIEWER GIVING WAY to another: back to its column where it has
 *  one, else parked if it may be (the 3D Brain), else closed. A graph is
 *  never closed by a placement path -- only by the one release path. */
function displaceMax(v: OpenViewer) {
  if (v.from) { open.set(v.id, { ...v, place: v.from, from: null }); return }
  if (parkable(v)) { open.set(v.id, { ...v, place: 'parked', from: null, parkedFrom: { place: 'max', from: null } }); return }
  open.delete(v.id); release(v)
}

/** Opens `content` from `source` at `place`; returns the viewer's id.
 *  `state` is for a renderer whose state is given at the start (the graph's
 *  session id); everything else starts as the reader last left its kind. */
export function openViewer(content: Viewable, source: ViewerSource, place: Place, state?: unknown): string {
  const id = `v${++seq}`
  /* one maximised viewer at a time: one already maximised goes back to its
     column, or parks or closes when it has none */
  if (place === 'max') for (const v of open.values()) if (v.place === 'max') displaceMax(v)
  open.set(id, { id, content, source, title: titleOf(content), state: state ?? startOf(content), place, from: null })
  changed()
  return id
}

/** PARKED: the same viewer, holding its id and its renderer's state, shown
 *  nowhere, and remembering where it was so it can ask for it back.
 *
 *  `keeping` is WHO IS ANSWERING FOR THE WAY BACK, and defaults to the graph,
 *  so every existing call means exactly what it meant. The 3D Brain may always
 *  park: the space navigation brings it back. Anything else may park only when
 *  the caller says it has kept a way back to it -- which a result has: its
 *  launch, its history entry and its return bar (`results/hostOpen.ts`
 *  `sourceSteps` `park`, `resumeSteps` `show-viewer`). Without this a "Go to
 *  source" from a maximised artifact with no column was a no-op, and the
 *  viewer stayed drawn over the very post it was sending the reader to
 *  (re-review adm-263df1ccb512, F10). A parked viewer is still excluded from
 *  `maximised`, `inColumn`, eviction and settlement, and still occupies
 *  nothing. */
export function parkViewer(id: string, keeping: 'graph' | 'kept' = 'graph') {
  const v = open.get(id)
  if (!v || v.place === 'parked' || (keeping === 'graph' && !parkable(v))) return
  open.set(id, { ...v, place: 'parked', from: null, parkedFrom: { place: v.place, from: v.place === 'max' ? v.from : null } })
  changed()
}

/** Back from parked, to the place the page chose for it (placement.ts says
 *  which). The same viewer and the same session: never a new one. */
export function returnViewer(id: string, place: Place, from: 's1' | 's2' | null) {
  const v = open.get(id)
  if (!v || v.place !== 'parked') return
  if (place === 'max') for (const o of open.values()) if (o.id !== id && o.place === 'max') displaceMax(o)
  open.set(id, { ...v, place, from: place === 'max' ? from : null, parkedFrom: undefined })
  changed()
}

/** Where a parked viewer was, for the page to ask for it again. */
export const parkedPlaceOf = (id: string) => open.get(id)?.parkedFrom ?? null
/** The parked viewers now, in the order they were opened. */
export const parkedViewers = () => [...open.values()].filter((v) => v.place === 'parked')
/** THE PAGE'S ONE GRAPH, wherever it is -- in a column, maximised or parked.
 *  There is at most one: the page focuses and reuses it rather than opening a
 *  second (addendum §1, "at most one live graph per resolved Brain"). */
export const spaceViewer = () => [...open.values()].find((v) => v.content.kind === 'brain-space') ?? null

export function setViewerState(id: string, state: unknown) {
  const v = open.get(id)
  if (!v) return
  if (v.state && state) rememberPresentation(v.content, v.state, state)
  open.set(id, { ...v, state })
  changed(false)
}

/** Shown elsewhere, the same viewer: maximised (remembering the column it
 *  left, if any), back to that column, or to another column. */
export function moveViewer(id: string, place: Place) {
  const v = open.get(id)
  if (!v || v.place === place) return
  /* a parked viewer comes back through `returnViewer`, which asks the page
     where it may go; a move is for one that is shown */
  if (v.place === 'parked') return
  if (place === 'max') for (const o of open.values()) if (o.id !== id && o.place === 'max') displaceMax(o)
  open.set(id, { ...v, place, from: place === 'max' ? (v.place === 'max' ? v.from : v.place) : null })
  changed()
}

export function closeViewer(id: string) {
  const v = open.get(id)
  if (v && open.delete(id)) { release(v); changed() }
}

/** A closed PDF's document is let go once no open viewer shows it. */
function release(v: OpenViewer) {
  if (v.content.kind !== 'pdf') return
  const url = v.content.url
  if ([...open.values()].some((o) => o.content.kind === 'pdf' && o.content.url === url)) return
  void import('./pdfDoc').then((m) => m.releasePdf(url))
}

/** Columns that are no longer shown give their viewers up: maximised if
 *  nothing is maximised, else closed (their source is untouched). Returns
 *  how many were moved or closed. */
export function settleColumns(shown: ('s1' | 's2')[]): number {
  let n = 0
  for (const v of [...open.values()]) {
    /* A PARKED GRAPH IS NOT IN A COLUMN and reserves none: settlement has
       nothing to release (addendum §3, "settleColumns must not release it"). */
    if (v.place === 'parked') continue
    const col = v.place === 'max' ? v.from : v.place
    if (!col || shown.includes(col)) continue
    n++
    if (v.place === 'max') open.set(v.id, { ...v, from: null })
    else if (!maximised()) open.set(v.id, { ...v, place: 'max', from: null })
    /* the graph goes nowhere to be closed: it parks, keeping its session */
    else if (parkable(v)) open.set(v.id, { ...v, place: 'parked', from: null, parkedFrom: { place: v.place, from: null } })
    else { open.delete(v.id); release(v) }
  }
  if (n) changed()
  return n
}

/** The viewer shown maximised, if any. */
export const maximised = () => [...open.values()].find((v) => v.place === 'max') ?? null
/** The viewer shown in column `s`, if any. A parked viewer is in none. */
export const inColumn = (s: 's1' | 's2') => [...open.values()].find((v) => v.place === s || (v.place === 'max' && v.from === s)) ?? null
