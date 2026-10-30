/* SURFACE TENSION: THE UNIVERSAL MAGNET (plan adm-15951b3daacc §3.10, §3.10.1;
 * part P0).
 *
 * One Magnet capability; "Conversation", "Search", "Gallery" and the rest
 * are configurations, never types. A magnet is a SURFACE and configured
 * view, not a copy of source records. Types word for word from the plan,
 * with each value list as its runtime companion; the functions are the
 * signature types their owners implement (P7; searchConversation is P8's,
 * in store.ts). */

import type { Arr } from '../../workspace/place'
import type { Availability, DevicePlacement, Level } from '../types'
import type { ActionId } from '../actions/types'

/** Every member of the union T, and nothing else, as a list. */
const all = <T,>() => <const A extends readonly T[]>(a: A & ([T] extends [A[number]] ? unknown : never)) => a

export type MagnetSource =
  | { kind: 'brain'; brain: string }
  | { kind: 'conversation'; conversation: string }
  | { kind: 'connector'; connector: string; location?: string }
  | { kind: 'web'; url?: string; domain?: string }
  | { kind: 'other'; type: string; ref: string }
export const MAGNET_SOURCE_KINDS = all<MagnetSource['kind']>()(['brain', 'conversation', 'connector', 'web', 'other'])
export interface MagnetSelection {
  criteria?: string
  phrases?: string[]                 // ≤ 20, each ≤ 500 chars
  topics?: string[]                  // ≤ 50 ids
  informationTypes?: Array<'post'|'file'|'image'|'attachment'|'link'|'form'|'other'>
  dates?: { after?: string; before?: string }
  filters?: Record<string, string | number | boolean>  // ≤ 20 scalar entries
}
export const INFORMATION_TYPES = all<NonNullable<MagnetSelection['informationTypes']>[number]>()([
  'post', 'file', 'image', 'attachment', 'link', 'form', 'other',
])
export interface MagnetConfig {
  id: `mag-${string}`                // stable identity; never a conversation id
  sources: MagnetSource[]            // 1..20; a conversation is one possible source value
  selection: MagnetSelection
  collection: { mode: 'one-time'|'scheduled'|'continuous'|'paused'; schedule?: string }
  synthesis: { mode: 'manual'|'scheduled'|'on-new-information'; schedule?: string }
  notifications: { newItems: boolean; changes: boolean; failures: boolean }
  presentation: { renderer: 'disc'|'ring'|'cards'|'list'|'gallery' } // shared Look only; never placement/level/navigation
}
export const COLLECTION_MODES = all<MagnetConfig['collection']['mode']>()(['one-time', 'scheduled', 'continuous', 'paused'])
export const SYNTHESIS_MODES = all<MagnetConfig['synthesis']['mode']>()(['manual', 'scheduled', 'on-new-information'])
export const RENDERERS = all<MagnetConfig['presentation']['renderer']>()(['disc', 'ring', 'cards', 'list', 'gallery'])
/** The bounds §3.7 and §3.10 set on the shared schema (P2 enforces them on the server). */
export const MAGNET_BOUNDS = {
  configs: 50, sources: { min: 1, max: 20 }, phrases: 20, phraseChars: 500, topics: 50, filters: 20,
} as const
export type MagnetConfigChange = Partial<Omit<MagnetConfig, 'id'>>
export type MagnetSeed = Omit<MagnetConfig, 'id'>
export type CreateMagnetFn = (seed: MagnetSeed, attach: { zone: MagnetZone; scope?: 'medium'|'compact'; presentation?: DevicePlacement; base?: Arr }) => Promise<MagnetConfig> // createMagnet: generic magnet.create; config + shared-zone patch are one locked op
export type ReconfigureFn = (magnetId: MagnetConfig['id'], change: MagnetConfigChange | MagnetSeed) => Promise<MagnetConfig> // reconfigure: missing id requires a complete MagnetSeed and recreates the same id
export type MagnetEnv = { permissions: ReadonlySet<string>; connectors: ReadonlySet<string>; runtime: ReadonlySet<string> }
export type MagnetAvailabilityFn = (config: MagnetConfig, env: MagnetEnv) => ReadonlyMap<ActionId, Availability>  // magnetAvailability: P7

/* ---- §3.10.1 First source adapter: conversation-backed ---- */

export interface MagnetZone {           // saved zone references a config; fetched content is never saved here
  type: 'zone'
  id: `mag-${string}`                   // equals MagnetConfig.id; stable, generated once
  show: 'magnet'
  name?: string
  options: { magnet: `mag-${string}` }
  level?: Level                         // v3; a magnet's icon level is a disc at its rect, not the `min` window tab
}
export type MagnetCapability = 'fetch'|'search'|'post'|'file'|'image'|'attachment'|'link'|'form'|'other'
export const MAGNET_CAPABILITIES = all<MagnetCapability>()([
  'fetch', 'search', 'post', 'file', 'image', 'attachment', 'link', 'form', 'other',
])
export type MagnetResult = { source: MagnetSource; kind: string; id: string; value: unknown } // source is never discarded
export type MagnetSummary = { title: string; initial?: string; activity?: number; unread?: number }
export interface MagnetSourceAdapter<S extends MagnetSource = MagnetSource> {
  kind: S['kind']
  capabilities(src: S, env: MagnetEnv): ReadonlySet<MagnetCapability>
  fetch(src: S, selection: MagnetSelection, page?: string): Promise<{ results: MagnetResult[]; next?: string }>
  search(src: S, q: string, page?: string): Promise<{ results: MagnetResult[]; next?: string }>
  summary(src: S): Promise<MagnetSummary>
}
export interface MagnetLive { config: MagnetConfig; summaries: Array<{source: MagnetSource; summary: MagnetSummary}>; results: MagnetResult[]; tabs: string[] }
export type UseMagnetFn = (configOrId: MagnetConfig | MagnetConfig['id']) => MagnetLive & { loading: boolean; error?: string } // useMagnet: P7; keyed by config id + revision
// searchConversation(conversation: string, q: string, opts?: { limit?: number; before?: string }): Promise<Hit[]>
//   is P8's, in the client store with its Hit; the conversation adapter wraps it unchanged.
