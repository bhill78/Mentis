/* THE ONE OBJECT ACTION ROW (objects/actions.ts): Open · Peek · Float · Keep
 * · ◎ · ⛶. Icons first, words in the tooltip and for screen readers. Every
 * origin draws this component; none draws its own buttons for these actions.
 *
 * `only` narrows the row where an action makes no sense (a float header has
 * no Float); `compact` drops to icons with no gaps for a dense line; `onAct`
 * lets a host that would be in the way (Peek) step aside before the action
 * runs, and is handed the action to run. `onOpen` is a place's own way of
 * opening what it shows (a section's cards open as that section opens them,
 * a search hit is read in its context): Open there does that, as a click on
 * the thing itself does. */

import type { MouseEvent } from 'react'
import { act, ACTION_LOOK, ACTION_ORDER, type ObjectAction, type ObjectTarget } from './actions'
import { FocusSplit } from '../focus/FocusSplit'
import './objects.css'

export function ObjectActions({ target, only, compact, className, onAct, onOpen }: {
  target: ObjectTarget
  only?: ObjectAction[]
  compact?: boolean
  className?: string
  onAct?: (action: ObjectAction, run: () => void) => void
  onOpen?: (t: ObjectTarget) => void
}) {
  const shown = ACTION_ORDER.filter((a) => !only || only.includes(a))
  const run = (a: ObjectAction) => (e: MouseEvent<HTMLButtonElement>) => {
    e.stopPropagation()
    const t = { ...target, anchor: target.anchor ?? (e.currentTarget.closest('[data-address], .rb-card, [data-post]') as HTMLElement | null) ?? e.currentTarget }
    const go = a === 'open' && onOpen ? () => onOpen(t) : () => act[a](t)
    if (onAct) onAct(a, go)
    else go()
  }
  return (
    <span className={'ob-acts' + (compact ? ' ob-compact' : '') + (className ? ' ' + className : '')} role="group" aria-label={`Actions for ${target.title ?? 'this object'}`}>
      {shown.map((a) => a === 'focus'
        ? <FocusSplit key={a} target={target} onAct={onAct && ((run) => onAct('focus', run))} />
        : (
          <button key={a} type="button" className="ob-act" data-act={a} onClick={run(a)}
            title={ACTION_LOOK[a].says + (ACTION_LOOK[a].key ? ` (${ACTION_LOOK[a].key})` : '')} aria-label={`${ACTION_LOOK[a].label} ${target.title ?? ''}`.trim()}>
            <span aria-hidden="true">{ACTION_LOOK[a].icon}</span>
          </button>
        ))}
    </span>
  )
}
