/* WHAT THIS TAB KNOWS OF THE WORKSPACES: the list, and each manifest it has read.
 * Beside the Fluid store and heard through it (`store.subscribe`, keys
 * `workspaces` and `workspace:<id>`), as an arrangement is. A manifest isn't in
 * the record, so no pulse moves it: it is what the door last answered.
 *
 * One manifest per workspace, and references only: a Magnet in three workspaces
 * is three lists naming one `mag-` id, with nothing of the Magnet copied here. */

import { useCallback, useSyncExternalStore } from 'react'
import { store } from '../store'
import {
  WorkspaceRefusal, addObject, createWorkspace, listWorkspaces, readWorkspace, removeObject, renameWorkspace, reorderObjects,
  type Manifest, type NewObject, type ObjectId, type Seed, type WorkspaceAnswer, type WorkspaceBrief, type WorkspaceId,
} from './client'

export interface HeldWorkspace {
  manifest: Manifest | null
  /** why there is none to use, or why the last change was refused */
  refusal: WorkspaceRefusal | null
  /** the last change was answered from its key: nothing was written again */
  replayed: boolean
}
export interface WorkspaceList { rows: WorkspaceBrief[] | null; refusal: WorkspaceRefusal | null }

const NONE: HeldWorkspace = { manifest: null, refusal: null, replayed: false }
const held = new Map<WorkspaceId, HeldWorkspace>()
let list: WorkspaceList = { rows: null, refusal: null }

const keep = (id: WorkspaceId, next: HeldWorkspace) => {
  held.set(id, next)
  store.notify('workspace:' + id)
}
const asRefusal = (e: unknown) => (e instanceof WorkspaceRefusal ? e : new WorkspaceRefusal('lost', null, null))

export const heldWorkspace = (id: WorkspaceId): HeldWorkspace => held.get(id) ?? NONE

export async function loadWorkspaces(): Promise<void> {
  try {
    list = { rows: await listWorkspaces(), refusal: null }
  } catch (e) {
    list = { rows: list.rows, refusal: asRefusal(e) }
  }
  store.notify('workspaces')
}

/** Answers come back in any order: an older revision never replaces a newer one. */
function took(id: WorkspaceId, m: Manifest, replayed: boolean) {
  const had = heldWorkspace(id).manifest
  keep(id, { manifest: had && had.revision > m.revision ? had : m, refusal: null, replayed })
}

export async function openWorkspace(id: WorkspaceId): Promise<void> {
  try {
    took(id, (await readWorkspace(id)).manifest, false)
  } catch (e) {
    keep(id, { manifest: null, refusal: asRefusal(e), replayed: false })
  }
}

/** One change, its answer taken in. A refusal is kept and thrown, for whoever
 *  asked: one saying the workspace is gone leaves nothing to show. */
async function change(id: WorkspaceId, act: () => Promise<WorkspaceAnswer>): Promise<WorkspaceAnswer> {
  try {
    const got = await act()
    took(id, got.manifest, !!got.replayed)
    void loadWorkspaces()
    return got
  } catch (e) {
    const refusal = asRefusal(e)
    const lost = refusal.refusal === 'missing' || refusal.refusal === 'gone' || refusal.refusal === 'unreadable'
    keep(id, { manifest: lost ? null : heldWorkspace(id).manifest, refusal, replayed: false })
    throw refusal
  }
}

export async function newWorkspace(o: { name?: string; from?: Seed } = {}): Promise<WorkspaceAnswer> {
  const got = await createWorkspace(o)
  took(got.id, got.manifest, !!got.replayed)
  void loadWorkspaces()
  return got
}
export const rename = (id: WorkspaceId, name: string) => change(id, () => renameWorkspace(id, name))
export const add = (id: WorkspaceId, object: NewObject) => change(id, () => addObject(id, object))
export const remove = (id: WorkspaceId, oid: ObjectId) => change(id, () => removeObject(id, oid))
export const reorder = (id: WorkspaceId, order: ObjectId[]) => change(id, () => reorderObjects(id, order))

/** The order with `oid` moved by `by` places: every id, each once, as the door
 *  asks. The same order back when it can't move. */
export function moved(order: readonly ObjectId[], oid: ObjectId, by: number): ObjectId[] {
  const from = order.indexOf(oid)
  const to = from + by
  if (from < 0 || to < 0 || to >= order.length) return [...order]
  const next = [...order]
  next.splice(to, 0, ...next.splice(from, 1))
  return next
}

export const useWorkspace = (id: WorkspaceId | null): HeldWorkspace => {
  const sub = useCallback((fn: () => void) => store.subscribe('workspace:' + id, fn), [id])
  return useSyncExternalStore(sub, () => (id ? heldWorkspace(id) : NONE))
}
const subList = (fn: () => void) => store.subscribe('workspaces', fn)
export const useWorkspaces = (): WorkspaceList => useSyncExternalStore(subList, () => list)
