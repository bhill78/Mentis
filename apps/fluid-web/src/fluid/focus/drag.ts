import { store } from '../store'
import { titleOf } from '../workspace/hooks'
import { workspace } from '../workspace/place'
import { dockFloat, dockSection, floatObject, floatOut, moveFloat } from './model'
import { DRAG } from '../workspace/keep'
import type { Dragged, Where } from './types'

export interface Pad { where: Where; x: number; y: number; ok: boolean; why?: string }
export interface DragView {
  payload: Dragged; x: number; y: number; x0: number; y0: number; started: boolean
  label: string; origin?: DOMRect; target?: { id: string; where: Where; rect: DOMRect }
}
let view: DragView | null = null
let startArr = workspace.arr
let floatRect: { x: number; y: number; w: number; h: number } | null = null
const listeners = new Set<() => void>()
const emit = () => listeners.forEach((f) => f())
const inMain = (x: number, y: number) => {
  const r = document.querySelector<HTMLElement>('.fx-main')?.getBoundingClientRect()
  return { x: x - (r?.left ?? 0), y: y - (r?.top ?? 0) }
}
export const subscribeDrag = (f: () => void) => { listeners.add(f); return () => listeners.delete(f) }
export const dragSnapshot = () => view
export const setDragTarget = (target?: DragView['target']) => { if (view) view = { ...view, target } }
export function pulseArrived(contentId: string, floatId?: string) {
  requestAnimationFrame(() => {
    const els = [document.querySelector<HTMLElement>(`.wt-cell[data-zone-id="${CSS.escape(contentId)}"]`),
      ...(floatId ? [document.querySelector<HTMLElement>(`.wk-float[data-float-id="${CSS.escape(floatId)}"]`)] : [])].filter((x): x is HTMLElement => !!x)
    for (const el of els) { el.classList.remove('arrived'); void el.offsetWidth; el.classList.add('arrived') }
  })
}

/** Mirror native object drags into the same compass/ghost layer. Browsers do
 *  not expose the payload until drop, so the live view intentionally carries
 *  only its kind; the drop handler reads the address. */
export function nativeObjectDrag(e: DragEvent) {
  if (!e.dataTransfer?.types.includes(DRAG)) return
  const source = document.querySelector<HTMLElement>('[data-address][draggable=true]:hover')
  const origin = source?.getBoundingClientRect()
  view = { payload: { type: 'object', address: '', from: source?.closest<HTMLElement>('[data-zone-id]')?.dataset.zoneId },
    x: e.clientX, y: e.clientY, x0: e.clientX, y0: e.clientY, started: true, label: 'Object', ...(origin ? { origin } : {}) }
  emit()
}
export function endNativeObjectDrag() { if (view?.payload.type === 'object') { view = null; emit() } }

export function floatNativeObject(e: DragEvent): boolean {
  if (!e.dataTransfer?.types.includes(DRAG)) return false
  let item: { address?: string; zone?: string } | null = null
  try { item = JSON.parse(e.dataTransfer.getData(DRAG) || 'null') } catch { return false }
  if (!item?.address) return false
  const st = store.objects.get(item.address)
  const title = st && 'object' in st ? titleOf(st.object) : 'Object'
  const p = inMain(e.clientX, e.clientY)
  workspace.edit((a) => floatObject(a, item!.address!, title, { x: p.x - 30, y: p.y - 16, w: 320, h: 220 }, item!.zone),
    `${title} floats. Drag it onto a section to dock or keep it.`)
  e.preventDefault()
  return true
}

export function dockNativeObject(e: DragEvent, target: string): boolean {
  if (!e.dataTransfer?.types.includes(DRAG)) return false
  let item: { address?: string; zone?: string } | null = null
  try { item = JSON.parse(e.dataTransfer.getData(DRAG) || 'null') } catch { return false }
  if (!item?.address) return false
  const st = store.objects.get(item.address)
  const title = st && 'object' in st ? titleOf(st.object) : 'Object'
  workspace.edit((a) => {
    const p = inMain(e.clientX, e.clientY)
    const floated = floatObject(a, item!.address!, title, { x: p.x, y: p.y, w: 320, h: 220 }, item!.zone)
    const f = floated.focus?.floats?.at(-1)
    return f ? dockFloat(floated, f.id, target, 'center') : a
  }, `Kept in ${locateName(target)}.`)
  e.preventDefault()
  return true
}
const locateName = (id: string) => {
  const l = workspace.arr.focus?.column?.id === id ? workspace.arr.focus.column : undefined
  return l?.name ?? 'the zone'
}

