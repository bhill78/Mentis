/* QUIET CHAT'S SHELL. ONE PACKAGE A ROUND WRITES THIS FILE -- P0 in round
   zero, R in round five -- and after that commit a package changes the body of
   the modules it owns and never this one. What is here is the address, who is
   writing, the notice, the two reads every region needs, and where each
   package mounts.

   THE DOCUMENT SCROLLS AT EVERY WIDTH. layout.css gives #qc-stream no overflow
   of its own, so there is no desktop stream scroller and never was one after
   the seam commit's own correction: what survives leaving, a reload and a new
   session is therefore a POST AND ITS OFFSET, not a scroll position
   (`reader/scroll.ts`). The composer is still mounted ONCE, into the dock
   below the stream rather than by the Flow and the Thread, so it is outside
   what scrolls; the page doing the reading says what it is for, through
   `setCompose`, and the reader that owns both now owns that pair together
   (`reader/ConversationReader.tsx`).

   WHERE ROUND FIVE MOUNTS. One WorkspaceBookmarkProvider per origin
   conversation, above everything that reads a bookmark identity -- `useRail`
   included (F4); one QuietNavigationProvider, so every link inside the reading
   knows which origin and Page it belongs to (F6); one `useWorkspaceRuntime`,
   which is the ONLY entrance to the Holder and the only nav adapter (there is
   deliberately no second entrance effect beside it); and one WorkspaceRoom
   with its four fixed slots.

   THE BROWSER HASH IS QUIET'S ONLY DESTINATION HISTORY (F8), AND ONE EFFECT
   WRITES IT. Everything in Quiet that wants to go somewhere -- a Page
   selected, a post read inside the working area, a link out of it, a message
   posted, a post chosen in a thread -- reports one destination intent through
   the bookmark's `intend`, and `ConversationView`'s location effect is what
   turns the latest intent into one hash entry. Nothing else assigns
   `window.location.hash`. A link the reader follows is still the browser
   writing the hash, which is not Quiet writing it; and applying an address is
   guarded (`replayExternal`) so the hash and Fluid's nav cannot echo each
   other.

   Everything a package may change is behind its own module: see contract.ts
   for the list and `tests/quiet_seam_unit.mjs` for the check that each one
   still exports what it declares. */
import './layout.css'
import './type.css'
import { useCallback, useEffect, useRef, useState } from 'react'
import { readAddress } from '../address'
import { useApi, usePulse, type Conversation, type ConversationList, type Id,
  type ParticipantsList } from '../api'
import { arrive, READABLE, replayExternal } from '../fluid/nav'
import Chrome, { ConversationNav, Welcome } from './chrome/Chrome'
import Heading from './chrome/Heading'
import type { ConversationsRead } from './contract'
import { CONVERSATION_PAGE, isResumeEntry, readQuietLocation, writeQuietLocation } from './pages/location'
import PageArrows from './pages/PageArrows'
import PageStrip from './pages/PageStrip'
import WhoFilter from './filter/WhoFilter'
import MediaLayer from './media/MediaLayer'
import ConversationReader from './reader/ConversationReader'
import { QuietNavigationProvider } from './reader/navigation'
import { knownPage, resumeReading } from './reader/scroll'
import Rail, { RailTools, useRail } from './rail/Rail'
import Surface from './surface/Surface'
import { useWorkspaceBookmark, WorkspaceBookmarkProvider } from './workspace/bookmarks'
import { useWorkspaceRuntime } from './workspace/runtime'
import WorkingArea from './workspace/WorkingArea'
import WorkspaceRoom from './workspace/WorkspaceRoom'
import type { QuietNavigate, ReadingBookmark, RoomBookmark } from './workspace/types'

/** The address, and the Quiet destination in it. One listener, two readings of
 *  the same hash: `readAddress` is the shared one every region already used,
 *  and `readQuietLocation` adds the `/qpage/<id>` suffix after it (F6). */
function useAddress() {
  const read = () => ({ address: readAddress(), at: readQuietLocation() })
  const [here, setHere] = useState(read)
  useEffect(() => {
    const changed = () => setHere(read())
    window.addEventListener('hashchange', changed)
    return () => window.removeEventListener('hashchange', changed)
  }, [])
  return here
}

