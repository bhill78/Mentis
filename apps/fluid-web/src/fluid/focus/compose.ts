/* THE FOCUS LENS, AS PURE FUNCTIONS (focus/lens.ts; the fluid-focus alt-b
 * lens model, with the owner's final rules). No DOM and no store here: what
 * the Focus area is, what sits beside it, how a lens session moves through
 * its targets, and the two ways out of it (Restore, Keep this layout). The
 * lens itself (lensImpl.ts) keeps one `Lens` per Page and draws it
 * (LensLayer.tsx); the arrangement is never written while it is on.
 *
 *   THE FOCUS AREA is decided by the room, the presentation and the shape
 *   fixed when Focus was entered (which side the shelf is on, whether there
 *   is one). Never by the target: switching to something else puts the new
 *   content in the same area, which neither shrinks nor moves because the
 *   last thing was small. Only the owner's explicit choices change it: a
 *   presentation, or Tidy around Focus (which reserves a band for windows).
 *
 *   Docked     the area beside a SHELF: the docked sections, the column and
 *              the windows, live, each at a height for what it holds; the
 *              shelf scrolls, nothing is squeezed into a strip.
 *   Floating   the area is the main area; windows stay real windows over it.
 *   Mixed      a shelf for what is docked; windows stay windows.
 *   Only Focus the area is the whole Page; everything else is hidden until
 *              the one compact control reveals it. Narrow screens always.
 */

import type { Arr } from '../workspace/place'
import { removeLeaf, zones, type Node, type Zone } from '../workspace/tree'
import { columnEmpty, columnZone, locate, objectZone, primaryOf, RUN_SHOW, withFocus } from './model'
import { CONVERSATION_SHOW, MIN_FLOAT_H, type Float } from './types'
import type { FocusPresentation, FocusTarget, LensState } from './lens'

export type Rect = { x: number; y: number; w: number; h: number }
export type Room = { w: number; h: number }

/** the Focus bar's height, the gap round everything, the least a tile is */
export const LENS_BAR = 36
export const LENS_GAP = 12
export const MIN_TILE = 150

const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v))
export const shelfWidth = (w: number) => clamp(Math.round(w * 0.22), 280, 360)
export const bandWidth = (w: number) => clamp(Math.round(w * 0.24), 260, 340)

/* -- one lens session -------------------------------------------------------- */

/** Where the windows were when Focus was entered, back to front: Restore
 *  puts exactly these back. The docked tree is never touched by the lens. */
export interface Entry { floats: (Rect & { id: string })[] }

export interface Lens extends LensState {
  /** targets stepped back from, nearest first: › goes to them again */
  forward: FocusTarget[]
  /** the shelf's side, fixed for the session */
  shelfSide: 'left' | 'right'
  /** what could go on a shelf when Focus was entered, by presentation, the
   *  entry target left out: a shelf is drawn when one of these exists, so
   *  switching never adds or takes one away */
  shelfFor: Record<'docked' | 'mixed', boolean>
  /** Hide other windows (Floating, Mixed): reversible */
  hideOthers: boolean
  /** Tidy around Focus: each window's rect in the band, by float id; null: off */
  tidy: Record<string, Rect> | null
  /** the hidden secondaries revealed by the compact control */
  reveal: boolean
  entry: Entry
}

export const sameTarget = (a: FocusTarget | null | undefined, b: FocusTarget | null | undefined): boolean =>
  !!a && !!b && a.kind === b.kind && (a.kind === 'surface' ? a.id === (b as typeof a).id : a.address === (b as typeof a).address)

export const entryOf = (a: Arr): Entry => ({ floats: (a.focus?.floats ?? []).map(({ id, x, y, w, h }) => ({ id, x, y, w, h })) })

/** Is `t` still something the Page can show? An object always is. */
export const targetExists = (a: Arr, t: FocusTarget) => t.kind === 'object' || !!locate(a, t.id)

