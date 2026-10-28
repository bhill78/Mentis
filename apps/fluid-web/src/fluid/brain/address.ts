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

/* -- carried out of the Brain: the drop paths Fluid already has ------------
 * A Turn is a post, and goes as a post does when dragged by its head
 * (PostCard, keep.tsx `POST`): a section keeps what it is made of. Anything
 * else goes as one object (keep.tsx `DRAG`) at the smallest address the
 * sections can draw by reference -- `brain:<entry>`, as What needs you's
 * `needs-you:<id>` -- so it is kept as a reference to the record, never a
 * copy. Acquired material also carries its artifact's address, which the
 * composer already takes as something Mentis holds (Carries.tsx does the
 * same). Moving it creates nothing: keeping is the arrangement's, and
 * anything durable still goes through the record's own doors. */

/** The prefix of a Brain object's address in a section. */
export const BRAIN_REF = 'brain:'
export const isBrainRef = (address: string) => address.startsWith(BRAIN_REF) && address.length > BRAIN_REF.length
export const brainRef = (entry: Id) => BRAIN_REF + entry
export const entryOfRef = (address: string) => (isBrainRef(address) ? address.slice(BRAIN_REF.length) : null)

/** The mimes Fluid's drop paths read (workspace/keep.tsx), named here so this
 *  file stays free of the browser. */
export const OBJECT_MIME = 'application/x-mentis-fluid-object'
export const POST_MIME = 'application/x-mentis-fluid-post'

/** What dragging a thing out of the Brain carries, mime by mime. */
export function dragPayload(n: Pick<SpaceNode, 'entry' | 'kind'>, origin: string): [string, string][] {
  if (isTurn(n)) return [[POST_MIME, JSON.stringify({ post: n.entry })], ['text/plain', n.entry]]
  const out: [string, string][] = [[OBJECT_MIME, JSON.stringify({ address: brainRef(n.entry), from: 'the 3D Brain' })]]
  if (/^adm-[0-9a-f]+$/.test(n.entry)) out.push(['text/uri-list', new URL(`/api/artifacts/${n.entry}`, origin).href])
  out.push(['text/plain', n.entry])
  return out
}

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
