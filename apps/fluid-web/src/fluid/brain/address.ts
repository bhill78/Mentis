/* WHAT A THING IN THE 3D BRAIN IS, TO THE REST OF FLUID: where it lives.
 * Browser-free, so it is testable. */

import type { SpaceNode } from '../../surfaces/space/layout'

export type Id = string

/** Where the Shell takes somebody who leaves the Brain for a thing's home. */
export interface BrainDoors {
  /** a Turn, read in its Conversation */
  openPost: (conversation: Id, post: Id) => void
  /** a Conversation, entered */
  openConversation: (conversation: Id) => void
}

/** A Turn is a post (`contribution` is the record's word for it). */
export const isTurn = (n: Pick<SpaceNode, 'kind'>) => n.kind === 'contribution'

/** What a thing is called to a reader: the record's kind, a Turn as a turn. */
export const kindWord = (n: Pick<SpaceNode, 'kind'>) => (isTurn(n) ? 'turn' : n.kind)

/** Where a thing lives: a Turn in its Conversation, a Conversation itself;
 *  anything else in the Conversation the record puts it in. False where the
 *  record places it nowhere a reader can go. */
export function goHome(n: Pick<SpaceNode, 'entry' | 'kind' | 'conversation'>, doors: BrainDoors): boolean {
  if (n.kind === 'conversation') { doors.openConversation(n.entry); return true }
  if (!n.conversation) return false
  if (isTurn(n)) doors.openPost(n.conversation, n.entry)
  else doors.openConversation(n.conversation)
  return true
}
