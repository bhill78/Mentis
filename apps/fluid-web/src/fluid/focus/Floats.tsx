import { useRef, useSyncExternalStore } from 'react'
import { Mount } from './hosts'
import { CONVERSATION_ID, MIN_FLOAT_H, MIN_FLOAT_W, type Float } from './types'
import { beginDrag, pulseArrived } from './drag'
import RunPanel from '../runs/RunPanel'
import * as nav from '../nav'
import { RUN_SHOW, closeFloat, dockBack, locate, makePrimary, moveFloat, primaryOf, toFront } from './model'
import { workspace } from '../workspace/place'
import { WorkspaceZone } from '../workspace/Zones'
import type { ZoneCtl } from '../workspace/TreeView'
import './floats.css'

const ctl: ZoneCtl = { stacked: false, across: false, canSplitRow: false, canSplitCol: false,
  whyNoSplitRow: 'Floating surfaces must be docked before they can be split', whyNoSplitCol: 'Floating surfaces must be docked before they can be split',
  canMerge: false, canClose: true, split: () => {}, merge: () => {}, close: () => {}, closing: false, widen: () => false, docked: false, fit: false, toggleFit: () => {} }

export default function Floats() {
  const a = useSyncExternalStore(workspace.subscribe, workspace.snapshot)
  return <div className="fq-floats">{(a.focus?.floats ?? []).map((f, i) => <One key={f.id} f={f} front={i === (a.focus?.floats?.length ?? 0) - 1} />)}</div>
}
function One({ f, front }: { f: Float; front: boolean }) {
  const el = useRef<HTMLElement | null>(null)
  const name = f.zone.name ?? 'Zone'
  const primary = primaryOf(workspace.arr) === f.zone.id
  const editPrimary = () => {
    const before = workspace.arr, old = locate(before, primaryOf(before))?.zone.name ?? 'Conversation'
    workspace.edit((a) => makePrimary(a, f.zone.id), `${name} is primary. ${old} floats where it was — ◎ on that window swaps back.`)
    pulseArrived(f.zone.id, f.id)
  }
  const resize = (e: React.PointerEvent) => {
    e.preventDefault(); e.stopPropagation()
    const before = workspace.arr, x = e.clientX, y = e.clientY, w = f.w, h = f.h
    const move = (m: PointerEvent) => workspace.live(moveFloat(workspace.arr, f.id, { x: f.x, y: f.y, w: Math.max(MIN_FLOAT_W, w + m.clientX - x), h: Math.max(MIN_FLOAT_H, h + m.clientY - y) }))
    const up = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up); workspace.live(workspace.arr, { from: before }) }
    window.addEventListener('pointermove', move); window.addEventListener('pointerup', up)
  }
  return <section ref={el} data-float-id={f.id} className={'wk-float' + (front ? ' front' : '') + (primary ? ' primary' : '')} style={{ left: f.x, top: f.y, width: f.w, height: f.h }}
    onPointerDown={() => workspace.quiet((a) => toFront(a, f.id))} role="dialog" aria-label={`Floating ${name}`}>
    <header className="fl-head" tabIndex={0} title="Drag to move; over a section, pads let you dock it"
      onPointerDown={(e) => { if (!(e.target as HTMLElement).closest('button') && el.current) beginDrag({ type: 'float', id: f.id }, e, el.current, name) }}
      onKeyDown={(e) => {
        if (e.key.toLowerCase() === 'f' && !e.altKey && !e.ctrlKey && !e.metaKey) { e.preventDefault(); editPrimary(); return }
        const d = e.shiftKey ? 40 : 10, delta: Record<string, [number, number]> = { ArrowLeft: [-d, 0], ArrowRight: [d, 0], ArrowUp: [0, -d], ArrowDown: [0, d] }
        if (e.altKey && delta[e.key]) { e.preventDefault(); const [dx, dy] = delta[e.key]; workspace.edit((a) => moveFloat(a, f.id, { x: f.x + dx, y: f.y + dy, w: f.w, h: f.h })) }
      }}>
      <span className="zc-name">{name}</span><span className="grow" />
      <span className="fl-tools">
        <button className="fl-btn" onClick={editPrimary} aria-label="Make primary" title="Make primary (F)">◎</button>
        <button className="fl-btn" onClick={() => workspace.edit((a) => dockBack(a, f.id), `Docked ${name} back beside the section it left.`)} aria-label="Dock back" title="Dock back">⤓</button>
        <button className="fl-btn fl-close" onClick={() => workspace.edit((a) => closeFloat(a, f.id), 'Closed the floating surface.')} aria-label="Close floating surface" title="Close">×</button>
      </span>
    </header>
    <div className="fl-body fq-float-body">{f.zone.show === 'conversation' ? <Mount id={CONVERSATION_ID} /> : f.zone.show === RUN_SHOW ? <RunPanel run={String(f.zone.options?.run ?? '')} who={String(f.zone.options?.who ?? name)} floating onClose={() => workspace.edit((a) => closeFloat(a, f.id))} onOpenPost={(c, p) => nav.read(c, p, null)} /> : <WorkspaceZone z={f.zone} r={{ x: 0, y: 0, w: f.w, h: f.h }} ctl={{ ...ctl, close: () => workspace.edit((a) => closeFloat(a, f.id)) }} page="this-post" first={false} />}</div>
    <span className="fl-resize" aria-hidden="true" onPointerDown={resize} />
  </section>
}
