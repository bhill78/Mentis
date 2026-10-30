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
import { presentationClass } from '../frame/narrow'
import { registry } from '../surface/actions/registry'
import { installProviders } from '../surface/actions/providers'
import { hosted, type SurfaceHost } from '../surface/actions/providers/ops'
import { hostCtx, hostSurface } from '../surface/actions/targets'
import { saysOf } from '../surface/actions/words'
import type { ActionId, ActionTarget } from '../surface/actions/types'

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

/* THE ARRANGE ITEMS ARE THE REGISTRY'S (Surface Tension P3; plan §3.5, rev 3
   §6 "zoneMenu.tsx section builder and window builder → one surface-action
   provider"). A section's ctl and a window's acts are lent to the registry as
   the host of their target (surface/actions/providers/ops.ts `hosted`); the
   items are `registry.list` of that target, in the host's order, each
   running through `registry.run`, the same entry point as the palette's.
   "Find an action…" is the last item.

   Words (I-1): Minimise is Collapse, its Restore is Expand; the × that took a
   section or window out of the arrangement is Remove from workspace (it is
   shared, on every device, and Undo brings it back). Close means only this
   device's presentation (surface/actions/providers/surface.ts). */

/** The one-word label under an item's icon, where its label is longer. */
const SHORT: Partial<Record<ActionId, string>> = {
  makePrimary: 'Primary', removeFromWorkspace: 'Remove', findAction: 'Find…', bringToFront: 'Front', keepAsWindow: 'Window',
}
/** The drawings the section's own tools used, kept for the same actions. */
const DRAWN: Partial<Record<ActionId, ReactNode>> = {
  fit: ARRANGE_ICON.fit, merge: ARRANGE_ICON.merge, collapse: ARRANGE_ICON.minimise, expand: ARRANGE_ICON.restore,
}

/** The registry's items for a host's target: in the host's order (its
 *  keys), then Find an action…; `extra` items the contract has no verb for
 *  yet (a window's Pin) go after the item they followed. */
function hostItems(target: ActionTarget, host: SurfaceHost, extra: { after: ActionId; item: IconItem }[] = []): IconItem[] {
  installProviders()
  hosted(target, host)
  const ctx = hostCtx(presentationClass(typeof window === 'undefined' ? 1280 : window.innerWidth))
  const order = Object.keys(host) as ActionId[]
  const listed = registry.list(target, ctx)
    .filter((x) => x.def.id === 'findAction' || order.includes(x.def.id))
    .sort((a, b) => (a.def.id === 'findAction' ? 1 : b.def.id === 'findAction' ? -1 : order.indexOf(a.def.id) - order.indexOf(b.def.id)))
  const run = (id: ActionId) => () => { void registry.run(id, target, ctx).catch((e: Error) => console.warn(`${id}: ${e.message}`)) }
  const out: IconItem[] = []
  for (const { def, availability } of listed) {
    const op = host[def.id]
    const why = availability.state === 'disabled' ? availability.reason.message : undefined
    if (op?.variants) for (const v of op.variants) out.push({ id: v.key, icon: v.icon as ReactNode, label: v.label, says: v.says, off: !!v.off, why: v.off ?? undefined, onPick: v.run })
    else out.push({ id: def.id, icon: DRAWN[def.id] ?? def.glyph, label: SHORT[def.id] ?? def.label, says: op?.says ?? saysOf(def.id),
      on: op?.on, off: !!why, why, onPick: run(def.id) })
    for (const x of extra) if (x.after === def.id) out.push(x.item)
  }
  return out
}

/** What a place offers to do with it (its ctl), as Arrange items: only what
 *  can be done there. `primary`: it is the primary, and `back` returns the
 *  one before it; `focus`: ⛶ it. */
