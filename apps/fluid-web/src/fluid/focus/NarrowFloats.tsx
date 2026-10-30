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
 * left out and listed after them with Reopen (ClosedHere). */

import { useLayoutEffect, useRef, useState, useSyncExternalStore } from 'react'
import * as nav from '../nav'
import { workspace } from '../workspace/place'
import type { Rect } from '../workspace/tree'
import { FloatBody, FromPost } from './Floats'
import { PlacedZone } from './ColumnPlace'
import { ConvStub } from './ConvLeaf'
import { isThreadZone, lookOf, RUN_SHOW, updateFloatSlot } from './model'
import { derive, narrowFloats, standIn } from './narrowView'
import { CONVERSATION_SHOW, type Float } from './types'
import { FloatingHeader, type FloatingZoneHead } from './FloatingHeader'
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
  const fs = openFloats(all, closed).sort((x, y) => view.order.indexOf(idOf(x)) - view.order.indexOf(idOf(y)))
  if (!fs.length && !closedHere(a, closed, stand).length) return null
  const shown = fs.map(idOf)
  /** Move up / down among the cards: this class's order, nothing else (workspace.apply, P1). */
  const move = (f: Float, by: -1 | 1): HostOp | undefined => {
    const to = stackStep(view.order, shown, idOf(f), by)
    if (to === null) return undefined
    return { run: () => { const o = workspace.apply(idOf(f), { prop: 'order', to }, { cls: narrowCls }); if (!o.ok) nav.toast({ text: o.reason }) } }
  }
  const placement = (f: Float) => (view.place[idOf(f)] === 'sheet' ? 'sheet' : 'stack')
  return (
    <section className="fq-nfloats" aria-label="Floating">
      {fs.map((f) => <Panel key={f.id} f={f} page={page} stand={f.zone.show === CONVERSATION_SHOW ? stand : null} placeAppearance={a.appearance}
        placement={placement(f)} up={move(f, -1)} down={move(f, 1)} />)}
      <ClosedHere view={a} />
    </section>
  )
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
  return (
    <section className={'fq-nfloat ' + look.className} data-float-id={f.id} data-placement={placement} aria-label={`Floating ${name}`}
      style={{ ...look.style, ['--fh' as string]: Math.round(f.h) + 'px' }}>
      {/* × is Close on this device: the conversation's stand-in too, since
          nothing shared changes (the desktop keeps its column). */}
      {!workspaceZone && <FloatingHeader name={name} floating={head} menuAt={null} onMenu={() => {}} settingsTitle="" />}
      <div ref={at} className="fl-body fq-float-body">
        {conv && stand ? <PlacedZone z={stand} page={page} why="Split it on a wider screen" /> : <FloatBody f={f} page={page} r={r} conversation={<ConvStub />}
          floating={workspaceZone ? { ...head, setSlot, useLookForPlace } : undefined} />}
      </div>
    </section>
  )
}
