/* THE READING ITSELF, AND THE PLACE IT WAS LEFT. Round 5, package R.
 *
 * EXTRACTED, NOT REPLACED. The Flow, the Thread and the reading column come
 * out of the shell into this module with their APIs, their history paging,
 * their draft builder and their composer exactly as they were: one
 * `qc-reading`, one `qc-stream`, one `qc-dock` and one composer, as there has
 * always been. What is NEW here is remembering where somebody was.
 *
 * WHAT IS REMEMBERED, AND WHAT IS NOT. The topic that was filtering the
 * reading, the half of it that was loaded (`model.ts`'s batch cursor, aliased
 * BatchCursor here because `QuietSequencePage` is in view in the same file),
 * the post that was visible and how far down the screen it was, the thread
 * that was open, and the post the composer was answering -- which is a
 * DIFFERENT CHOICE from the post being read, and a restored reply must never
 * quietly answer something else. Unsent words are already outside the tree
 * (`composer/drafts.ts`) and who is writing is already its own store
 * (`filter/who.ts`); neither is copied here.
 *
 * WHEN IT IS WRITTEN. A semantic change -- the topic, the batch, the thread,
 * the post being answered -- at once. Scrolling, coalesced into one write,
 * which the provider flushes when the tab goes. NOTHING while a restore is in
 * flight: a restoration that recorded itself would overwrite what it was
 * restoring.
 *
 * WHEN IT IS PUT BACK, AND WHEN IT IS NOT. Only on an arrival that asked for
 * it (`resumeReading`), only once the Brain is known, and only while nobody
 * has taken over: a restore that becomes possible late carries the arrival it
 * belongs to, and a reader who has scrolled or navigated since keeps the place
 * they are in. Deliberate Older/Newer still returns the reader to the top, and
 * a thread still scrolls to the post it is of -- except when that post's own
 * offset is the thing being restored.
 */
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useApi, type Conversation, type Id, type Turn } from '../../api'
import Composer from '../composer/Composer'
import { useDraft } from '../composer/drafts'
import type { Compose, SetCompose, Topics } from '../contract'
import DeepDiveAction from '../deep-dive/DeepDiveAction'
import { filterTurns, useWhoFilter } from '../filter/WhoFilter'
import { conversationPath, flowTurns, type BatchCursor, type ThreadLocation,
  type ThreadRead } from '../model'
import ParentHeader from '../post/ParentHeader'
import Post from '../post/Post'
import { ReadState } from '../read'
import { useWorkspaceBookmark } from '../workspace/bookmarks'
import type { ReadingAnchor, ReadingMargin, ReadingThread } from '../workspace/types'
import { useQuietHref } from './navigation'
import { captureReadingAnchor, restoreReadingAnchor, SCROLL_KEYS, validReplyTarget,
  type ResumedReading } from './scroll'

/** The document scrolls at every width -- layout.css gives #qc-stream no
 *  overflow of its own -- so calling scrollTo on the stream would succeed
 *  silently without moving anything. */
function resetReading() {
  document.scrollingElement?.scrollTo(0, 0)
}

/** How many posts the participant filter is hiding here, told to the strip in
 *  the heading. 0 again when the page goes, so a count cannot outlive it. */
type Report = (hidden: number) => void

/** A margin nobody has read yet. R writes the whole reading, so it carries
 *  M's half of it through untouched rather than defaulting over it. */
const NO_MARGIN: ReadingMargin = {
  reading: null,
  searchOpen: false,
  query: '',
  scrollByReading: {},
}

/** The one read of the conversation's own facts, made by the shell and handed
 *  on: a second reader of that path would be a second read of it. */
export interface FactsRead {
  data: Conversation | null
  loading: boolean
  error: string | null
  reload: () => void
}

export interface ConversationReaderProps {
  /** the conversation being READ -- a Deep dive's own, on its Page */
  conversation: Id
  /** the conversation that owns the Holder, the Page sequence and the address */
  originConversation: Id
  page: string
  topic: Id | null
  turn: Id | null
  me: Id | null
  topics: Topics
  facts: FactsRead
  /** the address names a topic this conversation does not have */
  missingTopic: boolean
  /** which reading this arrival shows, and what of it to put back */
  resume: ResumedReading
  /** whether the question "is anything being resumed here?" has been answered
   *  yet. Nothing is written down before it has: a capture made while the
   *  Brain was still being read would record the top of the conversation over
   *  the place somebody left. */
  decided: boolean
  notify: (text: string) => void
  report: Report
  /** the post the reader can see, for the working area (changes only) */
  onReadingPost: (post: Id | null) => void
}

