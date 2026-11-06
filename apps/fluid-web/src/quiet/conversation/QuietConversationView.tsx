import { useEffect, useState } from 'react'
import { read, type Batch, type Conversation, type Id, type Turn } from '../../api'
import { QuietPost } from './QuietPost'
import { QuietThread } from './QuietThread'
import './quiet-conversation.css'

const DEFAULT_BATCH = 40

export interface QuietConversationViewProps {
  /** Which Mentis Conversation to show. Nothing else identifies a place: the
   *  shell (Track A) drops this straight into its `content` slot with the
   *  id the nav track (Track B) currently has selected. */
  conversationId: Id
  /** A thread root to open immediately, as though its reply count had just
   *  been clicked -- for a deep link into one reply chain. Must be a thread
   *  ROOT's id (`Turn.root`), not any reply inside it; resolving a bare Turn
   *  id to its root is for whoever has that id in hand to do first. */
  focusRoot?: Id | null
  /** The reply composer's hook point. Track D owns the composer itself; this
   *  only says which post a reply was asked for. Omit it and no Reply
   *  control is drawn. */
  onReply?: (postId: Id) => void
}

interface LoadState {
  conversation: Conversation | null
  turns: Turn[]
  batch: Batch | null
  error: string | null
  loading: boolean
}

const EMPTY: LoadState = { conversation: null, turns: [], batch: null, error: null, loading: false }

/** Reads a Mentis conversation's posts and lets a reply chain be opened and
 *  read on its own, however many replies it holds. Preserves the shapes the
 *  record itself keeps apart: a post belongs to one Conversation, may carry
 *  Topics, and sits in a thread rooted at some post (possibly itself) -- none
 *  of that is flattened or re-derived here, only displayed as the API gives
 *  it (`src/api.ts`'s `Turn`, `Conversation`). */
export function QuietConversationView({ conversationId, focusRoot = null, onReply }: QuietConversationViewProps) {
  const [state, setState] = useState<LoadState>(EMPTY)
  const [openRoot, setOpenRoot] = useState<Id | null>(focusRoot)

  useEffect(() => {
    setOpenRoot(focusRoot)
  }, [conversationId, focusRoot])

  useEffect(() => {
    let live = true
    setState({ ...EMPTY, loading: true })
    read<Conversation>(`/api/conversations/${encodeURIComponent(conversationId)}?batch=${DEFAULT_BATCH}`)
      .then((conv) => {
        if (!live) return
        setState({ conversation: conv, turns: conv.turns, batch: conv.batch ?? null, error: null, loading: false })
      })
      .catch((e: Error) => { if (live) setState({ ...EMPTY, error: e.message }) })
    return () => { live = false }
  }, [conversationId])

  const loadOlder = () => {
    const earliest = state.turns[0]
    if (!earliest) return
    setState((s) => ({ ...s, loading: true }))
    read<Conversation>(`/api/conversations/${encodeURIComponent(conversationId)}?before=${encodeURIComponent(earliest.id)}&batch=${DEFAULT_BATCH}`)
      .then((conv) => {
        setState((s) => ({
          conversation: s.conversation,
          turns: [...conv.turns, ...s.turns],
          batch: conv.batch ?? s.batch,
          error: null,
          loading: false,
        }))
      })
      .catch((e: Error) => setState((s) => ({ ...s, loading: false, error: e.message })))
  }

  const topicNames = new Map((state.conversation?.topics ?? []).map((t) => [t.id, t.name] as const))

  if (state.error) return <div className="qc-view"><p className="qc-state">Could not read this conversation: {state.error}</p></div>
  if (openRoot) {
    return (
      <div className="qc-view">
        <QuietThread
          conversationId={conversationId}
          root={openRoot}
          topicNames={topicNames}
          onBack={() => setOpenRoot(null)}
          onReply={onReply}
        />
      </div>
    )
  }

  return (
    <div className="qc-view">
      {state.loading && state.turns.length === 0 && <p className="qc-state">Reading…</p>}
      {!state.loading && state.turns.length === 0 && state.conversation && (
        <p className="qc-state">Nobody has posted here yet.</p>
      )}
      {(state.batch?.older ?? 0) > 0 && (
        <button type="button" className="qc-edge" onClick={loadOlder} disabled={state.loading}>
          {state.loading ? 'Reading…' : `Show ${state.batch!.older} earlier`}
        </button>
      )}
      <div className="qc-posts">
        {state.turns.map((t) => (
          <QuietPost
            key={t.id}
            turn={t}
            topicNames={topicNames}
            onOpenThread={setOpenRoot}
            onReply={onReply}
          />
        ))}
      </div>
    </div>
  )
}