export function padsFor(r: { x: number; y: number; w: number; h: number }, column = false): Pad[] {
  const cx = r.x + r.w / 2, cy = r.y + r.h / 2, off = 46
  if (column) return [{ where: 'center', x: cx, y: cy, ok: true }]
  const row = r.w >= 492, col = r.h >= 292
  return [
    { where: 'center', x: cx, y: cy, ok: true },
    { where: 'left', x: cx - off, y: cy, ok: row, why: 'Too narrow to split' },
    { where: 'right', x: cx + off, y: cy, ok: row, why: 'Too narrow to split' },
    { where: 'top', x: cx, y: cy - off, ok: col, why: 'Too short to split' },
    { where: 'bottom', x: cx, y: cy + off, ok: col, why: 'Too short to split' },
  ]
}

export function beginDrag(payload: Dragged, e: React.PointerEvent | PointerEvent, origin: HTMLElement, label: string) {
  if (e.button !== 0) return
  e.preventDefault()
  startArr = workspace.arr
  const f = payload.type === 'float' ? workspace.arr.focus?.floats?.find((x) => x.id === payload.id) : undefined
  floatRect = f ? { x: f.x, y: f.y, w: f.w, h: f.h } : null
  view = { payload, x: e.clientX, y: e.clientY, x0: e.clientX, y0: e.clientY, started: false, label, origin: origin.getBoundingClientRect() }
  const move = (m: PointerEvent) => {
    if (!view) return
    const started = view.started || Math.hypot(m.clientX - view.x0, m.clientY - view.y0) >= 6
    view = { ...view, x: m.clientX, y: m.clientY, started }
    if (started && view.payload.type === 'float' && floatRect) {
      workspace.live(moveFloat(workspace.arr, view.payload.id, { ...floatRect, x: floatRect.x + m.clientX - view.x0, y: floatRect.y + m.clientY - view.y0 }))
    }
    emit()
  }
  const finish = (up: PointerEvent, cancel = false) => {
    const d = view
    window.removeEventListener('pointermove', move)
    window.removeEventListener('pointerup', done)
    window.removeEventListener('pointercancel', cancelled)
    view = null; emit()
    if (!d?.started) return
    if (cancel) { workspace.live(startArr); return }
    const t = d.target
    if (d.payload.type === 'float') {
      const next = t ? dockFloat(workspace.arr, d.payload.id, t.id, t.where) : workspace.arr
      workspace.live(next, { from: startArr })
      return
    }
    if (d.payload.type === 'section') {
      const p = inMain(up.clientX, up.clientY)
      const next = t ? dockSection(workspace.arr, d.payload.id, t.id, t.where) : floatOut(workspace.arr, d.payload.id, {
        x: p.x - 30, y: p.y - 16, w: Math.max(260, d.origin?.width ?? 320), h: Math.max(180, d.origin?.height ?? 220),
      })
      workspace.edit(() => next, t ? (t.where === 'center' ? `${d.label} and its target traded places.` : `Docked ${d.label} ${t.where} of its target.`) : `${d.label} floats; the sections beside it took its room. “Dock back” returns it.`)
    }
  }
  const done = (up: PointerEvent) => finish(up)
  const cancelled = (up: PointerEvent) => finish(up, true)
  window.addEventListener('pointermove', move)
  window.addEventListener('pointerup', done)
  window.addEventListener('pointercancel', cancelled)
}

/** Native object drop outside a centre pad: edge makes a new leaf, elsewhere a float. */
export function handleObjectDrop(e: React.DragEvent, targetId: string): boolean {
  let item: { address?: string; zone?: string } | null = null
  try { item = JSON.parse(e.dataTransfer.getData(DRAG) || 'null') } catch { return false }
  if (!item?.address) return false
  const cell = (e.currentTarget as HTMLElement).closest('.wt-cell') as HTMLElement | null
  const r = cell?.getBoundingClientRect()
  const pads = r ? padsFor({ x: r.left, y: r.top, w: r.width, h: r.height }) : []
  const hot = pads.find((p) => Math.abs(e.clientX - p.x) <= 21 && Math.abs(e.clientY - p.y) <= 21)
  if (hot?.where === 'center') return false
  e.preventDefault()
  const st = store.objects.get(item.address)
  const title = st && 'object' in st ? titleOf(st.object) : 'Object'
  workspace.edit((a) => {
    const p = inMain(e.clientX, e.clientY)
    const floated = floatObject(a, item!.address!, title, { x: p.x - 30, y: p.y - 16, w: 320, h: 220 }, item!.zone)
    const f = floated.focus?.floats?.at(-1)
    return hot?.ok && f ? dockFloat(floated, f.id, targetId, hot.where) : floated
  }, hot?.ok ? `A new section holds ${title}.` : `${title} floats. Drag it onto a section to dock or keep it.`)
  return true
}
