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
 * Adopted show for it. Read when the first post of that conversation asks,
 * shared by every post (and every drawing of a post) after. Read again when
 * the change feed says the conversation moved (`conv:<id>`, store.follow),
 * no sooner than SPACING after the last read began: on DAY-TO-DAY the read
 * takes seconds and agents move a conversation constantly.
 *
 * WHAT IT MISSES, SAID PLAINLY: a record recorded from ANOTHER
 * conversation's work that cites this post as its basis (7 of 473 post
 * citations on DAY-TO-DAY, 2026-11-10), and material neither list shows (the
 * notes holding a request's or decline's reason, which are not ladder
 * material). One whole-Brain read would catch the first at many times the
 * cost; it is not made.
 *
 * READ-ONLY. Nothing here writes, and nothing here decides what a record
 * is: kind, status, challenges and outcomes are the server's. */
import { useCallback, useEffect, useState, useSyncExternalStore } from 'react'
import { CLIENT_HEADERS } from '../../api'
import type { LadderItem, LadderItemDetail, LadderItemsResponse } from '../../fluid/governance/ladderTypes'
import { store, type Id } from '../../fluid/store'

/** How a record is this post's, in the record's own terms. */
export type Relation = 'recorded' | 'extracted-from' | 'derived-from' | 'outcome-of'
const CITES = new Set<string>(['extracted-from', 'derived-from', 'outcome-of'])

/** One record beside one post, with every way it is that post's. */
export interface Held { item: LadderItem; relations: Relation[] }

/** A conversation's records, by the post each belongs to. */
interface Read { byPost: Map<Id, Held[]>; at: number }
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

function readNow(id: Id) {
  const c = conv(id)
  if (c.out) return
  c.began = Date.now()
  const q = `?conversation=${encodeURIComponent(id)}&limit=${LIMIT}`
  c.out = Promise.all([
    getJson<LadderItemsResponse>('/api/ladder/items' + q),
    getJson<LadderItemsResponse>('/api/ladder/adopted' + q),
  ]).then(([items, adopted]) => {
    c.read = { byPost: index([...items.items, ...adopted.items]), at: Date.now() }
    c.error = null
    /* what an open record said may have changed with it */
    details.clear()
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

function subscribe(id: Id, fn: () => void) {
  const c = conv(id)
  c.listeners.add(fn)
  if (!c.unfollow) {
    /* THE CHANGE FEED NAMES A CONVERSATION THE STORE HOLDS: held, so a
       record recorded in it is heard (store.follow is the page's) */
    if (!store.conversations.has(id)) void store.loadConversations([id]).catch(() => {})
    c.unfollow = store.subscribe('conv:' + id, () => soon(id))
  }
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

/** This post's records, or null while its conversation is first read. */
export function usePostRecords(post: Id, conversation: Id | null | undefined): { held: Held[] | null; error: string | null } {
  const sub = useCallback((fn: () => void) => (conversation ? subscribe(conversation, fn) : () => {}), [conversation])
  const read = useSyncExternalStore(sub, () => (conversation ? convs.get(conversation)?.read ?? null : null))
  const error = useSyncExternalStore(sub, () => (conversation ? convs.get(conversation)?.error ?? null : null))
  return { held: read ? read.byPost.get(post) ?? NONE : null, error }
}

/* -- one record, inspected ------------------------------------------------ */

/** `/api/ladder/items/<id>`: the read Governance's item view makes (GovItem),
 *  with lineage, outcomes, challenges, citations and history. Asked once per
 *  record until its conversation is read again. */
const details = new Map<Id, Promise<LadderItemDetail>>()
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
  useEffect(() => {
    if (!want) return
    let live = true
    readDetail(id).then((d) => { if (live) set({ d, error: null }) }, (e: Error) => { if (live) set({ d: null, error: e.message }) })
    return () => { live = false }
  }, [id, want, set])
  return state
}
