/* ONE KIND OF MENU: ICONS IN COLUMNS, WITH TIERS (owner, 2026-10-28: "use more
 * icons than words; a tiered menu or a menu with multiple columns, not giant
 * vertical menus -- those only help on mobile").
 *
 * The content of a menu, drawn inside the frame's anchored Sheet (or any
 * panel). Each group is a column headed by a short word; each item is an icon
 * with a one-word label under it and its full meaning in the tooltip. An item
 * with `tier` opens that tier in place (‹ goes back); an item with `body`
 * draws a small control of its own (a slider, a picker) across the column.
 * At phone width the columns stack and the labels stay. Every window menu,
 * the Settings panel and the Look column use this, so they read alike. */

import { useState, type ReactNode } from 'react'
import './iconMenu.css'

export interface IconItem {
  id: string
  /** one glyph or a small inline SVG */
  icon: ReactNode
  /** one word, under the icon */
  label: string
  /** the full meaning, in the tooltip and for screen readers */
  says: string
  onPick?: () => void
  /** pressed / current */
  on?: boolean
  /** not available now, with why */
  off?: boolean
  why?: string
  /** a deeper tier opened in place */
  tier?: IconGroup[]
}

export interface IconGroup {
  /** a short heading word; omit for an unheaded row */
  title?: string
  items?: IconItem[]
  /** a control drawn across the column instead of (or after) the icons */
  body?: ReactNode
}

export function IconMenu({ groups, label, onDone }: { groups: IconGroup[]; label: string; onDone?: () => void }) {
  const [trail, setTrail] = useState<{ title: string; groups: IconGroup[] }[]>([])
  const shown = trail.length ? trail[trail.length - 1] : null
  const now = shown?.groups ?? groups
  return (
    <div className="im" role="menu" aria-label={shown ? `${label}: ${shown.title}` : label}>
      {shown && (
        <button type="button" className="im-back" onClick={() => setTrail((t) => t.slice(0, -1))} aria-label="Back">
          <span aria-hidden="true">‹</span> {shown.title}
        </button>
      )}
      <div className="im-cols">
        {now.map((g, gi) => (
          <section key={(g.title ?? '') + gi} className="im-col" aria-label={g.title}>
            {g.title && <h4 className="im-head">{g.title}</h4>}
            {!!g.items?.length && (
              <div className="im-items">
                {g.items.map((it) => (
                  <button key={it.id} type="button" role="menuitem" className={'im-item' + (it.on ? ' on' : '')}
                    data-item={it.id} aria-pressed={it.on || undefined} aria-disabled={it.off || undefined}
                    title={it.off && it.why ? `${it.says} (${it.why})` : it.says} aria-label={it.says}
                    onClick={() => {
                      if (it.off) return
                      if (it.tier) { setTrail((t) => [...t, { title: it.label, groups: it.tier! }]); return }
                      it.onPick?.()
                      onDone?.()
                    }}>
                    <span className="im-icon" aria-hidden="true">{it.icon}</span>
                    <span className="im-label">{it.label}{it.tier ? ' ›' : ''}</span>
                  </button>
                ))}
              </div>
            )}
            {g.body && <div className="im-body">{g.body}</div>}
          </section>
        ))}
      </div>
    </div>
  )
}
