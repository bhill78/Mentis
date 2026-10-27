/* A POST CARD (spec section 4): avatar, @author, time, #N; its words; chips
 * for what it carries ("checklist · chart → This post"), its replies
 * ("7 replies ›") and, on hover, Details and the post's other actions.
 *
 * Reading is a click: the card becomes the read post (accent bar). The post
 * whose replies or details are open is the ANCHOR (ring and notch), and it
 * pulses when the reader returns to it. Each card subscribes to its own post. */

import { createContext, useContext, useEffect, useRef, useState } from 'react'
import { ago } from '../../api'
import { Prose } from '../../prose'
import { useHeat } from '../../surfaces/recency'
import { turnPartScope } from '../../experimental/renderable'
import { namesFor } from '../../experimental/objects'
import * as nav from '../nav'
import { repliesOf, store, type Id, type Placement, type Post } from '../store'
import { exportTurn } from '../../api'
import { useAfterReads, useNav, usePost } from './hooks'
import { Who } from '../identity/Who'
import Carries from './Carries'
import { useWorkingUnder } from './presence'
import { closeSheet, openSheet, Sheet, useOpenSheet } from '../frame/Sheet'
import { AddressPop, Addressees, addressSheet } from './Addressing'
import { bare, inlinePart, said, textOf } from './text'
import { activate, isPinned, pinsOf, useThreads } from './threads'
import { aliasOf, useWorkingOn, type Working } from './working'
import { POST } from '../workspace/keep'
import { OnStageTag, onStageClass, useOnStage } from '../workspace/origin'
import Annotations, { Annotate } from './Annotations'
import PostDecisions from './Decisions'
import { formatPillText, useWorkByTurn } from '../../surfaces/WorkPill'
import type { WorkItem } from '../../work/contract'

/** Which thread the panel beside the conversation shows: the slid-out one,
 *  else the active pinned one (completion stream B). */
export function shownThread(here: Id | null, s: nav.NavState): Id | null {
  const sheet = nav.sheetOf(s)
  if (sheet?.kind === 'replies') return sheet.root
  if (sheet) return null
  return pinsOf(here).active
}

/** What a card can do besides being read, provided by the shell. */
export interface PostActions {
  /** the conversation shown, or null in the Stream */
  here: Id | null
  /** what `nav.read` is told the post is read in: the conversation, or 'stream' */
  readIn: Id
  selectMode: boolean
  selected: Set<Id>
  toggleSelect: (id: Id) => void
  startSelect: (id: Id) => void
  reply?: (id: Id) => void
  goHome: (conversation: Id, post: Id) => void
  include?: (id: Id) => void
  remove?: (id: Id) => void
  busy: boolean
}
export const Actions = createContext<PostActions | null>(null)
export const useActions = () => useContext(Actions)!

/** The card's flash when the reader comes back to it, as `.pulse`. */
export function usePulse(id: Id): boolean {
  const [on, setOn] = useState(0)
  useEffect(() => nav.onReturnTo((a) => { if (a.kind === 'post' && a.id === id) setOn((n) => n + 1) }), [id])
  useEffect(() => {
    if (!on) return
    const t = setTimeout(() => setOn(0), 1100)
    return () => clearTimeout(t)
  }, [on])
  return on > 0
}