export function startLens(a: Arr, page: string, target: FocusTarget, presentation: FocusPresentation): Lens {
  const not = (id: string) => !(target.kind === 'surface' && target.id === id)
  const docked = [...(columnEmpty(a) ? [] : [columnZone(a).id]), ...zones(a.tree).map((z) => z.id)].filter(not)
  const floats = (a.focus?.floats ?? []).map((f) => f.zone.id).filter(not)
  return {
    page, target, presentation, history: [], forward: [],
    shelfSide: columnEmpty(a) ? 'right' : 'left',
    shelfFor: { docked: docked.length + floats.length > 0, mixed: docked.length > 0 },
    hideOthers: false, tidy: null, reveal: false,
    entry: entryOf(a),
  }
}

/** Focus on something else while Focus is on: the same area, new content. */
export function switchLens(L: Lens, target: FocusTarget): Lens {
  if (sameTarget(L.target, target)) return L
  return { ...L, target, history: [...L.history, L.target].slice(-30), forward: [], reveal: false }
}

/** Esc / ‹ : the previous target still on the Page; null when there is none. */
export function backLens(L: Lens, exists: (t: FocusTarget) => boolean): Lens | null {
  const history = [...L.history]
  while (history.length) {
    const t = history.pop()!
    if (exists(t) && !sameTarget(t, L.target)) return { ...L, target: t, history, forward: [L.target, ...L.forward], reveal: false }
  }
  return null
}

/** › : the target stepped back from, again. */
export function forwardLens(L: Lens, exists: (t: FocusTarget) => boolean): Lens | null {
  const forward = [...L.forward]
  while (forward.length) {
    const t = forward.shift()!
    if (exists(t) && !sameTarget(t, L.target)) return { ...L, target: t, history: [...L.history, L.target], forward, reveal: false }
  }
  return null
}

/* -- the composition --------------------------------------------------------- */

export interface Shape {
  presentation: FocusPresentation
  shelfSide: 'left' | 'right'
  shelfFor: Lens['shelfFor']
  narrow: boolean
  hideOthers: boolean
  tidy: boolean
}
export const shapeOf = (L: Lens, narrow: boolean): Shape =>
  ({ presentation: L.presentation, shelfSide: L.shelfSide, shelfFor: L.shelfFor, narrow, hideOthers: L.hideOthers, tidy: !!L.tidy })

export interface Composition {
  /** the presentation drawn: Only Focus on a narrow screen */
  presentation: FocusPresentation
  /** the Focus area: the bar and the stage below it */
  area: Rect
  bar: Rect
  stage: Rect
  shelf: Rect | null
  /** Tidy around Focus: where the windows are aligned */
  band: Rect | null
  /** the page's windows: real windows over the area, on the shelf, or hidden */
  floats: 'shown' | 'shelved' | 'hidden'
  /** the column and the docked sections: on the shelf, or hidden */
  docked: 'shelved' | 'hidden'
}

/** THE FOCUS AREA for `room` (the main area, px). Pure in the shape alone:
 *  no target goes in, so a switch can't change it. */
export function compose(room: Room, s: Shape): Composition {
  const p: FocusPresentation = s.narrow ? 'only' : s.presentation
  const g = s.narrow ? 0 : LENS_GAP
  const inner: Rect = { x: g, y: g, w: Math.max(0, room.w - 2 * g), h: Math.max(0, room.h - 2 * g) }
  let area = { ...inner }
  let shelf: Rect | null = null
  let band: Rect | null = null
  if ((p === 'docked' || p === 'mixed') && s.shelfFor[p]) {
    const w = shelfWidth(room.w)
    shelf = { x: s.shelfSide === 'left' ? inner.x : inner.x + inner.w - w, y: inner.y, w, h: inner.h }
    area = { ...area, w: Math.max(0, area.w - w - g), x: s.shelfSide === 'left' ? inner.x + w + g : inner.x }
  }
  if (s.tidy && (p === 'floating' || p === 'mixed')) {
    const w = bandWidth(room.w)
    const right = s.shelfSide === 'left'
    band = { x: right ? area.x + area.w - w : area.x, y: area.y, w, h: area.h }
    area = { ...area, w: Math.max(0, area.w - w - g), x: right ? area.x : area.x + w + g }
  }
  const bar = { x: area.x, y: area.y, w: area.w, h: LENS_BAR }
  const stage = { x: area.x, y: area.y + LENS_BAR, w: area.w, h: Math.max(0, area.h - LENS_BAR) }
  return {
    presentation: p, area, bar, stage, shelf, band,
    floats: p === 'docked' ? 'shelved' : p === 'only' || s.hideOthers ? 'hidden' : 'shown',
    docked: p === 'docked' || p === 'mixed' ? 'shelved' : 'hidden',
  }
}

