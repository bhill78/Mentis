import { useEffect, useState } from 'react'
import { CLIENT_HEADERS } from '../../api'
import { READ_ONLY } from '../live'
import { resourceCorpus } from './managementApi'

interface ScopedWrites { corpus_id: string; conversations: string[]; arrangements: string[] }
/** Only the disposable proxy exposes this scope. Normal servers use normal UI authority. */
export function useMagnetWrites(brainKey: string | null) {
  const [scope, setScope] = useState<ScopedWrites | null>(null)
  useEffect(() => {
    setScope(null)
    if (!READ_ONLY || !brainKey) return
    const abort = new AbortController()
    void fetch('/__q2/magnet-capabilities', { headers: CLIENT_HEADERS, signal: abort.signal, cache: 'no-store' }).then(async (r) => {
      const v = await r.json()
      if (!abort.signal.aborted && r.ok && v.fixture === true && v.corpus_id === resourceCorpus(brainKey) && Array.isArray(v.conversations) && Array.isArray(v.arrangements)) setScope(v)
    }).catch(() => {})
    return () => abort.abort()
  }, [brainKey])
  const valid = !!brainKey && scope?.corpus_id === resourceCorpus(brainKey)
  return {
    /** Whether an own Conversation that ALREADY EXISTS may be written into. */
    conversation: (id: string | null | undefined) => !!brainKey && (!READ_ONLY || (!!id && valid && scope!.conversations.includes(id))),
    /** WHETHER THIS MAGNET'S OWN CONVERSATION MAY BE MADE HERE.
     *
     *  A Magnet with no own Conversation does not dead-end the first send: the
     *  send makes one and records the message in it (`conversation.ts`
     *  `createOwn`, `POST /fluid/api/magnets/<id>/conversation`). That is a
     *  DIFFERENT operation from writing into a Conversation that already
     *  exists, so it is a different question. Asking `conversation()` about an
     *  id that does not exist yet answers neither question: it answers "may I
     *  write into nothing", which is always no, and in a scoped build that is
     *  reported to the reader as the Magnet being unwritable here.
     *
     *  An ordinary server answers this with its ordinary UI authority, as it
     *  does every other write. The disposable fixture answers no, always: its
     *  proxy forwards exactly two writes -- a post into the one seeded
     *  Conversation, and one Magnet creation in the one seeded arrangement
     *  (`tools/quiet-magnet-additions-preview.mjs`) -- and the creation route is
     *  neither of them. The scope is NOT widened to cover it: returning true
     *  there would offer a send the authority door then refuses. The card says
     *  what cannot be done here instead (`NO_OWN_CONVERSATION_HERE`). */
    ownConversation: () => !!brainKey && !READ_ONLY,
    arrangement: (id: string | null | undefined) => !!brainKey && (!READ_ONLY || (!!id && valid && scope!.arrangements.includes(id))),
    fixture: READ_ONLY && valid,
  }
}

export type MagnetWrites = ReturnType<typeof useMagnetWrites>

/** WHETHER THIS MAGNET'S CARD MAY BE WRITTEN TO, and why not when it may not.
 *
 *  The card's Composer, Conversation view and Perspectives panel all write
 *  through one store, so they are all given this one answer. Which question it
 *  comes from depends on the Magnet, not on the card:
 *
 *    - it HAS an own Conversation -> may that Conversation be written into
 *    - it has NONE               -> may one be made here (the first send makes
 *                                   it: `conversation.ts` `createOwn`)
 *
 *  Asking the first question about an id that does not exist yet answers "may I
 *  write into nothing", which is no, and reports a Magnet that is simply new as
 *  one that cannot be written to at all. The collection is not part of either
 *  question: ordinary Conversation works on an empty collection because nothing
 *  here reads the sources (the owner's requirement, `ent-f7d052b9933b`).
 *
 *  `why` is supplied only where it is more exact than the card's own default. */
export function magnetWriteGate(writes: MagnetWrites, own: string | null | undefined,
                                noneHere: string): { mayWrite: boolean; why?: string } {
  const hasOwn = typeof own === 'string' && /^ent-[a-z0-9]{6,40}$/i.test(own)
  if (hasOwn) return { mayWrite: writes.conversation(own) }
  return { mayWrite: writes.ownConversation(), why: noneHere }
}
