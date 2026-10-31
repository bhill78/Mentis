import { store } from '../store'
import { titleOf } from '../workspace/hooks'
import { treeOf, withTree, workspace } from '../workspace/place'
import { dockFloat, dockSection, floatObject, floatOut, floatsAlone, locate, moveFloat } from './model'
import * as nav from '../nav'
import { DRAG } from '../workspace/keep'
import { GUTTER, MIN_H, MIN_W, unkeep } from '../workspace/tree'
import type { Dragged, Where } from './types'
import { fromOf } from '../conversation/Grip'
import { THIS_POST, onPage, pageIn, pageView, shownPage } from './page'
import { fitFloat, floatContentOf, measureFloat } from './fitFloat'
import type { Displacement, Guide } from './placement'
import type { Rect as SurfaceRect } from '../surface/types'

/** What a native object drag carries: its live address; the zone it was kept
 *  in, when it comes from a section (flick.ts); where it came from, said
 *  (Grip.tsx `from`). */
type Carried = { address?: string; zone?: string; page?: string; kept?: boolean; from?: string }
/** Where an object came from, said ("Tidewater survey · #12"): the drag's own
 *  words, else its post's, read from the object itself -- so a section's card
 *  says it as a grip in the post does. */
export function saysOf(address: string, given?: string): string | undefined {
  if (given) return given
  if (address.startsWith('post:')) {
    const whole = store.posts.get(address.slice(5))
    return whole ? fromOf(whole) : undefined
  }
  const st = store.objects.get(address)
  const post = st && 'object' in st ? store.posts.get(st.object.post) : undefined
  return post ? fromOf(post) : undefined
}

export interface Pad { where: Where; x: number; y: number; ok: boolean; why?: string }
export const TOUCH_HOLD_MS = 350
export const TOUCH_MOVE_PX = 8
export const PAD_HIT_RADIUS = 22
export type DropPart = Where | 'body' | 'outside'
export type PointerDragDecision = 'wait' | 'start' | 'cancel'
/** P1/P2 may supply this bounded hook once capabilities and the effective
 * setting exist. P6 owns its result; no setting or action API is invented. */
export type DragPlacementCoordinator = (rect: SurfaceRect, moving: string) => {
  rect: SurfaceRect; guides: Guide[]; displacements: Map<string, Displacement>
}

/** A coarse pointer gets a chance to scroll before an explicit handle takes
 *  it. Mouse keeps the prototype's immediate, six-pixel drag threshold. */
export function pointerDragDecision(pointerType: string, elapsed: number, distance: number): PointerDragDecision {
  if (pointerType === 'mouse') return 'start'
  if (distance > TOUCH_MOVE_PX) return 'cancel'
  return elapsed >= TOUCH_HOLD_MS ? 'start' : 'wait'
}

/** Arm a touch/pen handle without cancelling its pointerdown. Moving first
 *  leaves the gesture to scrolling; holding makes this handle exclusive. */
export function armTouchDrag(e: React.PointerEvent | PointerEvent, handle: Element, start: () => void): boolean {
  if (e.pointerType === 'mouse') return false
  if (!e.isPrimary) return true
  const id = e.pointerId, x = e.clientX, y = e.clientY, at = performance.now()
  let timer = 0
  const stop = () => {
    clearTimeout(timer)
    window.removeEventListener('pointermove', move)
    window.removeEventListener('pointerup', end)
    window.removeEventListener('pointercancel', end)
  }
  const end = (ev: PointerEvent) => { if (ev.pointerId === id) stop() }
  const move = (ev: PointerEvent) => {
    if (ev.pointerId !== id) return
    if (pointerDragDecision(e.pointerType, performance.now() - at, Math.hypot(ev.clientX - x, ev.clientY - y)) === 'cancel') stop()
  }
  timer = window.setTimeout(() => {
    stop()
    if (pointerDragDecision(e.pointerType, performance.now() - at, 0) !== 'start') return
    handle.classList.add('fx-touch-drag')
    const release = (ev: PointerEvent) => {
      if (ev.pointerId !== id) return
      handle.classList.remove('fx-touch-drag')
      window.removeEventListener('pointerup', release)
      window.removeEventListener('pointercancel', release)
    }
    window.addEventListener('pointerup', release)
    window.addEventListener('pointercancel', release)
    start()
  }, TOUCH_HOLD_MS)
  window.addEventListener('pointermove', move)
  window.addEventListener('pointerup', end)
  window.addEventListener('pointercancel', end)
  return true
}
export interface DragView {
  payload: Dragged; x: number; y: number; x0: number; y0: number; started: boolean
  label: string; origin?: DOMRect; target?: { id: string; where: Where; rect: DOMRect }
}
let view: DragView | null = null
let startArr = workspace.arr
/** the page a drag began on (page.ts): it lands there, whatever is shown by then */
let startPage = THIS_POST
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
    /* the page shown's: another page may have a section of the same id (the conversation's) */
    const page = `.wk-page[data-page="${CSS.escape(pageIn(workspace.arr, shownPage()))}"]`
    const els = [document.querySelector<HTMLElement>(`${page} .wt-cell[data-zone-id="${CSS.escape(contentId)}"]`),
      ...(floatId ? [document.querySelector<HTMLElement>(`.wk-float[data-float-id="${CSS.escape(floatId)}"]`)] : [])].filter((x): x is HTMLElement => !!x)
    for (const el of els) { el.classList.remove('arrived'); void el.offsetWidth; el.classList.add('arrived') }
  })
}

