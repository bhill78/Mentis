/* FLUID F6 NAVIGATION -- ui/src/fluid/nav.ts
 *
 * The one seam between Track A (frame + conversation) and Track B (workspace)
 * of the F6 "match the #184 demo" pass. These are exactly the contract's
 * exports; this file is their implementation: a small external store, read by
 * React through `subscribe` / `snapshot` (useSyncExternalStore). Presentation
 * state only: nothing here writes to the record or calls the Fluid command API.
 *
 * Semantics follow the demo (adm-629bf77b42f3) and the fidelity spec section 7:
 *  - Every temporary detail opens out of an ANCHOR and returns into it.
 *  - Back retraces steps; each step names its destination ("Back to #216").
 *  - Esc unwinds the whole open detail in one step, back to its anchor.
 *  - Moving to another post closes any temporary detail.
 *  - Keep and Open as page are arrangement changes and offer Undo in a toast.
 *
 * WIDENED IN THE F6 FIX ROUND (each optional, so every earlier caller reads
 * as before):
 *  - `beneath`: an object opened while a post's replies or details are open
 *    opens OVER the workspace and leaves that sheet open BENEATH it, as the
 *    demo does. Esc closes the object back to the sheet; Esc again, the sheet
 *    back to its post. `detail` is still the topmost temporary detail.
 *  - `openDetail(d, { read })`: open a post's replies AND read a post in
 *    them, in another conversation if named, as ONE step -- tracing "from
 *    #223" is one Back from where the reader was, and that Back closes it.
 *  - `enter(conversation)`: arrive at a conversation with nothing read yet (a
 *    new one), so nothing of the last conversation's place is carried in.
 *  - `closeAll()`: every temporary detail at once (a sheet's own ✕ while an
 *    object is open over it); `sheetOf(state)`: the open sheet, either slot.
 *  - (final fix round) `restore(pages, width)`: a reload's pages and width;
 *    `openAsPage` of an object already a page shows that page.
 *
 * WIDENED BY COMPLETION STREAM B (additive): `full` (a post or a thread
 * full screen, over everything, a sheet left beneath it) and `about` (the
 * conversation's Brief / Actions / Follow ups / Media / Guidance slide-out).
 * `isOver` says which details are drawn over the arrangement.
 *
 * WIDENED BY QUIET CHAT ROUND 5 (package S, F7/F8/F14), every addition
 * optional so that /fluid with no options behaves exactly as it did:
 *  - `arrive`, `read` and `openDetail` take an optional `page`, VALIDATED
 *    against this place's own `pages`, so one application can move the
 *    effective conversation, the post read and the Page shown together
 *    instead of in three steps -- including the object-detail branch, which
 *    forced This post.
 *  - `hostExternalNavigation(...)` scopes destination handling to an external
 *    history: Quiet's. In that scope Page changes go through `apply` and
 *    `setPages` and NEVER `navigate`, so they push nothing onto this stack;
 *    the one selection intent is reported to the host, which alone writes the
 *    browser hash. `replayExternal(...)` is the other direction, guarded:
 *    applying the hash reports no new intent and pushes no step, so the two
 *    cannot echo each other. Nothing is scoped unless a host is mounted.
 *  - `addPage(title, { kind: 'deep-dive' })`: the Deep dive label and its own
 *    toast, with the existing Undo. Defaults keep the existing title and
 *    toast exactly.
 *
 * HOW IT KNOWS A POST'S NUMBER AND THREAD. Opening replies reads their root,
 * and reading a reply inside its open thread keeps the thread open. The
 * contract's `openDetail` and `read` carry neither the root's number nor the
 * thread a reply belongs to, so both are looked up in the Fluid store's cache
 * of posts (read only): `number`, and the `reply_to` chain. */

import { store } from './store'
import { showToast } from './frame/toasts'

export type Anchor =
  | { kind: 'post'; id: string }                 // a post card in the conversation
  | { kind: 'object'; address: string }          // a workspace object card
  | { kind: 'zone'; zone: string }               // a workspace zone

export type DetailMode = 'aside' | 'over' | 'focus'  // Mixed: conversation material 'aside', workspace objects 'over'; 'focus' (Objects B2): one object on its own, over everything

/** What "About this conversation" opens at (#188's capability table). */
export type AboutSection = 'brief' | 'actions' | 'followups' | 'media' | 'guidance'

