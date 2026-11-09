/* STEPPED MARKERS: navigation without a panel.
 *
 * One short bar per conversation (or topic). Two dimensions, kept apart:
 *  - LENGTH is how much material there is, in four steps, never proportional,
 *    so a conversation of hundreds of posts is still only the longest step.
 *  - THICKNESS is how recently anything happened there.
 * At rest only the bars show. Hovering or focusing the stack opens the names
 * beside them, as a card that floats over the margin and reserves nothing.
 *
 * ROUND 1 THRESHOLDS, FOR REVIEW: they are here to be argued with, not
 * settled semantics. */
import { useState } from 'react'
import type { MarkerItem } from './sample'

/** Four discrete lengths, the longest about 30px. */
export const LENGTHS = [8, 14, 22, 30] as const
const LENGTH_AT = [10, 40, 150] // posts: <10, <40, <150, 150+

/** Thickness by recency: within the hour, today, this week, older. */
export const THICKNESS = [4, 3, 2, 1] as const
const RECENT_AT = [60, 60 * 24, 60 * 24 * 7] // minutes idle

export const lengthOf = (count: number) => LENGTHS[LENGTH_AT.filter((n) => count >= n).length]
export const thicknessOf = (idle: number) => THICKNESS[RECENT_AT.filter((n) => idle >= n).length]

const ago = (m: number) => m < 60 ? `${m} min ago` : m < 60 * 24 ? `${Math.round(m / 60)} h ago` : `${Math.round(m / 60 / 24)} d ago`

export default function Markers({ label, items, current, side, onPick, prefix = '' }: {
  label: string
  items: MarkerItem[]
  current: string | null
  side: 'left' | 'right'
  onPick: (key: string) => void
  prefix?: string
}) {
  const [open, setOpen] = useState(false)
  return (
    <nav className={`q2-markers q2-markers-${side}` + (open ? ' open' : '')} aria-label={label}
      onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node)) setOpen(false) }}>
      <ul>
        {items.map((it) => (
          <li key={it.key}>
            <button className={'q2-marker' + (it.key === current ? ' current' : '')} aria-current={it.key === current ? 'true' : undefined}
              onClick={() => onPick(it.key)}
              aria-label={`${prefix}${it.name}, ${it.count} posts, active ${ago(it.idle)}`}>
              <span className="q2-bar" style={{ width: lengthOf(it.count), height: thicknessOf(it.idle) }} />
              <span className="q2-marker-name" aria-hidden="true">
                <span>{prefix}{it.name}</span>
                <span className="q2-marker-meta">{it.count} · {ago(it.idle)}</span>
              </span>
            </button>
          </li>
        ))}
      </ul>
    </nav>
  )
}
