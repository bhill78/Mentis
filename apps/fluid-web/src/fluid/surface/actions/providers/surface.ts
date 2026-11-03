/* SURFACE VERBS (rev 3 §2.2, plan §3.3–§3.5; part P3).
 *
 * One definition per verb, the same for a section, a window, the
 * conversation, a Page panel and a launcher tile. Each runs one Change
 * through ctx.apply (= workspace.apply, P1), or, where today's control is
 * the host's own (ZoneCtl, WindowActs: ops.ts), the host's function.
 *
 * CLOSE IS NOT REMOVE. `close` is {prop:'open', to:false}: this browser
 * device stops showing it, in this presentation class; nothing shared
 * changes. `removeFromWorkspace` is {prop:'exists', to:false}: the shared
 * surface leaves the workspace on every device. Today's × on a section or
 * window removes it from the arrangement (Undo brings it back), so it is
 * Remove from workspace here, never Close.
 *
 * Availability, until P1's available() is wired in (useSurfaceAvailable):
 * a host decides what it offers; otherwise the surface's declared
 * capabilities and state decide, absent where the target value is not in its
 * capabilities for this class. */

import type { Availability, Change, Level, SurfaceVerb } from '../../types'
import { LEVELS } from '../../types'
import type { ActionCtx, ActionDef, ActionId, ActionTarget, SharedVerb } from '../types'
import { ABSENT, AVAILABLE, disabled } from '../registry'
import { def } from '../words'
import { hostOf, ops } from './ops'

/** The one Change each surface verb is, where it is one. */
export function changeOf(verb: SharedVerb, t: ActionTarget): Change | null {
  const s = t.surface?.state
  switch (verb) {
    case 'expand': return { prop: 'level', step: 1 }
    case 'collapse': return { prop: 'level', step: -1 }
    case 'resetSize': return { prop: 'level', to: 'reset' }
    case 'dock': return { prop: 'placement', to: { kind: 'dock' } }
    case 'float': return { prop: 'placement', to: { kind: 'float' } }
    case 'showAsSheet': return { prop: 'placement', to: { kind: 'sheet' } }
    case 'putAway': return { prop: 'placement', to: { kind: 'launcher' } }
    case 'bringBack': return { prop: 'placement', to: { kind: 'back' } }
    case 'focus': return { prop: 'emphasis', to: 'lens' }
    case 'exitFocus': return { prop: 'emphasis', to: 'none' }
    case 'fullscreen': return { prop: 'emphasis', to: 'fullscreen' }
    case 'exitFullscreen': return { prop: 'emphasis', to: 'none' }
    case 'makePrimary': return { prop: 'primary', on: true }
    case 'back': return { prop: 'primary', on: false }
    case 'follow': return { prop: 'binding', to: 'follow' }
    case 'hold': return { prop: 'binding', to: 'hold' }
    case 'bringToFront': return { prop: 'front' }
    case 'moveUp': return s?.placement.kind === 'stack' ? { prop: 'order', to: Math.max(0, s.placement.index - 1) } : null
    case 'moveDown': return s?.placement.kind === 'stack' ? { prop: 'order', to: s.placement.index + 1 } : null
    case 'close': return { prop: 'open', to: false }
    case 'reopen': return { prop: 'open', to: true }
    case 'removeFromWorkspace': return { prop: 'exists', to: false }
    default: return null
  }
}

const levelOf = (t: ActionTarget): Level => t.surface!.state.level.override ?? t.surface!.state.level.auto
const step = (t: ActionTarget, by: 1 | -1): Level | null => {
  const levels = t.surface!.caps.levels
  for (let i = LEVELS.indexOf(levelOf(t)) + by; i >= 0 && i < LEVELS.length; i += by) if (levels.has(LEVELS[i])) return LEVELS[i]
  return null
}

/** What a surface's capabilities and state say of `verb` (no host). */
export type SurfaceAvailableFn = (verb: SurfaceVerb, t: ActionTarget, ctx: ActionCtx) => Availability

/** The rule before P1: absent where the verb's target is not in the
 *  surface's capabilities for this class; disabled, with why, where it is but
 *  not now. */
