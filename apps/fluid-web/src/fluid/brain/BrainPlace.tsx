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
 * A CONVERSATION OVER THE BRAIN is the real one -- the column the Shell draws
 * once and moves between places (focus/hosts.tsx), with its posts, replies,
 * composer, annotations and the agents at work in it -- floating, or docked
 * as a column at one side, its replies sheet beside it. It is the one the
 * Shell shows: opening another here shows that one, without leaving the
 * Brain. Putting it away keeps it drawn out of sight, so a draft survives;
 * closing it only stops drawing it. Neither touches the Conversation, and
 * agents working in it go on working.
 *
 * Imported lazily by the Shell: nobody who never comes here loads it. */

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import SpaceSurface from '../../surfaces/space/SpaceSurface'
import type { SpaceNode, SpaceRead } from '../../surfaces/space/layout'
import { Mount } from '../focus/hosts'
import { CONVERSATION_ID } from '../focus/types'
import { goHome, kindWord, type BrainDoors } from './address'
import BrainFloat from './BrainFloat'
import BrainObject from './BrainObject'
import {
  CONVERSATION_OVERLAY, closeOver, dockOver, loadOverlays, minimise, openOver, placeOver, saveOverlays, toFront,
  type Id, type Overlay, type Overlays, type Shown,
} from './overlays'
import './brain.css'

const session = () => (typeof sessionStorage === 'undefined' ? null : sessionStorage)

/** The conversation the Shell shows, and how it is drawn here. */
export interface BrainConversation {
  id: Id | null
  name: string | null
  /** show this one instead, staying in the Brain */
  show: (id: Id) => void
  /** the column, drawn once (a `Hosted` portal); placed here by a `Mount` */
  column: () => ReactNode
  /** its replies sheet, while one is open */
  thread: ReactNode | null
}

export default function BrainPlace({ doors, conversation }: { doors: BrainDoors; conversation?: BrainConversation }) {
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

  /* -- the conversation over the Brain ------------------------------------- */
  const convOver = list.find((o) => o.id === CONVERSATION_OVERLAY)
  const convShows = convOver?.shows.type === 'conversation' ? convOver.shows : null
  const openConversation = (id: Id) => {
    conversation?.show(id)
    open({ type: 'conversation', conversation: id, title: nameOf(id) ?? (id === conversation?.id ? conversation.name : null) ?? 'Conversation' })
  }
  /* Back in this tab after a reload, the conversation that was over the
     Brain is shown again; from then on the surface follows whichever the
     Shell shows (a post opened inside it may lead to another). */
  const restored = useRef(false)
  useEffect(() => {
    if (!conversation || !convShows) { restored.current = true; return }
    if (!restored.current) {
      restored.current = true
      if (convShows.conversation !== conversation.id) { conversation.show(convShows.conversation); return }
    }
    const id = conversation.id
    const title = (id && (conversation.name || nameOf(id))) || convShows.title
    if (id && (id !== convShows.conversation || title !== convShows.title))
      setList((l) => l.map((o) => (o.id === CONVERSATION_OVERLAY ? { ...o, shows: { type: 'conversation', conversation: id, title } } : o)))
  }, [conversation?.id, conversation?.name, convShows, nameOf])

  const shown = list.filter((o) => !o.min)
  const away = list.filter((o) => o.min)
  const dockedSide = convOver && !convOver.min ? convOver.dock : undefined
  return (
    <SpaceSurface onRead={setRead} onOpen={(n) => open(entryOf(n))}>
      <div className="fq-floats bz-layer" ref={layer} data-docked={dockedSide}>
        {/* Drawn while it is over the Brain at all, put away included: its
            draft and scroll are kept until it is closed. */}
        {convOver && conversation?.id && conversation.column()}
        {shown.map((o, i) => (
          <OverFloat key={o.id} o={o} front={i === shown.length - 1} room={room} setList={setList}
            nameOf={nameOf} doors={doors} onOpenEntry={openEntry} conversation={conversation}
            onOpenConversation={conversation ? openConversation : undefined} />
        ))}
        <div className="bz-tray" role="group" aria-label="Put away over the Brain">
          {conversation?.id && !convOver && (
            <button type="button" className="bz-tray-item bz-tray-open" title={`Open ${conversation.name ?? 'the conversation'} over the Brain`}
              onClick={() => openConversation(conversation.id!)}>
              <span className="bz-tray-kind">conversation</span>
              <span className="bz-tray-name">{conversation.name ?? 'Conversation'}</span>
            </button>
          )}
          {away.map((o) => (
            <button key={o.id} type="button" className="bz-tray-item" title={`Bring back ${o.shows.title}`}
              onClick={() => setList((l) => minimise(l, o.id, false))}>
              <span className="bz-tray-kind">{o.shows.type === 'conversation' ? 'conversation' : kindWord(o.shows)}</span>
              <span className="bz-tray-name">{o.shows.title}</span>
            </button>
          ))}
        </div>
      </div>
    </SpaceSurface>
  )
}

function OverFloat({ o, front, room, setList, nameOf, doors, onOpenEntry, conversation, onOpenConversation }: {
  o: Overlay; front: boolean; room: { w: number; h: number }
  setList: (fn: (l: Overlays) => Overlays) => void
  nameOf: (c: string | null) => string | null
  doors: BrainDoors
  onOpenEntry: (entry: string) => void
  conversation?: BrainConversation
  onOpenConversation?: (id: Id) => void
}) {
  const s = o.shows
  const common = {
    o, front, room, name: s.title,
    onFront: () => setList((l) => toFront(l, o.id)),
    onPlace: (r: { x: number; y: number; w: number; h: number }) => setList((l) => placeOver(l, o.id, r)),
    onMin: () => setList((l) => minimise(l, o.id)),
    onClose: () => setList((l) => closeOver(l, o.id)),
  }
  if (s.type === 'conversation') {
    const dock = (side: 'left' | 'right' | null) => setList((l) => dockOver(l, o.id, side))
    return (
      <BrainFloat {...common} bodyClass="fq-float-body bz-conv-body"
        tools={o.dock
          ? <button className="fl-btn" onClick={() => dock(null)} aria-label="Float it" title="Float it over the Brain">⧉</button>
          : <>
              <button className="fl-btn" onClick={() => dock('left')} aria-label="Dock as a column at the left" title="Dock as a column at the left">⇤</button>
              <button className="fl-btn" onClick={() => dock('right')} aria-label="Dock as a column at the right" title="Dock as a column at the right">⇥</button>
            </>}
        head={<button className="fl-from" title="Leave the Brain for this conversation" onClick={() => doors.openConversation(s.conversation)}>Open</button>}>
        {conversation?.id === s.conversation ? <Mount id={CONVERSATION_ID} /> : <div className="fw-pending" aria-busy="true" />}
        {conversation?.thread && (
          <section className="fx-thread fx-panel bz-thread" aria-label="replies">
            <div className="fx-thread-inner">{conversation.thread}</div>
          </section>
        )}
      </BrainFloat>
    )
  }
  const conversationName = nameOf(s.kind === 'conversation' ? s.entry : s.conversation)
  const home = { entry: s.entry, kind: s.kind, conversation: s.conversation }
  const where = s.kind === 'conversation' ? s.entry : s.conversation
  return (
    <BrainFloat {...common}>
      <BrainObject shows={s} conversationName={conversationName} onOpenEntry={onOpenEntry}
        onGoHome={where ? () => goHome(home, doors) : undefined}
        onOpenConversation={where && onOpenConversation ? () => onOpenConversation(where) : undefined} />
    </BrainFloat>
  )
}
