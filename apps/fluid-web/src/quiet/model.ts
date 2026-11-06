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

/** WHAT ONE SUBMISSION IS. Two sends of the same words, posting action and
 *  reply target are one submission asked twice, and the server settles them
 *  by the key they carry (`op`).
 *
 *  A draft mints a new key on every keystroke, which is right for a draft
 *  that has become a different message and wrong for one that has become the
 *  same message again: a first attempt whose answer never arrived may have
 *  reached the record, and typing its words away and back would then have
 *  asked for a second copy of it. So an attempt that failed is remembered
 *  with the draft, and an identical submission asks with the key it already
 *  used. The LAST failed attempt is what a draft remembers -- that is what
 *  the reader is looking at -- and a success clears the draft and its memory
 *  with it, so posting the same words again on purpose is still two posts. */
export type Attempt = { submission: string; op: string }

export const submissionKey = (text: string, action: PostingAction, reply: Turn | null) =>
  JSON.stringify([text, action, reply?.id ?? null])

export const settlingKey = (submission: string, op: string, attempt?: Attempt) =>
  attempt && attempt.submission === submission ? attempt.op : op

export function postingBody(text: string, action: PostingAction, author: Id,
  conversation: Id, topic: Id | null, reply: Turn | null, op: string) {
  const draft = { ...emptyDraft(), text, action }
  const body = bodyOf(draft, author, topic ? [topic] : [])
  if (reply && reply.author !== author) body.addressed_to = [reply.author]
  return { ...body, conversation, ...(reply ? { replies_to: reply.id } : {}), op }
}

export const message = (error: unknown) => error instanceof Error ? error.message : String(error)
