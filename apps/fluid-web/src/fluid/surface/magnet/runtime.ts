/* THE MAGNET'S ONE ADAPTER REGISTRY AND RESULTS CACHE, BOUND TO THE STORE
 * (part P7). The conversation adapter reads through the client store's
 * existing reads and P8's searchConversation, unchanged; nothing is copied
 * out of the store's caches. */

import { searchConversation, store } from '../../store'
import { conversationAdapter, type ConversationReads, type ObjectRow } from './conversation'
import { createLive } from './live'
import { createAdapters } from './model'

export const storeReads: ConversationReads = {
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

export const adapters = createAdapters()
adapters.register(conversationAdapter(storeReads))
export const live = createLive(adapters)

/** The store keys a source's results are read from: hearing one, they are stale. */
export const storeKeysOf = (s: { kind: string; conversation?: string }): string[] =>
  s.kind === 'conversation' && s.conversation ? ['coll:conversation:' + s.conversation, 'cobjects:' + s.conversation, 'conv:' + s.conversation] : []
