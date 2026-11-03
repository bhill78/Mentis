/* THE WORKSPACE AND FOCUS PROVIDERS (rev 3 §6 "Arrange.tsx", "LensLayer.tsx
 * focus bar", rows 47–56; part P3).
 *
 * The workspace (the Page bar's Arrange): Save / Restore layout, Undo, Reset
 * this place, Put all away, Tidy and New follower through the workspace
 * Holder and model.ts, as Arrange does; Layouts and Sketch are Arrange's own
 * panels, lent by it as a host or pointed to. Tidy is also a window's (its
 * WindowActs, lent by zoneMenu.tsx).
 *
 * The lens (Focus): Exit focus (lens.restore; "Restore" by its old word),
 * Keep arrangement (lens.keepLayout), Tidy around, and Hide others as its
 * Filter. */

import type { ActionDef, ActionTarget } from '../types'
import { ABSENT, AVAILABLE, disabled } from '../registry'
import { def } from '../words'
import { hostOf, ops } from './ops'
import { hostAvailable } from './surface'

const isWorkspace = (t: ActionTarget) => t.resource?.kind === 'workspace' && !t.surface
const runHostOr = (id: ActionDef['id'], t: ActionTarget, fallback: () => void | Promise<void>) => { const op = hostOf(t)?.[id]; return op ? op.run() : fallback() }

/** The workspace verbs, registered as shared verbs: absent except on the
 *  workspace (or where a host lends them). */
export function workspaceDefs(): ActionDef[] {
  const ws = (id: 'saveLayout' | 'restoreLayout' | 'undo' | 'resetPlace' | 'putAllAway' | 'tidy' | 'newFollower',
    when: () => ReturnType<ActionDef['available']>, run: () => void | Promise<void>) => def(id, {
    plane: 'surface', writes: 'placement',
    available: (t) => hostAvailable(id, t) ?? (isWorkspace(t) ? when() : ABSENT),
    run: (t) => runHostOr(id, t, run),
  })
  const panel = (id: 'layouts' | 'sketch' | 'settings', where: string) => def(id, {
    plane: 'surface', writes: 'placement',
    available: (t) => hostAvailable(id, t) ?? (isWorkspace(t) ? disabled(where, 'scope', false) : ABSENT),
    run: (t) => runHostOr(id, t, () => { throw new Error(where) }),
  })
  return [
    ws('saveLayout', () => (ops.holder().kind === 'stream' ? disabled('The Stream has no arrangement to save') : AVAILABLE), () => ops.holder().save()),
    ws('restoreLayout', () => (ops.holder().savedAt ? AVAILABLE : disabled('Nothing is saved for this place yet')), () => ops.holder().restoreSaved()),
    ws('undo', () => (ops.holder().canUndo() ? AVAILABLE : disabled('Nothing to undo')), () => ops.holder().undo()),
    ws('resetPlace', () => AVAILABLE, () => ops.holder().reset()),
    ws('putAllAway', () => (ops.holder().kind !== 'workspace' ? ABSENT : ops.floatsHere().unfolded ? AVAILABLE : disabled('No open floating windows here')), () => ops.putAllAway()),
    ws('tidy', () => (ops.holder().kind !== 'workspace' ? ABSENT : ops.floatsHere().count ? AVAILABLE : disabled('No floating windows here')), () => ops.tidyFloats()),
    ws('newFollower', () => (ops.holder().kind === 'workspace' ? AVAILABLE : ABSENT), () => ops.newFollower()),
    panel('layouts', 'Open Arrange in the bar to apply, save or set a default layout'),
    panel('sketch', 'Open Arrange in the bar to sketch a layout'),
    /* the bar's Look column (row 55): the place's own look, unchanged */
    panel('settings', "Change this place's look from Look in the bar"),
  ]
}

/** The Focus lens's own bar (surface kind 'lens'). */
export function lensDefs(t: ActionTarget): ActionDef[] {
  const on = () => ops.lensOn()
  const lens = (id: 'exitFocus' | 'keepArrangement' | 'tidyAround' | 'filter', run: () => void, lead = false) => def(id, {
    plane: 'surface', writes: id === 'keepArrangement' ? 'placement' : 'none', ...(lead ? { lead } : {}),
    available: () => hostAvailable(id, t) ?? (on() ? AVAILABLE : ABSENT),
    run: () => runHostOr(id, t, run),
  })
  return [
    lens('exitFocus', () => ops.exitFocus(), true),
    lens('keepArrangement', () => ops.keepLensLayout()),
    lens('tidyAround', () => ops.tidyAround()),
    lens('filter', () => ops.hideOthers()),
    def('present', {
      plane: 'surface', writes: 'none',
      available: () => hostAvailable('present', t) ?? (on() ? disabled("Choose how Focus presents it on the focus bar", 'scope', false) : ABSENT),
      run: () => runHostOr('present', t, () => { throw new Error('Choose on the focus bar') }),
    }),
  ]
}