export const declaredAvailable: SurfaceAvailableFn = (verb, t, ctx) => {
  const sf = t.surface
  if (!sf) return ABSENT
  const { state: s, caps } = sf
  const places = caps.placementsBy[ctx.cls]
  const at = s.placement.kind
  const binding = s.binding
  const yes = (b: boolean) => (b ? AVAILABLE : ABSENT)
  switch (verb) {
    case 'expand': return step(t, 1) ? AVAILABLE : ABSENT
    case 'collapse': return step(t, -1) ? AVAILABLE : ABSENT
    case 'resetSize': return yes(!!s.level.override)
    case 'dock': return yes(places.has('dock') && at !== 'dock' && at !== 'launcher')
    case 'float': return yes(places.has('float') && at !== 'float' && at !== 'launcher')
    case 'showAsSheet': return yes(ctx.cls !== 'wide' && places.has('sheet') && at !== 'sheet')
    case 'putAway': return yes(caps.putAway && at !== 'launcher')
    case 'bringBack': return yes(at === 'launcher')
    case 'focus': return yes(caps.focusable && s.emphasis === 'none')
    case 'exitFocus': return yes(s.emphasis === 'lens')
    case 'fullscreen': return yes(caps.fullscreen && s.emphasis !== 'fullscreen')
    case 'exitFullscreen': return yes(s.emphasis === 'fullscreen')
    case 'makePrimary': return yes(caps.primaryable && at === 'dock')
    case 'back': return ABSENT                                  // needs the workspace's previous primary (P1)
    case 'follow': return s.kind !== 'section' || !caps.canFollow ? ABSENT : binding.mode === 'following' ? ABSENT : AVAILABLE
    case 'hold': return s.kind !== 'section' || !caps.canFollow ? ABSENT : binding.mode === 'held' ? ABSENT : AVAILABLE
    case 'keepAsWindow': return s.kind !== 'section' || binding.mode !== 'following' ? ABSENT
      : binding.current ? AVAILABLE : disabled('It shows nothing yet: read a post first')
    case 'bringToFront': return yes(at === 'float')
    case 'moveUp': return at !== 'stack' ? ABSENT : s.placement.kind === 'stack' && s.placement.index === 0 ? disabled('It is first already') : AVAILABLE
    case 'moveDown': return yes(at === 'stack')
    case 'close': return yes(caps.closable && s.open)
    case 'reopen': return yes(!s.open)
    case 'removeFromWorkspace': return yes(s.kind !== 'conversation' && s.kind !== 'lens' && s.kind !== 'launcher-tile')
    default: return ABSENT                                      // tidy, newFollower: workspace.ts
  }
}

let surfaceAvailable: SurfaceAvailableFn = declaredAvailable
/** P1's available(), once merged, replaces the declared rule here. */
export function useSurfaceAvailable(fn: SurfaceAvailableFn) { surfaceAvailable = fn }

/** A host's say over `id`, if the target has a host. */
export function hostAvailable(id: ActionId, t: ActionTarget): Availability | null {
  const host = hostOf(t)
  if (!host) return null
  const op = host[id]
  if (!op) return ABSENT
  return op.off ? disabled(op.off) : AVAILABLE
}

/** The verbs that move a surface: the Change each is, or the host's function. */
const MOVES: readonly SurfaceVerb[] = [
  'makePrimary', 'back', 'focus', 'exitFocus', 'fullscreen', 'exitFullscreen', 'float', 'dock', 'showAsSheet',
  'expand', 'collapse', 'resetSize', 'putAway', 'bringBack', 'follow', 'hold', 'keepAsWindow',
  'bringToFront', 'moveUp', 'moveDown', 'close', 'reopen', 'removeFromWorkspace',
]

function surfaceDef(verb: SurfaceVerb): ActionDef {
  return def(verb, {
    plane: 'surface', writes: 'placement',
    available(t, ctx) {
      const h = hostAvailable(verb, t)
      if (h) return h
      if (t.surface) return surfaceAvailable(verb, t, ctx)
      return objectAvailable(verb, t)
    },
    run(t, ctx) {
      const op = hostOf(t)?.[verb]
      if (op) return op.run()
      if (!t.surface) return objectRun(verb, t)
      if (verb === 'keepAsWindow') {
        const b = t.surface.state.binding
        if (b.mode === 'following' && b.current) ops.object.float(b.current.address, ops.anchorOf(b.current.address))
        return
      }
      const c = changeOf(verb, t)
      if (!c) throw new Error(`${verb}: no change for this surface`)
      const out = ctx.apply(t.surface.id, c)
      if (!out.ok) throw new Error(out.reason)
    },
  })
}

/* An object shown inside a surface (a chart in a post, a search hit) is not
   a surface yet: Float, Make primary and Focus make it one, exactly as the
   object row does today (objects/actions.ts act). */
const OBJECT_VERBS: Partial<Record<SurfaceVerb, keyof typeof ops.object>> = { float: 'float', makePrimary: 'primary', focus: 'focus' }
const objectAvailable = (verb: SurfaceVerb, t: ActionTarget): Availability => {
  const k = t.resource?.kind
  if (!k || !OBJECT_VERBS[verb] || k === 'workspace' || k === 'conversation') return ABSENT
  return verb === 'float' && k === 'post' ? ABSENT : AVAILABLE
}
const objectRun = (verb: SurfaceVerb, t: ActionTarget) => {
  const m = OBJECT_VERBS[verb]
  if (!m || !t.resource) throw new Error(`${verb}: nothing to do`)
  ops.object[m](t.resource.address, ops.anchorOf(t.resource.address))
}

/** Host-only arrangement verbs: what today's docked section offers by its
 *  own functions (split, fit, merge), and Look and Present, which its menu
 *  draws as columns. Absent with no host. */
function hostDef(id: Extract<SharedVerb, 'split' | 'fit' | 'merge' | 'present' | 'filter' | 'search'>): ActionDef {
  return def(id, {
    plane: id === 'search' ? 'resource' : 'surface', writes: id === 'search' || id === 'filter' ? 'none' : 'placement',
    available: (t) => hostAvailable(id, t) ?? ABSENT,
    run: (t) => { const op = hostOf(t)?.[id]; if (!op) throw new Error(`${id}: not offered here`); op.run() },
  })
}

/** Every surface verb, in the order T2 lists them within a group. */
export function surfaceDefs(): ActionDef[] {
  return [
    ...MOVES.map(surfaceDef),
    hostDef('split'), hostDef('fit'), hostDef('merge'),
    hostDef('search'), hostDef('filter'), hostDef('present'),
  ]                                                             // settings (Look): workspace.ts
}
