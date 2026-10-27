/* A POST CARD (spec section 4): avatar, @author, time, #N; its words; chips
 * for what it carries ("checklist · chart → This post"), its replies
 * ("7 replies ›") and, on hover, Details and the post's other actions.
 *
 * Reading is a click: the card becomes the read post (accent bar). The post
 * whose replies or details are open is the ANCHOR (ring and notch), and it
 * pulses when the reader returns to it. Each card subscribes to its own post.
 *
 * This is the card's PLACE in a column: what the post is drawn as -- its
 * identity line, words, chips and annotations -- is the shared renderer's
 * (render/post.tsx), the same in the thread, on Home and full screen. */

import { useEffect, useRef, useState } from 'react'
import { useHeat } from '../../surfaces/recency'
import * as nav from '../nav'
import { repliesOf, store, type Id, type Placement } from '../store'
import { useNav, usePost } from './hooks'
import Carries from './Carries'
import { useWorkingUnder } from './presence'
import { bare, said } from './text'
import { activate, isPinned, pinsOf, useThreads } from './threads'
import { useWorkingOn } from './working'
import { POST } from '../workspace/keep'
import { onStageClass, useOnStage } from '../workspace/origin'
import { PostView, WorkStatusPill, useActions } from '../render/post'

/* The renderer's pieces, where the places that drew posts have found them. */
export {
  Actions, LATER, MoreChips, PinTag, When, Where, Words, WorkOn, WorkStatusPill, WorkStatusProvider, moreSheet, useActions,
  type PostActions,
} from '../render/post'

/** Which thread the panel beside the conversation shows: the slid-out one,
 *  else the active pinned one (completion stream B). */
export function shownThread(here: Id | null, s: nav.NavState): Id | null {
  const sheet = nav.sheetOf(s)
  if (sheet?.kind === 'replies') return sheet.root
  if (sheet) return null
  return pinsOf(here).active
}

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
      <PostView post={post} context="post" here={a.here} card={ref} selecting={a.selectMode} onStage={onStage}
        head={{
          draggable: !a.selectMode,
          onPointerEnter: () => { if (!store.postObjects.has(id)) void store.loadObjects(id).catch(() => {}) },
          onDragStart: (e) => {
            e.dataTransfer.setData(POST, JSON.stringify({ post: id }))
            e.dataTransfer.setData('text/plain', `${post.home_name ? post.home_name + ' ' : ''}${num}`)
            e.dataTransfer.effectAllowed = 'copyMove'
          },
        }}
        check={a.selectMode ? { checked: selected, toggle: () => a.toggleSelect(id), label: `Select post ${post.number != null ? '#' + post.number : id}` } : null}
        /* Who is working on it, or in its thread, is said once, in its
           footer (WorkStatusPill), not in its head as well. */
        meta={included && <span className="fw-meta">included here</span>}
        lead={replyOutside && (
          <p className="fw-replying">
            Replying to {post.reply_to_home === a.here ? '' : `${post.reply_to_home_name ?? 'another conversation'} · `}
            {post.reply_to_number != null ? `#${post.reply_to_number}` : 'a post'}
          </p>
        )}
        chips={{
          place, headAway,
          before: <>
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
          </>,
          status: <WorkStatusPill post={post} workers={workers} under={under} />,
        }} />
    </article>
  )
}
