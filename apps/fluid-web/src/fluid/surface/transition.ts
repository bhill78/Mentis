/* SURFACE TENSION: transition() (plan §3.3; part P1).
 *
 * The one pure change a surface goes through. It wraps what focus/model.ts
 * already does -- floatOut, dockFloat, dockBack, dockSection, the
 * conversation's minimize/restore, makePrimary/swapBack, toFront, moveFloat,
 * setMinimized -- and adds the level, the class's device record, the
 * browser device's Close and the tab's emphasis. Each call changes ONE
 * property of ONE surface; the tree reflowing and floats clamping are the
 * workspace's consequences, not second changes. The zone id never changes.
 *
 * Which layer an outcome writes:
 *   - `shared`: the arrangement (every class reads it). Placement and level
 *     in wide, primary, binding, Remove from workspace. Never a device record.
 *   - `device`: in medium/compact, placement, level and order write only the
 *     class's DevicePlacement (`arr` is returned identical); Close/Reopen
 *     write only the browser device's closed set.
 *   - `session`: emphasis (lens, full screen), this tab only.
 * Nothing here writes the record.
 *
 * The change is made on the page the context names (`ctx.page`; null: This
 * post), read and written back through focus/page.ts's page views. */

import * as nav from '../nav'
import {
  closeFloat, clearOf, dockBack, dockFloat, dockSection, editZone, floatOut, floatsAlone, makePrimary, minimize, moveFloat, primaryOf,
  restore as bringBackConversation, setMinimized, swapBack, toFront, withFocus, focusOf,
} from '../focus/model'
import { THIS_POST, pageIn, pageView, withPageView } from '../focus/page'
import { CONVERSATION_ID, MAX_FLOATS, MIN_FLOAT_H, MIN_FLOAT_W } from '../focus/types'
import type { Arr, PlaceKind } from '../workspace/place'
import { followSlot, removeLeaf, withFeed, zone as newZone, type Node, type Zone } from '../workspace/tree'
import { MAGNET_SHOW, capabilitiesOf, placementsIn } from './capabilities'
import { levelShown, stepLevel } from './levels'
import { findSurface, orderIn, fallbackPlace, stateOf, type Found } from './state'
import type {
  Change, DeviceLocalState, DevicePlacement, Level, Outcome, PlacementKind, PlacementTarget, Rect, SurfaceCapabilities,
  SurfaceCtx, SurfaceState, TransitionFn, ZoneId,
} from './types'

/** The stored-float limit, said where a float is asked for (plan §3.7). */
export const FLOAT_LIMIT_MESSAGE = '12 stored windows already use every slot; locally closed windows still count. Reopen one or Remove one from the workspace.'

type Emphasis = SurfaceState['emphasis']
type DevicePlace = DevicePlacement['place'][ZoneId]

/** A surface's state as the context sees it: on its page, with this tab's emphasis. */
export function stateIn(ctx: SurfaceCtx, id: ZoneId): SurfaceState | null {
  const s = stateOf(viewOf(ctx), id, ctx.cls, ctx.device, ctx.deviceLocal)
  if (!s) return null
  const placement = s.placement.kind === 'dock' ? { ...s.placement, page: ctx.page } : s.placement
  return { ...s, placement, emphasis: ctx.session.emphasis[id] ?? 'none' }
}
const pageOf = (ctx: SurfaceCtx) => ctx.page ?? THIS_POST
/** The page the context names, as the model reads it. */
export const viewOf = (ctx: SurfaceCtx): Arr => pageView(ctx.arr, pageOf(ctx))

const no = (reason: string): Outcome => ({ ok: false, reason })

/** What Hold would keep: the post read now, or null. The one global read
 *  shared by transition() and available() (see Hold below; opr-991df732c969). */
export const holdable = (): string | null => nav.snapshot().reading ?? null
export const NOTHING_TO_HOLD = 'Nothing is being read to hold.'
const nameOf = (z: Zone) => z.name ?? (z.show === 'conversation' ? 'The conversation' : 'The section')

/** A float's rectangle when none was asked for: at the right of the room,
 *  stepped clear of a window already there. (P6's coordinator refines it.) */
