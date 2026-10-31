/* FLOATS AT A NARROW WIDTH (narrowView.ts). One column and one sheet leave
 * no room to float anything over, so the floats -- a travelling object's
 * too -- are listed in the workspace pane, after the shown page's tree, one full
 * width card each, under the one surface chrome (SurfaceChrome): a stack card
 * in compact, a card of the workspace sheet in medium (narrowView.ts
 * DEFAULT_PLACE). Their name, where an object came from, and × -- Close, on
 * this device only, the conversation's stand-in too (Surface Tension P4: the
 * narrow defect). No rectangle, no drag. Their rectangles are kept as they
 * are, and the desktop shows them where they were. The conversation's own
 * float shows what the column holds there, else says the conversation is in
 * the column.
 *
 * WHAT THIS DEVICE SHOWS (P5): the cards come in the class's order (derive:
 * the class's record over today's front-first order), Move up and Move down
 * change that order in this class's record only, and what is closed here is
 * left out and listed after them with Reopen (ClosedHere).
 *
 * DISCS (finding Turn #1614): a Magnet window at its disc is no card. It is
 * drawn over the page (Discs), where this class's record says it was moved
 * (`at`), else on a free slot of the disc grid (narrowView.ts discPlaces);
 * a move is this class's alone (transition.ts 'rect'), so the desktop's
 * windows never change. Tap, double-tap and hold are the disc's own, as on
 * the desktop, and none of them needs a hover. */

import { useLayoutEffect, useRef, useState, useSyncExternalStore } from 'react'
import * as nav from '../nav'
import { workspace } from '../workspace/place'
import type { Rect } from '../workspace/tree'
import { FloatBody, FromPost } from './Floats'
import { PlacedZone } from './ColumnPlace'
import { ConvStub } from './ConvLeaf'
import { isThreadZone, lookOf, RUN_SHOW, updateFloatSlot } from './model'
import { derive, discPlaces, narrowFloats, standIn } from './narrowView'
import { findSurface } from '../surface/state'
import { freeDisc, stateIn, viewOf } from '../surface/transition'
import type { DevicePlacement } from '../surface/types'
import { MAGNET_CHOICES } from '../surface/magnet/choices'
import { CONVERSATION_SHOW, type Float } from './types'
import { FloatingFrame, type FloatingZoneHead } from './FloatingHeader'
import { onPage, useShownView } from './page'
import { DEFAULT_APPEARANCE, readAppearance, zoneAppearanceStyle } from '../present'
import { useScheme } from '../frame/look'
import { usePresentationClass } from '../frame/narrow'
import { ClosedHere, closeHere, useClosedHere } from '../surface/ClosedHere'
import { closedHere, openFloats, stackStep } from '../surface/projection'
import type { HostOp } from '../surface/actions/providers/ops'
import './floats.css'

export { closeHere }

