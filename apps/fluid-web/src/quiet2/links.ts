/* WHICH PARENT IS IN QUESTION, WHEREVER IT IS SHOWN (combined refinement).
 *
 * Two things make a post's tie to its parent stand out:
 *  - a reply pointed at (hover or keyboard focus) emphasises its own
 *    connector and the post it actually answers;
 *  - a composer replying to a post marks that post as the parent being
 *    answered, for as long as the reply is being written, in every place the
 *    post is visible (the conversation it came from included).
 * Each composer holds its own entry, by its own key, so two composers never
 * share or overwrite each other's target. Presentation only: nothing here is
 * sent anywhere or decides where a post goes. */
import { useSyncExternalStore } from 'react'
import type { Id } from './sample'

let hovered: { reply: Id; parent: Id } | null = null
const composing = new Map<string, Id>()
let version = 0
const heard = new Set<() => void>()
const changed = () => { version++; heard.forEach((fn) => fn()) }
const subscribe = (fn: () => void) => { heard.add(fn); return () => { heard.delete(fn) } }

/** A reply is pointed at (or no longer is: null). */
export function pointAt(reply: Id | null, parent?: Id) {
  const next = reply && parent ? { reply, parent } : null
  if (next?.reply === hovered?.reply && next?.parent === hovered?.parent) return
  hovered = next
  changed()
}

/** The reply pointed at now, if any. */
export const pointedAt = () => hovered?.reply ?? null

/** The composer `dock` is now replying to `parent` (null: to nothing). */
export function composingTo(dock: string, parent: Id | null) {
  if ((composing.get(dock) ?? null) === parent) return
  if (parent) composing.set(dock, parent); else composing.delete(dock)
  changed()
}

export interface LinkState {
  /** this reply is the one pointed at */
  replyHot: boolean
  /** this post is the parent of the reply pointed at */
  parentHot: boolean
  /** a composer is writing a reply to this post */
  answering: boolean
}

const states = new Map<Id, LinkState>()
let statesAt = -1

/** How `post` stands now; re-renders only when that changes. */
export function useLink(post: Id): LinkState {
  return useSyncExternalStore(subscribe, () => {
    if (statesAt !== version) { states.clear(); statesAt = version }
    let s = states.get(post)
    if (!s) {
      s = {
        replyHot: hovered?.reply === post,
        parentHot: hovered?.parent === post,
        answering: [...composing.values()].includes(post),
      }
      const was = lastOf.get(post)
      if (was && was.replyHot === s.replyHot && was.parentHot === s.parentHot && was.answering === s.answering) s = was
      states.set(post, s)
      lastOf.set(post, s)
    }
    return s
  })
}
const lastOf = new Map<Id, LinkState>()
