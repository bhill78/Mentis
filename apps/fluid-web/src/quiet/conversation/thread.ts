import { useEffect, useState } from 'react'
import { read, type Id, type Turn } from '../../api'

/** `GET /api/conversations/<id>/thread/<root>` -- one thread's root and every
 *  reply under it, whole. The Conversation read only ever carries thread
 *  roots (`mentis/web/__init__.py`, "the flow renders thread roots; replies
 *  live in the thread rail"), so a many-reply thread is never the price of
 *  opening the Conversation it sits in -- it is its own, separate read. */
export interface ThreadRead {
  conversation: Id
  root: Id
  turn: Turn
  replies_total: number
  replies: Turn[]
}

interface ThreadState {
  data: ThreadRead | null
  error: string | null
  loading: boolean
}

/** One thread, read fresh whenever `conversation` or `root` changes. Not a
 *  live reader (`useApi`): a thread opened to read is not expected to track
 *  an agent working elsewhere the way the Conversation's own feed does, and
 *  the four parallel tracks' shared contract is `api.ts` + `address.ts`, not
 *  a new live-reread policy. */
export function useThread(conversation: Id | null, root: Id | null): ThreadState {
  const [state, setState] = useState<ThreadState>({ data: null, error: null, loading: false })
  useEffect(() => {
    if (!conversation || !root) {
      setState({ data: null, error: null, loading: false })
      return
    }
    let live = true
    setState({ data: null, error: null, loading: true })
    read<ThreadRead>(`/api/conversations/${encodeURIComponent(conversation)}/thread/${encodeURIComponent(root)}`)
      .then((got) => { if (live) setState({ data: got, error: null, loading: false }) })
      .catch((e: Error) => { if (live) setState({ data: null, error: e.message, loading: false }) })
    return () => { live = false }
  }, [conversation, root])
  return state
}
