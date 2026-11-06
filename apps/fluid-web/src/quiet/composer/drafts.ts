/* PACKAGE C owns this module: THE DRAFTS RECORD, LIFTED OUT OF THE TREE.
 *
 * Unsent words must survive moving between the conversation, a topic and a
 * thread, so they cannot live in the component that is unmounted by the move.
 * They are kept here instead -- the way `look.ts` keeps Fluid's atmosphere
 * outside the tree -- keyed by the place they were written, and read through
 * `useDraft`, which subscribes so every reader of a key sees the same words.
 *
 * `set(next, ifOp)` GUARDS THE WRITE. A delayed answer belongs to the draft
 * that asked, not to whatever is in the field now: a composer that has moved
 * on has a different `op`, and the stale answer is dropped rather than
 * clearing words the reader wrote afterwards. */
import { useEffect, useState } from 'react'
import type { Draft, SetDraft } from '../contract'

export const newDraft = (): Draft => ({ text: '', action: 'ask-mentis', op: crypto.randomUUID() })

const held = new Map<string, Draft>()
const listeners = new Set<() => void>()

const announce = () => { for (const fn of [...listeners]) fn() }

/** Every draft, thrown away. Used by the suites, so one case's words cannot
 *  reach the next; nothing in the interface calls it. */
export function clearDrafts() {
  held.clear()
  announce()
}

export function useDraft(key: string): { draft: Draft; setDraft: SetDraft } {
  const [, redraw] = useState(0)
  useEffect(() => {
    const fn = () => redraw((n) => n + 1)
    listeners.add(fn)
    return () => { listeners.delete(fn) }
  }, [])
  /* A key with nothing behind it is a fresh draft, minted per render exactly
     as it was when this record was React state -- and `set` below drops a
     guarded write against it, because there is no attempt to belong to. */
  const draft = held.get(key) ?? newDraft()
  const setDraft: SetDraft = (next, ifOp) => {
    if (ifOp && held.get(key)?.op !== ifOp) return
    held.set(key, next)
    announce()
  }
  return { draft, setDraft }
}
