import type { Address } from '../address'
import { NOWHERE, writeAddress } from '../address'
import type { Conversation, FindingChoice, Id, Turn } from '../api'
import { bodyOf, emptyDraft } from '../composer/draft'
import { writeQuietLocation } from './pages/location'

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
/** WHICH HALF OF A READING IS LOADED -- the batch cursor, and nothing to do
 *  with a destination (F23). Round 5's Page SEQUENCE descriptor is
 *  `QuietSequencePage` in `quiet/workspace/types.ts`; this name was here
 *  first, means what it has always meant, and is not renamed to make room for
 *  it. Where both are in view at once, alias this one as `BatchCursor`. */
export type Page = { before?: number; after?: number }
/** `Page` under the name that says which Page it is not. */
export type BatchCursor = Page

export function place(conversation: Id, topic: Id | null = null, turn: Id | null = null): Address {
  return { ...NOWHERE, conversation, topic, turn }
}

/** WHERE A LINK INSIDE QUIET POINTS, when Quiet is reading a Page of a
 *  conversation other than the one in the address bar.
 *
 *  The address's conversation is always the ORIGIN -- the Holder's owner --
 *  and the Page says which conversation is read there. So a link written
 *  inside a Deep dive keeps the origin and the Page and names the child's own
 *  topic or turn. `effectiveConversation` is what the caller is reading, and
 *  is what `useQuietHref` checks the link against: a link LEAVING the
 *  effective conversation leaves the sequence normally and is written without
 *  this argument. */
export interface QuietHrefLocation {
  originConversation: Id
  page: string
  effectiveConversation: Id
}

/** OMITTED, EVERY EXISTING CALL READS AS BEFORE. `at` given writes the Quiet
 *  destination suffix after the topic and turn pairs (`pages/location.ts`);
 *  the shared `writeAddress` cannot emit it and is unchanged.
 *
 *  A LINK THAT LEAVES THE EFFECTIVE CONVERSATION IS WRITTEN PLAINLY even when
 *  `at` was passed: the suffix names the origin, so attaching it to a link
 *  going somewhere else would quietly point it back home. */
export const href = (
  conversation: Id,
  topic: Id | null = null,
  turn: Id | null = null,
  at?: QuietHrefLocation,
) =>
  at && conversation === at.effectiveConversation
    ? writeQuietLocation({ originConversation: at.originConversation, topic, turn, page: at.page })
    : writeAddress(place(conversation, topic, turn))

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

/** WHAT AN ANSWER TO A DECISION CARRIES, as data for the server to check
 *  against what was actually offered (`mentis/conversation/posting.py`, which
 *  reads `chose` on the posting body). The prose of the Turn is for the
 *  reader and is never the record of the decision. The shape is
 *  `composer/draft.ts`'s own, so an answer written in Quiet and one written in
 *  Fluid are the same fact. */
export type Chose =
  | { expectation: Id; option: number; label: string; selections?: Record<Id, FindingChoice> }
  | { expectation: Id; withdraw: true }

/** `chose` IS OMITTED, NOT SENT EMPTY, when nothing was chosen: an ordinary
 *  message must stay identical field for field to what it has always been,
 *  and `posting.py` reads the key's presence. D answers a decision from the
 *  rail by passing it. */
export function postingBody(text: string, action: PostingAction, author: Id,
  conversation: Id, topic: Id | null, reply: Turn | null, op: string,
  chose?: Chose) {
  const draft = { ...emptyDraft(), text, action }
  const body = bodyOf(draft, author, topic ? [topic] : [])
  if (reply && reply.author !== author) body.addressed_to = [reply.author]
  return { ...body, conversation, ...(reply ? { replies_to: reply.id } : {}), op, ...(chose ? { chose } : {}) }
}

export const message = (error: unknown) => error instanceof Error ? error.message : String(error)
