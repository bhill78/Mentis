/* WHO IS WORKING, AND ON WHICH POST (combined refinement).
 *
 * Read from Mentis's own activity, through Fluid's one reader
 * (`fluid/identity/activity.ts`: `/api/activity`, woken by the pulse): a
 * live run, the conversation it runs in, and the post its acts are recorded
 * against (`working_on`) -- the record's association, never a guess. Quiet
 * shows it twice and nowhere else: a line under each composer (who is working
 * in that conversation) and a small mark beside the post being worked on.
 *
 * THE SAMPLE IS NOT A BRAIN. Its conversation shows two agents at work so the
 * presentation can be judged; those rows are made up here and marked as such
 * (`simulated`). Real conversations show only what `/api/activity` says. */
import { useSyncExternalStore } from 'react'
import { live, useActivity, type Activity } from '../fluid/identity/activity'
import { store } from '../fluid/store'
import { postOf } from './real'
import { PEOPLE, type Id } from './sample'

export interface Working {
  /** the run, else the participant: what tells two entries apart */
  key: string
  participant: Id
  alias: string
  runtime: string | null
  /** the post its work is recorded against, where the record says */
  post: Id | null
  /** that post's number, as the record gives it */
  number?: number | null
  conversation: Id | null
  /** what the run says it is doing now, in its own words */
  doing: string | null
  simulated?: boolean
}

const of = (a: Activity): Working => ({
  key: a.run ?? a.participant,
  participant: a.participant,
  alias: a.alias,
  runtime: a.runtime ?? null,
  post: a.working_on?.turn ?? null,
  number: a.working_on?.number ?? null,
  conversation: a.conversation ?? a.working_on?.conversation ?? null,
  doing: a.runs?.[0]?.words ?? a.runs?.[0]?.activity ?? null,
})

/** The sample conversation's made-up work, for judging the presentation. */
const SAMPLE: Working[] = [
  { key: 'sample-quill', participant: PEOPLE.quill.id, alias: PEOPLE.quill.name, runtime: 'claude', post: 'p3', conversation: 'sample', doing: 'drafting three invitations', simulated: true },
  { key: 'sample-reviewer', participant: PEOPLE.reviewer.id, alias: PEOPLE.reviewer.name, runtime: 'codex', post: 'p5', conversation: 'sample', doing: 'checking the site figures', simulated: true },
]

/** Everyone working now, one entry per run (the sample's simulated work
 *  included when `sample` is asked for). */
export function useWorking(sample: boolean): Working[] {
  const all = useActivity()
  const real = live(all).map(of)
  return sample ? [...real, ...SAMPLE] : real
}

/** Who is working in `conversation` ('sample' for the sample). */
export const workingIn = (ws: Working[], conversation: Id | null) =>
  conversation ? ws.filter((w) => w.conversation === conversation) : []

/** Who is working on `post`. */
export const workingOn = (ws: Working[], post: Id) => ws.filter((w) => w.post === post)

/* -- work under a thread ---------------------------------------------------
   A top-level post in the flow says when work is going on somewhere in its
   thread -- on one of its replies, not on itself. Which thread a working
   post belongs to is read from the record: Quiet's store where it holds the
   post, else Fluid's posts (`reply_to`, walked up to the post that answers
   nothing). Presentation only: who works on what is unchanged. */
const rootOfPost = new Map<Id, Id>()
const asking = new Set<Id>()
let rootsVersion = 0
const rootsHeard = new Set<() => void>()
const rootsSub = (fn: () => void) => { rootsHeard.add(fn); return () => { rootsHeard.delete(fn) } }

async function findRoot(post: Id): Promise<void> {
  if (asking.has(post) || rootOfPost.has(post)) return
  asking.add(post)
  try {
    let at: Id = post
    for (let i = 0; i < 64; i++) {
      const held = postOf(at)
      if (held?.root) { at = held.root; break }
      await store.loadPosts([at])
      const up: Id | null = store.posts.get(at)?.reply_to ?? null
      if (!up) break
      at = up
    }
    rootOfPost.set(post, at)
    rootsVersion++
    rootsHeard.forEach((fn) => fn())
  } catch { /* unreadable for now: no aggregate is shown, nothing is guessed */ } finally { asking.delete(post) }
}

/** The root of a held post's thread: its own word for it, else up its
 *  held parents to the one that answers nothing; undefined past what is held. */
function heldRoot(id: Id): Id | undefined {
  let p = postOf(id)
  for (let i = 0; p && i < 64; i++) {
    if (p.root) return p.root
    if (!p.replyTo) return p.id
    p = postOf(p.replyTo)
  }
  return undefined
}

/** The thread each working post belongs to, as far as it is known yet. */
export function useWorkRoots(ws: Working[]): Map<Id, Id> {
  useSyncExternalStore(rootsSub, () => rootsVersion)
  const out = new Map<Id, Id>()
  for (const w of ws) {
    if (!w.post) continue
    const root = heldRoot(w.post)
    if (root) { out.set(w.post, root); continue }
    const known = rootOfPost.get(w.post)
    if (known) out.set(w.post, known)
    else if (!w.simulated) void findRoot(w.post)
  }
  return out
}

/** Work going on in `root`'s thread on a post other than `root` itself. */
export const workUnder = (ws: Working[], roots: Map<Id, Id>, root: Id) =>
  ws.filter((w) => w.post && w.post !== root && roots.get(w.post) === root)
