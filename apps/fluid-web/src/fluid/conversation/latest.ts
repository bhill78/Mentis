/* LATEST: the newest conversation activity, and opening it exactly.
 *
 * The owner (2026-10): "Provide a clear way in Fluid to reach the latest
 * conversation activity, including a new reply to an older post, and open
 * that exact reply." A conversation is drawn by thread, so a new reply under
 * an old post lands far up the page; `GET /fluid/api/latest` names the newest
 * posts with what each answers and the top of its thread (`root`), and this
 * opens one the way every post opened from elsewhere opens:
 *
 *  - in the conversation already shown, the thread of `root` with the reply
 *    read inside it, as ONE step (`nav.openDetail(..., { read })`, as tracing
 *    "from #N" does) -- Back returns to where the reader was;
 *  - anywhere else, by address (the bar's `onOpenPost`, Shell's
 *    `handleOpenPost`), whose arrival opens the thread that draws it here
 *    round the reply (`nav.arrive(c, post, n, { root })`).
 *
 * Either way the reply is the post read -- Sheets / PostCard bring the post
 * read into view -- and it is marked for a moment (`fx-latest`), so the eye
 * finds it.
 *
 * AGENT WORK IS LEFT OUT BY DEFAULT, as a conversation folds it away
 * (agentWork.ts; owner, 2026-10: "Apply the existing agent-chatter filtering
 * to Latest as well"). The server says which posts are agent work -- the
 * same `agent_work.classify`, never-hidden rules first -- and leaves them out
 * unless asked (`?agent_work=1`); whether Latest shows them is the reader's,
 * remembered in this browser, for the bar's Latest and the switcher's alike.
 *
 * "NEW SINCE YOU LOOKED" IS THIS BROWSER'S: the time of the newest post the
 * reader was shown, in localStorage. Nothing is kept in the Brain. */

import { useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { CLIENT_HEADERS } from '../../api'
import * as nav from '../nav'
import { store, type Id } from '../store'
import { useList } from './hooks'
import './latest.css'

export interface LatestItem {
  id: Id
  conversation: Id
  conversation_name: string
  number: number | null
  reply_to: Id | null
  reply_to_number: number | null
  /** the top of its thread; the post itself when it answers nothing */
  root: Id
  author: Id
  author_alias: string
  at: number
  excerpt: string | null
  deleted?: boolean
  /** with agent work shown: what it is, or null when it is not agent work */
  agent_work?: { kind: string; why: string } | null
}

/** One read of Latest: its items, and what was left out. */
export interface LatestPage {
  items: LatestItem[]
  /** agent work posts left out above the last item (agent work hidden) */
  hidden: number
  /** agent work posts among the items (agent work shown) */
  agentWork: number
  /** read with agent work shown */
  showing: boolean
}

export const LATEST = 'latest'
export const LATEST_SHOWN = 10

/* -- agent work: shown or not, this browser's choice ---------------------- */

const WORK = 'mentis:fluid:latest:agent-work'
let showWork: boolean = (() => { try { return localStorage.getItem(WORK) === '1' } catch { return false } })()
const workHeard = new Set<() => void>()

/** Does Latest show agent work? Not unless the reader said. */
export const showsLatestWork = () => showWork
export const useLatestWork = () => useSyncExternalStore((fn) => { workHeard.add(fn); return () => { workHeard.delete(fn) } }, () => showWork)
export function setShowsLatestWork(on: boolean): void {
  if (on === showWork) return
  showWork = on
  try { if (on) localStorage.setItem(WORK, '1'); else localStorage.removeItem(WORK) } catch { /* a convenience, not a record */ }
  for (const fn of [...workHeard]) fn()
}

/** The newest posts, everywhere or in one conversation, agent work left
 *  out unless `work` (by default, the reader's choice). */
export async function loadLatestPage(conversation?: Id | null, limit = LATEST_SHOWN, work = showWork): Promise<LatestPage> {
  const q = new URLSearchParams({ limit: String(limit) })
  if (conversation) q.set('conversation', conversation)
  if (work) q.set('agent_work', '1')
  const res = await fetch('/fluid/api/latest?' + q.toString(), { headers: { ...CLIENT_HEADERS } })
  if (!res.ok) throw new Error(`latest: ${res.status}`)
  const body = (await res.json()) as { items?: LatestItem[]; hidden?: number; agent_work_count?: number }
  return { items: body.items ?? [], hidden: body.hidden ?? 0, agentWork: body.agent_work_count ?? 0, showing: work }
}

/** The newest posts, as `loadLatestPage`, the items alone. */
export async function loadLatest(conversation?: Id | null, limit = LATEST_SHOWN): Promise<LatestItem[]> {
  return (await loadLatestPage(conversation, limit)).items
}

/* -- what this browser has seen ------------------------------------------- */

const SEEN = 'mentis:fluid:latest:seen'
let seen: number | null = (() => {
  try { const v = Number(localStorage.getItem(SEEN)); return Number.isFinite(v) && v > 0 ? v : null } catch { return null }
})()
const heard = new Set<() => void>()

/** When the newest post this browser was shown was recorded (null: never). */
export const seenAt = () => seen
export const useSeenAt = () => useSyncExternalStore((fn) => { heard.add(fn); return () => { heard.delete(fn) } }, () => seen)

/** The reader has been shown everything up to `at`. */
export function markSeen(at: number | null | undefined): void {
  if (at == null || (seen != null && at <= seen)) return
  seen = at
  try { localStorage.setItem(SEEN, String(at)) } catch { /* this page only */ }
  for (const fn of [...heard]) fn()
}

/** Is this newer than what the reader was last shown? Before they have
 *  looked at all, nothing is called new -- everything would be. */
export const isNew = (item: LatestItem, since: number | null = seen) => since != null && item.at > since

/* -- reading it ----------------------------------------------------------- */

/** The newest posts, read when asked, again as the conversations move, and
 *  again when the reader shows or hides agent work. */
export function useLatest(on: boolean, conversation?: Id | null, now?: boolean): LatestPage | null {
  const list = useList()
  const work = useLatestWork()
  const [got, setGot] = useState<LatestPage | null>(null)
  /* The list moves when any conversation does (a post, a reply): a cheap,
     already-followed signal to read Latest again. */
  const moved = (list ?? []).reduce((m, c) => Math.max(m, c.last_activity ?? 0), 0)
  /* AT REST IT WAITS ITS TURN: the page's own reads -- the conversation,
     the post an address names -- go first, and a burst of moves is read
     once. Asked for (`now`: the sheet open), it is read at once. */
  const settled = useRef(false)
  useEffect(() => {
    if (!on) return
    let live = true
    const wait = now ? 0 : settled.current ? 400 : 2500
    const t = setTimeout(() => {
      settled.current = true
      void loadLatestPage(conversation, LATEST_SHOWN, work).then((x) => { if (live) setGot(x) },
        () => { if (live) setGot((g) => g ?? { items: [], hidden: 0, agentWork: 0, showing: work }) })
    }, wait)
    return () => { live = false; clearTimeout(t) }
  }, [on, conversation, moved, now, work])
  return got
}

/** Is `L` someone else's now? Typed into a field or editable text, already
 *  handled, held down, with a modifier, or pressed while anything is open
 *  over the page -- a sheet (this one included: Esc closes it), the media
 *  viewer, a full-screen post, any modal dialog. */
export function keyIsNotOurs(e: KeyboardEvent, sheetIsOpen: boolean): boolean {
  if (e.defaultPrevented || e.repeat || e.ctrlKey || e.metaKey || e.altKey || e.isComposing) return true
  const t = e.target as HTMLElement | null
  if (t && (t.matches?.('input, textarea, select, [role="textbox"], [role="combobox"]') || t.isContentEditable
    || t.closest?.('[contenteditable]:not([contenteditable="false"])'))) return true
  if (sheetIsOpen) return true
  return !!document.querySelector('[aria-modal="true"], dialog[open], .pz-viewer, .fx-full')
}

/** Where Latest's sheet opens under: its bar control, or -- where the bar
 *  has let it give way (latest.css) -- the conversation's name. */
export function latestAnchor(): HTMLElement | null {
  const own = document.getElementById('latest')
  if (own && own.getBoundingClientRect().width > 0) return own
  return document.getElementById('title')
}

/* -- opening it ----------------------------------------------------------- */

/* The bar's way to open a post by address (Shell's `handleOpenPost`),
   registered by the bar, which is always drawn: the switcher's Latest uses
   it too without a prop of its own. */
let byAddress: ((c: Id, p: Id) => void) | null = null
export function setOpener(fn: (c: Id, p: Id) => void): () => void {
  byAddress = fn
  return () => { if (byAddress === fn) byAddress = null }
}

/** Open `item` exactly: its thread, with it the post read, brought into
 *  view and marked for a moment. `here`: the conversation shown, if one is. */
export function openLatest(item: LatestItem, here: Id | null): void {
  markSeen(item.at)
  const want = [...new Set([item.id, item.root, item.reply_to].filter((x): x is Id => !!x))]
  const go = () => {
    if (here && here === item.conversation && nav.snapshot().conversation === here) {
      const n = store.posts.get(item.id)?.number ?? item.number
      nav.openRail()
      if (item.root === item.id) nav.read(here, item.id, n)
      else nav.openDetail({ kind: 'replies', root: item.root, anchor: { kind: 'post', id: item.root }, mode: 'aside' },
        { read: { conversation: here, post: item.id, number: n } })
    } else if (byAddress) {
      byAddress(item.conversation, item.id)
    } else {
      return
    }
    mark(item.id)
  }
  void store.loadPosts(want).then(go, go)
}

/** Open the newest post of one conversation (the switcher's Latest): its
 *  newest the reader would be shown, agent work left out unless shown. */
export async function openLatestIn(conversation: Id, here: Id | null, orPick: (c: Id) => void): Promise<void> {
  const items = await loadLatest(conversation, 1).catch(() => [] as LatestItem[])
  if (items[0]) openLatest(items[0], here)
  else orPick(conversation)
}

const MARK_MS = 2400
const WAIT_MS = 8000

/** Find the post read once it is drawn -- in its thread when it is a reply --
 *  bring it into view if it is not, and mark it for a moment. */
function mark(id: Id): void {
  const sel = `[data-post="${CSS.escape(id)}"]`
  const started = performance.now()
  const find = (): HTMLElement | null =>
    document.querySelector<HTMLElement>(`#thread ${sel}.reading`)
    ?? document.querySelector<HTMLElement>(`${sel}.reading`)
  const tick = () => {
    const el = find()
    if (!el) {
      if (performance.now() - started < WAIT_MS) setTimeout(tick, 80)
      return
    }
    const r = el.getBoundingClientRect()
    if (r.bottom < 0 || r.top > window.innerHeight) el.scrollIntoView({ block: 'center' })
    el.classList.add('fx-latest')
    el.setAttribute('data-latest', '')
    setTimeout(() => { el.classList.remove('fx-latest'); el.removeAttribute('data-latest') }, MARK_MS)
  }
  setTimeout(tick, 0)
}
