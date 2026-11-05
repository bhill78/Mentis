import { useEffect, useRef, useState } from 'react'
import { readAddress } from '../address'
import { ago, post, useApi, usePulse, type Activity, type Conversation,
  type ConversationList, type Id, type Part, type ParticipantsList, type Turn } from '../api'
import { Prose } from '../prose'
import { conversationPath, flowTurns, href, message, postingBody,
  type Page, type PostingAction, type ThreadLocation, type ThreadRead } from './model'
import './quiet.css'

type Draft = { text: string; action: PostingAction; op: string }
type SetDraft = (draft: Draft, ifOp?: string) => void
const newDraft = (): Draft => ({ text: '', action: 'ask-mentis', op: crypto.randomUUID() })

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
  const conversations = useApi<ConversationList>('/api/conversations')
  const people = useApi<ParticipantsList>('/api/participants')
  // Match the existing interface's author selection; never offer impersonation.
  const me = people.data?.participants.find((p) => p.about === 'the owner') ?? people.data?.participants[0]
  const [navigation, setNavigation] = useState(false)
  const [query, setQuery] = useState('')
  const [drafts, setDrafts] = useState<Record<string, Draft>>({})
  const [notice, setNotice] = useState('')
  const current = address.conversation
  useEffect(() => { setNavigation(false) }, [current])
  useEffect(() => {
    if (!navigation) return
    const close = (e: KeyboardEvent) => { if (e.key === 'Escape') setNavigation(false) }
    window.addEventListener('keydown', close)
    return () => window.removeEventListener('keydown', close)
  }, [navigation])
  useEffect(() => { document.title = 'Quiet Chat · Mentis' }, [])
  const choices = conversations.data?.conversations ?? []

  return <div className="qc">
    <a className="qc-skip" href="#qc-reading" onClick={(e) => {
      e.preventDefault()
      document.getElementById('qc-reading')?.focus()
    }}>Skip to conversation</a>
    <header className="qc-global">
      <button className="qc-brand" aria-expanded={navigation} aria-controls="qc-conversations"
        onClick={() => setNavigation(!navigation)}>MENTIS <span> / Quiet Chat</span> <span aria-hidden="true">⌄</span></button>
      <a className="qc-fluid" href="/fluid">Open Fluid ↗</a>
    </header>
    {navigation && <nav className="qc-navigation" id="qc-conversations" aria-label="Conversations">
      <div className="qc-nav-heading"><h2>Conversations</h2><button onClick={() => setNavigation(false)} aria-label="Close conversations">×</button></div>
      <input autoFocus type="search" aria-label="Find a conversation" placeholder="Find a conversation…"
        value={query} onChange={(e) => setQuery(e.target.value)} />
      <ReadState loading={conversations.loading} error={conversations.error} reload={conversations.reload} />
      {choices.filter((c) => (c.name + ' ' + c.about).toLowerCase().includes(query.toLowerCase())).map((c) =>
        <a key={c.id} href={href(c.id)} aria-current={c.id === current ? 'page' : undefined}>
          <strong>{c.name}</strong><span>{c.about || `${c.turns} posts · ${c.topics.length} topics`}</span>
          {!!c.live_executions && <small>{c.live_executions} running</small>}
        </a>)}
      {!choices.length && conversations.data && <p>No conversations yet. Create one in Fluid.</p>}
      {!!choices.length && !choices.some((c) => (c.name + ' ' + c.about).toLowerCase().includes(query.toLowerCase())) && <p>No matching conversations.</p>}
    </nav>}
    <div className="qc-notice" role="status">{notice}</div>
    {current ? <ConversationView key={current} conversation={current} topic={address.topic} turn={address.turn}
      me={me?.participant ?? null} drafts={drafts} setDrafts={setDrafts} notify={setNotice} />
      : <main className="qc-welcome" id="qc-reading" tabIndex={-1}>
        <p className="qc-eyebrow">A little room to think</p><h1>Quiet Chat</h1>
        <p>Pick a conversation. Follow a thought.</p>
        <ReadState loading={conversations.loading} error={conversations.error} reload={conversations.reload} />
        <nav aria-label="Choose a conversation">{choices.map((c) => <a key={c.id} href={href(c.id)}>
          <strong>{c.name}</strong><span>{c.about || `${c.turns} posts · ${c.topics.length} topics`}</span>
        </a>)}</nav>
      </main>}
  </div>
}

