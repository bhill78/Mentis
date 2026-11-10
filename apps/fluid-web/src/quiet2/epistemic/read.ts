/* THE EPISTEMIC RECORDS THAT BELONG TO A POST, read from the Ladder Mentis
 * already keeps (mentis/web/ladder.py), never inferred.
 *
 * WHICH RECORDS. Two relationships the record itself states, and nothing
 * else -- no likeness of wording or subject ever associates anything:
 *   recorded   the act that recorded it names this post as the Turn it was
 *              recorded in the work of (`recorded_by.turn`,
 *              conversation/ladder.py `recorded_by`): a record made while an
 *              agent worked on what this post asked.
 *   cites      one of its own basis links points at this post
 *              (`basis[].ref`, `basis_of`): `extracted-from`,
 *              `derived-from`, or `outcome-of` (an outcome of this post's
 *              work).
 * A record that stands in both is ONE record with both relations, said
 * beside it; it is counted once. A record that only rests on another record
 * from this post (lineage) is that record's descendant, not this post's: its
 * detail shows the lineage, the post's count does not include it.
 *
 * WHAT IS READ. Once per conversation, both Ladder lists filtered by the
 * conversation the recording act names (`/api/ladder/items?conversation=`
 * and `/api/ladder/adopted?conversation=`), together everything Learning and
 * Adopted show for it, page by page until each list's `total`. The
 * conversation is the post's HOME (`homeOf`), not the one it is being read
 * in: a post linked into another conversation was worked on from its own.
 * Read when the first post of that conversation asks, shared by every post
 * (and every drawing of a post) after.
 *
 * READ AGAIN ONLY WHEN MATERIAL MOVED THERE. The pulse already says where the
 * record moved (`/api/pulse?since=`, mentis/web/moved.py): `governed` when a
 * `material-*` or `governance-*` act was written (recording, adopting,
 * challenging), with the conversations it was written in. That, naming this
 * conversation -- or a move the pulse could not place (`loose`, none) --
 * schedules a reread, no sooner than SPACING after the last one began (on
 * DAY-TO-DAY the two reads take seconds). A post, a run's chatter or the
 * conversation list being read again is not a change here. A read that
 * failed is tried again on the next such move, or when a post next asks.
 *
 * WHAT IT MISSES, SAID PLAINLY: a record recorded from ANOTHER
 * conversation's work that cites this post as its basis (7 of 473 post
 * citations on DAY-TO-DAY, 2026-11-10); a record recorded in the work of
 * this post from a conversation other than the post's home (the act names
 * where the work was done); and material neither list shows (the notes
 * holding a request's or decline's reason, which are not ladder material).
 * One whole-Brain read would catch the first two at many times the cost; it
 * is not made. Past PAGES pages of a list the count is said as "at least".
 *
 * READ-ONLY. Nothing here writes, and nothing here decides what a record
 * is: kind, status, challenges and outcomes are the server's. */
import { useCallback, useEffect, useState, useSyncExternalStore } from 'react'
import { CLIENT_HEADERS } from '../../api'
import type { LadderItem, LadderItemDetail, LadderItemsResponse } from '../../fluid/governance/ladderTypes'
import { hearPulse, type Where } from '../../fluid/identity/activity'
import { store, type Id } from '../../fluid/store'

/** How a record is this post's, in the record's own terms. */
export type Relation = 'recorded' | 'extracted-from' | 'derived-from' | 'outcome-of'
const CITES = new Set<string>(['extracted-from', 'derived-from', 'outcome-of'])

/** One record beside one post, with every way it is that post's. */
export interface Held { item: LadderItem; relations: Relation[] }

/** A conversation's records, by the post each belongs to. */
interface Read { byPost: Map<Id, Held[]>; at: number; truncated: boolean }
interface Conv {
  read: Read | null
  error: string | null
  out: Promise<void> | null
  began: number
  timer: number
  listeners: Set<() => void>
  unfollow: (() => void) | null
}

/** No two reads of one conversation begin closer together than this. */
const SPACING = 20000
const LIMIT = 1000
/** Pages of one list read before the rest is said as "at least". */
const PAGES = 10
const convs = new Map<Id, Conv>()

async function getJson<T>(path: string): Promise<T> {
  const r = await fetch(path, { headers: { ...CLIENT_HEADERS } })
  const body = await r.json().catch(() => null) as (T & { error?: string }) | null
  if (!r.ok || !body || body.error) throw new Error(body?.error ?? r.statusText ?? 'the record did not answer')
  return body
}

/** Every record of a conversation, placed beside the posts it states. */
function index(items: LadderItem[]): Map<Id, Held[]> {
  const byPost = new Map<Id, Map<Id, Held>>()
  const add = (post: Id | null | undefined, item: LadderItem, rel: Relation) => {
    if (!post) return
    let here = byPost.get(post)
    if (!here) byPost.set(post, (here = new Map()))
    const held = here.get(item.id)
    if (!held) here.set(item.id, { item, relations: [rel] })
    else if (!held.relations.includes(rel)) held.relations.push(rel)
  }
  const seen = new Set<Id>()
  for (const item of items) {
    /* the two lists never share an entry, but a record is a record once */
    if (seen.has(item.id)) continue
    seen.add(item.id)
    add(item.recorded_by?.turn, item, 'recorded')
    /* a post is a Turn: an entry of Kind `contribution` */
    for (const b of item.basis ?? []) if (CITES.has(b.relation) && b.kind === 'contribution') add(b.ref, item, b.relation as Relation)
  }
  return new Map([...byPost].map(([p, m]) => [p, [...m.values()]]))
}