export type Detail =
  | { kind: 'replies'; root: string; anchor: Anchor; mode: 'aside' }
  | { kind: 'post-details'; id: string; anchor: Anchor; mode: 'aside' }
  | { kind: 'object'; address: string; anchor: Anchor; mode: DetailMode }
  /* COMPLETION STREAM B, ADDITIVE. A post or a whole thread full screen
     (#448): over everything, leaving any sheet beneath it, and Esc / Back
     return to exactly the anchor it was opened from. */
  | { kind: 'full'; of: 'post' | 'thread'; id: string; anchor: Anchor; mode: 'over' }
  /* Brief, Actions, Follow ups, Media and Guidance as one slide-out beside
     the conversation, opened from its menu. */
  | { kind: 'about'; conversation: string; section: AboutSection; anchor: Anchor; mode: 'aside' }

export type Page =
  | { id: 'this-post' }                                      // always first, follows the read post
  | { id: string; title: string; object?: string }           // Open as page (its object), or the owner's own (+)

export type ConversationWidth = 'wide' | 'narrow' | 'rail'

/* THE CONVERSATION'S WIDTH IS DRAGGED (Fluid completion, stream A; #187 #6:
   no Narrow/Wide modes). It is pixels; the class the conversation draws
   itself with is read from them -- at its narrowest it is the rail. The
   three names remain only as what a caller asks for ("give it room"). */
/* NO SLIVER OF A COLUMN (the owner: "if the columns are getting too narrow
   ... I'd rather columns go into a hidden or minimized state rather than
   reading a very narrow column of text"). Narrower than READABLE the
   conversation is the rail; between the two it is never drawn. 330 px is
   where the composer still keeps its tools and Send on one row (at 320 Send
   drops to a second) and every post's head is one line (e50ce20: from 316),
   measured on Local LLM Prelim. Opening the rail brings back `openPx`, the
   last readable width. */
export const READABLE = 330
export const PRESET: Record<ConversationWidth, number> = { wide: 440, narrow: READABLE, rail: 64 }
export const CONV_MIN = 64
export const RAIL_BELOW = 150
/** Is this width the rail (anything a reader cannot read)? */
export const railPx = (px: number) => px < READABLE
export const THREAD_MIN = 300
export const classOf = (px: number): ConversationWidth => (px < RAIL_BELOW ? 'rail' : px < 380 ? 'narrow' : 'wide')

export interface NavState {
  conversation: string | null
  reading: string | null          // post id currently read (the anchor of This post)
  readingNumber: number | null    // its home number, for "Reading #N" / "This post . #N"
  /** one decision to show when this post was opened from an Answer action */
  decision?: string | null
  detail: Detail | null           // at most one temporary detail
  beneath?: Detail | null         // replies or details left open under an object detail
  pages: Page[]                   // pages[0] is always { id: 'this-post' }
  page: string                    // id of the shown page
  width: ConversationWidth        // read from convPx
  convPx: number                  // the conversation column, dragged
  threadPx: number                // the replies panel's outer width, dragged
  backLabel: string | null        // e.g. "Back to #216", null when there is nowhere to go
  /** (A1, additive) the replies / details sheet follows the post read */
  follow?: boolean
  /** (A2, additive) the object detail aside under which the reader sized the
   *  conversation themselves: its own narrowing gives way (`drawnConvPx`) */
  sizedUnder?: Detail | null
  /** the last readable width, which opening the rail brings back */
  openPx?: number
  /** the most the stage leaves the conversation beside what is open (Shell
   *  measures it; null where nothing is shared, as in Focus or narrow) */
  convRoom?: number | null
}

/* AN OBJECT DETAIL MOVED ASIDE GIVES IT ROOM (A2, a defect): a wide
   conversation is drawn narrow while one is open beside it -- its area, not
   its words. That is the width it is DRAWN at, so it is the width a dragged
   boundary starts from: dragging from the hidden wider width widened a
   column the reader was narrowing. Once the reader sizes it under that
   object, their width is the one drawn. Focus (Shell.tsx) draws its own.
   NEVER BELOW READABLE: narrowed for an object it stops at READABLE, and
   where the stage has not even that much room beside the replies and the
   workspace, it is drawn as the rail -- its own width kept for when the
   room comes back. */
export const drawnConvPx = (s: NavState): number => {
  const px = s.detail?.kind === 'object' && s.detail.mode === 'aside' && s.width === 'wide' && s.sizedUnder !== s.detail
    ? Math.min(s.convPx, READABLE)
    : s.convPx
  return !railPx(px) && s.convRoom != null && s.convRoom < READABLE ? CONV_MIN : px
}
/** Is the conversation drawn as the rail only for want of room? */
export const squeezed = (s: NavState): boolean => !railPx(s.convPx) && railPx(drawnConvPx(s))

