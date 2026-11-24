/* Own Conversation only. Evidence stays inside the card through onEvidence.
 * Full Conversation navigation is a separate, labelled owner action.
 *
 * THIS IS THE CONVERSATION VIEW, NOT THE COMPOSER. In the approved hybrid card
 * the composer is persistent and lives in the frame's footer slot, on every
 * tab (`ComposerBar.tsx`); this view reads and shows the Conversation the bar
 * writes into, and the two share one store (`miniConversationOf`). What used to
 * sit beside the composer here has moved and is not lost: the reading choice is
 * a group in the bar's own "What Mentis reads" menu, the Perspective selector
 * has its one approved home in the Perspectives view, and the disclosure
 * sentences are this view's header. */

import { useEffect, useRef, useSyncExternalStore } from 'react'
import { useBrainBound } from '../../brainBinding'
import { hearPulse } from '../../fluid/identity/activity'
import { flowMoved, spacedAfter } from '../real'
import { evidencePieces, isEvidence } from './evidence'
import type { MagnetResource } from './contract'
import {
  NO_OWN_CONVERSATION, WORK_WORDS, miniConversationOf,
  type MiniPost, type MiniWork,
} from './conversation'
import './conversation.css'
import { restore } from './places'
import { PERSPECTIVE_DISCLOSURE } from './perspectives'

