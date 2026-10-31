import { emptyZone, keepSlot, findZone, isEmptyZone, keepIn, removeLeaf, replaceZone, splitOuter, splitZone, swapLeaves, unkeep, zones, type Node, type Slot, type Split, type Zone } from '../workspace/tree'
import type { Arr } from '../workspace/place'
import { THIS_POST } from './page'
import {
  CONVERSATION_ID, CONVERSATION_SHOW, MAX_FLOATS, MIN_FLOAT_H, MIN_FLOAT_W,
  type Float, type FocusArr, type Located, type Minimized, type Origin, type Side, type Where,
} from './types'

export const conversationZone = (): Zone => ({ type: 'zone', id: CONVERSATION_ID, show: CONVERSATION_SHOW, name: 'Conversation' })
export const focusOf = (a: Arr): FocusArr => a.focus ?? {}
export const columnZone = (a: Arr): Zone => a.focus?.column ?? conversationZone()

const all = (a: Arr): Located[] => [
  ...(columnEmpty(a) ? [] : [{ place: 'column', zone: columnZone(a) } as Located]),
  ...zones(a.tree).map((zone): Located => ({ place: 'leaf', zone })),
  ...(a.focus?.floats ?? []).map((float): Located => ({ place: 'float', zone: float.zone, float })),
]
export const locate = (a: Arr, id: string): Located | null => all(a).find((x) => x.zone.id === id) ?? null
export const primaryOf = (a: Arr): string => {
  const wanted = a.focus?.primary ?? CONVERSATION_ID
  return locate(a, wanted) ? wanted : CONVERSATION_ID
}

/** Edit what a floating workspace zone keeps or how it looks. It is outside
 *  the page tree, so the ordinary tree update cannot reach it. */
export function updateFloatSlot(a: Arr, id: string, fn: (slot: Slot) => Slot): Arr {
  const fs = a.focus?.floats
  if (!fs?.some((f) => f.id === id && f.zone.slot)) return a
  return withFocus(a, { ...focusOf(a), floats: fs.map((f) => f.id === id ? { ...f, zone: { ...f.zone, slot: fn(f.zone.slot!) } } : f) })
}

/** `from`: the zone it was kept in, here (docked in another, it leaves that
 *  one); `says`: where it came from, said ("Tidewater survey · #12"). */
export function objectZone(address: string, title: string, from?: string, says?: string): Zone {
  const options = { ...(from ? { from } : {}), ...(says ? { says } : {}) }
  return { type: 'zone', id: `object-${fresh()}`, show: 'object', name: title, slot: keepSlot([address], 'focus'), ...(from || says ? { options } : {}) }
}

let serial = 0
const fresh = () => `${Date.now().toString(36)}-${(++serial).toString(36)}`
const tidy = (f: FocusArr): FocusArr => ({
  ...(f.primary && f.primary !== CONVERSATION_ID ? { primary: f.primary } : {}),
  ...(f.column && f.column.id !== CONVERSATION_ID ? { column: f.column } : {}),
  ...(f.floats?.length ? { floats: f.floats } : {}),
  ...(f.previous?.length ? { previous: f.previous.slice(-20) } : {}),
  ...(f.minimized ? { minimized: f.minimized } : {}),
})
/** `a` with focus `f`, tidied (empty parts dropped). */
export const withFocus = (a: Arr, f: FocusArr): Arr => {
  const focus = tidy(f)
  return Object.keys(focus).length ? { ...a, focus } : (({ focus: _drop, ...rest }) => rest)(a)
}
const replaceAt = (a: Arr, at: Located, zone: Zone): Arr => {
  if (at.place === 'leaf') return { ...a, tree: replaceZone(a.tree, at.zone.id, zone) }
  const f = focusOf(a)
  if (at.place === 'column') return withFocus(a, { ...f, column: zone })
  return withFocus(a, { ...f, floats: (f.floats ?? []).map((x) => x.id === at.float.id ? { ...x, zone } : x) })
}
const exchange = (a: Arr, x: Located, y: Located): Arr => {
  if (x.place === 'leaf' && y.place === 'leaf') return { ...a, tree: swapLeaves(a.tree, x.zone.id, y.zone.id) }
  const first = replaceAt(a, x, y.zone)
  return replaceAt(first, y, x.zone)
}

function makePrimaryInner(a: Arr, id: string, remember: boolean): Arr {
  const incoming = locate(a, id), current = locate(a, primaryOf(a))
  if (!incoming || !current || incoming === current || isEmptyZone(incoming.zone)) return a
  const old = current.zone.id
  let next = exchange(a, incoming, current)
  const f = focusOf(next)
  next = withFocus(next, { ...f, primary: id, ...(remember ? { previous: [...(f.previous ?? []), old].slice(-20) } : {}) })
  return next
}
export const makePrimary = (a: Arr, id: string): Arr => {
  const at = locate(a, id)
  return id === primaryOf(a) && at?.place === 'float' ? swapBack(a) : makePrimaryInner(a, id, true)
}

