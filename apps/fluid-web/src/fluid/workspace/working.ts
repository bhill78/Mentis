/* WHO IS WORKING ON WHAT A ZONE SHOWS (#568 4.6; FW #1: "show independent
 * activity states when agents are updating zone content").
 *
 * A zone whose posts -- the one it follows, its thread's replies, or the
 * posts of what is kept in it -- are one an execution is working on shows
 * that, quietly, in its caption: what it shows may change. Nothing is
 * inferred from silence: no `working_on`, no state.
 *
 * Read by Fluid's one activity reader (identity/activity.ts), the same read
 * the column and its cards use; this only shapes its rows for the zones. */

import { useMemo } from 'react'
import { useActivity, workingOnPosts } from '../identity/activity'
import type { Id } from '../store'

export interface Working { participant: Id; alias: string; turn: Id; number: number | null; since: number | null }

/** Every live execution working on one of `posts`, as the record says. */
export function useWorkingOn(posts: Id[]): Working[] {
  const all = useActivity()
  return useMemo(() => workingOnPosts(all, posts).map((a) => ({
    participant: a.participant, alias: a.alias, turn: a.working_on!.turn,
    number: a.working_on!.number, since: a.working_on!.since ?? null,
  })), [all, posts])
}
