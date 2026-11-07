/* WHOSE POSTS TO SHOW: the record of it, lifted out of the tree.
 *
 * A filter is a READING PREFERENCE about a conversation, not a fact about it,
 * and it belongs to whoever is reading. So, like `composer/drafts.ts`, it is
 * kept here rather than in the component that shows the chips -- moving to a
 * topic, opening a thread and coming back must not silently show posts the
 * reader had put away -- and it is written to `localStorage` under the
 * conversation, so it survives a reload the way the atmosphere does.
 *
 * EMPTY MEANS EVERYONE, and it is the only way to say that. A filter listing
 * every participant would be the same reading with a different record of it,
 * so `setWhoFilter` reduces that case to empty before it stores anything --
 * which is what lets "All" be `aria-pressed` on exactly one state.
 *
 * Storage that is missing, full or refused changes nothing about the reading:
 * the filter still works for this sitting and is simply not remembered. */

import { useEffect, useState } from 'react'
import type { Id } from '../../api'

const KEY = (conversation: Id) => `mentis:quiet:who:${conversation}`

const held = new Map<Id, Id[]>()
const listeners = new Set<() => void>()
const announce = () => { for (const fn of [...listeners]) fn() }

function remembered(conversation: Id): Id[] {
  try {
    const raw = localStorage.getItem(KEY(conversation))
    if (!raw) return []
    const got: unknown = JSON.parse(raw)
    return Array.isArray(got) ? got.filter((x): x is Id => typeof x === 'string') : []
  } catch { return [] }
}

/** Whom the posts are filtered by in this conversation; empty is everyone. */
export function whoFilter(conversation: Id): Id[] {
  const had = held.get(conversation)
  if (had) return had
  const read = remembered(conversation)
  held.set(conversation, read)
  return read
}

/** Show these people's posts and nobody else's; empty, or everybody there is,
 *  is everyone. `all` is who there is to show, where the caller knows. */
export function setWhoFilter(conversation: Id, who: Iterable<Id>, all: Id[] = []): void {
  const chosen = [...new Set(who)]
  const every = all.length > 0 && all.every((a) => chosen.includes(a))
  const next = chosen.length === 0 || every ? [] : chosen
  held.set(conversation, next)
  try {
    if (next.length) localStorage.setItem(KEY(conversation), JSON.stringify(next))
    else localStorage.removeItem(KEY(conversation))
  } catch { /* unavailable storage: the reading stands, unremembered */ }
  announce()
}

/** Every filter, forgotten -- including what was stored. Used by the suites,
 *  so one case's reading cannot reach the next. */
export function clearWhoFilters(): void {
  for (const conversation of held.keys()) {
    try { localStorage.removeItem(KEY(conversation)) } catch { /* nothing to undo */ }
  }
  held.clear()
  announce()
}

/** The filter in force here, as a reader sees it move. */
export function useWhoFilter(conversation: Id): Id[] {
  const [, redraw] = useState(0)
  useEffect(() => {
    const fn = () => redraw((n) => n + 1)
    listeners.add(fn)
    return () => { listeners.delete(fn) }
  }, [])
  return whoFilter(conversation)
}

/** WHICH POSTS THE FILTER LEAVES. Pure, and by the post's AUTHOR alone: who
 *  wrote it is what a chip says, and nothing here reads a post's prose,
 *  addressees or topics. An empty filter leaves the list untouched -- the same
 *  array, so a reader cannot tell "everyone" from "no filter", because they
 *  are not different readings. */
export function filterTurns<T extends { author: Id }>(turns: T[], filter: Id[]): T[] {
  if (!filter.length) return turns
  const who = new Set(filter)
  return turns.filter((t) => who.has(t.author))
}
