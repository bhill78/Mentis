/* THE CONVERSATION COLUMN ON HOME (owner decision D1, #599: "A conversation
 * column on Home. The column should work exactly how it does in a
 * conversation ... From that conversation I should be able to open the new
 * conversation and continue from home.").
 *
 * IT IS THE CONVERSATION COLUMN, not a copy: `ConversationColumn` and its
 * `Composer` (@, #, runtime and model, attachments and drops, formatting,
 * Ask and Record), its selection bar, its compact view at a narrow width,
 * its threads and details, drawn in a zone of Home's arrangement. The zone's
 * width is the column's: below 380 px it is the compact view, as a
 * conversation's dragged boundary makes it.
 *
 * NO SLIVER OF A COLUMN HERE EITHER (the owner's rule, nav.READABLE): a zone
 * narrower than 330 px -- zones may be 240 -- draws it as the rail, and it is
 * the column again as soon as the zone is that wide. Minimized so, it gives
 * its room back: Home draws its zone at the rail's own width at the edge of
 * its row (Home.tsx DOCK). Opening the rail (its ⤢, or its pencil) widens the
 * zone to 330 from the zones beside it in its row, as dragging their divider
 * would, with Undo; where they have not that much to give, or nothing shares
 * its row, a toast says there is no room, and offers the conversation as its
 * own. The arrangement is not otherwise
 * touched: a zone's minimum stays the tree's, and a saved Home loads as it
 * was saved. A zone as wide as Home itself (a phone, where the zones stack)
 * is the reader's whole screen, not a sliver beside others: it stays the
 * column.
 *
 * BEFORE ITS FIRST POST IT IS A NEW CONVERSATION NOT MADE YET: an empty
 * column with the composer, nothing in the record (#562's unnamed
 * conversation, made only when it is needed). Sending makes it, the post goes
 * into it, and it stays here and goes on here. "Open as its own
 * conversation" in its ⋯ (or a post's #N) opens it as any conversation is
 * opened; coming back to Home finds the same one, until "Start another
 * conversation here" empties the column again.
 *
 * Which conversation Home shows is this browser's (localStorage), as where
 * the reader left off is: presentation, not the record. */

import { useEffect, useRef, useState, useSyncExternalStore, type ReactNode } from 'react'
import * as nav from '../nav'
import { store, type Id } from '../store'
import Composer, { type Starting } from '../Composer'
import { workspace } from '../workspace/place'
import { ColumnFrame, ConversationColumn, railPencil } from './Column'
import { useConversation } from './hooks'

const KEY = 'mentis:fluid:home:conversation'
let current: Id | null = (() => { try { return localStorage.getItem(KEY) || null } catch { return null } })()
const heard = new Set<() => void>()

/** The conversation Home's column holds; null: a new one, not made yet. */
export const homeConversation = {
  get: () => current,
  set(id: Id | null) {
    if (id === current) return
    current = id
    try { if (id) localStorage.setItem(KEY, id); else localStorage.removeItem(KEY) } catch { /* this page only */ }
    for (const fn of [...heard]) fn()
  },
  subscribe(fn: () => void) { heard.add(fn); return () => { heard.delete(fn) } },
}
export const useHomeConversation = () => useSyncExternalStore(homeConversation.subscribe, homeConversation.get)

/** The new conversation, before its first post: the column as a new,
 *  unnamed conversation shows it, with nothing yet in the record. */
function NewColumn({ width, start, tools, rail }: { width: nav.ConversationWidth; start: Starting; tools?: ReactNode; rail: Rail }) {
  const scroller = useRef<HTMLDivElement | null>(null)
  return (
    <ColumnFrame title="New conversation" width={width} scroller={scroller} label="conversation"
      tools={width === 'rail' ? rail.tools : tools && <div className="fx-conv-tools">{tools}</div>}
      footer={
        <div className="fx-composer-slot" {...railPencil(width === 'rail', rail.open)}>
          <Composer conversation={null} start={start} replyTo={null} onClearReply={() => {}} />
        </div>
      }>
      <p className="fx-welcome">Nothing here yet. Write the first post below.</p>
    </ColumnFrame>
  )
}

type Rail = { open: () => void; tools: ReactNode }