export function placeItems(ctl: ZoneCtl, { focus, back, floating = false }: { focus?: () => void; back?: () => void; floating?: boolean } = {}): IconItem[] {
  if (floating) return []
  const host: SurfaceHost = {}
  if (ctl.focus) host.makePrimary = { run: ctl.focus, says: 'Make primary: swap it into the primary place (F)' }
  if (back) host.back = { run: back, says: 'Back: the primary before this one returns; they swap back' }
  if (focus) host.focus = { run: focus, says: 'Focus on it: it takes the Focus area, everything else steps aside (Esc returns)' }
  if (ctl.float) host.float = { run: ctl.float, says: 'Float it: a window you can move and size' }
  /* a docked section: its split, fit, merge and removal (the primary column,
     a place of its own, has none of those) */
  if (ctl.canSplitRow || ctl.canSplitCol || ctl.canMerge || ctl.canClose) {
    host.split = {
      run: () => ctl.split(ctl.canSplitRow ? 'row' : 'col'),
      off: ctl.canSplitRow || ctl.canSplitCol ? null : ctl.whyNoSplitRow ?? ctl.whyNoSplitCol ?? 'No room to split it',
      variants: [
        { key: 'split-row', icon: ARRANGE_ICON.splitRow, label: 'Side', says: 'Split side by side', off: ctl.canSplitRow ? null : ctl.whyNoSplitRow ?? 'No room to split it side by side', run: () => ctl.split('row') },
        { key: 'split-col', icon: ARRANGE_ICON.splitCol, label: 'Below', says: 'Split top and bottom', off: ctl.canSplitCol ? null : ctl.whyNoSplitCol ?? 'No room to split it top and bottom', run: () => ctl.split('col') },
      ],
    }
    if (ctl.canFit && ctl.toggleFit) host.fit = { run: ctl.toggleFit, on: ctl.fit,
      says: ctl.fit ? 'Fitted to its content: take its share again' : 'Fit to content: size it to what it holds' }
    host.merge = { run: ctl.merge, off: ctl.canMerge ? null : 'Nothing beside it to merge into', says: 'Merge with the section beside it' }
    host.removeFromWorkspace = { run: ctl.close, off: ctl.canClose ? null : 'A page keeps one section',
      says: 'Remove from workspace: take this section out, on every device (Undo brings it back)' }
  }
  if (!Object.keys(host).length) return []
  return hostItems({ surface: hostSurface(ctl.id ?? 'zone', 'section', 'dock') }, host)
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
  const host: SurfaceHost = {}
  if (w.primary) host.makePrimary = { run: w.primary, says: 'Make primary: it and the primary trade places (F; again swaps back)' }
  if (w.focus) host.focus = { run: w.focus, says: 'Focus on it: it takes the Focus area (Esc returns)' }
  if (w.dockBack) host.dock = { run: w.dockBack, says: 'Dock back beside the section it left' }
  if (w.minimise) {
    if (w.minimise.on) host.expand = { run: w.minimise.run, says: 'Expand: open the window again where it is' }
    else host.collapse = { run: w.minimise.run, says: 'Collapse: fold it to its title line, where it is' }
  }
  if (w.tidy) host.tidy = { run: w.tidy, says: 'Tidy floating windows: line them up at the right' }
  if (w.close) host.removeFromWorkspace = { run: w.close, says: 'Remove from workspace: take this window out, on every device (Undo brings it back)' }
  if (!Object.keys(host).length && !w.pin) return []
  /* Pin ("goes with me everywhere", I-1) has no verb in the shared contract
     yet: it stays the window's own item, after Focus (recorded as discovered
     work for a contract revision). */
  const pin: IconItem[] = w.pin ? [{ id: 'pin', icon: '📌', label: w.pin.on ? 'Pinned' : 'Pin', on: w.pin.on, onPick: w.pin.run,
    says: w.pin.on ? 'Pinned: this window stays with you in every conversation. Press to leave it here' : 'Pin: keep this window with you in every conversation' }] : []
  const after: ActionId = w.focus ? 'focus' : 'makePrimary'
  const items = hostItems({ surface: hostSurface('window', 'float', 'float') }, host, pin.map((item) => ({ after, item })))
  return items.some((x) => x.id === 'pin') ? items : [...pin, ...items]
}

/** The Arrange column, from what the place and the window offer: one
 *  "Find an action…" (the place's, when both give one), last. */
export function arrangeGroup(items: IconItem[]): IconGroup | null {
  const find = items.find((x) => x.id === 'findAction')
  const rest = items.filter((x) => x.id !== 'findAction')
  return rest.length ? { title: 'Arrange', items: find ? [...rest, find] : rest } : null
}
