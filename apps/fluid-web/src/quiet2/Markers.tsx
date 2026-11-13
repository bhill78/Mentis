/* STEPPED MARKERS: navigation without a panel.
 *
 * One short bar per conversation (or topic). Two dimensions, kept apart:
 *  - LENGTH is how much material there is, in four steps, never proportional,
 *    so a conversation of hundreds of posts is still only the longest step.
 *  - THICKNESS is how recently anything happened there.
 * At rest only the bars show. Hovering or focusing the stack opens the names
 * in a card beside it that floats over the page and reserves nothing.
 *
 * THE CARD READS LIKE A SECTION LIST: each name is the thing to read, and
 * wraps rather than being cut short; how many posts it holds and when it
 * last moved sit under it, smaller and quieter; the one in use is marked.
 *
 * THE CARD IS PLACED, NOT ASSUMED (round 1 refinement). Both rails use one
 * rule, `placeCard`: it opens beside its own rail, toward the side with room,
 * row for row level with the bars it names; where the window is too short it
 * slides to stay inside it, and where it is too narrow it narrows (names
 * ellipsise) rather than run off the edge.
 *
 * ROUND 1 THRESHOLDS, FOR REVIEW: they are here to be argued with, not
 * settled semantics. */
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import type { MarkerItem } from './sample'

/** Four discrete lengths, the longest about 30px. */
export const LENGTHS = [8, 14, 22, 30] as const
const LENGTH_AT = [10, 40, 150] // posts: <10, <40, <150, 150+

/** Thickness by recency: within the hour, today, this week, older. */
export const THICKNESS = [4, 3, 2, 1] as const
const RECENT_AT = [60, 60 * 24, 60 * 24 * 7] // minutes idle

export const lengthOf = (count: number) => LENGTHS[LENGTH_AT.filter((n) => count >= n).length]
export const thicknessOf = (idle: number) => THICKNESS[RECENT_AT.filter((n) => idle >= n).length]

export const ago = (m: number) => m < 60 ? `${m} min ago` : m < 60 * 24 ? `${Math.round(m / 60)} h ago` : `${Math.round(m / 60 / 24)} d ago`

/** The gap between the rail and its card, and the least room kept from the
 *  window's edges. */
const GAP = 10
const EDGE = 8
const CARD_W = 300
const CARD_PAD = 8

export interface Placed { left: number; top: number; width: number; toward: 'right' | 'left' }

/** Where a rail's card goes, given the rail's box, the card's natural height
 *  and the window. Prefers the side away from the rail's own edge (a left
 *  rail opens rightward); flips when that side lacks room and the other has
 *  more; narrows to fit whichever side it takes. Vertically it starts level
 *  with the rail (so rows sit beside their bars) and slides only as far as
 *  needed to stay inside the window. */
export function placeCard(rail: DOMRect, height: number, vw: number, vh: number, side: 'left' | 'right', cardW = CARD_W, minTop = EDGE): Placed {
  const roomRight = vw - rail.right - GAP - EDGE
  const roomLeft = rail.left - GAP - EDGE
  const prefer = side === 'left' ? 'right' : 'left'
  const preferred = prefer === 'right' ? roomRight : roomLeft
  const other = prefer === 'right' ? roomLeft : roomRight
  const toward = preferred >= Math.min(cardW, 200) || preferred >= other ? prefer : (prefer === 'right' ? 'left' : 'right')
  const room = Math.max(toward === 'right' ? roomRight : roomLeft, 0)
  /* never wider than the window allows, however little room either side has */
  const width = Math.max(Math.min(cardW, room, vw - 2 * EDGE), Math.min(160, vw - 2 * EDGE))
  let left = toward === 'right' ? rail.right + GAP : rail.left - GAP - width
  left = Math.min(Math.max(left, EDGE), vw - EDGE - width)
  let top = rail.top - CARD_PAD
  top = Math.min(Math.max(top, minTop), Math.max(minTop, vh - EDGE - height))
  return { left, top, width, toward }
}

/** What a rail's own card is given when it draws something of its own (the
 *  conversation list): how to close it, how to keep it open while a menu or
 *  an edit is open in it, and a count bumped to move focus into it. */
export interface CardControl { close: (refocus: boolean) => void; hold: (held: boolean) => void; focusInto: number }

/** how long a card of its own waits after the pointer leaves before closing */
const LEAVE_MS = 160

