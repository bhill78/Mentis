/* THE SPLIT FOCUS CONTROL (owner's brief §3): ⛶ uses the last presentation at
 * once; ▾ beside it offers Docked / Floating / Mixed / Only Focus by icon, and
 * choosing one focuses in it and remembers it. SHARED INTERFACE: the Focus
 * workstream owns the finished look and behaviour; this first version already
 * works through objects/actions.ts and focus/lens.ts. */

import { useState, type MouseEvent } from 'react'
import { act, ACTION_LOOK, type ObjectTarget } from '../objects/actions'
import { PRESENTATIONS, rememberPresentation, rememberedPresentation, type FocusPresentation } from './lens'

export function FocusSplit({ target }: { target: ObjectTarget }) {
  const [open, setOpen] = useState(false)
  const go = (e: MouseEvent<HTMLElement>, p?: FocusPresentation) => {
    e.stopPropagation()
    if (p) rememberPresentation(p)
    setOpen(false)
    act.focus({ ...target, anchor: target.anchor ?? (e.currentTarget.closest('[data-address]') as HTMLElement | null) })
  }
  const now = PRESENTATIONS.find((p) => p.id === rememberedPresentation())
  return (
    <span className="ob-focus" data-act="focus">
      <button type="button" className="ob-act" onClick={(e) => go(e)}
        title={`${ACTION_LOOK.focus.says} · ${now?.label ?? ''} (${ACTION_LOOK.focus.key})`} aria-label={`Focus ${target.title ?? ''}`.trim()}>
        <span aria-hidden="true">{ACTION_LOOK.focus.icon}</span>
      </button>
      <button type="button" className="ob-act ob-more" aria-haspopup="menu" aria-expanded={open}
        title="Choose how Focus is presented" aria-label="Focus presentation" onClick={(e) => { e.stopPropagation(); setOpen((x) => !x) }}>▾</button>
      {open && (
        <span className="ob-menu" role="menu">
          {PRESENTATIONS.map((p) => (
            <button key={p.id} type="button" role="menuitemradio" aria-checked={p.id === now?.id} title={p.says} onClick={(e) => go(e, p.id)}>
              <span aria-hidden="true">{p.icon}</span> {p.label}
            </button>
          ))}
        </span>
      )}
    </span>
  )
}
