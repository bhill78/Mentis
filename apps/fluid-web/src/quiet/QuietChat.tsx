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
import WhoFilter, { filterTurns, useWhoFilter } from './filter/WhoFilter'
import MediaLayer from './media/MediaLayer'
import Margin from './margin/Margin'
import NavigationRail from './navigation/NavigationRail'
import { conversationPath, flowTurns, href, type Page, type ThreadLocation,
  type ThreadRead } from './model'
import ParentHeader from './post/ParentHeader'
import Post from './post/Post'
import Rail, { RailTools, TopicsNav, useRail } from './rail/Rail'
import { ReadState } from './read'
import Surface from './surface/Surface'

/** The document scrolls at every width -- layout.css gives #qc-stream no
 *  overflow of its own -- so calling scrollTo on the stream would succeed
 *  silently without moving anything. */
function resetReading() {
  document.scrollingElement?.scrollTo(0, 0)
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
    <NavigationRail side="left" title="Conversations">
      <ConversationNav conversation={current} conversations={conversations} />
    </NavigationRail>
    <div className="qc-notice" role="status">{notice}</div>
    {current ? <ConversationView key={current} conversation={current} topic={address.topic} turn={address.turn}
      me={me?.participant ?? null} notify={setNotice} />
      : <Welcome conversations={conversations} />}
    <MediaLayer />
  </Surface>
}

function ConversationView({ conversation, topic, turn, me, notify }: {
  conversation: Id; topic: Id | null; turn: Id | null; me: Id | null
  notify: (text: string) => void
}) {
  const facts = useApi<Conversation>(`/api/conversations/${encodeURIComponent(conversation)}?batch=0`)
  const { rail, setRail } = useRail()
  const [revision, setRevision] = useState(0)
  /* WHAT THE DOCK IS COMPOSING, set by whichever page is reading and cleared
     when it goes, so a thread's reply target cannot outlive the thread. */
  const [compose, setCompose] = useState<Compose | null>(null)
  /* WHAT THE PARTICIPANT FILTER IS HIDING. The strip is mounted up here, in
     the heading, because it reads the whole conversation; the posts it hides
     are counted where they are drawn -- by the Flow for its page, by the
     Thread for its thread -- and reported back so the strip can say it. Each
     page reads the filter itself (`useWhoFilter`), so the two stay in step
     without this shell holding the reading. */
  const [hidden, setHidden] = useState(0)
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
    <NavigationRail side="right" title="Topics">
      <ReadState loading={!data && facts.loading} error={facts.error} reload={facts.reload} />
      <TopicsNav conversation={conversation} topic={topic} facts={data ?? null} />
    </NavigationRail>
    <div className="qc-heading">
      <WhoFilter conversation={conversation} facts={data ?? null} hidden={hidden} />
      <Heading name={data?.name ?? null} topic={topic ? selected?.name ?? null : undefined} />
      <RailTools rail={rail} choose={setRail} />
    </div>
    <div className="qc-work">
      <aside className="qc-cell-nav qc-work-left" aria-label="Left workspace margin">
        {rail === 'carried' && <div className="qc-margin"><Margin side="left" /></div>}
      </aside>
      <main id="qc-reading" className="qc-reading" tabIndex={-1}>
        <div id="qc-stream" className="qc-stream" tabIndex={-1}>
          <ReadState loading={!data && facts.loading} error={facts.error} reload={facts.reload} />
          {data && topic && !selected ? <p role="alert">This topic is not in this conversation. <a href={href(conversation)}>Show all posts</a></p>
            : data && (turn ? <Thread key={`${conversation}/${turn}`} conversation={conversation} topic={topic} target={turn}
              topics={data.topics} draft={draft} setDraft={setDraft} setCompose={setCompose} report={setHidden} />
              : <Flow key={`${topic ?? ''}/${revision}`} conversation={conversation} topic={topic} topics={data.topics}
                setCompose={setCompose} report={setHidden} />)}
        </div>
        <div className="qc-dock">
          {compose && <Composer {...{ conversation, topic, me, draft, setDraft }} reply={compose.reply} onPosted={wrote} />}
        </div>
      </main>
      {rail && <Rail rail={rail} close={() => setRail(null)} conversation={conversation} topic={topic} facts={data ?? null} />}
    </div>
  </>
}

/** How many posts the participant filter is hiding here, told to the strip in
 *  the heading. 0 again when the page goes, so a count cannot outlive it. */
type Report = (hidden: number) => void

