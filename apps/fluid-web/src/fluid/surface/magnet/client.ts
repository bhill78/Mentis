/* THE MAGNET ACTIONS, BOUND TO THE APP (part P7): the workspace's Magnet
 * clients (workspace/place.ts createMagnet, patchShared, forgetMagnet),
 * nav's toasts, the store's conversation names and the Magnet's view state.
 * Bound once by appOps.ts wireActions. */

import { useSyncExternalStore } from 'react'
import { CLIENT_HEADERS } from '../../../api'
import { fluidFetch } from '../../http'
import * as nav from '../../nav'
import { newOp, store } from '../../store'
import { workspace } from '../../workspace/place'
import { ops as appOps } from '../actions/providers/ops'
import { stateIn } from '../transition'
import { setViewState, forgetSurface } from '../viewState'
import { classNow } from '../../frame/narrow'
import { removeQuestion } from '../chrome'
import type { MagnetConfig, MagnetConfigChange, MagnetId, MagnetSeed } from './types'
import { MAGNET_CHOICES } from './choices'
import { existingFor, newMagnetZone, setUpChange, type TabId } from './model'
import { bindMagnetOps, type MagnetOps } from './provider'
import { adapters, live } from './runtime'
import { createActivations, type ActivationKey, type ActivationNow } from './activation'
import { chooseWorkspaceFor } from '../../workspaces/Chooser'

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

/* -- its quick summary card: one open at a time, held here, not in the arrangement -- */

export type PeekHow = 'hover' | 'pinned'
let peeked: { id: string; how: PeekHow } | null = null
const peekFns = new Set<() => void>()
const peekSubscribe = (fn: () => void) => { peekFns.add(fn); return () => { peekFns.delete(fn) } }
export const usePeeked = (id: string): PeekHow | null => useSyncExternalStore(peekSubscribe, () => (peeked?.id === id ? peeked.how : null))
export function openPeek(id: string, how: PeekHow) {
  if (peeked?.id === id && (peeked.how === how || how === 'hover')) return
  peeked = { id, how }
  peekFns.forEach((fn) => fn())
}
/** Close the card (only `id`'s, when given; only a hover's, when `hover`). */
export function closePeek(id?: string, hover = false) {
  if (!peeked || (id && peeked.id !== id) || (hover && peeked.how !== 'hover')) return
  peeked = null
  peekFns.forEach((fn) => fn())
}

/* -- the editor's draft: working state, kept by the Magnet (its resource), not
   view state (viewState.ts), so it survives every move of the surface -------- */

const drafts = new Map<string, MagnetSeed>()
const draftFns = new Set<() => void>()
const draftSubscribe = (fn: () => void) => { draftFns.add(fn); return () => { draftFns.delete(fn) } }
export const useDraft = (id: string): MagnetSeed | undefined => useSyncExternalStore(draftSubscribe, () => drafts.get(id))
export function setDraft(id: string, d: MagnetSeed | null) {
  if (d) drafts.set(id, d)
  else drafts.delete(id)
  draftFns.forEach((fn) => fn())
}

/** One level up from the disc, so its pane can show what was asked. */
function openPast(id: MagnetId) {
  const s = stateIn(workspace.surfaceCtx(), id)
  if (s && (s.level.override ?? s.level.auto) === 'icon') workspace.apply(id, { prop: 'level', to: 'compact' })
}

/** The editor's save: the named facets of the SAME config, through
 *  magnet.reconfigure. Answers the config now kept, or throws with why not. */
export async function saveConfig(id: MagnetId, change: MagnetConfigChange): Promise<MagnetConfig> {
  try {
    const kept = await workspace.reconfigureMagnet(id, change)
    nav.toast({ text: 'Saved what this magnet collects. It is the same magnet, where it was.' })
    return kept
  } catch (e) {
    const why = refusalOf(e)
    nav.toast({ text: `Not saved: ${why}` })
    throw new Error(why)
  }
}

const refusalOf = (e: unknown): string => {
  const r = e as Error & { reason?: { message?: string } }
  return r.reason?.message ?? r.message ?? 'It could not be done.'
}

/* -- Activate: one press, one key (activation.ts), its door here ------------- */

