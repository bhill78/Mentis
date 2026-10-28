/* THE CONVERSATION COLUMN (spec section 4): one continuous width, dragged at
 * its boundary (workspace/Boundary.tsx) from the rail to wide, holding the
 * posts and the composer. Narrower, posts clamp; in rail it is avatars and
 * numbers, the conversation's name written up its side, and a pencil.
 *
 * The same column carries the Stream (every post, newest first) when the
 * shell is in the Stream, and the selection bar while posts are selected. */

import { useCallback, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import * as nav from '../nav'
import { closeSheet, openSheet, Sheet, sheetOpen, useOpenSheet } from '../frame/Sheet'
import { store, topicKey, type Collection, type Conversation, type Id } from '../store'
import { exportConversation, exportTurn } from '../../api'
import Composer from '../Composer'
import { Who } from '../identity/Who'
import { SectionSpin, useSectionLoad } from '../../loading'
import { useFacts } from './facts'
import { useCollection, useConversationObjects, useList, useNav } from './hooks'
import PostCard, { WorkStatusProvider } from './PostCard'
import { drawnBy, filterOf, focused, inThread, pinsOf, setFilter, setFocused, setTopic, topicOf, useThreads } from './threads'
import { useWorking } from './working'
import WorkingLine from '../runs/WorkingLine'
import { agentWhy, setShowsAgentWork, showsAgentWork, useAgentWork, useAgentWorkIn } from './agentWork'
import TimeSpent from '../../experimental/TimeSpent'
import { SearchButton, useFocusSearch } from '../search-in/FocusSearch'
import { CONVERSATION_ID } from '../focus/types'
import { anyIn, type Matcher } from '../search-in/match'
import { act } from '../objects/actions'

export const WIDTHS = { wide: 440, narrow: 280, rail: 64 } as const

export function SelectionBar({ selected, busy, here, onKeep, onInclude, onRemove, onCancel, onExport, picking, onCancelPick, onConfirmInclude }: {
  selected: Set<Id>
  busy: boolean
  here: Id | null
  onKeep: () => void
  onInclude: () => void
  onRemove?: () => void
  onCancel: () => void
  onExport?: () => void
  picking: boolean
  onCancelPick: () => void
  onConfirmInclude: (target: Id) => void
}) {
  const list = useList()
  /* EACH ACTION SAYS WHAT IT WILL DO BEFORE IT DOES IT (#187 #4): the first
     press states the consequence, the second acts. */
  const [asking, setAsking] = useState<null | 'keep' | 'remove' | 'export' | { include: Id }>(null)
  const n = selected.size
  /* ONE WAY OUT (#568 2.1): ✕ or Esc, "Cancel selection", clears what is
     selected and leaves selecting -- nothing stays selected out of sight.
     Esc unwinds the nearest thing first: a consequence being asked, then the
     destination list, then the selection; an open sheet and anything typed
     into keep their own Esc. */
  const esc = useRef({ asking, picking, onCancel, onCancelPick })
  esc.current = { asking, picking, onCancel, onCancelPick }
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape' || sheetOpen()) return
      const el = e.target as HTMLElement | null
      if (el?.matches?.('input, textarea, select') || el?.isContentEditable || el?.closest?.('.fx-pop, .fx-float, [role="dialog"]:not(.fx-pickpanel)')) return
      e.preventDefault()
      e.stopPropagation()
      const x = esc.current
      if (x.asking) setAsking(null)
      else if (x.picking) x.onCancelPick()
      else x.onCancel()
    }
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  }, [])
  /* WHAT IS SELECTED, AT THE POINT OF ACTION (#568 2.2): the count and the
     posts' numbers lead the bar, and the actions follow them as what is done
     to these posts -- no explanation at rest. A number brings its post into
     view. */
  const nums = [...selected].map((id) => store.posts.get(id)).filter((p) => p?.number != null)
    .sort((a, b) => a!.number! - b!.number!).map((p) => ({ id: p!.id, n: p!.number! }))
  const posts = n === 1 ? 'this post' : `these ${n} posts`
  const they = n === 1 ? 'It stays' : 'They stay'
  const hereName = (here && store.conversations.get(here)?.name) || 'this conversation'
  useEffect(() => { if (!n) setAsking(null) }, [n])
  const consequence = asking === 'keep'
    ? <>Opens a new, unnamed conversation that includes {posts}. {they} where {n === 1 ? 'it lives' : 'they live'}; nothing is moved or copied. You can name it with Save.</>
    : asking === 'remove'
      ? <>Ends the inclusion of {posts} in {hereName}. {n === 1 ? 'It' : 'Each'} stays in the conversation it lives in; nothing is deleted. A post that lives here cannot be removed, and says so.</>
      : asking === 'export'
        ? <>Exports {posts} as {n === 1 ? 'a .zip archive' : `${n} .zip archives`}. Nothing is moved or changed.</>
        : asking && typeof asking === 'object'
        ? <>Includes {posts} in <b>{list?.find((c) => c.id === asking.include)?.name ?? 'that conversation'}</b>. {they} where {n === 1 ? 'it lives' : 'they live'} and {n === 1 ? 'shows' : 'show'} there too; nothing is moved or copied.</>
        : null
  return (
    <>
      <div className="fw-selection-bar fx-selbar" role="toolbar" aria-label={`${n} selected`}>
        <button className="fw-action-cancel fx-sel-x" disabled={busy} onClick={onCancel} aria-label="Cancel selection"
          title="Cancel selection (Esc): nothing stays selected">✕</button>
        <span className="fx-sel-what">
          <span className="fw-selection-count">{n === 0 ? 'Select posts' : `${n} selected`}</span>
          {nums.slice(0, 4).map((p) => (
            <button key={p.id} className="fx-sel-num" title={`Show #${p.n}`}
              onClick={() => document.querySelector(`.fx-post[data-post="${CSS.escape(p.id)}"]`)?.scrollIntoView({ block: 'center', behavior: 'smooth' })}>#{p.n}</button>
          ))}
          {nums.length > 4 && <span className="fx-sel-more">+{nums.length - 4}</span>}
        </span>
        <span className="fx-sel-acts" role="group" aria-label={`what to do with ${n === 1 ? 'this post' : `these ${n} posts`}`}>
        <button className="fw-action-btn fw-keep-conv" disabled={busy || n === 0} aria-pressed={asking === 'keep'} title="Make a new conversation that includes these posts"
          onClick={() => setAsking('keep')}>Keep as conversation…</button>
        <button className="fw-action-btn fw-include-btn" disabled={busy || n === 0} title="Show these posts in another conversation too" onClick={() => { setAsking(null); onInclude() }}>Include in…</button>
        <button className="fw-action-btn fw-export-btn" disabled={busy || n === 0} aria-pressed={asking === 'export'} title="Export selected posts as .zip archive"
          onClick={() => setAsking('export')}>Export…</button>
        {onRemove && <button className="fw-action-btn fw-remove-btn" disabled={busy || n === 0} aria-pressed={asking === 'remove'} title="End these posts' inclusion here"
          onClick={() => setAsking('remove')}>Remove from here…</button>}
        </span>
        {consequence && (
          <div className="fx-consequence-row" role="alertdialog" aria-label="what this will do">
            <p className="fx-consequence">{consequence}</p>
            <button className="fw-action-btn fx-do" disabled={busy} onClick={() => {
              const was = asking
              setAsking(null)
              if (was === 'keep') onKeep()
              else if (was === 'remove') onRemove?.()
              else if (was === 'export') {
                if (onExport) onExport()
                else {
                  for (const id of selected) void exportTurn(id)
                  onCancel()
                }
              }
              else if (was && typeof was === 'object') onConfirmInclude(was.include)
            }}>{asking === 'keep' ? 'Keep as conversation' : asking === 'remove' ? 'Remove from here' : asking === 'export' ? 'Export' : 'Include there'}</button>
            <button className="fw-action-cancel fx-dont" onClick={() => setAsking(null)}>Cancel</button>
          </div>
        )}
      </div>
      {picking && (
        <div className="fw-picker-panel fx-pickpanel" role="dialog" aria-label="choose destination conversation">
          <div className="fw-picker-head">
            <span>Include {n === 1 ? 'this post' : `${n} posts`} in…</span>
            <button className="fw-close" onClick={onCancelPick} aria-label="close">×</button>
          </div>
          <p className="fw-meta fx-pick-note">They stay where they live and show in the one you choose too. You confirm before anything changes.</p>
          <ul className="fw-picker-list">
            {(list ?? []).map((t: Conversation) => (
              <li key={t.id}>
                <button disabled={busy} onClick={() => { onCancelPick(); setAsking({ include: t.id }) }}>
                  <span className="fw-cname">{t.name}</span>
                  {t.id === here && <span className="fw-meta"> (current conversation)</span>}
                </button>
              </li>
            ))}
          </ul>
          <div className="fw-picker-actions">
            <button type="button" className="fw-picker-cancel" onClick={onCancelPick}>Cancel</button>
          </div>
        </div>
      )}
    </>
  )
}

