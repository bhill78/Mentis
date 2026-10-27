/* WHAT FITS (#1 compact / medium / large; adm-c93a 3.1, 5.2, L5): an object
 * is drawn from the space it is given, not always as a compact card. The
 * drawing's size comes from its width; below what its kind can be read at,
 * it is a readable plate with Open wider (adm-c93a 3.3: "supported sizes
 * don't fit: readable text ... plus Open wider"). */

import { useLayoutEffect, useRef, useState, type RefObject } from 'react'
import type { PostObjectEntry } from '../store'
import { kindOf } from '../../experimental/objectkinds'

export type Size = 'compact' | 'medium' | 'large'
export type Fit = Size | 'fallback'

/* What an object is comes from the kind registry (experimental/objectkinds.ts). */
export const isPicture = (o: PostObjectEntry) => kindOf(o).word === 'image'
/** A film or sound FILE. A video link is not: it plays in its own plate. */
export const isPlayable = (o: PostObjectEntry) => o.kind === 'media' && /^(video|audio)$/.test(kindOf(o).word)
/** What the post-scoped viewer shows: pictures, and sound and film. */
export const isViewable = (o: PostObjectEntry) => isPicture(o) || isPlayable(o)

/** Width bands, the content's own width (a card's padding taken off). */
export const sizeOf = (w: number): Size => (w < 300 ? 'compact' : w < 600 ? 'medium' : 'large')

/** The narrowest and lowest each kind can still be read at. */
function least(o: PostObjectEntry): { w: number; h: number } {
  if (isPicture(o)) return { w: 72, h: 56 }
  if (o.kind === 'block') {
    if (o.type === 'table') return { w: 220, h: 96 }
    if (o.type === 'chart' || o.type === 'diagram' || o.type === 'timeline') return { w: 200, h: 110 }
    return { w: 160, h: 64 }
  }
  if (o.kind === 'post-text') return { w: 150, h: 56 }
  if (o.kind === 'link') return o.link?.video ? { w: 160, h: 90 } : { w: 120, h: 40 }
  return { w: 140, h: 56 }
}

/* WHAT ITS AUTHOR DECLARED (adm-c93a 3.1; #31: "objects may declare
   supported compact, medium and large presentations and an optional
   preferred size"; L8). A block may say `sizes=`, `prefer=` and `open=`;
   they are read by the renderer's own rules (experimental/spec/core.ts
   `readShared`): a bad value is ignored and its default applies, so a
   declaration can never hide content. Only what was written counts: a block
   that says nothing is drawn as large as its space allows, as before.
   (Read here rather than imported: Fluid asking production's shared chunk
   for an export it never asked for would rename production's -- vite.config.ts.) */
const ORDER: Size[] = ['compact', 'medium', 'large']
export interface Declared { sizes: Size[] | null; prefer: Size | null; open: boolean | null }
const ATTR = /(?:^|\s)([A-Za-z][A-Za-z0-9_-]*)=(?:"((?:[^"\\]|\\.)*)"|([^\s"]+))/g
function attrsOf(info: string): Record<string, string> {
  const out: Record<string, string> = {}
  for (const m of info.matchAll(ATTR)) if (!(m[1] in out)) out[m[1]] = m[2] !== undefined ? m[2] : m[3]
  return out
}
const read = new WeakMap<object, Declared | null>()
export function declaredOf(o: PostObjectEntry): Declared | null {
  const b = o.kind === 'block' ? o.block : undefined
  if (!b || typeof b.info !== 'string') return null
  if (read.has(b)) return read.get(b)!
  const a = attrsOf(b.info)
  let out: Declared | null = null
  if ('sizes' in a || 'prefer' in a || 'open' in a) {
    const listed = 'sizes' in a ? a.sizes.split(',').map((x) => x.trim()) : null
    const sizes = listed && listed.length && listed.every((x) => (ORDER as string[]).includes(x)) ? ORDER.filter((x) => listed.includes(x)) : null
    const allowed = sizes ?? ORDER
    const prefer = 'prefer' in a && allowed.includes(a.prefer as Size) ? (a.prefer as Size)
      : sizes ? (sizes.includes('medium') ? 'medium' : sizes[sizes.length - 1]) : null
    /* open=false folds only what has a label to fold to: a title, or a
       panel's leading heading */
    const label = !!a.title || (b.type === 'panel' && /^\s*#{1,6}\s/.test(b.body))
    const open = a.open === 'false' && label ? false : a.open === 'true' ? true : null
    out = { sizes, prefer, open }
  }
  read.set(b, out)
  return out
}

/** The presentation an object gets in a box of w x h (content pixels): the
 *  size its width allows -- or, where its author declared sizes, the
 *  preferred size if it fits, else the nearest smaller one it supports, else
 *  the readable plate (adm-c93a 5.2). */
export function fitFor(o: PostObjectEntry, w: number, h: number): Fit {
  const min = least(o)
  if (w > 0 && w < min.w) return 'fallback'
  if (h > 0 && h < min.h) return 'fallback'
  const room = sizeOf(w)
  const d = declaredOf(o)
  if (!d || (!d.sizes && !d.prefer)) return room
  const fits = (x: Size) => ORDER.indexOf(x) <= ORDER.indexOf(room)
  if (d.prefer && fits(d.prefer)) return d.prefer
  const smaller = (d.sizes ?? ORDER).filter(fits)
  return smaller.length ? smaller[smaller.length - 1] : 'fallback'
}

/** An element's content box, kept current as the zone is dragged. */
export function useBox(ref: RefObject<HTMLElement | null>): { w: number; h: number } {
  const [box, setBox] = useState({ w: 0, h: 0 })
  const watched = useRef<{ el: HTMLElement; ro: ResizeObserver } | null>(null)
  /* The element can be replaced (a zone body is keyed by what it follows):
     whichever is there after a render is the one watched. */
  useLayoutEffect(() => {
    const el = ref.current
    if (watched.current?.el === el) return
    watched.current?.ro.disconnect()
    watched.current = null
    if (!el) return
    const read = () => {
      const w = Math.round(el.clientWidth), h = Math.round(el.clientHeight)
      setBox((b) => (b.w === w && b.h === h ? b : { w, h }))
    }
    read()
    const ro = new ResizeObserver(read)
    ro.observe(el)
    watched.current = { el, ro }
  })
  useLayoutEffect(() => () => { watched.current?.ro.disconnect(); watched.current = null }, [])
  return box
}