/** Where a post lives: its number, and its home's name when that is elsewhere. */
export function Where({ post, here }: { post: Post; here: Id | null }) {
  const a = useActions()
  const away = post.home !== here
  const convName = post.home_name || (post.home ? store.conversations.get(post.home)?.name : null)
  const content = (
    <>
      {away && convName ? <span className="fw-where-home">{convName} · </span> : ''}
      {post.number != null && <span className="fw-num">#{post.number}</span>}
    </>
  )
  if (!post.home) return <span className="fw-where fx-num">{content}</span>
  return (
    <a className="fw-where fx-num" href={a.selectMode ? undefined : `/fluid?c=${encodeURIComponent(post.home)}&t=${encodeURIComponent(post.id)}`}
      title={a.selectMode ? undefined : convName ? `Go to ${convName}` : 'Go to conversation'}
      onClick={(e) => {
        e.stopPropagation()
        if (a.selectMode) { e.preventDefault(); a.toggleSelect(post.id); return }
        if (!e.ctrlKey && !e.metaKey && !e.shiftKey) { e.preventDefault(); a.goHome(post.home!, post.id) }
      }}>
      {content}
    </a>
  )
}

/** When it was written, as a post says it: how long ago, the full time on
 *  hover. A reply says it the same way wherever it is drawn (A9). */
export function When({ at }: { at: number }) {
  const d = new Date(at * 1000)
  return <time className="fw-time fx-when" dateTime={d.toISOString()} title={d.toLocaleString()}>{ago(at)}</time>
}

/** The post's words: its Markdown without the blocks This post draws. A
 *  form stays in the words and is drawn and answered here, keyed by its own
 *  text part with that part's names, exactly as This post and Classic key
 *  it, so every copy is the same form with the same answers (P5a). */
export function Words({ post, size }: { post: Post; size?: 'reply' }) {
  if (post.deleted) return <p className="fw-deleted fx-text">Deleted{post.deleted.because ? `: ${post.deleted.because}` : ''}</p>
  const part = inlinePart(post)
  const { words } = said(post, part !== null)
  if (!words) return null
  const scope = turnPartScope(post.id, part ?? 0)
  return (
    /* `turn-body` is where the shared renderers' styles are scoped (app.css). */
    <div className={'fw-body turn-body fx-text' + (size === 'reply' ? ' fx-text-reply' : '')}>
      <Prose src={words} scope={scope} names={part !== null ? namesFor(post.parts[part].text ?? '', scope) : undefined} />
    </div>
  )
}

/* THE POST'S TOOLBAR (A6; production's TurnActions as the reference): a
 * compact bar of marks, shown on hover or keyboard focus, each saying its
 * words on hover and its whole name to a screen reader -- and on a touch
 * screen, which cannot hover, the words beside the marks. The everyday ones
 * are marks; what applies only sometimes (Include here, Remove from here,
 * Open in its home) appears only then; the rest is under More.
 *
 * Only what Fluid can already do is here. React, Comment and Deep dive are
 * drawn by Annotate, beside Address (Annotations.tsx); Edit, Delete and
 * Topic have their places kept (`LATER`), drawn by nothing until their
 * writes exist. Include here and Remove from here say what they will do,
 * and do it only when that is confirmed (#187 #4). */

/** Where the actions still to come go, in production's order, once Fluid
 *  can do them: Topic on the bar beside Address, Edit and Delete under More.
 *  None is drawn yet. */
export const LATER = { bar: ['topic'], more: ['edit', 'delete'] } as const

export const moreSheet = (post: Id) => 'post-more:' + post

/** Open a pop from a mark near the window's foot above it, not under the edge. */
function openPop(id: string, el: HTMLElement, tall = 260) {
  const r = el.getBoundingClientRect()
  const up = r.bottom + tall > window.innerHeight - 8 && r.top - tall > 8
  openSheet(id, up ? { getBoundingClientRect: () => ({ ...r.toJSON(), left: r.left, right: r.right, top: r.top - tall - 12, bottom: r.top - tall - 12 }) } as Element : el)
}

export function MoreChips({ post, place }: { post: Post; place?: Placement }) {
  const a = useActions()
  const [asking, setAsking] = useState<null | 'include' | 'remove'>(null)
  const sheetNow = useOpenSheet()
  if (a.selectMode) return null
  const included = place?.via === 'linked' || (post.memberships ?? []).some((m) => m.conversation === a.here && m.via === 'linked')
  const away = !a.here || post.home !== a.here
  const num = post.number != null ? `#${post.number}` : 'this post'
  const homeName = post.home_name || (post.home ? store.conversations.get(post.home)?.name : null) || 'its own conversation'
  const hereName = (a.here && store.conversations.get(a.here)?.name) || 'this conversation'
  if (asking) {
    return (
      <span className="fx-more fx-confirm" role="group" aria-label="confirm" onClick={(e) => e.stopPropagation()}>
        <span className="fx-consequence">
          {asking === 'include'
            ? <>Include {num} here? It stays in <b>{homeName}</b>; {hereName} shows it too. Nothing is moved or copied.</>
            : <>Remove {num} from {hereName}? It stays in <b>{homeName}</b>; only its inclusion here ends. Nothing is deleted.</>}
        </span>
        <button className="fx-chip go" disabled={a.busy} onClick={() => { setAsking(null); (asking === 'include' ? a.include : a.remove)?.(post.id) }}>
          {asking === 'include' ? 'Include here' : 'Remove from here'}
        </button>
        <button className="fx-chip more" onClick={() => setAsking(null)}>Cancel</button>
      </span>
    )
  }
  const details = () => nav.openDetail({ kind: 'post-details', id: post.id, anchor: { kind: 'post', id: post.id }, mode: 'aside' })
  const full = () => nav.openDetail({ kind: 'full', of: 'post', id: post.id, anchor: { kind: 'post', id: post.id }, mode: 'over' })
  const copy = async (what: 'text' | 'link') => {
    closeSheet()
    const link = post.home ? `${location.origin}/fluid?c=${encodeURIComponent(post.home)}&t=${encodeURIComponent(post.id)}` : ''
    try {
      await navigator.clipboard.writeText(what === 'link' ? link : [`@${bare(post.author_name)} · ${num}`, '', textOf(post).trim(), ''].join('\n'))
      nav.toast({ text: what === 'link' ? `A link to ${num} is copied.` : `${num} is copied.` })
    } catch (e) {
      /* A denied clipboard is the browser's answer, said, not swallowed. */
      nav.toast({ text: `Could not copy: ${(e as Error).message}` })
    }
  }
  const canAddress = !post.deleted && !!(a.here ?? post.home)
  /* One mark: its words on hover and to a screen reader, beside it on touch. */
  const mark = (cls: string, glyph: string, label: string, aria: string, title: string, run: (el: HTMLElement) => void, extra?: { act?: string; disabled?: boolean; pressed?: boolean }) => (
    <button className={'fx-chip more fx-act ' + cls} data-act={extra?.act} aria-label={aria} title={title} disabled={extra?.disabled}
      aria-expanded={extra?.pressed} onClick={(e) => { e.stopPropagation(); run(e.currentTarget) }}>
      <span className="fx-act-glyph" aria-hidden="true">{glyph}</span><span className="fx-act-label">{label}</span>
    </button>
  )
  const more = moreSheet(post.id), addr = addressSheet(post.id)
  return (
    <span className="fx-more fx-postbar" role="toolbar" aria-label={`${num}: actions`}>
      {a.reply && !post.deleted && mark('fw-reply-to', '↩', 'Reply', `Reply to ${num}`, "Reply in this post's thread, with the thread's own composer", () => a.reply!(post.id), { act: 'reply' })}
      {mark('fx-details', 'ⓘ', 'Details', `Details of ${num}`, 'Details: who wrote it, what was asked, the runs', details, { act: 'details' })}
      {canAddress && mark('fx-address', '@', 'Address', `Address ${num} to someone`, 'Address: ask someone to respond to this post', (el) => openPop(addr, el, 320), { act: 'address', pressed: sheetNow?.id === addr })}
      {/* react, comment, deep dive on the whole post, beside Address where
          production has them (Annotations.tsx) */}
      <Annotate post={post} />
      {mark('fx-fullchip', '⤢', 'Full', `${num} full screen`, 'Full screen', full, { act: 'full' })}
      {mark('fw-select-chip', '☐', 'Select', `Select ${num}`, 'Select posts to keep or include elsewhere', () => a.startSelect(post.id), { act: 'select' })}
      {away && post.home && (
        <a className="fx-chip more fx-act fw-card-open" href={`/fluid?c=${encodeURIComponent(post.home)}&t=${encodeURIComponent(post.id)}`}
          title={`Open in ${post.home_name ?? 'its conversation'}`} aria-label={`Open post in ${post.home_name || 'home conversation'}`} data-act="open-in"
          onClick={(e) => {
            e.stopPropagation()
            if (!e.ctrlKey && !e.metaKey && !e.shiftKey) { e.preventDefault(); a.goHome(post.home!, post.id) }
          }}>
          <span className="fx-act-glyph" aria-hidden="true">⇱</span><span className="fx-act-label">Open in {post.home_name ?? 'its conversation'}</span>
        </a>
      )}
      {included && a.remove && mark('fw-card-remove', '⊖', 'Remove from here…', `Remove ${num} from here…`, `Remove from here: end its inclusion here; it stays in ${homeName}`, () => setAsking('remove'), { act: 'remove', disabled: a.busy })}
      {!included && a.include && a.here && post.home && post.home !== a.here &&
        mark('fw-card-include', '⊕', 'Include here…', `Include ${num} here…`, `Include here: show it here too; it stays in ${homeName}`, () => setAsking('include'), { act: 'include', disabled: a.busy })}
      {mark('fx-more-menu', '⋯', 'More', `More for ${num}`, 'More: copy, a link, Classic', (el) => openPop(more, el, 200), { act: 'more', pressed: sheetNow?.id === more })}
      {sheetNow?.id === addr && <AddressPop post={post} here={a.here} />}
      {sheetNow?.id === more && (
        <Sheet id={more} label={`more for ${num}`} className="fx-post-more">
          <button className="fx-opt" data-act="copy" onClick={() => void copy('text')}>Copy <small>its words, with who and #</small></button>
          {post.home && <button className="fx-opt" data-act="copy-link" onClick={() => void copy('link')}>Copy link <small>to {num} in Fluid</small></button>}
          <button className="fx-opt" data-act="export" onClick={() => { closeSheet(); void exportTurn(post.id) }}>
            Export turn <small>download as a .zip archive</small>
          </button>
          {post.home && (
            <a className="fx-opt fx-classic" href={`/#/c/${encodeURIComponent(post.home)}/turn/${encodeURIComponent(post.id)}`} target="_blank" rel="noopener"
              title="Open in Classic: editing, and sending a comment on to someone, are there for now" aria-label={`Open ${num} in Classic`} onClick={() => closeSheet()}>
              Open in Classic ↗ <small>editing, sending a comment on</small>
            </a>
          )}
        </Sheet>
      )}
    </span>
  )
}

/* THE WORK A POST STARTED (item 11): Classic's work pills, kept. The
 * conversation's work is read once, by the pills' own reader
 * (`useWorkByTurn`), and each card looks itself up by the post the work
 * started from. Its words are the pills' (`formatPillText`): objective met
 * only when the record says so, and ended work keeps its "not marked
 * complete". Who is running now, by `/api/activity`, says it is working. */
const WorkByTurn = createContext<Map<Id, WorkItem> | null>(null)

export function WorkStatusProvider({ conversation, children }: { conversation: Id; children: React.ReactNode }) {
  /* Asked once the conversation's own posts are read (`useAfterReads`). */
  const { itemsByTurn } = useWorkByTurn(useAfterReads(conversation))
  return <WorkByTurn.Provider value={itemsByTurn}>{children}</WorkByTurn.Provider>
}

/** ONE STATUS PER POST, IN ITS FOOTER, left of its tools: the work it
 *  started, and who is working on it or in its thread now (#568 4.6; A3).
 *  Nothing when it started no work and nobody is working there. */
export function WorkStatusPill({ post, workers, under }: { post: Post; workers: Working[]; under: Working[] }) {
  const item = useContext(WorkByTurn)?.get(post.id)
  const live = [...workers, ...under.filter((u) => !workers.some((w) => w.participant === u.participant))]
  if (!item && !live.length) return null
  const words = item ? formatPillText(item) : null
  const met = item?.objective_met === true
  const state = met ? 'met' : live.length ? 'working' : words!.status === 'ended' ? 'ended' : words!.status === 'not started' ? 'not-started' : 'in-flight'
  const where = workers.length ? '' : ' in its thread'
  const who = live.length === 1 ? `${aliasOf(live[0])} working${where}` : `${live.length} working${where}`
  const title = [
    item && `Work: ${item.status_words}${item.title ? ` (${item.title})` : ''}`,
    live.length > 0 && `Working now: ${live.map((w) => `${aliasOf(w)} since ${new Date(w.working_on!.since * 1000).toLocaleTimeString()}`).join('; ')}`,
  ].filter(Boolean).join('\n')
  return (
    <span className={'fx-status-pill fx-status-' + state} role="status" data-work-state={state} title={title}>
      {state === 'working'
        ? live.slice(0, 2).map((w) => <Who key={w.participant} id={w.participant} name={w.alias} show="avatar" size={14} working />)
        : <span className="fx-status-glyph" aria-hidden="true">{met ? '✓' : state === 'ended' ? '◌' : state === 'not-started' ? '○' : '◐'}</span>}
      <span className="fx-status-words">
        {state === 'working' ? who : words!.status}
        {words?.decisions && <> · <span className="fx-status-owed">{words.decisions}</span></>}
        {state !== 'working' && words?.extra && <> · {words.extra}</>}
      </span>
    </span>
  )
}

/** WHO IS WORKING ON THIS POST, OR IN ITS THREAD (#568 4.6; A3): their
 *  faces with the live ring, and the words -- on the post itself, or on a
 *  reply under it ("in its thread") -- since when. Nothing when nobody is.
 *  Drawn in the thread's sheet; a post card says it in its footer. */
export function WorkOn({ num, on, under }: { num: string; on: Working[]; under: Working[] }) {
  const all = [...on, ...under.filter((u) => !on.some((o) => o.participant === u.participant))]
  if (!all.length) return null
  const one = all[0]
  const where = on.length ? '' : ' in its thread'
  const since = (w: Working) => `${aliasOf(w)} ${on.includes(w) ? `on ${num}` : `on ${w.working_on?.number != null ? `#${w.working_on.number}, a reply` : 'a reply'} in the thread of ${num}`}, since ${new Date(w.working_on!.since * 1000).toLocaleTimeString()}`
  return (
    <span className={'fx-work' + (on.length ? '' : ' fx-work-under')} role="status" title={`Working now: ${all.map(since).join('; ')}`}>
      {all.slice(0, 2).map((w) => <Who key={w.participant} id={w.participant} name={w.alias} show="avatar" size={16} working />)}
      <span className="fx-work-words">{all.length === 1 ? `${aliasOf(one)} working${where}` : `${all.length} working${where}`}</span>
    </span>
  )
}

/** A TALL POST OR REPLY (item 15): one taller than the column it scrolls in
 *  keeps its row of chips at the column's foot (`fx-tall`, conversation.css).
 *  `headAway` says its head -- who and # -- has scrolled up out of the
 *  column, so the row says which post it is (PinTag). Used for the
 *  conversation's posts and, in the thread beside it, the root and replies;
 *  `ready` once the card is drawn with its post, not as a placeholder. */
export function useTall(ref: React.RefObject<HTMLElement | null>, boxOf: (el: HTMLElement) => Element | null, ready = true) {
  const [tall, setTall] = useState(false)
  const [headAway, setHeadAway] = useState(false)
  const boxRef = useRef(boxOf)
  boxRef.current = boxOf
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const box = boxRef.current(el)
    const check = () => {
      if (!box) return
      const isTall = el.offsetHeight > box.clientHeight * 0.8
      setTall((prev) => (prev !== isTall ? isTall : prev))
    }
    check()
    const ro = new ResizeObserver(check)
    ro.observe(el)
    if (box) ro.observe(box)
    return () => ro.disconnect()
  }, [ref, ready])
  useEffect(() => {
    const el = ref.current
    const head = el?.querySelector(':scope > .fx-head')
    const box = el && boxRef.current(el)
    if (!tall || !head || !box) { setHeadAway(false); return }
    /* Measured on each scroll, not observed crossing the box's edge: a jump
       (a link, Back) can take the head from below the box to above it
       without ever crossing into view. */
    let frame = 0
    const check = () => {
      frame = 0
      const away = head.getBoundingClientRect().bottom <= box.getBoundingClientRect().top
      setHeadAway((prev) => (prev !== away ? away : prev))
    }
    const onScroll = () => { if (!frame) frame = requestAnimationFrame(check) }
    check()
    box.addEventListener('scroll', onScroll, { passive: true })
    return () => { box.removeEventListener('scroll', onScroll); cancelAnimationFrame(frame) }
  }, [ref, tall, ready])
  return { tall, headAway }
}

