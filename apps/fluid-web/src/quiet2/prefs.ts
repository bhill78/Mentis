/* THE READER'S PREFERENCES, remembered by this browser (Track B).
 *
 * One model, three kinds of thing, each kept in one place:
 *
 * 1. HOW THINGS LOOK -- global, the same on every Brain, conversation and
 *    surface. Mentis has no per-reader settings on the server (Fluid's
 *    `/fluid/api/settings` is Brain-wide, holds only `makeRoom`, and is a
 *    Brain write that DAY-TO-DAY refuses), so these are BROWSER-LOCAL:
 *      theme                      `mentis:theme`            Fluid's own (setTheme)
 *      reading surface solid/glass `mentis:quiet-surface`   Mark 1's store
 *      opacity, blur              `mentis:quiet-appearance` Mark 1's store
 *      header bar                 `q2:topbar`               Look.tsx
 *      reading measure, picture collection's arrangement, a new PDF
 *      viewer's mode and fit, a new picture viewer's layout
 *                                 `q2:prefs`                here
 *    The existing keys are kept as they are; nothing is duplicated here.
 *
 * 2. THE WORKSPACE -- how the page is arranged, and the conversation last
 *    read: one, two or three columns, the conversation's side, receded or
 *    restored, the column widths per arrangement, the conversation. It names
 *    conversation ids, so it is kept PER BRAIN, browser-local:
 *      `q2:workspace:dev`, `q2:workspace:dayday` (the development server's
 *      two Brains), `q2:workspace:page` (a page Mentis serves itself).
 *    Nothing that writes (drafts, permissions) is kept here: drafts stay
 *    Fluid's own, in its session store, with the Brain they belong to.
 *
 * 3. WHAT IS BEING LOOKED AT -- an open viewer's page, zoom, selected
 *    picture -- is the viewer's own state (viewers.ts) and is not a
 *    preference. Only the presentation a reader chose (a PDF's mode and fit,
 *    a gallery's layout) becomes the default for viewers opened after it.
 *
 * The Brain's look (its background) is the Brain's, server-side: Fluid reads
 * it back for every page (`useLook`), so nothing about it is kept here.
 *
 * Address parameters (`?arr=`, `?side=`, `?receded=`, `?measure=`, `?c=`)
 * override what is restored for that load only; what is saved changes only
 * when the reader changes it. */
import { BRAIN } from './live'
import type { GalleryLayout, PdfFit, PdfMode } from './viewer/types'

export type Arrangement = 'one' | 'two' | 'three'
export type Side = 'left' | 'right'
export type Measure = 'current' | 'wide'

const one = <T extends string>(v: unknown, ok: readonly T[], d: T): T => (ok as readonly unknown[]).includes(v) ? v as T : d
const GALLERY: readonly GalleryLayout[] = ['across', 'grid', 'focus', 'mosaic']

function read(key: string): Record<string, unknown> {
  try {
    const v: unknown = JSON.parse(localStorage.getItem(key) ?? '{}')
    return v && typeof v === 'object' && !Array.isArray(v) ? v as Record<string, unknown> : {}
  } catch { return {} }
}
function write(key: string, value: object) {
  try { localStorage.setItem(key, JSON.stringify(value)) } catch { /* this page only */ }
}
const obj = (v: unknown): Record<string, unknown> => v && typeof v === 'object' && !Array.isArray(v) ? v as Record<string, unknown> : {}

/* -- 1. global: how things look ------------------------------------------ */

export interface Prefs {
  measure: Measure
  /** an inline picture collection's arrangement, as first drawn */
  collection: GalleryLayout
  /** a newly opened PDF viewer */
  pdf: { mode: PdfMode; fit: PdfFit }
  /** a newly opened picture viewer */
  gallery: { layout: GalleryLayout }
}
const PREFS_KEY = 'q2:prefs'

export function readPrefs(): Prefs {
  const p = read(PREFS_KEY)
  const pdf = obj(p.pdf), gallery = obj(p.gallery)
  return {
    measure: one(p.measure, ['current', 'wide'], 'current'),
    collection: one(p.collection, GALLERY, 'grid'),
    pdf: { mode: one(pdf.mode, ['single', 'spread', 'scroll'], 'single'), fit: one(pdf.fit, ['page', 'width'], 'page') },
    gallery: { layout: one(gallery.layout, GALLERY, 'focus') },
  }
}
export function savePrefs(change: Partial<Prefs>) {
  write(PREFS_KEY, { ...readPrefs(), ...change })
}

/* -- 2. per Brain: the workspace ----------------------------------------- */

export interface Workspace {
  arr: Arrangement
  side: Side
  receded: boolean
  /** column widths, as fractions of the row, by the panes shown ("conv,s1") */
  sizes: Record<string, number[]>
  /** the conversation last chosen; null for the Brain's most recent */
  conversation: string | null
}

/** which Brain this page's workspace belongs to */
export const brainScope = () => BRAIN?.brain ?? 'page'
const workspaceKey = () => `q2:workspace:${brainScope()}`

const PANES = /^(conv|s1|s2)(,(conv|s1|s2)){0,2}$/
function sizesOf(v: unknown): Record<string, number[]> {
  const out: Record<string, number[]> = {}
  for (const [k, s] of Object.entries(obj(v))) {
    if (!PANES.test(k) || !Array.isArray(s) || s.length !== k.split(',').length) continue
    if (!s.every((x) => typeof x === 'number' && Number.isFinite(x) && x >= 0)) continue
    const sum = (s as number[]).reduce((a, b) => a + b, 0)
    if (sum > 0.98 && sum < 1.02) out[k] = s as number[]
  }
  return out
}

export function readWorkspace(): Workspace {
  const w = read(workspaceKey())
  return {
    arr: one(w.arr, ['one', 'two', 'three'], 'one'),
    side: one(w.side, ['left', 'right'], 'left'),
    receded: w.receded === true,
    sizes: sizesOf(w.sizes),
    conversation: typeof w.conversation === 'string' && w.conversation ? w.conversation : null,
  }
}
export function saveWorkspace(change: Partial<Workspace>) {
  write(workspaceKey(), { ...readWorkspace(), ...change })
}
