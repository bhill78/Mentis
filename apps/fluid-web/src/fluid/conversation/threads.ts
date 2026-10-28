/* THE CONVERSATION'S OWN PRESENTATION STATE (completion stream B): pinned
 * threads, where each thread's composer replies, conversation focus and the
 * participant filter. Presentation only: nothing here writes to the record.
 *
 * KEPT THREADS (#187 #5, #188 decision 3; owner feedback, round 2). A
 * slide-out thread is temporary: reading another post closes it (#184). A
 * thread kept stays -- and is now a WINDOW of the workspace (focus/model.ts
 * THREAD_SHOW), opened beside the conversation on a wide screen, which docks,
 * floats, is made primary and so on like any other. At a narrow width the
 * kept threads are still tabs in the ONE sheet beside the conversation. They
 * are part of the place's arrangement (stream D; #188: "zones, pages, kept
 * items and pinned threads are saved per place"): this tab's until Save keeps
 * them in the Brain with the rest (place.ts readThreadWindows). Which tab is
 * shown is reading state, this page's only.
 *
 * THE COMPOSER BELONGS TO THE SURFACE WITH FOCUS (#188, #448). Each thread
 * has its own composer; `target` is what it replies to (the thread's root
 * unless a reply in it was chosen), and `ask` focuses it.
 *
 * CONVERSATION FOCUS (#117): a conversation-focused arrangement of the same
 * workspace -- the conversation takes the room, the workspace recedes without
 * being unmounted, so position, drafts and arrangement all survive. */

import { useSyncExternalStore } from 'react'
import * as nav from '../nav'
import { store, type Id } from '../store'
import { workspace, type Arr } from '../workspace/place'
import { removeLeaf, zones } from '../workspace/tree'
import { closeFloat, floatThread, threadOf, threadRootOf, threadsOf, threadWindowRect, toFront } from '../focus/model'
import { onPage, pageView, shownPage } from '../focus/page'
import type { Located } from '../focus/types'

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

/* KEPT THREADS ARE THREAD WINDOWS (owner feedback, round 2: a reply thread is
   a surface like the others, focus/model.ts THREAD_SHOW). What was pinned is
   now each thread shown on the page -- in a window, a section or the column
   -- so it stays while other posts are read, and is saved with the place
   (place.ts readThreadWindows). The frontmost is the one shown first; at a
   narrow width, where nothing floats, they are the thread pane's tabs. */
const NONE: Pins = { pinned: [], active: null }
let held: { key: string | null; pinned: string[]; active: Id | null; pins: Pins } = { key: null, pinned: [], active: null, pins: NONE }
function current(): Pins {
  const pinned = [...new Set(threadsOf(pageView(workspace.arr, shownPage())).map((t) => threadRootOf(t.zone)!))]
  const key = workspace.key
  const want = key ? shownTab[key] ?? null : null
  const active = want && pinned.includes(want) ? want : pinned[pinned.length - 1] ?? null
  if (held.key !== key || held.active !== active || held.pinned.join() !== pinned.join())
    held = { key, pinned, active, pins: pinned.length ? { pinned, active } : NONE }
  return held.pins
}
/* The arrangement changes (a window opened or closed, Restore saved, another
   place or page): whoever draws the threads draws again -- only when they changed. */
const changed = () => { const was = held.pins; if (current() !== was) emit() }
workspace.subscribe(changed)
nav.subscribe(changed)

export const pinsOf = (conversation: Id | null): Pins => (conversation && conversation === workspace.key ? current() : NONE)
export const isPinned = (conversation: Id | null, root: Id) => pinsOf(conversation).pinned.includes(root)

/** Keep `root`'s thread here: in a window of its own (beside the
 *  conversation, as opening it does on a wide screen). */
export function pin(conversation: Id, root: Id) {
  if (conversation !== workspace.key) return
  shownTab = { ...shownTab, [conversation]: root }
  if (!isPinned(conversation, root)) {
    const post = store.posts.get(root)
    workspace.edit(onPage((v) => floatThread(v, root, threadWindowRect(mainRoom(), null, v.focus?.floats ?? []), conversation, post?.number ?? null)),
      `The thread of ${post?.number != null ? `#${post.number}` : 'this post'} is in a window: it stays while you read other posts.`)
  }
  emit()
}
/** Close every window showing `root`'s thread on the page shown. */
export function unpin(conversation: Id, root: Id) {
  if (conversation !== workspace.key) return
  workspace.edit(onPage((v) => {
    let next = v
    for (const t of threadsOf(v)) if (threadRootOf(t.zone) === root) next = closeThread(next, t)
    return next
  }), 'Closed the thread.')
}
/** Show `root`'s thread: its window to the front, or its tab at a narrow width. */
export function activate(conversation: Id, root: Id) {
  const p = pinsOf(conversation)
  if (!p.pinned.includes(root)) return
  shownTab = { ...shownTab, [conversation]: root }
  const at = threadOf(pageView(workspace.arr, shownPage()), root)
  if (at?.place === 'float') workspace.quiet(onPage((v) => toFront(v, at.float.id)))
  emit()
  for (const fn of [...shown]) fn(root)
}
/** A thread taken off the page: a window closes; docked, its section closes
 *  (the tree's own close). In the primary column it stays: what would take
 *  its place there is the owner's to choose (◎ on another surface). */
function closeThread(a: Arr, at: Located): Arr {
  if (at.place === 'float') return closeFloat(a, at.float.id)
  if (at.place === 'leaf') return zones(a.tree).length > 1 ? { ...a, tree: removeLeaf(a.tree, at.zone.id) } : a
  return a
}
const mainRoom = () => {
  const r = typeof document === 'undefined' ? null : document.querySelector<HTMLElement>('.fx-main')?.getBoundingClientRect()
  return { w: r?.width || 1200, h: r?.height || 800 }
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
