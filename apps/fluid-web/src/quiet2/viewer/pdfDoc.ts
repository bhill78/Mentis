/// <reference types="vite/client" />
/* The PDF viewer's document side: pdf.js loading, a module-level cache of
 * loaded documents (so a viewer that is remounted, e.g. moved between the
 * maximised view and a column, never fetches or parses again), page sizes
 * and the outline resolved to page numbers. No PDF parsing of our own. */
import * as pdfjs from 'pdfjs-dist'
import type { PDFDocumentProxy } from 'pdfjs-dist'
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url'

pdfjs.GlobalWorkerOptions.workerSrc = workerUrl

/** CSS px per PDF point at 100% (pdf.js's own convention: 96 / 72). */
export const UNIT = 4 / 3

export interface PageSize { w: number; h: number }
export interface OutlineEntry { title: string; page: number | null; depth: number }
export interface LoadedPdf {
  doc: PDFDocumentProxy
  /** every page's size in PDF points, rotation applied */
  sizes: PageSize[]
}

const docs = new Map<string, Promise<LoadedPdf>>()
const outlines = new WeakMap<PDFDocumentProxy, Promise<OutlineEntry[]>>()

/** The document at `url`, loaded once per page lifetime. A failed load is
 *  forgotten so that opening it again tries again. */
export function loadPdf(url: string): Promise<LoadedPdf> {
  let p = docs.get(url)
  if (!p) {
    p = (async () => {
      const doc = await pdfjs.getDocument({ url, isEvalSupported: false }).promise
      /* a page that cannot be read takes the first page's size, so one bad
         page does not stop the document opening */
      const got = await Promise.allSettled(Array.from({ length: doc.numPages }, async (_, i) => {
        const vp = (await doc.getPage(i + 1)).getViewport({ scale: 1 })
        return { w: vp.width, h: vp.height }
      }))
      const first = got.find((g) => g.status === 'fulfilled') as PromiseFulfilledResult<PageSize> | undefined
      const fallback = first?.value ?? { w: 612, h: 792 }
      const sizes = got.map((g) => (g.status === 'fulfilled' ? g.value : fallback))
      return { doc, sizes }
    })()
    p.catch(() => docs.delete(url))
    docs.set(url, p)
  }
  return p
}

/** Let go of the document at `url` (its viewers have all closed). */
export function releasePdf(url: string) {
  const p = docs.get(url)
  if (!p) return
  docs.delete(url)
  void p.then((l) => l.doc.destroy()).catch(() => {})
}

/** The outline, flattened in reading order, each entry resolved to its page. */
export function outlineOf(doc: PDFDocumentProxy): Promise<OutlineEntry[]> {
  let p = outlines.get(doc)
  if (!p) {
    p = (async () => {
      const raw = await doc.getOutline()
      const out: OutlineEntry[] = []
      const walk = async (items: Array<{ title?: unknown; dest?: unknown; items?: unknown }> | null | undefined, depth: number) => {
        for (const it of items ?? []) {
          out.push({ title: String(it.title ?? ''), page: await pageOfDest(doc, it.dest), depth })
          await walk(it.items as typeof items, depth + 1)
        }
      }
      await walk(raw, 0)
      return out
    })().catch(() => [])
    outlines.set(doc, p)
  }
  return p
}

async function pageOfDest(doc: PDFDocumentProxy, dest: unknown): Promise<number | null> {
  try {
    const d = typeof dest === 'string' ? await doc.getDestination(dest) : dest
    if (!Array.isArray(d) || d.length === 0) return null
    const ref = d[0]
    if (typeof ref === 'number') return ref + 1
    if (ref && typeof ref === 'object') return (await doc.getPageIndex(ref)) + 1
  } catch { /* an unresolvable destination is simply not a link */ }
  return null
}