export default function NarrowFloats() {
  const { page, view: a } = useShownView()
  const cls = usePresentationClass()
  const narrowCls = cls === 'wide' ? 'compact' : cls
  /* a thread's window is one of the thread pane's tabs here (Sheets.tsx
     ThreadPanel), as kept threads always were at this width */
  const closed = useClosedHere()
  const record = useSyncExternalStore(workspace.subscribe, () => workspace.devices[narrowCls])
  const all = narrowFloats(a).filter((f) => !isThreadZone(f.zone))
  const stand = standIn(a)
  const view = derive(a, narrowCls, record)
  /* the conversation's own window is in the order as what stands in for it */
  const idOf = (f: Float) => (f.zone.show === CONVERSATION_SHOW && stand ? stand.id : f.zone.id)
  const open = openFloats(all, closed).sort((x, y) => view.order.indexOf(idOf(x)) - view.order.indexOf(idOf(y)))
  const ctx = workspace.surfaceCtx({ page, cls: narrowCls })
  const isDisc = (f: Float) => { const found = findSurface(viewOf(ctx), f.zone.id), s = stateIn(ctx, f.zone.id); return !!found && !!s && freeDisc(found, s) }
  const discs = open.filter(isDisc)
  const fs = open.filter((f) => !isDisc(f))
  const discLayer = discs.length ? <Discs fs={discs} page={page} cls={narrowCls} at={record?.at} /> : null
  if (!fs.length && !closedHere(a, closed, stand).length) return discLayer
  const shown = fs.map(idOf)
  /** Move up / down among the cards: this class's order, nothing else (workspace.apply, P1). */
  const move = (f: Float, by: -1 | 1): HostOp | undefined => {
    const to = stackStep(view.order, shown, idOf(f), by)
    if (to === null) return undefined
    return { run: () => { const o = workspace.apply(idOf(f), { prop: 'order', to }, { cls: narrowCls }); if (!o.ok) nav.toast({ text: o.reason }) } }
  }
  const placement = (f: Float) => (view.place[idOf(f)] === 'sheet' ? 'sheet' : 'stack')
  return (<>
    <section className="fq-nfloats" aria-label="Floating">
      {fs.map((f) => <Panel key={f.id} f={f} page={page} stand={f.zone.show === CONVERSATION_SHOW ? stand : null} placeAppearance={a.appearance}
        placement={placement(f)} up={move(f, -1)} down={move(f, 1)} />)}
      <ClosedHere view={a} />
    </section>
    {discLayer}
  </>)
}

/** The discs over the page: each where this class's record puts it, held in
 *  the room; a move follows the press and is kept, when it ends, as this
 *  class's `at` (one undo step), never as its window's rectangle. */
function Discs({ fs, page, cls, at }: { fs: Float[]; page: string; cls: 'medium' | 'compact'; at: DevicePlacement['at'] }) {
  const el = useRef<HTMLDivElement | null>(null)
  const [room, setRoom] = useState({ w: 0, h: 0 })
  const [live, setLive] = useState<{ id: string; x: number; y: number } | null>(null)
  /* the page scrolls when cards follow its sections: the discs stay over
     what is in view, as a desktop disc stays over the canvas */
  const [scroll, setScroll] = useState(0)
  useLayoutEffect(() => {
    const node = el.current
    if (!node) return
    const read = () => setRoom((r) => (r.w === node.clientWidth && r.h === node.clientHeight ? r : { w: node.clientWidth, h: node.clientHeight }))
    const ro = new ResizeObserver(read)
    ro.observe(node); read()
    const page = node.parentElement
    const scrolled = () => setScroll(page?.scrollTop ?? 0)
    page?.addEventListener('scroll', scrolled, { passive: true }); scrolled()
    return () => { ro.disconnect(); page?.removeEventListener('scroll', scrolled) }
  }, [])
  const disc = MAGNET_CHOICES.disc
  const places = discPlaces(fs.map((f) => f.zone.id), at, room, disc)
  const hold = (p: { x: number; y: number }) => ({ x: Math.max(0, Math.min(p.x, room.w - disc)), y: Math.max(0, Math.min(p.y, room.h - disc)) })
  /* the disc told a move from its tap and hold (MagnetZone startMove): follow the press from there */
  const moveFrom = (f: Float) => (from: { x: number; y: number }) => {
    const start = places[f.zone.id]
    if (!start) return
    let to = start
    const follow = (m: PointerEvent) => { if (m.pointerType !== 'mouse') m.preventDefault(); to = hold({ x: start.x + m.clientX - from.x, y: start.y + m.clientY - from.y }); setLive({ id: f.zone.id, ...to }) }
    const stop = () => { window.removeEventListener('pointermove', follow); window.removeEventListener('pointerup', up); window.removeEventListener('pointercancel', cancel) }
    const up = () => {
      stop()
      if (to !== start) {
        const o = workspace.apply(f.zone.id, { prop: 'rect', rect: { x: to.x, y: to.y, w: f.w, h: f.h } }, { page, cls })
        if (!o.ok && o.reason) nav.toast({ text: o.reason })
      }
      setLive(null)
    }
    const cancel = () => { stop(); setLive(null) }
    window.addEventListener('pointermove', follow, { passive: false }); window.addEventListener('pointerup', up); window.addEventListener('pointercancel', cancel)
  }
  return <div ref={el} className="fq-ndiscs" data-moving={live ? '' : undefined} style={scroll ? { transform: `translateY(${scroll}px)` } : undefined}>
    {fs.map((f) => {
      const p = live?.id === f.zone.id ? live : places[f.zone.id] ?? { x: 0, y: 0 }
      const name = f.zone.name ?? 'Magnet'
      return <section key={f.id} className="fq-ndisc" data-float-id={f.id} data-level="icon" aria-label={`Floating ${name}`} style={{ left: p.x, top: p.y }}>
        <FloatBody f={f} page={page} r={{ x: 0, y: 0, w: disc, h: disc }}
          floating={{ id: f.zone.id, placement: 'float', move: moveFrom(f), closeHere: closeHere(f.zone.id) }} />
      </section>
    })}
  </div>
}

