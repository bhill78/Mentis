/* THE NEWEST ACTIVITY IN A CONVERSATION, for Go to latest (usability 5.6).
 *
 * WHAT "NEWEST" MEANS: the post recorded last in the conversation, replies
 * included -- which may be a reply to a reply deep inside an old thread, not
 * a top-level post. The conversation's page is ordered by thread, so that
 * post can be far from the bottom, folded away, or not read at all.
 *
 * WHERE IT COMES FROM: the server's existing read for exactly this question,
 * Fluid's Latest (`GET /fluid/api/latest?conversation=<id>&limit=1`,
 * mentis/fluid/latest.py: newest by record position, each with its thread's
 * top), with agent work kept in (`agent_work=1`) because Quiet Chat shows
 * agents' posts. It is read when the conversation is read (and read again
 * after a post); posts this page has read since -- a reply just made in a
 * thread -- are weighed against it, so the newer of the two wins. Within one
 * conversation a post's number is its place in the record, so the higher
 * number is the newer; the time decides only where a number is missing. */
import { CLIENT_HEADERS } from '../api'
import type { Id, Post } from './sample'

export interface Activity {
  id: Id
  /** its number in its conversation (record order) */
  number: number | null
  /** when it was recorded, epoch seconds */
  at: number | null
  /** the top of its thread (itself for a top-level post), where known */
  root: Id | null
}

/** Whether `a` is newer than `b` (same conversation). */
export function newer(a: Activity, b: Activity): boolean {
  if (a.number != null && b.number != null && a.number !== b.number) return a.number > b.number
  if (a.at != null && b.at != null && a.at !== b.at) return a.at > b.at
  return false
}

/** The newest of what is known; null when nothing is. */
export function newestOf(xs: (Activity | null | undefined)[]): Activity | null {
  let best: Activity | null = null
  for (const x of xs) if (x && (!best || newer(x, best))) best = x
  return best
}

/** A post this page holds, as activity. */
export const activityOf = (p: Post): Activity => ({ id: p.id, number: p.number ?? null, at: p.atTime ?? null, root: p.root ?? (p.replyTo ? null : p.id) })

/** The conversation's newest post, from the server's Latest read. */
export async function readNewest(conversation: Id): Promise<Activity | null> {
  const r = await fetch(`/fluid/api/latest?conversation=${encodeURIComponent(conversation)}&limit=1&agent_work=1`, { headers: CLIENT_HEADERS })
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`)
  const j = await r.json() as { items?: { id: Id; number?: number | null; at?: number | null; root?: Id | null; deleted?: boolean }[]; error?: string }
  if (j.error) throw new Error(j.error)
  const it = j.items?.[0]
  return it ? { id: it.id, number: it.number ?? null, at: it.at ?? null, root: it.root ?? null } : null
}
