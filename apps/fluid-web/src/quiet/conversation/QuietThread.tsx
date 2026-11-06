import type { Id } from '../../api'
import { QuietPost } from './QuietPost'
import { useThread } from './thread'

export interface QuietThreadProps {
  conversationId: Id
  root: Id
  topicNames?: Map<Id, string>
  onBack: () => void
  onReply?: (postId: Id) => void
}

/** One thread, opened on its own: the root post, then every reply under it
 *  in order. Reached from a post's reply count (`QuietPost.onOpenThread`);
 *  this is the one place a many-reply thread is actually read in full, kept
 *  apart from the Conversation's own feed so opening it is never the price
 *  of opening the Conversation. */
export function QuietThread({ conversationId, root, topicNames, onBack, onReply }: QuietThreadProps) {
  const { data, error, loading } = useThread(conversationId, root)
  return (
    <div className="qc-thread">
      <button type="button" className="qc-back" onClick={onBack}>&larr; Back to conversation</button>
      {loading && !data && <p className="qc-state">Reading this thread…</p>}
      {error && <p className="qc-state">Could not read this thread: {error}</p>}
      {data && (
        <>
          <div className="qc-thread-root">
            <QuietPost turn={data.turn} topicNames={topicNames} onReply={onReply} />
          </div>
          <div className="qc-replies">
            {data.replies.map((r) => (
              <div key={r.id} className="qc-reply">
                {r.answering_number != null && r.answering !== root && (
                  <p className="qc-reply-of">replying to #{r.answering_number}</p>
                )}
                <QuietPost turn={r} topicNames={topicNames} onReply={onReply} />
              </div>
            ))}
            {data.replies.length === 0 && <p className="qc-state">No replies yet.</p>}
          </div>
        </>
      )}
    </div>
  )
}