/** Reading a post as part of opening a detail (`openDetail`'s option). */
export interface ReadWith {
  conversation?: string
  post: string
  number: number | null
}

/** The open conversation sheet -- replies or details -- whether it is the
 *  topmost detail or open beneath an object. */
export const sheetOf = (s: NavState): Detail | null =>
  s.detail && !isOver(s.detail) ? s.detail : s.beneath ?? null

/** A detail drawn OVER the arrangement (an object, a full-screen post or
 *  thread): a sheet open beside the conversation stays beneath it. */
export const isOver = (d: Detail | null | undefined): boolean => !!d && (d.kind === 'object' || d.kind === 'full')

export interface Toast {
  text: string
  action?: { label: string; run: () => void }   // e.g. Undo, Start fresh
}

/* -- the store ------------------------------------------------------------ */

/** One step of history: where the reader was. Width is not a step. */
interface Step {
  conversation: string | null
  reading: string | null
  readingNumber: number | null
  decision?: string | null
  detail: Detail | null
  beneath: Detail | null
  page: string
}

const THIS_POST = 'this-post'

/* FOLLOWING THE POST READ (A1, a missing capability). The workspace follows
   the post read; the replies did not -- they opened only from a post's chip
   or Reply, and reading another post closed them. With Follow on (the
   sheet's own control, and the conversation's menu) reading another post in
   the conversation opens ITS replies -- or its details, while details are
   what the sheet shows -- in the same step, so Back returns to the last one.
   Kept per browser, as the Lab's replies mode is (lab/fluid.ts). */
const FOLLOW = 'mentis:fluid:follow'
function readFollow(): boolean {
  try { return localStorage.getItem(FOLLOW) === '1' } catch { return false }
}

let state: NavState = {
  conversation: null,
  reading: null,
  readingNumber: null,
  decision: null,
  detail: null,
  beneath: null,
  pages: [{ id: THIS_POST }],
  page: THIS_POST,
  width: 'wide',
  convPx: PRESET.wide,
  openPx: PRESET.wide,
  convRoom: null,
  threadPx: 400,
  backLabel: null,
  follow: readFollow(),
}
let stack: Step[] = []
let pageSeq = 0
const listeners = new Set<() => void>()
const returning = new Set<(a: Anchor) => void>()

/* -- an external destination history (Quiet Chat round 5, F7/F8) ----------- */

/** WHERE QUIET'S DESTINATIONS GO INSTEAD. Quiet keeps its destination history
 *  in the browser hash, which is addressable and participates in Back and
 *  Forward; a second stack beside it would make one movement take two Backs
 *  to undo. So a host mounted here is told what was asked for -- ONE intent
 *  per transition -- and it alone writes the hash.
 *
 *  `read` carries the Page as well as the conversation and post, because the
 *  three move together: synchronising them one at a time is what put the
 *  parent's composer under the child's heading. */
export interface ExternalNavigation {
  page: (id: string) => void
  read: (conversation: string, post: string | null, page: string, detail?: Detail) => void
}

let external: ExternalNavigation | null = null
let replaying = 0

/** Scope destination handling to an external history. Returns the remover, so
 *  a component that mounts it takes it away again on unmount and /fluid is
 *  never left in this scope. Nothing is scoped while nothing is mounted. */
export function hostExternalNavigation(fn: ExternalNavigation | null): () => void {
  external = fn
  return () => {
    if (external === fn) external = null
  }
}

/** THE OTHER DIRECTION, GUARDED. The location controller applying the hash
 *  (an arrival, Back, Forward) calls the ordinary functions inside this, and
 *  they report no intent and push no step: one guarded direction per
 *  transition, so the hash and this store cannot echo each other. */
export function replayExternal<T>(fn: () => T): T {
  replaying += 1
  try {
    return fn()
  } finally {
    replaying -= 1
  }
}

const intendPage = (id: string) => {
  if (external && !replaying) external.page(id)
}
const intendRead = (conversation: string | null, post: string | null, page: string, detail?: Detail) => {
  if (external && !replaying && conversation) external.read(conversation, post, page, detail)
}

const stepOf = (s: NavState): Step => ({
  conversation: s.conversation,
  reading: s.reading,
  readingNumber: s.readingNumber,
  decision: s.decision ?? null,
  detail: s.detail,
  beneath: s.beneath ?? null,
  page: s.page,
})
const same = (a: Step, b: Step) => JSON.stringify(a) === JSON.stringify(b)
const isConversation = (d: Detail | null) => !!d && (d.kind === 'replies' || d.kind === 'post-details' || d.kind === 'about')