export function swapBack(a: Arr): Arr {
  const previous = [...(a.focus?.previous ?? [])]
  while (previous.length) {
    const id = previous.pop()!
    if (!locate(a, id) || id === primaryOf(a)) continue
    const next = makePrimaryInner(a, id, false)
    return withFocus(next, { ...focusOf(next), previous })
  }
  return a
}

function parentInfo(n: Node, id: string): { parent: Split; i: number } | null {
  if (n.type === 'zone') return null
  for (let i = 0; i < n.kids.length; i++) {
    const kid = n.kids[i]
    if (kid.type === 'zone' && kid.id === id) return { parent: n, i }
    const got = parentInfo(kid, id)
    if (got) return got
  }
  return null
}
const edgeZone = (n: Node, last = false): Zone => {
  const zs = zones(n)
  return zs[last ? zs.length - 1 : 0]
}

/** Float a docked section out of the tree, nothing split: the neighbour
 *  removeLeaf gives its share to (the one before it, else the one after) is
 *  its `origin`, so docking back takes that share from that neighbour alone.
 *  The only section of the page floats only when the caller says it may
 *  (`alone`, as `floatsAlone` decides): the page is then left empty (the
 *  empty leaf, tree.ts), whose place it docks back into. Otherwise the only
 *  section stays, as before. */
export function floatOut(a: Arr, id: string, rect: { x: number; y: number; w: number; h: number }, opts: { alone?: boolean } = {}): Arr {
  const hit = locate(a, id)
  if (!hit || hit.place !== 'leaf' || (a.focus?.floats?.length ?? 0) >= MAX_FLOATS) return a
  const f0 = focusOf(a)
  if (a.tree.type === 'zone') {
    if (!opts.alone) return a
    const home = emptyZone()
    const fl: Float = { id: `float-${fresh()}`, zone: hit.zone, ...rect, origin: { near: home.id, side: 'right' } }
    return withFocus({ ...a, tree: home }, { ...f0, floats: [...(f0.floats ?? []), fl] })
  }
  const pi = parentInfo(a.tree, id)
  if (!pi) return a
  const { parent, i } = pi
  const ni = i > 0 ? i - 1 : 1
  const near = edgeZone(parent.kids[ni], ni < i).id
  const side: Side = parent.dir === 'row' ? (i < ni ? 'left' : 'right') : (i < ni ? 'top' : 'bottom')
  const pair = parent.sizes[i] + parent.sizes[ni]
  const share = pair ? parent.sizes[ni] / pair : 0.5
  const fl: Float = { id: `float-${fresh()}`, zone: hit.zone, ...rect, origin: { near, side, share } }
  return withFocus({ ...a, tree: removeLeaf(a.tree, id) }, { ...f0, floats: [...(f0.floats ?? []), fl] })
}

/** Whether the only section of a page may float (Surface Tension §3.3,
 *  r3 §8 risk 2): a Contents section on This post of a conversation place.
 *  Every other page -- a place's own Pages, an unnamed place, Home -- keeps
 *  "a section floats only beside another". */
export const floatsAlone = (placeKind: string, page: string | null | undefined, z: Zone): boolean =>
  placeKind === 'conversation' && (page ?? THIS_POST) === THIS_POST && isContents(z)
/* Contents showing Media is the same Contents (sections/conversationViews.tsx
   registers both on ContentsView): its Float is not refused for the feed it
   was set to (owner, Turn #1458). */
const CONTENTS = new Set(['contents', 'media'])
const isContents = (z: Zone) => CONTENTS.has(z.show) || CONTENTS.has(z.slot?.feed?.source ?? '')

export function floatObject(a: Arr, address: string, title: string, rect: { x: number; y: number; w: number; h: number }, from?: string, says?: string): Arr {
  if ((a.focus?.floats?.length ?? 0) >= MAX_FLOATS) return a
  const f = focusOf(a)
  const fl: Float = { id: `float-${fresh()}`, zone: objectZone(address, title, from, says), ...clearOf(rect, f.floats ?? []) }
  return withFocus(a, { ...f, floats: [...(f.floats ?? []), fl] })
}

/** A new float asked for where another already sits (several kept from one
 *  card, or opened from the same corner) steps down and in until its title
 *  line is clear, so it never hides the one before it. */
export function clearOf<R extends { x: number; y: number }>(rect: R, floats: readonly { x: number; y: number }[]): R {
  let r = rect
  for (let i = 0; i < MAX_FLOATS && floats.some((o) => Math.abs(o.x - r.x) < 16 && Math.abs(o.y - r.y) < 16); i++)
    r = { ...r, x: Math.max(12, r.x - 28), y: r.y + 28 }
  return r
}

