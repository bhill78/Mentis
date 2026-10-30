/* SURFACE TENSION: FLUID'S BRAIN-WIDE SETTINGS (plan §3.8; part P2).
 *
 * The global default for Make room, kept by the server beside the record
 * (`mentis/fluid/settings.py`, `<brain>/presentation/fluid-settings.json`):
 *
 *   GET  /fluid/api/settings            -> {makeRoom}
 *   POST /fluid/api/settings {makeRoom, op?} -> {makeRoom}
 *
 * A workspace may override it in its arrangement (v3 `spatial.makeRoom`,
 * every Page of the place sharing it). Which wins: the workspace override,
 * then the global default, then Off. P2 stores both; P6 reads them. */

import { useSyncExternalStore } from 'react'
import { CLIENT_HEADERS } from '../../api'
import { fluidFetch } from '../http'
import { newOp } from '../store'
import type { Arr } from '../workspace/place'
import { MAKE_ROOM, type MakeRoom } from './types'

export interface FluidSettings { makeRoom: MakeRoom }
/** The built-in default: what an absent (or unreadable) file means. */
export const DEFAULT_SETTINGS: FluidSettings = { makeRoom: 'off' }

const isMakeRoom = (v: unknown): v is MakeRoom => (MAKE_ROOM as readonly unknown[]).includes(v)

/** The effective Make room for a workspace: its own override, then the
 *  global default, then Off. */
export function effectiveMakeRoom(arr: Arr, global: MakeRoom | undefined): MakeRoom {
  return arr.spatial?.makeRoom ?? global ?? 'off'
}

/** The arrangement with this workspace's override set, or cleared (undefined:
 *  use the global default). Pure; the caller makes it an edit. */
export function withMakeRoom(arr: Arr, makeRoom: MakeRoom | undefined): Arr {
  const { spatial: _was, ...rest } = arr
  return makeRoom ? { ...rest, spatial: { makeRoom } } : rest
}

let settings: FluidSettings | null = null
let loading: Promise<FluidSettings> | null = null
const fns = new Set<() => void>()
const set = (s: FluidSettings) => { settings = s; fns.forEach((fn) => fn()) }

/** The settings as the server keeps them, read once; the built-in default
 *  while unread or when the server cannot be reached. */
export function loadSettings(force = false): Promise<FluidSettings> {
  if (!force && settings) return Promise.resolve(settings)
  if (!force && loading) return loading
  loading = fluidFetch('/fluid/api/settings', { headers: { ...CLIENT_HEADERS } })
    .then((r) => r.json().catch(() => null))
    .then((b) => { const got = { makeRoom: isMakeRoom(b?.makeRoom) ? b.makeRoom : DEFAULT_SETTINGS.makeRoom }; set(got); return got },
      () => DEFAULT_SETTINGS)
  return loading
}

/** Change the default for all workspaces. Refused (an unknown value, or a
 *  settings file the server cannot read and will not overwrite) throws. */
export async function setDefaultMakeRoom(makeRoom: MakeRoom): Promise<MakeRoom> {
  const res = await fluidFetch('/fluid/api/settings', {
    method: 'POST', headers: { ...CLIENT_HEADERS, 'Content-Type': 'application/json' },
    body: JSON.stringify({ makeRoom, op: newOp() }),
  })
  const got = await res.json().catch(() => null)
  if (!res.ok || !got || got.error || !isMakeRoom(got.makeRoom)) throw Object.assign(new Error(got?.error ?? res.statusText), { status: res.status })
  set({ makeRoom: got.makeRoom })
  return got.makeRoom
}

/** The global settings as React reads them (null until first read). */
export const useSettings = () => useSyncExternalStore((fn) => { fns.add(fn); return () => { fns.delete(fn) } }, () => settings)
