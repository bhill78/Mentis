import { useRef, useState, useSyncExternalStore } from 'react'
import { Mount } from './hosts'
import { CONVERSATION_ID, MIN_FLOAT_H, MIN_FLOAT_W, type Float } from './types'
import { beginDrag, pulseArrived } from './drag'
import RunPanel from '../runs/RunPanel'
import * as nav from '../nav'
import { RUN_SHOW, closeFloat, dockBack, locate, makePrimary, moveFloat, primaryOf, tidyFloats, toFront } from './model'
import { workspace } from '../workspace/place'
import { store } from '../store'
import { WorkspaceZone } from '../workspace/Zones'
import type { ZoneCtl } from '../workspace/TreeView'
import { Opt, Sheet } from '../frame/Sheet'
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
  const [menuAt, setMenuAt] = useState<HTMLElement | null>(null)
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
      <span className="zc-name">{name}</span>{typeof f.zone.options?.says === 'string' && <FromPost f={f} says={f.zone.options.says} />}<span className="grow" />
      <button aria-label="Floating window menu" aria-expanded={!!menuAt} onClick={(e) => setMenuAt(e.currentTarget)}>⋯</button>
      <button onClick={editPrimary} aria-label="Make primary" title="Make primary (F)">◎</button>
      <button onClick={() => workspace.edit((a) => dockBack(a, f.id), `Docked ${name} back beside the section it left.`)} aria-label="Dock back" title="Dock back">⤓</button>
      <button onClick={() => workspace.edit((a) => closeFloat(a, f.id), 'Closed the floating surface.')} aria-label="Close floating surface" title="Close">×</button>
    </header>
    {menuAt && <Sheet anchor={menuAt} onClose={() => setMenuAt(null)} label="floating window menu">
      <Opt onPick={() => {
        setMenuAt(null)
        const r = document.querySelector<HTMLElement>('.fx-main')?.getBoundingClientRect()
        workspace.edit((a) => tidyFloats(a, r?.width ?? 0, r?.height ?? 0), 'Tidied the floating windows.')
      }}>Tidy floating windows</Opt>
    </Sheet>}
    <div className="fl-body fq-float-body">{f.zone.show === 'conversation' ? <Mount id={CONVERSATION_ID} /> : f.zone.show === RUN_SHOW ? <RunPanel run={String(f.zone.options?.run ?? '')} who={String(f.zone.options?.who ?? name)} floating onClose={() => workspace.edit((a) => closeFloat(a, f.id))} onOpenPost={(c, p) => nav.read(c, p, null)} /> : <WorkspaceZone z={f.zone} r={{ x: 0, y: 0, w: f.w, h: f.h }} ctl={{ ...ctl, close: () => workspace.edit((a) => closeFloat(a, f.id)) }} page="this-post" first={false} />}</div>
    <span className="fl-resize" aria-hidden="true" onPointerDown={resize} />
  </section>
}

/** Where an object float came from ("Tidewater survey · #12"), wherever the
 *  owner has gone since (model.ts carryObjectFloats); pressed, its home post
 *  is read, in its own conversation. */
function FromPost({ f, says }: { f: Float; says: string }) {
  const address = f.zone.slot?.items[0]
  const st = address ? store.objects.get(address) : undefined
  const post = st && 'object' in st ? store.posts.get(st.object.post) : undefined
  const home = post?.home
  return <button className="fl-from" title={home ? `From ${says}: open its post` : `From ${says}`} disabled={!home}
    onClick={() => { if (post && home) nav.read(home, post.id, post.number ?? null) }}>{says}</button>
}