function pageTitle(id: string): string {
  if (id === THIS_POST) return 'This post'
  const p = state.pages.find((x) => x.id === id)
  return p && 'title' in p ? p.title : 'page'
}

/** Where Back goes from here, said as the demo's `describe` says it. */
function describe(prev: Step): string {
  const s = state
  if (prev.conversation === HOME) return 'Back to Home'
  if (s.detail?.kind === 'full' && prev.detail?.kind !== 'full') {
    const n = store.posts.get(s.detail.id)?.number
    return n != null ? `Back to #${n}` : 'Back to the conversation'
  }
  if (s.detail?.kind === 'object' && prev.detail?.kind !== 'object') return 'Back to This post'
  if (isConversation(s.detail) && !isConversation(prev.detail)) return 'Back to the conversation'
  if (prev.conversation !== s.conversation && prev.conversation)
    return `Back to ${prev.conversation === 'stream' ? 'the Stream' : prev.conversation.startsWith('wsp-') ? 'the workspace' : store.conversations.get(prev.conversation)?.name ?? 'the conversation'}`
  if (prev.page !== s.page) return `Back to ${pageTitle(prev.page)}`
  if (prev.reading !== s.reading && prev.readingNumber != null) return `Back to #${prev.readingNumber}`
  return 'Back'
}

function emit() {
  const top = stack[stack.length - 1]
  state = { ...state, backLabel: top ? describe(top) : null }
  for (const fn of [...listeners]) fn()
}

/** Make `next` current, without touching history. A detail that goes away
 *  returns to its anchor, which is told so it can flash. */
/** A sheet left beneath nothing is the topmost detail again (an object that
 *  closed by becoming a page, say): Esc must still reach it. */
const norm = (s: Step): Step => {
  const next = { ...s, decision: s.decision ?? null }
  return !next.detail && next.beneath ? { ...next, detail: next.beneath, beneath: null } : next
}

function apply(step: Step) {
  const next = norm(step)
  const stays = new Set([next.detail, next.beneath].filter(Boolean).map((d) => JSON.stringify(d)))
  const gone = [state.detail, state.beneath ?? null].filter((d): d is Detail => !!d && !stays.has(JSON.stringify(d)))
  const pages = state.pages.some((p) => p.id === next.page) ? next.page : THIS_POST
  state = { ...state, ...next, page: pages }
  emit()
  for (const d of gone) for (const fn of [...returning]) fn(d.anchor)
}

/** A step the reader took: the current place is remembered for Back. */
function navigate(step: Step) {
  const next = norm(step)
  const cur = stepOf(state)
  if (same(cur, next)) return
  /* Arriving is not a step: before anything was read there is nowhere to go back to.
     A workspace of its own is somewhere to go back to, with nothing read in it. */
  if (cur.reading !== null || cur.detail !== null || cur.conversation?.startsWith('wsp-')) stack.push(cur)
  apply(next)
}

/** A DESTINATION CHANGE, in whichever history owns it. Inside the external
 *  scope the browser hash is the history, so the change is applied and
 *  nothing is pushed here; outside it, this is `navigate` and every earlier
 *  caller behaves exactly as it did. */
const move = (step: Step) => (external ? apply(step) : navigate(step))

/** THE PAGE A DESTINATION CHANGE LANDS ON (F7). A Page supplied is honoured
 *  only if this place actually HAS it -- an absent Page cannot be selected,
 *  including one named by another browser's address. */
const pageFor = (page: string | undefined, fallback: string): string =>
  page && state.pages.some((p) => p.id === page) ? page : fallback

/** The Page a call that named none lands on. Inside the external scope that
 *  is the ACTIVE Page, even when the conversation changes: a nested action,
 *  or reading a Deep dive's own post, is no reason to leave the Page it
 *  happened on. Outside the scope, arriving in another conversation returns
 *  to This post as it always has. */
const activePage = (conversation: string | null): string =>
  external || conversation === state.conversation ? state.page : THIS_POST

/** Is `post` the root of the open thread, or a reply somewhere under it? */
function inThread(post: string, root: string): boolean {
  let at: string | null = post
  for (let i = 0; at && i < 64; i++) {
    if (at === root) return true
    at = store.posts.get(at)?.reply_to ?? null
  }
  return false
}

/* Reading */
const num = (n: number | null | undefined) => (n != null && Number.isFinite(n) ? n : null)

export interface ReadOptions {
  number?: number | null
  decision?: string | null
  /** (round 5, F7) the Page to read it on, validated against this place's
   *  own pages; omitted reads as before. */
  page?: string
}