const isObject = (z: Zone) => z.show === 'object' && z.slot?.items.length === 1
/** A zone showing one object: its float travels with the owner. */
export const isObjectZone = isObject
const withoutFloat = (a: Arr, id: string): Arr => withFocus(a, { ...focusOf(a), floats: (a.focus?.floats ?? []).filter((f) => f.id !== id) })
/** An agent's live run in its own float (the run panel, runs/RunPanel.tsx):
 *  it keeps streaming there while the owner works. One float per run. */
export const RUN_SHOW = 'run'
export function floatRun(a: Arr, run: string, who: string, rect: { x: number; y: number; w: number; h: number }): Arr {
  const id = `run-${run}`.replace(/[^A-Za-z0-9_-]/g, '-').slice(0, 80)
  if (locate(a, id) || (a.focus?.floats?.length ?? 0) >= MAX_FLOATS) return a
  const f = focusOf(a)
  const zone: Zone = { type: 'zone', id, show: RUN_SHOW, name: who, options: { run, who } }
  return withFocus(a, { ...f, floats: [...(f.floats ?? []), { id: `float-${fresh()}`, zone, ...rect }] })
}

/* A REPLY THREAD IS A SURFACE LIKE THE OTHERS (owner feedback, round 2:
 * "replies ... don't feel part of the work surface so much as they open into
 * the available workspace area"). A thread is a zone showing one post's
 * thread -- its root, its replies and its own composer -- by the root's id
 * (`options.root`) and the conversation it is replied in (`options.conversation`).
 * Like any content it floats, docks, is made primary, is focused, pinned and
 * minimised; the zone body draws it wherever it is (Zones.tsx). `follow`
 * marks the one window that shows the replies of each post read (nav.ts
 * Follow). Nothing is copied: the root is a reference, as an object's
 * address is. */
export const THREAD_SHOW = 'thread'
export const isThreadZone = (z: Zone): boolean => z.show === THREAD_SHOW && typeof z.options?.root === 'string'
export const threadRootOf = (z: Zone): string | null => (isThreadZone(z) ? z.options!.root as string : null)
/** A thread's zone; `number` names it ("Thread #12") until its post is read. */
export function threadZone(root: string, conversation?: string | null, number?: number | null, follow = false): Zone {
  return { type: 'zone', id: `thread-${fresh()}`, show: THREAD_SHOW, name: number != null ? `Thread #${number}` : 'Thread',
    options: { root, ...(conversation ? { conversation } : {}), ...(follow ? { follow: true } : {}) } }
}
/** Every thread shown on this page, wherever it is: the column, a section, a
 *  window (back to front, so the last is the frontmost window). */
export const threadsOf = (a: Arr): Located[] => all(a).filter((x) => isThreadZone(x.zone))
/** The surface showing `root`'s thread on this page, if one does. */
export const threadOf = (a: Arr, root: string): Located | null => threadsOf(a).find((x) => threadRootOf(x.zone) === root) ?? null
/** The window that follows the post read (Follow), if one does. */
export const followerOf = (a: Arr): Located | null => threadsOf(a).find((x) => x.zone.options?.follow === true) ?? null

/** A thread in a new window at `rect`; unchanged when the page holds as
 *  many windows as it may (the caller falls back to the side sheet). */
export function floatThread(a: Arr, root: string, rect: Rect, conversation?: string | null, number?: number | null, follow = false): Arr {
  if ((a.focus?.floats?.length ?? 0) >= MAX_FLOATS) return a
  const base = follow ? markFollower(a, null) : a
  const f = focusOf(base)
  const zone = threadZone(root, conversation, number, follow)
  return withFocus(base, { ...f, floats: [...(f.floats ?? []), { id: `float-${fresh()}`, zone, ...rect }] })
}

/** Edit the zone `id` wherever it is on this page. */
export function editZone(a: Arr, id: string, fn: (z: Zone) => Zone): Arr {
  const at = locate(a, id)
  return at ? replaceAt(a, at, fn(at.zone)) : a
}
/* A THREAD'S OWN LOOK. A section keeps its look in its slot; a thread has no
   slot, so it keeps the same three values in its options, flat, as a saved
   arrangement keeps options (arrangements._options). Absent: the place's look. */