export default function QuietChat() {
  usePulse()
  const { address, at } = useAddress()
  const read = useApi<ConversationList>('/api/conversations')
  const people = useApi<ParticipantsList>('/api/participants')
  // Match the existing interface's author selection; never offer impersonation.
  const me = people.data?.participants.find((p) => p.about === 'the owner') ?? people.data?.participants[0]
  const [notice, setNotice] = useState('')
  const current = address.conversation
  useEffect(() => { document.title = 'Quiet Chat · Mentis' }, [])
  /* READ ONCE, HANDED ON. `useApi` holds its state per reader, so a second
     reader of this path would be a second read of it and a second failure to
     recover from; the shell reads and the packages render. */
  const conversations: ConversationsRead = {
    choices: read.data?.conversations ?? [],
    loaded: !!read.data,
    loading: read.loading,
    error: read.error,
    reload: read.reload,
  }

  return <Surface>
    {/* THE HREF STAYS THE MAIN REGION and the FOCUS goes to the stream: the
        href is what a reader without JavaScript follows, and the stream does
        not exist on the welcome page, while the main region always does. */}
    <a className="qc-skip" href="#qc-reading" onClick={(e) => {
      e.preventDefault()
      ;(document.getElementById('qc-stream') ?? document.getElementById('qc-reading'))?.focus()
    }}>Skip to conversation</a>
    <Chrome conversation={current} conversations={conversations} />
    <div className="qc-notice" role="status">{notice}</div>
    {current ? <ConversationWorkspace key={current} conversation={current} topic={address.topic}
      turn={address.turn} page={at?.page ?? CONVERSATION_PAGE} explicit={!at || !isResumeEntry(at)}
      me={me?.participant ?? null} conversations={conversations} notify={setNotice} />
      : <Welcome conversations={conversations} />}
    <MediaLayer />
  </Surface>
}

interface Place {
  /** the conversation in the address: the ORIGIN, which owns the Holder */
  conversation: Id
  topic: Id | null
  turn: Id | null
  page: string
  /** the address names a topic, a post or a Page, so it is deliberate and
   *  overrides what this browser remembers */
  explicit: boolean
  me: Id | null
  conversations: ConversationsRead
  notify: (text: string) => void
}

/** ONE BOOKMARK PER ORIGIN CONVERSATION, mounted above everything that reads
 *  an identity from it. `useRail` is called by the view below, so the provider
 *  cannot be mounted by that view: a hook in the component that mounts a
 *  provider is not a descendant of it (F4). */
function ConversationWorkspace(place: Place) {
  return <WorkspaceBookmarkProvider originConversation={place.conversation} page={place.page}>
    <ConversationView {...place} />
  </WorkspaceBookmarkProvider>
}

/** A Page with no room of its own: Single chat, at the readable floor. L owns
 *  the roomier initial widths and the controls that change the mode. */
const FIRST_ROOM: RoomBookmark = { mode: 'single', readingPx: READABLE }

