/* THE MAGNET'S OWN CONVERSATION, IN THE CARD.
 *
 * A small, real presentation of ONE existing Conversation -- the Magnet's own,
 * never a source it collects from -- with its actual posts, its replies, the
 * Work recorded on them, and an explicit Send and Reply.
 *
 * WHAT IT WILL NOT DO. It does not create, repair or substitute a Conversation:
 * a Magnet with none, or one pointed at a source, says so here and offers
 * nothing. It draws words as TEXT and never as markup. It reads this
 * Conversation only, through its own seam (`conversation.ts`): Quiet's main
 * post store and its navigation are untouched, and the only way out of this
 * card is the full Conversation, which the parent carries out (`onFull`).
 *
 * WHAT IT NEEDS FROM THE PARENT. `canWrite` is a capability the parent supplies
 * for this card alone; it is never read off the page's own read-only state, and
 * false means the composer is visibly unavailable rather than quietly broken.
 * `hasMiniDraft(resource)` (exported from `conversation.ts`) is what the parent
 * asks before closing this card or navigating away from it. */

import { useEffect, useMemo, useRef, useSyncExternalStore } from 'react'
import type { MagnetResource } from './contract'
import {
  WORK_WORDS, createMiniConversation,
  type MiniAt, type MiniConversation as MiniStore, type MiniPost, type MiniWork,
} from './conversation'
import './conversation.css'

export interface MiniConversationProps {
  resource: MagnetResource
  onFull(): void
  canWrite: boolean
}

const when = (at: number): string => {
  if (!at) return ''
  const d = new Date(at * 1000)
  if (Number.isNaN(d.getTime())) return ''
  return `${d.toLocaleDateString([], { month: 'short', day: 'numeric' })}, ${d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}`
}

/** The author's words, drawn as text. Paragraphs are the blank lines they
 *  wrote; nothing here renders markup, and no string reaches the DOM as HTML.
 *  Exported, with `WorkLine` and `PostView`, so what a post actually draws can
 *  be asserted without a browser. */
export function Words({ text }: { text: string }) {
  const paragraphs = text.split(/\n{2,}/).map((p) => p.trim()).filter(Boolean)
  if (!paragraphs.length) return null
  return <>{paragraphs.map((p, i) => <p className="q2-mini-words" key={i}>{p}</p>)}</>
}

/** ONE RECORDED REQUEST, as the read states it. Nothing is inferred: an
 *  unassigned request says nobody carries it rather than naming somebody. */
export function WorkLine({ work }: { work: MiniWork }) {
  return <li className={`q2-mini-work q2-mini-work-${work.state}`}>
    <span className="q2-mini-work-state">{WORK_WORDS[work.state]}</span>
    <span className="q2-mini-work-expects">{work.expects || 'what this asks for is not stated in this read'}</span>
    <span className="q2-mini-work-who">
      {work.unassigned ? 'nobody carries it' : `carried by ${work.ofAlias ?? 'a participant this read does not name'}`}
      {work.byAlias ? ` · asked by ${work.byAlias}` : ''}
      {work.liveExecution ? ' · a run is live' : ''}
    </span>
  </li>
}

export function PostView({ post, onReply, onThread, canReply, threadOpen }: {
  post: MiniPost
  onReply(): void
  onThread(): void
  canReply: boolean
  threadOpen: boolean
}) {
  return <li className="q2-mini-post">
    <p className="q2-mini-attribution">
      {post.number !== null ? `#${post.number} · ` : ''}{post.authorAlias}{post.agent ? ' · agent' : ''}
      {when(post.at) ? ` · ${when(post.at)}` : ''}
      {post.replyNumber !== null ? ` · in reply to #${post.replyNumber}` : ''}
    </p>
    {post.deleted
      ? <p className="q2-mini-muted">This post was deleted. What it said is not shown here.</p>
      : post.text ? <Words text={post.text} /> : <p className="q2-mini-muted">This post has no words of its own in this read.</p>}
    {post.work.length > 0 && <ul className="q2-mini-works">{post.work.map((w) => <WorkLine key={w.expectation} work={w} />)}</ul>}
    <p className="q2-mini-post-actions">
      {canReply && <button type="button" className="q2-mini-link" onClick={onReply}>Reply</button>}
      {post.replies > 0 && <button type="button" className="q2-mini-link" onClick={onThread}>
        {threadOpen ? 'Hide' : 'Show'} {post.replies} {post.replies === 1 ? 'reply' : 'replies'}
      </button>}
    </p>
  </li>
}