/* THE READER'S PLACE SURVIVES A CHANGE OF SIZE (opr-8f6b2b36b16c). Focus and
   its way back, a dragged boundary, a window narrowed to one column: every post
   rewraps, and the same scrollTop then showed other posts (#210 at y=386 came
   back at y=4856, the column on #146). The post the reader is on -- the one
   being read while it is in view, else the first whose top is in view -- is
   noted with its height whenever the reader moves or what is shown changes, and put back at that height
   whenever the column's size changes. Scrolls a change of size causes are not
   the reader's and never move the note, so leaving Focus returns exactly to
   where entering it began.

   WHERE EACH CONVERSATION WAS LEFT (opr-219c06af4fd1). The note is kept per
   conversation (the scroller's `data-place`), with the post read when it was
   taken, so coming back -- Back, Alt+Left, the browser's Back, the switcher
   -- puts the reader where they left it. It once went to the bottom, which
   is the same place only while the newest post fits the column. */
interface Left { id: string; y: number; reading: string | null }
const left = new Map<Id, Left>()

function useKeptPlace(scroller: React.RefObject<HTMLDivElement | null>) {
  const reading = useNav().reading
  const noteRef = useRef<() => void>(() => {})
  useEffect(() => {
    const box = scroller.current
    if (!box) return
    let place: { id: string; y: number } | null = null
    /* every post in view at the note, by its height: a post read in the same
       step as the size changes ("→ This post" leaving Focus) is put back at
       the height it had, though it was read too late to be noted */
    let seenAt = new Map<string, number>()
    const sizeOf = () => `${box.clientWidth}x${box.clientHeight}`
    let size = sizeOf()
    let settling = 0
    const note = () => {
      const b = box.getBoundingClientRect()
      /* The browser's own scroll anchoring answers a new width with a scroll
         before the observer below hears of it: a scroll at a size not yet
         settled is the size's, never the reader's. */
      if (!b.width || sizeOf() !== size || performance.now() < settling) return
      const posts = [...box.querySelectorAll<HTMLElement>('.fx-post[data-post]')]
      const seen = (el: HTMLElement) => { const r = el.getBoundingClientRect(); return r.bottom > b.top + 8 && r.top < b.bottom - 8 }
      const el = posts.find((p) => p.classList.contains('reading') && seen(p))
        ?? posts.find((p) => p.getBoundingClientRect().top >= b.top) ?? posts.find(seen)
      place = el ? { id: el.dataset.post!, y: el.getBoundingClientRect().top - b.top } : null
      seenAt = new Map(posts.filter(seen).map((p) => [p.dataset.post!, p.getBoundingClientRect().top - b.top]))
      const key = box.dataset.place, n = nav.snapshot()
      if (key && place) left.set(key, { ...place, reading: n.conversation === key ? n.reading : null })
    }
    const put = () => {
      const r = nav.snapshot().reading
      const at = r && r !== place?.id && seenAt.has(r) ? { id: r, y: seenAt.get(r)! } : place
      const el = at && box.querySelector<HTMLElement>(`.fx-post[data-post="${CSS.escape(at.id)}"]`)
      if (!at || !el) return
      const off = el.getBoundingClientRect().top - box.getBoundingClientRect().top - at.y
      if (Math.abs(off) >= 1) box.scrollTop += off
    }
    /* A CONVERSATION PLACED WHILE THE SIZE SETTLES IS NOTED ONCE IT HAS
       (P12). Notes while it settles are let go, and a column placed in that
       time -- arriving as its layout's width comes in, the read post brought
       into view -- was never noted unless the reader then scrolled: coming
       back found no place and went to the bottom (777 px on a new brain,
       whose Focus default widens the column just after it opens). Only a
       conversation with no place kept yet: one kept is the reader's, and
       the size's scrolls never move it. */
    let settled = 0
    const ro = new ResizeObserver(() => {
      const now = sizeOf()
      if (!box.clientWidth || now === size) return
      size = now
      /* a width that animates puts the post back at every step of it */
      settling = performance.now() + 600
      put()
      window.clearTimeout(settled)
      settled = window.setTimeout(() => { if (!left.has(box.dataset.place ?? '')) note() }, 620)
    })
    ro.observe(box)
    const onScroll = () => note()
    box.addEventListener('scroll', onScroll, { passive: true })
    /* WHAT IS SHOWN CHANGED WITHOUT A SCROLL (opr-408bfdc22f6c): "N earlier"
       at the top puts a page above with no scroll, so the post noted was no
       longer the one on screen, and Focus went back to it. Posts coming,
       going or rewritten are noted again once drawn, as a scroll would be. */
    let raf = 0
    const mo = new MutationObserver(() => {
      cancelAnimationFrame(raf)
      raf = requestAnimationFrame(note)
    })
    mo.observe(box, { childList: true, subtree: true, characterData: true })
    noteRef.current = note
    return () => { ro.disconnect(); mo.disconnect(); cancelAnimationFrame(raf); window.clearTimeout(settled); box.removeEventListener('scroll', onScroll); noteRef.current = () => {} }
  }, [scroller])
  /* Reading another post without scrolling makes it the one kept. */
  useEffect(() => { const r = requestAnimationFrame(() => noteRef.current()); return () => cancelAnimationFrame(r) }, [reading])
}