export function read(conversation: string, post: string, numberOrOptions: number | null | ReadOptions): void {
  /* Moving to another post closes the temporary detail -- except a thread's own
     posts, which are read inside it, and the post a details sheet is about.
     An object detail always closes; the sheet beneath it stays on those terms. */
  const keeps = (d: Detail | null | undefined) => !!d && conversation === state.conversation && (
    (d.kind === 'replies' && inThread(post, d.root)) ||
    (d.kind === 'post-details' && d.id === post))
  const sheet = sheetOf(state)
  const options = typeof numberOrOptions === 'object' && numberOrOptions !== null ? numberOrOptions : null
  const number = options ? options.number ?? store.posts.get(post)?.number ?? null : numberOrOptions as number | null
  const page = pageFor(options?.page, activePage(conversation))
  /* ONE INTENT, AND A CROSS-CONVERSATION ONE IS NOT APPLIED HERE: the host
     routes it through the working area's onNavigate first, so nothing inside
     the arrangement can switch the conversation while the Holder still
     belongs to the one it came from. */
  if (external && !replaying) {
    intendRead(conversation, post, page)
    if (conversation !== state.conversation) return
  }
  move({
    conversation,
    reading: post,
    readingNumber: num(number),
    decision: options?.decision ?? null,
    detail: keeps(sheet) ? sheet : followed(conversation, post, sheet),
    beneath: null,
    page,
  })
}

/** With Follow on, the sheet a post read in the conversation already being
 *  read opens for it: its details while details are shown, else its replies.
 *  Arriving in a conversation is not following (nothing was read in it yet). */
function followed(conversation: string, post: string, sheet: Detail | null): Detail | null {
  if (!state.follow || conversation !== state.conversation || state.reading === null) return null
  const anchor: Anchor = { kind: 'post', id: post }
  if (sheet?.kind !== 'post-details' && hosted(post, conversation, 'follow')) return null
  return sheet?.kind === 'post-details'
    ? { kind: 'post-details', id: post, anchor, mode: 'aside' }
    : { kind: 'replies', root: post, anchor, mode: 'aside' }
}

/** Follow the post read (A1): on, the replies or details sheet opens for
 *  each post read; off, reading another post closes it, as before. */
export function setFollow(on: boolean): void {
  if (!!state.follow === on) return
  try { localStorage.setItem(FOLLOW, on ? '1' : '0') } catch { /* this page only */ }
  state = { ...state, follow: on }
  emit()
}

/* REPLY THREADS IN WINDOWS (owner feedback, round 2: "it should match
   everything else"). Where a window can be (a conversation's page on a wide
   screen), the frame hosts threads (`hostThreads`): a thread asked for -- a
   post's "N replies", Reply, a reply arrived at, Follow -- opens in a window
   of the workspace (focus/model.ts THREAD_SHOW), or comes to the front where
   it already is, and the post is read as before; no sheet opens beside the
   conversation. `how` says why: 'follow' moves the following window to the
   post read. The host answers false where it cannot (no room for another
   window), and the sheet opens as it always did -- as it does at a narrow
   width, on Home and over the 3D Brain, where nothing is hosted. */
export type ThreadHost = (root: string, conversation: string | null, how: 'open' | 'follow') => boolean
let threadHost: ThreadHost | null = null
export function hostThreads(fn: ThreadHost | null): void { threadHost = fn }
const hosted = (root: string, conversation: string | null, how: 'open' | 'follow'): boolean => !!threadHost && threadHost(root, conversation, how)
/** Follow turned on with nothing open: the post read shows its replies now --
 *  in the window that follows, where threads are hosted, else in the sheet. */
export function followNow(post: string): void {
  if (hosted(post, state.conversation, 'follow')) return
  openDetail({ kind: 'replies', root: post, anchor: { kind: 'post', id: post }, mode: 'aside' })
}
/** The replies sheet given up for a window (windows became possible while
 *  it was open): no step, and the post read stays read. */
export function dropRepliesSheet(): void {
  const d = sheetOf(state)
  if (d?.kind !== 'replies') return
  apply(state.detail === d ? { ...stepOf(state), detail: null } : { ...stepOf(state), beneath: null })
}

/** Arrive at a conversation with nothing read in it yet (a new one): the
 *  last conversation's place, detail and reading are not carried in. */
export function enter(conversation: string): void {
  navigate({ conversation, reading: null, readingNumber: null, decision: null, detail: null, beneath: null, page: THIS_POST })
}

/** Home itself, as a step: Back to it leaves the conversation for Home (D1). */
export const HOME = 'home'

