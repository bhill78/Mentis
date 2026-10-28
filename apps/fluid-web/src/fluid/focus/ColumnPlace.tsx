/* THE COLUMN AS A PLACE (types.ts). Where the conversation column is drawn,
 * at its width and with its boundary, any content can be shown: the
 * conversation, by default, or what was swapped into the primary place
 * while the conversation went to a section or a float. A workspace zone or
 * one object is drawn here by the same zone body every place uses
 * (`PlacedZone`), so it looks and behaves as it does docked or floating.
 * Each page has its own: the column shows the page shown's (page.ts). */

import { useLayoutEffect, useRef, useState } from 'react'
import type { Arr } from '../workspace/place'
import { zones, type Rect, type Zone } from '../workspace/tree'
import type { ZoneCtl } from '../workspace/TreeView'
import { WorkspaceZone } from '../workspace/Zones'
import { useNarrow } from '../frame/narrow'
import { Mount } from './hosts'
import { columnEmpty, columnZone, minimizedOf, primaryOf } from './model'
import PageLauncher from './Launcher'
import { CONVERSATION_ID, CONVERSATION_SHOW } from './types'
import { useShownView } from './page'

/** Is the conversation somewhere other than the column (minimized too)? */
function convElsewhere(a: Arr): boolean {
  const f = a.focus
  if (!f?.column || f.column.show === CONVERSATION_SHOW) return false
  return !!f.minimized || zones(a.tree).some((z) => z.show === CONVERSATION_SHOW) || !!f.floats?.some((x) => x.zone.show === CONVERSATION_SHOW)
}

export default function ColumnPlace({ width, conversation = null, name = '' }: { width: 'wide' | 'narrow' | 'rail'; conversation?: string | null; name?: string }) {
  const { page, view: a } = useShownView()
  /* NARROW (narrowView.ts): the one column is the conversation's, as it was
     before Fluid Focus, wherever the arrangement puts it; what the column
     holds is shown in the conversation's place instead. Nothing is moved. */
  const narrow = useNarrow()
  /* MINIMIZED (model.ts minimize): the conversation is in no place, at any
     width. The launcher waits where the column was; the column's place shows
     what else it holds, or nothing, and the page takes the room. */
  const minimized = !!minimizedOf(a)
  const launcher = minimized ? <PageLauncher conversation={conversation} name={name} /> : null
  /* The conversation went to a section or a float and nothing came here in
     its place: the column is empty, drawn at no width. */
  if (!minimized && !narrow && columnEmpty(a)) return null
  /* What the column shows; the conversation when nothing else holds it, so
     an arrangement that lost track of it never loses the conversation. */
  const z = (minimized || !narrow) && convElsewhere(a) ? a.focus!.column! : null
  if (minimized && !z) return launcher
  /* the column's place is primary when what it shows is */
  const primary = !narrow && primaryOf(a) === (z ?? columnZone(a)).id ? ' primary' : ''
  if (!z) return <Mount id={CONVERSATION_ID} className={'fq-col' + primary} />
  return (
    <>
      {launcher}
      <div className={'fq-mount fq-col' + primary}>
        <section className={'fx-conv fx-panel fx-' + width + ' fq-col-zone'} id="conv" aria-label={z.name ?? 'Primary'} data-content={z.id}>
          <PlacedZone z={z} page={page} />
        </section>
      </div>
    </>
  )
}

/** A place that is not a leaf of the tree: no split, merge or close here. */
export function placeCtl(why: string): ZoneCtl {
  return {
    stacked: false, across: false, canSplitRow: false, canSplitCol: false, whyNoSplitRow: why, whyNoSplitCol: why,
    canMerge: false, canClose: false, split: () => {}, merge: () => {}, close: () => {}, closing: false, widen: () => false, docked: false, fit: false, toggleFit: () => {},
  }
}

/** One content of page `page` drawn by the zone body, sized to the element
 *  that holds it. */
export function PlacedZone({ z, page, why = 'Swap it into a section to split it' }: { z: Zone; page: string; why?: string }) {
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
      <WorkspaceZone z={z} r={r} ctl={placeCtl(why)} page={page} first={false} />
    </div>
  )
}
