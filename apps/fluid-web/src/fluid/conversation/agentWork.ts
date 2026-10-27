/* AGENT WORK, FOLDED AWAY BY DEFAULT (owner: "automatically hide agent work
 * chatter/follow-ups from the main conversation, with a visible control to
 * show them"). Which posts are agent work is the server's answer
 * (`agent_work` on each post, `conversation.agent_work`); whether this
 * conversation shows them is the reader's, remembered per conversation in
 * this browser. Presentation only: nothing here writes to the record. */

import { useCallback, useMemo, useSyncExternalStore } from 'react'
import { store, type Id } from '../store'
import './agentWork.css'

const KEY = 'mentis:fluid:agent-work'

function read(): Record<Id, boolean> {
  try { const v = localStorage.getItem(KEY); return v ? (JSON.parse(v) as Record<Id, boolean>) : {} } catch { return {} }
}

let shown: Record<Id, boolean> = read()
let version = 0
const heard = new Set<() => void>()

export const useAgentWork = () => useSyncExternalStore((fn) => { heard.add(fn); return () => { heard.delete(fn) } }, () => version)

/** Does this conversation show its agent work? Hidden unless the reader said. */
export const showsAgentWork = (conversation: Id | null) => !!conversation && !!shown[conversation]

export function setShowsAgentWork(conversation: Id, on: boolean) {
  shown = { ...shown }
  if (on) shown[conversation] = true
  else delete shown[conversation]
  try { localStorage.setItem(KEY, JSON.stringify(shown)) } catch { /* a convenience, not a record */ }
  version += 1
  for (const fn of [...heard]) fn()
}

/** Which of these posts are agent work, as they now read: heard again
 *  whenever any of them is read again (an owner's reply under one turns it
 *  back into the conversation). */
export function useAgentWorkIn(ids: Id[]): Set<Id> {
  const key = ids.join(',')
  const sub = useCallback((fn: () => void) => {
    const offs = key ? key.split(',').map((id) => store.subscribe('post:' + id, fn)) : []
    return () => { for (const off of offs) off() }
  }, [key])
  const got = useSyncExternalStore(sub, () => ids.filter((id) => !!store.posts.get(id)?.agent_work).join(','))
  return useMemo(() => new Set(got ? got.split(',') : []), [got])
}

/** What the post says it is, for the line over its card while shown. */
export const agentWhy = (id: Id) => store.posts.get(id)?.agent_work?.why ?? null