export default function ConversationReader({
  conversation, originConversation, page, topic, turn, me, topics, facts, missingTopic,
  resume, decided, notify, report, onReadingPost,
}: ConversationReaderProps): ReactNode {
  const bookmark = useWorkspaceBookmark()
  const quietHref = useQuietHref()
  const stream = useRef<HTMLDivElement>(null)
  /* WHAT THE DOCK IS COMPOSING, set by whichever page is reading and cleared
     when it goes, so a thread's reply target cannot outlive the thread. */
  const [compose, setCompose] = useState<Compose | null>(null)
  const [revision, setRevision] = useState(0)
  const { draft, setDraft } = useDraft(`${conversation}/${topic ?? ''}/${turn ?? ''}`)

  /* -- WHICH HALF OF THE READING IS LOADED. The reader's own paging wins over
     a resumed batch, and a resumed batch applies only to the reading it was
     saved for: posting returns the flow to its latest page, and a different
     topic is a different reading. */
  const flowKey = `${conversation}/${topic ?? ''}/${revision}`
  const [paged, setPaged] = useState<{ key: string; batch: BatchCursor } | null>(null)
  const resumedFlow = resume.from === 'bookmark' && revision === 0 && topic === resume.topic
  const resumedThread = resume.from === 'bookmark' && turn !== null && turn === resume.turn
  const batch: BatchCursor = paged?.key === flowKey
    ? paged.batch
    : resumedFlow ? resume.batch : {}
  const batchKey = JSON.stringify(batch)

  /* -- WHAT IS OPEN IN THE THREAD, reported up by it so the reading can be
     written down in one place. */
  const [opened, setOpened] = useState<ReadingThread | null>(null)
  const thread = turn !== null ? opened : null
  const threadKey = thread ? `${thread.root}/${thread.target}/${thread.replyTo}` : ''

  /* -- THE LAST PLACE EACH READING WAS SEEN AT.
     The flow's own anchor is KEPT WHILE A THREAD IS OPEN, because reading a
     thread does not move the flow. And neither is overwritten by a measurement
     that could not be made: the write that happens as a reading is taken off
     the screen has nothing left to measure, and "nothing is drawn" is not the
     same fact as "they were at the top". */
  const seen = useRef<{ flow: ReadingAnchor | null; thread: ReadingAnchor | null }>({ flow: null, thread: null })
  /* A DIFFERENT READING HAS NO PLACE YET. Paging, changing the topic, posting
     and opening another thread each start one, and the place the one before it
     was at is not theirs to inherit. */
  const was = useRef({ flow: `${flowKey}/${batchKey}`, thread: thread ? `${thread.root}/${thread.target}` : '' })
  const nowFlow = `${flowKey}/${batchKey}`
  const nowThread = thread ? `${thread.root}/${thread.target}` : ''
  if (was.current.flow !== nowFlow) {
    was.current.flow = nowFlow
    seen.current.flow = null
  }
  if (was.current.thread !== nowThread) {
    was.current.thread = nowThread
    seen.current.thread = null
  }
  useEffect(() => {
    if (!resumedFlow) return
    if (resume.flowAnchor) seen.current.flow = resume.flowAnchor
    if (resume.threadAnchor) seen.current.thread = resume.threadAnchor
  }, [resumedFlow, resume.flowAnchor, resume.threadAnchor])

  /* -- TAKING CONTROL. Wheel, touch and the scrolling keys are the reader
     saying where they want to be; a restore that has not happened yet gives
     way to that rather than stealing it back. */
  const taken = useRef(false)
  const took = useCallback(() => { taken.current = true }, [])
  useEffect(() => {
    const keyed = (e: KeyboardEvent) => { if (SCROLL_KEYS.has(e.key)) taken.current = true }
    window.addEventListener('wheel', took, { passive: true })
    window.addEventListener('touchmove', took, { passive: true })
    window.addEventListener('keydown', keyed)
    return () => {
      window.removeEventListener('wheel', took)
      window.removeEventListener('touchmove', took)
      window.removeEventListener('keydown', keyed)
    }
  }, [took])

  /* -- WRITING THE READING DOWN. One place, one shape; the margin's half is
     carried through exactly as M left it. */
  const stored = bookmark?.envelope.readings[page] ?? null
  const latest = useRef({ topic, batch, thread, margin: stored?.margin ?? NO_MARGIN })
  latest.current = { topic, batch, thread, margin: stored?.margin ?? NO_MARGIN }

  const patch = bookmark?.patch
  const restoring = bookmark?.restoring ?? false
  const write = useCallback((coalesce: boolean) => {
    if (!patch || restoring) return
    const now = latest.current
    const inThread = !!now.thread
    const measured = captureReadingAnchor(stream.current)
    if (measured) seen.current = inThread
      ? { ...seen.current, thread: measured }
      : { ...seen.current, flow: measured }
    patch({
      readings: {
        [page]: {
          flow: { topic: now.topic, batch: now.batch, anchor: seen.current.flow },
          thread: now.thread ? { ...now.thread, anchor: seen.current.thread } : null,
          margin: now.margin,
        },
      },
    }, { coalesce })
  }, [patch, restoring, page])

  /* A semantic change is written at once. */
  useEffect(() => { write(false) }, [write, topic, batchKey, threadKey])

  /* Scrolling is one write, not one a frame, and it is also what tells the
     working area which post is being read. */
  const reported = useRef<Id | null>(null)
  const told = useCallback(() => {
    const anchor = captureReadingAnchor(stream.current)
    const post = anchor?.post ?? null
    if (post === reported.current) return
    reported.current = post
    onReadingPost(post)
  }, [onReadingPost])
  useEffect(() => {
    const scrolled = () => { write(true); told() }
    window.addEventListener('scroll', scrolled, { passive: true })
    return () => window.removeEventListener('scroll', scrolled)
  }, [write, told])

  /* LEAVING THIS READING IS THE LAST CHANCE TO WRITE IT. */
  const leaving = useRef<() => void>(() => {})
  leaving.current = () => { write(false); bookmark?.flush() }
  useEffect(() => () => leaving.current(), [])

  /* -- PUTTING THE PLACE BACK. */
  const wanted = resumedThread ? resume.threadAnchor : resumedFlow ? resume.flowAnchor : null
  const [drawn, setDrawn] = useState(false)
  const [back, setBack] = useState(false)
  const settle = bookmark?.settle
  useEffect(() => {
    if (!wanted) return
    if (back || taken.current || !drawn) return
    let live = true
    /* TWO FRAMES: the first lets the rows that have just been drawn lay out,
       the second measures what they actually came to. */
    const first = requestAnimationFrame(() => {
      if (!live) return
      requestAnimationFrame(() => {
        if (!live || taken.current) return
        setBack(true)
        if (!restoreReadingAnchor(stream.current, wanted))
          notify('The post you were reading is not shown here now.')
        settle?.()
      })
    })
    return () => { live = false; cancelAnimationFrame(first) }
  }, [wanted, back, drawn, notify, settle])

  /* REFLOW CORRECTION, answering actual layout events and nothing else: a font
     arriving, an image settling, a margin opening. It stops the moment the
     reader takes control, and there is no timer and no retry behind it. */
  useEffect(() => {
    if (!back || !wanted || taken.current) return
    const el = stream.current
    if (!el || typeof ResizeObserver === 'undefined') return
    const watch = new ResizeObserver(() => {
      if (taken.current) { watch.disconnect(); return }
      restoreReadingAnchor(el, wanted)
    })
    watch.observe(el)
    return () => watch.disconnect()
  }, [back, wanted])

  /* RESTORATION IS OVER AS SOON AS THERE IS NOTHING LEFT TO PUT BACK, and not
     before the question has been answered. That includes a reader who went
     somewhere else while the Brain was still being read: the restore is
     dropped, and capture is let go rather than being suppressed for the rest
     of the reading. */
  useEffect(() => {
    if (!restoring || !decided) return
    if (wanted && !back) return
    settle?.()
  }, [restoring, decided, wanted, back, settle])

  const wrote = (id: Id) => {
    facts.reload()
    setRevision((n) => n + 1)
    took()
    notify(turn ? 'Reply posted.' : 'Message posted.')
    // Return the flow to its latest page; a thread keeps its current reading place.
    if (!turn) location.hash = quietHref(conversation, topic)
    else location.hash = quietHref(conversation, topic, id)
  }

  /* THE DEEP DIVE SLOT, with a live accessor for the post's own drawn body
     (F5). D captures its selection against the Source actually drawn; R mounts
     the slot and never needs editing again for it. */
  const action = useMemo(() => (post: Turn) => (body: () => HTMLElement | null) => (
    <DeepDiveAction post={post} body={body} effectiveConversation={conversation}
      originConversation={originConversation} page={page} onOpened={() => facts.reload()} />
  ), [conversation, originConversation, page, facts.reload])

  const data = facts.data
  return <main id="qc-reading" className="qc-reading" tabIndex={-1}>
    <div id="qc-stream" className="qc-stream" tabIndex={-1} ref={stream}>
      <ReadState loading={!data && facts.loading} error={facts.error} reload={facts.reload} />
      {data && missingTopic ? <p role="alert">This topic is not in this conversation. <a href={quietHref(conversation)}>Show all posts</a></p>
        : data && (turn ? <Thread key={`${conversation}/${turn}`} conversation={conversation} topic={topic} target={turn}
          topics={topics} draft={draft} setDraft={setDraft} setCompose={setCompose} report={report}
          action={action} savedReplyTo={resumedThread ? resume.replyTo : null}
          holdStill={resumedThread && !!resume.threadAnchor && !back}
          onThread={setOpened} onDrawn={setDrawn} onLost={notify} took={took} />
          : <FlowPage key={`${flowKey}/${batchKey}`} conversation={conversation} topic={topic} topics={topics}
            setCompose={setCompose} report={report} page={batch} action={action} onDrawn={setDrawn}
            move={(next) => { setPaged({ key: flowKey, batch: next }); took(); resetReading() }} />)}
    </div>
    <div className="qc-dock">
      {compose && <Composer {...{ conversation, topic, me, draft, setDraft }} reply={compose.reply} onPosted={wrote} />}
    </div>
  </main>
}

