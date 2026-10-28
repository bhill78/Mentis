import { useEffect, useLayoutEffect, useState, useSyncExternalStore } from 'react'
import { dockNativeObject, dragSnapshot, endNativeObjectDrag, floatNativeObject, nativeObjectDrag, padsFor, setDragTarget, subscribeDrag } from './drag'
import type { Where } from './types'
import { workspace } from '../workspace/place'
import { columnZone } from './model'
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
      /* Kept in the column only when it keeps things; over the conversation it
         floats, rather than trading the conversation out of its place. */
      if (column && columnZone(workspace.arr).slot) dockNativeObject(e, columnZone(workspace.arr).id)
      else if (!(e.target as HTMLElement | null)?.closest('.wk-zone')) floatNativeObject(e)
      end()
    }
    document.addEventListener('dragover', over)
    document.addEventListener('drop', drop)
    document.addEventListener('dragend', end)
    return () => { document.removeEventListener('dragover', over); document.removeEventListener('drop', drop); document.removeEventListener('dragend', end) }
  }, [])
  useLayoutEffect(() => {
    if (!drag?.started) return
    const els = targets()
    let hit: HTMLElement | undefined
    for (const el of els) {
      const r = el.getBoundingClientRect()
      if (drag.x >= r.left && drag.x <= r.right && drag.y >= r.top && drag.y <= r.bottom) { hit = el; break }
    }
    if (!hit) { setDragTarget(); return }
    const r = hit.getBoundingClientRect(), column = isColumn(hit)
    const ps = padsFor({ x: r.left, y: r.top, w: r.width, h: r.height }, column)
    const hot = ps.find((p) => p.ok && Math.abs(drag.x - p.x) <= 21 && Math.abs(drag.y - p.y) <= 21)
    const id = isColumn(hit) ? columnZone(workspace.arr).id : hit.dataset.zoneId
    setDragTarget(hot && id ? { id, where: hot.where, rect: r } : undefined)
    redraw((x) => x + 1)
  }, [drag?.x, drag?.y, drag?.started])
  if (!drag?.started) return null
  const hit = targets().find((el) => {
    const r = el.getBoundingClientRect(); return drag.x >= r.left && drag.x <= r.right && drag.y >= r.top && drag.y <= r.bottom
  })
  const r = hit?.getBoundingClientRect(), column = !!hit && isColumn(hit)
  const pads = r ? padsFor({ x: r.left, y: r.top, w: r.width, h: r.height }, column) : []
  const target = drag.target
  const label = target ? `${target.where === 'center' ? (drag.payload.type === 'object' ? 'Keep in' : 'Swap with') : `Dock ${target.where} of`} ${hit?.querySelector('.wk-what')?.textContent ?? 'section'}` : 'Let go to float'
  return <div className="fq-dock-layer" aria-hidden="true">
    {drag.payload.type !== 'float' && <div className="ghost" style={{ left: drag.x + 14, top: drag.y + 10 }}><b>{drag.label}</b><span className="hint">{label}</span></div>}
    {drag.payload.type === 'object' && drag.origin && <svg className="tether"><line x1={drag.origin.left + Math.min(40, drag.origin.width / 2)} y1={drag.origin.top + 12} x2={drag.x} y2={drag.y} /><circle cx={drag.origin.left + Math.min(40, drag.origin.width / 2)} cy={drag.origin.top + 12} r="3" /></svg>}
    {pads.map((p) => <div key={p.where} className={'pad' + (!p.ok ? ' off' : target?.where === p.where ? ' hot' : '')} title={p.ok ? '' : p.why} style={{ left: p.x - 18, top: p.y - 18 }}>{icon[p.where]}</div>)}
    {target && <div className="dock-preview" style={preview(target.rect, target.where)}><span>{label}</span></div>}
  </div>
}
/* What a drag can land on: This post's sections, and the column's place
   (its mount draws no box of its own, so the panel inside it is the target). */
const COLUMN = '.fx-main > .fq-col .fx-conv'
const isColumn = (el: HTMLElement) => el.matches(COLUMN)
const targets = () => [...document.querySelectorAll<HTMLElement>(`.wk-page[data-page="this-post"] .wt-cell[data-zone-id], ${COLUMN}`)]
function preview(r: DOMRect, where: Where): React.CSSProperties {
  if (where === 'center') return { left: r.left, top: r.top, width: r.width, height: r.height }
  if (where === 'left') return { left: r.left, top: r.top, width: r.width / 2, height: r.height }
  if (where === 'right') return { left: r.left + r.width / 2, top: r.top, width: r.width / 2, height: r.height }
  if (where === 'top') return { left: r.left, top: r.top, width: r.width, height: r.height / 2 }
  return { left: r.left, top: r.top + r.height / 2, width: r.width, height: r.height / 2 }
}