export default function Markers({ label, items, current, side, onPick, onBeside, onLatest, onMore, moreOpen, onNew, newLabel, prefix = '', card: renderCard, cardWidth, openSignal = 0 }: {
  label: string
  items: MarkerItem[]
  current: string | null
  side: 'left' | 'right'
  onPick: (key: string) => void
  /** opens the item in a working surface, where there is one */
  onBeside?: (key: string) => void
  /** goes straight to the item's newest post (a conversation's) */
  onLatest?: (key: string) => void
  /** THE CHEVRON at the rail's end: opens every item (Discover.tsx) */
  onMore?: () => void
  moreOpen?: boolean
  /** THE + ABOVE THE RAIL: starts a new item (a conversation), the way the
   *  full list's New does; absent where nothing may be written */
  onNew?: () => void
  /** its accessible name and title */
  newLabel?: string
  prefix?: string
  /** THE CARD'S OWN CONTENT, interactive (the conversation list), in place
   *  of the names. With it, Enter on a bar and the chevron go into the card,
   *  and a tap on touch opens it rather than choosing. */
  card?: (ctl: CardControl) => React.ReactNode
  cardWidth?: number
  /** bumped to open the card with focus in it (back from the Danger Zone) */
  openSignal?: number
}) {
  const [open, setOpen] = useState(false)
  const [hot, setHot] = useState<string | null>(null)
  const [placed, setPlaced] = useState<Placed | null>(null)
  const rail = useRef<HTMLUListElement>(null)
  const card = useRef<HTMLDivElement>(null)
  const closing = useRef<number | null>(null)
  const nav = useRef<HTMLElement>(null)
  /* a menu or an edit is open in a card of its own: it stays */
  const held = useRef(false)
  const hold = useCallback((h: boolean) => { held.current = h }, [])
  const [focusInto, setFocusInto] = useState(0)
  /* the rail control focus goes back to when the card closes by key */
  const opener = useRef<HTMLElement | null>(null)
  /* the last press was a touch: a tap on a bar opens the card */
  const touch = useRef(false)
  /* focus given back to the rail by Esc does not open the card again */
  const quiet = useRef(false)

  useLayoutEffect(() => {
    if (!open) { setPlaced(null); return }
    const place = () => {
      if (!rail.current || !card.current) return
      /* a card of its own stays below the page's top line */
      const below = renderCard && nav.current ? nav.current.getBoundingClientRect().top + EDGE : EDGE
      setPlaced(placeCard(rail.current.getBoundingClientRect(), card.current.offsetHeight, window.innerWidth, window.innerHeight, side, cardWidth, below))
    }
    place()
    window.addEventListener('resize', place)
    /* a card of its own grows as it is read: placed again as it does */
    const ro = renderCard && card.current ? new ResizeObserver(place) : null
    if (ro && card.current) ro.observe(card.current)
    return () => { window.removeEventListener('resize', place); ro?.disconnect() }
  }, [open, side, cardWidth, !!renderCard]) // eslint-disable-line react-hooks/exhaustive-deps

  const shut = useCallback((refocus: boolean) => {
    held.current = false
    setOpen(false); setHot(null)
    if (refocus && opener.current?.isConnected) { quiet.current = true; opener.current.focus(); quiet.current = false }
    else if (nav.current?.contains(document.activeElement)) (document.activeElement as HTMLElement).blur()
  }, [])
  const into = () => { setOpen(true); setFocusInto((n) => n + 1) }
  useEffect(() => { if (openSignal) into() }, [openSignal]) // eslint-disable-line react-hooks/exhaustive-deps

  /* a press outside the rail and its card closes a card of its own */
  useEffect(() => {
    if (!open || !renderCard) return
    const away = (e: PointerEvent) => {
      const t = e.target as Element
      if (nav.current?.contains(t) || t.closest?.('.q2-danger-veil')) return
      shut(false)
    }
    document.addEventListener('pointerdown', away)
    return () => document.removeEventListener('pointerdown', away)
  }, [open, renderCard, shut])

  /* the card and the rail are one target: moving between them keeps it open */
  const enter = () => { if (closing.current) { clearTimeout(closing.current); closing.current = null } setOpen(true) }
  const leave = () => {
    if (closing.current) clearTimeout(closing.current)
    closing.current = window.setTimeout(() => {
      closing.current = null
      /* a card of its own stays while a menu or edit is open, or focus is in it */
      if (renderCard && (held.current || card.current?.contains(document.activeElement))) return
      setOpen(false); setHot(null)
    }, renderCard ? LEAVE_MS : 120)
  }

  return (
    <nav ref={nav} className={`q2-markers q2-markers-${side}` + (open ? ' open' : '')} aria-label={label}
      onMouseEnter={enter} onMouseLeave={leave}
      onFocus={(e) => {
        if (quiet.current) return
        if (renderCard && !card.current?.contains(e.target as Node)) opener.current = e.target as HTMLElement
        enter()
      }}
      onPointerDown={(e) => { touch.current = e.pointerType === 'touch' }}
      onBlur={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node) && !(renderCard && held.current)) { setOpen(false); setHot(null) } }}
      onKeyDown={(e) => {
        if (e.key !== 'Escape' || e.defaultPrevented) return
        if (renderCard) { e.preventDefault(); shut(true) } else { setOpen(false); (document.activeElement as HTMLElement | null)?.blur() }
      }}>
      <ul ref={rail}>
        {onNew && (
          <li>
            <button className="q2-rail-new" title={newLabel} aria-label={newLabel}
              onMouseEnter={() => { setOpen(false); setHot(null) }}
              onFocus={(e) => { e.stopPropagation(); setOpen(false); setHot(null) }}
              onClick={() => { setOpen(false); setHot(null); onNew() }}>
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" aria-hidden="true"><path d="M6 1.5v9M1.5 6h9" /></svg>
            </button>
          </li>
        )}
        {items.map((it) => (
          <li key={it.key}>
            <button className={'q2-marker' + (it.key === current ? ' current' : '') + (it.key === hot ? ' hot' : '')}
              aria-current={it.key === current ? 'true' : undefined}
              onMouseEnter={() => setHot(it.key)} onFocus={() => setHot(it.key)}
              onKeyDown={renderCard ? (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); opener.current = e.currentTarget; into() } } : undefined}
              onClick={(e) => {
                /* a tap on touch opens the card; a click chooses, as before */
                if (renderCard && touch.current) { e.preventDefault(); opener.current = e.currentTarget; into(); return }
                if (e.shiftKey && onBeside && it.key !== current) onBeside(it.key); else onPick(it.key)
              }}
              aria-description={onBeside && it.key !== current ? 'Shift+Enter opens it in a working surface' : undefined}
              aria-label={`${prefix}${it.name}, ${it.count} posts, active ${ago(it.idle)}`}>
              <span className="q2-bar" style={{ width: lengthOf(it.count), height: thicknessOf(it.idle) }} />
            </button>
          </li>
        ))}
        {(onMore || renderCard) && (
          <li>
            <button className="q2-rail-more" aria-haspopup="dialog" aria-expanded={renderCard ? open : !!moreOpen} title={`Every ${label.toLowerCase()}`} aria-label={`Show every one of the ${label.toLowerCase()}`}
              onMouseEnter={renderCard ? undefined : () => { setOpen(false); setHot(null) }}
              onClick={(e) => {
                if (renderCard) { opener.current = e.currentTarget; into(); return }
                setOpen(false); setHot(null); onMore?.()
              }}>
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.4" aria-hidden="true"><path d={side === 'left' ? 'M4.5 2.5 8 6l-3.5 3.5' : 'M7.5 2.5 4 6l3.5 3.5'} /></svg>
            </button>
          </li>
        )}
      </ul>
      {open && renderCard && (
        <div ref={card} className={'q2-marker-card q2-cl-card toward-' + (placed?.toward ?? (side === 'left' ? 'right' : 'left'))}
          role="dialog" aria-label={label}
          style={placed ? { left: placed.left, top: placed.top, width: placed.width } : { visibility: 'hidden', left: 0, top: 0, width: cardWidth ?? CARD_W }}>
          {renderCard({ close: shut, hold, focusInto })}
        </div>
      )}
      {open && !renderCard && !moreOpen && (
        <div ref={card} className={'q2-marker-card toward-' + (placed?.toward ?? (side === 'left' ? 'right' : 'left'))} aria-hidden="true"
          style={placed ? { left: placed.left, top: placed.top, width: placed.width } : { visibility: 'hidden', left: 0, top: 0, width: CARD_W }}>
          <ul>
            {items.map((it) => (
              <li key={it.key} className={(it.key === current ? 'current' : '') + (it.key === hot ? ' hot' : '')}
                onMouseEnter={() => setHot(it.key)} onClick={() => onPick(it.key)}>
                {/* the name first; what it holds and when, quieter, under it */}
                <span className="q2-marker-text">
                  <span className="q2-marker-name">{prefix}{it.name}</span>
                  <span className="q2-marker-meta">{it.count} {it.count === 1 ? 'post' : 'posts'} · {ago(it.idle)}</span>
                </span>
                {onLatest && (
                  <button className="q2-latest-of" tabIndex={-1} title={`Go to the newest post in ${prefix}${it.name}`} aria-label={`Go to the newest post in ${prefix}${it.name}`}
                    onClick={(e) => { e.stopPropagation(); setOpen(false); setHot(null); onLatest(it.key) }}><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 5v14M6 13l6 6 6-6" /></svg></button>
                )}
                {onBeside && it.key !== current && (
                  <button className="q2-marker-beside" tabIndex={-1} title={`Open ${prefix}${it.name} in a working surface`} aria-label={`Open ${prefix}${it.name} in a working surface`}
                    onClick={(e) => { e.stopPropagation(); onBeside(it.key) }}>⇥</button>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </nav>
  )
}
