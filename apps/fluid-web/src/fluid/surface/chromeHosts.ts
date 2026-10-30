/* WHAT EACH CHROME LENDS THE REGISTRY (part P4).
 *
 * SurfaceChrome draws a target's actions from the registry (P3). Today's
 * hosts -- a docked section, a window, a stack card, the Brain's window, the
 * launcher tile, the Page bar -- know how to do what they offer through
 * their own functions (a ZoneCtl, WindowActs, the Holder, the Brain's
 * overlay list). Each is lent here for its target with `hosted`, so every
 * item runs through registry.run and does exactly what the control it
 * replaces did. Remove from workspace asks first on coarse input
 * (chrome.ts asksFirst). Browser-free. */

import type { InputMode, PlacementKind, SurfaceKind, ZoneId } from './types'
import type { ActionTarget } from './actions/types'
import { hosted, ops, type HostOp, type SurfaceHost } from './actions/providers/ops'
import { hostSurface, workspaceTarget } from './actions/targets'
import { asksFirst, removeQuestion } from './chrome'

/** A surface target with `host` lent to it; `binding`: a section's (its chip). */
export function chromeTarget(id: ZoneId, kind: SurfaceKind, at: PlacementKind, host: SurfaceHost,
  binding?: { following: boolean; resource?: string }): ActionTarget {
  const surface = hostSurface(id, kind, at)
  if (binding) surface.state = {
    ...surface.state,
    binding: binding.following
      ? { mode: 'following', source: 'reading' }
      : { mode: 'held', resource: { address: binding.resource ?? 'zone:' + id, kind } },
  }
  return hosted({ surface }, host)
}

/** The workspace (the Page bar), with the bar's own panels lent. */
export const pageBarTarget = (key: string, host: SurfaceHost): ActionTarget => hosted(workspaceTarget(key), host)

/** Remove from workspace, asking first where a tap could be a slip. */
export function guarded(host: SurfaceHost, name: string, input: InputMode): SurfaceHost {
  const r = host.removeFromWorkspace
  if (!r || !asksFirst('removeFromWorkspace', input)) return host
  return { ...host, removeFromWorkspace: { ...r, run: () => { if (ops.confirm(removeQuestion(name))) r.run() } } }
}

/** A docked section's controls (workspace/TreeView.tsx ZoneCtl), as a host. */
export interface SectionCtl {
  focus?: () => void
  lens?: boolean
  float?: () => void
  /** why Float is refused now (transition()), said beside it */
  whyNoFloat?: string | null
  canSplitRow: boolean
  canSplitCol: boolean
  whyNoSplitRow: string | null
  whyNoSplitCol: string | null
  canMerge: boolean
  canClose: boolean
  split: (dir: 'row' | 'col') => void
  merge: () => void
  close: () => void
  fit: boolean
  canFit?: boolean
  toggleFit?: () => void
}
export interface SectionExtras {
  /** ⛶ Focus on it (the lens) */
  lensOn?: () => void
  /** the primary's way back */
  back?: () => void
  /** open the in-section search */
  search?: () => void
  /** the host's own settings (what it shows, how it looks): the Look row */
  settings?: () => void
  /** put it away to the launcher (the conversation's section) */
  putAway?: () => void
  /** folded to its caption (Home's zones): Collapse / Expand */
  fold?: { on: boolean; run: () => void }
  /** split, merge and removal: a section among others (not the primary column) */
  arrange?: boolean
}

export function sectionHost(ctl: SectionCtl, x: SectionExtras = {}): SurfaceHost {
  const h: SurfaceHost = {}
  if (ctl.focus) h.makePrimary = { run: ctl.focus, says: 'Make primary: swap it into the primary place (F)' }
  if (x.back) h.back = { run: x.back, says: 'Back: the primary before this one returns; they swap back' }
  if (x.lensOn) h.focus = { run: x.lensOn, says: 'Focus on it: it takes the Focus area, everything else steps aside (Esc returns)' }
  if (x.search) h.search = { run: x.search }
  if (ctl.canFit !== false && ctl.toggleFit) h.fit = { run: ctl.toggleFit, on: ctl.fit,
    says: ctl.fit ? 'Fitted to its content: take its share again' : 'Fit to content: size it to what it holds' }
  if (ctl.float) h.float = { run: ctl.float, off: ctl.whyNoFloat ?? null, says: 'Float it: a window you can move and size' }
  if (x.fold) {
    if (x.fold.on) h.expand = { run: x.fold.run, says: 'Expand: unfold it' }
    else h.collapse = { run: x.fold.run, says: 'Collapse: fold it to its caption' }
  }
  if (x.putAway) h.putAway = { run: x.putAway, says: 'Put away to the launcher (Undo brings it back)' }
  if (x.arrange !== false) {
    h.split = {
      run: () => ctl.split(ctl.canSplitRow ? 'row' : 'col'),
      off: ctl.canSplitRow || ctl.canSplitCol ? null : ctl.whyNoSplitRow ?? ctl.whyNoSplitCol ?? 'No room to split it',
      variants: [
        { key: 'split-row', label: 'Split side by side', says: 'Split side by side', off: ctl.canSplitRow ? null : ctl.whyNoSplitRow ?? 'No room to split it side by side', run: () => ctl.split('row') },
        { key: 'split-col', label: 'Split top and bottom', says: 'Split top and bottom', off: ctl.canSplitCol ? null : ctl.whyNoSplitCol ?? 'No room to split it top and bottom', run: () => ctl.split('col') },
      ],
    }
    h.merge = { run: ctl.merge, off: ctl.canMerge ? null : 'Nothing beside it to merge into', says: 'Merge with the section beside it' }
    h.removeFromWorkspace = { run: ctl.close, off: ctl.canClose ? null : 'A page keeps one section',
      says: 'Remove from workspace: take this section out, on every device (Undo brings it back)' }
  }
  if (x.settings) h.settings = { run: x.settings, says: 'Settings: what it shows, how it looks, where it sits' }
  return h
}

