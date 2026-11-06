import { useState } from 'react'
import { ago, initial, whoColour, type Id, type Turn } from '../../api'
import { Prose } from '../../prose'
import { turnPartScope } from '../../experimental/objects'
import { textOf } from './text'

/** Long enough that a reader benefits from "Show more" rather than scrolling
 *  past a wall of text to reach the next post. Not a hard limit: it only
 *  decides whether the post opens collapsed. */
const LONG = 700

export interface QuietPostProps {
  turn: Turn
  /** this post's Topics, resolved to names by the caller (`Conversation.topics`). */
  topicNames?: Map<Id, string>
  /** Present (and shown) only on a thread root with replies to open. */
  onOpenThread?: (root: Id) => void
  /** The reply composer's hook point (Track D owns the composer itself). */
  onReply?: (postId: Id) => void
}

/** One post: who wrote it, when, its words in full, and -- where this is a
 *  thread root -- how to open its replies. No border, no card: spacing and a
 *  faint rule under the avatar line are what separate one post from the
 *  next. */
export function QuietPost({ turn, topicNames, onOpenThread, onReply }: QuietPostProps) {
  const [expanded, setExpanded] = useState(false)
  if (turn.deleted) {
    return (
      <div className="qc-post">
        <p className="qc-meta">#{turn.number} · deleted</p>
      </div>
    )
  }
  const words = textOf(turn)
  const long = !expanded && words.length > LONG
  const topics = (turn.topics ?? []).map((t) => topicNames?.get(t)).filter((n): n is string => !!n)
  return (
    <article className="qc-post">
      <div className="qc-post-head">
        <span className="qc-avatar" style={{ background: whoColour(turn.author) }}>
          {initial(turn.author_alias)}
        </span>
        <span className="qc-author">{turn.author_alias}</span>
        <span className="qc-meta">#{turn.number} · {ago(turn.at)}</span>
      </div>
      {topics.length > 0 && (
        <div className="qc-topics">
          {topics.map((name) => <span key={name} className="qc-topic">{name}</span>)}
        </div>
      )}
      <div className={long ? 'qc-body qc-clamped' : 'qc-body'}>
        <Prose src={words} scope={turnPartScope(turn.id, 0)} />
      </div>
      {long && (
        <button type="button" className="qc-more" onClick={() => setExpanded(true)}>
          Show more
        </button>
      )}
      <div className="qc-foot">
        {onOpenThread && (turn.thread_replies ?? 0) > 0 && (
          <button type="button" className="qc-thread-open" onClick={() => onOpenThread(turn.root ?? turn.id)}>
            {turn.thread_replies} {turn.thread_replies === 1 ? 'reply' : 'replies'}
          </button>
        )}
        {onReply && (
          <button type="button" className="qc-reply-hook" onClick={() => onReply(turn.id)}>
            Reply
          </button>
        )}
      </div>
    </article>
  )
}