/** ARRIVING AT A POST OPENED FROM ELSEWHERE, with no step of its own (D1).
 *  `from: HOME`: it was opened from Home, so Back goes to Home -- not into
 *  the conversation Home's column was reading. `root`: the arrival completes,
 *  the thread that draws the post open round it and its number filled in.
 *  Forward onto such an entry arrives the same way, `post` null when the
 *  entry no longer names one (opr-18ce7867fa89). */
export function arrive(conversation: string, post: string | null, number: number | null, opts: { from?: typeof HOME; root?: string; decision?: string | null; page?: string } = {}): void {
  /* Home as a step belongs to Fluid's own stack; inside the external scope
     the browser's history is where going back is recorded. */
  if (opts.from === HOME && !external) stack.push({ conversation: HOME, reading: null, readingNumber: null, detail: null, beneath: null, page: THIS_POST })
  const cur = stepOf(state)
  const here = cur.conversation === conversation && cur.reading === post
  apply({
    conversation,
    reading: post,
    readingNumber: num(number) ?? (here ? cur.readingNumber : null),
    decision: opts.decision ?? null,
    detail: opts.root && !hosted(opts.root, conversation, 'open') ? { kind: 'replies', root: opts.root, anchor: { kind: 'post', id: opts.root }, mode: 'aside' } : null,
    beneath: null,
    page: pageFor(opts.page, activePage(conversation)),
  })
}

/* Details */
export function openDetail(d: Detail, opts?: { read?: ReadWith; page?: string }): void {
  const cur = stepOf(state)
  if (d.kind === 'replies' || d.kind === 'post-details') {
    /* Conversation material is read from its post: opening it reads that post,
       or -- `read` -- the post named, in the conversation named, in the same step. */
    const id = d.kind === 'replies' ? d.root : d.id
    const n = store.posts.get(id)?.number ?? (cur.reading === id ? cur.readingNumber : null)
    const conversation = opts?.read?.conversation ?? cur.conversation
    /* a thread hosted in a window: the post is read, and no sheet opens */
    const windowed = d.kind === 'replies' && hosted(d.root, conversation, 'open')
    const page = pageFor(opts?.page, activePage(conversation))
    const reading = opts?.read ? opts.read.post : id
    if (external && !replaying) {
      intendRead(conversation, reading, page, windowed ? undefined : d)
      if (conversation !== cur.conversation) return
    }
    move({
      ...cur,
      conversation,
      reading,
      readingNumber: opts?.read ? num(opts.read.number) : n,
      detail: windowed ? null : d,
      beneath: null,
      page,
    })
  } else if (d.kind === 'about') {
    /* About the conversation, not a post: nothing new is read. */
    move({ ...cur, detail: d, beneath: null })
  } else if (d.kind === 'full') {
    /* Full screen, over everything: the sheet beside the conversation and
       the page shown stay as they are beneath it. */
    const beneath = cur.detail && !isOver(cur.detail) ? cur.detail : cur.beneath
    move({ ...cur, detail: d, beneath })
  } else {
    /* An object opens over the workspace; a sheet open beside the conversation
       stays, beneath it. THE PAGE IS NOT FORCED BACK TO THIS POST where a
       validated one is supplied, or where Quiet's own Page is active (F7):
       opening an object on a Page used to leave the Page it was on. */
    const beneath = cur.detail && cur.detail.kind !== 'object' ? cur.detail : cur.beneath
    move({ ...cur, page: pageFor(opts?.page, external ? cur.page : THIS_POST), detail: d, beneath })
  }
}

/** A reply read where its thread is not open -- reached before the posts it
 *  answers were known -- is shown inside the thread of `root`, completing the
 *  step that read it rather than adding one Back would have to retrace. */
export function showInThread(root: string): void {
  const cur = stepOf(state)
  if (!cur.reading || cur.detail) return
  if (hosted(root, cur.conversation, 'open')) return
  apply({ ...cur, detail: { kind: 'replies', root, anchor: { kind: 'post', id: root }, mode: 'aside' }, beneath: null })
}

/** Esc / the detail's own "<" label: unwind the whole temporary view at once
 *  -- an object open over a sheet unwinds to that sheet, the sheet to its post. */
export function closeDetail(): void {
  const d = state.detail
  if (!d) return
  if (isOver(d) && state.beneath) {
    const under = state.beneath
    while (stack.length && isOver(stack[stack.length - 1].detail)) stack.pop()
    apply({ ...stepOf(state), detail: under, beneath: null })
  } else {
    while (stack.length && stack[stack.length - 1].detail) stack.pop()
    const next = { ...stepOf(state), detail: null, beneath: null }
    if (d.kind === 'replies') {
      next.reading = d.root
      next.readingNumber = store.posts.get(d.root)?.number ?? next.readingNumber
    }
    apply(next)
  }
  while (stack.length && same(stack[stack.length - 1], stepOf(state))) stack.pop()
  emit()
}