/* HELD AT THE NEWEST WHILE IT SETTLES (#568 1.1; production's "at the
   newest, followed", surfaces/ConversationSurface.tsx). Arriving at the
   newest posts, the column was put at its foot once; pictures and prose
   then laid out under it and the newest drifted screens away. While the
   reader is at the newest -- and the newest held is the conversation's --
   whatever grows or arrives keeps them there: posts laying out, a picture
   loading, a new post, the composer growing. Their own scrolling (wheel,
   touch, the scrollbar, the keys) decides whether they are still there,
   and is never written over while their hand is on it. A post read
   elsewhere and brought into view by its card is their place, not the
   newest. */
function useStayAtNewest(scroller: React.RefObject<HTMLDivElement | null>, id: Id, newest: React.MutableRefObject<boolean>) {
  const reading = useNav().reading
  useEffect(() => {
    const box = scroller.current
    if (!box) return
    const now = () => performance.now()
    let hand = -1e9, pressed = false
    const handOn = () => pressed || now() - hand < 700
    const gap = () => box.scrollHeight - box.scrollTop - box.clientHeight
    const atEnd = () => (store.collections.get('conversation:' + id)?.newer ?? 0) === 0
    /* A change of WIDTH is the kept place's to answer (useKeptPlace): the
       post being read stays at its height. Growth is this hook's. */
    let width = box.clientWidth, tall = box.scrollHeight, settling = 0, settled = 0
    const hold = () => {
      /* A width animates (Focus, a dragged boundary) and the posts rewrap
         for as long as it does: none of that is growth to follow. */
      if (box.clientWidth !== width) {
        width = box.clientWidth
        settling = now() + 700
        window.clearTimeout(settled)
        settled = window.setTimeout(() => { newest.current = newest.current && gap() < 24; tall = box.scrollHeight }, 720)
        return
      }
      if (now() < settling) return
      tall = box.scrollHeight
      if (!newest.current || !atEnd() || handOn()) return
      if (gap() > 1) box.scrollTop = box.scrollHeight
    }
    /* Whether the reader is still at the newest is decided by any scroll
       that is not content growing under them (the browser keeping its
       anchor while a picture lands), which the observer above answers. */
    const onScroll = () => {
      const grew = box.scrollHeight !== tall
      tall = box.scrollHeight
      if (handOn() || !grew) newest.current = gap() < 24 && atEnd()
    }
    const touched = () => { hand = now() }
    const down = () => { pressed = true; hand = now() }
    const up = () => { if (pressed) { pressed = false; hand = now(); requestAnimationFrame(onScroll) } }
    const keys = (e: KeyboardEvent) => { if (/^(PageUp|PageDown|ArrowUp|ArrowDown|Home|End| )$/.test(e.key)) hand = now() }
    const ro = new ResizeObserver(hold)
    const watch = () => { ro.observe(box); for (const k of Array.from(box.children)) ro.observe(k) }
    watch()
    const mo = new MutationObserver(() => { watch(); hold() })
    mo.observe(box, { childList: true })
    box.addEventListener('scroll', onScroll, { passive: true })
    box.addEventListener('wheel', touched, { passive: true })
    box.addEventListener('touchmove', touched, { passive: true })
    box.addEventListener('pointerdown', down)
    window.addEventListener('pointerup', up)
    box.addEventListener('keydown', keys)
    return () => {
      ro.disconnect(); mo.disconnect(); window.clearTimeout(settled)
      box.removeEventListener('scroll', onScroll); box.removeEventListener('wheel', touched)
      box.removeEventListener('touchmove', touched); box.removeEventListener('pointerdown', down)
      window.removeEventListener('pointerup', up); box.removeEventListener('keydown', keys)
    }
  }, [scroller, id, newest])
  useEffect(() => {
    const r = requestAnimationFrame(() => {
      const box = scroller.current
      if (box && box.scrollHeight - box.scrollTop - box.clientHeight >= 24) newest.current = false
    })
    return () => cancelAnimationFrame(r)
  }, [reading, scroller, newest])
}

/** Whose posts to show (#568 1.4; UX #712: a compact participant strip, one
 *  row, scrolling): their avatars at the column's top edge, quiet until the
 *  column is hovered, and held in view while it hides anyone. A press shows
 *  or hides someone's posts; a double press shows only theirs; All, everyone.
 *
 *  ONLY WHO IS ACTIVE, EVERYONE ON HOVER (E3, the owner's choice): at rest
 *  the strip shows who is working now -- the live ring -- and whoever the
 *  posts are being filtered by, then "+N" for the rest; with nobody working
 *  and nobody chosen, "All +N". Hover or keyboard focus opens it out to
 *  everyone, the workers still ringed. Who is working is the one activity
 *  reader's (identity/activity.ts), read for this conversation. */
