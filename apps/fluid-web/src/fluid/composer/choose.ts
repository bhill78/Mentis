/* WHAT A PALETTE PICK DOES TO A DRAFT, for every composer that opens the
 * palette.
 *
 * MOVED, NOT REWRITTEN. This was a closure inside `fluid/Composer.tsx`
 * (`choose`, and the three draft transforms it dispatches to), which meant the
 * only way to get Fluid's `@` and `#` behaviour somewhere else was to write it
 * again -- and two copies of "what picking a name means" would drift. The body
 * below is Fluid's, character for character where it can be; Fluid's composer
 * calls it and keeps the state, the text splicing and the caret, which are
 * genuinely its own.
 *
 * WHAT STAYS WITH THE CALLER. Where the trigger is, how the token is written
 * back into the text, and where the caret lands afterwards all belong to one
 * particular textarea. So they arrive here as the four handlers below
 * (`address`, `attachTopic`, `markWork`, and the two writes), and this module
 * decides only WHICH of them a pick means -- including the two cases that are
 * not simply a write: a Topic that does not exist yet, and a name not in this
 * conversation yet.
 *
 * Nothing here holds state and nothing here reads the record directly. */

import type { Addressee, Mark } from '../../composer/draft'
import { shiftMarks, withMark } from '../../composer/draft'
import type { Trigger } from '../../composer/trigger'
import type { Id } from '../store'
import type { Pick } from './hashRows'

/** A NEW CONVERSATION NOT MADE YET (owner decision D1, #599): a Topic created
 *  or a name brought in before the first post is held in the draft, in the
 *  place the real id goes once it exists. `LATER` is how it is spelled; the
 *  first post applies what was held and swaps the ids in. */
export const LATER = { topic: 'later-topic:', name: 'later-name:' }
export const later = (id: Id) => id.startsWith(LATER.topic) || id.startsWith(LATER.name)

/** As much of a draft as landing a pick touches. Both composers' drafts are
 *  this and more, so neither has to adopt the other's shape to share this. */
export interface Composing {
  text: string
  to: Addressee[]
  topics: Id[]
  marks: Mark[]
}

/** Addressees whose alias is still written in the text. A name deleted from
 *  the sentence is no longer addressed by it. */
export const retextualise = (text: string, list: Addressee[]) =>
  list.filter((a) => text.includes(a.alias))

/** The draft with `next` addressed, the token already written into `text`.
 *  Addressing somebody twice is one addressee, the newer decision winning. */
export function addressed<D extends Composing>(d: D, text: string, next: Addressee): D {
  return { ...d, text, to: [...retextualise(text, d.to).filter((a) => a.participant !== next.participant), next] }
}

/** The draft with this post FILED under the Topic and the characters that
 *  name it marked. Two facts (membership and an authored reference), both. */
export function topicAttached<D extends Composing>(d: D, t: Trigger, text: string, id: Id, name: string): D {
  const written = '#' + name.replace(/^#/, '')
  return {
    ...d, text, to: retextualise(text, d.to),
    topics: d.topics.includes(id) ? d.topics : [...d.topics, id],
    marks: withMark(shiftMarks(d.marks, d.text, text), { topic: id, text: written, start: t.start }),
  }
}

/** The draft with existing work REFERRED TO: a mark and nothing else. A post
 *  or a conversation is not filed under, so membership is untouched. */
export function workMarked<D extends Composing>(
  d: D, t: Trigger, text: string, id: Id, said: string, kind: 'conversation' | 'turn' | 'acquired',
): D {
  const written = '#' + said.replace(/^#/, '')
  return {
    ...d, text, to: retextualise(text, d.to),
    marks: withMark(shiftMarks(d.marks, d.text, text), { kind, topic: id, text: written, start: t.start }),
  }
}

/** What the composer round this landing holds and can do. */
export interface Landing {
  /** the trigger the pick answers; nothing lands without one */
  trigger: Trigger | null
  /** the conversation being written to, or null: not made yet, so a Topic or
   *  a name is held in the draft rather than written anywhere */
  writing: Id | null
  me: Id | null
  creating: boolean
  setCreating: (creating: boolean) => void
  setErr: (why: string | null) => void
  setTrigger: (trigger: Trigger | null) => void
  address: (t: Trigger, next: Addressee) => void
  attachTopic: (t: Trigger, id: Id, name: string) => void
  markWork: (t: Trigger, id: Id, said: string, kind: 'conversation' | 'turn' | 'acquired') => void
  bringIn: (into: Id, alias: string, op?: string) => Promise<{ participant: Id; alias: string; created: boolean }>
  createTopic: (into: Id, name: string, op?: string) => Promise<{ topic: Id; name: string }>
}

/** A pick from the `@` or `#` palette, landed. Fluid's own `choose`. */
export async function choosePick(p: Pick, h: Landing): Promise<void> {
  const t = h.trigger
  if (!t) return
  h.setErr(null)
  try {
    if (p.kind === 'topic') return h.attachTopic(t, p.id, p.name)
    if (p.kind === 'ref') return h.markWork(t, p.id, p.label, p.refKind)
    if (p.kind === 'create') {
      if (!h.writing) return h.attachTopic(t, LATER.topic + p.name, p.name)
      if (h.creating || !h.me) return
      h.setCreating(true)
      try {
        const r = await h.createTopic(h.writing, p.name)
        h.attachTopic(t, r.topic, r.name)
      } finally { h.setCreating(false) }
      return
    }
    if (p.kind === 'summon' || p.joining) {
      const fresh = p.kind === 'summon'
      if (!h.writing)
        return h.address(t, { participant: LATER.name + p.alias, alias: p.alias, dispatch: p.dispatch,
          summoned: fresh, newInstance: fresh, runtime: p.runtime, model: p.model })
      const got = await h.bringIn(h.writing, p.alias)
      return h.address(t, { participant: got.participant, alias: got.alias, dispatch: p.dispatch,
        summoned: got.created, newInstance: got.created, runtime: p.runtime, model: p.model })
    }
    h.address(t, { participant: p.participant, alias: p.alias, dispatch: p.dispatch, runtime: p.runtime, model: p.model })
  } catch (e) {
    h.setErr((e as Error).message)
    h.setTrigger(null)
  }
}
