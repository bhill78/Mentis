/* THE COLUMN AS A PLACE (types.ts). Where the conversation column is drawn,
 * at its width and with its boundary, any content can be shown: the
 * conversation, by default, or what was swapped into the primary place
 * while the conversation went to a section or a float. A workspace zone or
 * one object is drawn here by the same zone body every place uses
 * (`PlacedZone`), so it looks and behaves as it does docked or floating. */

import { useLayoutEffect, useRef, useState } from 'react'
import { useArr } from '../workspace/place'
import { zones, type Rect, type Zone } from '../workspace/tree'
import type { ZoneCtl } from '../workspace/TreeView'
import { WorkspaceZone } from '../workspace/Zones'
import { Mount } from './hosts'
import { columnZone, primaryOf } from './model'
import { CONVERSATION_ID, CONVERSATION_SHOW, type FocusArr } from './types'

/** Is the conversation somewhere other than the column? */
type WithFocus = ReturnType<typeof useArr> & { focus?: FocusArr }
function convElsewhere(a: WithFocus): boolean {
  const f = a.focus
  if (!f?.column || f.column.show === CONVERSATION_SHOW) return false
  return zones(a.tree).some((z) => z.show === CONVERSATION_SHOW) || !!f.floats?.some((x) => x.zone.show === CONVERSATION_SHOW)
}

export default function ColumnPlace({ width }: { width: 'wide' | 'narrow' | 'rail' }) {
  const a: WithFocus = useArr()
  /* What the column shows; the conversation when nothing else holds it, so
     an arrangement that lost track of it never loses the conversation. */
  const z = convElsewhere(a) ? a.focus!.column! : null
  /* the column's place is primary when what it shows is */
  const primary = primaryOf(a) === (z ?? columnZone(a)).id ? ' primary' : ''
  if (!z) return <Mount id={CONVERSATION_ID} className={'fq-col' + primary} />
  return (
    <div className={'fq-mount fq-col' + primary}>
      <section className={'fx-conv fx-panel fx-' + width + ' fq-col-zone'} id="conv" aria-label={z.name ?? 'Primary'} data-content={z.id}>
        <PlacedZone z={z} />
      </section>
    </div>
  )
}

/** A place that is not a leaf of the tree: no split, merge or close here. */
export function placeCtl(why: string): ZoneCtl {
  return {
    stacked: false, across: false, canSplitRow: false, canSplitCol: false, whyNoSplitRow: why, whyNoSplitCol: why,
    canMerge: false, canClose: false, split: () => {}, merge: () => {}, close: () => {}, closing: false, widen: () => false, docked: false,
  }
}

/** One content drawn by the zone body, sized to the element that holds it. */
export function PlacedZone({ z, why = 'Swap it into a section to split it' }: { z: Zone; why?: string }) {
  const at = useRef<HTMLDivElement | null>(null)
  const [r, setR] = useState<Rect>({ x: 0, y: 0, w: 480, h: 400 })
  useLayoutEffect(() => {
    const el = at.current
    if (!el) return
    const read = () => { const b = el.getBoundingClientRect(); setR((o) => (Math.round(o.w) === Math.round(b.width) && Math.round(o.h) === Math.round(b.height) ? o : { x: 0, y: 0, w: b.width, h: b.height })) }
    read()
    const ro = new ResizeObserver(read)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  return (
    <div ref={at} className="fq-placed">
      <WorkspaceZone z={z} r={r} ctl={placeCtl(why)} page="this-post" first={false} />
    </div>
  )
}
