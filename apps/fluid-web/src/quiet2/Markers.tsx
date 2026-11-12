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
import { useLayoutEffect, useRef, useState } from 'react'
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
export function placeCard(rail: DOMRect, height: number, vw: number, vh: number, side: 'left' | 'right'): Placed {
  const roomRight = vw - rail.right - GAP - EDGE
  const roomLeft = rail.left - GAP - EDGE
  const prefer = side === 'left' ? 'right' : 'left'
  const preferred = prefer === 'right' ? roomRight : roomLeft
  const other = prefer === 'right' ? roomLeft : roomRight
  const toward = preferred >= Math.min(CARD_W, 200) || preferred >= other ? prefer : (prefer === 'right' ? 'left' : 'right')
  const room = Math.max(toward === 'right' ? roomRight : roomLeft, 0)
  /* never wider than the window allows, however little room either side has */
  const width = Math.max(Math.min(CARD_W, room, vw - 2 * EDGE), Math.min(160, vw - 2 * EDGE))
  let left = toward === 'right' ? rail.right + GAP : rail.left - GAP - width
  left = Math.min(Math.max(left, EDGE), vw - EDGE - width)
  let top = rail.top - CARD_PAD
  top = Math.min(Math.max(top, EDGE), Math.max(EDGE, vh - EDGE - height))
  return { left, top, width, toward }
}

export default function Markers({ label, items, current, side, onPick, onBeside, onMore, moreOpen, onNew, newLabel, prefix = '' }: {
  label: string
  items: MarkerItem[]
  current: string | null
  side: 'left' | 'right'
  onPick: (key: string) => void
  /** opens the item in a working surface, where there is one */
  onBeside?: (key: string) => void
  /** THE CHEVRON at the rail's end: opens every item (Discover.tsx) */
  onMore?: () => void
  moreOpen?: boolean
  /** THE + ABOVE THE RAIL: starts a new item (a conversation), the way the
   *  full list's New does; absent where nothing may be written */
  onNew?: () => void
  /** its accessible name and title */
  newLabel?: string
  prefix?: string
}) {
  const [open, setOpen] = useState(false)
  const [hot, setHot] = useState<string | null>(null)
  const [placed, setPlaced] = useState<Placed | null>(null)
  const rail = useRef<HTMLUListElement>(null)
  const card = useRef<HTMLDivElement>(null)
  const closing = useRef<number | null>(null)

  useLayoutEffect(() => {
    if (!open) { setPlaced(null); return }
    const place = () => {
      if (!rail.current || !card.current) return
      setPlaced(placeCard(rail.current.getBoundingClientRect(), card.current.offsetHeight, window.innerWidth, window.innerHeight, side))
    }
    place()
    window.addEventListener('resize', place)
    return () => window.removeEventListener('resize', place)
  }, [open, side])

  /* the card and the rail are one target: moving between them keeps it open */
  const enter = () => { if (closing.current) { clearTimeout(closing.current); closing.current = null } setOpen(true) }
  const leave = () => { closing.current = window.setTimeout(() => { setOpen(false); setHot(null) }, 120) }

  return (
    <nav className={`q2-markers q2-markers-${side}` + (open ? ' open' : '')} aria-label={label}
      onMouseEnter={enter} onMouseLeave={leave}
      onFocus={enter}
      onBlur={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node)) { setOpen(false); setHot(null) } }}
      onKeyDown={(e) => { if (e.key === 'Escape') { setOpen(false); (document.activeElement as HTMLElement | null)?.blur() } }}>
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
              onClick={(e) => { if (e.shiftKey && onBeside && it.key !== current) onBeside(it.key); else onPick(it.key) }}
              aria-description={onBeside && it.key !== current ? 'Shift+Enter opens it in a working surface' : undefined}
              aria-label={`${prefix}${it.name}, ${it.count} posts, active ${ago(it.idle)}`}>
              <span className="q2-bar" style={{ width: lengthOf(it.count), height: thicknessOf(it.idle) }} />
            </button>
          </li>
        ))}
        {onMore && (
          <li>
            <button className="q2-rail-more" aria-haspopup="dialog" aria-expanded={!!moreOpen} title={`Every ${label.toLowerCase()}`} aria-label={`Show every one of the ${label.toLowerCase()}`}
              onMouseEnter={() => { setOpen(false); setHot(null) }}
              onClick={() => { setOpen(false); setHot(null); onMore() }}>
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.4" aria-hidden="true"><path d={side === 'left' ? 'M4.5 2.5 8 6l-3.5 3.5' : 'M7.5 2.5 4 6l3.5 3.5'} /></svg>
            </button>
          </li>
        )}
      </ul>
      {open && !moreOpen && (
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
