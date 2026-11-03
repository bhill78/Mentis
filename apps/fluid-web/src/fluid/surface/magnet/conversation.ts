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
  preview?: {
    type?: string
    media_type?: string | null
    /** what the server says it is (experimental/objectkinds.ts ObjectIs) */
    is?: { filter?: string; family?: string; source?: string; word?: string; fillable?: boolean } | null
    artifact?: { url?: string } | null
    ref?: string | null
  } | null
}

/** Where an object row's picture is read from, when it is one that has bytes. */
export const pictureOf = (row: ObjectRow): string | null =>
  row.preview?.artifact?.url ?? (row.preview?.ref ? `/api/artifacts/${row.preview.ref}` : null)

export interface ConversationReads {
  /** a page of the conversation's posts, newest page first; `page` an older cursor */
  posts(conversation: string, page?: string): Promise<{ ids: string[]; next?: string }>
  /** every object in the conversation (its index) */
  objects(conversation: string): Promise<ObjectRow[]>
  /** P8's searchConversation, unchanged */
  search(conversation: string, q: string, opts: { limit?: number; before?: string }): Promise<Hit[]>
  /** its name, activity and what it says of itself, with how many posts it holds */
  about(conversation: string): Promise<{ title: string; activity?: number; about?: string; posts?: number }>
}

/** What a conversation can give a Magnet in this build. */
export const CONVERSATION_CAPABILITIES: ReadonlySet<MagnetCapability> = new Set<MagnetCapability>(['fetch', 'search', 'post', 'file', 'image', 'attachment', 'link', 'form'])
export const SEARCH_PAGE = 20

export type ObjectType = 'image' | 'file' | 'attachment' | 'link' | 'form'

/** An object row's information type, or null for one that is none of them
 *  (a section of a post's own words). What the server says it is comes
 *  first: images, video and audio are images and media; a file attached to a
 *  post is an attachment, any other file a file; a link is a link (a video
 *  link is media); something to fill in is a form. A Magnet that selects
 *  files but not attachments still sees its attached files, as files: a
 *  selection never hides what it used to show. Rows the server has not
 *  described are read from their words, as before. */
export function objectTypeOf(row: ObjectRow, want?: ReadonlySet<string>): ObjectType | null {
  const is = row.preview?.is
  if (is) {
    if (is.fillable) return 'form'
    if (is.family === 'media') return 'image'
    if (is.family === 'link') return 'link'
    if (is.family === 'file') return is.source === 'attachment' && (!want || want.has('attachment')) ? 'attachment' : 'file'
    if (is.family) return null
  }
  const said = `${row.kind} ${row.preview?.type ?? ''} ${row.preview?.media_type ?? ''} ${is?.filter ?? ''}`.toLowerCase()
  if (/image|picture|photo|png|jpe?g|gif|webp|svg|video|audio/.test(said)) return 'image'
  if (/file|document|pdf|attachment|sheet|data|code|zip|archive/.test(said)) return 'file'
  return null
}

export function conversationAdapter(reads: ConversationReads): MagnetSourceAdapter<ConversationSource> {
  return {
    kind: 'conversation',
    capabilities: (_src, env) => (env.permissions.has('read') ? CONVERSATION_CAPABILITIES : new Set()),
    async fetch(src, selection: MagnetSelection, page) {
      const want = new Set<string>(selection.informationTypes?.length ? selection.informationTypes : ['post', 'file', 'image'])
      const results: MagnetResult[] = []
      let next: string | undefined
      if (want.has('post')) {
        const got = await reads.posts(src.conversation, page)
        for (const id of got.ids) results.push({ source: src, kind: 'post', id, value: { post: id } })
        next = got.next
      }
      /* the object index is whole: read with the first page only */
      if (!page && ['file', 'image', 'attachment', 'link', 'form'].some((t) => want.has(t))) {
        for (const row of await reads.objects(src.conversation)) {
          const t = objectTypeOf(row, want)
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
      return { title: a.title, initial: initialOf(a.title), ...(a.activity ? { activity: a.activity } : {}),
        ...(a.about ? { about: a.about } : {}), ...(a.posts != null ? { posts: a.posts } : {}) }
    },
  }
}