type Look = { panel: string; content: string; opacity: number }
export function lookOf(z: Zone): unknown {
  if (z.slot?.appearance) return z.slot.appearance
  const o = z.options
  return o && typeof o.panel === 'string' ? { panel: o.panel, content: o.content, opacity: o.opacity } : undefined
}
export function setThreadLook(a: Arr, id: string, look: Look | undefined): Arr {
  return editZone(a, id, (z) => {
    const { panel: _p, content: _c, opacity: _o, ...options } = z.options ?? {}
    return { ...z, options: look ? { ...options, panel: look.panel, content: look.content, opacity: look.opacity } : options }
  })
}
/** The thread `id` now shows `root` (Follow moves it to the post read). */
export function setThreadRoot(a: Arr, id: string, root: string, number?: number | null): Arr {
  const at = locate(a, id)
  if (!at || !isThreadZone(at.zone) || threadRootOf(at.zone) === root) return a
  return editZone(a, id, (z) => ({ ...z, name: number != null ? `Thread #${number}` : 'Thread', options: { ...z.options, root } }))
}
/** Make thread `id` the one that follows the post read -- null: none does. */
export function markFollower(a: Arr, id: string | null): Arr {
  let next = a
  for (const t of threadsOf(a)) {
    const on = t.zone.id === id
    if (!!t.zone.options?.follow === on) continue
    next = editZone(next, t.zone.id, (z) => {
      const { follow: _f, ...options } = z.options ?? {}
      return { ...z, options: on ? { ...options, follow: true } : options }
    })
  }
  return next
}

/** WHERE A THREAD WINDOW OPENS: beside the conversation (`conv`, its rectangle
 *  in the main area, when it is drawn), as tall as is useful, on the first
 *  run of the room that no other window covers; with none free, where it
 *  would have gone, stepped clear of a window already there (`clearOf`). It
 *  never takes a fixed share of the workspace. */
export function threadWindowRect(room: { w: number; h: number }, conv: Rect | null, floats: readonly Rect[] = []): Rect {
  const margin = 12, gap = 12
  const w = Math.max(MIN_FLOAT_W, Math.min(440, Math.round(room.w * 0.36)))
  const h = Math.max(MIN_FLOAT_H, Math.min(720, room.h - 2 * margin - 12))
  const y = margin + 12
  const last = Math.max(margin, room.w - w - margin)
  const start = conv && conv.w > 0 && conv.x + conv.w + gap + w <= room.w - margin ? conv.x + conv.w + gap : last
  const covers = (x: number) => floats.some((o) => x < o.x + o.w && x + w > o.x && y < o.y + o.h && y + h > o.y)
  for (let x = start; x <= last; x += Math.max(48, Math.round(w / 3))) if (!covers(x)) return { x, y, w, h }
  if (!covers(last)) return { x: last, y, w, h }
  return clearOf({ x: start, y, w, h }, floats)
}

/* A WINDOW MINIMISED (owner feedback, round 2: every window can be). It folds
 * to its title line where it is; its content stays drawn underneath, so its
 * scroll, its draft and its search survive. The conversation's own window
 * goes to the launcher instead (minimize, below). */
export const MIN_BAR = 38
export function setMinimized(a: Arr, floatId: string, on: boolean): Arr {
  const fs = a.focus?.floats ?? []
  const fl = fs.find((f) => f.id === floatId)
  if (!fl || !!fl.min === on) return a
  return withFocus(a, { ...focusOf(a), floats: fs.map((f) => {
    if (f !== fl) return f
    const { min: _m, ...rest } = f
    return on ? { ...rest, min: true } : rest
  }) })
}

/** Minimise or restore every ordinary window on this Page. Pinned windows
 * travel with the owner and are deliberately left exactly as they are. */
export function setAllMinimized(a: Arr, on: boolean): Arr {
  const fs = a.focus?.floats ?? []
  if (!fs.some((f) => !f.pinned && !!f.min !== on)) return a
  return withFocus(a, { ...focusOf(a), floats: fs.map((f) => {
    if (f.pinned || !!f.min === on) return f
    const { min: _m, ...rest } = f
    return on ? { ...rest, min: true } : rest
  }) })
}

/** Sections a new layout left without a place (the sketcher's `leftover`)
 *  float, cascading from the top left, so nothing is lost. */
export function floatZones(a: Arr, zs: Zone[], w = 360, h = 300): Arr {
  const f = focusOf(a)
  const room = Math.max(0, MAX_FLOATS - (f.floats?.length ?? 0))
  const fl: Float[] = zs.slice(0, room).map((zone, i) => ({ id: `float-${fresh()}`, zone, x: 40 + i * 28, y: 40 + i * 28, w, h }))
  return fl.length ? withFocus(a, { ...f, floats: [...(f.floats ?? []), ...fl] }) : a
}

