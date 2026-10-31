import { useEffect, useLayoutEffect, useState, useSyncExternalStore } from 'react'
import { dockNativeObject, dragSnapshot, dropPart, endNativeObjectDrag, floatNativeObject, nativeObjectDrag, padsFor, PAD_HIT_RADIUS, setDragTarget, subscribeDrag } from './drag'
import type { Where } from './types'
import { workspace } from '../workspace/place'
import * as nav from '../nav'
import { columnZone } from './model'
import { pageIn, pageView, shownPage } from './page'
import './floats.css'

const icon: Record<Where, string> = { center: '▣', left: '◧', right: '◨', top: '⬒', bottom: '⬓' }
export default function DockLayer() {
  const drag = useSyncExternalStore(subscribeDrag, dragSnapshot)
  const [, redraw] = useState(0)
  useEffect(() => {
    const over = (e: DragEvent) => nativeObjectDrag(e)
    const end = () => setTimeout(endNativeObjectDrag, 0)
    const drop = (e: DragEvent) => {
      /* a composer or a zone took it already */
      if (e.defaultPrevented) { end(); return }
      const column = (e.target as HTMLElement | null)?.closest<HTMLElement>('.fx-main > .fq-col .fx-conv')
      /* Over the conversation: an edge pad docks it at that edge of the
         workspace; the centre keeps it in the column only when the column
         keeps things -- never trading the conversation out of its place --
         and anywhere else it floats. */
      const target = dragSnapshot()?.target
      if (column && target && (target.where !== 'center' || columnZone(pageView(workspace.arr)).slot)) dockNativeObject(e, target.id, target.where)
      else if (column && target?.where === 'center') { e.preventDefault(); nav.toast({ text: 'The conversation stays here. Place this in a section instead.' }) }
      else if (!(e.target as HTMLElement | null)?.closest('.wk-zone')) floatNativeObject(e)
      end()
    }
    document.addEventListener('dragover', over)
    document.addEventListener('drop', drop)
    document.addEventListener('dragend', end)
    return () => { document.removeEventListener('dragover', over); document.removeEventListener('drop', drop); document.removeEventListener('dragend', end) }
  }, [])
  /* a move only (a Magnet's disc) offers no pad and has no target */
  const moveOnly = drag?.payload.type === 'float' && drag.payload.only === 'move'
  useLayoutEffect(() => {
    if (!drag?.started || moveOnly) return
    const els = targets()
    let hit: HTMLElement | undefined
    for (const el of els) {
      const r = el.getBoundingClientRect()
      if (drag.x >= r.left && drag.x <= r.right && drag.y >= r.top && drag.y <= r.bottom) { hit = el; break }
    }
    if (!hit) { setDragTarget(); return }
    const r = visibleRect(hit.getBoundingClientRect()), column = isColumn(hit)
    const part = dropPart({ x: r.left, y: r.top, w: r.width, h: r.height }, drag.x, drag.y, column)
    const id = isColumn(hit) ? columnZone(pageView(workspace.arr)).id : hit.dataset.zoneId
    /* MOVING A WINDOW IS MOVING IT (owner, 2026-10-28): a window dragged by its
       header docks or keeps only when let go ON a pad, never because it passes
       over a section's body. Objects and sections dragged from elsewhere keep
       the whole body as their target. */
    const onPad = drag.payload.type === 'float'
      ? padsFor({ x: r.left, y: r.top, w: r.width, h: r.height }, column).find((p) => p.ok && Math.hypot(drag.x - p.x, drag.y - p.y) <= PAD_HIT_RADIUS)
      : undefined
    const where = drag.payload.type === 'float' ? onPad?.where ?? null : part === 'body' ? 'center' : part === 'outside' ? null : part
    const outer = column && where !== 'center' ? workspaceRect() : null
    setDragTarget(where && id ? { id, where, rect: outer ?? r } : undefined)
    redraw((x) => x + 1)
  }, [drag?.x, drag?.y, drag?.started])
  if (!drag?.started || moveOnly) return null
  const hit = targets().find((el) => {
    const r = el.getBoundingClientRect(); return drag.x >= r.left && drag.x <= r.right && drag.y >= r.top && drag.y <= r.bottom
  })
  const r = hit ? visibleRect(hit.getBoundingClientRect()) : undefined, column = !!hit && isColumn(hit)
  const pads = r ? padsFor({ x: r.left, y: r.top, w: r.width, h: r.height }, column) : []
  const target = drag.target
  const section = hit?.querySelector('.wk-what')?.textContent ?? 'section'
  const destination = column && target?.where !== 'center' ? shownTitle() : `${shownTitle()} · ${section}`
  const refusing = column && target?.where === 'center' && !columnZone(pageView(workspace.arr)).slot
  const label = target ? refusing ? 'Conversation stays here'
    : `${target.where === 'center' ? (drag.payload.type === 'section' ? 'Swap with' : 'Place in') : 'New section here ·'} ${destination}` : 'Let go to float'
  return <div className="fq-dock-layer" aria-hidden="true">
    {drag.payload.type !== 'float' && <div className="ghost" style={{ left: drag.x + 14, top: drag.y + 10 }}><b>{drag.label}</b><span className="hint">{label}</span></div>}
    {drag.payload.type === 'object' && drag.origin && <svg className="tether"><line x1={drag.origin.left + Math.min(40, drag.origin.width / 2)} y1={drag.origin.top + 12} x2={drag.x} y2={drag.y} /><circle cx={drag.origin.left + Math.min(40, drag.origin.width / 2)} cy={drag.origin.top + 12} r="3" /></svg>}
    {pads.map((p) => <div key={p.where} className={'pad' + (drag.payload.type === 'float' ? ' quiet' : '') + (!p.ok ? ' off' : target?.where === p.where ? ' hot' : '')} title={p.ok ? '' : p.why} style={{ left: p.x - 18, top: p.y - 18 }}>{icon[p.where]}</div>)}
    {target && <div className="dock-preview" style={preview(target.rect, target.where)}><span>{label}</span></div>}
  </div>
}
/* What a drag can land on: the sections of the page shown (page.ts), and the
   column's place (its mount draws no box of its own, so the panel inside it
   is the target). */
