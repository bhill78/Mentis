/* THE 3D BRAIN, AS ONE OF FLUID'S PLACES (`#/brain/space`, from the Brain
 * menu, as Mark IV had it).
 *
 * The drawing is Mark IV's own (surfaces/space/), carried across unchanged:
 * the field, its choosing, its strands and reach, its options and its chosen
 * card. What Fluid adds sits around it, never in it.
 *
 * THE BRAIN IS THE GROUND, AND STAYS LIVE. Open on a chosen thing (its card,
 * or Enter) opens it in a Fluid surface over the field; several can be open,
 * and they stay while somebody goes on choosing. The layer they float in
 * passes the pointer through wherever no surface is, so the Brain still
 * turns, travels and chooses there. Where they are is this tab's view state
 * (overlays.ts): it changes no conversation's arrangement and no record.
 *
 * Imported lazily by the Shell: nobody who never comes here loads it. */

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import SpaceSurface from '../../surfaces/space/SpaceSurface'
import type { SpaceNode, SpaceRead } from '../../surfaces/space/layout'
import { goHome, kindWord, type BrainDoors } from './address'
import BrainFloat from './BrainFloat'
import BrainObject from './BrainObject'
import { closeOver, loadOverlays, minimise, openOver, placeOver, saveOverlays, toFront, type Overlay, type Overlays, type Shown } from './overlays'
import './brain.css'

const session = () => (typeof sessionStorage === 'undefined' ? null : sessionStorage)

export default function BrainPlace({ doors }: { doors: BrainDoors }) {
  const [list, setList] = useState<Overlays>(() => loadOverlays(session()))
  useEffect(() => { saveOverlays(session(), list) }, [list])
  const [read, setRead] = useState<SpaceRead | null>(null)
  const byId = useMemo(() => new Map((read?.nodes ?? []).map((n) => [n.entry, n])), [read])
  const nameOf = useCallback((c: string | null) => (c && read?.conversations ? read.conversations[c] ?? null : null), [read])

  /* The field the surfaces float over, measured, so a new one opens inside it. */
  const layer = useRef<HTMLDivElement | null>(null)
  const [room, setRoom] = useState({ w: 0, h: 0 })
  useLayoutEffect(() => {
    const el = layer.current
    if (!el) return
    const measure = () => setRoom((r) => (r.w === el.clientWidth && r.h === el.clientHeight ? r : { w: el.clientWidth, h: el.clientHeight }))
    const ro = new ResizeObserver(measure)
    ro.observe(el); measure()
    return () => ro.disconnect()
  }, [])

  const open = useCallback((shows: Shown) => setList((l) => openOver(l, shows, room)), [room])
  const entryOf = (n: SpaceNode): Shown => ({
    type: 'entry', entry: n.entry, kind: n.kind, conversation: n.conversation,
    title: n.summary || (n.deleted ? `a deleted ${kindWord(n)}` : n.entry),
  })
  /* Another entry named inside one already open: as the Brain read it, or,
     where it is not drawn, by its id alone. */
  const openEntry = (entry: string) => {
    const n = byId.get(entry)
    open(n ? entryOf(n) : { type: 'entry', entry, kind: 'entry', conversation: null, title: entry })
  }

  const away = list.filter((o) => o.min)
  return (
    <SpaceSurface onRead={setRead} onOpen={(n) => open(entryOf(n))}>
      <div className="fq-floats bz-layer" ref={layer}>
        {list.filter((o) => !o.min).map((o, i, shown) => (
          <OverFloat key={o.id} o={o} front={i === shown.length - 1} room={room} setList={setList}
            nameOf={nameOf} doors={doors} onOpenEntry={openEntry} />
        ))}
        {away.length > 0 && (
          <div className="bz-tray" role="group" aria-label="Put away over the Brain">
            {away.map((o) => (
              <button key={o.id} type="button" className="bz-tray-item" title={`Bring back ${o.shows.title}`}
                onClick={() => setList((l) => minimise(l, o.id, false))}>
                <span className="bz-tray-kind">{o.shows.type === 'conversation' ? 'conversation' : kindWord(o.shows)}</span>
                <span className="bz-tray-name">{o.shows.title}</span>
              </button>
            ))}
          </div>
        )}
      </div>
    </SpaceSurface>
  )
}

function OverFloat({ o, front, room, setList, nameOf, doors, onOpenEntry }: {
  o: Overlay; front: boolean; room: { w: number; h: number }
  setList: (fn: (l: Overlays) => Overlays) => void
  nameOf: (c: string | null) => string | null
  doors: BrainDoors
  onOpenEntry: (entry: string) => void
}) {
  const s = o.shows
  if (s.type !== 'entry') return null
  const conversationName = nameOf(s.kind === 'conversation' ? s.entry : s.conversation)
  const home = { entry: s.entry, kind: s.kind, conversation: s.conversation }
  const canGo = s.kind === 'conversation' || !!s.conversation
  return (
    <BrainFloat o={o} front={front} room={room} name={s.title}
      onFront={() => setList((l) => toFront(l, o.id))}
      onPlace={(r) => setList((l) => placeOver(l, o.id, r))}
      onMin={() => setList((l) => minimise(l, o.id))}
      onClose={() => setList((l) => closeOver(l, o.id))}>
      <BrainObject shows={s} conversationName={conversationName} onOpenEntry={onOpenEntry}
        onGoHome={canGo ? () => goHome(home, doors) : undefined} />
    </BrainFloat>
  )
}
