/* TRACK C owns this module: A POST'S WHOLE WORDS, ASSEMBLED FROM THE PARTS
   THAT DRAW THEM.

   THE PROBLEM. An anchor's passage is an offset into ONE text part, and it is
   placed in the rendered post by way of the post's JOINED words -- every text
   and reference part run together, with each text part's span kept
   (`annotated.ts` `sourceOf`). Quiet draws a post one part at a time:
   `Post.tsx` hands each part to `parts.tsx` on its own, no part sees its
   siblings, and `Post.tsx` is not this package's to change. So the layer that
   places the marks was given the FIRST part's text and nothing else, and an
   anchor on any later text part had no span to be found in: `drawnRange`
   answered null and the icon sat at the top of the body, a fixed distance
   above the passage it is supposed to be level with.

   THE ANSWER IS THE ONE THIS PACKAGE ALREADY USES for the same shape of
   problem (`margin/carried.ts`, and `composer/drafts.ts` before it): one
   module-level record, written by whoever knows and read by whoever shows.
   Each part says what it draws under its own index; the layer reads the
   assembled `Source` and re-measures when a later part arrives. No prop
   crosses the frozen shell, and nothing here reads the DOM.

   WHAT A PART SAYS IS WHAT IT DRAWS, not what it is in the record. An
   attachment is an `object` part, which the joined words would include, but
   `MediaPart` draws it as `data-src-skip` chrome -- so it contributes no
   words here either, or the walk would hunt for text the body never shows and
   every passage after it would be misplaced. `parts.tsx` says what each part
   draws, beside the branch that draws it.

   THE INDICES ARE THE RECORD'S. A part that contributes nothing still takes
   its place, because an anchor names its part by index: the assembled list is
   dense, with a gap standing in for a part not drawn (a type the joined walk
   skips), so part 1 is part 1 whatever part 0 turned out to be. */
import { useCallback, useSyncExternalStore } from 'react'
import { sourceOf, type Source } from '../../fluid/conversation/annotated'

/** One part as the post draws it: the type the joined walk should read it as,
 *  and the stored text it stands for ('' where it stands for none). */
export interface Drawn {
  type: string
  text: string
}

/** A part not drawn, or drawn as chrome: neither text nor a reference, so the
 *  joined words skip it and the indices after it still hold. */
const GAP: Drawn = { type: 'quiet-gap', text: '' }

/** A post nothing has said anything about yet. One object, so a hook handed
 *  it is handed the same one every time. */
const NOTHING: Source = { text: '', drawn: '', spans: [] }

const told = new Map<string, Map<number, Drawn>>()
const heard = new Map<string, Set<() => void>>()
const version = new Map<string, number>()
const cache = new Map<string, { at: number; src: Source }>()

function tell(post: string) {
  version.set(post, (version.get(post) ?? 0) + 1)
  for (const fn of [...(heard.get(post) ?? [])]) fn()
}

/** This part of this post draws this. Returns the withdrawal, for an effect's
 *  cleanup: a part no longer drawn says nothing about the post's words. */
export function sayPart(post: string, index: number, drawn: Drawn): () => void {
  const parts = told.get(post) ?? new Map<number, Drawn>()
  told.set(post, parts)
  const had = parts.get(index)
  parts.set(index, drawn)
  if (!had || had.type !== drawn.type || had.text !== drawn.text) tell(post)
  return () => {
    const now = told.get(post)
    /* Only what this registration itself said is withdrawn: a part drawn
       again before its old cleanup ran has already replaced it. */
    if (now?.get(index) !== drawn) return
    now.delete(index)
    if (!now.size) told.delete(post)
    tell(post)
  }
}

/** The post's joined words, as `sourceOf` reads them. Cached per post and per
 *  change, so `useSyncExternalStore` is handed the same `Source` until a part
 *  says something different. */
function sourceFor(post: string): Source {
  const at = version.get(post) ?? 0
  const got = cache.get(post)
  if (got && got.at === at) return got.src
  const parts = told.get(post)
  if (!parts?.size) {
    cache.set(post, { at, src: NOTHING })
    return NOTHING
  }
  const dense: Drawn[] = []
  const last = Math.max(...parts.keys())
  for (let i = 0; i <= last; i++) dense.push(parts.get(i) ?? GAP)
  const src = sourceOf({ parts: dense } as never)
  cache.set(post, { at, src })
  return src
}

/** The post's words as its parts draw them, read again whenever a part
 *  changes what it draws or a later one arrives. */
export function usePostSource(post: string): Source {
  const subscribe = useCallback((fn: () => void) => {
    const set = heard.get(post) ?? new Set<() => void>()
    heard.set(post, set)
    set.add(fn)
    return () => {
      set.delete(fn)
      if (!set.size) heard.delete(post)
    }
  }, [post])
  return useSyncExternalStore(subscribe, () => sourceFor(post), () => NOTHING)
}

/** Thrown away between suites. Nothing in the interface calls it. */
export function clearPostWords() {
  told.clear()
  cache.clear()
  version.clear()
  for (const post of [...heard.keys()]) tell(post)
}
