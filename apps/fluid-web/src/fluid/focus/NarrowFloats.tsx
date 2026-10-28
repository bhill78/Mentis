/* FLOATS AT A NARROW WIDTH (narrowView.ts). One column and one sheet leave
 * no room to float anything over, so the floats -- a travelling object's
 * too -- are listed in the workspace pane, after This post's tree, one full
 * width panel each, front first: their name, where an object came from, and
 * Close; no rectangle, no drag. Their rectangles are kept as they are, and
 * the desktop shows them where they were. The conversation's own float shows
 * what the column holds there, else says the conversation is in the column. */

import { useLayoutEffect, useRef, useState, useSyncExternalStore } from 'react'
import { workspace } from '../workspace/place'
import type { Rect } from '../workspace/tree'
import { FloatBody, FromPost } from './Floats'
import { PlacedZone } from './ColumnPlace'
import { ConvStub } from './ConvLeaf'
import { closeFloat } from './model'
import { narrowFloats, standIn } from './narrowView'
import { CONVERSATION_SHOW, type Float } from './types'
import './floats.css'

export default function NarrowFloats() {
  const a = useSyncExternalStore(workspace.subscribe, workspace.snapshot)
  const fs = narrowFloats(a)
  if (!fs.length) return null
  const stand = standIn(a)
  return (
    <section className="fq-nfloats" aria-label="Floating">
      {fs.map((f) => <Panel key={f.id} f={f} stand={f.zone.show === CONVERSATION_SHOW ? stand : null} />)}
    </section>
  )
}

function Panel({ f, stand }: { f: Float; stand: Float['zone'] | null }) {
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
  return (
    <section className="fq-nfloat" data-float-id={f.id} aria-label={`Floating ${name}`}
      style={{ ['--fh' as string]: Math.round(f.h) + 'px' }}>
      <header className="fl-head">
        <span className="zc-name">{name}</span>{says && <FromPost f={f} says={says} />}<span className="grow" />
        {/* The conversation's place is not closed from here: on the desktop
            that would take what the column holds with it. */}
        {!conv && <span className="fl-tools">
          <button className="fl-btn fl-close" onClick={() => workspace.edit((x) => closeFloat(x, f.id), 'Closed the floating surface.')} aria-label="Close floating surface" title="Close">×</button>
        </span>}
      </header>
      <div ref={at} className="fl-body fq-float-body">
        {conv && stand ? <PlacedZone z={stand} why="Split it on a wider screen" /> : <FloatBody f={f} r={r} conversation={<ConvStub />} />}
      </div>
    </section>
  )
}