function Flow({ conversation, topic, topics, setCompose, report }: {
  conversation: Id; topic: Id | null; topics: Topics; setCompose: SetCompose; report: Report
}) {
  const [page, setPage] = useState<Page>({})
  return <FlowPage key={JSON.stringify(page)} {...{ conversation, topic, topics, setCompose, report, page }}
    move={(next) => { setPage(next); resetReading() }} />
}

function FlowPage({ conversation, topic, topics, setCompose, report, page, move }: {
  conversation: Id; topic: Id | null; topics: Topics; setCompose: SetCompose; report: Report
  page: Page; move: (page: Page) => void
}) {
  const read = useApi<Conversation>(conversationPath(conversation, topic, page))
  const batch = read.data?.batch
  const ready = !!read.data
  /* WHOSE POSTS THIS READER IS SHOWING (filter/who.ts). By the post's author
     alone, over the rows this page would otherwise draw -- the paging, the
     empty message and the reads above are untouched, because hiding a voice
     is a reading preference and not a different page of the conversation. */
  const who = useWhoFilter(conversation)
  const rows = read.data ? flowTurns(read.data) : []
  const linked = read.data?.linked ?? []
  const shown = filterTurns(rows, who)
  const shownLinked = filterTurns(linked, who)
  const hiding = (rows.length - shown.length) + (linked.length - shownLinked.length)
  useEffect(() => {
    if (!ready) return
    setCompose({ reply: null })
    return () => setCompose(null)
  }, [ready, setCompose])
  useEffect(() => {
    report(hiding)
    return () => report(0)
  }, [hiding, report])
  return <>
    <ReadState loading={read.loading} error={read.error} reload={read.reload} />
    <nav className="qc-paging" aria-label="Conversation history">
      {!!batch?.older && batch.first !== null && <button onClick={() => move({ before: batch.first! })}>← Older posts ({batch.older})</button>}
      {(page.before !== undefined || page.after !== undefined) && <button onClick={() => move({})}>Latest posts</button>}
    </nav>
    {shown.map((p) => <Post key={p.id} turn={p} {...{ conversation, topic, topics }} />)}
    {shownLinked.map((p) => <Post key={`linked-${p.id}`} turn={p} {...{ conversation, topic, topics }} />)}
    {read.data && !read.data.turns.length && !read.data.linked?.length && <p className="qc-empty">{topic ? 'No posts filed under this topic yet.' : 'The conversation starts here.'}</p>}
    <nav className="qc-paging" aria-label="Newer conversation history">
      {!!batch?.newer && batch.last !== null && <button onClick={() => move({ after: batch.last! })}>Newer posts ({batch.newer}) →</button>}
    </nav>
  </>
}

function Thread({ conversation, topic, target, topics, draft, setDraft, setCompose, report }: {
  conversation: Id; topic: Id | null; target: Id; topics: Topics
  draft: ReturnType<typeof useDraft>['draft']; setDraft: ReturnType<typeof useDraft>['setDraft']
  setCompose: SetCompose; report: Report
}) {
  const [replyId, setReplyId] = useState(target)
  const where = useApi<ThreadLocation>(`/api/turns/${encodeURIComponent(target)}`)
  const root = where.data?.inspector.root
  const thread = useApi<ThreadRead>(root ? `/api/conversations/${encodeURIComponent(conversation)}/thread/${encodeURIComponent(root)}` : null)
  const data = thread.data
  const rows = data ? [data.turn, ...data.replies] : []
  const byId = new Map(rows.map((p) => [p.id, p]))
  const reply = rows.find((p) => p.id === replyId)
  const index = rows.findIndex((p) => p.id === target)
  /* THE FILTER HIDES POSTS, IT DOES NOT SHORTEN THE THREAD. `rows` still has
     every post in it, so "Go to post", Previous/Next, the parent header and
     what the dock is replying to all keep meaning what they meant; only what
     is DRAWN is filtered. */
  const who = useWhoFilter(conversation)
  const shown = filterTurns(rows, who)
  const hiding = rows.length - shown.length
  useEffect(() => {
    report(hiding)
    return () => report(0)
  }, [hiding, report])
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
    {data && <ParentHeader turn={data.turn} conversation={conversation} topic={topic} />}
    {shown.map((p) => <Post key={p.id} turn={p} {...{ conversation, topic, topics }} inThread selected={p.id === replyId}
      answeringAuthor={p.answering ? byId.get(p.answering)?.author_alias ?? null : null}
      onReply={() => {
        if (replyId !== p.id) setDraft({ ...draft, op: crypto.randomUUID() })
        setReplyId(p.id)
        requestAnimationFrame(() => document.getElementById('qc-compose')?.focus())
      }} />)}
    {data && !reply && <p role="alert">The requested post is not in this thread.</p>}
  </>
}