function WhoStrip({ id, hidden }: { id: Id; hidden: number }) {
  const facts = useFacts(id)
  const coll = useCollection('conversation:' + id)
  useThreads()
  const working = new Set(useWorking(id).map((w) => w.participant))
  const who = filterOf(id)
  const last = new Map<Id, number>()
  coll?.items.forEach((it, i) => { const a = store.posts.get(it.id)?.author; if (a) last.set(a, i) })
  const people = [...(facts.data?.participants ?? [])].sort((a, b) => (last.get(b.participant) ?? -1) - (last.get(a.participant) ?? -1))
  const all = people.map((p) => p.participant)
  const shows = (p: Id) => !who.length || who.includes(p)
  const toggle = (p: Id) => {
    const next = new Set(who.length ? who : all)
    if (next.has(p)) next.delete(p)
    else next.add(p)
    setFilter(id, next.size === 0 || all.every((a) => next.has(a)) ? [] : [...next])
  }
  if (people.length < 2) return <span className="fx-grow" />
  /* Active: working now, or among those the posts are filtered by. Working
     first, then the rest in the strip's own order. */
  const active = (p: Id) => working.has(p) || who.includes(p)
  const order = [...people.filter((p) => working.has(p.participant)), ...people.filter((p) => !working.has(p.participant))]
  const rest = people.filter((p) => !active(p.participant)).length
  return (
    <div className="fx-who-strip" role="group" aria-label="Show posts by" data-working={working.size}>
      <button className="fx-who-all" aria-pressed={!who.length} title="Show everyone's posts" onClick={() => setFilter(id, [])}>All</button>
      <div className="fx-who-scroll">
        {order.map((p) => {
          const name = p.alias.replace(/^@/, '')
          const on = working.has(p.participant)
          return (
            <button key={p.participant} className={'fx-who-chip' + (active(p.participant) ? ' fx-who-active' : '')} data-author={p.participant}
              data-working={on || undefined} aria-pressed={shows(p.participant)} aria-label={`${name}${on ? ', working now' : ''}`}
              title={`${name}${on ? ' · working now' : ''}: press to ${shows(p.participant) && who.length ? 'hide' : 'show'} their posts; double press for only theirs`}
              onClick={() => toggle(p.participant)} onDoubleClick={() => setFilter(id, [p.participant])}>
              <Who id={p.participant} name={p.alias} show="avatar" size={20} working={on} />
            </button>
          )
        })}
      </div>
      {rest > 0 && <span className="fx-who-rest" aria-hidden="true" title="Everyone: hover, or move into the strip with the keyboard">+{rest}</span>}
      {hidden > 0 && <span className="fx-who-hidden" title={`${hidden} ${hidden === 1 ? 'post is' : 'posts are'} hidden`}>{hidden} hidden</span>}
    </div>
  )
}

/** The column's frame: rail title, scroller, what sits under it. */
export function ColumnFrame({ title, width, scroller, children, footer, label, tools, place, loading, loadId, searchBar }: {
  title: string
  width: 'wide' | 'narrow' | 'rail'
  scroller: React.RefObject<HTMLDivElement | null>
  children: ReactNode
  footer?: ReactNode
  label: string
  /** the conversation whose place this column keeps for coming back to it */
  place?: Id
  /** quiet controls at the panel's top edge, shown on hover or focus */
  tools?: ReactNode
  loading?: boolean
  loadId?: string | null
  /** Focus Search's bar (search-in/), open under the header over the scroller */
  searchBar?: ReactNode
}) {
  /* THE POST BEING READ STAYS IN VIEW when the column changes width (spec
     19, 22): its posts wrap to the new width, so the column's height
     changes under the reader and the read post could end up cut off under
     the composer. Once the width has settled (.34s), it is brought back into
     view -- only as far as needed. */
  useEffect(() => {
    const t = setTimeout(() => {
      const box = scroller.current
      const el = box?.querySelector<HTMLElement>('.fx-post.reading, .fx-post.anchor')
      if (!box || !el) return
      const r = el.getBoundingClientRect(), b = box.getBoundingClientRect()
      if (r.top < b.top || r.bottom > b.bottom) el.scrollIntoView({ block: r.height > b.height ? 'start' : 'nearest' })
    }, 380)
    return () => clearTimeout(t)
  }, [width, scroller])
  useKeptPlace(scroller)
  return (
    <section className={'fx-conv fx-panel fx-' + width} id="conv" aria-label={label} aria-busy={loading || undefined}>
      <div className="fx-rail-title">{title}{loadId && <SectionSpin id={loadId} label={title} />}</div>
      {tools}
      {searchBar}
      <div className="fw-flow fx-conv-scroll" ref={scroller} data-place={place}>{children}</div>
      {footer}
      {/* Its width is its boundary's, dragged (workspace/Boundary.tsx): no steps. */}
    </section>
  )
}

/** THE RAIL'S PENCIL OPENS IT, FROM THE KEYBOARD TOO: drawn as the rail, the
 *  composer's slot is a button -- in the tab order, Enter or Space -- that
 *  opens the column and puts the caret in its composer. */
export function railPencil(rail: boolean, open: () => void): React.HTMLAttributes<HTMLDivElement> {
  if (!rail) return {}
  const go = (e: React.SyntheticEvent<HTMLDivElement>) => {
    const slot = e.currentTarget
    open()
    requestAnimationFrame(() => requestAnimationFrame(() => {
      if (!slot.closest('.fx-rail')) slot.querySelector<HTMLElement>('.fw-composer-field')?.focus()
    }))
  }
  return {
    role: 'button', tabIndex: 0, 'aria-label': 'Write here: open the conversation', title: 'Open the conversation and write (Enter)',
    onClick: go,
    onKeyDown: (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go(e) } },
  }
}

/** The column drawn on Home (HomeColumn.tsx, D1): the same column, its
 *  Focus left out (there is no workspace beside it to step back), and two
 *  more rows in its ⋯ -- open it as its own conversation, or start another. */
export interface OnHome { open: () => void; fresh: () => void }