/** Close every temporary detail at once: a sheet's own ✕ while an object is open over it. */
export function closeAll(): void {
  while (state.detail) closeDetail()
}

/* History */
export function back(): void {
  const prev = stack.pop()
  if (!prev) return
  apply(prev)
}

/* Pages */
/** How long a page's own title may be before it is shortened. */
const shorten = (title: string) => (title.length > 22 ? title.slice(0, 20) + '…' : title)

export function openAsPage(object: string, title: string): void {
  /* One page per object: opened again, its tab is shown, not a twin of it. */
  const had = state.pages.find((p) => 'object' in p && p.object && p.object === object)
  if (had) { showPage(had.id); return }
  pageSeq += 1
  const id = `page-${pageSeq}`
  const short = shorten(title)
  state = { ...state, pages: [...state.pages, { id, title: short, object }] }
  move({ ...stepOf(state), detail: null, page: id })
  intendPage(id)
  toast({
    text: `"${short}" is now a page. This post kept its arrangement.`,
    action: { label: 'Undo', run: () => closePage(id) },
  })
}

/** A GOVERNED ITEM OPENED BESIDE ITS CONVERSATION (Fluid Governance): a page
 *  beside This post, as Open as page makes one, under the item's own title
 *  and without the arrangement toast -- opening an item changes no
 *  arrangement. One page per item: opened again, its tab is shown. */
export function openItemPage(object: string, title: string): void {
  const had = state.pages.find((p) => 'object' in p && p.object === object)
  if (had) { showPage(had.id); return }
  pageSeq += 1
  const id = `page-${pageSeq}`
  state = { ...state, pages: [...state.pages, { id, title, object }] }
  move({ ...stepOf(state), detail: null, page: id })
  intendPage(id)
}

/** A reload brings back the pages and the width the reader had: no step,
 *  no toast; This post stays the page shown (F6 final fix round). */
export function restore(pages: { title: string; object: string }[], width: ConversationWidth | null): void {
  const known = new Set(state.pages.map((p) => ('object' in p ? p.object : '')))
  const add = pages.filter((p) => !known.has(p.object)).map((p) => ({ id: `page-${(pageSeq += 1)}`, title: p.title, object: p.object }))
  state = { ...state, pages: [...state.pages, ...add] }
  if (width) setConvPx(PRESET[width])
  emit()
}

export function showPage(id: string): void {
  /* AN ABSENT PAGE CANNOT BE SELECTED: a stale address, another browser's
     arrangement or a closed Page asks for nothing rather than for a blank. */
  if (!state.pages.some((p) => p.id === id)) return
  move({ ...stepOf(state), page: id, detail: null })
  intendPage(id)
}

export function closePage(id: string): void {
  if (id === THIS_POST || !state.pages.some((p) => p.id === id)) return
  const shown = state.page === id
  state = { ...state, pages: state.pages.filter((p) => p.id !== id) }
  stack = stack.filter((s) => s.page !== id)
  if (shown) apply({ ...stepOf(state), page: THIS_POST, detail: null })
  else emit()
  /* Closing the Page being read is a destination change -- back to the
     conversation -- and the hash has to say so. */
  if (shown) intendPage(THIS_POST)
}

/* Conversation width: a caller asking for room (tracing "from #N" out of the
   rail, say) gets that width; the reader drags it anywhere between. */
export function setWidth(w: ConversationWidth): void {
  if (state.width === w) return
  setConvPx(PRESET[w])
}

/** A width the column may have: the rail, or READABLE and wider. One saved
 *  or asked for between them (a place kept before this rule, at 280) is
 *  READABLE; under RAIL_BELOW it was the rail, and stays it. */
const allowed = (px: number) => (px < RAIL_BELOW ? CONV_MIN : Math.round(Math.max(READABLE, px)))
const opened = (v: number) => (railPx(v) ? state.openPx : v)

export function setConvPx(px: number): void {
  const v = allowed(px)
  if (v === state.convPx) return
  state = { ...state, convPx: v, width: classOf(v), openPx: opened(v) }
  emit()
}

/** The reader sizing the conversation (its boundary): the width is theirs,
 *  under whatever object is open beside it (`drawnConvPx`). `under` given
 *  puts back what it was (a cancelled drag); `open` is the readable width
 *  the rail opens to again, when it is not this one. */
