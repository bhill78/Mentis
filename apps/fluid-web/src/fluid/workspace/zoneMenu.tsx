/* THE WINDOW AND SECTION MENUS, AS ICONS IN COLUMNS (owner feedback, round
 * 2: "Organize the menus on windows ... Use more icons than words ... a
 * tiered menu or a menu that has multiple columns"). Every section's,
 * window's, reply thread's and the conversation's ⋯ is drawn by the one
 * IconMenu (frame/IconMenu.tsx) from the columns made here:
 *
 *   Content   what it brings in, what that is narrowed to, what it shows (tiers)
 *   Present   how it lays out what it holds (each mode its drawing)
 *   Look      this surface's appearance: Clear, Quiet, Glass, Solid, opacity
 *   Arrange   what can be done with it where it is -- a window its window
 *             actions, a docked section its split and fit, the primary its
 *             focus and the way back -- and nothing that does nothing
 *
 * Each item is an icon and one word; its full meaning is its tooltip. Only
 * how the choices are drawn is here: what each does is the caller's. */

import type { ReactNode } from 'react'
import type { IconGroup, IconItem } from '../frame/IconMenu'
import { APPEARANCE_PRESETS, AppearancePicker, PRESENT_MODES, readAppearance, type Appearance, type PresentMode } from '../present'
import { ModeIcon } from '../present/Pickers'
import type { ZoneCtl } from './TreeView'

const same = (a: Appearance, b: Appearance) => a.panel === b.panel && a.content === b.content && Math.abs(a.opacity - b.opacity) < 0.005

/** One look, drawn as itself: its panel behind, its content on it. */
const Swatch = ({ a }: { a: Appearance }) => <span className={`pz-swatch pz-panel-${a.panel} pz-content-${a.content}`} aria-hidden="true"><i /><i /></span>

/** LOOK: the four looks as swatches, opacity as a slider, the detail (panel
 *  and content apart) a tier deeper; `reset` back to the place's look, and
 *  `forAll` to make this the place's look. */
export function lookGroup({ value, onChange, reset, forAll }: {
  value: Appearance; onChange: (a: Appearance) => void
  reset?: { run: () => void; isDefault: boolean }
  forAll?: () => void
}): IconGroup {
  const a = readAppearance(value)
  const pct = Math.round(a.opacity * 100)
  const covers = a.panel !== 'transparent' || a.content !== 'transparent'
  const items: IconItem[] = APPEARANCE_PRESETS.map((p) => ({
    id: 'look-' + p.id, icon: <Swatch a={p.a} />, label: p.label, says: `${p.label}: ${p.says}`, on: same(p.a, a), onPick: () => onChange(p.a),
  }))
  items.push({ id: 'look-more', icon: '⚙', label: 'Detail', says: 'Set the panel and the content apart, and how much they cover',
    tier: [{ title: 'Look', body: <AppearancePicker value={a} onChange={onChange} onReset={reset?.run} isDefault={reset?.isDefault}
      resetLabel={["Back to this place's look", "This place's look"]} title="Appearance" /> }] })
  if (reset && !reset.isDefault) items.push({ id: 'look-reset', icon: '↺', label: 'Place', says: "Back to this place's look", onPick: reset.run })
  if (forAll) items.push({ id: 'look-all', icon: '⇶', label: 'For all', says: "Use this look for every section here: it becomes the place's look", onPick: forAll })
  return {
    title: 'Look', items,
    body: (
      <label className="im-range" title={covers ? 'How much of the atmosphere a fill covers' : 'Nothing is filled: opacity has nothing to cover'}>
        <span className="im-range-word">Opacity</span>
        <input type="range" min={0} max={100} step={5} value={pct} disabled={!covers} aria-label="Opacity"
          onChange={(e) => onChange({ ...a, opacity: Number(e.target.value) / 100 })} />
        <span className="im-range-n">{pct}%</span>
      </label>
    ),
  }
}

/** PRESENT: each way of laying out what it holds, as its drawing. */
export function presentGroup(mode: PresentMode, onMode: (m: PresentMode) => void, body?: ReactNode): IconGroup {
  return {
    title: 'Present', body,
    items: PRESENT_MODES.map((p) => ({ id: 'present-' + p.mode, icon: <ModeIcon mode={p.mode} />, label: p.label.split(' ')[0],
      says: `${p.label}: ${p.says}`, on: p.mode === mode, onPick: () => onMode(p.mode) })),
  }
}

/* The drawings Arrange uses: a split side by side and top and bottom, Fit,
   Merge, as the section's own tools draw them (TreeView.tsx). */
const svg = (d: ReactNode) => <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.3" aria-hidden="true">{d}</svg>
export const ARRANGE_ICON = {
  splitRow: svg(<><rect x="2" y="3" width="12" height="10" rx="1.5" /><path d="M8 3v10" /></>),
  splitCol: svg(<><rect x="2" y="3" width="12" height="10" rx="1.5" /><path d="M2 8h12" /></>),
  merge: svg(<><rect x="2" y="3" width="12" height="10" rx="1.5" /><path d="M6 8h4M8.5 6.5 10 8l-1.5 1.5" /></>),
  fit: svg(<><rect x="3" y="4" width="10" height="8" rx="1.2" /><path d="M1 6V2h4M15 10v4h-4" /></>),
  minimise: svg(<path d="M3 11h10" />),
  restore: svg(<rect x="3" y="4" width="10" height="8" rx="1.2" />),
}