/** A window's actions (workspace/zoneMenu.tsx WindowActs), as a host. */
export interface WindowCtl {
  primary?: () => void
  focus?: () => void
  dockBack?: () => void
  minimise?: { on: boolean; run: () => void }
  tidy?: () => void
  /** takes the window out of the arrangement: Remove from workspace */
  close?: () => void
}
export interface WindowExtras {
  settings?: () => void
  /** × here: this device stops showing it (device-local Close) */
  closeHere?: HostOp
  putAway?: () => void
  float?: () => void
}

export function windowHost(w: WindowCtl, x: WindowExtras = {}): SurfaceHost {
  const h: SurfaceHost = {}
  if (w.primary) h.makePrimary = { run: w.primary, says: 'Make primary: it and the primary trade places (F; again swaps back)' }
  if (w.minimise) {
    if (w.minimise.on) h.expand = { run: w.minimise.run, says: 'Expand: open the window again where it is' }
    else h.collapse = { run: w.minimise.run, says: 'Collapse: fold it to its title line, where it is' }
  }
  if (w.focus) h.focus = { run: w.focus, says: 'Focus on it: it takes the Focus area (Esc returns)' }
  if (w.dockBack) h.dock = { run: w.dockBack, says: 'Dock back beside the section it left' }
  if (x.float) h.float = { run: x.float }
  if (x.putAway) h.putAway = { run: x.putAway }
  if (w.tidy) h.tidy = { run: w.tidy, says: 'Tidy floating windows: line them up at the right' }
  if (x.closeHere) h.close = x.closeHere
  if (w.close) h.removeFromWorkspace = { run: w.close, says: 'Remove from workspace: take this window out, on every device (Undo brings it back)' }
  if (x.settings) h.settings = { run: x.settings, says: 'Settings: where it sits, and what it shows' }
  return h
}

/** The Page bar: the workspace's own verbs as the workspace provider runs
 *  them (providers/workspace.ts, through the Holder), with its Settings panel
 *  lent for Layouts, Sketch and Look, which open there. */
export function pageBarHost(openSettings: () => void): SurfaceHost {
  const h = ops.holder()
  const here = h.kind === 'workspace'
  const floats = here ? ops.floatsHere() : { count: 0, unfolded: 0 }
  const host: SurfaceHost = {
    saveLayout: { run: () => void h.save(), off: h.kind === 'stream' ? 'The Stream has no arrangement to save' : null },
    restoreLayout: { run: () => void h.restoreSaved(), off: h.savedAt ? null : 'Nothing is saved for this place yet' },
    undo: { run: () => h.undo(), off: h.canUndo() ? null : 'Nothing to undo' },
    resetPlace: { run: () => h.reset() },
    layouts: { run: openSettings, says: 'Layouts: apply, save, or set a default arrangement (in Settings)' },
    sketch: { run: openSettings, says: 'Sketch a layout (in Settings)' },
    settings: { run: openSettings, says: 'Workspace settings: arrange this Page, layouts, Focus, look and background' },
  }
  if (here) {
    host.tidy = { run: () => ops.tidyFloats(), off: floats.count ? null : 'No floating windows here' }
    host.putAllAway = { run: () => ops.putAllAway(), off: floats.unfolded ? null : 'No open floating windows here' }
    host.newFollower = { run: () => ops.newFollower() }
  }
  return host
}

/** The launcher tile: tap is Bring back; its other ways back are Bring
 *  back's variants (providers/conversation.ts launcherDefs). */
export function launcherHost(restore: () => void, choices: readonly { label: string; says?: string; run: () => void }[]): SurfaceHost {
  return {
    bringBack: {
      run: restore, says: 'Bring back where it was',
      variants: choices.map((c, i) => ({ key: 'back-' + i, label: c.label, says: c.says ?? c.label, run: c.run })),
    },
  }
}
