/* THE CONVERSATION'S OWN PRESENTATION STATE (completion stream B): pinned
 * threads, where each thread's composer replies, conversation focus and the
 * participant filter. Presentation only: nothing here writes to the record.
 *
 * PINNED THREADS (#187 #5, #188 decision 3). A slide-out thread is temporary:
 * reading another post closes it (#184). Pin makes it stay. Several pinned
 * threads are tabs in ONE panel beside the conversation; a temporary thread
 * opened while some are pinned shows as one more, unpinned, tab in the same
 * panel. They are part of the place's arrangement (stream D; #188: "zones,
 * pages, kept items and pinned threads are saved per place"): this tab's
 * until Save keeps them in the Brain with the rest, so a reload keeps them
 * and another browser opens with them once saved. Which tab is shown is
 * reading state, this page's only.
 *
 * THE COMPOSER BELONGS TO THE SURFACE WITH FOCUS (#188, #448). Each thread
 * has its own composer; `target` is what it replies to (the thread's root
 * unless a reply in it was chosen), and `ask` focuses it.
 *
 * CONVERSATION FOCUS (#117): a conversation-focused arrangement of the same
 * workspace -- the conversation takes the room, the workspace recedes without
 * being unmounted, so position, drafts and arrangement all survive. */

import { useSyncExternalStore } from 'react'
import { store, type Id } from '../store'
import { workspace } from '../workspace/place'

interface Pins { pinned: Id[]; active: Id | null }

const FOCUS = 'mentis:fluid:focus'
const FILTER = 'mentis:fluid:filter'

function readJson<T>(key: string, fallback: T, where: Storage | null = safe(() => localStorage)): T {
  try { const v = where?.getItem(key); return v ? (JSON.parse(v) as T) : fallback } catch { return fallback }
}
function writeJson(key: string, v: unknown, where: Storage | null = safe(() => localStorage)) {
  try { where?.setItem(key, JSON.stringify(v)) } catch { /* a convenience, not a record */ }
}
function safe<T>(fn: () => T): T | null { try { return fn() } catch { return null } }

/** which pinned tab is shown, per conversation: this page's only */
let shownTab: Record<Id, Id | null> = {}
let focus: boolean = readJson(FOCUS, false)
let filters: Record<Id, Id[]> = readJson(FILTER, {}, safe(() => sessionStorage))
let targets: Record<Id, Id | null> = {}
let version = 0
const heard = new Set<() => void>()
const emit = () => { version += 1; for (const fn of [...heard]) fn() }
const subscribe = (fn: () => void) => { heard.add(fn); return () => { heard.delete(fn) } }
const snapshot = () => version

/** Re-render when any of this changes. */
export const useThreads = () => useSyncExternalStore(subscribe, snapshot)

/* -- pinned threads --------------------------------------------------------- */

const NONE: Pins = { pinned: [], active: null }
/* The pins of the place shown, read from its arrangement; a conversation
   not shown (between two) has none. One Pins object per change, so a hook
   reading it sees the same value until something changes. */
let held: { key: string | null; pinned: string[]; active: Id | null; pins: Pins } = { key: null, pinned: [], active: null, pins: NONE }
function current(): Pins {
  const pinned = workspace.arr.threads?.pinned ?? []
  const key = workspace.key
  const want = key ? shownTab[key] ?? null : null
  const active = want && pinned.includes(want) ? want : pinned[pinned.length - 1] ?? null
  if (held.key !== key || held.active !== active || held.pinned.join() !== pinned.join())
    held = { key, pinned, active, pins: pinned.length ? { pinned, active } : NONE }
  return held.pins
}
/* The arrangement changes (a pin, Restore saved, another place entered):
   whoever draws the pins draws again -- only when they changed. */
workspace.subscribe(() => { const was = held.pins; if (current() !== was) emit() })

export const pinsOf = (conversation: Id | null): Pins => (conversation && conversation === workspace.key ? current() : NONE)

export function setPins(conversation: Id, next: Pins) {
  if (conversation !== workspace.key) return
  shownTab = { ...shownTab, [conversation]: next.active }
  const same = (workspace.arr.threads?.pinned ?? []).join() === next.pinned.join()
  if (!same) workspace.quiet(({ threads: _was, ...a }) => (next.pinned.length ? { ...a, threads: { pinned: next.pinned, active: null } } : a))
  emit()
}
export const isPinned = (conversation: Id | null, root: Id) => pinsOf(conversation).pinned.includes(root)