/** The nearest box that scrolls a card: the thread's body, for a reply. */
export function scrollBoxOf(el: HTMLElement): Element | null {
  let box = el.parentElement
  while (box && !/(auto|scroll)/.test(getComputedStyle(box).overflowY)) box = box.parentElement
  return box
}

/** WHICH POST THIS IS, in a tall post's row once its head has scrolled out
 *  of view: "#N · name", shortened with "…" where the row has no room. */
export function PinTag({ post }: { post: Post }) {
  const what = `${post.number != null ? `#${post.number}` : 'This post'} · ${bare(post.author_name)}`
  return <span className="fx-pin-tag" title={what} aria-hidden="true">{what}</span>
}

/** The post read by a click (or Enter) on its own card: already where the
 *  reader is looking, so it is not brought into view. */
let readHere: Id | null = null

export default function PostCard({ id, place, scroller }: {
  id: Id
  place?: Placement
  /** the scrolling column, so a post read from elsewhere is brought into view */
  scroller?: React.RefObject<HTMLDivElement | null>
}) {
  const post = usePost(id)
  const a = useActions()
  const s = useNav()
  const ref = useRef<HTMLElement | null>(null)
  const pulse = usePulse(id)
  const reading = s.reading === id
  const workers = useWorkingOn(id)
  const under = useWorkingUnder(id)
  const onStage = useOnStage(id)
  const heat = useHeat(post?.at)
  const { tall, headAway } = useTall(ref, (el) => scroller?.current ?? el.closest('.fx-scroll') ?? el.parentElement, !!post)
  /* The sheet open beside the conversation, even beneath an object detail;
     or, with none, the pinned thread the panel shows. */
  useThreads()
  const d = nav.sheetOf(s)
  const shown = shownThread(a.here, s)
  const anchor = (!!d && d.anchor.kind === 'post' && d.anchor.id === id) || (!d && shown === id)

  /* A post read from somewhere else -- Back, a link, a trace -- is brought
     into view; so is the post whose replies a trace opened. It lands with
     its header in view (opr-835dfb8981a8 item 4): one taller than the column
     is put at its top, not centred deep inside its words, and one read from
     elsewhere whose header is out of view is brought in though some of it
     shows. A post read here, by its own card, is never moved. */
  useEffect(() => {
    const el = ref.current, box = scroller?.current
    if (!(reading || anchor) || !el || !box) return
    const here = readHere === id
    if (reading) readHere = null
    const r = el.getBoundingClientRect(), b = box.getBoundingClientRect()
    const tall = r.height > b.height * 0.8
    const head = el.querySelector('.fx-head')?.getBoundingClientRect() ?? r
    const away = r.bottom < b.top + 8 || r.top > b.bottom - 8
    const headAway = reading && !here && (head.top < b.top - 1 || head.bottom > b.bottom + 1)
    if (away || headAway) el.scrollIntoView({ block: tall ? 'start' : 'center' })
  }, [reading, anchor, scroller, id])

  if (!post) return <article className="fw-card fx-post fw-pending" aria-busy="true" />
  /* What This post will show for it: its objects and its whole thread's, as
     the server lists them (F6); its own words' blocks until that is read. */
  const kinds = post.thread?.extracted ? post.thread.kinds : said(post).kinds
  const selected = a.selected.has(id)
  const included = place?.via === 'linked' || (post.memberships ?? []).some((m) => m.conversation === a.here && m.via === 'linked')
  const replyOutside = post.reply_to && place && place.reply_to && post.reply_to_home
  const n = repliesOf(post)
  const elsewhere = Object.entries(post.thread?.by_home ?? post.replies.by_home).filter(([h]) => h !== a.here)
  const repliesOpen = shown === id
  const pinnedHere = !!a.here && isPinned(a.here, id)
  const num = post.number != null ? `#${post.number}` : 'this post'
  const readIt = () => {
    if (a.selectMode) a.toggleSelect(id)
    else { readHere = id; nav.read(a.readIn, id, post.number) }
  }

  return (
    <article ref={ref}
      className={'fw-card fx-post' + (reading ? ' reading fw-picked' : '') + (anchor ? ' anchor' : '') + (pulse ? ' pulse' : '')
        + (included ? ' fw-included' : '') + (repliesOpen ? ' fw-open' : '') + (a.selectMode ? ' fw-selectable' : '') + (selected ? ' fw-selected' : '') + (tall ? ' fx-tall' : '') + onStageClass(onStage)}
      data-post={id} data-number={post.number ?? undefined} data-heat={heat || undefined}
      aria-selected={a.selectMode ? selected : undefined}
      /* Reachable by keyboard: Tab to the card, Enter (or Space) reads it, and
         its hover chips show while focus is inside it (conversation.css). */
      tabIndex={0}
      aria-label={`${num} by @${bare(post.author_name)}${reading ? ', reading' : ''}`}
      aria-current={reading ? 'true' : undefined}
      onKeyDown={(e) => {
        if ((e.key === 'Enter' || e.key === ' ') && e.target === e.currentTarget) { e.preventDefault(); readIt() }
      }}
      onClick={readIt}
      onDoubleClick={(e) => {
        if (!a.selectMode && post.home && post.home !== a.here) { e.stopPropagation(); a.goHome(post.home, post.id) }
      }}>
      {/* A POST IS DRAGGED BY ITS HEAD (D1, #599: drag and drop "as in a
          conversation", in the compact view too): onto a zone it is kept
          there, its words and what it carries; its words stay selectable. */}
      <header className="fw-head fx-head" draggable={!a.selectMode}
        onPointerEnter={() => { if (!store.postObjects.has(id)) void store.loadObjects(id).catch(() => {}) }}
        onDragStart={(e) => {
          e.dataTransfer.setData(POST, JSON.stringify({ post: id }))
          e.dataTransfer.setData('text/plain', `${post.home_name ? post.home_name + ' ' : ''}${num}`)
          e.dataTransfer.effectAllowed = 'copyMove'
        }}>
        {a.selectMode && (
          <input type="checkbox" className="fw-card-checkbox" checked={selected}
            onChange={() => a.toggleSelect(id)} onClick={(e) => e.stopPropagation()}
            aria-label={`Select post ${post.number != null ? '#' + post.number : id}`} />
        )}
        <Who id={post.author} name={post.author_name} show="line" size={24} className="fx-who fw-author" />
        {/* the time and what is said beside it: in a narrow column, the line
            under the face, the name and the number (conversation.css) */}
        <span className="fx-stamp">
          <When at={post.at} />
          {post.edited_at && <span className="fw-meta">edited</span>}
          {included && <span className="fw-meta">included here</span>}
          {/* Who is working on it, or in its thread, is said once, in its
              footer (WorkStatusPill), not here as well. */}
        </span>
        <Where post={post} here={a.here} />
      </header>
      {replyOutside && (
        <p className="fw-replying">
          Replying to {post.reply_to_home === a.here ? '' : `${post.reply_to_home_name ?? 'another conversation'} · `}
          {post.reply_to_number != null ? `#${post.reply_to_number}` : 'a post'}
        </p>
      )}
      <Addressees post={post} />
      <Words post={post} />
      <PostDecisions post={post} />
      <div className="fx-chips">
        <Carries post={post} kinds={kinds} readIn={a.readIn} selecting={a.selectMode}
          onRead={() => { readHere = id; nav.read(a.readIn, id, post.number) }} />
        {n > 0 && (
          <button className={'fx-chip go fw-replies' + (repliesOpen ? ' on' : '')} data-act="replies" aria-expanded={repliesOpen}
            aria-label={`${n} ${n === 1 ? 'reply' : 'replies'} to ${num}${repliesOpen ? ': close' : ''}`}
            onClick={(e) => {
              e.stopPropagation()
              /* A pinned thread is shown, not opened again; a slid-out one closes. */
              if (pinnedHere) { if (d) nav.closeAll(); activate(a.here!, id) }
              else if (repliesOpen) nav.closeAll()
              else nav.openDetail({ kind: 'replies', root: id, anchor: { kind: 'post', id }, mode: 'aside' })
            }}>
            {pinnedHere ? '📌 ' : ''}{n} {n === 1 ? 'reply' : 'replies'} ›
            {elsewhere.length > 0 && (
              <span className="fw-elsewhere">
                {elsewhere.map(([h, k]) => ` · ${k} in ${store.conversations.get(h)?.name ?? 'another conversation'}`).join('')}
              </span>
            )}
          </button>
        )}
        {headAway && <PinTag post={post} />}
        <WorkStatusPill post={post} workers={workers} under={under} />
        <MoreChips post={post} place={place} />
      </div>
      <OnStageTag n={onStage} />
      {/* ANNOTATIONS (Annotations.tsx): marks in the card's right gutter,
          the passages' wash, and the bar beside a selection in its words */}
      {!a.selectMode && <Annotations post={post} card={ref} />}
    </article>
  )
}
