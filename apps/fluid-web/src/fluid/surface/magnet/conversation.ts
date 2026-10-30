/* THE FIRST SOURCE ADAPTER: CONVERSATION-BACKED (plan adm-b848fa881c8d
 * §3.10.1; part P7).
 *
 * What a Magnet reads from a conversation, through the reads the client
 * already has (its posts, its object index) and P8's conversation-bounded
 * search, which it wraps unchanged. Nothing is copied: a result carries its
 * source and the record's id; the content stays in the store's caches.
 * The reads are injected, so the adapter is browser-free and tests count
 * every call (storeReads.ts binds the real ones). */

import type { Hit } from '../../store'
import type { MagnetCapability, MagnetResult, MagnetSelection, MagnetSourceAdapter, MagnetSummary } from './types'
import { initialOf } from './model'

type ConversationSource = { kind: 'conversation'; conversation: string }

/** One row of a conversation's object index, as the adapter needs it. */
export interface ObjectRow {
  address: string
  kind: string
  title: string | null
  post: string
  number: number | null
  preview?: { type?: string; is?: { filter?: string } | null } | null
}

export interface ConversationReads {
  /** a page of the conversation's posts, newest page first; `page` an older cursor */
  posts(conversation: string, page?: string): Promise<{ ids: string[]; next?: string }>
  /** every object in the conversation (its index) */
  objects(conversation: string): Promise<ObjectRow[]>
  /** P8's searchConversation, unchanged */
  search(conversation: string, q: string, opts: { limit?: number; before?: string }): Promise<Hit[]>
  /** its name and activity */
  about(conversation: string): Promise<{ title: string; activity?: number }>
}

/** What a conversation can give a Magnet in this build. */
export const CONVERSATION_CAPABILITIES: ReadonlySet<MagnetCapability> = new Set<MagnetCapability>(['fetch', 'search', 'post', 'file', 'image'])
export const SEARCH_PAGE = 20

/** An object row's information type: an image, a file, or neither. */
export function objectTypeOf(row: ObjectRow): 'image' | 'file' | null {
  const said = `${row.kind} ${row.preview?.type ?? ''} ${row.preview?.is?.filter ?? ''}`.toLowerCase()
  if (/image|picture|photo|png|jpe?g|gif|webp|svg/.test(said)) return 'image'
  if (/file|document|pdf|attachment|sheet|data|code|zip|archive/.test(said)) return 'file'
  return null
}

export function conversationAdapter(reads: ConversationReads): MagnetSourceAdapter<ConversationSource> {
  return {
    kind: 'conversation',
    capabilities: (_src, env) => (env.permissions.has('read') ? CONVERSATION_CAPABILITIES : new Set()),
    async fetch(src, selection: MagnetSelection, page) {
      const want = new Set(selection.informationTypes?.length ? selection.informationTypes : ['post', 'file', 'image'])
      const results: MagnetResult[] = []
      let next: string | undefined
      if (want.has('post')) {
        const got = await reads.posts(src.conversation, page)
        for (const id of got.ids) results.push({ source: src, kind: 'post', id, value: { post: id } })
        next = got.next
      }
      /* the object index is whole: read with the first page only */
      if (!page && (want.has('file') || want.has('image'))) {
        for (const row of await reads.objects(src.conversation)) {
          const t = objectTypeOf(row)
          if (t && want.has(t)) results.push({ source: src, kind: t, id: row.address, value: row })
        }
      }
      return { results, ...(next ? { next } : {}) }
    },
    async search(src, q, page) {
      const hits = await reads.search(src.conversation, q, { limit: SEARCH_PAGE, ...(page ? { before: page } : {}) })
      const results = hits.map((h): MagnetResult => ({ source: src, kind: 'hit', id: h.post, value: h }))
      return { results, ...(hits.length === SEARCH_PAGE ? { next: hits[hits.length - 1].post } : {}) }
    },
    async summary(src): Promise<MagnetSummary> {
      const a = await reads.about(src.conversation)
      return { title: a.title, initial: initialOf(a.title), ...(a.activity ? { activity: a.activity } : {}) }
    },
  }
}
