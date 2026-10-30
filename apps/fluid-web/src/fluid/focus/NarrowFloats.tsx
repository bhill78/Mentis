/* FLOATS AT A NARROW WIDTH (narrowView.ts). One column and one sheet leave
 * no room to float anything over, so the floats -- a travelling object's
 * too -- are listed in the workspace pane, after the shown page's tree, one full
 * width card each, front first, under the one surface chrome (SurfaceChrome,
 * placement 'stack'): their name, where an object came from, and × -- Close,
 * on this device only, the conversation's stand-in too (Surface Tension P4:
 * the narrow defect). What is closed here is listed after the cards, each
 * with Reopen, until P5 projects the device's closed set everywhere. No
 * rectangle, no drag. Their rectangles are kept as they are, and the desktop
 * shows them where they were. The conversation's own float shows what the
 * column holds there, else says the conversation is in the column. */

import { useLayoutEffect, useRef, useState, useSyncExternalStore } from 'react'
import * as nav from '../nav'
import { workspace } from '../workspace/place'
import type { Rect } from '../workspace/tree'
import { FloatBody, FromPost } from './Floats'
import { PlacedZone } from './ColumnPlace'
import { ConvStub } from './ConvLeaf'
import { isThreadZone, lookOf, RUN_SHOW, updateFloatSlot } from './model'
import { narrowFloats, standIn } from './narrowView'
import { CONVERSATION_SHOW, type Float } from './types'
import { FloatingHeader, type FloatingZoneHead } from './FloatingHeader'
import { onPage, useShownView } from './page'
import { DEFAULT_APPEARANCE, readAppearance, zoneAppearanceStyle } from '../present'
import { useScheme } from '../frame/look'
import { classNow } from '../surface/input'
import type { HostOp } from '../surface/actions/providers/ops'
import './floats.css'

export default function NarrowFloats() {
  const { page, view: a } = useShownView()
  /* a thread's window is one of the thread pane's tabs here (Sheets.tsx
     ThreadPanel), as kept threads always were at this width */
  const closed = useSyncExternalStore(workspace.subscribe, () => workspace.closed[classNow()])
  const all = narrowFloats(a).filter((f) => !isThreadZone(f.zone))
  if (!all.length) return null
  const stand = standIn(a)
  const fs = all.filter((f) => !closed.has(f.zone.id))
  const gone = all.filter((f) => closed.has(f.zone.id))
  const nameOf = (f: Float) => (f.zone.show === CONVERSATION_SHOW ? stand?.name ?? 'Conversation' : f.zone.name ?? 'Zone')
  return (
    <section className="fq-nfloats" aria-label="Floating">
      {fs.map((f) => <Panel key={f.id} f={f} page={page} stand={f.zone.show === CONVERSATION_SHOW ? stand : null} placeAppearance={a.appearance} />)}
      {gone.length > 0 && (
        <p className="fq-nclosed" aria-label="Closed on this device">
          <span className="fq-nclosed-word">Closed here</span>
          {gone.map((f) => (
            <button key={f.id} type="button" className="fq-nreopen" data-reopen={f.zone.id} title={`Reopen ${nameOf(f)} on this device`}
              onClick={() => { const o = workspace.apply(f.zone.id, { prop: 'open', to: true }); if (!o.ok) nav.toast({ text: o.reason }) }}>↺ {nameOf(f)}</button>
          ))}
        </p>
      )}
    </section>
  )
}

/** × on a card: Close on this device (workspace.apply, P1), never the window itself. */
export const closeHere = (id: string): HostOp => ({
  run: () => { const o = workspace.apply(id, { prop: 'open', to: false }); if (!o.ok) nav.toast({ text: o.reason }) },
  says: 'Close here: this device stops showing it; the workspace keeps it (Reopen brings it back)',
})

function Panel({ f, page, stand, placeAppearance }: { f: Float; page: string; stand: Float['zone'] | null; placeAppearance?: unknown }) {
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
  return (
    <section className={'fq-nfloat ' + look.className} data-float-id={f.id} aria-label={`Floating ${name}`}
      style={{ ...look.style, ['--fh' as string]: Math.round(f.h) + 'px' }}>
      {/* × is Close on this device: the conversation's stand-in too, since
          nothing shared changes (the desktop keeps its column). */}
      {!workspaceZone && <FloatingHeader name={name} floating={{ id: f.zone.id, placement: 'stack', closeHere: closeHere(f.zone.id),
        from: says ? <FromPost f={f} says={says} /> : undefined }} menuAt={null} onMenu={() => {}} settingsTitle="" />}
      <div ref={at} className="fl-body fq-float-body">
        {conv && stand ? <PlacedZone z={stand} page={page} why="Split it on a wider screen" /> : <FloatBody f={f} page={page} r={r} conversation={<ConvStub />}
          floating={workspaceZone ? { id: f.zone.id, placement: 'stack', closeHere: closeHere(f.zone.id), from: says ? <FromPost f={f} says={says} /> : undefined, setSlot, useLookForPlace } : undefined} />}
      </div>
    </section>
  )
}