/** Mirror native object drags into the same compass/ghost layer. Browsers do
 *  not expose the payload until drop, so the live view intentionally carries
 *  only its kind; the drop handler reads the address. */
export function nativeObjectDrag(e: DragEvent) {
  if (!e.dataTransfer?.types.includes(DRAG)) return
  /* Accepted everywhere: without this no drop outside a zone (the page
     between sections, a float's head, the column) ever fires, so nothing
     dragged out of a post could float. A zone or composer says its own. */
  if (!e.defaultPrevented) { e.preventDefault(); e.dataTransfer.dropEffect = e.ctrlKey ? 'copy' : 'move' }
  /* One drag, one view: dragover fires on and on where the pointer rests, so
     a drag already seen only moves -- its origin and the target the dock
     layer found for it stay (DockLayer recomputes the target as it moves). */
  if (view?.payload.type === 'object' && view.started) {
    if (view.x !== e.clientX || view.y !== e.clientY) { view = { ...view, x: e.clientX, y: e.clientY }; emit() }
    return
  }
  const source = document.querySelector<HTMLElement>('[data-address][draggable=true]:hover')
  const origin = source?.getBoundingClientRect()
  view = { payload: { type: 'object', address: '', from: source?.closest<HTMLElement>('[data-zone-id]')?.dataset.zoneId },
    x: e.clientX, y: e.clientY, x0: e.clientX, y0: e.clientY, started: true, label: 'Object', ...(origin ? { origin } : {}) }
  emit()
}
export function endNativeObjectDrag() { if (view?.payload.type === 'object') { view = null; emit() } }

export function floatNativeObject(e: DragEvent): boolean {
  if (!e.dataTransfer?.types.includes(DRAG)) return false
  let item: Carried | null = null
  try { item = JSON.parse(e.dataTransfer.getData(DRAG) || 'null') } catch { return false }
  if (!item?.address) return false
  const st = store.objects.get(item.address)
  const title = st && 'object' in st ? titleOf(st.object) : 'Object'
  const p = inMain(e.clientX, e.clientY)
  const source = document.querySelector<HTMLElement>('[data-address][draggable=true]:hover')
  const rect = objectRect(item.address, { x: p.x - 30, y: p.y - 16 }, source)
  workspace.edit(onPage((a) => floatObject(a, item!.address!, title, rect, e.ctrlKey ? undefined : item!.zone, saysOf(item!.address!, item!.from))),
    `${title} floats. Drag it onto a section to dock or keep it.`)
  e.preventDefault()
  return true
}

export function dockNativeObject(e: DragEvent, target: string, where: Where = 'center'): boolean {
  if (!e.dataTransfer?.types.includes(DRAG)) return false
  let item: Carried | null = null
  try { item = JSON.parse(e.dataTransfer.getData(DRAG) || 'null') } catch { return false }
  if (!item?.address) return false
  const st = store.objects.get(item.address)
  const title = st && 'object' in st ? titleOf(st.object) : 'Object'
  let docked = false
  workspace.edit((whole) => {
    const next = onPage((a) => {
      const p = inMain(e.clientX, e.clientY)
      const before = new Set(a.focus?.floats?.map((f) => f.id) ?? [])
      const floated = floatObject(a, item!.address!, title, objectRect(item!.address!, p), e.ctrlKey ? undefined : item!.zone, saysOf(item!.address!, item!.from))
      const f = floated.focus?.floats?.find((x) => !before.has(x.id))
      if (!f) return a
      const placed = dockFloat(floated, f.id, target, where)
      docked = placed !== floated
      return docked ? placed : a
    })(whole)
    return docked ? leaveSource(next, item!, e.ctrlKey) : next
  }, where === 'center' ? `Kept in ${locateName(target)}.` : `A new section holds ${title}.`)
  e.preventDefault()
  return true
}
const locateName = (id: string) => {
  const v = pageView(workspace.arr)
  const l = v.focus?.column?.id === id ? v.focus.column : undefined
  return l?.name ?? 'the zone'
}
const leaveSource = (a: typeof workspace.arr, item: Carried, copy: boolean) => {
  if (copy || !item.kept || !item.page || !item.zone || !item.address) return a
  const source = treeOf(a, item.page)
  return source ? withTree(a, item.page, unkeep(source, item.zone, item.address)) : a
}