/** What a place offers to do with it (its ctl), as Arrange items: only what
 *  can be done there. `primary`: it is the primary, and `back` returns the
 *  one before it; `focus`: ⛶ it. */
export function placeItems(ctl: ZoneCtl, { focus, back, floating = false }: { focus?: () => void; back?: () => void; floating?: boolean } = {}): IconItem[] {
  const out: IconItem[] = []
  if (floating) return out
  if (ctl.focus) out.push({ id: 'primary', icon: '◎', label: 'Primary', says: 'Make primary: swap it into the primary place (F)', onPick: ctl.focus })
  if (back) out.push({ id: 'back', icon: '↶', label: 'Back', says: 'Restore the primary before this one: they swap back', onPick: back })
  if (focus) out.push({ id: 'focus', icon: '⛶', label: 'Focus', says: 'Focus on it: it takes the Focus area, everything else steps aside (Esc returns)', onPick: focus })
  if (ctl.float) out.push({ id: 'float', icon: '⇱', label: 'Float', says: 'Float it: a window you can move and size', onPick: ctl.float })
  /* a docked section: its split, fit, merge and close (the primary column, a
     place of its own, has none of those) */
  if (ctl.canSplitRow || ctl.canSplitCol || ctl.canMerge || ctl.canClose) {
    out.push({ id: 'split-row', icon: ARRANGE_ICON.splitRow, label: 'Side', says: 'Split side by side', off: !ctl.canSplitRow, why: ctl.whyNoSplitRow ?? undefined, onPick: () => ctl.split('row') })
    out.push({ id: 'split-col', icon: ARRANGE_ICON.splitCol, label: 'Below', says: 'Split top and bottom', off: !ctl.canSplitCol, why: ctl.whyNoSplitCol ?? undefined, onPick: () => ctl.split('col') })
    if (ctl.canFit && ctl.toggleFit) out.push({ id: 'fit', icon: ARRANGE_ICON.fit, label: 'Fit', on: ctl.fit,
      says: ctl.fit ? 'Fitted to its content: take its share again' : 'Fit to content: size it to what it holds', onPick: ctl.toggleFit })
    out.push({ id: 'merge', icon: ARRANGE_ICON.merge, label: 'Merge', says: 'Merge with the section beside it', off: !ctl.canMerge, why: 'Nothing beside it to merge into', onPick: ctl.merge })
    out.push({ id: 'close', icon: '×', label: 'Close', says: 'Close this section (Undo brings it back)', off: !ctl.canClose, why: 'A page keeps one section', onPick: ctl.close })
  }
  return out
}

/** What a floating window offers, as Arrange items (focus/Floats.tsx gives
 *  them to the zone's menu, or draws them in its own). */
export interface WindowActs {
  primary?: () => void
  focus?: () => void
  pin?: { on: boolean; run: () => void }
  dockBack?: () => void
  minimise?: { on: boolean; run: () => void }
  tidy?: () => void
  close?: () => void
}
export function windowItems(w: WindowActs): IconItem[] {
  const out: IconItem[] = []
  if (w.primary) out.push({ id: 'primary', icon: '◎', label: 'Primary', says: 'Make primary: it and the primary trade places (F; again swaps back)', onPick: w.primary })
  if (w.focus) out.push({ id: 'focus', icon: '⛶', label: 'Focus', says: 'Focus on it: it takes the Focus area (Esc returns)', onPick: w.focus })
  if (w.pin) out.push({ id: 'pin', icon: '📌', label: w.pin.on ? 'Pinned' : 'Pin', on: w.pin.on, onPick: w.pin.run,
    says: w.pin.on ? 'Pinned: this window stays with you in every conversation. Press to leave it here' : 'Pin: keep this window with you in every conversation' })
  if (w.dockBack) out.push({ id: 'dock', icon: '⤓', label: 'Dock', says: 'Dock back beside the section it left', onPick: w.dockBack })
  if (w.minimise) out.push({ id: 'minimise', icon: w.minimise.on ? ARRANGE_ICON.restore : ARRANGE_ICON.minimise, label: w.minimise.on ? 'Restore' : 'Minimise', on: w.minimise.on,
    says: w.minimise.on ? 'Restore: open the window again where it is' : 'Minimise: fold it to its title line, where it is', onPick: w.minimise.run })
  if (w.tidy) out.push({ id: 'tidy', icon: '⊞', label: 'Tidy', says: 'Tidy floating windows: line them up at the right', onPick: w.tidy })
  if (w.close) out.push({ id: 'close', icon: '×', label: 'Close', says: 'Close this window (Undo brings it back)', onPick: w.close })
  return out
}

/** The Arrange column, from what the place and the window offer. */
export const arrangeGroup = (items: IconItem[]): IconGroup | null => (items.length ? { title: 'Arrange', items } : null)