export function dockFloat(a: Arr, floatId: string, target: string, where: Where, share = 0.5): Arr {
  const fl = a.focus?.floats?.find((f) => f.id === floatId)
  const to = locate(a, target)
  if (!fl || !to || to.place === 'float') return a
  /* onto an empty page, wherever it is asked: the window becomes its section */
  if (isEmptyZone(to.zone)) return to.place === 'leaf' ? withoutFloat({ ...a, tree: replaceZone(a.tree, to.zone.id, fl.zone) }, floatId) : a
  if (where === 'center') {
    if (isObject(fl.zone)) {
      if (to.zone.slot) {
        const address = fl.zone.slot!.items[0]
        let tree = a.tree
        let kept = a
        if (to.place === 'leaf') kept = { ...a, tree: keepIn(tree, to.zone.id, address) }
        else if (to.place === 'column') kept = replaceAt(a, to, { ...to.zone, slot: { ...to.zone.slot, items: [...new Set([...to.zone.slot.items, address])] } })
        else return a
        const from = typeof fl.zone.options?.from === 'string' ? fl.zone.options.from : undefined
        if (from && findZone(kept.tree, from)) kept = { ...kept, tree: unkeep(kept.tree, from, address) }
        return withoutFloat(kept, floatId)
      }
      return a
    }
    const exchanged = exchange(a, { place: 'float', zone: fl.zone, float: fl }, to)
    const f = focusOf(exchanged)
    return withFocus(exchanged, {
      ...f,
      primary: fl.zone.id,
      previous: [...(f.previous ?? []), to.zone.id].slice(-20),
    })
  }
  const finish = (next: Arr) => {
    const from = isObject(fl.zone) && typeof fl.zone.options?.from === 'string' ? fl.zone.options.from : undefined
    const moved = from && findZone(next.tree, from) ? { ...next, tree: unkeep(next.tree, from, fl.zone.slot!.items[0]) } : next
    return withoutFloat(moved, floatId)
  }
  if (to.place === 'column') return finish({ ...a, tree: splitOuter(a.tree, where, fl.zone, share) })
  if (to.place !== 'leaf') return a
  const dir = where === 'left' || where === 'right' ? 'row' : 'col'
  const before = where === 'left' || where === 'top'
  const tree = splitZone(a.tree, to.zone.id, dir, fl.zone, before, share).tree
  return finish({ ...a, tree })
}

export function dockBack(a: Arr, floatId: string): Arr {
  const fl = a.focus?.floats?.find((f) => f.id === floatId)
  if (!fl) return a
  let near = fl.origin?.near
  let side: Side = fl.origin?.side ?? 'right'
  if (!near || locate(a, near)?.place !== 'leaf') {
    const p = locate(a, primaryOf(a))
    near = p?.place === 'leaf' ? p.zone.id : zones(a.tree)[0]?.id
    side = 'right'
  }
  return near ? dockFloat(a, floatId, near, side, fl.origin?.share) : a
}

export function dockSection(a: Arr, id: string, target: string, where: Where): Arr {
  const from = locate(a, id), to = locate(a, target)
  if (!from || !to || from === to || from.place === 'float' || to.place === 'float' || isEmptyZone(to.zone)) return a
  if (where === 'center') {
    const exchanged = exchange(a, from, to)
    const f = focusOf(exchanged)
    return withFocus(exchanged, {
      ...f,
      primary: from.zone.id,
      previous: [...(f.previous ?? []), to.zone.id].slice(-20),
    })
  }
  if (from.place !== 'leaf') return a
  if (to.place === 'column') {
    if (zones(a.tree).length < 2) return a
    return { ...a, tree: splitOuter(removeLeaf(a.tree, id), where, from.zone) }
  }
  if (to.place !== 'leaf') return a
  const removed = removeLeaf(a.tree, id)
  if (!findZone(removed, target)) return a
  const dir = where === 'left' || where === 'right' ? 'row' : 'col'
  return { ...a, tree: splitZone(removed, target, dir, from.zone, where === 'left' || where === 'top').tree }
}

export const moveFloat = (a: Arr, floatId: string, rect: { x: number; y: number; w: number; h: number }): Arr => {
  if (!a.focus?.floats?.some((f) => f.id === floatId)) return a
  return withFocus(a, { ...a.focus, floats: a.focus.floats.map((f) => f.id === floatId ? { ...f, ...rect } : f) })
}
export const closeFloat = (a: Arr, floatId: string): Arr => a.focus?.floats?.some((f) => f.id === floatId) ? withoutFloat(a, floatId) : a
export const toFront = (a: Arr, floatId: string): Arr => {
  const fs = a.focus?.floats ?? [], f = fs.find((x) => x.id === floatId)
  return !f || fs[fs.length - 1] === f ? a : withFocus(a, { ...focusOf(a), floats: [...fs.filter((x) => x !== f), f] })
}
export function clampFloats(a: Arr, w: number, h: number): Arr {
  const fs = a.focus?.floats
  if (!fs?.length) return a
  const floats = fs.map((f) => {
    const fw = Math.max(MIN_FLOAT_W, Math.min(f.w, Math.max(MIN_FLOAT_W, w)))
    const fh = Math.max(MIN_FLOAT_H, Math.min(f.h, Math.max(MIN_FLOAT_H, h)))
    return { ...f, w: fw, h: fh, x: Math.max(-fw + 80, Math.min(f.x, w - 80)), y: Math.max(0, Math.min(f.y, h - 36)) }
  })
  return floats.every((f, i) => f.x === fs[i].x && f.y === fs[i].y && f.w === fs[i].w && f.h === fs[i].h) ? a : withFocus(a, { ...focusOf(a), floats })
}

