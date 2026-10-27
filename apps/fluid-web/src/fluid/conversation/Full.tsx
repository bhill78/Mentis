/* A POST, OR A WHOLE THREAD, FULL SCREEN (#442 #3, #448).
 *
 * Opened from the post (⤢ on its hover chips) or the thread's head, it lies
 * over everything -- the conversation, its sheet and the workspace stay as
 * they are beneath it, nothing reflows -- and Esc, its "‹" or the bar's Back
 * return to exactly the anchor it came from, which flashes once (`nav`'s
 * `full` detail; a sheet that was open stays open beneath it).
 *
 * The post is drawn whole: its words with every block the shared renderers
 * draw, and its attachments. A thread keeps its own composer here too, so
 * replying never means leaving full screen. */

import { useEffect, useRef } from 'react'
import { Prose } from '../../prose'
import { turnPartScope } from '../../experimental/renderable'
import * as nav from '../nav'
import { repliesOf, store, type Post } from '../store'
import { usePost } from './hooks'
import { Where, useActions } from './PostCard'
import { Who } from '../identity/Who'
import { ThreadBody, classicHref } from './Sheets'
import { bare, textOf } from './text'
import PostDecisions from './Decisions'

function Whole({ post }: { post: Post }) {
  if (post.deleted) return <p className="fw-deleted fx-text">Deleted{post.deleted.because ? `: ${post.deleted.because}` : ''}</p>
  const files = post.parts.filter((p) => p.type !== 'text' && p.ref && !['turn', 'topic', 'conversation', 'acquired'].includes(p.type))
  return (
    <>
      <div className="fw-body turn-body fx-text fx-full-text"><Prose src={textOf(post)} scope={turnPartScope(post.id, 0)} /></div>
      {files.length > 0 && (
        <div className="fx-full-files">
          {files.map((p, i) => {
            const mt = String((p as { media_type?: string }).media_type ?? '')
            const name = String(p.alt ?? p.name ?? p.ref)
            return p.type === 'image' || mt.startsWith('image/')
              ? <img key={i} src={`/api/artifacts/${p.ref}`} alt={name} loading="lazy" />
              : <a key={i} className="fx-chip" href={`/api/artifacts/${p.ref}`} target="_blank" rel="noopener">{name}</a>
          })}
        </div>
      )}
    </>
  )
}

export default function Full({ d }: { d: Extract<nav.Detail, { kind: 'full' }> }) {
  const post = usePost(d.id)
  const a = useActions()
  useEffect(() => { if (!store.posts.has(d.id)) void store.loadPosts([d.id]) }, [d.id])
  /* The keyboard goes in with the reader, and comes back where it was. */
  const head = useRef<HTMLButtonElement | null>(null)
  useEffect(() => {
    const was = document.activeElement as HTMLElement | null
    head.current?.focus({ preventScroll: true })
    return () => { if (was?.isConnected) was.focus({ preventScroll: true }) }
  }, [])
  const num = post?.number != null ? `#${post.number}` : 'this post'
  const back = () => nav.closeDetail()
  return (
    <div className="fx-full" role="dialog" aria-modal="true" aria-label={d.of === 'thread' ? `the thread of ${num}, full screen` : `${num}, full screen`} data-full={d.of}>
      <header className="fx-full-head">
        <button ref={head} className="fx-ret" data-act="back" onClick={back} title="Esc">‹ Back to {num}</button>
        <h2>{d.of === 'thread' ? `Replies to ${num}${post ? ` · ${repliesOf(post)}` : ''}` : <>{num}{post ? <span className="fx-faint"> · @{bare(post.author_name)}</span> : null}</>}</h2>
        <span className="fx-grow" />
        {d.of === 'post' && post && repliesOf(post) > 0 && (
          <button className="fx-ctl" onClick={() => nav.openDetail({ kind: 'full', of: 'thread', id: d.id, anchor: d.anchor, mode: 'over' })}>
            {repliesOf(post)} {repliesOf(post) === 1 ? 'reply' : 'replies'} ›
          </button>
        )}
        {post?.home && <a className="fx-ctl" href={classicHref(post.home, d.id)} target="_blank" rel="noopener" title="Editing, and sending a comment on to someone, are in Classic for now. Reactions, comments and deep dives are on the post in its conversation, not in full screen">Classic ↗</a>}
        <button className="fx-ctl fx-x" aria-label={`close full screen, back to ${num}`} onClick={back}>✕</button>
      </header>
      {d.of === 'post' ? (
        <div className="fx-full-body">
          <article className="fx-full-col fx-full-post">
            {post ? (
              <>
                <div className="fx-head fw-head">
                  <Who id={post.author} name={post.author_name} show="line" size={24} className="fx-who fw-author" />
                  {/* Its time is said once, here, in full (the head said it again as "5d ago"). */}
                  <time className="fx-when" dateTime={new Date(post.at * 1000).toISOString()}>{new Date(post.at * 1000).toLocaleString()}</time>
                  <Where post={post} here={a.here} />
                </div>
                <Whole post={post} />
                <PostDecisions post={post} />
              </>
            ) : <div className="fw-pending" aria-busy="true" />}
          </article>
        </div>
      ) : (
        <div className="fx-full-thread"><ThreadBody root={d.id} full /></div>
      )}
    </div>
  )
}
