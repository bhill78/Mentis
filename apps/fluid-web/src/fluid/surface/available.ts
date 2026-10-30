/* SURFACE TENSION: available() (plan §3.4; r3 §2.1–§2.2; r4 §1.2 rule 3;
 * part P1).
 *
 * Whether a surface verb applies, computed from the surface's capabilities
 * and its state, never coded per host:
 *   - ABSENT: the verb's target value is not in the capabilities for this
 *     class (it can never apply here: Dock on the lens, Collapse at icon);
 *   - DISABLED, with a reason: it applies to the kind, but bounds or the
 *     present state forbid it now (a thirteenth stored window).
 * A surface closed on this device offers only Reopen and Remove from
 * workspace: it is not drawn, so nothing else could act on it. */

import { primaryOf } from '../focus/model'
import { MAX_FLOATS } from '../focus/types'
import { placementsIn } from './capabilities'
import { levelShown, stepLevel } from './levels'
import { findSurface, orderIn } from './state'
import { FLOAT_LIMIT_MESSAGE, NOTHING_TO_HOLD, holdable, viewOf } from './transition'
import type { Availability, AvailableFn, CapabilityUnavailable, SurfaceCapabilities, SurfaceCtx, SurfaceState, SurfaceVerb } from './types'

const yes: Availability = { state: 'available' }
const absent: Availability = { state: 'absent' }
const disabled = (code: CapabilityUnavailable['code'], message: string, retryable = true): Availability =>
  ({ state: 'disabled', reason: { code, message, retryable } })
/** The stored windows are all used: said only where a float is the target. */
const floatLimit = (ctx: SurfaceCtx): Availability | null =>
  (viewOf(ctx).focus?.floats?.length ?? 0) >= MAX_FLOATS ? disabled('limit', FLOAT_LIMIT_MESSAGE) : null

export function available(verb: SurfaceVerb, s: SurfaceState, caps: SurfaceCapabilities, ctx: SurfaceCtx): Availability {
  const p = s.placement
  if (!s.open) return verb === 'reopen' || verb === 'removeFromWorkspace' ? removable(verb) : absent
  const may = placementsIn(caps, ctx.cls)
  const wide = ctx.cls === 'wide'
  const docked = p.kind === 'dock' || p.kind === 'stack' || p.kind === 'sheet'
  /* the lens is emphasis, not a place: nothing moves it until it ends (r3 §2.2 Dock/Float) */
  const lensed = s.emphasis === 'lens'
  const view = () => viewOf(ctx)

  switch (verb) {
    case 'expand':
    case 'collapse': {
      if (s.placement.kind === 'launcher') return absent
      if (!stepLevel(levelShown(s.level), verb === 'expand' ? 1 : -1, caps.levels)) return absent
      return wide && p.kind === 'dock' && p.in === 'column'
        ? disabled('state', 'The conversation column takes its width from its boundary; float it or dock it as a section to change its size.')
        : yes
    }
    case 'resetSize':
      if (caps.levels.size < 2 || p.kind === 'launcher') return absent
      return s.level.override ? yes : disabled('state', 'It is already at its automatic size.')
    case 'dock':
      if (!may.has('dock') || lensed || p.kind === 'dock' || p.kind === 'launcher' || p.kind === 'page-root' || p.kind === 'nested') return absent
      return yes
    case 'float':
      if (!may.has('float') || lensed || p.kind === 'float' || p.kind === 'launcher' || p.kind === 'page-root' || p.kind === 'nested') return absent
      if (p.kind === 'dock' && p.in === 'column' && s.kind !== 'conversation') return absent
      return floatLimit(ctx) ?? yes
    case 'focus':
      return !caps.focusable || s.emphasis !== 'none' || p.kind === 'launcher' ? absent : yes
    case 'exitFocus':
      return s.emphasis === 'lens' ? yes : absent
    case 'fullscreen':
      return !caps.fullscreen || s.emphasis === 'fullscreen' || p.kind === 'launcher' ? absent : yes
    case 'exitFullscreen':
      return s.emphasis === 'fullscreen' ? yes : absent
    case 'putAway':
      return !caps.putAway || !may.has('launcher') || p.kind === 'launcher' || lensed ? absent : yes
    case 'bringBack':
      return p.kind === 'launcher' ? yes : absent
    case 'makePrimary':
      if (!caps.primaryable || p.kind === 'launcher' || p.kind === 'nested' || p.kind === 'page-root') return absent
      return primaryOf(view()) === s.id ? absent : yes
    case 'back':
      if (!caps.primaryable || p.kind === 'launcher') return absent
      return (view().focus?.previous ?? []).length ? yes : disabled('state', 'Nothing earlier was primary to go back to.')
    case 'close':
      return caps.closable ? yes : absent
    case 'reopen':
      return absent
    case 'removeFromWorkspace':
      return removable(verb)
    case 'follow':
    case 'hold': {
      /* as transition() asks it: a section docked in the tree in wide, whatever this class shows */
      const w = findSurface(view(), s.id)?.wide
      if (!caps.canFollow || p.kind === 'launcher' || w?.kind !== 'dock' || w.in !== 'tree') return absent
      const following = s.binding.mode === 'following'
      if ((verb === 'follow') === following) return absent
      /* the same documented read transition() makes (holdable, opr-991df732c969) */
      return verb === 'hold' && !holdable() ? disabled('state', NOTHING_TO_HOLD) : yes
    }
    case 'keepAsWindow':
      /* Keep → New window, from a section that follows (rev 3 §1.1.3) */
      if (!caps.canFollow || s.binding.mode !== 'following' || !docked || !wide) return absent
      return floatLimit(ctx) ?? yes
    case 'newFollower':
      return caps.canFollow && docked ? yes : absent
    case 'bringToFront': {
      if (!wide || p.kind !== 'float') return absent
      const fs = view().focus?.floats ?? []
      return fs[fs.length - 1]?.id === p.floatId ? disabled('state', 'It is already in front.') : yes
    }
    case 'tidy':
      return wide && p.kind === 'float' ? yes : absent
    case 'moveUp':
    case 'moveDown': {
      if (wide || p.kind !== 'stack') return absent
      const order = orderIn(view(), ctx.device)
      const at = order.indexOf(s.id)
      return (verb === 'moveUp' ? at <= 0 : at >= order.length - 1) ? disabled('state', verb === 'moveUp' ? 'It is already first.' : 'It is already last.') : yes
    }
    case 'showAsSheet':
      return wide || !may.has('sheet') || p.kind === 'sheet' ? absent : yes
  }

  function removable(v: 'reopen' | 'removeFromWorkspace'): Availability {
    if (v === 'reopen') return yes
    /* the conversation is the place's own; a Page root or a card is removed with its parent */
    return s.kind === 'conversation' || p.kind === 'page-root' || p.kind === 'nested' || caps.kind === 'lens' ? absent : yes
  }
}
available satisfies AvailableFn