function ReadState({ loading, error, reload }: { loading: boolean; error: string | null; reload: () => void }) {
  return <>{loading && <p className="qc-muted" role="status">Reading…</p>}
    {error && <p role="alert" className="qc-error">{error} <button onClick={reload}>Try again</button></p>}</>
}

function ConversationView({ conversation, topic, turn, me, drafts, setDrafts, notify }: {
  conversation: Id; topic: Id | null; turn: Id | null; me: Id | null
  drafts: Record<string, Draft>; setDrafts: React.Dispatch<React.SetStateAction<Record<string, Draft>>>; notify: (text: string) => void
}) {
  const facts = useApi<Conversation>(`/api/conversations/${encodeURIComponent(conversation)}?batch=0`)
  const [rail, setRail] = useState<'topics' | 'brief' | 'activity' | null>('topics')
  const [revision, setRevision] = useState(0)
  const data = facts.data
  const selected = data?.topics.find((t) => t.id === topic)
  const draftKey = `${conversation}/${topic ?? ''}/${turn ?? ''}`
  const draft = drafts[draftKey] ?? newDraft()
  const setDraft: SetDraft = (next, ifOp) => setDrafts((all) =>
    ifOp && all[draftKey]?.op !== ifOp ? all : { ...all, [draftKey]: next })
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
      <div><p className="qc-eyebrow">Conversation</p><h1>{data?.name ?? 'Opening conversation…'}</h1>
        {topic && <p className="qc-focus">{selected ? `# ${selected.name}` : 'Opening topic…'}</p>}</div>
      <nav aria-label="Conversation tools">{(['topics', 'brief', 'activity'] as const).map((item) =>
        <button key={item} aria-expanded={rail === item} aria-controls="qc-margin"
          onClick={() => setRail(rail === item ? null : item)}>{item[0].toUpperCase() + item.slice(1)}</button>)}</nav>
    </div>
    <div className={'qc-work ' + (rail ? 'qc-with-margin' : '')}>
      <main id="qc-reading" className="qc-reading" tabIndex={-1}>
        <ReadState loading={!data && facts.loading} error={facts.error} reload={facts.reload} />
        {data && topic && !selected ? <p role="alert">This topic is not in this conversation. <a href={href(conversation)}>Show all posts</a></p>
          : data && (turn ? <Thread key={`${conversation}/${turn}`} conversation={conversation} topic={topic} target={turn}
            topics={data.topics} me={me} draft={draft} setDraft={setDraft} wrote={wrote} />
            : <Flow key={`${topic ?? ''}/${revision}`} conversation={conversation} topic={topic} topics={data.topics}
              me={me} draft={draft} setDraft={setDraft} wrote={wrote} />)}
      </main>
      {rail && <aside id="qc-margin" className="qc-margin" aria-label={rail}>
        <div className="qc-nav-heading"><h2>{rail[0].toUpperCase() + rail.slice(1)}</h2>
          <button aria-label="Close margin" onClick={() => setRail(null)}>×</button></div>
        {rail === 'topics' && <nav aria-label="Topics">
          <a href={href(conversation)} aria-current={!topic ? 'page' : undefined}><strong>All posts</strong><span>{data?.turns_total ?? '…'} posts in this conversation</span></a>
          {data?.topics.map((t) => <a key={t.id} href={href(conversation, t.id)} aria-current={t.id === topic ? 'page' : undefined}>
            <strong># {t.name}</strong><span>{t.about || `${t.turns} posts filed here`}</span></a>)}
          {data && !data.topics.length && <p>No topics in this conversation yet.</p>}
        </nav>}
        {rail === 'brief' && <><p>{data?.about || 'This conversation has no description.'}</p>
          <h3>People here</h3><p>{data?.participants.map((p) => p.alias).join(', ')}</p></>}
        {rail === 'activity' && <ActivitySummary conversation={conversation} topic={topic} />}
      </aside>}
    </div>
  </>
}

function Flow({ conversation, topic, topics, me, draft, setDraft, wrote }: {
  conversation: Id; topic: Id | null; topics: Conversation['topics']; me: Id | null
  draft: Draft; setDraft: SetDraft; wrote: (id: Id) => void
}) {
  const [page, setPage] = useState<Page>({})
  return <FlowPage key={JSON.stringify(page)} {...{ conversation, topic, topics, me, draft, setDraft, wrote, page }}
    move={(next) => { setPage(next); document.getElementById('qc-reading')?.scrollTo(0, 0) }} />
}

function FlowPage({ conversation, topic, topics, me, draft, setDraft, wrote, page, move }: {
  conversation: Id; topic: Id | null; topics: Conversation['topics']; me: Id | null
  draft: Draft; setDraft: SetDraft; wrote: (id: Id) => void; page: Page; move: (page: Page) => void
}) {
  const read = useApi<Conversation>(conversationPath(conversation, topic, page))
  const batch = read.data?.batch
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
    {read.data && <Composer {...{ conversation, topic, me, draft, setDraft }} reply={null} onPosted={wrote} />}
  </>
}

function Thread({ conversation, topic, target, topics, me, draft, setDraft, wrote }: {
  conversation: Id; topic: Id | null; target: Id; topics: Conversation['topics']; me: Id | null
  draft: Draft; setDraft: SetDraft; wrote: (id: Id) => void
}) {
  const [replyId, setReplyId] = useState(target)
  const location = useApi<ThreadLocation>(`/api/turns/${encodeURIComponent(target)}`)
  const root = location.data?.inspector.root
  const thread = useApi<ThreadRead>(root ? `/api/conversations/${encodeURIComponent(conversation)}/thread/${encodeURIComponent(root)}` : null)
  const data = thread.data
  const rows = data ? [data.turn, ...data.replies] : []
  const reply = rows.find((p) => p.id === replyId)
  const index = rows.findIndex((p) => p.id === target)
  useEffect(() => {
    if (!data) return
    document.getElementById(`qc-post-${target}`)?.scrollIntoView({ block: 'start' })
  }, [data, target])
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
    <ReadState loading={location.loading || thread.loading} error={location.error || thread.error}
      reload={() => { location.reload(); thread.reload() }} />
    {location.data && !root && <p role="alert">This post has no thread in this conversation.</p>}
    {rows.map((p) => <Post key={p.id} turn={p} {...{ conversation, topic, topics }} inThread selected={p.id === replyId}
      onReply={() => {
        if (replyId !== p.id) setDraft({ ...draft, op: crypto.randomUUID() })
        setReplyId(p.id)
        requestAnimationFrame(() => document.getElementById('qc-compose')?.focus())
      }} />)}
    {data && !reply && <p role="alert">The requested post is not in this thread.</p>}
    {reply && <Composer {...{ conversation, topic, me, draft, setDraft }} reply={reply} onPosted={wrote} />}
  </>
}

function Post({ turn, conversation, topic, topics, inThread = false, selected = false, onReply }: {
  turn: Turn; conversation: Id; topic: Id | null; topics: Conversation['topics']; inThread?: boolean; selected?: boolean; onReply?: () => void
}) {
  const home = turn.linked?.home ?? conversation
  const postHref = href(home, home === conversation ? topic : null, turn.id)
  return <article className="qc-post" id={`qc-post-${turn.id}`} aria-label={`Post ${turn.number} by ${turn.author_alias}`} data-selected={selected || undefined}>
    <header><strong>{turn.author_alias}</strong><a href={postHref}>#{turn.number}</a>
      <time dateTime={new Date(turn.at * 1000).toISOString()} title={new Date(turn.at * 1000).toLocaleString()}>{ago(turn.at)}</time>
      {turn.revision && <small>edited</small>}</header>
    {turn.linked && <p className="qc-context">Linked from <a href={href(home, null, turn.id)}>another conversation ↗</a></p>}
    {turn.answering && <p className="qc-context">Replying to <a href={href(home, home === conversation ? topic : null, turn.answering)}>#{turn.answering_number ?? 'post'}</a></p>}
    <div className="qc-body">{turn.deleted ? <p className="qc-muted">This post was deleted.</p>
      : turn.parts.map((part, i) => <PostPart key={i} part={part} scope={`${turn.id}:part:${i}`} />)}</div>
    <footer>
      <a href={postHref} onClick={onReply ? (e) => { e.preventDefault(); onReply() } : undefined}>{inThread ? 'Reply to this post' : turn.thread_replies ? `Open thread · ${turn.thread_replies} replies` : 'Reply'}</a>
      {turn.topics.map((id) => {
        const t = topics.find((t) => t.id === id)
        return t && home === conversation ? <a key={id} href={href(conversation, id)}># {t.name}</a> : null
      })}
    </footer>
  </article>
}

function PostPart({ part, scope }: { part: Part; scope: string }) {
  if (part.type === 'text') return <Prose src={part.text ?? ''} scope={scope} untrusted />
  if (part.type === 'topic_ref' && part.text) return <span>{part.text}</span>
  if (part.artifact?.state === 'held' && part.artifact.url) return <p><a href={part.artifact.url}>{part.alt || part.artifact.name || part.ref} ↗</a></p>
  // Retain authored non-text references without importing Fluid's object surfaces.
  return <p className="qc-context">{part.text || part.alt || part.ref || part.type}</p>
}

function Composer({ conversation, topic, me, reply, draft, setDraft, onPosted }: {
  conversation: Id; topic: Id | null; me: Id | null; reply: Turn | null
  draft: Draft; setDraft: SetDraft; onPosted: (id: Id) => void
}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const submitting = useRef(false)
  const active = useRef(true)
  const latestOp = useRef(draft.op)
  latestOp.current = draft.op
  useEffect(() => {
    active.current = true
    return () => { active.current = false }
  }, [])
  const send = async () => {
    if (!me || !draft.text.trim() || submitting.current) return
    submitting.current = true
    setBusy(true)
    setError(null)
    try {
      const result = await post<{ post: Id }>('/fluid/api/posts', postingBody(draft.text, draft.action, me, conversation, topic, reply, draft.op))
      setDraft(newDraft(), draft.op)
      if (active.current && latestOp.current === draft.op) onPosted(result.post)
    } catch (e) { if (active.current) setError(message(e)) }
    finally { submitting.current = false; if (active.current) setBusy(false) }
  }
  return <form className="qc-composer" onSubmit={(e) => { e.preventDefault(); void send() }}>
    <label htmlFor="qc-compose">{reply ? `Replying to #${reply.number} · ${reply.author_alias}` : 'Continue the conversation'}</label>
    <textarea id="qc-compose" rows={4} placeholder={reply ? 'Write a reply…' : 'A thought, a question, a next step…'}
      value={draft.text} disabled={busy} onChange={(e) => setDraft({ ...draft, text: e.target.value, op: crypto.randomUUID() })}
      onKeyDown={(e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey) && !e.nativeEvent.isComposing) { e.preventDefault(); void send() } }} />
    <div className="qc-compose-actions"><span className="qc-muted">Ctrl / ⌘ Enter to send</span>
      <select aria-label="Posting action" value={draft.action} disabled={busy}
        onChange={(e) => setDraft({ ...draft, action: e.target.value as PostingAction, op: crypto.randomUUID() })}>
        <option value="ask-mentis">Ask Mentis</option><option value="record-only">Post only</option>
      </select><button type="submit" disabled={busy || !me || !draft.text.trim()}>{busy ? 'Sending…' : draft.action === 'ask-mentis' ? 'Ask Mentis ↑' : 'Post ↑'}</button></div>
    {!me && <p className="qc-muted">The author must be available before posting.</p>}
    {error && <p role="alert" className="qc-error">{error} Your draft is still here.</p>}
  </form>
}

function ActivitySummary({ conversation, topic }: { conversation: Id; topic: Id | null }) {
  const read = useApi<Activity>('/api/activity', { runs: true })
  const rows = read.data?.activity.filter((a) => a.has_live_execution && a.conversation === conversation) ?? []
  return <><ReadState loading={read.loading} error={read.error} reload={read.reload} />
    {read.data && !rows.length && <p className="qc-muted">No active agents reported here.</p>}
    {rows.map((a) => <div className="qc-activity" key={a.participant}><strong>{a.alias}</strong>
      {a.runs?.map((run) => <p key={run.run}>{run.words}</p>)}
      {a.working_on?.turn ? <a href={href(conversation, topic, a.working_on.turn)}>Working on #{a.working_on.number ?? 'post'} →</a>
        : <p>{a.working_on_gap || 'The record does not name a post.'}</p>}</div>)}
  </>
}