export function padsFor(r: { x: number; y: number; w: number; h: number }, column = false): Pad[] {
  const cx = r.x + r.w / 2, cy = r.y + r.h / 2, off = 46
  const insideX = (x: number) => r.w < PAD_HIT_RADIUS * 2 ? cx : Math.max(r.x + PAD_HIT_RADIUS, Math.min(x, r.x + r.w - PAD_HIT_RADIUS))
  const insideY = (y: number) => r.h < PAD_HIT_RADIUS * 2 ? cy : Math.max(r.y + PAD_HIT_RADIUS, Math.min(y, r.y + r.h - PAD_HIT_RADIUS))
  const row = column || r.w >= 2 * MIN_W + GUTTER, col = column || r.h >= 2 * MIN_H + GUTTER
  return [
    { where: 'center', x: cx, y: cy, ok: true },
    { where: 'left', x: insideX(cx - off), y: cy, ok: row, why: 'Too narrow to split' },
    { where: 'right', x: insideX(cx + off), y: cy, ok: row, why: 'Too narrow to split' },
    { where: 'top', x: cx, y: insideY(cy - off), ok: col, why: 'Too short to split' },
    { where: 'bottom', x: cx, y: insideY(cy + off), ok: col, why: 'Too short to split' },
  ]
}

/** A section's whole body is a placement target. Only an enabled edge pad
 *  splits; the small centre pad is just the body's visual anchor. */
export function dropPart(r: { x: number; y: number; w: number; h: number }, x: number, y: number, column = false): DropPart {
  if (x < r.x || x > r.x + r.w || y < r.y || y > r.y + r.h) return 'outside'
  const edge = padsFor(r, column).find((p) => p.where !== 'center' && p.ok
    && Math.abs(x - p.x) <= PAD_HIT_RADIUS && Math.abs(y - p.y) <= PAD_HIT_RADIUS)
  return edge?.where ?? 'body'
}

const objectRect = (address: string, at: { x: number; y: number }, source?: HTMLElement | null) => {
  const main = document.querySelector<HTMLElement>('.fx-main')
  const room = { w: main?.clientWidth ?? 1200, h: main?.clientHeight ?? 800 }
  const st = store.objects.get(address)
  const object = st && 'object' in st ? st.object : null
  const shown = source ?? document.querySelector<HTMLElement>(`[data-address="${CSS.escape(address)}"]`)
  return fitFloat(measureFloat(shown, floatContentOf(object)), room, at)
}

