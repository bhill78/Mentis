/* WHAT FLOATS OVER THE 3D BRAIN: view state of this place, nothing more.
 *
 * Objects opened from the Brain, and a conversation opened over it, are Fluid
 * surfaces over the field (BrainPlace.tsx). Where they are is kept for this
 * tab only (sessionStorage), never in any conversation's arrangement: going
 * to the Brain and back changes nobody's saved layout, and nothing here
 * writes to the record. Closing a surface only stops drawing it.
 *
 * Browser-free apart from the storage it is handed, so it is testable. */

import { MAX_FLOATS, MIN_FLOAT_H, MIN_FLOAT_W } from '../focus/types'

export type Id = string

/** What a surface over the Brain shows. */
export type Shown =
  /** one durable thing, by its entry; its kind and Conversation as the Brain read them */
  | { type: 'entry'; entry: Id; kind: string; conversation: Id | null; title: string }
  /** a conversation, the real column (one at a time: it is drawn once) */
  | { type: 'conversation'; conversation: Id; title: string }

export type Dock = 'left' | 'right'

export interface Overlay {
  id: string
  shows: Shown
  /** px over the field, top-left */
  x: number
  y: number
  w: number
  h: number
  /** put away in the tray: still open, not drawn */
  min?: boolean
  /** a conversation docked as a column at this side of the field, not floating */
  dock?: Dock
}

/** back to front: the last is in front */
export type Overlays = Overlay[]

export const STORE_KEY = 'mentis:fluid:brain-overlays'
/** The one conversation over the Brain has one place; another replaces it. */
export const CONVERSATION_OVERLAY = 'conversation'
export const DOCK_W = 420

export const overlayId = (s: Shown) => (s.type === 'conversation' ? CONVERSATION_OVERLAY : 'entry:' + s.entry)

/** Open `shows` over the Brain, in a field `room` big: in front, and drawn.
 *  Already open, it is brought forward where it was; a conversation takes
 *  the conversation's one place, wherever that is. */
export function openOver(list: Overlays, shows: Shown, room: { w: number; h: number }, at?: { x: number; y: number }): Overlays {
  const id = overlayId(shows)
  const had = list.find((o) => o.id === id)
  if (had) return [...list.filter((o) => o.id !== id), { ...had, shows, min: false }]
  const n = list.filter((o) => !o.dock).length
  const conv = shows.type === 'conversation'
  const w = Math.max(MIN_FLOAT_W, Math.min(conv ? 440 : 380, Math.round(room.w * 0.42)))
  const h = Math.max(MIN_FLOAT_H, Math.min(conv ? 620 : 460, Math.round(room.h * (conv ? 0.82 : 0.62))))
  /* Opened at the right, stepping down and in, so the field's own title,
     options and chosen card stay clear and no two land on one another. */
  const step = (n % 6) * 28
  /* Let go at a point (dropped on the field), it opens there, inside it. */
  const x = Math.max(0, at ? Math.min(at.x - 30, room.w - w) : room.w - w - 24 - step)
  const y = Math.max(0, at ? Math.min(at.y - 16, room.h - h) : Math.min(room.h - h, 64 + step))
  const next = [...list, { id, shows, x, y, w, h }]
  /* No more than Focus allows: the one at the back that is not the
     conversation gives way. */
  if (next.length <= MAX_FLOATS) return next
  const drop = next.find((o) => o.id !== CONVERSATION_OVERLAY)
  return drop ? next.filter((o) => o !== drop) : next
}

export const closeOver = (list: Overlays, id: string): Overlays => list.filter((o) => o.id !== id)

export function toFront(list: Overlays, id: string): Overlays {
  const o = list.find((x) => x.id === id)
  if (!o || list[list.length - 1] === o) return list
  return [...list.filter((x) => x !== o), o]
}

/** Moved or sized; never smaller than a Focus float may be. */
export const placeOver = (list: Overlays, id: string, r: { x: number; y: number; w: number; h: number }): Overlays =>
  list.map((o) => (o.id === id ? { ...o, x: Math.round(r.x), y: Math.round(r.y), w: Math.round(Math.max(MIN_FLOAT_W, r.w)), h: Math.round(Math.max(MIN_FLOAT_H, r.h)) } : o))

export const minimise = (list: Overlays, id: string, min = true): Overlays => {
  const next = list.map((o) => (o.id === id ? { ...o, min } : o))
  return min ? next : toFront(next, id)
}

/** Dock a surface as a column at `side` of the field, or float it again. */
export const dockOver = (list: Overlays, id: string, dock: Dock | null): Overlays =>
  list.map((o) => {
    if (o.id !== id) return o
    const { dock: _was, ...rest } = o
    return dock ? { ...rest, dock, min: false } : rest
  })

/** Where a float is drawn in a field `room` big: kept reachable, its head on
 *  screen, however the window was resized since. The stored place is kept. */
export function shownRect(o: Overlay, room: { w: number; h: number }) {
  if (!room.w || !room.h) return { x: o.x, y: o.y, w: o.w, h: o.h }
  const w = Math.min(o.w, Math.max(MIN_FLOAT_W, room.w))
  const h = Math.min(o.h, Math.max(MIN_FLOAT_H, room.h))
  return { x: Math.max(0, Math.min(o.x, room.w - Math.min(w, 120))), y: Math.max(0, Math.min(o.y, room.h - 36)), w, h }
}

/* -- kept for this tab -------------------------------------------------------- */

const isShown = (s: any): s is Shown =>
  !!s && typeof s.title === 'string' && (
    (s.type === 'entry' && typeof s.entry === 'string' && typeof s.kind === 'string' && (s.conversation === null || typeof s.conversation === 'string'))
    || (s.type === 'conversation' && typeof s.conversation === 'string'))
const num = (v: unknown) => typeof v === 'number' && Number.isFinite(v)

/** What this tab had over the Brain. Anything unreadable is left out, never guessed. */
export function readOverlays(raw: string | null): Overlays {
  try {
    const got = JSON.parse(raw ?? '[]')
    if (!Array.isArray(got)) return []
    return got.filter((o: any) => o && typeof o.id === 'string' && isShown(o.shows) && o.id === overlayId(o.shows)
      && num(o.x) && num(o.y) && num(o.w) && num(o.h) && (o.dock === undefined || o.dock === 'left' || o.dock === 'right'))
      .slice(-MAX_FLOATS)
  } catch { return [] }
}

export function loadOverlays(storage: Pick<Storage, 'getItem'> | null): Overlays {
  try { return readOverlays(storage?.getItem(STORE_KEY) ?? null) } catch { return [] }
}

export function saveOverlays(storage: Pick<Storage, 'setItem' | 'removeItem'> | null, list: Overlays) {
  try {
    if (list.length) storage?.setItem(STORE_KEY, JSON.stringify(list))
    else storage?.removeItem(STORE_KEY)
  } catch { /* view state is a convenience, not a record */ }
}
