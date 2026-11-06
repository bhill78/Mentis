/* QUIET CHAT'S SHELL. P0 owns this file and it is FINAL: after the seam
   commit, a package changes the body of the modules it owns and never this
   one. What is here is the address, who is writing, the notice, the two reads
   every region needs, and where each package mounts.

   THE READING COLUMN IS ITS OWN SCROLL CONTAINER above 900px (layout.css),
   and the composer is mounted ONCE into the dock below it rather than by Flow
   and Thread -- so it is outside what scrolls, and no later package has to
   edit a file two of them would own. The page doing the reading says what the
   composer is for, through `setCompose`.

   Everything a package may change is behind its own module: see contract.ts
   for the list and `tests/quiet_seam_unit.mjs` for the check that each one
   still exports what it declares. */
import './layout.css'
import './type.css'
import { useEffect, useState } from 'react'
import { readAddress } from '../address'
import { useApi, usePulse, type Conversation, type ConversationList, type Id,
  type ParticipantsList } from '../api'
import Chrome, { ConversationNav, Welcome } from './chrome/Chrome'
import Heading from './chrome/Heading'
import Composer from './composer/Composer'
import { useDraft } from './composer/drafts'
import type { Compose, ConversationsRead, SetCompose, Topics } from './contract'
import MediaLayer from './media/MediaLayer'
import { conversationPath, flowTurns, href, type Page, type ThreadLocation,
  type ThreadRead } from './model'
import Post from './post/Post'
import Rail, { RailTools, useRail } from './rail/Rail'
import { ReadState } from './read'
import Surface from './surface/Surface'

/** WHICH ELEMENT ACTUALLY SCROLLED, by the same 900px boundary layout.css
 *  uses -- so the two can never disagree. Above it the stream is its own
 *  container; at it and below, the document is what moved, and calling
 *  scrollTo on the stream would succeed silently without moving anything. */
function resetReading() {
  const wide = window.matchMedia('(min-width: 901px)').matches
  const moved = wide ? document.getElementById('qc-stream') : document.scrollingElement
  moved?.scrollTo(0, 0)
}

function useAddress() {
  const [address, setAddress] = useState(() => readAddress())
  useEffect(() => {
    const changed = () => setAddress(readAddress())
    window.addEventListener('hashchange', changed)
    return () => window.removeEventListener('hashchange', changed)
  }, [])
  return address
}

export default function QuietChat() {
  usePulse()
  const address = useAddress()
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
    {current ? <ConversationView key={current} conversation={current} topic={address.topic} turn={address.turn}
      me={me?.participant ?? null} conversations={conversations} notify={setNotice} />
      : <Welcome conversations={conversations} />}
    <MediaLayer />
  </Surface>
}

function ConversationView({ conversation, topic, turn, me, conversations, notify }: {
  conversation: Id; topic: Id | null; turn: Id | null; me: Id | null
  conversations: ConversationsRead; notify: (text: string) => void
}) {
  const facts = useApi<Conversation>(`/api/conversations/${encodeURIComponent(conversation)}?batch=0`)
  const { rail, setRail } = useRail()
  const [revision, setRevision] = useState(0)
  /* WHAT THE DOCK IS COMPOSING, set by whichever page is reading and cleared
     when it goes, so a thread's reply target cannot outlive the thread. */
  const [compose, setCompose] = useState<Compose | null>(null)
  const data = facts.data
  const selected = data?.topics.find((t) => t.id === topic)
  const { draft, setDraft } = useDraft(`${conversation}/${topic ?? ''}/${turn ?? ''}`)
  const wrote = (id: Id) => {
    facts.reload()
    setRevision((n) => n + 1)
    notify(turn ? 'Reply posted.' : 'Message posted.')
    // Return the flow to its latest page; a thread keeps its current reading place.
    if (!turn) location.hash = href(conversation, topic)
    else location.hash = href(conversation, topic, id)
  }
  return <>
    <div className="qc-heading">
      <Heading name={data?.name ?? null} topic={topic ? selected?.name ?? null : undefined} />
      <RailTools rail={rail} choose={setRail} />
    </div>
    <div className="qc-work">
      <div className="qc-cell-nav"><ConversationNav conversation={conversation} conversations={conversations} /></div>
      <main id="qc-reading" className="qc-reading" tabIndex={-1}>
        <div id="qc-stream" className="qc-stream" tabIndex={-1}>
          <ReadState loading={!data && facts.loading} error={facts.error} reload={facts.reload} />
          {data && topic && !selected ? <p role="alert">This topic is not in this conversation. <a href={href(conversation)}>Show all posts</a></p>
            : data && (turn ? <Thread key={`${conversation}/${turn}`} conversation={conversation} topic={topic} target={turn}
              topics={data.topics} draft={draft} setDraft={setDraft} setCompose={setCompose} />
              : <Flow key={`${topic ?? ''}/${revision}`} conversation={conversation} topic={topic} topics={data.topics}
                setCompose={setCompose} />)}
        </div>
        <div className="qc-dock">
          {compose && <Composer {...{ conversation, topic, me, draft, setDraft }} reply={compose.reply} onPosted={wrote} />}
        </div>
      </main>
      {rail && <Rail rail={rail} close={() => setRail(null)} conversation={conversation} topic={topic} facts={data ?? null} />}
    </div>
  </>
}

