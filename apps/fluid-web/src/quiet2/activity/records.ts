/* WHAT THE ACTIVITY PANEL READS ABOUT A RUN, A POST AND A CONVERSATION.
 *
 * Every helper here is a view over a read Fluid's store already makes; none
 * asks anything new of the server:
 *   a run          `/fluid/api/runs?ids=` (store.loadRuns / store.runs)
 *   a post         `/fluid/api/posts?ids=` (store.loadPosts / store.posts)
 *   a conversation `/fluid/api/conversations?ids=` (store.loadConversations)
 * and each re-renders on the store's own key for it (`run:`, `post:`,
 * `conv:`), so the change loop (store.follow) keeps them current.
 *
 * A RUN'S STATE IS THE SERVER'S (mentis/operational/runs.py `run_state`), not
 * a reading of it here. Closed by the record: completed, recovered (it
 * SUCCEEDED; its end was read back), stopped (the session was cancelled; the
 * work stays open), failed, superseded. Open by the record: running,
 * no-event, not-launched, not-running, runtime-ended (returned, its end not
 * recorded yet) and unknown (no process here holds it). */
import { useCallback, useEffect, useSyncExternalStore } from 'react'
import { store, type Id, type Post, type RunItem } from '../../fluid/store'
import { repairText } from '../text'

/** What `/fluid/api/runs` sends beyond the store's own type. */
export type Run = RunItem & { words?: string | null; expectation?: Id | null; source?: string | null }

/** States the record has closed: the run is over. */
export const ENDED = new Set(['completed', 'recovered', 'stopped', 'failed', 'superseded'])
/** Of the open states, the ones that are work going on now (Fluid's Home,
 *  sections/activity.tsx RUN_LIVE, with the server's `no-event`). */
export const ACTIVE = new Set(['running', 'no-event', 'active', 'performing'])

/** A run's line: closed runs by their end, open ones by their start. */
export const isEnded = (r: Pick<RunItem, 'state' | 'ended_at'>) => r.ended_at != null || ENDED.has(r.state)

/** "claude (claude-sonnet-5)"; a run that names no model says only its
 *  runtime (Home's RunCard says the same). */
export const runtimeModel = (runtime?: string | null, model?: string | null) =>
  [runtime, model ? `(${model})` : ''].filter(Boolean).join(' ') || null

/** The server's words for a state, without the clock time it ends with
 *  (" · 2026-11-08 21:58:57" or "· 21:58:57"): the row says the time itself. */
export const stateWords = (words: string | null | undefined) =>
  words ? repairText(words).replace(/\s*·\s*(\d{4}-\d{2}-\d{2} )?\d{2}:\d{2}:\d{2}\s*$/, '') : null

const subscribeKey = (key: string) => (fn: () => void) => store.subscribe(key, fn)

/** One run as the store holds it, read if it is not held. */
export function useRun(id: Id | null | undefined): Run | undefined {
  const sub = useCallback((fn: () => void) => (id ? store.subscribe('run:' + id, fn) : () => {}), [id])
  const run = useSyncExternalStore(sub, () => (id ? store.runs.get(id) : undefined)) as Run | undefined
  useEffect(() => { if (id && !store.runs.has(id)) void store.loadRuns([id]).catch(() => {}) }, [id])
  return run
}

/** One post as the store holds it, read if it is not held. */
export function usePost(id: Id | null | undefined): Post | undefined {
  const sub = useCallback((fn: () => void) => (id ? store.subscribe('post:' + id, fn) : () => {}), [id])
  const post = useSyncExternalStore(sub, () => (id ? store.posts.get(id) : undefined))
  useEffect(() => { if (id && !store.posts.has(id)) void store.loadPosts([id]).catch(() => {}) }, [id])
  return post
}

const askedConv = new Set<Id>()
/** A conversation's name as the store holds it, read once if it is not held. */
export function useConvName(id: Id | null | undefined, given?: string | null): string {
  const sub = useCallback((fn: () => void) => (id ? subscribeKey('conv:' + id)(fn) : () => {}), [id])
  const name = useSyncExternalStore(sub, () => (id ? store.conversations.get(id)?.name ?? null : null))
  useEffect(() => {
    if (!id || given || store.conversations.has(id) || askedConv.has(id)) return
    askedConv.add(id)
    void store.loadConversations([id]).catch(() => {})
  }, [id, given])
  return repairText(given || name || '') || (id ? 'A conversation' : 'No conversation')
}

/** A post's own first line, as written: its first text part's first line
 *  that says something, markdown's leading marks dropped. Null where the
 *  post has no text (or is not read yet). Never a summary. */
export function firstLine(p: Post | undefined, max = 160): string | null {
  if (!p || p.deleted) return null
  for (const part of p.parts ?? []) {
    if (typeof part.text !== 'string') continue
    for (const raw of part.text.split('\n')) {
      const line = raw.replace(/^\s*(#{1,6}\s+|[-*>]\s+|\d+[.)]\s+)/, '').replace(/[*_`]{1,3}/g, '').trim()
      if (!line) continue
      const s = repairText(line)
      return s.length > max ? s.slice(0, max - 1).trimEnd() + '…' : s
    }
  }
  return null
}
