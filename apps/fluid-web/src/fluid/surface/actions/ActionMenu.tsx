/* T1, T2 AND T3: THE ACTION BAR, THE ACTION MENU AND THE FIND-AN-ACTION
 * PALETTE (rev 3 §5; plan §3.5–§3.6; part P3).
 *
 * Three renderers of one list. ActionMenu (T2) draws registry.list in the
 * fixed groups, every available action including those in T1, disabled ones
 * with their reason beside them, and "Find an action…" last. ActionBar (T1)
 * draws registry.primary within a budget. ActionPalette (T3) is the same
 * list, narrowed by label and old words, opened by Ctrl/⌘+K or by Find an
 * action…. Each runs only registry.run. P4's SurfaceChrome places them. */

import { Fragment, useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react'
import { hostOf } from './providers/ops'
import { createPortal } from 'react-dom'
import { ACTION_GROUPS, type ActionCtx, type ActionDef, type ActionGroup, type ActionId, type ActionTarget } from './types'
import { findActionKey, paletteList, registry, type Listed } from './registry'
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

/** A host's ways of doing one action (Split side / below; the launcher's
 *  Bring back targets), each a row of its own under the action's. */
function Variants({ x, target, onDone }: { x: Listed; target: ActionTarget; onDone?: () => void }) {
  const vs = hostOf(target)?.[x.def.id]?.variants
  if (!vs?.length || x.availability.state === 'disabled') return null
  return <>{vs.map((v) => (
    <button key={v.key} type="button" role="menuitem" className="am-row am-variant" data-variant={v.key}
      aria-disabled={v.off ? true : undefined} title={v.says} onClick={() => { if (!v.off) { onDone?.(); v.run() } }}>
      <span className="am-glyph" aria-hidden="true" />
      <span className="am-label">{v.label}</span>
      {v.off && <small className="am-why">{v.off}</small>}
    </button>
  ))}</>
}

/** T2: every action for `target`, in the fixed groups; "Find an action…" last.
 *  `apart`: actions drawn in a section of their own, under `apartWord`, before
 *  Find an action… (SurfaceChrome keeps Remove from workspace away from Close). */
export function ActionMenu({ target, ctx, label, onDone, apart = [], apartWord }: {
  target: ActionTarget; ctx: ActionCtx; label: string; onDone?: () => void
  apart?: readonly ActionId[]; apartWord?: string
}) {
  const rows = registry.list(target, ctx)
  const find = rows.find((x) => x.def.id === 'findAction')
  const set = rows.filter((x) => apart.includes(x.def.id))
  const groups = ACTION_GROUPS.map((g) => ({ g, rows: rows.filter((x) => x.def.group === g && x !== find && !set.includes(x)) })).filter((x) => x.rows.length)
  const row = (x: Listed) => <Fragment key={x.def.id}><Row x={x} onPick={() => runIt(x.def.id, target, ctx, onDone)} /><Variants x={x} target={target} onDone={onDone} /></Fragment>
  return (
    <div className="am" role="menu" aria-label={label}>
      {groups.map(({ g, rows: rs }) => (
        <section key={g} className="am-group" data-group={g} aria-label={GROUP_WORD[g]}>
          <h4 className="am-head">{GROUP_WORD[g]}</h4>
          {rs.map(row)}
        </section>
      ))}
      {set.length > 0 && (
        <section className="am-group am-apart" data-group="apart" aria-label={apartWord ?? 'Apart'}>
          {apartWord && <h4 className="am-head">{apartWord}</h4>}
          {set.map(row)}
        </section>
      )}
      {find && <div className="am-find"><Row x={find} onPick={() => runIt(find.def.id, target, ctx, onDone)} /></div>}
    </div>
  )
}

/** T1: the lead action, then the host's shared verbs, within `budget`; or
 *  exactly `defs`, where the chrome has already decided them (chrome.ts t1Of). */
export function ActionBar({ target, ctx, budget, defs: given }: { target: ActionTarget; ctx: ActionCtx; budget: number; defs?: readonly ActionDef[] }) {
  const defs = given ? given.slice(0, Math.max(0, budget)) : registry.primary(target, ctx, budget)
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

/** A header's or footer's actions (SurfaceChrome's regions): the registry ids
 *  content named, each a labelled button run by registry.run. One the
 *  registry does not offer here is not drawn; a disabled one is drawn
 *  disabled with the registry's reason. */
export function RegionActions({ ids, target, ctx, region }: { ids: readonly ActionId[]; target: ActionTarget; ctx: ActionCtx; region: 'header' | 'footer' }) {
  const listed = registry.list(target, ctx)
  const rows = ids.map((id) => listed.find((x) => x.def.id === id)).filter((x): x is Listed => !!x)
  if (!rows.length) return null
  return (
    <span className="am-region" role="toolbar" data-region={region}>
      {rows.map(({ def, availability: a }) => {
        const why = a.state === 'disabled' ? a.reason.message : null
        return (
          <button key={def.id} type="button" className="am-ra fl-btn" data-action={def.id} aria-disabled={why ? true : undefined}
            title={why ? `${def.label}: ${why}` : saysOf(def.id)}
            onClick={(e) => { e.stopPropagation(); if (!why) runIt(def.id, target, ctx) }}>
            {def.glyph && <span className="am-glyph" aria-hidden="true">{def.glyph}</span>}
            <span className="am-label">{def.label}</span>
            {why && <small className="am-why">{why}</small>}
          </button>
        )
      })}
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
    /* capture: first, before any handler that stops a key on its way up */
    const key = (e: KeyboardEvent) => { findActionKey(e, () => (paletteOpen() ? closePalette() : openPalette(aimed()))) }
    window.addEventListener('keydown', key, { capture: true })
    return () => window.removeEventListener('keydown', key, { capture: true })
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