function Flow({ conversation, topic, topics, setCompose }: {
  conversation: Id; topic: Id | null; topics: Topics; setCompose: SetCompose
}) {
  const [page, setPage] = useState<Page>({})
  return <FlowPage key={JSON.stringify(page)} {...{ conversation, topic, topics, setCompose, page }}
    move={(next) => { setPage(next); resetReading() }} />
}

function FlowPage({ conversation, topic, topics, setCompose, page, move }: {
  conversation: Id; topic: Id | null; topics: Topics; setCompose: SetCompose
  page: Page; move: (page: Page) => void
}) {
  const read = useApi<Conversation>(conversationPath(conversation, topic, page))
  const batch = read.data?.batch
  const ready = !!read.data
  useEffect(() => {
    if (!ready) return
    setCompose({ reply: null })
    return () => setCompose(null)
  }, [ready, setCompose])
  return <>
    <ReadState loading={read.loading} error={read.error} reload={read.reload} />
    <nav className="qc-paging" aria-label="Conversation history">
      {!!batch?.older && batch.first !== null && <button onClick={() => move({ before: batch.first! })}>← Older posts ({batch.older})</button>}
      {(page.before !== undefined || page.after !== undefined) && <button onClick={() => move({})}>Latest posts</button>}
    </nav>
    {read.data && flowTurns(read.data).map((p) => <Post key={p.id} turn={p} {...{ conversation, topic, topics }} />)}
    {read.data?.linked?.map((p) => <Post key={`linked-${p.id}`} turn={p} {...{ conversation, topic, topics }} />)}
    {read.data && !read.data.turns.length && !read.data.linked?.length && <p className="qc-empty">{topic ? 'No posts filed under this topic yet.' : 'The conversation starts here.'}</p>}
    <nav className="qc-paging" aria-label="Newer conversation history">
      {!!batch?.newer && batch.last !== null && <button onClick={() => move({ after: batch.last! })}>Newer posts ({batch.newer}) →</button>}
    </nav>
  </>
}

function Thread({ conversation, topic, target, topics, draft, setDraft, setCompose }: {
  conversation: Id; topic: Id | null; target: Id; topics: Topics
  draft: ReturnType<typeof useDraft>['draft']; setDraft: ReturnType<typeof useDraft>['setDraft']
  setCompose: SetCompose
}) {
  const [replyId, setReplyId] = useState(target)
  const where = useApi<ThreadLocation>(`/api/turns/${encodeURIComponent(target)}`)
  const root = where.data?.inspector.root
  const thread = useApi<ThreadRead>(root ? `/api/conversations/${encodeURIComponent(conversation)}/thread/${encodeURIComponent(root)}` : null)
  const data = thread.data
  const rows = data ? [data.turn, ...data.replies] : []
  const reply = rows.find((p) => p.id === replyId)
  const index = rows.findIndex((p) => p.id === target)
  useEffect(() => {
    if (!data) return
    document.getElementById(`qc-post-${target}`)?.scrollIntoView({ block: 'start' })
  }, [data, target])
  useEffect(() => {
    if (!reply) return
    setCompose({ reply })
    return () => setCompose(null)
  }, [reply, setCompose])
  return <>
    <div className="qc-thread-head"><a href={href(conversation, topic)}>← Back to {topic ? 'topic' : 'conversation'}</a>
      {data && <><h2>Thread #{data.turn.number} <span> · {data.replies_total} replies</span></h2>
        <label>Go to post <select aria-label="Go to post in thread" value={target}
          onChange={(e) => { window.location.hash = href(conversation, topic, e.target.value) }}>
          {rows.map((p) => <option key={p.id} value={p.id}>#{p.number} · {p.author_alias}{p.answering_number ? ` · replying to #${p.answering_number}` : ''}</option>)}
        </select></label>
        <nav aria-label="Thread navigation">
          {index > 0 && <a href={href(conversation, topic, rows[index - 1].id)}>← Previous post</a>}
          {index < rows.length - 1 && <a href={href(conversation, topic, rows[index + 1].id)}>Next post →</a>}
        </nav></>}
    </div>
    <ReadState loading={where.loading || thread.loading} error={where.error || thread.error}
      reload={() => { where.reload(); thread.reload() }} />
    {where.data && !root && <p role="alert">This post has no thread in this conversation.</p>}
    {rows.map((p) => <Post key={p.id} turn={p} {...{ conversation, topic, topics }} inThread selected={p.id === replyId}
      onReply={() => {
        if (replyId !== p.id) setDraft({ ...draft, op: crypto.randomUUID() })
        setReplyId(p.id)
        requestAnimationFrame(() => document.getElementById('qc-compose')?.focus())
      }} />)}
    {data && !reply && <p role="alert">The requested post is not in this thread.</p>}
  </>
}