/** A saved float as it can be drawn in the room now. Its saved rectangle is
 *  untouched; at least 44 px of its header remains reachable on each axis. */
export function drawnFloatRect(f: Float, w: number, h: number): { x: number; y: number; w: number; h: number } {
  const visible = 44
  const roomW = Math.max(0, Number.isFinite(w) ? w : 0)
  const roomH = Math.max(0, Number.isFinite(h) ? h : 0)
  /* Placed on a larger screen, a float that fits is drawn wholly inside the
     right and bottom edges (a tablet showing a desktop arrangement), not just
     its header; one larger than the room keeps its header in reach. */
  const right = f.w <= roomW ? roomW - f.w : roomW - visible
  const bottom = f.h <= roomH ? roomH - f.h : Math.max(0, roomH - visible)
  return {
    x: Math.max(-f.w + visible, Math.min(f.x, right)),
    y: Math.max(0, Math.min(f.y, bottom)),
    w: f.w,
    h: f.h,
  }
}

/** Align floating places at the right of the main area, back to front.
 *  Their sizes, content and z-order are untouched; a full column wraps left. */
export function tidyFloats(a: Arr, w: number, h: number): Arr {
  const fs = a.focus?.floats
  if (!fs?.length) return a
  const gap = 12, margin = 12
  const rightEdge = Math.max(0, Number.isFinite(w) ? w : 0) - margin
  const bottom = Math.max(margin, (Number.isFinite(h) ? h : 0) - margin)
  let right = rightEdge, y = margin, columnWidth = 0
  const floats = fs.map((f) => {
    if (y > margin && y + f.h > bottom) {
      right -= columnWidth + gap
      y = margin
      columnWidth = 0
    }
    const placed = { ...f, x: Math.max(0, right - f.w), y }
    y += f.h + gap
    columnWidth = Math.max(columnWidth, f.w)
    return placed
  })
  return floats.every((f, i) => f.x === fs[i].x && f.y === fs[i].y) ? a : withFocus(a, { ...focusOf(a), floats })
}

/* A PINNED WINDOW GOES WITH THE OWNER (owner feedback: "a 'pin' on the
 * floating window to allow it to stay between conversations"). Every float
 * once travelled when it showed one object, and the screen filled up; now a
 * window travels only when the owner pins it (`Float.pinned`). Pinned, it is
 * the owner's, not the place's: over whichever Page is shown (travel.ts
 * gatherTravel) and whichever conversation is opened (place.ts Holder
 * `carry`), at the same rectangle, kept in this tab and never in a place's
 * saved layout. Unpinned, it stays on the Page and in the conversation it was
 * made in. A window showing one object, a post or a section can be pinned;
 * the conversation's own float and a run's stay with their place.
 * Holder.enter takes the pinned floats out of the place left and puts them
 * into the place arrived at, so each is in exactly one place: the one shown.
 * What it shows and where it came from (`says`) go with it; the zone it was
 * kept in there (`from`) and where it docks back (`origin`) name sections of
 * the place left, so they do not. */
export const objectFloatsOf = (a: Arr): Float[] => (a.focus?.floats ?? []).filter((f) => isObject(f.zone))
/** Can this window be pinned (and so travel)? Not the conversation's, not a run's. */
export const canPin = (z: Zone): boolean => z.show !== CONVERSATION_SHOW && z.show !== RUN_SHOW
const isPinned = (f: Float): boolean => !!f.pinned && canPin(f.zone)
export const pinnedFloatsOf = (a: Arr): Float[] => (a.focus?.floats ?? []).filter(isPinned)
/** What a travelling window shows, so it is never carried in twice: its
 *  object's address, else its section. */
export const travelKey = (f: Float): string => (isObject(f.zone) ? 'a:' + f.zone.slot!.items[0] : isThreadZone(f.zone) ? 't:' + threadRootOf(f.zone) : 'z:' + f.zone.id)
/** A window of content (one object, or a thread), not of the place's shape:
 *  a layout neither keeps it nor moves it, and it stays where it was made. */
export const isContentZone = (z: Zone): boolean => isObject(z) || isThreadZone(z)
/** Pin or unpin a window: one change of the Page, undone like any other. */
export function setPinned(a: Arr, floatId: string, on: boolean): Arr {
  const fs = a.focus?.floats ?? []
  const fl = fs.find((f) => f.id === floatId)
  if (!fl || !canPin(fl.zone) || !!fl.pinned === on) return a
  return withFocus(a, { ...focusOf(a), floats: fs.map((f) => {
    if (f !== fl) return f
    const { pinned: _p, ...rest } = f
    return on ? { ...rest, pinned: true } : rest
  }) })
}
/** The place as left: its pinned floats gone with the owner. */
export function leavePinnedFloats(a: Arr): Arr {
  const fs = a.focus?.floats ?? []
  return fs.some(isPinned) ? withFocus(a, { ...focusOf(a), floats: fs.filter((f) => !isPinned(f)) }) : a
}
/** The place arrived at, with the pinned floats of `left` over it, in front,
 *  back-to-front order kept -- not twice what it already has pinned, and never
 *  past MAX_FLOATS. */