export function ConversationColumn({ id, name, width, replyTo, setReplyTo, autoFocusComposer, onAutoFocused, selection, home, zoneTools, rail, onMinimize }: {
  id: Id
  name: string
  width: 'wide' | 'narrow' | 'rail'
  replyTo: Id | null
  setReplyTo: (id: Id | null) => void
  autoFocusComposer?: boolean
  onAutoFocused?: () => void
  selection?: ReactNode
  /** drawn on Home, in a zone of its arrangement */
  home?: OnHome
  /** that zone's own tools, quiet among the column's */
  zoneTools?: ReactNode
  /** drawn as the rail on Home: what opens it there (its pencil), and what
   *  its rail shows in place of the column's tools */
  rail?: { open: () => void; tools: ReactNode }
  /** put it away to the launcher where it is drawn (focus/Launcher.tsx, or
   *  the 3D Brain's tray); absent where it cannot be (Home) */
  onMinimize?: () => void
}) {
  const coll: Collection | undefined = useCollection('conversation:' + id)
  const indexed = useConversationObjects(id)
  const scroller = useRef<HTMLDivElement | null>(null)
  useEffect(() => { void store.loadConversationObjects(id).catch(() => {}) }, [id])
  const replyMatches = useCallback((m: Matcher) => {
    if (!indexed) return null
    const drawn = new Set(coll?.items.map((x) => x.id) ?? [])
    const hits = indexed.objects.filter((row) => !drawn.has(row.post) && anyIn([
      row.title, row.kind, row.preview?.title, row.preview?.name,
      row.preview?.type, row.preview?.block?.body,
    ], m))
    if (!hits.length) return null
    const siblings = indexed.objects.map((x) => x.address)
    return {
      label: `${hits.length} ${hits.length === 1 ? 'match' : 'matches'} in replies`,
      matches: hits.slice(0, 4).map((hit) => ({
        label: `#${hit.number ?? '?'} · ${hit.title ?? hit.kind}`,
        pick: () => act.peek({ address: hit.address, title: hit.title ?? hit.kind,
          kind: hit.kind, from: `#${hit.number ?? '?'} · reply to #${hit.reply_to_number ?? '?'}`, siblings }),
      })),
    }
  }, [indexed, coll])
  /* FOCUS SEARCH (search-in/): find within what the column shows; the bar
     opens under the header and searches the scroller. The rail shows no
     posts, so it has no search of its own. */
  const search = useFocusSearch(
    () => (width === 'rail' ? null : scroller.current),
    () => (width === 'rail' ? null : (scroller.current?.closest('.fx-conv') as HTMLElement | null) ?? null),
    /* the conversation is one content wherever it is drawn (focus/types.ts) */
    CONVERSATION_ID,
    replyMatches,
  )
  const [first, setFirst] = useState(true)
  /* Where it was left, taken as it is entered: once its posts are drawn here
     the column notes itself again, before they are placed. */
  const kept = useRef<{ for: Id | null; at: Left | null }>({ for: null, at: null })
  if (kept.current.for !== id) kept.current = { for: id, at: left.get(id) ?? null }
  /* PLACED ONCE WHAT IS SHOWN IS WHAT WAS READ FOR THIS ENTRY (#568 1.1).
     Coming back to a conversation still held, it was placed on the held
     posts, and then the newest page was swapped in beneath the restored
     place, which then showed posts near the top. Now a remembered place
     still in what is held is read again as it is held (`keepWidth`), so the
     place is still there; with none, the newest page is read; and the column
     is placed only once that read has landed. */
  const [ready, setReady] = useState<Id | null>(null)
  const loadId = 'fluid:conversation:' + id
  const isReading = ready !== id || !coll
  useSectionLoad(loadId, name || 'Conversation', { loading: isReading, error: null, data: coll ? true : null })
  useEffect(() => {
    setFirst(true)
    setReady(null)
    const at = kept.current.at, held = store.collections.get('conversation:' + id)
    const keepHeld = !!at && !!held?.items.some((i) => i.id === at.id)
    let live = true
    void store.loadConversation(id, keepHeld).finally(() => { if (live) setReady(id) })
    return () => { live = false }
  }, [id])
  const newest = useRef(false)
  useEffect(() => {
    if (coll && first && ready === id && scroller.current) {
      const box = scroller.current, at = kept.current.at, r = nav.snapshot().reading
      /* Back where it was left, while the post read then is the one read now;
         a post named on arriving is brought into view by its card instead. */
      const el = at && r === at.reading ? box.querySelector<HTMLElement>(`.fx-post[data-post="${CSS.escape(at.id)}"]`) : null
      if (el && at) box.scrollTop += el.getBoundingClientRect().top - box.getBoundingClientRect().top - at.y
      else {
        box.scrollTop = box.scrollHeight
        /* The post being read -- named by the address, or the one read last --
           stays in view, as its card would bring it: placed after the read
           lands, the foot must not carry it away. */
        const rd = r ? box.querySelector<HTMLElement>(`.fx-post[data-post="${CSS.escape(r)}"]`) : null
        if (rd) {
          const a = rd.getBoundingClientRect(), b = box.getBoundingClientRect()
          if (a.bottom < b.top + 8 || a.top > b.bottom - 8) rd.scrollIntoView({ block: a.height > b.height * 0.8 ? 'start' : 'center' })
        }
      }
      newest.current = !el && coll.newer === 0 && box.scrollHeight - box.scrollTop - box.clientHeight < 24
      setFirst(false)
    }
  }, [coll, first, ready, id])
  useStayAtNewest(scroller, id, newest)
  /* THE POST BEING READ IS IN THE CONVERSATION (opr-49f1f943b6a9). Opened
     from search, a link, Home, a notification or "from #N", it may be older
     than the newest page held: the conversation is then read around it, where
     its card shows it read and brings it into view (PostCard). A reply is
     drawn through its thread: the conversation is read around the thread's
     post, and the thread opens beside it with the reply read inside -- in the
     same step, so Back still goes where the reader came from. Each post is
     looked for once per conversation. */
  const s = useNav()
  const want = s.conversation === id ? s.reading : null
  const tried = useRef(new Set<Id>())
  useEffect(() => { tried.current = new Set() }, [id])
  useEffect(() => {
    if (!coll || !want || tried.current.has(want) || coll.items.some((i) => i.id === want)) return
    let live = true
    void drawnBy(id, want).then((at) => {
      if (!live || tried.current.has(want)) return
      const now = nav.snapshot()
      if (now.conversation !== id || now.reading !== want) return
      if (at !== want) {
        const open = nav.sheetOf(now)
        const pinned = pinsOf(id).active
        const shown = open?.kind === 'replies' ? open.root : open ? null : pinned
        if (!shown || !inThread(want, shown)) { tried.current.add(want); nav.showInThread(at) }
      }
      const held = store.collections.get('conversation:' + id)
      if (held?.items.some((i) => i.id === at)) return
      tried.current.add(want)
      void store.conversationAround(id, at)
    })
    return () => { live = false }
  }, [coll, want, id])
  /* ...and from there the reader scrolls both ways: older pages load near
     the top, newer ones near the bottom, one read at a time each way. */
  useEffect(() => {
    const el = scroller.current
    if (!el) return
    const busy = { older: false, newer: false }
    const page = (way: 'older' | 'newer') => {
      if (busy[way]) return
      busy[way] = true
      void (way === 'older' ? store.olderOfConversation(id) : store.newerOfConversation(id)).finally(() => { busy[way] = false })
    }
    const onScroll = () => {
      const c = store.collections.get('conversation:' + id)
      if (!c) return
      if (c.newer > 0 && el.scrollHeight - el.scrollTop - el.clientHeight < 400) page('newer')
      if (c.older > 0 && el.scrollTop < 400) page('older')
    }
    el.addEventListener('scroll', onScroll, { passive: true })
    return () => el.removeEventListener('scroll', onScroll)
  }, [id])
  useThreads()
  const who = filterOf(id)
  /* A TOPIC IN FORCE (A8) draws its posts in place of the conversation's:
     their own collection, read by the conversation collection's `topic`. */
  const topic = topicOf(id)
  const topicColl = useCollection(topic ? topicKey(id, topic) : '')
  useEffect(() => { if (topic) void store.loadTopic(id, topic).catch((e: Error) => store.setError(e.message)) }, [id, topic])
  const flow = topic ? topicColl : coll
  const byWho = (flow?.items ?? []).filter((p) => !who.length || who.includes(store.posts.get(p.id)?.author ?? ''))
  const hidden = (flow?.items.length ?? 0) - byWho.length
  /* AGENT WORK IS FOLDED AWAY BY DEFAULT (agentWork.ts), behind a control
     that says how many and shows them. A post navigated to -- a link, Latest,
     the bell, search -- is never kept folded: the post read, or the thread it
     is read in, is revealed and stays so while this conversation is open. */
  useAgentWork()
  const showWork = showsAgentWork(id)
  const work = useAgentWorkIn(byWho.map((p) => p.id))
  const opened = useRef<{ for: Id; ids: Set<Id> }>({ for: id, ids: new Set() })
  if (opened.current.for !== id) opened.current = { for: id, ids: new Set() }
  if (want) for (const p of byWho) if (work.has(p.id) && (p.id === want || inThread(want, p.id))) opened.current.ids.add(p.id)
  const folded = showWork ? new Set<Id>() : new Set(byWho.filter((p) => work.has(p.id) && !opened.current.ids.has(p.id)).map((p) => p.id))
  const shown = byWho.filter((p) => !folded.has(p.id))
  const workShown = showWork ? work.size : folded.size
  const isFocused = focused()
  const working = useWorking(id)
  /* On Home its menu is a sheet of its own: the conversation shown beside
     the workspace is another column, with its own. */
  const menuId = home ? CONV_MENU + ':home' : CONV_MENU
  return (
    <ColumnFrame title={name} width={width} scroller={scroller} label="conversation" place={id} loading={isReading} loadId={loadId}
      searchBar={width === 'rail' ? undefined : search.bar}
      tools={width === 'rail' ? rail?.tools : (
        <div className={'fx-conv-tools' + (who.length || topic || working.length ? ' held' : '')}>
          <SectionSpin id={loadId} label={name} />
          <WhoStrip id={id} hidden={hidden} />
          <TopicsControl id={id} sheet={menuId + ':topics'} />
          {zoneTools}
          <SearchButton className="fx-ctl" onOpen={() => search.setOpen(true)} label="Search in this conversation" />
          {!home && (
            <button className="fx-ctl fx-focus-btn" aria-pressed={isFocused}
              title={isFocused ? 'Show the workspace again (Esc)' :'Conversation focus: the conversation takes the room, the workspace steps back'}
              onClick={() => setFocused(!isFocused)}>{isFocused ? '⤡ Workspace' : '⤢ Focus'}</button>
          )}
          {onMinimize && (
            <button className="fx-ctl fx-min-btn" aria-label="Minimize the conversation" title="Minimize: the page takes its room; the launcher brings it back (Undo too)"
              onClick={onMinimize}>–</button>
          )}
          <button className="fx-ctl fx-conv-menu-btn" aria-label="conversation menu" title="This conversation: Brief, Actions, Follow ups, Media, Guidance"
            onClick={(e) => openSheet(menuId, e.currentTarget)}>⋯</button>
          <ConversationMenu id={id} sheet={menuId} home={home} onMinimize={onMinimize} />
        </div>
      )}
      footer={
        <>
          {working.length > 0 && <WorkingLine working={working} />}
          {selection}
          <div className="fx-composer-slot" {...railPencil(width === 'rail', rail?.open ?? nav.openRail)}>
            <Composer conversation={id} replyTo={replyTo} onClearReply={() => setReplyTo(null)}
              autoFocus={autoFocusComposer} onAutoFocused={onAutoFocused} />
          </div>
        </>
      }>
      <TimeSpent id={id} className="fx-time-spent" />
      {workShown > 0 && width !== 'rail' && (
        <div className="fx-agent-work-bar">
          <button className="fx-agent-work-toggle" aria-pressed={showWork}
            title={showWork ? 'Fold away the posts agents wrote to each other' : 'Show the briefs, findings, results and follow-ups agents wrote to each other'}
            onClick={() => setShowsAgentWork(id, !showWork)}>
            {showWork ? `Hide agent work (${work.size})` : `Show ${folded.size} agent work ${folded.size === 1 ? 'post' : 'posts'}`}
          </button>
        </div>
      )}
      {topic ? (
        <TopicFlow id={id} topic={topic} coll={topicColl} total={coll?.total ?? null} reading={want} />
      ) : (
        <>
          {coll && coll.older > 0 && (
            <button className="fw-more fx-more-btn" onClick={() => void store.olderOfConversation(id)}>{coll.older} earlier</button>
          )}
          {coll && coll.items.length === 0 && <p className="fx-welcome">Nothing here yet. Write the first post below.</p>}
        </>
      )}
      {/* the conversation's work, read once for its cards (WorkStatusPill) */}
      <WorkStatusProvider conversation={id}>
        {shown.map((p) => work.has(p.id) ? (
          <div key={p.id} className="fx-agent-work" data-agent-work={store.posts.get(p.id)?.agent_work?.kind}>
            <p className="fx-agent-work-why">Agent work · {agentWhy(p.id)}</p>
            <PostCard id={p.id} place={p} scroller={scroller} />
          </div>
        ) : <PostCard key={p.id} id={p.id} place={p} scroller={scroller} />)}
      </WorkStatusProvider>
      {!topic && coll && coll.newer > 0 && (
        <button className="fw-more fx-more-btn fx-later-btn" onClick={() => void store.newerOfConversation(id)}>{coll.newer} later</button>
      )}
      {hidden > 0 && <p className="fx-faint fx-hidden-note">{hidden} {hidden === 1 ? 'post is' : 'posts are'} hidden by who you chose to show. <button className="fx-linkish" onClick={() => setFilter(id, [])}>Show everyone's</button></p>}
    </ColumnFrame>
  )
}

const CONV_MENU = 'conversation-menu'

/** The conversation's ⋯ (#188's capability table): whose posts to show,
 *  Brief, Actions, Follow ups, Media and Guidance as slide-outs, conversation
 *  focus, and its export. */
function ConversationMenu({ id, sheet, home, onMinimize }: { id: Id; sheet: string; home?: OnHome; onMinimize?: () => void }) {
  const facts = useFacts(id)
  useThreads()
  const about = (section: nav.AboutSection) => {
    closeSheet()
    nav.openDetail({ kind: 'about', conversation: id, section, anchor: { kind: 'zone', zone: 'conversation' }, mode: 'aside' })
  }
  return (
    <Sheet id={sheet} label="conversation menu" className="fx-conv-menu">
      {home && (
        <>
          <button className="fx-opt fx-home-open" onClick={() => { closeSheet(); home.open() }}>Open as its own conversation <small>with its workspace; Home keeps it here</small></button>
          <button className="fx-opt fx-home-fresh" onClick={() => { closeSheet(); home.fresh() }}>Start another conversation here <small>this one stays where it is</small></button>
        </>
      )}
      <div className="fx-sec">About this conversation</div>
      <button className="fx-opt" onClick={() => about('brief')}>Brief <small>what's going on, what waits on you</small></button>
      <button className="fx-opt" onClick={() => about('actions')}>Actions <small>{facts.data ? `${facts.data.owed.length} owed, not answered` : 'what is owed here'}</small></button>
      <button className="fx-opt" onClick={() => about('followups')}>Follow ups <small>side-notes nobody carries</small></button>
      <button className="fx-opt" onClick={() => about('media')}>Media <small>attachments in these posts</small></button>
      <button className="fx-opt" onClick={() => about('guidance')}>Guidance <small>what governs work here</small></button>
      <div className="fx-sec">Presentation</div>
      <FollowOption />
      {!home && (
        <button className="fx-opt" aria-pressed={focused()} onClick={() => { closeSheet(); setFocused(!focused()) }}>
          {focused() ? 'Show the workspace again' : 'Conversation focus'} <small>{focused() ? 'the workspace comes back as it was' : 'the conversation takes the room'}</small>
        </button>
      )}
      {onMinimize && (
        <button className="fx-opt" data-act="minimize" onClick={() => { closeSheet(); onMinimize() }}>
          Minimize <small>the page takes its room; the launcher brings it back</small>
        </button>
      )}
      <button className="fx-opt" data-act="export" onClick={() => { closeSheet(); void exportConversation(id) }}>
        Export conversation <small>download as a .zip archive</small>
      </button>
    </Sheet>
  )
}

/* -- Topics (A8): production's Topics rail, Fluid-native -------------------
   A conversation's Topics are a navigation of their own (surfaces/
   TopicsAffordance.tsx): reachable without opening anything else, saying at
   rest only how many there are -- or, while one holds the conversation, its
   name -- and listing them, with how many posts each holds, on a press. One
   holds the conversation until All is chosen; nothing is sent anywhere. */
interface TopicRow { id: Id; name: string; about?: string; turns?: number }

function TopicsControl({ id, sheet }: { id: Id; sheet: string }) {
  const facts = useFacts(id)
  useThreads()
  const list = (facts.data?.topics ?? []) as TopicRow[]
  const topic = topicOf(id)
  const on = list.find((t) => t.id === topic)
  if (!list.length && !topic) return null
  return (
    <>
      {topic ? (
        <span className="fx-filter-chip fx-topic-chip" data-topic={topic}>
          <button className="fx-topic-name" title="Topics: choose another, or All" onClick={(e) => openSheet(sheet, e.currentTarget)}># {on?.name ?? 'Topic'}</button>
          <button aria-label={`stop reading under ${on?.name ?? 'this topic'}: show all posts`} title="Show all posts" onClick={() => setTopic(id, null)}>✕</button>
        </span>
      ) : (
        <button className="fx-ctl fx-topics-btn" aria-label={`Topics: ${list.length}`} title={`This conversation's Topics (${list.length}): read one on its own`}
          onClick={(e) => openSheet(sheet, e.currentTarget)}># {list.length}</button>
      )}
      <Sheet id={sheet} label="topics" className="fx-topics-sheet">
        <TopicsList id={id} list={list} />
      </Sheet>
    </>
  )
}

function TopicsList({ id, list }: { id: Id; list: TopicRow[] }) {
  const [q, setQ] = useState('')
  const coll = useCollection('conversation:' + id)
  const topic = topicOf(id)
  const want = q.trim().toLowerCase()
  const rows = want ? list.filter((t) => t.name.toLowerCase().includes(want)) : list
  const choose = (t: Id | null) => { closeSheet(); setTopic(id, t) }
  return (
    <div className="fx-topics">
      {list.length > 6 && (
        <input className="fx-topics-find" placeholder="Find a topic" aria-label="find a topic" value={q} autoFocus onChange={(e) => setQ(e.target.value)} />
      )}
      <button className={'fx-opt fx-topic-row' + (!topic ? ' on' : '')} aria-current={!topic} onClick={() => choose(null)}>
        All posts <small>{coll ? `${coll.total}` : ''}</small>
      </button>
      {rows.map((t) => (
        <button key={t.id} className={'fx-opt fx-topic-row' + (topic === t.id ? ' on' : '')} aria-current={topic === t.id} data-topic={t.id}
          title={t.about ? `${t.name}: ${t.about}` : t.name} onClick={() => choose(topic === t.id ? null : t.id)}>
          <span className="fx-topic-label"># {t.name}</span> <small>{t.turns ?? ''}</small>
        </button>
      ))}
      {want && rows.length === 0 && <p className="fx-faint fx-none">No topic by that name.</p>}
    </div>
  )
}

/** The head of a conversation read under one Topic: which, how many of all,
 *  the way back to every post, and the post being read if it is not here. */
function TopicFlow({ id, topic, coll, total, reading }: { id: Id; topic: Id; coll: Collection | undefined; total: number | null; reading: Id | null }) {
  const facts = useFacts(id)
  const name = ((facts.data?.topics ?? []) as TopicRow[]).find((t) => t.id === topic)?.name ?? 'this topic'
  const here = !reading || !coll || coll.items.some((i) => i.id === reading || inThread(reading, i.id))
  const r = reading ? store.posts.get(reading) : undefined
  return (
    <div className="fx-topic-head" role="status">
      <p className="fx-topic-says">
        Reading <b># {name}</b>{coll ? ` · ${coll.total} of ${total ?? '…'} posts` : ' · reading…'}
        {' '}<button className="fx-linkish" onClick={() => setTopic(id, null)}>Show all posts</button>
      </p>
      <TimeSpent id={topic} className="fx-time-spent" />
      {coll && coll.older > 0 && (
        <button className="fw-more fx-more-btn" onClick={() => void store.olderOfTopic(id, topic)}>{coll.older} earlier under this topic</button>
      )}
      {coll && coll.items.length === 0 && <p className="fx-welcome">Nothing is filed under this topic yet.</p>}
      {!here && r && (
        <p className="fx-faint fx-topic-away">
          {r.number != null ? `#${r.number}` : 'The post'} you are reading is not under this topic. <button className="fx-linkish" onClick={() => setTopic(id, null)}>Show it among all posts</button>
        </p>
      )}
    </div>
  )
}

/** Follow the post read (A1), from the menu: turned on with nothing open
 *  beside the conversation, the post being read opens there at once. */
function FollowOption() {
  const s = useNav()
  const on = !!s.follow
  return (
    <button className="fx-opt fx-follow-opt" aria-pressed={on} onClick={() => {
      closeSheet()
      nav.setFollow(!on)
      if (!on && s.reading && !nav.sheetOf(s))
        nav.openDetail({ kind: 'replies', root: s.reading, anchor: { kind: 'post', id: s.reading }, mode: 'aside' })
    }}>
      {on ? 'Stop following the post read' : 'Follow the post read'} <small>{on ? 'replies stay where you opened them' : 'its replies open beside the conversation'}</small>
    </button>
  )
}

export function StreamColumn({ width, selection }: { width: 'wide' | 'narrow' | 'rail'; selection?: ReactNode }) {
  const coll = useCollection('stream')
  const scroller = useRef<HTMLDivElement | null>(null)
  const loadingOlder = useRef(false)
  useEffect(() => {
    void store.loadStream()
    return () => { store.dropStream() }
  }, [])
  const older = () => {
    if (loadingOlder.current) return
    loadingOlder.current = true
    store.olderOfStream().finally(() => { loadingOlder.current = false })
  }
  /* Older pages load on scroll. */
  useEffect(() => {
    const el = scroller.current
    if (!el) return
    const onScroll = () => {
      if (el.scrollHeight - el.scrollTop - el.clientHeight < 300 && coll?.before) older()
    }
    el.addEventListener('scroll', onScroll, { passive: true })
    return () => el.removeEventListener('scroll', onScroll)
  }, [coll?.before])
  return (
    <ColumnFrame title="Stream" width={width} scroller={scroller} label="stream" footer={selection}>
      <div className="fw-stream-flow" aria-label="stream flow">
        {coll && coll.items.length === 0 && <p className="fx-welcome">Nothing in the Stream yet.</p>}
        {coll?.items.map((p) => <PostCard key={p.id} id={p.id} place={p} scroller={scroller} />)}
        {coll && coll.before && <button className="fw-more fx-more-btn" onClick={older}>Older posts</button>}
      </div>
    </ColumnFrame>
  )
}

export function Welcome({ width }: { width: 'wide' | 'narrow' | 'rail' }) {
  const scroller = useRef<HTMLDivElement | null>(null)
  /* THE PICKER NEVER COVERS THE LINE (F6 final fix round): while a sheet is
     open over the column -- the first visit's picker -- the line sits below
     its bottom edge, wherever that falls, never higher than 40vh. The picker
     is drawn in the layer, outside this column's flow, so its edge is
     measured -- and measured again whenever the picker or the column changes
     size (its list arriving late, a resize), not once on open. */
  const sheet = useOpenSheet()
  const [below, setBelow] = useState<number | null>(null)
  useLayoutEffect(() => {
    if (!sheet) { setBelow(null); return }
    let raf = 0, tries = 0, watched: Element | null = null
    const measure = () => {
      const pop = document.querySelector('.fx-pop'), sc = scroller.current
      if (!pop || !sc) { if (++tries < 60) raf = requestAnimationFrame(measure); return }
      if (pop !== watched) { if (watched) ro.unobserve(watched); ro.observe(pop); watched = pop }
      setBelow(Math.ceil(pop.getBoundingClientRect().bottom - sc.getBoundingClientRect().top + 24))
    }
    const ro = new ResizeObserver(() => measure())
    if (scroller.current) ro.observe(scroller.current)
    window.addEventListener('resize', measure)
    raf = requestAnimationFrame(measure)
    return () => { cancelAnimationFrame(raf); ro.disconnect(); window.removeEventListener('resize', measure) }
  }, [sheet])
  return (
    <ColumnFrame title="Mentis" width={width} scroller={scroller} label="conversation">
      <div className="fx-welcome fx-first" style={below != null ? { marginTop: `max(40vh, ${below}px)` } : undefined}>Choose a conversation to start.</div>
    </ColumnFrame>
  )
}
