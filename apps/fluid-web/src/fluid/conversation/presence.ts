/* WORK ON A REPLY SHOWS ON ITS THREAD (A3, a missing capability).
 *
 * Who is working on which post is the one activity reader's
 * (identity/activity.ts, `working_on`: the post the run's acts are recorded
 * against -- never guessed from prose). A run answering a reply is working on
 * that reply, which the conversation column does not draw: it draws the
 * thread's root. So the root says somebody is working in its thread, and the
 * reply says it in the thread itself.
 *
 * Which thread a reply is in is its `reply_to` chain, read from the store; a
 * post being worked on that the store does not hold yet is read, with the
 * posts it answers, once. Nothing here reads activity itself. */

import { useEffect, useState } from 'react'
import { live, useActivity, type Activity } from '../identity/activity'
import { store, type Id } from '../store'
import { inThread } from './threads'

/* One read per post, shared: every card that asks is told when it is done,
   so each draws again with the chain known. */
const reaching = new Map<Id, Promise<boolean>>()

/** Read `post` and the posts it answers, as far as the store lacks them. */
function reach(post: Id): Promise<boolean> {
  let got = reaching.get(post)
  if (!got) {
    got = (async () => {
      let at: Id | null = post, read = false
      for (let i = 0; at && i < 16; i++) {
        if (!store.posts.has(at)) { await store.loadPosts([at]).catch(() => {}); read = true }
        at = store.posts.get(at)?.reply_to ?? null
      }
      return read
    })()
    reaching.set(post, got)
  }
  return got
}

/** Who is working on a post under `root` -- a reply at any depth -- not on
 *  `root` itself (that is `useWorkingOn`). */
export function useWorkingUnder(root: Id): Activity[] {
  const all = useActivity()
  const [, again] = useState(0)
  const rows = live(all).filter((a) => !!a.working_on)
  const key = rows.map((a) => a.working_on!.turn).join(',')
  useEffect(() => {
    let on = true
    void Promise.all(rows.map((a) => reach(a.working_on!.turn))).then((got) => { if (on && got.some(Boolean)) again((n) => n + 1) })
    return () => { on = false }
  }, [key])  // eslint-disable-line react-hooks/exhaustive-deps
  return rows.filter((a) => a.working_on!.turn !== root && inThread(a.working_on!.turn, root))
}