function conv(id: Id): Conv {
  let c = convs.get(id)
  if (!c) convs.set(id, (c = { read: null, error: null, out: null, began: 0, timer: 0, listeners: new Set(), unfollow: null }))
  return c
}

const tell = (c: Conv) => { for (const fn of [...c.listeners]) fn() }

/** One Ladder list of one conversation, every page of it up to PAGES. */
async function readList(path: string, id: Id): Promise<{ items: LadderItem[]; truncated: boolean }> {
  const items: LadderItem[] = []
  for (let page = 0; page < PAGES; page++) {
    const got = await getJson<LadderItemsResponse>(`${path}?conversation=${encodeURIComponent(id)}&limit=${LIMIT}&offset=${page * LIMIT}`)
    items.push(...got.items)
    if (!got.items.length || items.length >= got.total) return { items, truncated: false }
  }
  return { items, truncated: true }
}

function readNow(id: Id) {
  const c = conv(id)
  if (c.out) return
  c.began = Date.now()
  c.out = Promise.all([readList('/api/ladder/items', id), readList('/api/ladder/adopted', id)]).then(([items, adopted]) => {
    c.read = { byPost: index([...items.items, ...adopted.items]), at: Date.now(), truncated: items.truncated || adopted.truncated }
    c.error = null
    /* what an open record said may have changed with it: an open detail reads again */
    details.clear()
    detailEpoch++
    for (const fn of [...detailHeard]) fn()
  }, (e: Error) => {
    c.error = e.message
  }).finally(() => { c.out = null; tell(c) })
}

/** Read again, no sooner than SPACING after the last read began. */
function soon(id: Id) {
  const c = conv(id)
  if (c.timer) return
  const wait = Math.max(0, c.began + SPACING - Date.now())
  c.timer = window.setTimeout(() => { c.timer = 0; if (c.listeners.size) readNow(id) }, wait)
}

/** Whether a durable move can have changed this conversation's records. */
export const movesRecords = (where: Where | null, id: Id) =>
  !where || where.loose || (where.governed && where.conversations.includes(id))

function subscribe(id: Id, fn: () => void) {
  const c = conv(id)
  c.listeners.add(fn)
  if (!c.unfollow) c.unfollow = hearPulse((m, where) => { if (m === 'durable' && movesRecords(where, id)) soon(id) })
  /* first asked, or the last read failed: read now */
  if (!c.read && !c.out) readNow(id)
  return () => {
    c.listeners.delete(fn)
    if (!c.listeners.size) {
      c.unfollow?.(); c.unfollow = null
      if (c.timer) { clearTimeout(c.timer); c.timer = 0 }
    }
  }
}

const NONE: Held[] = []

/** The conversation a post's records are read from: its home, as Fluid's
 *  store holds the post, else the conversation it is being read in. */
export const homeOf = (post: Id, reading: Id | null | undefined): Id | null =>
  store.posts.get(post)?.home ?? reading ?? null

/** This post's records, or null while its conversation is first read.
 *  `truncated`: the lists were longer than PAGES pages; the count is a floor. */
export function usePostRecords(post: Id, conversation: Id | null | undefined): { held: Held[] | null; error: string | null; truncated: boolean } {
  const sub = useCallback((fn: () => void) => (conversation ? subscribe(conversation, fn) : () => {}), [conversation])
  const read = useSyncExternalStore(sub, () => (conversation ? convs.get(conversation)?.read ?? null : null))
  const error = useSyncExternalStore(sub, () => (conversation ? convs.get(conversation)?.error ?? null : null))
  return { held: read ? read.byPost.get(post) ?? NONE : null, error, truncated: !!read?.truncated }
}

/* -- one record, inspected ------------------------------------------------ */

/** `/api/ladder/items/<id>`: the read Governance's item view makes (GovItem),
 *  with lineage, outcomes, challenges, citations and history. Asked once per
 *  record until its conversation is read again. */
const details = new Map<Id, Promise<LadderItemDetail>>()
/** Moves each time the details are let go, so an open one reads again. */
let detailEpoch = 0
const detailHeard = new Set<() => void>()
const hearDetails = (fn: () => void) => { detailHeard.add(fn); return () => { detailHeard.delete(fn) } }
export function readDetail(id: Id): Promise<LadderItemDetail> {
  let p = details.get(id)
  if (!p) {
    p = getJson<LadderItemDetail>('/api/ladder/items/' + encodeURIComponent(id))
    p.catch(() => { if (details.get(id) === p) details.delete(id) })
    details.set(id, p)
  }
  return p
}

/** One record's detail, read when asked for (`want`). */
export function useDetail(id: Id, want: boolean): { d: LadderItemDetail | null; error: string | null } {
  const [state, set] = useState<{ d: LadderItemDetail | null; error: string | null }>({ d: null, error: null })
  /* the conversation read again: what is shown stays until the new answer */
  const epoch = useSyncExternalStore(hearDetails, () => detailEpoch)
  useEffect(() => {
    if (!want) return
    let live = true
    readDetail(id).then((d) => { if (live) set({ d, error: null }) }, (e: Error) => { if (live) set((was) => ({ d: was.d, error: was.d ? null : e.message })) })
    return () => { live = false }
  }, [id, want, set, epoch])
  return state
}
