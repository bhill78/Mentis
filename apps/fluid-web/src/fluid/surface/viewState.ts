/* SURFACE TENSION: VIEW STATE (plan adm-15951b3daacc §3.4; API in P0,
 * implementation in P1b).
 *
 * View state -- scroll, the open fold, the current card, a tab -- belongs to
 * a (surface, resource) pair, not to a component, so it survives the
 * surface being docked, floated, collapsed or redrawn. Working state
 * (drafts, form edits) does NOT go here: it stays keyed by resource
 * (drafts.ts, formsStorage.ts).
 *
 * This is the tiny implementation the contract needs: memory per tab, the
 * last 8 resources per surface. P1b mirrors it to sessionStorage
 * 'mentis.fluid.view:<placeKey>'. */

import { useCallback, useSyncExternalStore } from 'react'
import type { ZoneId } from './types'

export type ViewKey = { surface: ZoneId; resource: string }          // view state is per (surface, resource)

/** Resources remembered per surface (r3 §1.1.2); the oldest is forgotten. */
export const VIEW_RESOURCES = 8

/* surface -> resource -> part -> value; each surface's resources in use order. */
const held = new Map<ZoneId, Map<string, Map<string, unknown>>>()
const fns = new Set<() => void>()
const subscribe = (fn: () => void) => { fns.add(fn); return () => { fns.delete(fn) } }

export function viewState<T>(key: ViewKey, part: string): T | undefined {
  return held.get(key.surface)?.get(key.resource)?.get(part) as T | undefined
}

function setViewState(key: ViewKey, part: string, v: unknown) {
  let resources = held.get(key.surface)
  if (!resources) held.set(key.surface, (resources = new Map()))
  const parts = resources.get(key.resource) ?? new Map<string, unknown>()
  resources.delete(key.resource)
  resources.set(key.resource, parts.set(part, v))
  while (resources.size > VIEW_RESOURCES) resources.delete(resources.keys().next().value!)
  fns.forEach((fn) => fn())
}

export function useViewState<T>(key: ViewKey, part: string, initial: T): [T, (v: T) => void] {
  const { surface, resource } = key
  const get = () => viewState<T>({ surface, resource }, part)
  const got = useSyncExternalStore(subscribe, get, get)
  const set = useCallback((v: T) => setViewState({ surface, resource }, part, v), [surface, resource, part])
  return [got === undefined ? initial : got, set]
}

/** Only on Remove from workspace (exists:false), never local Close. */
export function forgetSurface(surface: ZoneId): void {
  if (held.delete(surface)) fns.forEach((fn) => fn())
}