export function defaultFloatRect(view: Arr, room: { w: number; h: number }): Rect {
  const w = Math.max(MIN_FLOAT_W, Math.min(480, Math.round(room.w * 0.4)))
  const h = Math.max(MIN_FLOAT_H, Math.min(560, Math.round(room.h * 0.7)))
  return clearOf({ x: Math.max(0, room.w - w - 24), y: 24, w, h }, view.focus?.floats ?? [])
}

/** The tree without leaf `id`; the only leaf gives way to the product's
 *  empty leaf following what is read, so a page is never without a tree. */
const withoutLeaf = (tree: Node, id: string): Node => (tree.type === 'zone' ? newZone(null, followSlot()) : removeLeaf(tree, id))

export function transition(ctx: SurfaceCtx, id: ZoneId, change: Change): Outcome {   // PURE (one known exception: Hold, below); P1
  const view = viewOf(ctx)
  const s = stateIn(ctx, id)
  const found = findSurface(view, id)
  if (!s || !found) return no('That surface is not on this page.')
  if (!s.open && change.prop !== 'open' && change.prop !== 'exists') return no(`${nameOf(found.zone)} is closed on this device; reopen it first.`)
  const caps = ctx.caps(id)
  const name = nameOf(found.zone)
  const page = pageOf(ctx)

  const shared = (next: Arr, label: string, unchanged: string): Outcome =>
    next === view ? no(unchanged) : { ok: true, arr: withPageView(ctx.arr, page, next), label, layer: 'shared' }
  const device = (record: DevicePlacement, label: string): Outcome =>
    ({ ok: true, arr: ctx.arr, device: { ...record, updatedAt: Date.now() }, label, layer: 'device' })
  const record = (): DevicePlacement => ctx.device ?? { order: [], place: {}, level: {}, updatedAt: 0 }

  switch (change.prop) {
    case 'placement': return placement(change.to)
    case 'rect': {
      if (ctx.cls !== 'wide' || found.wide.kind !== 'float') return no('Only a window has a rectangle to move or size.')
      return shared(moveFloat(view, found.wide.floatId, change.rect), `Moved ${name}.`, `${name} is already there.`)
    }
    case 'front': {
      if (ctx.cls !== 'wide' || found.wide.kind !== 'float') return no('Only a window comes to the front.')
      return shared(toFront(view, found.wide.floatId), `Brought ${name} to the front.`, `${name} is already in front.`)
    }
    case 'level': return level('to' in change ? change.to : change.step)
    case 'emphasis': return emphasis(change.to)
    case 'binding': {
      if (!caps.canFollow || !found.zone.slot || found.wide.kind !== 'dock' || found.wide.in !== 'tree')
        return no('Follow and Hold are for sections in this build.')
      const slot = found.zone.slot
      if (change.to === 'follow') {
        if (change.source !== undefined && change.source !== 'reading') return no('Following another surface’s selection is not in this build.')
        if (slot.follow && !slot.pin) return no(`${name} already follows what you read.`)
        return shared(editZone(view, id, (z) => ({ ...z, slot: withFeed(slot, 'reading') })), `${name} follows what you read.`, `${name} already follows.`)
      }
      if (s.binding.mode === 'held') return no(`${name} already holds what it shows.`)
      /* Hold keeps what the source selects now: the post read. KNOWN EXCEPTION
         TO PURITY: the one global read in transition(), because SurfaceCtx
         has no way to resolve a binding's source yet. available() makes the
         same read (holdable) so the two agree. To be removed when SurfaceCtx
         gains a binding resolver: discovered work opr-991df732c969. */
      const reading = holdable()
      if (!reading) return no(NOTHING_TO_HOLD)
      return shared(editZone(view, id, (z) => ({ ...z, slot: withFeed(slot, 'post', reading) })), `${name} holds the post it shows.`, `${name} already holds.`)
    }
    case 'primary': {
      if (!caps.primaryable || s.placement.kind === 'launcher') return no(`${name} has no primary place to take.`)
      if (change.on) {
        if (primaryOf(view) === id) return no(`${name} is already primary.`)
        return shared(makePrimary(view, id), `${name} is primary.`, `${name} cannot be made primary here.`)
      }
      return shared(swapBack(view), 'Back to the previous primary.', 'Nothing earlier to go back to.')
    }
    case 'order': {
      if (ctx.cls === 'wide') return no('Order is the stack’s, in medium and compact.')
      const order = orderIn(view, ctx.device)
      const from = order.indexOf(id)
      const to = Math.max(0, Math.min(order.length - 1, Math.round(change.to)))
      if (from === to) return no(`${name} is already there.`)
      order.splice(from, 1)
      order.splice(to, 0, id)
      return device({ ...record(), order }, `Moved ${name} ${to < from ? 'up' : 'down'}.`)
    }
    case 'open': {
      const closed = new Set(ctx.deviceLocal.closed)
      if (!change.to) {
        if (!caps.closable) return no(`${name} cannot be closed.`)
        closed.add(id)
      } else {
        if (s.open) return no(`${name} is already open.`)
        closed.delete(id)
      }
      const deviceLocal: DeviceLocalState = { closed }
      return { ok: true, arr: ctx.arr, deviceLocal, label: change.to ? `Reopened ${name}.` : `Closed ${name} here.`, layer: 'device' }
    }
    case 'exists': {
      if (found.zone.show === 'conversation') return no('The conversation is this place’s own and cannot be removed; close it here or put it away.')
      const w = found.wide
      if (w.kind === 'float') return shared(closeFloat(view, w.floatId), `Removed ${name} from the workspace.`, `${name} is already gone.`)
      if (w.kind === 'dock' && w.in === 'column') return shared(withFocus(view, { ...focusOf(view), column: undefined }), `Removed ${name} from the workspace.`, `${name} is already gone.`)
      if (w.kind === 'dock') return shared({ ...view, tree: withoutLeaf(view.tree, id) }, `Removed ${name} from the workspace.`, `${name} is already gone.`)
      return no(`${name} cannot be removed from where it is.`)
    }
  }

  function placement(to: PlacementTarget): Outcome {
    const may = placementsIn(caps, ctx.cls)
    if (ctx.cls !== 'wide') return devicePlacement(to, may)
    if (s!.emphasis === 'lens') return no('Exit focus first: the lens is not a place.')
    const w = found!.wide
    const room = ctx.viewport
    switch (to.kind) {
      case 'float': {
        if (!may.has('float')) return no(`${name} does not float.`)
        if (w.kind === 'float') return no(`${name} already floats.`)
        if ((view.focus?.floats?.length ?? 0) >= MAX_FLOATS) return no(FLOAT_LIMIT_MESSAGE)
        const rect = to.rect ?? defaultFloatRect(view, room)
        if (w.kind === 'dock' && w.in === 'tree') {
          /* the only section: `caps` already said whether it may (capsFor, floatsAlone) */
          const alone = view.tree.type === 'zone'
          return shared(floatOut(view, id, rect, { alone }),
            alone ? `${name} floats; an empty section following what you read takes its place.` : `${name} floats; the sections beside it took its room.`,
            `${name} cannot float from here.`)
        }
        if (id !== CONVERSATION_ID) return no(`${name} cannot float from here.`)
        /* The conversation, from the column or the launcher, at the rectangle asked. */
        const out = w.kind === 'launcher' ? bringBackConversation(view, 'float', room) : bringBackConversation(minimize(view, Date.now()), 'float', room)
        const fl = out.focus?.floats?.find((f) => f.zone.id === CONVERSATION_ID)
        return shared(fl && to.rect ? moveFloat(out, fl.id, to.rect) : out, 'The conversation floats.', 'The conversation cannot float from here.')
      }
      case 'dock': {
        if (!may.has('dock')) return no(`${name} does not dock.`)
        const where = to.where ?? 'right'
        if (w.kind === 'float') {
          if (to.near) return shared(dockFloat(view, w.floatId, to.near, where), `Docked ${name}.`, `${name} cannot dock there.`)
          /* The conversation with nowhere it came from goes back to its column. */
          if (id === CONVERSATION_ID && !w.origin && !view.focus?.column) return shared(closeFloat(view, w.floatId), 'The conversation is back in its column.', 'The conversation cannot dock.')
          return shared(dockBack(view, w.floatId), `Docked ${name} where it was.`, `${name} cannot dock back.`)
        }
        if (w.kind === 'launcher') return shared(bringBackConversation(view, 'leaf', room), 'The conversation is back as a section.', 'The conversation cannot come back here.')
        if (w.kind === 'dock' && to.near) return shared(dockSection(view, id, to.near, where), `Moved ${name}.`, `${name} cannot dock there.`)
        return no(`${name} is already docked.`)
      }
      case 'column': {
        if (id !== CONVERSATION_ID) return no('Only the conversation has a column.')
        if (w.kind === 'dock' && w.in === 'column') return no('The conversation is already in its column.')
        if (view.focus?.column) return no('Something else is in the column; make the conversation primary instead.')
        if (w.kind === 'float') return shared(closeFloat(view, w.floatId), 'The conversation is back in its column.', 'The conversation cannot go back.')
        if (w.kind === 'launcher') return shared(bringBackConversation(view, 'column', room), 'The conversation is back in its column.', 'The conversation cannot come back.')
        return shared({ ...view, tree: withoutLeaf(view.tree, id) }, 'The conversation is back in its column.', 'The conversation cannot go back.')
      }
      case 'launcher': {
        if (!caps.putAway || !may.has('launcher')) return no(`${name} has no launcher to go to here.`)
        if (w.kind === 'launcher') return no(`${name} is already put away.`)
        return shared(minimize(view, Date.now()), `${name} is put away; bring it back from the launcher.`, `${name} cannot be put away.`)
      }
      case 'back': {
        if (w.kind !== 'launcher') return no(`${name} is not put away.`)
        return shared(bringBackConversation(view, undefined, room), `${name} is back where it was.`, `${name} cannot come back.`)
      }
      default: return no('Stacks and sheets are for medium and compact screens.')
    }
  }

  function devicePlacement(to: PlacementTarget, may: ReadonlySet<PlacementKind>): Outcome {
    const now = ctx.device?.place[id] ?? fallbackPlace(found!.wide, ctx.cls as 'medium' | 'compact')
    const want: DevicePlace | null = to.kind === 'dock' ? 'dock'
      : to.kind === 'column' ? (id === CONVERSATION_ID ? (ctx.cls === 'medium' ? 'dock' : 'stack') : null)
      : to.kind === 'stack' || to.kind === 'sheet' || to.kind === 'launcher' ? to.kind
      : to.kind === 'back' ? (now === 'launcher' ? backFrom(found!) : null)
      : null
    if (to.kind === 'float') return no('Windows float only on a wide screen.')
    if (to.kind === 'back' && now !== 'launcher') return no(`${name} is not put away.`)
    if (!want || !may.has(want)) return no(`${name} cannot be ${want === 'dock' ? 'docked' : want ?? 'placed there'} on this screen.`)
    if (to.kind === 'launcher' && !caps.putAway) return no(`${name} cannot be put away.`)
    const index = to.kind === 'stack' ? to.index : undefined
    if (want === now && index === undefined) return no(`${name} is already there.`)
    const base = record()
    let order = base.order
    if (index !== undefined) {
      order = orderIn(view, ctx.device).filter((x) => x !== id)
      order.splice(Math.max(0, Math.min(order.length, index)), 0, id)
    }
    return device({ ...base, order, place: { ...base.place, [id]: want } }, labelOf(want))
  }
  /* Brought back in medium/compact: where its wide placement suggests, never the launcher again. */
  function backFrom(f: Found): DevicePlace {
    const p = fallbackPlace(f.wide, ctx.cls as 'medium' | 'compact')
    return p === 'launcher' ? (ctx.cls === 'medium' ? 'dock' : 'stack') : p
  }
  function labelOf(p: DevicePlace): string {
    return p === 'launcher' ? `${name} is put away on this screen.` : p === 'sheet' ? `${name} opens as a sheet.` : p === 'dock' ? `Docked ${name}.` : `${name} is in the stack.`
  }

  function level(to: Level | 'reset' | 1 | -1): Outcome {
    const st = s!
    const now = levelShown(st.level)
    let want: Level | undefined
    if (to === 'reset') {
      if (!st.level.override) return no(`${name} is already at its automatic size.`)
      want = undefined
    } else if (to === 1 || to === -1) {
      const next = stepLevel(now, to, caps.levels)
      if (!next) return no(to === 1 ? `${name} is as large as it goes here; open it as a workspace instead.` : `${name} is as small as it goes.`)
      want = next
    } else {
      if (!caps.levels.has(to)) return no(`${name} has no ${to} level.`)
      if (st.level.override === to) return no(`${name} is already ${to}.`)
      want = to
    }
    const label = want === undefined ? `${name} is back to its automatic size.` : to === 1 ? `Expanded ${name}.` : to === -1 ? `Collapsed ${name}.` : `${name} is ${want}.`
    if (ctx.cls !== 'wide') {
      const base = record()
      const { [id]: _was, ...rest } = base.level
      return device({ ...base, level: want ? { ...rest, [id]: want } : rest }, label)
    }
    return shared(wideLevel(found!, want), label, `${name} cannot change size where it is.`)
  }
  /* Wide: the zone's `level`; a non-magnet window folds to its tab at icon (`min`). */
  function wideLevel(f: Found, want: Level | undefined): Arr {
    const w = f.wide
    if (w.kind === 'launcher' || (w.kind === 'dock' && w.in === 'column')) return view
    const unset = (z: Zone): Zone => { const { level: _l, ...rest } = z; return rest }
    if (w.kind === 'float' && f.zone.show !== MAGNET_SHOW) {
      const folded = setMinimized(view, w.floatId, want === 'icon')
      return editZone(folded, id, (z) => (want && want !== 'icon' ? { ...z, level: want } : unset(z)))
    }
    return editZone(view, id, (z) => (want ? { ...z, level: want } : unset(z)))
  }

  function emphasis(to: Emphasis): Outcome {
    const now = s!.emphasis
    if (to === now) return no(to === 'none' ? `${name} is not in focus or full screen.` : `${name} is already ${to === 'lens' ? 'in focus' : 'full screen'}.`)
    if (to === 'lens' && !caps.focusable) return no(`${name} cannot be focused.`)
    if (to === 'fullscreen' && !caps.fullscreen) return no(`${name} has no full screen.`)
    /* One surface holds the lens, one the full screen: another's ends. */
    const kept = Object.entries(ctx.session.emphasis).filter(([k, v]) => k !== id && v !== 'none' && v !== to)
    const emphasisNext = Object.fromEntries(to === 'none' ? kept : [...kept, [id, to]]) as Record<ZoneId, Emphasis>
    const label = to === 'lens' ? `Focus on ${name}.` : to === 'fullscreen' ? `${name} is full screen.` : now === 'lens' ? 'Focus ended.' : 'Full screen ended.'
    return { ok: true, arr: ctx.arr, session: { emphasis: emphasisNext }, label, layer: 'session' }
  }
}
transition satisfies TransitionFn

/** A context's capabilities: each surface's, where it is in `cls` on `page`. */
export function capsFor(arr: Arr, page: string | null, cls: SurfaceCtx['cls'], device?: DevicePlacement, placeKind: PlaceKind = 'conversation'): (id: ZoneId) => SurfaceCapabilities {
  const view = pageView(arr, page ?? THIS_POST)
  return (id) => {
    const f = findSurface(view, id)
    const s = stateOf(view, id, cls, device)
    if (!f || !s) throw new Error(`no surface ${id} on this page`)
    const caps = capabilitiesOf(f.zone, s.placement)
    /* the only section of a page floats only where floatsAlone says (r3 §8 risk 2) */
    const sole = view.tree.type === 'zone' && f.wide.kind === 'dock' && f.wide.in === 'tree'
    if (!sole || !caps.placementsBy.wide.has('float') || floatsAlone(placeKind, pageIn(arr, page ?? THIS_POST), f.zone)) return caps
    const wide = new Set(caps.placementsBy.wide)
    wide.delete('float')
    return { ...caps, placementsBy: { ...caps.placementsBy, wide } }
  }
}