export default function MiniConversation({ resource, onFull, canWrite }: MiniConversationProps) {
  /* The store reads `canWrite` when Send is pressed, so a capability withdrawn
     mid-draft is honoured without rebuilding the card or losing the words. */
  const holder = useRef<MiniAt>({ resource, canWrite })
  holder.current.resource = resource
  holder.current.canWrite = canWrite
  const store: MiniStore = useMemo(() => createMiniConversation(holder.current), [resource])
  const s = useSyncExternalStore(store.subscribe, store.snapshot, store.snapshot)
  const box = useRef<HTMLTextAreaElement>(null)

  useEffect(() => () => store.dispose(), [store])
  useEffect(() => { void store.read() }, [store])

  if (s.unavailable) {
    return <section className="q2-mini q2-mini-unavailable" aria-label="Magnet conversation">
      <h3>Magnet conversation unavailable</h3>
      <p>{s.unavailable}</p>
      <p className="q2-mini-muted">No Conversation is created, repaired or stood in for here, and nothing can be sent.</p>
    </section>
  }

  const blocked = !!s.identity
  const writable = canWrite && !blocked
  const reply = (post: MiniPost | null) => {
    store.replyTo(post)
    if (post) requestAnimationFrame(() => box.current?.focus())
  }

  return <section className="q2-mini" aria-label="Magnet conversation">
    <div className="q2-mini-head">
      <h3>{s.name || 'Magnet conversation'}</h3>
      <button type="button" className="q2-mini-link" onClick={onFull}>Open full Conversation →</button>
    </div>
    <p className="q2-mini-muted">
      {s.total !== null ? `${s.total} ${s.total === 1 ? 'post' : 'posts'} recorded here` : 'How many posts are recorded here is unavailable'}
      {s.owed !== null ? ` · ${s.owed} ${s.owed === 1 ? 'obligation' : 'obligations'} outstanding` : ' · outstanding work is unavailable in this read'}
    </p>
    {blocked && <p className="q2-mini-alert" role="status">{s.identity}</p>}
    {s.error && <p className="q2-mini-alert" role="status">{s.error}</p>}
    {s.loading && <p className="q2-mini-muted" role="status">Reading this Conversation…</p>}

    {s.older > 0 && <p className="q2-mini-earlier">
      <button type="button" className="q2-mini-link" disabled={s.loadingEarlier} onClick={() => void store.earlier()}>
        {s.loadingEarlier ? 'Reading earlier posts…' : `Earlier posts (${s.older} older)`}
      </button>
    </p>}
    {s.earlierError && <p className="q2-mini-alert" role="status">{s.earlierError}</p>}

    {s.posts.length === 0 && !s.loading && !s.error && <p className="q2-mini-muted">No posts have been read here yet.</p>}
    <ul className="q2-mini-posts">
      {s.posts.map((p) => <PostView key={p.id} post={p} canReply={writable}
        threadOpen={s.thread?.root === p.id}
        onReply={() => reply(p)}
        onThread={() => s.thread?.root === p.id ? store.closeThread() : void store.openThread(p.id)} />)}
    </ul>

    {s.thread && <div className="q2-mini-thread">
      <div className="q2-mini-head">
        <h4>Replies</h4>
        <button type="button" className="q2-mini-link" onClick={() => store.closeThread()}>Close thread</button>
      </div>
      {s.thread.loading && <p className="q2-mini-muted" role="status">Reading this thread…</p>}
      {s.thread.error && <p className="q2-mini-alert" role="status">{s.thread.error}</p>}
      {!s.thread.loading && !s.thread.error && s.thread.replies.length === 0 && <p className="q2-mini-muted">No replies were read in this thread.</p>}
      <ul className="q2-mini-posts">
        {s.thread.replies.map((p) => <PostView key={p.id} post={p} canReply={writable} threadOpen={false}
          onReply={() => reply(p)} onThread={() => {}} />)}
      </ul>
    </div>}

    {!canWrite
      ? <p className="q2-mini-muted q2-mini-nowrite">Sending is unavailable for this Magnet here. Nothing in this card writes to the record.</p>
      : <form className="q2-mini-composer" onSubmit={(e) => { e.preventDefault(); void store.send() }}>
        {s.replyTo && <p className="q2-mini-replying">
          <span>Replying to {s.replyTo.alias}{s.replyTo.number !== null ? ` #${s.replyTo.number}` : ''}</span>
          <button type="button" className="q2-mini-link" onClick={() => reply(null)}>Reply to the Conversation instead</button>
        </p>}
        <label className="q2-mini-label" htmlFor={`q2-mini-${resource.id}`}>Write in this Conversation</label>
        <textarea id={`q2-mini-${resource.id}`} ref={box} className="q2-mini-text" rows={3}
          value={s.draft} disabled={blocked}
          onChange={(e) => store.draft(e.target.value)} />
        <div className="q2-mini-send-row">
          <button type="submit" className="q2-mini-send" disabled={s.sending || blocked || !s.draft.trim()}>
            {s.sending ? 'Sending…' : s.uncertain ? 'Send again under the same key' : s.replyTo ? 'Send reply' : 'Send'}
          </button>
          <span className="q2-mini-muted">Recorded as a post. Nothing is dispatched and no run is started.</span>
        </div>
        {s.sendError && <p className={s.uncertain ? 'q2-mini-alert q2-mini-uncertain' : 'q2-mini-alert'} role="status">{s.sendError}</p>}
        {s.sent && <p className="q2-mini-sent" role="status">
          {s.sent.replayed
            ? 'That post was already recorded under this key; nothing was recorded a second time.'
            : `Recorded${s.sent.number !== null ? ` as #${s.sent.number}` : ''}.`}
        </p>}
      </form>}
  </section>
}
