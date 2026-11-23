/* Own Conversation only. Questions dispatch with retained evidence; notes are
 * explicitly separate. Evidence stays inside the card through onEvidence.
 * Full Conversation navigation is a separate, labelled owner action. */

import { useEffect, useMemo, useRef, useSyncExternalStore } from 'react'
import Composer from '../../fluid/Composer'
import { miniAsking } from './asking'
import { useBrainBound } from '../../brainBinding'
import { evidencePieces, isEvidence } from './evidence'
import type { MagnetResource } from './contract'
import {
  NO_OWN_CONVERSATION, WORK_WORDS, createMiniConversation, miniAttempt,
  type MiniAt, type MiniConversation as MiniStore, type MiniPost, type MiniWork,
} from './conversation'
import './conversation.css'
import { perspectivesOf, PERSPECTIVE_DISCLOSURE } from './perspectives'
import { LensSelector } from './InquiryPanel'

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
  /* The store reads `canWrite` when Send is pressed, so a capability withdrawn
     mid-draft is honoured without rebuilding the card or losing the words. */
  const holder = useRef<MiniAt>({ resource, canWrite })
  const inquiries = useMemo(() => perspectivesOf(resource), [resource])
  const lens = useSyncExternalStore(inquiries.subscribe, inquiries.snapshot, inquiries.snapshot)
  const working = useSyncExternalStore(resource.subscribe, resource.snapshot, resource.snapshot)
  holder.current.resource = resource
  holder.current.canWrite = canWrite
  holder.current.contextKey = () => {
    const current = inquiries.snapshot(), row = current.rows.find((p) => p.perspective === current.selected)
    return `${current.selected ?? ''}:${row?.question?.ref ?? ''}:${resource.snapshot().assistanceMode ?? 'ordinary'}`
  }
  holder.current.beforeRequest = async (post, op) => {
    const previous = miniAttempt(resource)
    if (previous?.perspective && ['in-flight', 'uncertain', 'malformed'].includes(previous.state)) throw new Error('Resolve the original frozen Perspective request before sending a different question.')
    if (resource.snapshot().assistanceMode === 'retained' && !inquiries.snapshot().selected) return { post, op }
    // The Perspective package supplies a fresh durable question, not a frozen
    // evidence package. It checks Brain and selection races before returning.
    const contextStore = inquiries as typeof inquiries & { ordinaryContext(): Promise<{ perspective: string; name: string; question: string; revision: string } | null> }
    const perspective = await contextStore.ordinaryContext()
    return { post: { ...post, _magnetAssistance: { magnet: resource.saved.id,
      configuration: resource.saved.config, perspective,
      supported_sources: ['Conversations', 'exact held UTF-8 filesystem files'],
      collection: 'manual Collect now; opening and saving do not collect',
      unsupported: ['web search', 'Topic/post-specific adapters', 'Git/SQLite Magnet adapters', 'connected services', 'automatic collection'],
      grounded_perspective_execution: 'disabled; configured-source agent access is not enforced',
    } }, op }
  }
  holder.current.afterRecorded = async (attempt, answer) => {
    if (!attempt.perspective) return
    const requests = answer.expectations
    if (!Array.isArray(requests) || requests.length !== 1 || typeof requests[0] !== 'string') throw new Error('A Perspective question needs exactly one actual agent request. Its frozen intent is kept.')
    await inquiries.bind(attempt.perspective, requests[0])
    inquiries.update({ active: attempt.perspective })
  }
  const bound = useBrainBound()
  const own = resource.saved.config?.conversation
  const store: MiniStore = useMemo(() => createMiniConversation(holder.current), [resource, own, bound])
  const s = useSyncExternalStore(store.subscribe, store.snapshot, store.snapshot)
  const asking = useMemo(() => miniAsking(resource, store), [resource, store])
  const composer = useRef<HTMLDivElement>(null)

  useEffect(() => () => store.dispose(), [store])
  useEffect(() => { void store.read() }, [store])
  useEffect(() => { void store.prepare() }, [store])

  if (s.unavailable) {
    return <section className="q2-mini q2-mini-unavailable" aria-label="Magnet conversation">
      <h3>{s.unavailable === NO_OWN_CONVERSATION ? 'Start a Conversation here' : 'Magnet conversation unavailable'}</h3>
      <p>{s.unavailable}</p>
      {s.unavailable === NO_OWN_CONVERSATION && canWrite && <button type="button" className="q2-mini-send"
        disabled={s.creating} onClick={() => void store.createOwn()}>
        {s.creating ? 'Creating Conversation…' : 'Create own Conversation'}
      </button>}
      {s.contextError && <p className="q2-mini-alert" role="status">{s.contextError}</p>}
      {s.sendError && <p className="q2-mini-alert" role="status">{s.sendError}</p>}
    </section>
  }

  const blocked = !!s.identity
  const writable = canWrite && !blocked
  const reply = (post: MiniPost | null) => {
    store.replyTo(post)
    if (post) requestAnimationFrame(() => composer.current?.querySelector('textarea')?.focus())
  }

  return <section className="q2-mini" aria-label="Magnet conversation">
    <div className="q2-mini-head">
      <h3>{s.name || 'Magnet conversation'}</h3>
      <span className="q2-mini-head-actions">
        {/* WHAT HAS ARRIVED SINCE, when the owner asks for it. Replies and
            Work recorded while this card is open are read without collapsing
            and reopening it. Nothing here is on a timer and nothing polls. */}
        <button type="button" className="q2-mini-link" disabled={s.loading}
          onClick={() => { void store.refresh(); void store.prepare() }}>
          {s.loading ? 'Refreshing…' : 'Refresh conversation'}
        </button>
        <button type="button" className="q2-mini-link" onClick={onFull}>Open full Conversation →</button>
      </span>
    </div>
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

    {!canWrite
      ? <p className="q2-mini-muted q2-mini-nowrite">Sending is unavailable for this Magnet here. Nothing in this card writes to the record.</p>
      : <div className="q2-mini-composer" ref={composer}>
        <LensSelector resource={resource} canWrite={canWrite} />
        <label className="q2-mini-muted">Assistance mode<select aria-label="Magnet assistance mode" value={lens.selected ? 'ordinary' : working.assistanceMode ?? 'ordinary'} disabled={!!lens.selected || s.sending || s.uncertain} onChange={(e) => resource.update({ assistanceMode: e.target.value as 'ordinary' | 'retained' })}><option value="ordinary">Ordinary configuration and inquiry help</option><option value="retained">Discuss retained collection · ordinary reply</option></select></label>
        <p className="q2-mini-muted">Ordinary help works before collecting. Retained discussion uses the selected batch and remains an unqualified reply. Grounded Perspective execution is disabled.</p>
        <p className="q2-mini-muted">{PERSPECTIVE_DISCLOSURE}</p>
        {s.replyTo && <p className="q2-mini-replying">
          <span>Replying to {s.replyTo.alias}{s.replyTo.number !== null ? ` #${s.replyTo.number}` : ''}</span>
          <button type="button" className="q2-mini-link" onClick={() => reply(null)}>Reply to the Conversation instead</button>
        </p>}
        <fieldset className="q2-mini-composer-controls" disabled={blocked || !bound || s.sending || s.uncertain}>
          <Composer key={asking.where} conversation={s.conversation}
            asking={{ ...asking, key: `${asking.key}:${s.replyTo?.id ?? ''}` }}
            replyTo={s.replyTo?.id ?? null} onClearReply={() => reply(null)} operations />
        </fieldset>
        {s.uncertain && <button type="button" className="q2-mini-send" disabled={s.sending || blocked || !bound}
          onClick={() => {
            const attempt = miniAttempt(resource)
            if (attempt?.request) void store.submit(attempt.request.body, attempt.op, attempt.brain).catch(() => {})
            else void store.send()
          }}>Send again under the same key</button>}
        {s.sendError && <p className={s.uncertain ? 'q2-mini-alert q2-mini-uncertain' : 'q2-mini-alert'} role="status">{s.sendError}</p>}
        {s.sent && <p className="q2-mini-sent" role="status">
          {s.sent.replayed
            ? 'That post was already recorded under this key; nothing was recorded a second time.'
            : `Recorded${s.sent.number !== null ? ` as #${s.sent.number}` : ''}.`}
        </p>}
      </div>}
  </section>
}
