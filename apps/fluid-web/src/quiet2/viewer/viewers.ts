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
import { readPrefs, savePrefs } from '../prefs'
import { GALLERY_START, PDF_START, type GalleryState, type PdfState, type Viewable, type ViewerSource } from './types'

export type Place = 'max' | 's1' | 's2'

export interface OpenViewer {
  id: string
  content: Viewable
  source: ViewerSource
  /** what it is called, for its header */
  title: string
  /** its renderer's own state, kept across moves */
  state: unknown
  place: Place
  /** maximised from a column: the column Restore returns it to */
  from: 's1' | 's2' | null
}

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
  }
}

export function kindOf(c: Viewable): string {
  switch (c.kind) {
    case 'pdf': return 'PDF'
    case 'gallery': return c.images.length > 1 ? 'Pictures' : 'Picture'
    case 'file': return c.item.kind === 'markdown' ? 'Document' : c.item.kind === 'html' ? 'HTML mockup' : c.item.kind === 'text' ? 'Text' : c.item.kind === 'video' ? 'Film' : c.item.kind === 'audio' ? 'Sound' : 'File'
    case 'block': return c.label
  }
}

/** Opens `content` from `source` at `place`; returns the viewer's id. */
export function openViewer(content: Viewable, source: ViewerSource, place: Place): string {
  const id = `v${++seq}`
  /* one maximised viewer at a time: one already maximised goes back to its
     column, or closes when it has none */
  if (place === 'max') for (const v of open.values()) if (v.place === 'max') {
    if (v.from) open.set(v.id, { ...v, place: v.from, from: null }); else { open.delete(v.id); release(v) }
  }
  open.set(id, { id, content, source, title: titleOf(content), state: startOf(content), place, from: null })
  changed()
  return id
}

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
  if (place === 'max') for (const o of open.values()) if (o.id !== id && o.place === 'max') {
    if (o.from) open.set(o.id, { ...o, place: o.from, from: null }); else { open.delete(o.id); release(o) }
  }
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
    const col = v.place === 'max' ? v.from : v.place
    if (!col || shown.includes(col)) continue
    n++
    if (v.place === 'max') open.set(v.id, { ...v, from: null })
    else if (!maximised()) open.set(v.id, { ...v, place: 'max', from: null })
    else { open.delete(v.id); release(v) }
  }
  if (n) changed()
  return n
}

/** The viewer shown maximised, if any. */
export const maximised = () => [...open.values()].find((v) => v.place === 'max') ?? null
/** The viewer shown in column `s`, if any. */
export const inColumn = (s: 's1' | 's2') => [...open.values()].find((v) => v.place === s || (v.place === 'max' && v.from === s)) ?? null
