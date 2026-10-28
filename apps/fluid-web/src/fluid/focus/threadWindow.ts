/* WHERE A REPLY THREAD OPENS, ON A WIDE SCREEN (owner feedback, round 2).
 *
 * The frame hosts threads (nav.ts `hostThreads`) while a conversation's page
 * is shown at a width where windows can be. A thread asked for opens in a
 * window beside the conversation, on the room no other window covers
 * (model.ts threadWindowRect), or comes to the front where it is already
 * shown -- a window, a section, the column. Follow moves the following
 * window to the post read; reading a reply in a thread already shown moves
 * nothing. The model is model.ts's; this file only measures the room and
 * makes the change on the page shown. */

import { store, type Id } from '../store'
import { workspace } from '../workspace/place'
import { inThread } from '../conversation/threads'
import * as nav from '../nav'
import { floatThread, followerOf, markFollower, setThreadRoot, threadOf, threadRootOf, threadsOf, threadWindowRect, toFront } from './model'
import { pulseArrived } from './drag'
import { onPage, pageView, shownPage } from './page'
import type { Located } from './types'

type Rect = { x: number; y: number; w: number; h: number }

/** The main area, and the conversation's rectangle in it where it is drawn. */
function measure(): { room: { w: number; h: number }; conv: Rect | null } {
  const main = typeof document === 'undefined' ? null : document.querySelector<HTMLElement>('.fx-main')
  const m = main?.getBoundingClientRect()
  const room = { w: m?.width || 1200, h: m?.height || 800 }
  const el = main ? [...main.querySelectorAll<HTMLElement>('.fx-conv')].find((x) => !x.classList.contains('fq-col-zone') && x.getBoundingClientRect().width > 0) : null
  const c = el?.getBoundingClientRect()
  return { room, conv: c && m ? { x: c.left - m.left, y: c.top - m.top, w: c.width, h: c.height } : null }
}

const front = (at: Located, page: string) => {
  if (at.place === 'float') workspace.quiet(onPage((v) => toFront(v, at.float.id), page))
  pulseArrived(at.zone.id, at.place === 'float' ? at.float.id : undefined)
}

function open(root: Id, conversation: Id, page: string, follow: boolean): boolean {
  const before = workspace.arr
  const { room, conv } = measure()
  const v = pageView(before, page)
  const rect = threadWindowRect(room, conv, v.focus?.floats ?? [])
  workspace.edit(onPage((x) => floatThread(x, root, rect, conversation, store.posts.get(root)?.number ?? null, follow), page))
  if (workspace.arr === before) return false
  const made = threadOf(pageView(workspace.arr, page), root)
  if (made) pulseArrived(made.zone.id, made.place === 'float' ? made.float.id : undefined)
  return true
}

/** Show `root`'s thread on the page shown, `how` nav asked. */
export function showThread(root: Id, conversation: Id, how: 'open' | 'follow'): boolean {
  const page = shownPage()
  const v = pageView(workspace.arr, page)
  if (how === 'follow') {
    const follower = followerOf(v)
    /* a post read inside a thread already shown: that thread stays, and with
       none following yet, it is the one that follows now */
    const holding = threadsOf(v).find((t) => inThread(root, threadRootOf(t.zone)!))
    if (holding) {
      if (!follower) workspace.quiet(onPage((x) => markFollower(x, holding.zone.id), page))
      return true
    }
    if (follower) {
      workspace.quiet(onPage((x) => setThreadRoot(x, follower.zone.id, root, store.posts.get(root)?.number ?? null), page))
      if (follower.place === 'float') workspace.quiet(onPage((x) => toFront(x, follower.float.id), page))
      return true
    }
    return open(root, conversation, page, true)
  }
  const at = threadOf(v, root)
  if (at) { front(at, page); return true }
  return open(root, conversation, page, false)
}

/* A thread asked for while the place is still being entered (a link with a
   thread, a reload) waits until it has settled: a change made before what the
   Brain keeps for it arrives would set that aside (place.ts Holder.ready). */
let waiting: { root: Id; conversation: Id; how: 'open' | 'follow'; at: number } | null = null
workspace.subscribe(() => {
  if (!waiting) return
  if (Date.now() - waiting.at > 15000) { waiting = null; return }
  if (workspace.key !== waiting.conversation || !workspace.ready) return
  const w = waiting
  waiting = null
  showThread(w.root, w.conversation, w.how)
})

/** The host the frame registers (nav.hostThreads). */
export function threadHost(root: Id, conversation: Id | null, how: 'open' | 'follow'): boolean {
  if (!conversation) return false
  if (workspace.key !== conversation || !workspace.ready) {
    waiting = { root, conversation, how, at: Date.now() }
    return true
  }
  return showThread(root, conversation, how)
}

/** Follow from a thread window's menu: on, it is the window that shows the
 *  replies of each post read; off, nothing follows. */
export function followIn(zoneId: string | null, page: string = shownPage()) {
  nav.setFollow(!!zoneId)
  workspace.quiet(onPage((v) => markFollower(v, zoneId), page))
}