const COLUMN = '.fx-main > .fq-col .fx-conv'
const isColumn = (el: HTMLElement) => el.matches(COLUMN)
/** the page shown, as its tab names it */
const shownTitle = () => { const p = nav.snapshot().pages.find((x) => x.id === shownPage()); return p && 'title' in p ? p.title : 'This post' }
const shownPageSel = () => `.wk-page[data-page="${CSS.escape(pageIn(workspace.arr, shownPage()))}"]`
/* Only what can be seen: while Focus is on, the arrangement under it is
   hidden, so there is nothing to dock into (a window only moves). An empty
   page is no target either: a window or Magnet dropped on it only moves. */
const targets = () => document.querySelector('.fx-main.fx-lens') ? []
  : [...document.querySelectorAll<HTMLElement>(`${shownPageSel()} .wt-cell[data-zone-id]:not([data-empty]), ${COLUMN}`)].filter((el) => getComputedStyle(el).visibility !== 'hidden' && el.getClientRects().length > 0)
const workspaceRect = () => document.querySelector<HTMLElement>(`${shownPageSel()} > .wt`)?.getBoundingClientRect() ?? null
const visibleRect = (r: DOMRect): DOMRect => {
  const main = document.querySelector<HTMLElement>('.fx-main')?.getBoundingClientRect()
  const left = Math.max(0, main?.left ?? 0, r.left)
  const top = Math.max(0, main?.top ?? 0, r.top)
  const right = Math.min(window.innerWidth, main?.right ?? window.innerWidth, r.right)
  const bottom = Math.min(window.innerHeight, main?.bottom ?? window.innerHeight, r.bottom)
  return new DOMRect(left, top, Math.max(0, right - left), Math.max(0, bottom - top))
}
function preview(r: DOMRect, where: Where): React.CSSProperties {
  if (where === 'center') return { left: r.left, top: r.top, width: r.width, height: r.height }
  if (where === 'left') return { left: r.left, top: r.top, width: r.width / 2, height: r.height }
  if (where === 'right') return { left: r.left + r.width / 2, top: r.top, width: r.width / 2, height: r.height }
  if (where === 'top') return { left: r.left, top: r.top, width: r.width, height: r.height / 2 }
  return { left: r.left, top: r.top + r.height / 2, width: r.width, height: r.height / 2 }
}
