/* PACKAGE E owns this module: one post, whole -- its header, its reply
   indicators, its body and its footer. At P0 it renders what Quiet rendered
   before the split.

   WHAT E CHANGES. §8 and the rest of §1: a wide table scrolling inside the
   column rather than widening it, Quiet's own .qc-body .pr-* prose rules in
   prose.css instead of any dependency on .turn-body, and an ordering over
   computed size, weight and contrast across author, number, timestamp, edited,
   reply indicator and footer. The content must not change: `untrusted` stays
   on, and a post's extracted text is the same before and after. */
import { ago, type Conversation, type Id, type Turn } from '../../api'
import { Who } from '../../fluid/identity/Who'
import { href } from '../model'
import PostPart from './parts'
import './post.css'
import './prose.css'

export default function Post({ turn, conversation, topic, topics, inThread = false, selected = false, onReply, answeringAuthor }: {
  turn: Turn; conversation: Id; topic: Id | null; topics: Conversation['topics']
  inThread?: boolean; selected?: boolean; onReply?: () => void
  /** the alias of whoever wrote what this answers, when it is already in hand
   *  (the Thread view has every row loaded); omitted, the reply line still
   *  names the post it answers, just not who wrote it. */
  answeringAuthor?: string | null
}) {
  const home = turn.linked?.home ?? conversation
  const postHref = href(home, home === conversation ? topic : null, turn.id)
  const repliesCount = turn.thread_replies ?? 0
  return <article className="qc-post" id={`qc-post-${turn.id}`} aria-label={`Post ${turn.number} by ${turn.author_alias}`} data-selected={selected || undefined}>
    <header><Who show="avatar" id={turn.author} name={turn.author_alias} size={24} />
      <strong>{turn.author_alias}</strong><a href={postHref}>#{turn.number}</a>
      <time dateTime={new Date(turn.at * 1000).toISOString()} title={new Date(turn.at * 1000).toLocaleString()}>{ago(turn.at)}</time>
      {turn.revision && <small>edited</small>}</header>
    {turn.linked && <p className="qc-context">Linked from <a href={href(home, null, turn.id)}>another conversation ↗</a></p>}
    {turn.answering && <p className="qc-reply-line">
      <a href={href(home, home === conversation ? topic : null, turn.answering)}>
        <span aria-hidden="true">↳</span> replying to{answeringAuthor ? ` @${answeringAuthor.replace(/^@/, '')} ·` : ''} #{turn.answering_number ?? 'post'}
      </a>
    </p>}
    <div className="qc-body">{turn.deleted ? <p className="qc-muted">This post was deleted.</p>
      : turn.parts.map((part, i) => <PostPart key={i} part={part} scope={`${turn.id}:part:${i}`} />)}</div>
    <footer>
      <a className="qc-post-reply" href={postHref} onClick={onReply ? (e) => { e.preventDefault(); onReply() } : undefined}>
        {inThread ? 'Reply to this post' : repliesCount
          ? <><span aria-hidden="true">↳</span> {repliesCount} {repliesCount === 1 ? 'reply' : 'replies'}</>
          : 'Reply'}
      </a>
      {turn.topics.map((id) => {
        const t = topics.find((t) => t.id === id)
        return t && home === conversation ? <a key={id} href={href(conversation, id)}># {t.name}</a> : null
      })}
    </footer>
  </article>
}