export function beginDrag(payload: Dragged, e: React.PointerEvent | PointerEvent, origin: HTMLElement, label: string, coordinate?: DragPlacementCoordinator) {
  if (e.button !== 0) return
  if (armTouchDrag(e, e.currentTarget as HTMLElement, () => beginDragNow(payload, e, origin, label, coordinate))) return
  beginDragNow(payload, e, origin, label, coordinate)
}
function beginDragNow(payload: Dragged, e: React.PointerEvent | PointerEvent, origin: HTMLElement, label: string, coordinate?: DragPlacementCoordinator) {
  e.preventDefault()
  workspace.clearDisplacements()
  startArr = workspace.arr
  startPage = shownPage()
  const f = payload.type === 'float' ? pageView(startArr, startPage).focus?.floats?.find((x) => x.id === payload.id) : undefined
  const main = document.querySelector<HTMLElement>('.fx-main')?.getBoundingClientRect()
  const shown = origin.getBoundingClientRect()
  floatRect = f ? { x: shown.left - (main?.left ?? 0), y: shown.top - (main?.top ?? 0), w: f.w, h: f.h } : null
  view = { payload, x: e.clientX, y: e.clientY, x0: e.clientX, y0: e.clientY, started: false, label, origin: origin.getBoundingClientRect() }
  const move = (m: PointerEvent) => {
    if (!view) return
    if (m.pointerType !== 'mouse') m.preventDefault()
    const started = view.started || Math.hypot(m.clientX - view.x0, m.clientY - view.y0) >= 6
    view = { ...view, x: m.clientX, y: m.clientY, started }
    if (started && view.payload.type === 'float' && floatRect) {
      const id = view.payload.id, raw = { ...floatRect, x: floatRect.x + m.clientX - view.x0, y: floatRect.y + m.clientY - view.y0 }
      const planned = coordinate?.(raw, id)
      if (planned) workspace.displace(planned.displacements)
      workspace.live(onPage((v) => moveFloat(v, id, planned?.rect ?? raw), startPage)(workspace.arr))
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
    if (cancel) { workspace.clearDisplacements(); workspace.live(startArr); return }
    const t = d.target
    if (d.payload.type === 'float') {
      const fid = d.payload.id
      const beforeDock = workspace.arr
      const next = t ? onPage((v) => dockFloat(v, fid, t.id, t.where), startPage)(beforeDock) : beforeDock
      if (t) workspace.clearDisplacements()
      workspace.live(next, { from: startArr })
      if (t?.where === 'center' && next === beforeDock) {
        return
      }
      /* Docked, kept or swapped, it says so with Undo, as every other step does. */
      if (t && next !== startArr) {
        const was = pageView(startArr, startPage).focus?.floats?.find((x) => x.id === fid)?.zone
        const name = was?.name ?? d.label
        const into = locate(pageView(next, startPage), t.id)?.zone.name ?? 'the section'
        const words = t.where !== 'center' ? `Docked ${name} ${t.where} of ${into}.`
          : was?.show === 'object' ? `Kept in ${into}.` : `${name} is primary; ${into} floats in its place.`
        nav.toast({ text: words, action: { label: 'Undo', run: () => workspace.undo() } })
      }
      return
    }
    if (d.payload.type === 'section') {
      const p = inMain(up.clientX, up.clientY), id = d.payload.id
      const main = document.querySelector<HTMLElement>('.fx-main')
      const origin = document.querySelector<HTMLElement>(`[data-zone-id="${CSS.escape(id)}"]`)
      const measured = measureFloat(origin, (origin?.scrollWidth ?? 0) > 600 ? 'wide' : 'other')
      const rect = fitFloat(measured, { w: main?.clientWidth ?? 1200, h: main?.clientHeight ?? 800 }, { x: p.x - 30, y: p.y - 16 })
      const view = pageView(workspace.arr, startPage), sole = locate(view, id)?.zone
      const alone = view.tree.type === 'zone' && !!sole && floatsAlone(workspace.kind, pageIn(workspace.arr, startPage), sole)
      const next = onPage((v) => t ? dockSection(v, id, t.id, t.where) : floatOut(v, id, rect, { alone }), startPage)(workspace.arr)
      workspace.edit(() => next, t ? (t.where === 'center' ? `${d.label} is primary; its target traded places.` : `Docked ${d.label} ${t.where} of its target.`) : `${d.label} floats; ${alone ? 'the page behind it is empty' : 'the sections beside it took its room'}. “Dock back” returns it.`)
    }
  }
  const done = (up: PointerEvent) => finish(up)
  const cancelled = (up: PointerEvent) => finish(up, true)
  window.addEventListener('pointermove', move)
  window.addEventListener('pointerup', done)
  window.addEventListener('pointercancel', cancelled)
}

/** A native object drop on an edge makes a new section. The rest of the
 *  section is left to its ordinary placement handler; only outside sections
 *  reaches the document handler and becomes a float. */
export function handleObjectDrop(e: React.DragEvent, targetId: string): boolean {
  let item: Carried | null = null
  try { item = JSON.parse(e.dataTransfer.getData(DRAG) || 'null') } catch { return false }
  if (!item?.address) return false
  const cell = (e.currentTarget as HTMLElement).closest('.wt-cell') as HTMLElement | null
  const r = cell?.getBoundingClientRect()
  const part = r ? dropPart({ x: r.left, y: r.top, w: r.width, h: r.height }, e.clientX, e.clientY) : 'outside'
  if (part === 'body') return false
  e.preventDefault()
  const st = store.objects.get(item.address)
  const title = st && 'object' in st ? titleOf(st.object) : 'Object'
  workspace.edit((whole) => {
    let placed = false
    let next = onPage((a) => {
      const p = inMain(e.clientX, e.clientY)
      const before = new Set(a.focus?.floats?.map((f) => f.id) ?? [])
      const floated = floatObject(a, item!.address!, title, objectRect(item!.address!, { x: p.x - 30, y: p.y - 16 }), e.ctrlKey ? undefined : item!.zone, saysOf(item!.address!, item!.from))
      const f = floated.focus?.floats?.find((x) => !before.has(x.id))
      if (part === 'outside' || !f) return floated
      const docked = dockFloat(floated, f.id, targetId, part)
      placed = docked !== floated
      return placed ? docked : a
    })(whole)
    return placed ? leaveSource(next, item!, e.ctrlKey) : next
  }, part !== 'outside' ? `A new section holds ${title}.` : `${title} floats. Drag it onto a section to dock or keep it.`)
  return true
}
