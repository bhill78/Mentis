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
  /** names the group for a composed layout (data-group); default: its title, lower-cased */
  id?: string
  /** a short heading word; omit for an unheaded row */
  title?: string
  items?: IconItem[]
  /** a control drawn across the column instead of (or after) the icons */
  body?: ReactNode
  /** accordion: the row's icon, and what it is set to now (default: the
   *  labels of its pressed items) */
  icon?: ReactNode
  summary?: string
  /** accordion: always open, above the folding rows (the frequent controls) */
  pinned?: boolean
  /** accordion: smaller headed sets shown inside the open row (no deeper level) */
  sub?: IconGroup[]
}

/* An accordion row's icon when the group gives none. */
const ROW_ICON: Record<string, string> = {
  content: '▤', present: '▦', look: '◐', arrange: '⊞', focus: '⛶', theme: '☼', background: '▧',
  surfaces: '◫', surface: '◫', opening: '⧉', thread: '↳', reading: '≡', more: '⋯',
}

/** `layout`: 'flow' (default) wraps columns; 'grid2' sets them two by two;
 *  'settings' is a composed panel; 'accordion' (owner, 2026-10-28: "configuration
 *  revealed as needed rather than displayed all at once") shows `pinned`
 *  groups open, then one folding row per other group (icon, name, what it is
 *  set to), one open at a time. */
export function IconMenu({ groups, label, onDone, layout = 'flow', open: first = null }: { groups: IconGroup[]; label: string; onDone?: () => void; layout?: 'flow' | 'grid2' | 'settings' | 'accordion'; open?: string | null }) {
  const [trail, setTrail] = useState<{ title: string; groups: IconGroup[] }[]>([])
  const [openRow, setOpenRow] = useState<string | null>(first)
  const shown = trail.length ? trail[trail.length - 1] : null
  const now = shown?.groups ?? groups
  const keyOf = (g: IconGroup, gi: number) => g.id ?? (g.title ? g.title.toLowerCase().replace(/[^a-z]+/g, '-') : 'g' + gi)
  const items = (g: IconGroup) => !!g.items?.length && (
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
  )
  if (layout === 'accordion' && !shown) {
    const pinned = now.filter((g) => g.pinned)
    const rows = now.filter((g) => !g.pinned)
    return (
      <div className="im im-accordion" role="menu" aria-label={label}>
        {!!pinned.length && <div className="im-pinned">
          {pinned.map((g, gi) => (
            <section key={keyOf(g, gi)} className="im-col" aria-label={g.title} data-group={keyOf(g, gi)}>
              {g.title && <h4 className="im-head">{g.title}</h4>}
              {items(g)}
              {g.body && <div className="im-body">{g.body}</div>}
            </section>
          ))}
        </div>}
        <div className="im-rows">
          {rows.map((g, gi) => {
            const k = keyOf(g, gi)
            const on = openRow === k
            const summary = g.summary ?? (g.items ?? []).filter((it) => it.on).map((it) => it.label).join(' · ')
            return (
              <section key={k} className={'im-row' + (on ? ' open' : '')} data-group={k}>
                <button type="button" className="im-rowhead" aria-expanded={on} aria-controls={`im-${k}`}
                  onClick={() => setOpenRow(on ? null : k)}>
                  <span className="im-rowicon" aria-hidden="true">{g.icon ?? ROW_ICON[k] ?? '•'}</span>
                  <span className="im-rowname">{g.title}</span>
                  <span className="im-rowsum">{summary}</span>
                  <span className="im-rowcaret" aria-hidden="true">▸</span>
                </button>
                {on && <div className="im-rowbody" id={`im-${k}`}>
                  {(g.sub ?? []).map((sg, si) => (
                    <div key={(sg.title ?? '') + si} className="im-sub">
                      {sg.title && <h5 className="im-subhead">{sg.title}</h5>}
                      {items(sg)}
                      {sg.body && <div className="im-body">{sg.body}</div>}
                    </div>
                  ))}
                  {items(g)}
                  {g.body && <div className="im-body">{g.body}</div>}
                </div>}
              </section>
            )
          })}
        </div>
      </div>
    )
  }
  return (
    <div className={'im im-' + layout} role="menu" aria-label={shown ? `${label}: ${shown.title}` : label}>
      {shown && (
        <button type="button" className="im-back" onClick={() => setTrail((t) => t.slice(0, -1))} aria-label="Back">
          <span aria-hidden="true">‹</span> {shown.title}
        </button>
      )}
      <div className="im-cols">
        {now.map((g, gi) => (
          <section key={(g.title ?? '') + gi} className="im-col" aria-label={g.title} data-group={g.id ?? (g.title ?? '').toLowerCase().replace(/[^a-z]+/g, '-')}>
            {g.title && <h4 className="im-head">{g.title}</h4>}
            {items(g)}
            {g.body && <div className="im-body">{g.body}</div>}
          </section>
        ))}
      </div>
    </div>
  )
}

/** The Settings gear, the same everywhere (the bar's Settings, a section's,
 *  a window's). */
export const GearMark = () => (
  <svg width="16" height="16" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <circle cx="10" cy="10" r="2.6" />
    <path d="M10 2.5v2M10 15.5v2M2.5 10h2M15.5 10h2M4.7 4.7l1.4 1.4M13.9 13.9l1.4 1.4M4.7 15.3l1.4-1.4M13.9 6.1l1.4-1.4" />
    <circle cx="10" cy="10" r="5.2" />
  </svg>
)
