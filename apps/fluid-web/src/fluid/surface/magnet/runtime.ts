/* THE MAGNET'S ONE ADAPTER REGISTRY AND RESULTS CACHE, BOUND TO THE STORE
 * (part P7). The conversation adapter reads through the client store's
 * existing reads and P8's searchConversation, unchanged; nothing is copied
 * out of the store's caches. */

import { said } from '../../conversation/text'
import { searchConversation, store, type Post } from '../../store'
import { conversationAdapter, type ConversationReads, type ObjectRow } from './conversation'
import { createLive } from './live'
import { createAdapters } from './model'
import { plainWords } from './presentation'
import { createMagnetRoute } from './route'
import { ownerAuthCheck } from '../../http'

/** The read itself. A body that isn't JSON says nothing beyond its status. */
const routeRead = createMagnetRoute(async (path, signal) => {
  const res = await fetch('/fluid/api/' + path, { headers: { 'X-Mentis-Client': '1' }, ...(signal ? { signal } : {}) })
  await ownerAuthCheck(res)
  return { status: res.status, body: await res.json().catch(() => null) }
})

export const storeReads: ConversationReads = {
  route: routeRead,
  /* The newest page the store holds of it (read once if it holds none),
     newest first. Older pages are stage B's. */
  async posts(conversation) {
    const key = 'conversation:' + conversation
    if (!store.collections.has(key)) await store.loadConversation(conversation)
    return { ids: (store.collections.get(key)?.items ?? []).map((i) => i.id).reverse() }
  },
  async objects(conversation) {
    await store.loadConversationObjects(conversation)
    return (store.conversationObjects.get(conversation)?.objects ?? []) as ObjectRow[]
  },
  search: (conversation, q, opts) => searchConversation(conversation, q, opts),
  async about(conversation) {
    if (!store.conversations.has(conversation)) await store.loadConversations([conversation])
    const c = store.conversations.get(conversation)
    return { title: c?.name ?? 'Conversation', ...(c?.last_activity ? { activity: c.last_activity } : {}),
      ...(c?.about ? { about: c.about } : {}), ...(c ? { posts: c.posts } : {}) }
  },
}

/** Each post's words and who wrote it, from what the store holds, or else one
 *  read of just these, without their threads, that leaving ends. For a hover: it
 *  stays out of the store, so a card has its few lines and no more. */
export interface PostGlance { id: string; author_name?: string; author?: string; at?: number; number?: number | null; deleted?: boolean; words: string }
const glanced = new Map<string, PostGlance>()
const GLANCES_KEPT = 60
const glanceOf = (p: Post): PostGlance => ({ id: p.id, author_name: p.author_name, author: p.author, at: p.at, number: p.number, ...(p.deleted ? { deleted: true } : {}), words: plainWords(said(p).words) })
export async function readGlances(ids: readonly string[], signal?: AbortSignal): Promise<Map<string, PostGlance>> {
  const out = new Map<string, PostGlance>()
  const want: string[] = []
  for (const id of ids) {
    const held = store.posts.get(id)
    const had = held ? glanceOf(held) : glanced.get(id)
    if (had) out.set(id, had)
    else want.push(id)
  }
  if (!want.length) return out
  const res = await fetch('/fluid/api/posts?ids=' + want.map(encodeURIComponent).join(','), { headers: { 'X-Mentis-Client': '1' }, ...(signal ? { signal } : {}) })
  await ownerAuthCheck(res)
  if (!res.ok) return out
  const body = await res.json().catch(() => null) as { posts?: (Post & { error?: string })[] } | null
  for (const raw of body?.posts ?? []) {
    if (raw.error) continue
    const one = glanceOf(raw)
    if (glanced.size >= GLANCES_KEPT) glanced.delete(glanced.keys().next().value!)
    glanced.set(one.id, one)
    out.set(one.id, one)
  }
  return out
}

export const adapters = createAdapters()
adapters.register(conversationAdapter(storeReads))
export const live = createLive(adapters)

/** The store keys a source's results are read from: hearing one, they are stale. */
export const storeKeysOf = (s: { kind: string; conversation?: string }): string[] =>
  s.kind === 'conversation' && s.conversation ? ['coll:conversation:' + s.conversation, 'cobjects:' + s.conversation, 'conv:' + s.conversation] : []
