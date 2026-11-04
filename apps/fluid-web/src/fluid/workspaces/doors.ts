/* GOING TO A WORKSPACE, AND PUTTING A THING IN ONE. The frame lends its navigation
 * (Shell.tsx); making one from a Magnet or a Conversation curates it and, for a
 * Magnet, draws it, through the same create a Magnet's Undo goes through: a
 * definition already kept is placed as it stands, so the workspace's layout names
 * the Magnet and copies none of it. */

import { CLIENT_HEADERS } from '../../api'
import { classNow } from '../frame/narrow'
import { fluidFetch } from '../http'
import * as nav from '../nav'
import { newOp, store, type Id } from '../store'
import { MAGNET_CHOICES } from '../surface/magnet/choices'
import { newMagnetZone } from '../surface/magnet/model'
import type { MagnetId } from '../surface/magnet/types'
import { toLayout, workspace, workspaceStart } from '../workspace/place'
import { WorkspaceRefusal, type NewObject, type Seed, type WorkspaceId } from './client'
import { add, newWorkspace } from './state'

export interface WorkspaceDoors {
  openWorkspace(id: WorkspaceId): void
  openConversation(id: Id): void
  openPost(conversation: Id, post: Id): void
}
let doors: WorkspaceDoors | null = null
export const bindWorkspaceDoors = (d: WorkspaceDoors | null) => { doors = d }
export const workspaceDoors = (): WorkspaceDoors => {
  if (!doors) throw new Error('the workspace doors are not bound')
  return doors
}

/** What a Magnet or a Conversation is when somebody puts it in a workspace. */
export type Curating = { kind: 'magnet' | 'conversation'; ref: string; name: string }

/** Chosen directly by the owner: the source is who chose it (workspace_manifest.py). */
export const chosenBy = (me: Id, kind: NewObject['kind'], ref: string): NewObject =>
  ({ kind, ref, provenance: { source: { kind: 'participant', ref: me }, by: me } })

/** Draw a Magnet in a workspace's layout: under its `wsp-` key, by its id. Through
 *  the holder where the workspace is shown; otherwise written there and this tab's
 *  untouched copy of that place let go, so arriving reads what is kept. */
export async function placeMagnet(id: WorkspaceId, magnet: MagnetId, name: string): Promise<void> {
  const cls = classNow()
  const scoped = cls !== 'wide' ? { scope: cls, presentation: { place: 'stack' as const, level: MAGNET_CHOICES.newLevel } } : {}
  if (workspace.key === id) {
    await workspace.createMagnet(null, newMagnetZone(name), { id: magnet, wideFallback: MAGNET_CHOICES.wideFallback, ...scoped })
    return
  }
  const res = await fluidFetch(`/fluid/api/arrangements/${encodeURIComponent(id)}/magnets`, {
    method: 'POST', headers: { ...CLIENT_HEADERS, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      id: magnet, wideFallback: MAGNET_CHOICES.wideFallback, op: newOp(),
      attach: { zone: newMagnetZone(name), ...scoped, base: toLayout(workspaceStart()) },
    }),
  })
  const got = await res.json().catch(() => null)
  if (!res.ok || !got || got.error) throw new Error(got?.reason?.message ?? got?.error ?? res.statusText)
  workspace.letGo(id)
}

/** The workspace now holds it; drawing it is a second write, and failing that
 *  takes nothing back: its row still offers Show. */
async function drawIt(id: WorkspaceId, what: Curating) {
  if (what.kind !== 'magnet') return
  try {
    await placeMagnet(id, what.ref as MagnetId, what.name)
  } catch (e) {
    nav.toast({ text: `Added, but ${what.name} isn’t drawn yet: ${(e as Error).message}` })
  }
}

const seedOf = (what: Curating): Seed => (what.kind === 'magnet' ? { magnet: what.ref } : { conversation: what.ref })

/** A new workspace starting from one Magnet or Conversation, and go there. */
export async function newWorkspaceFrom(what: Curating): Promise<void> {
  const got = await newWorkspace({ name: what.name, from: seedOf(what) })
  await drawIt(got.id, what)
  workspaceDoors().openWorkspace(got.id)
}

/** A Magnet or Conversation added to a workspace there is, and go there. */
export async function addToWorkspace(id: WorkspaceId, what: Curating): Promise<void> {
  const me = await store.loadMe()
  const got = await add(id, chosenBy(me, what.kind, what.ref))
  /* Already curated there, the first provenance stands and it is drawn already,
     unless somebody took its disc away: then its row's Show is the way back. */
  if (got.changed !== false) await drawIt(id, what)
  workspaceDoors().openWorkspace(id)
}

/** A Magnet just made in the workspace shown: curated there too, as one put in is, so
 *  its row lists it and a request made here reads it. Drawn already: this draws nothing. */
export async function curateMade(id: WorkspaceId, magnet: MagnetId): Promise<void> {
  await add(id, chosenBy(await store.loadMe(), 'magnet', magnet))
}

/** How a refusal from these reads in a toast. */
export const refusalWords = (e: unknown): string =>
  e instanceof WorkspaceRefusal || e instanceof Error ? e.message : 'It could not be done.'