export function pin(conversation: Id, root: Id) {
  const p = pinsOf(conversation)
  setPins(conversation, { pinned: p.pinned.includes(root) ? p.pinned : [...p.pinned, root], active: root })
}
export function unpin(conversation: Id, root: Id) {
  const p = pinsOf(conversation)
  const rest = p.pinned.filter((r) => r !== root)
  setPins(conversation, { pinned: rest, active: p.active === root ? rest[rest.length - 1] ?? null : p.active })
}
export function activate(conversation: Id, root: Id) {
  const p = pinsOf(conversation)
  if (!p.pinned.includes(root)) return
  if (p.active !== root) setPins(conversation, { ...p, active: root })
  for (const fn of [...shown]) fn(root)
}
/* A pinned thread was asked for (its chip, its tab, Reply in it): whoever
   must show it -- the narrow sheet's thread pane -- is told, even when it
   was the tab already shown. */
const shown = new Set<(root: Id) => void>()
export function onShown(fn: (root: Id) => void) { shown.add(fn); return () => { shown.delete(fn) } }

/* -- each thread's composer ------------------------------------------------- */

/** What the composer of `root`'s thread replies to: a reply in it, or null
 *  for the root itself. */
export const targetOf = (root: Id): Id | null => targets[root] ?? null
export function setTarget(root: Id, post: Id | null) {
  targets = { ...targets, [root]: post && post !== root ? post : null }
  emit()
}

const asked = new Set<(root: Id) => void>()
/** Put the caret in `root`'s thread composer (once it is drawn). */
export function ask(root: Id) {
  requestAnimationFrame(() => requestAnimationFrame(() => { for (const fn of [...asked]) fn(root) }))
}
export function onAsk(fn: (root: Id) => void) { asked.add(fn); return () => { asked.delete(fn) } }

/** A reply was just written in `root`'s thread: its body shows it when it arrives. */
const wrote = new Set<Id>()
export function posted(root: Id) { wrote.add(root) }
export function takePosted(root: Id): boolean { return wrote.delete(root) }

/** Is `post` the root of `root`'s thread, or a reply anywhere under it? */
export function inThread(post: Id, root: Id): boolean {
  let at: Id | null = post
  for (let i = 0; at && i < 64; i++) {
    if (at === root) return true
    at = store.posts.get(at)?.reply_to ?? null
  }
  return false
}

/* -- where a post is drawn ---------------------------------------------------- */

/** The post the conversation draws for `post`: the highest of it and the
 *  posts it replies to that is a member here (a reply is drawn through its
 *  thread), else `post` itself. */
export async function drawnBy(conversation: Id, post: Id): Promise<Id> {
  let best = post
  let at: Id | null = post
  for (let i = 0; at && i < 32; i++) {
    if (!store.posts.has(at)) await store.loadPosts([at]).catch(() => {})
    const p = store.posts.get(at)
    if (!p) break
    if (p.home === conversation || (p.memberships ?? []).some((m) => m.conversation === conversation)) best = at
    at = p.reply_to ?? null
  }
  return best
}

/* -- conversation focus ----------------------------------------------------- */

export const focused = () => focus
export function setFocused(on: boolean) {
  if (focus === on) return
  focus = on
  writeJson(FOCUS, on)
  emit()
}

/** Something asked to be shown in the workspace -- "→ This post", a medium
 *  from About -- is shown: Focus, which steps the workspace back, is left
 *  (#184; opr-835dfb8981a8 item 6). The reader's place is kept (Column.tsx). */
export function showWorkspaceContent() {
  setFocused(false)
}

/* -- the participant filter (the conversation's menu) ------------------------ */

/* -- the Topic in force (A8) -------------------------------------------------- */

/** The Topic a conversation is read under, or null for all its posts: the
 *  scope production's Topics rail sets (`?topic=`). For this tab only. */
const TOPIC = 'mentis:fluid:topic'
let topics: Record<Id, Id> = readJson(TOPIC, {}, safe(() => sessionStorage))
export const topicOf = (conversation: Id | null): Id | null => (conversation && topics[conversation]) || null
export function setTopic(conversation: Id, topic: Id | null) {
  if (topicOf(conversation) === topic) return
  topics = { ...topics }
  if (topic) topics[conversation] = topic
  else delete topics[conversation]
  writeJson(TOPIC, topics, safe(() => sessionStorage))
  emit()
}

/** Whose posts are shown here; empty is everyone's. For this tab only. */
export const filterOf = (conversation: Id | null): Id[] => (conversation && filters[conversation]) || []
export function setFilter(conversation: Id, who: Id[]) {
  filters = { ...filters, [conversation]: who }
  if (!who.length) delete filters[conversation]
  writeJson(FILTER, filters, safe(() => sessionStorage))
  emit()
}