/* -- what is beside it ------------------------------------------------------- */

export interface Surface {
  /** the content id (Zone.id) */
  id: string
  name: string
  place: 'column' | 'leaf' | 'float'
  zone: Zone
  float?: Float
  /** for its height: 'conversation', 'run', 'object', 'section' */
  kind: 'conversation' | 'run' | 'object' | 'section'
}
const kindOfZone = (z: Zone): Surface['kind'] =>
  z.show === CONVERSATION_SHOW ? 'conversation' : z.show === RUN_SHOW ? 'run' : z.show === 'object' ? 'object' : 'section'

/** Every surface on the Page: the column, the docked sections in tree
 *  order, then the windows front first. */
export function surfacesOf(a: Arr): Surface[] {
  const of = (zone: Zone, place: Surface['place'], float?: Float): Surface =>
    ({ id: zone.id, name: zone.name ?? (zone.show === CONVERSATION_SHOW ? 'Conversation' : 'Section'), place, zone, kind: kindOfZone(zone), ...(float ? { float } : {}) })
  return [
    ...(columnEmpty(a) ? [] : [of(columnZone(a), 'column')]),
    ...zones(a.tree).map((z) => of(z, 'leaf')),
    ...[...(a.focus?.floats ?? [])].reverse().map((f) => of(f.zone, 'float', f)),
  ]
}

const notTarget = (t: FocusTarget) => (s: Surface) => !(t.kind === 'surface' && t.id === s.id)

/** On the shelf, in order. */
export function shelfOf(a: Arr, t: FocusTarget, c: Composition): Surface[] {
  if (!c.shelf) return []
  return surfacesOf(a).filter(notTarget(t)).filter((s) => s.place === 'float' ? c.floats === 'shelved' : c.docked === 'shelved')
}

/** Hidden (neither shelved nor a window): what the compact control reveals. */
export function hiddenOf(a: Arr, t: FocusTarget, c: Composition): Surface[] {
  const shelved = new Set(shelfOf(a, t, c).map((s) => s.id))
  return surfacesOf(a).filter(notTarget(t)).filter((s) => !shelved.has(s.id) && (s.place === 'float' ? c.floats !== 'shown' : true))
}

/** A secondary's height on the shelf, for what it holds (the owner's
 *  correction in alt-b): the conversation tall enough to read and write in,
 *  a section a useful screenful, never under MIN_TILE, never squeezed. */
export function prefHeight(kind: string, roomH: number): number {
  const h = kind === 'conversation' ? clamp(Math.round(roomH * 0.52), 360, 520)
    : kind === 'run' ? 280
    : kind === 'section' ? 260
    : kind === 'chart' || kind === 'diagram' || kind === 'image' || kind === 'map' ? 300
    : kind === 'table' ? 240
    : kind === 'brain' ? 190
    : kind === 'post' ? 180
    : 230
  return Math.max(MIN_TILE, h)
}

/** Tidy around Focus: the windows aligned in the band, back to front, top
 *  down, each at the band's width. Too many to fit at their heights, they
 *  share it, but none goes under MIN_FLOAT_H; past that they overlap from
 *  the bottom rather than shrink further. */