export function sizeConvPx(px: number, under: Detail | null | undefined = state.detail, open?: number): void {
  const v = allowed(px)
  const o = open != null && !railPx(open) ? open : opened(v)
  if (v === state.convPx && under === state.sizedUnder && o === state.openPx) return
  state = { ...state, convPx: v, width: classOf(v), sizedUnder: under, openPx: o }
  emit()
}

/** OPENING THE RAIL (its boundary clicked or dragged out, its pencil, a
 *  trace out of it, the keyboard): the last readable width, never a sliver. */
export function openRail(): void {
  if (!railPx(state.convPx)) return
  sizeConvPx(state.openPx ?? PRESET.wide)
}

/** The room the stage leaves the conversation (Shell.tsx measures it). */
export function setConvRoom(px: number | null): void {
  const v = px == null ? null : Math.round(px)
  if (v === (state.convRoom ?? null)) return
  state = { ...state, convRoom: v }
  emit()
}

export function setThreadPx(px: number): void {
  const v = Math.round(Math.max(THREAD_MIN, px))
  if (v === state.threadPx) return
  state = { ...state, threadPx: v }
  emit()
}

/* -- the owner's pages (Fluid completion, stream A) ------------------------- */

/** "+": a blank page of the owner's own, shown; Undo takes it away. */
export function newPage(): string {
  const used = new Set(state.pages.map((p) => ('title' in p ? p.title : '')))
  let n = 2
  while (used.has(`Page ${n}`)) n++
  pageSeq += 1
  const id = `page-${pageSeq}`
  state = { ...state, pages: [...state.pages, { id, title: `Page ${n}` }] }
  move({ ...stepOf(state), detail: null, page: id })
  intendPage(id)
  toast({ text: `Page ${n} is yours: keep things on it, or drag them onto it.`, action: { label: 'Undo', run: () => closePage(id) } })
  return id
}

/** WHAT A PAGE WAS MADE FOR (round 5, F14). Omitted, a page is the
 *  arrangement change it has always been, under its own title and with its
 *  own toast. `'deep-dive'`: the page a Deep dive was opened as, which is a
 *  new conversation rather than a rearrangement, so it says so. */
export interface AddPageOptions { kind?: 'deep-dive' }

const DIVE = 'Deep dive: '

/** THE PREFIX EXACTLY ONCE, AND KEPT WHEN THE NAME IS SHORTENED. A returned
 *  name that already says "Deep dive:" is not told twice, and shortening
 *  takes characters off the NAME -- a label that loses its own prefix to a
 *  long name says nothing about what it is. */
export function deepDiveTitle(name: string): string {
  const bare = name.trim().replace(/^deep\s*dive\s*:\s*/i, '')
  return DIVE + shorten(bare)
}

/** A page made with what it holds already chosen (Keep on a new page, a
 *  suggested page, a Deep dive): shown, with Undo. */
export function addPage(title: string, opts: AddPageOptions = {}): string {
  pageSeq += 1
  const id = `page-${pageSeq}`
  const dive = opts.kind === 'deep-dive'
  const label = dive ? deepDiveTitle(title) : shorten(title)
  state = { ...state, pages: [...state.pages, { id, title: label }] }
  move({ ...stepOf(state), detail: null, page: id })
  intendPage(id)
  toast({
    text: dive ? 'Deep dive opened as a page.' : `"${label}" is now a page. This post kept its arrangement.`,
    action: { label: 'Undo', run: () => closePage(id) },
  })
  return id
}

/** A place's own pages, as it left them (entering a conversation, a layout
 *  applied): no step, no toast. The page shown stays if the place has it. */
export function setPages(pages: { id: string; title: string; object?: string }[]): void {
  for (const p of pages) {
    const m = /^page-(\d+)$/.exec(p.id)
    if (m) pageSeq = Math.max(pageSeq, Number(m[1]))
  }
  const next: Page[] = [{ id: THIS_POST }, ...pages.filter((p) => p.id !== THIS_POST).map((p) => ({ ...p }))]
  const page = next.some((p) => p.id === state.page) ? state.page : THIS_POST
  state = { ...state, pages: next, page }
  emit()
}

/* Toasts */
export function toast(t: Toast): void {
  showToast(t)
}

/* Anchor flash on return: components subscribe and flash when their anchor is named */
export function onReturnTo(listener: (a: Anchor) => void): () => void {
  returning.add(listener)
  return () => { returning.delete(listener) }
}

/* Subscription for React (useSyncExternalStore) */
export function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => { listeners.delete(listener) }
}

export function snapshot(): NavState {
  return state
}
