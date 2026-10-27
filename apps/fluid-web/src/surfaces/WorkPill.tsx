import { createContext, useCallback, useContext, useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { useApi, type Id } from '../api'
import { useMe } from '../identity'
import type { WorkItem, WorkOverview } from '../work/contract'
import WorkHoverCard from '../work/WorkHoverCard'
import WorkDrawer, { claimDrawer, releaseDrawer } from '../work/WorkDrawer'
import { stageParts } from '../work/stage'
import './WorkPill.css'

/* ------------------------------------------------------------------------ *
 * THE CONVERSATION'S WORK PILLS: ONE READ, ONE DRAWER.
 *
 * `WorkPillProvider` is mounted once by `ConversationSurface`. It reads the
 * conversation's work once, indexes it by originating Turn, and holds the
 * one drawer the surface may have open. A pill only looks itself up and asks
 * the provider to open its drawer, so opening a second pill's drawer
 * replaces the first instead of stacking a second one over it.
 *
 * NOT A LIVE-RUNS READER. `/api/work` is a projection over the record; it
 * rereads when the record advances, spaced, and not when only live
 * execution moved -- the Turn's own work status (`WorkStatus`) shows that.
 * ------------------------------------------------------------------------ */

/** Reread the conversation's work at most this often (ms) on an advance. */
export const PILL_SPACING = 15_000

/** At or below this viewport width the drawer is a full-screen sheet. */
export const SHEET_BELOW = 900

/** And whenever making room for it would leave the conversation's column
 *  narrower than this (px), so the column never collapses. */
export const MIN_COLUMN = 420

/** The drawer's width as the stylesheet gives it (`--work-drawer-width`). */
function drawerWidth() {
  const probe = document.createElement('div')
  probe.style.cssText = 'position:fixed;visibility:hidden;pointer-events:none;width:var(--work-drawer-width)'
  document.body.append(probe)
  const w = probe.offsetWidth
  probe.remove()
  return w
}

/** THE PUSH IS WHAT THE DRAWER COVERS OF THE COLUMN, read from the layout:
 *  the conversation's centre track gives up exactly the part of itself the
 *  drawer would lie over (`--work-drawer-push`), which is nothing where the
 *  track ends left of the drawer. Where what is left would be too narrow to
 *  read, nothing is pushed and the drawer is a sheet instead. Returns
 *  whether it is a sheet. */
function usePush(open: boolean, host: { current: HTMLElement | null }) {
  const [sheet, setSheet] = useState(false)
  useLayoutEffect(() => {
    if (!open) return
    const root = document.documentElement
    /* THE CONVERSATION THAT HOSTS THE DRAWER: the one its pill is in, not
       whichever comes first on the page (Compare shows two). */
    const conv = host.current?.closest('.conv') ?? document.querySelector('.conv')
    const centre = conv?.closest<HTMLElement>('.centre') ?? null
    /* COMPARE IS ALWAYS A SHEET: its two panes fill the width, so a drawer
       at the right lies over the other conversation whichever side opened
       it, and pushing would halve two columns at once. */
    const compare = !!conv?.closest('.workspace.compare')
    const measure = () => {
      const view = root.clientWidth
      const box = centre?.getBoundingClientRect()
      const push = box ? Math.max(0, Math.ceil(box.right - (view - drawerWidth()))) : 0
      const narrow = compare || view <= SHEET_BELOW || (box !== undefined && box.width - push < MIN_COLUMN)
      root.style.setProperty('--work-drawer-push', `${narrow ? 0 : push}px`)
      setSheet(narrow)
    }
    measure()
    window.addEventListener('resize', measure)
    const size = new ResizeObserver(measure)
    if (centre) size.observe(centre)
    return () => {
      window.removeEventListener('resize', measure)
      size.disconnect()
      root.style.removeProperty('--work-drawer-push')
    }
  }, [open, host])
  return open && sheet
}

interface ConvWork {
  itemsByTurn: Map<Id, WorkItem>
  viewer: Id | null
  /** The Turn whose drawer is open, or null. */
  open: Id | null
  openDrawer: (turn: Id, expectation: Id, opener: HTMLElement | null) => void
}

const Ctx = createContext<ConvWork | null>(null)

const workPath = (viewer: Id | null, conversation: Id) =>
  `/api/work?${viewer ? `viewer=${encodeURIComponent(viewer)}&` : ''}conversation=${encodeURIComponent(conversation)}`

/** THE CONVERSATION'S WORK, READ ONCE AND INDEXED BY ORIGINATING TURN: the
 *  pills' one reader, shared with Fluid's post cards (fluid/conversation/
 *  PostCard.tsx), which mount it once per conversation as these do. */
export function useWorkByTurn(conversation: Id | null) {
  const { me } = useMe()
  const viewer = me ?? null
  const read = useApi<WorkOverview>(conversation ? workPath(viewer, conversation) : null, { spacing: PILL_SPACING })
  const itemsByTurn = useMemo(() => {
    const map = new Map<Id, WorkItem>()
    for (const it of read.data?.items ?? []) {
      if (it.origin?.turn && !map.has(it.origin.turn)) map.set(it.origin.turn, it)
    }
    return map
  }, [read.data])
  return { itemsByTurn, viewer }
}

export function WorkPillProvider({ conversation, children }: { conversation: Id | null; children: React.ReactNode }) {
  const { itemsByTurn, viewer } = useWorkByTurn(conversation)

  const [open, setOpen] = useState<{ turn: Id; expectation: Id } | null>(null)
  const opener = useRef<HTMLElement | null>(null)
  useEffect(() => setOpen(null), [conversation])
  const close = useCallback(() => setOpen(null), [])
  /* ONE OPEN DRAWER, APP-WIDE (`claimDrawer`): each conversation surface has
     its own provider, and Compare shows two. Claiming before the render
     closes the other's in the same render, so the push and `inert` are only
     ever the open drawer's. */
  const openDrawer = useCallback((turn: Id, expectation: Id, from: HTMLElement | null) => {
    claimDrawer(close)
    opener.current = from
    setOpen({ turn, expectation })
  }, [close])
  useEffect(() => {
    if (open === null) releaseDrawer(close)
  }, [open, close])
  useEffect(() => () => releaseDrawer(close), [close])
  const narrow = usePush(open !== null, opener)
  const value = useMemo<ConvWork>(
    () => ({ itemsByTurn, viewer, open: open?.turn ?? null, openDrawer }),
    [itemsByTurn, viewer, open, openDrawer],
  )
  return (
    <Ctx.Provider value={value}>
      {children}
      {/* ONE DRAWER, NOT KEYED: switching pills changes what it reads while
          the push and `inert` it set stay exactly as they are; closing it
          is the only thing that restores them. */}
      {open && (
        <WorkDrawer
          expectation={open.expectation}
          viewer={viewer}
          sheet={narrow}
          returnFocus={opener}
          onClose={close}
        />
      )}
    </Ctx.Provider>
  )
}

/** The pill's words. What the viewer owes is said, in coral, whenever the
 *  item needs them -- even when the objective was claimed met, and whether
 *  it is owed as a decision or through what they otherwise owe. */
export function formatPillText(item: WorkItem) {
  const parts = item.status_words.split('·').map((s) => s.trim())
  const owes = (() => {
    if (item.decisions_open > 0) {
      return `${item.decisions_open} ${item.decisions_open === 1 ? 'decision' : 'decisions'}`
    }
    if (item.group !== 'needs_you') return null
    // The server's own count of what is owed, e.g. "2 questions for you".
    const ask = parts.slice(1).find((p) => /\b(decisions?|questions?)\b/i.test(p))
    return ask ? ask.replace(/\s+for you$/i, '') : 'owed by you'
  })()

  if (item.objective_met === true) {
    return { status: 'objective met', decisions: owes, extra: null }
  }

  /* WHERE THE WORK STANDS, when the server says it: "awaiting review",
     "blocked · the review found problems to fix", "deployed". */
  const staged = stageParts(item)
  if (staged) {
    const word = staged.word.toLowerCase()
    const owedAlready = staged.stage === 'awaiting_owner' && owes !== null
    return { status: word, decisions: owes, extra: staged.detail && !owedAlready ? staged.detail : null }
  }

  // Primary status word (never "objective met" unless objective_met === true)
  const primary = (() => {
    if (item.group === 'unknown') return 'unknown'
    const first = item.status_words.split(/[·—]/)[0].trim().toLowerCase()
    if (first.includes('objective met')) return 'in flight'
    return first || 'in flight'
  })()

  // With nothing owed, the execution summary phrase if there is one. Ended
  // work always keeps its "not marked complete": "ended" alone reads as done.
  let extra: string | null = null
  if ((!owes || primary === 'ended') && parts.length > 1 && !/decision|question/i.test(parts[1])) {
    extra = parts[1]
  }

  return { status: primary, decisions: owes, extra }
}

export default function WorkPill({ turn }: { turn: Id; conversation?: Id }) {
  const work = useContext(Ctx)
  const item = work?.itemsByTurn.get(turn)

  const [hovered, setHovered] = useState(false)
  const pillRef = useRef<HTMLButtonElement | null>(null)
  const leaveTimer = useRef<number | null>(null)
  const cardId = useId()

  useEffect(() => {
    return () => {
      if (leaveTimer.current) window.clearTimeout(leaveTimer.current)
    }
  }, [])

  // Show the pill only on Turns that originate a work item
  if (!work || !item) return null

  const drawerOpen = work.open === turn
  const { status, decisions, extra } = formatPillText(item)
  const isHot = decisions !== null || item.group === 'needs_you' || drawerOpen

  const show = () => {
    if (leaveTimer.current) {
      window.clearTimeout(leaveTimer.current)
      leaveTimer.current = null
    }
    setHovered(true)
  }
  const hide = () => {
    leaveTimer.current = window.setTimeout(() => setHovered(false), 180)
  }
  const openDrawer = () => {
    setHovered(false)
    work.openDrawer(turn, item.expectation, pillRef.current)
  }
  const cardShown = hovered && !drawerOpen && pillRef.current !== null

  return (
    <>
      <button
        ref={pillRef}
        type="button"
        className={'wpill' + (isHot ? ' hot' : '')}
        onClick={(e) => {
          e.stopPropagation()
          openDrawer()
        }}
        onMouseEnter={show}
        onMouseLeave={hide}
        // The summary for keyboard focus only: focus handed back by a closed
        // drawer, or left by a click, is not asking for it. Leaving takes it
        // away at once, so a card the reader has moved on from cannot hold
        // on to the next Escape.
        onFocus={(e) => {
          if (e.currentTarget.matches(':focus-visible')) show()
        }}
        onBlur={() => {
          if (leaveTimer.current) window.clearTimeout(leaveTimer.current)
          setHovered(false)
        }}
        aria-haspopup="dialog"
        aria-expanded={drawerOpen}
        aria-describedby={cardShown ? cardId : undefined}
      >
        Work · <b>{status}</b>
        {decisions && <> · <span className="nd">{decisions}</span></>}
        {extra && <> · {extra}</>}
      </button>

      {cardShown && (
        <WorkHoverCard
          id={cardId}
          item={item}
          anchor={pillRef.current!}
          viewer={work.viewer}
          onOpen={openDrawer}
          onDismiss={() => setHovered(false)}
          onMouseEnter={show}
          onMouseLeave={hide}
        />
      )}
    </>
  )
}
