/* THE SPLIT FOCUS CONTROL (owner's brief §3): ⛶ focuses at once in the
 * remembered presentation (or the one already on); ▾ beside it offers
 * Docked / Floating / Mixed / Only Focus by icon, and choosing one focuses
 * in it and remembers it. The words are in the tooltips.
 *
 * Two kinds of target: an object (`target`, through objects/actions.ts, so
 * every origin focuses the same way) or a surface already on the Page
 * (`surface`: a docked section, the column, a window), focused by its
 * content id. With Focus on, either one SWITCHES: the new content takes the
 * same Focus area. `onAct` lets a host that is itself in the way (Peek)
 * step aside first. */

import { useEffect, useRef, useState, type MouseEvent } from 'react'
import { act, ACTION_LOOK, type ObjectTarget } from '../objects/actions'
import { lens, PRESENTATIONS, rememberPresentation, rememberedPresentation, type FocusPresentation } from './lens'

export function FocusSplit({ target, surface, onAct, className }: {
  target?: ObjectTarget
  surface?: { id: string; title?: string }
  onAct?: (run: () => void) => void
  className?: string
}) {
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLSpanElement | null>(null)
  useEffect(() => {
    if (!open) return
    const away = (e: PointerEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false) }
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') { e.stopPropagation(); setOpen(false) } }
    document.addEventListener('pointerdown', away, true)
    box.current?.addEventListener('keydown', esc)
    const el = box.current
    return () => { document.removeEventListener('pointerdown', away, true); el?.removeEventListener('keydown', esc) }
  }, [open])
  const go = (e: MouseEvent<HTMLElement>, p?: FocusPresentation) => {
    e.stopPropagation()
    setOpen(false)
    const anchor = target?.anchor ?? (e.currentTarget.closest('[data-address]') as HTMLElement | null)
    const run = () => {
      if (p) rememberPresentation(p)
      if (surface) lens.enter({ kind: 'surface', id: surface.id, title: surface.title }, p)
      else if (target) {
        act.focus({ ...target, anchor })
        if (p && lens.current()) lens.setPresentation(p)
      }
    }
    if (onAct) onAct(run)
    else run()
  }
  const on = lens.current()
  const now = PRESENTATIONS.find((p) => p.id === (on?.presentation ?? rememberedPresentation()))
  const name = surface?.title ?? target?.title ?? ''
  const says = on ? `Focus on ${name || 'this'} instead: it takes the same Focus area` : `${ACTION_LOOK.focus.says} · ${now?.label ?? ''}`
  return (
    <span ref={box} className={'ob-focus' + (className ? ' ' + className : '')} data-act="focus">
      <button type="button" className="ob-act" onClick={(e) => go(e)}
        title={`${says} (${ACTION_LOOK.focus.key})`} aria-label={`Focus ${name}`.trim()}>
        <span aria-hidden="true">{ACTION_LOOK.focus.icon}</span>
      </button>
      <button type="button" className="ob-act ob-more" aria-haspopup="menu" aria-expanded={open}
        title="Focus in a presentation you choose" aria-label="Focus presentation" onClick={(e) => { e.stopPropagation(); setOpen((x) => !x) }}>▾</button>
      {open && (
        <span className="ob-menu ob-menu-icons" role="menu" aria-label="Focus presentation">
          {PRESENTATIONS.map((p) => (
            <button key={p.id} type="button" role="menuitemradio" aria-checked={p.id === now?.id} title={`${p.label}: ${p.says}`}
              aria-label={p.label} onClick={(e) => go(e, p.id)}>
              <span aria-hidden="true">{p.icon}</span>
            </button>
          ))}
        </span>
      )}
    </span>
  )
}