const magnetDoor = (id: MagnetId, verb: string, body: unknown) => fluidFetch(`/fluid/api/magnets/${encodeURIComponent(id)}/${verb}`, {
  method: 'POST', headers: { ...CLIENT_HEADERS, 'Content-Type': 'application/json' }, body: JSON.stringify(body),
})
const KEY = 'mentis:magnet-activation:'

export const activations = createActivations({
  async post(id, key) {
    const res = await magnetDoor(id, 'activate', key)
    return { status: res.status, body: await res.json().catch(() => null) }
  },
  me: () => store.loadMe(),
  newKey: newOp,
  keptKey(id) {
    try {
      const k = JSON.parse(localStorage.getItem(KEY + id) ?? 'null') as ActivationKey | null
      return k && typeof k.author === 'string' && typeof k.op === 'string' ? { author: k.author, op: k.op } : null
    } catch { return null }
  },
  keepKey(id, key) {
    try {
      if (key) localStorage.setItem(KEY + id, JSON.stringify(key))
      else localStorage.removeItem(KEY + id)
    } catch { /* private mode: it lasts as long as this answer does */ }
  },
})
export const useActivation = (id: MagnetId): ActivationNow => useSyncExternalStore(activations.subscribe, () => activations.now(id))

async function pressActivate(id: MagnetId) {
  const started = activations.press(id)
  nav.toast({ text: 'Activating: one page from what it reads…' })
  const now = await started
  const r = now.result
  nav.toast(r
    ? { text: now.words ?? '', action: { label: 'Read the result', run: () => nav.read(r.conversation, r.post, null) } }
    : { text: now.words ?? 'It could not be done.' })
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
    setViewState(magnetView(id), 'panel', 'results')
    openPast(id)
  },
  configure(id, at) {
    closePeek()
    setViewState(magnetView(id), 'panel', 'configure')
    setViewState(magnetView(id), 'configAt', at)
    openPast(id)
  },
  peek(id) {
    /* a disc in a window: the card at its corner; anywhere else (a section,
       a card in the stack) its pane's Summary, one level up */
    const s = stateIn(workspace.surfaceCtx(), id)
    if (s && (s.level.override ?? s.level.auto) === 'icon' && s.placement.kind === 'float') { openPeek(id, 'pinned'); return }
    setViewState(magnetView(id), 'panel', 'summary')
    openPast(id)
  },
  look(id) {
    closePeek()
    setViewState(magnetView(id), 'look', true)
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
    closePeek(id)
    setDraft(id, null)
    live.forget(id)
    nav.toast({ text: `Removed the ${name} magnet from this workspace.` })
  },
  adapters: () => adapters,
  toWorkspace: (what) => chooseWorkspaceFor(what),
  activate: pressActivate,
  activating: (id) => activations.now(id).phase === 'running',
  async setUpActivation(id) {
    const config = workspace.arr.magnets?.[id]
    const change = config && setUpChange(config)
    if (!change) return
    try {
      await workspace.reconfigureMagnet(id, change)
      nav.toast({ text: 'Manual activation is set up on this same magnet. Nothing runs until you press Activate.' })
    } catch (e) {
      const why = refusalOf(e)
      nav.toast({ text: `It was not set up: ${why}` })
      throw new Error(why)
    }
  },
  async ownConversation(id) {
    const res = await magnetDoor(id, 'conversation', { author: await store.loadMe() })
    const got = await res.json().catch(() => null) as { conversation?: string; error?: string; reason?: { message?: string } } | null
    if (!res.ok || !got?.conversation) {
      const why = got?.reason?.message ?? got?.error ?? res.statusText
      nav.toast({ text: `Its Conversation could not be opened: ${why}` })
      throw new Error(why)
    }
    return got.conversation
  },
}

export const wireMagnets = () => bindMagnetOps(magnetAppOps)

/** What is closed on this browser device in this class, redrawn when a Close
 *  or Reopen changes it (it is not the arrangement, so useArr does not hear it). */
export const useClosedHere = (): ReadonlySet<string> => useSyncExternalStore(workspace.subscribe, () => workspace.closed[classNow()])
