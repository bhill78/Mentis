/* THE MAGNET ACTIONS, BOUND TO THE APP (part P7): the workspace's Magnet
 * clients (workspace/place.ts createMagnet, patchShared, forgetMagnet),
 * nav's toasts, the store's conversation names and the Magnet's view state.
 * Bound once by appOps.ts wireActions. */

import { useSyncExternalStore } from 'react'
import * as nav from '../../nav'
import { store } from '../../store'
import { workspace } from '../../workspace/place'
import { ops as appOps } from '../actions/providers/ops'
import { stateIn } from '../transition'
import { setViewState, forgetSurface } from '../viewState'
import { classNow } from '../../frame/narrow'
import { removeQuestion } from '../chrome'
import type { MagnetId } from './types'
import { MAGNET_CHOICES } from './choices'
import { existingFor, newMagnetZone, type TabId } from './model'
import { bindMagnetOps, type MagnetOps } from './provider'
import { adapters, live } from './runtime'

/** A Magnet's view-state key: its surface, and itself as the resource. */
export const magnetView = (id: string) => ({ surface: id, resource: 'magnet:' + id })

/* -- reveal: the one asked for, lit for a moment --------------------------- */

let revealed: { id: string; at: number } | null = null
const fns = new Set<() => void>()
const subscribe = (fn: () => void) => { fns.add(fn); return () => { fns.delete(fn) } }
export const useRevealed = (id: string): boolean => useSyncExternalStore(subscribe, () => revealed?.id === id && Date.now() - revealed.at < 1600)
function light(id: string) {
  revealed = { id, at: Date.now() }
  fns.forEach((fn) => fn())
  setTimeout(() => fns.forEach((fn) => fn()), 1700)
}

const refusalOf = (e: unknown): string => {
  const r = e as Error & { reason?: { message?: string } }
  return r.reason?.message ?? r.message ?? 'It could not be done.'
}

export const magnetAppOps: MagnetOps = {
  notHere: () => (workspace.kind === MAGNET_CHOICES.onlyIn && workspace.key ? null : MAGNET_CHOICES.notHere),
  config: (id) => workspace.arr.magnets?.[id],
  existing: (conversation) => existingFor(workspace.arr, conversation),
  async create(seed, name) {
    const cls = classNow()
    try {
      const made = await workspace.createMagnet(seed, newMagnetZone(name), {
        wideFallback: MAGNET_CHOICES.wideFallback,
        ...(cls !== 'wide' ? { scope: cls, presentation: { place: 'stack' as const, level: MAGNET_CHOICES.newLevel } } : {}),
      })
      nav.toast({ text: `Made a magnet of ${name}.` })
      return made
    } catch (e) {
      nav.toast({ text: `No magnet was made: ${refusalOf(e)}` })
      throw e
    }
  },
  reveal(id) {
    const ctx = workspace.surfaceCtx()
    const s = stateIn(ctx, id)
    if (!s) {
      nav.toast({ text: 'That magnet is on another Page of this workspace.' })
      return
    }
    if (!s.open) workspace.apply(id, { prop: 'open', to: true })
    if (s.placement.kind === 'float') workspace.apply(id, { prop: 'front' })
    light(id)
  },
  current() {
    if (workspace.kind !== 'conversation' || !workspace.key) return null
    return { conversation: workspace.key, name: store.conversations.get(workspace.key)?.name ?? 'Conversation' }
  },
  conversationName: (c) => store.conversations.get(c)?.name ?? 'Conversation',
  showTab(id: MagnetId, tab: TabId) {
    setViewState(magnetView(id), 'tab', tab)
    const s = stateIn(workspace.surfaceCtx(), id)
    if (s && (s.level.override ?? s.level.auto) === 'icon') workspace.apply(id, { prop: 'level', to: 'compact' })
  },
  async remove(id, name) {
    if (!appOps.confirm(removeQuestion(name))) return
    const cls = classNow()
    try {
      await workspace.patchShared({ op: 'remove', id }, cls === 'wide' ? undefined : { scope: cls })
      await workspace.forgetMagnet(id)
    } catch (e) {
      nav.toast({ text: `The magnet was not removed: ${refusalOf(e)}` })
      return
    }
    forgetSurface(id)
    live.forget(id)
    nav.toast({ text: `Removed the ${name} magnet from this workspace.` })
  },
  adapters: () => adapters,
}

export const wireMagnets = () => bindMagnetOps(magnetAppOps)

/** What is closed on this browser device in this class, redrawn when a Close
 *  or Reopen changes it (it is not the arrangement, so useArr does not hear it). */
export const useClosedHere = (): ReadonlySet<string> => useSyncExternalStore(workspace.subscribe, () => workspace.closed[classNow()])
