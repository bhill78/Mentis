/* T1, T2 AND T3: THE ACTION BAR, THE ACTION MENU AND THE FIND-AN-ACTION
 * PALETTE (rev 3 §5; plan §3.5–§3.6; part P3).
 *
 * Three renderers of one list. ActionMenu (T2) draws registry.list in the
 * fixed groups, every available action including those in T1, disabled ones
 * with their reason beside them, and "Find an action…" last. ActionBar (T1)
 * draws registry.primary within a budget. ActionPalette (T3) is the same
 * list, narrowed by label and old words, opened by Ctrl/⌘+K or by Find an
 * action…. Each runs only registry.run. P4's SurfaceChrome places them. */

import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react'
import { createPortal } from 'react-dom'
import { ACTION_GROUPS, type ActionCtx, type ActionGroup, type ActionId, type ActionTarget } from './types'
import { isFindActionKey, paletteList, registry, type Listed } from './registry'
import { aimed, closePalette, openPalette, paletteOpen, subscribePalette } from './paletteStore'
import { saysOf } from './words'
import { ESC, onEscape } from '../../escape'
import './actions.css'

export const GROUP_WORD: Record<ActionGroup, string> = {
  resource: 'Resource', view: 'View', arrange: 'Arrange', look: 'Look', share: 'Share', details: 'Details',
}

const runIt = (id: ActionId, target: ActionTarget, ctx: ActionCtx, done?: () => void) => {
  done?.()
  void registry.run(id, target, ctx).catch((e: Error) => console.warn(`${id}: ${e.message}`))
}

/** One row: glyph, label, shortcut, and why not, when it is disabled. */
function Row({ x, onPick, active }: { x: Listed; onPick: () => void; active?: boolean }) {
  const { def, availability: a } = x
  const why = a.state === 'disabled' ? a.reason.message : null
  return (
    <button type="button" role="menuitem" className={'am-row' + (active ? ' on' : '')} data-action={def.id}
      aria-disabled={why ? true : undefined} title={saysOf(def.id)} onClick={() => { if (!why) onPick() }}>
      <span className="am-glyph" aria-hidden="true">{def.glyph}</span>
      <span className="am-label">{def.label}</span>
      {def.shortcut && <kbd className="am-key">{def.shortcut}</kbd>}
      {why && <small className="am-why">{why}</small>}
    </button>
  )
}

/** T2: every action for `target`, in the fixed groups; "Find an action…" last. */
export function ActionMenu({ target, ctx, label, onDone }: { target: ActionTarget; ctx: ActionCtx; label: string; onDone?: () => void }) {
  const rows = registry.list(target, ctx)
  const find = rows.find((x) => x.def.id === 'findAction')
  const groups = ACTION_GROUPS.map((g) => ({ g, rows: rows.filter((x) => x.def.group === g && x !== find) })).filter((x) => x.rows.length)
  return (
    <div className="am" role="menu" aria-label={label}>
      {groups.map(({ g, rows: rs }) => (
        <section key={g} className="am-group" data-group={g} aria-label={GROUP_WORD[g]}>
          <h4 className="am-head">{GROUP_WORD[g]}</h4>
          {rs.map((x) => <Row key={x.def.id} x={x} onPick={() => runIt(x.def.id, target, ctx, onDone)} />)}
        </section>
      ))}
      {find && <div className="am-find"><Row x={find} onPick={() => runIt(find.def.id, target, ctx, onDone)} /></div>}
    </div>
  )
}

/** T1: the lead action, then the host's shared verbs, within `budget`. */
export function ActionBar({ target, ctx, budget }: { target: ActionTarget; ctx: ActionCtx; budget: number }) {
  const defs = registry.primary(target, ctx, budget)
  return (
    <span className="am-bar" role="toolbar">
      {defs.map((d) => (
        <button key={d.id} type="button" className="am-t1" data-action={d.id} aria-label={d.label} title={saysOf(d.id)}
          onClick={(e) => { e.stopPropagation(); runIt(d.id, target, ctx) }}>
          <span aria-hidden="true">{d.glyph}</span>
        </button>
      ))}
    </span>
  )
}

/** T3: the palette, mounted once by the shell. Ctrl/⌘+K opens it on what is
 *  aimed at (paletteStore); plain "/" stays the bar's resource search. */
export function ActionPalette() {
  const at = useSyncExternalStore(subscribePalette, paletteOpen)
  const [q, setQ] = useState('')
  const [i, setI] = useState(0)
  const input = useRef<HTMLInputElement>(null)
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (!isFindActionKey(e)) return
      e.preventDefault()
      if (paletteOpen()) closePalette()
      else openPalette(aimed())
    }
    window.addEventListener('keydown', key)
    return () => window.removeEventListener('keydown', key)
  }, [])
  useEffect(() => {
    if (!at) return
    setQ(''); setI(0)
    requestAnimationFrame(() => input.current?.focus())
    return onEscape(ESC.sheet, () => { closePalette(); return true })
  }, [at])
  const rows = useMemo(() => (at ? paletteList(registry.list(at.target, at.ctx), q) : []), [at, q])
  if (!at) return null
  const pick = (x: Listed | undefined) => {
    if (!x || x.availability.state !== 'available') return
    closePalette()
    runIt(x.def.id, at.target, at.ctx)
  }
  return createPortal(
    <div className="am-scrim" onPointerDown={(e) => { if (e.target === e.currentTarget) closePalette() }}>
      <div className="am-palette" role="dialog" aria-label={`Find an action: ${at.name}`}>
        <input ref={input} className="am-q" value={q} placeholder="Find an action…" aria-label="Find an action"
          onChange={(e) => { setQ(e.target.value); setI(0) }}
          onKeyDown={(e) => {
            if (e.key === 'ArrowDown') { e.preventDefault(); setI((n) => Math.min(rows.length - 1, n + 1)) }
            else if (e.key === 'ArrowUp') { e.preventDefault(); setI((n) => Math.max(0, n - 1)) }
            else if (e.key === 'Enter') { e.preventDefault(); pick(rows[i]) }
            /* Esc in a field is the field's (escape.ts): the palette's own field closes it */
            else if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); closePalette() }
          }} />
        <div className="am am-list" role="menu" aria-label="actions">
          {rows.map((x, n) => (
            <div key={x.def.id} className="am-prow">
              <Row x={x} active={n === i} onPick={() => pick(x)} />
              <span className="am-group-word">{GROUP_WORD[x.def.group]}</span>
            </div>
          ))}
          {!rows.length && <p className="am-none">No action here is called that.</p>}
        </div>
      </div>
    </div>,
    document.body,
  )
}