export function carryPinnedFloats(a: Arr, left: Arr): Arr {
  const carried = pinnedFloatsOf(left)
  if (!carried.length) return a
  const f = focusOf(a)
  const ids = new Set([...all(a).map((x) => x.zone.id), ...(f.floats ?? []).map((x) => x.id)])
  const shown = new Set(pinnedFloatsOf(a).map(travelKey))
  const room = Math.max(0, MAX_FLOATS - (f.floats?.length ?? 0))
  const add = carried.filter((x) => !ids.has(x.id) && !ids.has(x.zone.id) && !shown.has(travelKey(x))).slice(0, room)
    .map(({ origin: _o, ...x }): Float => {
      if (!isObject(x.zone)) return x
      const { from: _f, ...options } = x.zone.options ?? {}
      const { options: _drop, ...zone } = x.zone
      return { ...x, zone: Object.keys(options).length ? { ...zone, options } : zone }
    })
  return add.length ? withFocus(a, { ...f, floats: [...(f.floats ?? []), ...add] }) : a
}

/* THE CONVERSATION, MINIMIZED (types.ts `Minimized`). Put away to the
 * launcher (Launcher.tsx), it leaves its place -- the column, a leaf or a
 * float -- so the page's sections or canvas take the room, and the page keeps
 * where it was so it goes back there. Nothing else on the page moves either
 * way. Kept in the page's focus, so each page has its own, it is saved and
 * undone like any other placement, and nothing here writes to the record. */

type Rect = { x: number; y: number; w: number; h: number }
export const minimizedOf = (a: Arr): Minimized | null => a.focus?.minimized ?? null
const isConversation = (z: Zone) => z.show === CONVERSATION_SHOW

/** The column's place holds nothing: it would show the conversation (nothing
 *  else was put there), but the conversation is minimized, or is in a leaf or
 *  a float instead. It is drawn at no width, and is no place to swap with. */
export function columnEmpty(a: Arr): boolean {
  const c = a.focus?.column
  if (c && !isConversation(c)) return false
  return !!a.focus?.minimized || zones(a.tree).some(isConversation) || !!a.focus?.floats?.some((f) => isConversation(f.zone))
}

/** columnEmpty on this device: also when what the column holds instead of
 *  the conversation is closed here (P5 Close), so the page takes its room. */
export function columnEmptyHere(a: Arr, closed: ReadonlySet<string>): boolean {
  const c = a.focus?.column
  if (c && !isConversation(c) && closed.has(c.id)) return columnEmpty({ ...a, focus: { ...a.focus, column: undefined } })
  return columnEmpty(a)
}

/** Minimize the conversation on this page, at `at` (epoch ms). */
export function minimize(a: Arr, at: number): Arr {
  if (a.focus?.minimized) return a
  const where = locate(a, CONVERSATION_ID)
  if (!where) return a
  const f = focusOf(a)
  if (where.place === 'column') return withFocus(a, { ...f, minimized: { from: 'column', at } })
  if (where.place === 'float') {
    const { x, y, w, h } = where.float
    return withFocus(a, { ...f, floats: (f.floats ?? []).filter((x) => x !== where.float), minimized: { from: 'float', rect: { x, y, w, h }, at } })
  }
  /* Its leaf's share goes to the neighbour removeLeaf gives it to (the one
     before it, else the one after); which, on which side and at what share
     are kept, so restoring takes back that share from that neighbour alone.
     The only section of the page leaves it empty. */
  const pi = parentInfo(a.tree, where.zone.id)
  if (!pi) return withFocus({ ...a, tree: emptyZone() }, { ...f, minimized: { from: 'leaf', at } })
  const { parent, i } = pi
  const ni = i > 0 ? i - 1 : 1
  const side: Side = parent.dir === 'row' ? (i < ni ? 'left' : 'right') : (i < ni ? 'top' : 'bottom')
  const pair = parent.sizes[i] + parent.sizes[ni]
  const near: Origin = { near: edgeZone(parent.kids[ni], ni < i).id, side, share: pair ? parent.sizes[ni] / pair : 0.5 }
  return withFocus({ ...a, tree: removeLeaf(a.tree, where.zone.id) }, { ...f, minimized: { from: 'leaf', near, at } })
}

/** Where the conversation goes back to from the launcher. */
export type RestoreAs = Minimized['from']