export const NO_ROOM = 'No room to open it here: the zones beside it are at their least. Widen the window, or merge or close a zone beside it.'

/** The rail's head, down the rail: open it here, then the zone's own tools
 *  as the rail has them (close: a rail is not split), one under another. Where there is no room, the
 *  rail is too narrow to say so: the toast says it, with the conversation
 *  as its own. */
function RailHead({ tools, open }: { tools?: ReactNode; open: () => void }) {
  return (
    <div className="fx-conv-tools fw-home-rail-head held">
      <button className="fx-ctl fw-home-rail-open" aria-label="Open the conversation here"
        title={`Minimized: too narrow to read. Open it here, ${nav.READABLE} px wide, taking the room from the zones beside it`}
        onClick={open}>⤢</button>
      {tools}
    </div>
  )
}

/** Opened from the keyboard, the caret goes on into the column's composer
 *  rather than being lost with the control that opened it. */
export function focusComposer(within: () => Element | null) {
  requestAnimationFrame(() => requestAnimationFrame(() => {
    const was = document.activeElement
    if (was && was !== document.body && was.isConnected) return
    within()?.querySelector<HTMLElement>('.fw-composer-field')?.focus()
  }))
}

export default function HomeColumn({ px, selection, tools, railTools, widen, across, onOpen }: {
  /** the zone's width, which is the column's */
  px: number
  /** make the zone that wide from the zones beside it; false: no room */
  widen?: (px: number) => boolean
  /** the zone is as wide as Home: nothing beside it takes the room */
  across?: boolean
  /** the frame's selection bar, while posts are selected */
  selection?: ReactNode
  /** the zone's own tools (split, merge, close), quiet with the column's */
  tools?: ReactNode
  /** the zone's tools on the rail: no split */
  railTools?: ReactNode
  /** open this conversation as its own (the switcher's way in) */
  onOpen: (id: Id) => void
}) {
  const id = useHomeConversation()
  const conv = useConversation(id)
  const [replyTo, setReplyTo] = useState<Id | null>(null)
  const rail = !across && nav.railPx(Math.round(px))
  const width = rail ? 'rail' : nav.classOf(px)
  const open = () => {
    if (widen?.(nav.READABLE)) { focusComposer(() => document.querySelector('.fw-home-conv')); return }
    nav.toast({ text: NO_ROOM, ...(id ? { action: { label: 'Open it as its own conversation', run: () => onOpen(id) } } : {}) })
  }
  const railed: Rail = { open, tools: <RailHead tools={railTools ?? tools} open={open} /> }
  /* One the record no longer holds (another brain, say) gives way to a new one. */
  useEffect(() => {
    if (!id || store.conversations.has(id)) return
    let live = true
    void store.loadConversations([id]).then(() => { if (live && !store.conversations.has(id)) homeConversation.set(null) }).catch(() => {})
    return () => { live = false }
  }, [id])
  /* Its threads pinned, as in the conversation itself: they are its place's. */
  const provisional = !!conv?.provisional
  useEffect(() => {
    if (id && conv) workspace.enter(id, provisional ? 'unnamed' : 'conversation')
  }, [id, !!conv, provisional])
  useEffect(() => { setReplyTo(null) }, [id])
  /* ON HOME IT IS THE CONVERSATION BEING READ: what opens out of it -- a
     thread, a post's details, About, a post full screen -- belongs to it and
     is drawn on Home (Shell.tsx), from the first press, before any post in
     it has been read. Arriving reads nothing in it; the frame stays on Home. */
  useEffect(() => {
    if (id && nav.snapshot().conversation !== id) nav.enter(id)
  }, [id])
  const start: Starting = {
    create: async (op) => {
      const author = await store.loadMe()
      const got = await store.createConversation(author, op)
      return got.conversation
    },
    made: (c) => homeConversation.set(c),
  }
  if (!id) return <NewColumn width={width} start={start} tools={tools} rail={railed} />
  return (
    <ConversationColumn id={id} name={conv?.name ?? ''} width={width} replyTo={replyTo} setReplyTo={setReplyTo}
      selection={selection} zoneTools={tools} rail={railed}
      home={{ open: () => onOpen(id), fresh: () => homeConversation.set(null) }} />
  )
}