/** The Deep dive slot, as a post asks for it. */
type ActionFor = (post: Turn) => (body: () => HTMLElement | null) => ReactNode

function FlowPage({ conversation, topic, topics, setCompose, report, page, move, action, onDrawn }: {
  conversation: Id; topic: Id | null; topics: Topics; setCompose: SetCompose; report: Report
  page: BatchCursor; move: (page: BatchCursor) => void
  action: ActionFor; onDrawn: (drawn: boolean) => void
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
  /* DRAWN, so a restore measures rows that exist. A reading whose data arrives
     after the reader has gone somewhere else never reports itself: this is
     reported from the page that drew them. */
  useEffect(() => {
    if (!ready) return
    onDrawn(true)
    return () => onDrawn(false)
  }, [ready, onDrawn])
  return <>
    <ReadState loading={read.loading} error={read.error} reload={read.reload} />
    <nav className="qc-paging" aria-label="Conversation history">
      {!!batch?.older && batch.first !== null && <button onClick={() => move({ before: batch.first! })}>← Older posts ({batch.older})</button>}
      {(page.before !== undefined || page.after !== undefined) && <button onClick={() => move({})}>Latest posts</button>}
    </nav>
    {shown.map((p) => <Post key={p.id} turn={p} {...{ conversation, topic, topics }} action={action(p)} />)}
    {shownLinked.map((p) => <Post key={`linked-${p.id}`} turn={p} {...{ conversation, topic, topics }} action={action(p)} />)}
    {read.data && !read.data.turns.length && !read.data.linked?.length && <p className="qc-empty">{topic ? 'No posts filed under this topic yet.' : 'The conversation starts here.'}</p>}
    <nav className="qc-paging" aria-label="Newer conversation history">
      {!!batch?.newer && batch.last !== null && <button onClick={() => move({ after: batch.last! })}>Newer posts ({batch.newer}) →</button>}
    </nav>
  </>
}

function Thread({ conversation, topic, target, topics, draft, setDraft, setCompose, report, action,
  savedReplyTo, holdStill, onThread, onDrawn, onLost, took }: {
  conversation: Id; topic: Id | null; target: Id; topics: Topics
  draft: ReturnType<typeof useDraft>['draft']; setDraft: ReturnType<typeof useDraft>['setDraft']
  setCompose: SetCompose; report: Report; action: ActionFor
  /** the post the composer was answering when this thread was left */
  savedReplyTo: Id | null
  /** that post's own offset is being restored, so do not scroll to the target */
  holdStill: boolean
  onThread: (thread: ReadingThread | null) => void
  onDrawn: (drawn: boolean) => void
  onLost: (text: string) => void
  took: () => void
}) {
  const quietHref = useQuietHref()
  const [chosen, setChosen] = useState<Id | null>(null)
  const where = useApi<ThreadLocation>(`/api/turns/${encodeURIComponent(target)}`)
  const root = where.data?.inspector.root
  const thread = useApi<ThreadRead>(root ? `/api/conversations/${encodeURIComponent(conversation)}/thread/${encodeURIComponent(root)}` : null)
  const data = thread.data
  const rows = data ? [data.turn, ...data.replies] : []
  const byId = new Map(rows.map((p) => [p.id, p]))
  /* THE POST BEING ANSWERED IS NOT THE POST BEING READ. The reader's own
     choice wins; failing that the saved one, if it is still in this thread. */
  const picked = chosen ?? savedReplyTo
  const settled = data ? validReplyTarget(rows, picked, target) : { reply: picked ?? target, lost: false }
  const replyId = settled.reply
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
    onDrawn(true)
    return () => onDrawn(false)
  }, [data, onDrawn])
  /* WHAT IS OPEN HERE, told to the reader so it is written down once. */
  useEffect(() => {
    if (!root || !data) return
    onThread({ root, target, replyTo: replyId, anchor: null })
    return () => onThread(null)
  }, [root, data, target, replyId, onThread])
  /* A LOST REPLY TARGET IS SAID, NEVER SWALLOWED. */
  const said = useRef(false)
  useEffect(() => {
    if (!settled.lost || said.current) return
    said.current = true
    onLost('The post you were replying to is no longer in this thread; replying to the post you are reading.')
  }, [settled.lost, onLost])
  useEffect(() => {
    if (!data || holdStill) return
    document.getElementById(`qc-post-${target}`)?.scrollIntoView({ block: 'start' })
  }, [data, target, holdStill])
  useEffect(() => {
    if (!reply) return
    setCompose({ reply })
    return () => setCompose(null)
  }, [reply, setCompose])
  return <>
    <div className="qc-thread-head"><a href={quietHref(conversation, topic)}>← Back to {topic ? 'topic' : 'conversation'}</a>
      {data && <><h2>Thread #{data.turn.number} <span> · {data.replies_total} replies</span></h2>
        <label>Go to post <select aria-label="Go to post in thread" value={target}
          onChange={(e) => { took(); window.location.hash = quietHref(conversation, topic, e.target.value) }}>
          {rows.map((p) => <option key={p.id} value={p.id}>#{p.number} · {p.author_alias}{p.answering_number ? ` · replying to #${p.answering_number}` : ''}</option>)}
        </select></label>
        <nav aria-label="Thread navigation">
          {index > 0 && <a href={quietHref(conversation, topic, rows[index - 1].id)}>← Previous post</a>}
          {index < rows.length - 1 && <a href={quietHref(conversation, topic, rows[index + 1].id)}>Next post →</a>}
        </nav></>}
    </div>
    <ReadState loading={where.loading || thread.loading} error={where.error || thread.error}
      reload={() => { where.reload(); thread.reload() }} />
    {where.data && !root && <p role="alert">This post has no thread in this conversation.</p>}
    {data && <ParentHeader turn={data.turn} conversation={conversation} topic={topic} />}
    {shown.map((p) => <Post key={p.id} turn={p} {...{ conversation, topic, topics }} inThread selected={p.id === replyId}
      answeringAuthor={p.answering ? byId.get(p.answering)?.author_alias ?? null : null}
      action={action(p)}
      onReply={() => {
        if (replyId !== p.id) setDraft({ ...draft, op: crypto.randomUUID() })
        setChosen(p.id)
        requestAnimationFrame(() => document.getElementById('qc-compose')?.focus())
      }} />)}
    {data && !reply && <p role="alert">The requested post is not in this thread.</p>}
  </>
}
