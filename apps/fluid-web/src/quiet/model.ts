import type { Address } from '../address'
import { NOWHERE, writeAddress } from '../address'
import type { Conversation, Id, Turn } from '../api'
import { bodyOf, emptyDraft } from '../composer/draft'

export type PostingAction = 'ask-mentis' | 'record-only'
export interface ThreadRead {
  conversation: Id
  root: Id
  turn: Turn
  replies_total: number
  replies: Turn[]
}
export interface ThreadLocation {
  id: Id
  inspector: { conversation: Id; root: Id | null }
}
export type Page = { before?: number; after?: number }

export function place(conversation: Id, topic: Id | null = null, turn: Id | null = null): Address {
  return { ...NOWHERE, conversation, topic, turn }
}
export const href = (conversation: Id, topic: Id | null = null, turn: Id | null = null) =>
  writeAddress(place(conversation, topic, turn))

export function conversationPath(conversation: Id, topic: Id | null, page: Page): string {
  const q = new URLSearchParams({ batch: '30' })
  if (topic) q.set('topic', topic)
  if (page.before !== undefined) q.set('before', String(page.before))
  if (page.after !== undefined) q.set('after', String(page.after))
  return `/api/conversations/${encodeURIComponent(conversation)}?${q}`
}

export function flowTurns(conversation: Conversation): Turn[] {
  // A topic is a flat filing view, including replies filed there. At conversation
  // scope the server's root is authoritative, even if the parent is not loaded.
  return conversation.focus_topic ? conversation.turns : conversation.turns.filter(
    (turn) => turn.root ? turn.root === turn.id : !turn.answering,
  )
}

export function postingBody(text: string, action: PostingAction, author: Id,
  conversation: Id, topic: Id | null, reply: Turn | null, op: string) {
  const draft = { ...emptyDraft(), text, action }
  const body = bodyOf(draft, author, topic ? [topic] : [])
  if (reply && reply.author !== author) body.addressed_to = [reply.author]
  return { ...body, conversation, ...(reply ? { replies_to: reply.id } : {}), op }
}

export const message = (error: unknown) => error instanceof Error ? error.message : String(error)