/** A float's rectangle for the conversation in a main area `room` big: at its
 *  right, as tall as is useful, clear of the top. */
export function conversationFloatRect(room: { w: number; h: number }): Rect {
  const w = Math.max(MIN_FLOAT_W, Math.min(440, Math.round(room.w * 0.42)))
  const h = Math.max(MIN_FLOAT_H, Math.min(640, Math.round(room.h * 0.85)))
  return { x: Math.max(0, room.w - w - 24), y: Math.max(0, Math.min(24, room.h - h)), w, h }
}

/** Restore the minimized conversation: where it was (`as` absent), or as a
 *  float, the column, or a section beside the page's primary. */
export function restore(a: Arr, as?: RestoreAs, room: { w: number; h: number } = { w: 1200, h: 800 }): Arr {
  const m = a.focus?.minimized
  if (!m) return a
  const to = as ?? m.from
  const { minimized: _m, ...f } = focusOf(a)
  const conv = conversationZone()
  if (to === 'float') {
    const rect = as === undefined || m.from === 'float' ? m.rect ?? conversationFloatRect(room) : conversationFloatRect(room)
    return withFocus(a, { ...f, floats: [...(f.floats ?? []), { id: `float-${fresh()}`, zone: conv, ...rect }] })
  }
  if (to === 'column') {
    /* Something was swapped into the column while the conversation was in a
       section or a float: it floats now, never lost, and nothing else moves. */
    const held = f.column && !isConversation(f.column) ? f.column : null
    const floats = held ? [...(f.floats ?? []), { id: `float-${fresh()}`, zone: held, ...cascade(f.floats ?? [], room) }] : f.floats
    return withFocus(a, { ...f, column: undefined, floats })
  }
  /* A section: beside the neighbour it left, on its side and at its share;
     else beside the primary section (or the first), at its right. */
  const ids = new Set(zones(a.tree).map((z) => z.id))
  let near: Origin | undefined = m.near && ids.has(m.near.near) && as === undefined ? m.near : undefined
  if (!near) {
    const p = locate(a, primaryOf(a))
    near = { near: p?.place === 'leaf' ? p.zone.id : zones(a.tree)[0].id, side: 'right' }
  }
  const dir = near.side === 'left' || near.side === 'right' ? 'row' : 'col'
  const before = near.side === 'left' || near.side === 'top'
  const tree = splitZone(a.tree, near.near, dir, conv, before, near.share ?? 0.5).tree
  return withFocus({ ...a, tree }, f)
}
const cascade = (fs: Float[], room: { w: number; h: number }): Rect => {
  const n = fs.length % 6, w = Math.min(360, Math.max(MIN_FLOAT_W, room.w - 80)), h = Math.min(300, Math.max(MIN_FLOAT_H, room.h - 80))
  return { x: 40 + n * 28, y: 40 + n * 28, w, h }
}

/** How many of `posts` came after `since` (epoch ms; a post's `at` is in
 *  seconds): the launcher's unread count. A deleted post is not news. */
export const unreadSince = (posts: readonly { at: number; deleted?: unknown }[], since: number): number =>
  posts.filter((p) => !p.deleted && p.at * 1000 > since).length

/** `focus.minimized` as a saved layout gives it, or undefined when it is not
 *  readable or the layout puts the conversation in a leaf or a float anyway
 *  (`tree`, `floats`: what the same layout reads them as). */
export function readMinimized(v: unknown, tree: Node, floats: readonly Float[] = []): Minimized | undefined {
  const o = v as Record<string, unknown> | null
  if (!o || typeof o !== 'object' || !['column', 'leaf', 'float'].includes(o.from as string)) return undefined
  if (typeof o.at !== 'number' || !Number.isFinite(o.at) || o.at < 0) return undefined
  if (zones(tree).some(isConversation) || floats.some((f) => isConversation(f.zone))) return undefined
  const r = o.rect as Record<string, unknown> | undefined
  const rect = r && typeof r === 'object' && ['x', 'y', 'w', 'h'].every((k) => typeof r[k] === 'number' && Number.isFinite(r[k] as number) && Math.abs(r[k] as number) <= 100000)
    && (r.w as number) >= 1 && (r.h as number) >= 1 ? { x: r.x as number, y: r.y as number, w: r.w as number, h: r.h as number } : undefined
  const n = o.near as Record<string, unknown> | undefined
  const near = n && typeof n === 'object' && typeof n.near === 'string' && ['left', 'right', 'top', 'bottom'].includes(n.side as string)
    ? { near: n.near, side: n.side as Side, ...(typeof n.share === 'number' && n.share >= 0 && n.share <= 1 ? { share: n.share } : {}) } : undefined
  return { from: o.from as Minimized['from'], ...(rect ? { rect } : {}), ...(near ? { near } : {}), at: o.at }
}