export interface MiniConversationProps {
  resource: MagnetResource
  onFull(): void
  canWrite: boolean
  onEvidence?(ref: string): void
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
export function Words({ text, onEvidence }: { text: string; onEvidence?(ref: string): void }) {
  const paragraphs = text.split(/\n{2,}/).map((p) => p.trim()).filter(Boolean)
  if (!paragraphs.length) return null
  return <>{paragraphs.map((p, i) => <p className="q2-mini-words" key={i}>
    {evidencePieces(p).map((piece, j) => onEvidence && isEvidence(piece)
      ? <button type="button" className="q2-mini-link q2-mini-evidence" key={j}
        aria-label={`Inspect ${piece} inside Magnet`} onClick={() => onEvidence(piece)}>{piece}</button>
      : piece)}
  </p>)}</>
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

export function PostView({ post, onReply, onThread, canReply, threadOpen, onEvidence }: {
  post: MiniPost
  onReply(): void
  onThread(): void
  canReply: boolean
  threadOpen: boolean
  onEvidence?(ref: string): void
}) {
  return <li className="q2-mini-post">
    <p className="q2-mini-attribution">
      {post.number !== null ? `#${post.number} · ` : ''}{post.authorAlias}{post.agent ? ' · agent' : ''}
      {when(post.at) ? ` · ${when(post.at)}` : ''}
      {post.replyNumber !== null ? ` · in reply to #${post.replyNumber}` : ''}
    </p>
    {post.agent && <p className="q2-mini-muted">{PERSPECTIVE_DISCLOSURE}</p>}
    {post.deleted
      ? <p className="q2-mini-muted">This post was deleted. What it said is not shown here.</p>
      : post.text ? <Words text={post.text} onEvidence={onEvidence} /> : <p className="q2-mini-muted">This post has no words of its own in this read.</p>}
    {post.work.length > 0 && <ul className="q2-mini-works">{post.work.map((w) => <WorkLine key={w.expectation} work={w} />)}</ul>}
    <p className="q2-mini-post-actions">
      {canReply && <button type="button" className="q2-mini-link" onClick={onReply}>Reply</button>}
      {post.replies > 0 && <button type="button" className="q2-mini-link" onClick={onThread}>
        {threadOpen ? 'Hide' : 'Show'} {post.replies} {post.replies === 1 ? 'reply' : 'replies'}
      </button>}
    </p>
  </li>
}

export default function MiniConversation({ resource, onFull, canWrite, onEvidence }: MiniConversationProps) {
  const bound = useBrainBound()
  const working = useSyncExternalStore(resource.subscribe, resource.snapshot, resource.snapshot)
  /* The same store the footer composer writes through: two would read this
     Conversation twice and could disagree about what was sent. It is not
     disposed here -- it outlives this view, as the composer does. */
  const { store } = miniConversationOf(resource, canWrite, bound)
  const s = useSyncExternalStore(store.subscribe, store.snapshot, store.snapshot)
  const refreshed = useRef(0)

  useEffect(() => {
    refreshed.current = Date.now()
    void store.read()
  }, [store])

  /* THE SAME LIVE RECORD FOLLOWING AS THE REGULAR QUIET CONVERSATION. The
     page's one /api/pulse beat says where durable material moved; this visible
     Conversation rereads only when its own id may have moved, trailing with
     the same spacing as useRealFlow/useThread. No second poll or stream. */
  useEffect(() => {
    const conversation = store.conversation
    if (!conversation) return
    let owed: number | null = null
    const stop = hearPulse((moved, where) => {
      if (!flowMoved(moved, where, conversation) || owed !== null) return
      owed = window.setTimeout(() => {
        owed = null
        refreshed.current = Date.now()
        void store.refresh()
      }, spacedAfter(refreshed.current))
    })
    return () => { stop(); if (owed !== null) clearTimeout(owed) }
  }, [store, store.conversation])

  /* THE WAY BACK, saved when a message was sent from another view. Restoring a
     route moves the card, never the words: the draft and any inquiry draft are
     held per Magnet and `restore()` does not touch them. */
  const back = working.returnRoute
  const returnToWhereIWas = back && <button type="button" id="return-view" className="q2-mini-link"
    onClick={() => { restore(resource, back); resource.update({ returnRoute: null }) }}>
    ← Return to {back.overlay === 'search' ? 'search results' : back.overlay === 'settings' ? 'settings' : back.tab}
  </button>

  if (s.unavailable) {
    return <section className="q2-mini q2-mini-unavailable" aria-label="Magnet conversation">
      <h3 id="view-title" tabIndex={-1}>{s.unavailable === NO_OWN_CONVERSATION ? 'Start a Conversation here' : 'Magnet conversation unavailable'}</h3>
      <p>{s.unavailable}</p>
      {s.unavailable === NO_OWN_CONVERSATION && canWrite && <>
        <p className="q2-mini-muted">Writing a message below makes this Conversation and records the message in it. Creating it first is the same act, without a message.</p>
        <button type="button" className="q2-mini-send"
          disabled={s.creating} onClick={() => void store.createOwn()}>
          {s.creating ? 'Creating Conversation…' : 'Create own Conversation'}
        </button>
      </>}
      {returnToWhereIWas}
      {s.contextError && <p className="q2-mini-alert" role="status">{s.contextError}</p>}
      {s.sendError && <p className="q2-mini-alert" role="status">{s.sendError}</p>}
    </section>
  }

  const blocked = !!s.identity
  const writable = canWrite && !blocked
  const reply = (post: MiniPost | null) => {
    store.replyTo(post)
    /* The composer is the card's one footer bar, wherever this view is. */
    if (post) requestAnimationFrame(() => document.querySelector<HTMLTextAreaElement>('.q2-magnet-composer textarea')?.focus())
  }

  return <section className="q2-mini" aria-label="Magnet conversation">
    <div className="q2-mini-head">
      <h3 id="view-title" tabIndex={-1}>{s.name || 'Magnet conversation'}</h3>
      <span className="q2-mini-head-actions">
        <button type="button" className="q2-mini-link" onClick={onFull}>Open full Conversation →</button>
        {returnToWhereIWas}
      </span>
    </div>
    {/* The disclosure sentences the composer used to carry are this view's:
        they are about what an agent reads here, which is what this view shows. */}
    <p className="q2-mini-muted">{PERSPECTIVE_DISCLOSURE}</p>
    <p className="q2-mini-muted">
      {s.total !== null ? `${s.total} ${s.total === 1 ? 'post' : 'posts'} recorded here` : 'How many posts are recorded here is unavailable'}
      {s.owed !== null ? ` · ${s.owed} ${s.owed === 1 ? 'obligation' : 'obligations'} outstanding` : ' · outstanding work is unavailable in this read'}
    </p>
    {s.collection && onEvidence && <button type="button" className="q2-mini-link"
      onClick={() => onEvidence(s.collection!.artifact.ref)}>Inspect retained collection</button>}
    {s.contextError && <p className="q2-mini-alert" role="status">{s.contextError}</p>}
    {s.dispatchStatus && <p className="q2-mini-muted" role="status">{s.dispatchStatus}</p>}
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
        onEvidence={onEvidence}
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
          onEvidence={onEvidence}
          onReply={() => reply(p)} onThread={() => {}} />)}
      </ul>
    </div>}

    {/* No composer here: the card has one, in its footer, on every tab. What
        the owner may not do is still said where they would look for it. */}
    {!canWrite && <p className="q2-mini-muted q2-mini-nowrite">Sending is unavailable for this Magnet here. Nothing in this card writes to the record.</p>}
  </section>
}