function ConversationView({ conversation: origin, topic: addressed, turn: addressedTurn, page,
  explicit, me, conversations, notify }: Place) {
  const bookmark = useWorkspaceBookmark()
  const envelope = bookmark?.envelope ?? null
  /* WHICH CONVERSATION IS BEING READ HERE. The Holder, the Page sequence and
     the address always belong to the origin; a Deep dive Page reads its own
     conversation, and its topics and reply ids are its own. */
  const destination = envelope?.destinations[page]
  const effective = destination?.kind === 'deep-dive' ? destination.conversation : origin
  const facts = useApi<Conversation>(`/api/conversations/${encodeURIComponent(effective)}?batch=0`)
  const { rail, setRail } = useRail()
  /* WHAT THE PARTICIPANT FILTER IS HIDING. The strip is mounted up here, in
     the heading, because it reads the whole conversation; the posts it hides
     are counted where they are drawn -- by the Flow for its page, by the
     Thread for its thread -- and reported back so the strip can say it. Each
     page reads the filter itself (`useWhoFilter`), so the two stay in step
     without this shell holding the reading. */
  const [hidden, setHidden] = useState(0)
  const [readingPost, setReadingPost] = useState<Id | null>(null)

  /* -- THE ONE HOLDER AND NAV ADAPTER (W2 owns its body). No second entrance
     effect is added beside it. */
  const runtime = useWorkspaceRuntime({ originConversation: origin, effectiveConversation: effective, page, readingPost })
  /* IS THE ADDRESSED PAGE ONE THIS BROWSER HAS? true, false, or NOT YET: until
     the runtime has entered the Holder and hydrated its Pages, an absence from
     `runtime.pages` says nothing at all, and the question stays open rather
     than being answered wrongly (`knownPage`, round 5 finding 4). While it is
     open the address is taken at its word -- that is where the reading is
     drawn -- and nothing is said and nothing is rewritten. */
  const known = knownPage(page, runtime.pages, runtime.ready)
  const shown = known === false ? CONVERSATION_PAGE : page
  const intend = bookmark?.intend

  /* -- WHAT WAS BEING READ HERE. Adopted ONCE, on arrival. An explicit address
     is deliberate and adopts nothing, which is also what makes Back and
     Forward land on the entry they name rather than on the latest bookmark. A
     null bookmark means no provider and no identity: memory-only, never a
     fresh arrival to be recorded over.
     `decided` is what the reader waits for: until the question has been
     ANSWERED, nothing is captured, because capturing first would record the
     top of the conversation over the place somebody left.

     THREE ANSWERS, AND ONLY ONE OF THEM WAITS (F10, round 5 finding 2).
     'pending' is the Brain still being read, and that is the only state the
     question stays open in. 'resolved' is a Brain named, and the durable
     envelope is what is resumed from. 'unavailable' -- identity could not be
     read at all, or storage is refused or full -- is a MEMORY-ONLY SESSION,
     and it is decided just as firmly: this session remembers where somebody
     was for as long as the tab lasts, nothing is written under an unknown
     Brain, and the reader is told so once rather than being left with a
     reading that quietly never remembers anything. Waiting on it forever,
     which is what a gate on `brain` alone did, meant the restoration never
     settled and nothing was ever captured, even in memory. */
  const [resumed, setResumed] = useState<ReadingBookmark | null>(null)
  const [decided, setDecided] = useState(false)
  const identity = bookmark?.identity ?? null
  const saved = envelope?.readings[shown] ?? null
  useEffect(() => {
    if (decided) return
    if (explicit || !bookmark) { setDecided(true); return }
    if (identity === 'pending') return
    if (saved) setResumed(saved)
    setDecided(true)
    if (identity === 'unavailable')
      notify('This browser is not remembering your reading place; it is kept until this tab closes.')
  }, [bookmark, identity, decided, explicit, saved, notify])

  /* IT IS AN ARRIVAL'S ANSWER, NOT A STANDING ONE. The moment the address
     changes -- following a link, closing a thread with "Back to conversation",
     posting, a Back into another entry -- what was remembered has been
     answered and is not applied again: otherwise leaving a thread would reopen
     the thread, and "All posts" would put the topic straight back. */
  const here = `${addressed ?? ''}/${addressedTurn ?? ''}/${page}`
  const arrival = useRef(here)
  const left = useRef(false)
  if (here !== arrival.current) left.current = true
  const resume = resumeReading({ topic: addressed, turn: addressedTurn },
    left.current ? null : resumed, explicit)
  const topic = resume.topic
  const turn = resume.turn
  /* A PAGE THIS BROWSER DOES NOT HAVE -- another browser's arrangement, or one
     since closed -- falls back to the conversation VISIBLY. Only once that has
     actually been DECIDED: a Page the runtime has not read yet is not a Page
     that is gone, and saying so early would both mislead the reader and
     rewrite the address they arrived on. */
  useEffect(() => {
    if (known !== false || !intend) return
    notify('That page is not in this browser; showing the conversation.')
    intend({ originConversation: origin, topic: addressed, turn: addressedTurn, page: CONVERSATION_PAGE })
  }, [known, intend, origin, addressed, addressedTurn, notify])

  /* -- THE ONE WRITER OF THE ADDRESS (F8). Nothing else in Quiet assigns
     `window.location.hash`: the Page adapter, the way out of the working area,
     the composer after it posts and the thread's own "Go to post" all report a
     destination intent, and this is what turns the latest one into one hash
     entry. */
  const intent = bookmark?.location
  useEffect(() => {
    if (!intent) return
    const next = writeQuietLocation(intent)
    if (window.location.hash !== next) window.location.hash = next
  }, [intent])

  /* -- THE HASH DRIVES THE ARRANGEMENT, never the other way round (F7/F8).
     One guarded direction per transition: inside `replayExternal` the ordinary
     nav functions report no intent and push no step, so applying an address --
     an arrival, a Back, a Forward -- cannot start the cycle again. The Page is
     validated against this place's own pages inside `arrive`. */
  useEffect(() => {
    replayExternal(() => { arrive(effective, turn, null, { page: shown }) })
  }, [effective, turn, shown])

  /* -- THE ONE WAY OUT OF THE WORKING AREA. Nothing inside it switches the
     conversation where it stands: it asks here, and a conversation that is not
     the one being read leaves the sequence normally rather than carrying the
     origin's Page suffix out with it (F6/F7). It reports an INTENT like
     everything else, so the effect above is still the only writer. */
  const onNavigate: QuietNavigate = useCallback((to) => {
    if (!intend) return
    intend(to.conversation === effective
      ? { originConversation: origin, topic: to.topic ?? null, turn: to.turn ?? null, page: shown }
      : { originConversation: to.conversation, topic: to.topic ?? null, turn: to.turn ?? null, page: CONVERSATION_PAGE })
  }, [intend, effective, origin, shown])

  const room = envelope?.rooms[shown] ?? FIRST_ROOM
  const onRoom = useCallback((next: Partial<RoomBookmark>) => {
    bookmark?.patch({ rooms: { [shown]: next } })
  }, [bookmark, shown])

  const data = facts.data
  const selected = data?.topics.find((t) => t.id === topic)
  const where = Math.max(0, runtime.pages.findIndex((p) => p.id === runtime.page))

  return <QuietNavigationProvider originConversation={origin} effectiveConversation={effective} page={shown}>
    <div className="qc-heading">
      <WhoFilter conversation={effective} facts={data ?? null} hidden={hidden} />
      <Heading name={data?.name ?? null} topic={topic ? selected?.name ?? null : undefined} />
    </div>
    {/* ONE STABLE INSTANCE EACH, in the room's `tools` slot, never two
        conditional mounts and never reparented (F27): the reading state M
        keeps in them has to survive the room being expanded and collapsed,
        and CSS is what moves them. L owns the two slot-passing lines that
        build `tools` and `conversation` for round five; R owns the rest of
        this file. */}
    <WorkspaceRoom originConversation={origin} page={shown} room={room} onRoom={onRoom}
      tools={<>
        <RailTools rail={rail} choose={setRail} />
        <div className="qc-cell-nav"><ConversationNav conversation={origin} conversations={conversations} /></div>
      </>}
      conversation={<div className="qc-work">
        <ConversationReader conversation={effective} originConversation={origin} page={shown}
          topic={topic} turn={turn} me={me} topics={data?.topics ?? []}
          facts={{ data: data ?? null, loading: facts.loading, error: facts.error, reload: facts.reload }}
          missingTopic={!!(data && topic && !selected)} resume={resume} decided={decided}
          notify={notify} report={setHidden} onReadingPost={setReadingPost} />
        {rail && <Rail rail={rail} close={() => setRail(null)} conversation={effective} topic={topic} facts={data ?? null} />}
      </div>}
      working={<WorkingArea originConversation={origin} effectiveConversation={effective}
        page={shown} readingPost={readingPost} onNavigate={onNavigate} />}
      pageControls={<>
        <PageStrip originConversation={origin} pages={runtime.pages} current={runtime.page}
          onSelect={runtime.selectPage} onAdd={runtime.addPage} canAdd={runtime.ready} />
        <PageArrows previous={where > 0 ? runtime.pages[where - 1] : null}
          next={where + 1 < runtime.pages.length ? runtime.pages[where + 1] : null}
          onSelect={runtime.selectPage} />
      </>} />
  </QuietNavigationProvider>
}
