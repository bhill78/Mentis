import { keepSlot, findZone, keepIn, removeLeaf, replaceZone, splitZone, swapLeaves, unkeep, zones, type Node, type Split, type Zone } from '../workspace/tree'
import type { Arr } from '../workspace/place'
import {
  CONVERSATION_ID, CONVERSATION_SHOW, MAX_FLOATS, MIN_FLOAT_H, MIN_FLOAT_W,
  type Float, type FocusArr, type Located, type Side, type Where,
} from './types'

export const conversationZone = (): Zone => ({ type: 'zone', id: CONVERSATION_ID, show: CONVERSATION_SHOW, name: 'Conversation' })
export const focusOf = (a: Arr): FocusArr => a.focus ?? {}
export const columnZone = (a: Arr): Zone => a.focus?.column ?? conversationZone()

const all = (a: Arr): Located[] => [
  { place: 'column', zone: columnZone(a) },
  ...zones(a.tree).map((zone): Located => ({ place: 'leaf', zone })),
  ...(a.focus?.floats ?? []).map((float): Located => ({ place: 'float', zone: float.zone, float })),
]
export const locate = (a: Arr, id: string): Located | null => all(a).find((x) => x.zone.id === id) ?? null
export const primaryOf = (a: Arr): string => {
  const wanted = a.focus?.primary ?? CONVERSATION_ID
  return locate(a, wanted) ? wanted : CONVERSATION_ID
}

export function objectZone(address: string, title: string, from?: string): Zone {
  return { type: 'zone', id: `object-${fresh()}`, show: 'object', name: title, slot: keepSlot([address], 'focus'), ...(from ? { options: { from } } : {}) }
}

let serial = 0
const fresh = () => `${Date.now().toString(36)}-${(++serial).toString(36)}`
const tidy = (f: FocusArr): FocusArr => ({
  ...(f.primary && f.primary !== CONVERSATION_ID ? { primary: f.primary } : {}),
  ...(f.column && f.column.id !== CONVERSATION_ID ? { column: f.column } : {}),
  ...(f.floats?.length ? { floats: f.floats } : {}),
  ...(f.previous?.length ? { previous: f.previous.slice(-20) } : {}),
})
const withFocus = (a: Arr, f: FocusArr): Arr => {
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
  if (!incoming || !current || incoming === current) return a
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

export function floatOut(a: Arr, id: string, rect: { x: number; y: number; w: number; h: number }): Arr {
  const hit = locate(a, id)
  if (!hit || hit.place !== 'leaf' || zones(a.tree).length < 2 || (a.focus?.floats?.length ?? 0) >= MAX_FLOATS) return a
  const pi = parentInfo(a.tree, id)
  if (!pi) return a
  const { parent, i } = pi
  const ni = i + 1 < parent.kids.length ? i + 1 : i - 1
  const near = edgeZone(parent.kids[ni], ni < i).id
  const side: Side = parent.dir === 'row' ? (i < ni ? 'left' : 'right') : (i < ni ? 'top' : 'bottom')
  const pair = parent.sizes[i] + parent.sizes[ni]
  const share = pair ? parent.sizes[ni] / pair : 0.5
  const fl: Float = { id: `float-${fresh()}`, zone: hit.zone, ...rect, origin: { near, side, share } }
  const tree = removeLeaf(a.tree, id)
  const f = focusOf(a)
  const next = withFocus({ ...a, tree }, { ...f, floats: [...(f.floats ?? []), fl] })
  return next
}

export function floatObject(a: Arr, address: string, title: string, rect: { x: number; y: number; w: number; h: number }, from?: string): Arr {
  if ((a.focus?.floats?.length ?? 0) >= MAX_FLOATS) return a
  const f = focusOf(a)
  const fl: Float = { id: `float-${fresh()}`, zone: objectZone(address, title, from), ...rect }
  return withFocus(a, { ...f, floats: [...(f.floats ?? []), fl] })
}

const isObject = (z: Zone) => z.show === 'object' && z.slot?.items.length === 1
const withoutFloat = (a: Arr, id: string): Arr => withFocus(a, { ...focusOf(a), floats: (a.focus?.floats ?? []).filter((f) => f.id !== id) })
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
  if (where === 'center') {
    if (isObject(fl.zone) && to.zone.slot) {
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
    return exchange(a, { place: 'float', zone: fl.zone, float: fl }, to)
  }
  if (to.place !== 'leaf') return a
  const dir = where === 'left' || where === 'right' ? 'row' : 'col'
  const before = where === 'left' || where === 'top'
  const tree = splitZone(a.tree, to.zone.id, dir, fl.zone, before, share).tree
  return withoutFloat({ ...a, tree }, floatId)
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
  if (!from || !to || from === to || from.place === 'float' || to.place === 'float') return a
  if (where === 'center') return exchange(a, from, to)
  if (from.place !== 'leaf' || to.place !== 'leaf') return a
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
