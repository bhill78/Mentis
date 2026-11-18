/* THE OPEN GRAPH SESSIONS OF THIS PAGE (addendum §1).
 *
 * One live graph per resolved Brain, held for as long as Quiet Chat's page
 * lives and no longer. The registry holds SESSIONS, by id; the browser's
 * history and the viewer store hold only ids and keys -- never a session, a
 * read, a camera, a credential or an environment address.
 *
 * WHAT A BRAIN KEY IS. The serving corpus identity (`/api/brain?identity=1`,
 * read by the page already), the page's own origin, and the development
 * server's pinned Brain choice where there is one. An identity that is not
 * known yet is NOT a key: it is a loading state, and a graph is never created
 * against a guessed one, so two different Brains can never share a session.
 *
 * Nothing here persists. A Brain change, a reload or the owner's unmount
 * disposes every session and tombstones its id, so an old history entry can
 * never attach to a new page's graph. */
import type { SpaceBrainKey, SpaceSession, SpaceSessionId } from './contract'
import { spaceSessions } from './provider'

/** The key for the Brain this page is serving, or null where its identity is
 *  not known yet. Pure, so it is checkable. */
export function spaceBrainKey(at: { corpusId?: string | null; origin: string; proxy?: string | null }): SpaceBrainKey | null {
  const id = (at.corpusId ?? '').trim()
  if (!id) return null
  return `${at.origin}|${at.proxy ?? ''}|${id}`
}

let seq = 0
/** A fresh session id, never reused within this page. */
export const nextSpaceSessionId = (): SpaceSessionId => `sp${++seq}`

const live = new Map<SpaceSessionId, SpaceSession>()
/** ids this page has closed: an old history entry naming one is expired, and
 *  a late detach, camera save or dispose for it is harmless. */
const closed = new Set<SpaceSessionId>()
let version = 0
const heard = new Set<() => void>()
const changed = () => { version++; heard.forEach((fn) => fn()) }

/** Every change to WHICH sessions exist (not to their views). */
export const subscribeSessions = (fn: () => void) => { heard.add(fn); return () => { heard.delete(fn) } }
export const sessionsVersion = () => version
export const sessionById = (id: SpaceSessionId): SpaceSession | null => live.get(id) ?? null
export const liveSessions = (): SpaceSession[] => [...live.values()]
export const sessionOfBrain = (key: SpaceBrainKey): SpaceSession | null =>
  [...live.values()].find((s) => s.brainKey === key) ?? null
export const isClosedSession = (id: SpaceSessionId) => closed.has(id)

/** The live graph of this Brain, created on the FIRST explicit Open only.
 *  Returns null where the graph module is not wired into this build. */
export function openSession(key: SpaceBrainKey): SpaceSession | null {
  const had = sessionOfBrain(key)
  if (had) return had
  const mod = spaceSessions()
  if (!mod) return null
  const s = mod.createSpaceSession({ id: nextSpaceSessionId(), brainKey: key })
  live.set(s.id, s)
  changed()
  return s
}

/** ONE RELEASE PATH (addendum §1, "Disposal"): explicit Close, the owner's
 *  unmount and a Brain identity change all come through here. Generic
 *  eviction never does: it parks instead (placement.ts). */
export function releaseSession(id: SpaceSessionId) {
  const s = live.get(id)
  if (!s) { closed.add(id); return }
  live.delete(id)
  closed.add(id)
  try { s.dispose() } finally { changed() }
}

/** Every session of a Brain that is no longer the one being served, and every
 *  session at all where `key` is null (identity unknown or changed). */
export function invalidateOtherBrains(key: SpaceBrainKey | null) {
  for (const s of [...live.values()]) if (!key || s.brainKey !== key) releaseSession(s.id)
}

/** The owner unmounting: nothing survives the page. */
export function releaseAllSessions() {
  for (const s of [...live.values()]) releaseSession(s.id)
}

/** Only for a check: an empty page again. */
export function forgetSessions() { live.clear(); closed.clear(); seq = 0; version = 0 }
