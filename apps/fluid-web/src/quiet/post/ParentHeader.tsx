/* PACKAGE E owns this module: the sticky parent-post header a thread reads
 * under its heading, so scrolling a long reply chain never loses sight of
 * what it is a thread *of*. It is additive -- the root is still drawn in
 * full as the stream's first row (full interaction: selecting it, replying
 * to it, "Go to post" addressing it, stays exactly as before) -- this is a
 * condensed, always-visible summary of the same post, pinned above it. */
import { useLayoutEffect, useRef, useState } from 'react'
import { ago, type Id, type Turn } from '../../api'
import { Who } from '../../fluid/identity/Who'
import { useQuietHref } from '../reader/navigation'
import PostPart from './parts'
import './post.css'

export default function ParentHeader({ turn, conversation, topic }: {
  turn: Turn; conversation: Id; topic: Id | null
}) {
  /* ROUND 5 (F6): the link back to the parent post stays on the Page this
     thread is being read on. With no Quiet navigation above it, unchanged. */
  const href = useQuietHref()
  const [expanded, setExpanded] = useState(false)
  const [clampable, setClampable] = useState(false)
  const bodyRef = useRef<HTMLDivElement>(null)
  useLayoutEffect(() => {
    const el = bodyRef.current
    if (!el) return
    setClampable(el.scrollHeight - el.clientHeight > 1)
  }, [turn.id, turn.parts])
  const home = turn.linked?.home ?? conversation
  const postHref = href(home, home === conversation ? topic : null, turn.id)
  return <div className="qc-parent-header">
    <Who show="avatar" id={turn.author} name={turn.author_alias} size={28} />
    <div className="qc-parent-meta">
      <a className="qc-parent-link" href={postHref}><strong>{turn.author_alias}</strong> <span>#{turn.number}</span></a>
      <time dateTime={new Date(turn.at * 1000).toISOString()} title={new Date(turn.at * 1000).toLocaleString()}>{ago(turn.at)}</time>
    </div>
    <div ref={bodyRef} className="qc-parent-body" data-expanded={expanded || undefined}>
      {turn.deleted ? <p className="qc-muted">This post was deleted.</p>
        : turn.parts.map((part, i) => <PostPart key={i} part={part} scope={`${turn.id}:parent:${i}`} />)}
    </div>
    {clampable && <button type="button" className="qc-parent-toggle" aria-expanded={expanded}
      onClick={() => setExpanded((e) => !e)}>{expanded ? 'Show less' : 'Show more'}</button>}
  </div>
}
