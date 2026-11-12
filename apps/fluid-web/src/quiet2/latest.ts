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
  return (await readRecent(conversation, 1))[0] ?? null
}

/** One of the conversation's newest posts, as the Latest read says it. */
export interface RecentPost extends Activity {
  author: string | null
  excerpt: string | null
}

/** How many of the newest posts the picker reads: bounded, one read. */
export const RECENT_READ = 50

/** The conversation's newest posts, newest first (the server's Latest read,
 *  at most 50 by its own bound), each with the top of its thread. */
export async function readRecent(conversation: Id, limit = RECENT_READ): Promise<RecentPost[]> {
  const r = await fetch(`/fluid/api/latest?conversation=${encodeURIComponent(conversation)}&limit=${limit}&agent_work=1`, { headers: CLIENT_HEADERS })
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`)
  const j = await r.json() as { items?: { id: Id; number?: number | null; at?: number | null; root?: Id | null; author_alias?: string | null; excerpt?: string | null }[]; error?: string }
  if (j.error) throw new Error(j.error)
  return (j.items ?? []).map((it) => ({ id: it.id, number: it.number ?? null, at: it.at ?? null, root: it.root ?? null, author: it.author_alias ?? null, excerpt: it.excerpt ?? null }))
}

/* -- WHERE WORK LAST ENDED: one destination per reply chain ----------------
   A reply chain is a thread: a top-level post and every reply under it
   (the server's `root`). The picker offers each chain once, at its newest
   post -- not every post that moved -- newest first: the chains that moved
   within the last hour, and always the conversation's newest post, however
   long ago. */

/** How recent a chain's last post must be to be offered (seconds). */
export const CHAIN_WINDOW = 3600

export interface Chain {
  /** the top of the chain (its thread) */
  root: Id
  /** its newest post: the destination */
  newest: RecentPost
  /** how many of the posts read are in it */
  posts: number
  /** this is the conversation's newest post */
  latest: boolean
}

/** The chains to offer, from the newest posts (any order), at `now` (epoch s). */
export function chainsOf(recent: RecentPost[], now: number, window = CHAIN_WINDOW): Chain[] {
  const by = new Map<Id, Chain>()
  for (const p of recent) {
    const root = p.root ?? p.id
    const had = by.get(root)
    if (!had) by.set(root, { root, newest: p, posts: 1, latest: false })
    else { had.posts++; if (newer(p, had.newest)) had.newest = p }
  }
  const all = [...by.values()].sort((a, b) => (newer(a.newest, b.newest) ? -1 : newer(b.newest, a.newest) ? 1 : 0))
  if (!all.length) return []
  all[0].latest = true
  return all.filter((c, i) => i === 0 || (c.newest.at != null && now - c.newest.at <= window))
}

/** The words of the posts named (Fluid's posts read), for chains' subjects. */
export async function readWords(ids: Id[]): Promise<Map<Id, string>> {
  const out = new Map<Id, string>()
  if (!ids.length) return out
  const r = await fetch(`/fluid/api/posts?ids=${ids.map(encodeURIComponent).join(',')}`, { headers: CLIENT_HEADERS })
  if (!r.ok) return out
  const j = await r.json().catch(() => null) as { posts?: { id: Id; parts?: { type?: string; text?: string }[] }[] } | null
  for (const p of j?.posts ?? []) out.set(p.id, (p.parts ?? []).filter((x) => x.type === 'text' || x.type === undefined).map((x) => x.text ?? '').join(''))
  return out
}

/** A chain's subject: the first line of words its starter holds, without
 *  Markdown's heading marks or emphasis, kept short. */
export function subjectOf(text: string | null | undefined, max = 80): string {
  const line = (text ?? '').split(/\r?\n/).map((l) => l.trim()).find((l) => l.length) ?? ''
  const plain = line.replace(/^#{1,6}\s+/, '').replace(/^[>*-]\s+/, '').replace(/[*_`]+/g, '').trim()
  return plain.length > max ? plain.slice(0, max - 1).trimEnd() + '…' : plain
}