export function tidyInBand(floats: readonly { id: string; h: number }[], band: Rect): Record<string, Rect> {
  const n = floats.length
  if (!n) return {}
  const g = LENS_GAP
  const natural = floats.reduce((s, f) => s + f.h, 0) + g * (n - 1)
  const even = Math.max(MIN_FLOAT_H, Math.floor((band.h - g * (n - 1)) / n))
  const out: Record<string, Rect> = {}
  let y = band.y
  for (const f of floats) {
    const h = natural <= band.h ? f.h : Math.min(f.h, even)
    out[f.id] = { x: band.x, y: Math.min(y, band.y + Math.max(0, band.h - h)), w: band.w, h }
    y += h + g
  }
  return out
}

/* -- the two ways out -------------------------------------------------------- */

/** RESTORE: the windows back exactly where they were, in their stacking
 *  order; one opened meanwhile stays, in front. What changed in content
 *  meanwhile (something kept, a feed chosen) is the owner's and stays.
 *  Unchanged, `a` itself. */
export function restoreArr(a: Arr, entry: Entry): Arr {
  const now = a.focus?.floats ?? []
  if (!now.length) return a
  const byId = new Map(now.map((f) => [f.id, f]))
  const was = entry.floats.filter((e) => byId.has(e.id)).map((e) => ({ ...byId.get(e.id)!, x: e.x, y: e.y, w: e.w, h: e.h }))
  const kept = new Set(was.map((f) => f.id))
  const floats = [...was, ...now.filter((f) => !kept.has(f.id))]
  const same = floats.every((f, i) => f === now[i] || (f.id === now[i].id && f.x === now[i].x && f.y === now[i].y && f.w === now[i].w && f.h === now[i].h))
  return same ? a : withFocus(a, { ...a.focus, floats })
}

/** KEEP THIS LAYOUT: the composition as one ordinary arrangement. The
 *  target becomes the main section (0.7 of the row, on the side away from
 *  the shelf) and Primary; in Docked the windows it shelved are docked
 *  beside the rest; tidied windows keep their tidy places. */
export function keepArr(a: Arr, L: Lens, c: Composition, title: string): Arr {
  let b = restoreArr(a, L.entry)
  const t = L.target
  const f = b.focus ?? {}
  let floats = [...(f.floats ?? [])]
  let column = f.column
  let rest: Node | null = b.tree
  let main: Zone
  if (t.kind === 'object') main = objectZone(t.address, title, undefined, t.from)
  else {
    const at = locate(b, t.id)
    if (!at) return a
    main = at.zone
    if (at.place === 'leaf') rest = zones(b.tree).length > 1 ? removeLeaf(b.tree, t.id) : null
    else if (at.place === 'float') floats = floats.filter((x) => x.id !== at.float.id)
    else column = undefined
  }
  if (c.floats === 'shelved') {
    const docking = floats.filter((x) => x.zone.show !== RUN_SHOW && !(t.kind === 'surface' && x.zone.id === t.id))
    floats = floats.filter((x) => !docking.includes(x))
    for (const [i, x] of [...docking].reverse().entries()) {
      const n = i + 1
      rest = rest ? { type: 'split', dir: 'col', sizes: [n / (n + 1), 1 / (n + 1)], kids: [rest, x.zone] } : x.zone
    }
  } else if (L.tidy) floats = floats.map((x) => (L.tidy![x.id] ? { ...x, ...L.tidy![x.id] } : x))
  const right = L.shelfSide === 'left'
  const tree: Node = !rest ? main
    : { type: 'split', dir: 'row', sizes: right ? [0.3, 0.7] : [0.7, 0.3], kids: right ? [rest, main] : [main, rest] }
  b = { ...b, tree }
  const was = primaryOf(a)
  return withFocus(b, {
    ...f, column, floats, primary: main.id,
    previous: was !== main.id ? [...(f.previous ?? []), was].slice(-20) : f.previous,
  })
}