function Panel({ f, page, stand, placeAppearance, placement, up, down }: { f: Float; page: string; stand: Float['zone'] | null; placeAppearance?: unknown
  placement: 'stack' | 'sheet'; up?: HostOp; down?: HostOp }) {
  const at = useRef<HTMLDivElement | null>(null)
  const [r, setR] = useState<Rect>({ x: 0, y: 0, w: f.w, h: f.h })
  useLayoutEffect(() => {
    const el = at.current
    if (!el) return
    const read = () => { const b = el.getBoundingClientRect(); if (b.width && b.height) setR((o) => (Math.round(o.w) === Math.round(b.width) && Math.round(o.h) === Math.round(b.height) ? o : { x: 0, y: 0, w: b.width, h: b.height })) }
    read()
    const ro = new ResizeObserver(read)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  const conv = f.zone.show === CONVERSATION_SHOW
  const name = (conv && stand ? stand.name : f.zone.name) ?? (conv ? 'Conversation' : 'Zone')
  const says = !conv && typeof f.zone.options?.says === 'string' ? f.zone.options.says : null
  const workspaceZone = !conv && f.zone.show !== RUN_SHOW
  const scheme = useScheme()
  const appearance = readAppearance(lookOf(f.zone), readAppearance(placeAppearance, DEFAULT_APPEARANCE))
  const look = zoneAppearanceStyle(appearance, scheme)
  const setSlot: NonNullable<FloatingZoneHead['setSlot']> = (fn, words) =>
    workspace.edit(onPage((v) => updateFloatSlot(v, f.id, fn), page), words)
  const useLookForPlace: NonNullable<FloatingZoneHead['useLookForPlace']> = (appearance) => workspace.edit((a) => ({
    ...onPage((v) => updateFloatSlot(v, f.id, (slot) => ({ ...slot, appearance: undefined })), page)(a), appearance,
  }), `Every zone here without a look of its own now looks like ${name}.`)
  const head = { id: f.zone.id, placement, closeHere: closeHere(f.zone.id), moveUp: up, moveDown: down,
    from: says ? <FromPost f={f} says={says} /> : undefined }
  /* ONE FRAME PER CARD (surface composition package 3): what the card shows
     is the body of the floating surface's frame, as on the desktop -- the
     conversation (or its stand-in) and a run in FloatingFrame, a section or a
     thread framing itself. × is Close on this device: the conversation's
     stand-in too, since nothing shared changes (the desktop keeps its column). */
  return (
    <section className={'fq-nfloat ' + look.className} data-float-id={f.id} data-placement={placement} aria-label={`Floating ${name}`}
      style={{ ...look.style, ['--fh' as string]: Math.round(f.h) + 'px' }}>
      {conv
        ? <FloatingFrame name={name} floating={head} onMenu={() => {}} body={<div className="fl-body fq-float-body">
          {stand ? <PlacedZone z={stand} page={page} why="Split it on a wider screen" /> : <ConvStub />}</div>} />
        : workspaceZone
          ? <div ref={at} className="fl-body fq-float-body"><FloatBody f={f} page={page} r={r} floating={{ ...head, setSlot, useLookForPlace }} /></div>
          : <FloatBody f={f} page={page} r={r} floating={head} />}
    </section>
  )
}
