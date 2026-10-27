/* WHO IS WORKING HERE, AND ON WHICH POST (#568 4.6; FW #1, UX #548).
 *
 * Read by Fluid's one activity reader (identity/activity.ts: `/api/activity`,
 * woken by the pulse as Production's Presence is). This only keeps the hooks
 * the column and the cards already call. The column says which conversation
 * it shows (`useWorking`); a card only listens (`useWorkingOn`). When the
 * conversation's own count of work moves on the change feed, the reader is
 * asked again at once. */

import { useConversation } from './hooks'
import { atAlias, useActivity, useActivityPoke, workingIn, workingOnPosts, type Activity } from '../identity/activity'
import { store, type Id } from '../store'

export type Working = Activity

/** Who is working in `here`, read for it: the column calls this once. */
export function useWorking(here: Id | null): Working[] {
  const conv = useConversation(here)
  const all = useActivity()
  useActivityPoke(here ? conv?.working ?? 0 : undefined)
  return here && all ? workingIn(all, here) : []
}

/** Who is working on post `id`, by the record. Reads nothing itself. */
export function useWorkingOn(id: Id): Working[] {
  return workingOnPosts(useActivity(), [id])
}

export const aliasOf = (a: Working) => atAlias(a.alias)

/** "@Caretaker is working", "@A and @B are working", "@A and 2 others are working" */
export function workingLine(ws: Working[]): string {
  if (ws.length === 1) return `${aliasOf(ws[0])} is working`
  if (ws.length === 2) return `${aliasOf(ws[0])} and ${aliasOf(ws[1])} are working`
  return `${aliasOf(ws[0])} and ${ws.length - 1} others are working`
}

/** The post a participant's work is on, if this conversation holds it. */
export const postOf = (a: Working) => (a.working_on && store.posts.has(a.working_on.turn) ? a.working_on.turn : null)
