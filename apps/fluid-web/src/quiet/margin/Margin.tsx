/* TRACK C owns this module: WHAT THE POSTS CARRY, PRESENTED BESIDE THEM.

   THE MOCKUP'S MARGINS (`quiet-chat-concept.html`, and its README: "what each
   turn carries goes beside it: media and the timeline, chart, git graph and
   flow chart on the right; documents, the table and the form on the left").
   Each one is a SMALL WINDOW: a head that says what it is and which post it
   came from, and the two things a reader does with it -- go back to the post
   it belongs to, and put it away. A picture and a film open in the viewer
   from here as they do from the post (that is the mockup's "pop out"); a
   block is the SAME block as the one in the post, keyed identically
   (`carried.ts`), so ticking a checklist here ticks it there.

   IT ADAPTS TO ITS OWN WIDTH, NOT THE WINDOW'S. `.qc-margin` is a container
   (rail.css), so every box asks how wide the MARGIN is -- which is a third
   of the shell's grid at 1440 and the whole column below 900 -- and nothing
   here reads the viewport. Anything that cannot shrink (a wide table, a long
   diagram) scrolls INSIDE its own box; the page never scrolls sideways.

   NOT A FLOATING WINDOW. Fluid's floats, magnets and Pages are outside this
   work: a box is an element in the margin's flow that LOOKS like a small
   window, and there is no dragging, no stacking and no z-order here. */
import { useEffect, useRef, useState } from 'react'
import { Prose } from '../../prose'
import { RenderableBlock, turnPartScope } from '../../experimental/renderable'
import { commentsOldestFirst, lead, tallyWords } from '../../fluid/conversation/annotated'
import { usePost } from '../../fluid/conversation/hooks'
import { said } from '../../fluid/conversation/text'
import { store } from '../../fluid/store'
import type { PostAnchor } from '../../fluid/actions'
import { openViewer } from '../media/MediaLayer'
import { kindWords } from '../media/view'
import { goToPost, postNumber, putAway, useCarried, useOpened, type Carried } from './carried'
import './margin.css'

/* -- an annotation, READ in its box ---------------------------------------- */

/** One comment on the passage, with its own words.
 *
 *  A COMMENT IS WORDS SOMEBODY WROTE. The box said how many were attached and
 *  not one of them, so the annotation was not readable anywhere the icon led:
 *  a count is a promise of content, not content. The comment is a Turn, so it
 *  is read as Quiet reads any Turn's words -- `said` for the Markdown the
 *  card draws, `Prose` under the comment's own part scope, which is the scope
 *  its blocks are keyed by wherever else it is drawn. Reused from Fluid's own
 *  reading of the same thing (`fluid/conversation/Annotations.tsx`
 *  `CommentLine`), not written again. */
function Comment({ id }: { id: string }) {
  const post = usePost(id)
  const words = post && !post.deleted ? said(post).words : ''
  const by = post ? '@' + post.author_name.replace(/^@/, '') : ''
  return <li className="qc-box-comment" data-comment={id}>
    {by && <p className="qc-box-comment-by">{by}</p>}
    {post?.deleted
      ? <p className="qc-muted"><i>This comment was deleted.</i></p>
      : words
        ? <div className="qc-box-comment-words qc-body"><Prose src={words} scope={turnPartScope(id, 0)} /></div>
        : <p className="qc-muted" role="status">Reading it…</p>}
  </li>
}

/** What is attached to the passage: the passage itself, the tally, and every
 *  comment's words. The comments are read in one batch, oldest first, as
 *  anchored replies are a history and are always read that way. */
function AnnotationBody({ anchor, excerpt }: { anchor: PostAnchor; excerpt: string | null }) {
  const replies = anchor.replies
  const key = replies.join('\n')
  const [, read] = useState(0)
  useEffect(() => {
    let live = true
    void store.loadPosts(replies).then(() => { if (live) read((n) => n + 1) }).catch(() => {})
    return () => { live = false }
    // the IDs, not the array's identity, say whether this history changed
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])
  const { n } = lead(anchor)
  const inOrder = commentsOldestFirst(replies, (id) => store.posts.get(id)?.at)
  return <>
    {excerpt && <blockquote className="qc-box-passage">{excerpt}</blockquote>}
    <p className="qc-box-tally">{tallyWords(anchor)}</p>
    {inOrder.length > 0
      ? <ol className="qc-box-comments" aria-label={inOrder.length === 1 ? 'one comment' : `${inOrder.length} comments, oldest first`}>
        {inOrder.map((id) => <Comment key={id} id={id} />)}
      </ol>
      : <p className="qc-muted">{n === 1 ? 'one thing is attached here' : `${n} things are attached here`}</p>}
  </>
}

function BoxBody({ c }: { c: Carried }) {
  if (c.kind === 'block')
    return <RenderableBlock block={c.block} blockKey={c.blockKey} where={c.where} names={c.names} size="compact" />
  if (c.kind === 'media') {
    const { item } = c
    if (item.kind === 'image')
      return <button type="button" className="qc-box-image" aria-label={`Open ${item.name}`}
        onClick={(e) => openViewer([item], 0, e.currentTarget)}>
        <img src={item.url} alt={item.alt} />
      </button>
    return <button type="button" className="qc-box-open" aria-label={`Open ${item.name}`}
      onClick={(e) => openViewer([item], 0, e.currentTarget)}>
      Open · {kindWords[item.kind]}
    </button>
  }
  return <AnnotationBody anchor={c.anchor} excerpt={c.excerpt} />
}

function Box({ c, marked }: { c: Carried; marked: boolean }) {
  const box = useRef<HTMLElement>(null)
  const number = postNumber(c.post)
  const from = number != null ? `post #${number}` : 'its post'
  useEffect(() => { if (marked) box.current?.scrollIntoView({ block: 'nearest' }) }, [marked])
  return (
    <section className="qc-box" ref={box} data-kind={c.kind} data-side={c.side}
      data-marked={marked || undefined} aria-label={`${c.title}, carried by ${from}`}>
      <div className="qc-box-head">
        <h3 className="qc-box-title">{c.title}</h3>
        <button type="button" className="qc-box-where" onClick={() => goToPost(c.post)}
          aria-label={`Go to ${from}`} title={`Go to ${from}`}>{number != null ? `#${number}` : '↑'}</button>
        <button type="button" className="qc-box-away" onClick={() => putAway(c.id)}
          aria-label={`Put away ${c.title}`} title="Put away">×</button>
      </div>
      <div className="qc-box-body"><BoxBody c={c} /></div>
    </section>
  )
}

export default function Margin({ side }: { side?: 'left' | 'right' }) {
  const carried = useCarried().filter((c) => !side || c.side === side)
  const opened = useOpened()
  if (!carried.length)
    return <p className="qc-carried-none">Nothing is carried beside these posts yet. A post's
      chart, table, checklist, timeline, diagram, file or annotation is presented here.</p>
  return <div className="qc-carried">
    {carried.map((c) => <Box key={c.id} c={c} marked={c.id === opened} />)}
  </div>
}
