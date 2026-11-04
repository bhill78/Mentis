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
import type { Availability, Level } from '../types'
import type { ActionId } from '../actions/types'

/** Every member of the union T, and nothing else, as a list. */
const all = <T,>() => <const A extends readonly T[]>(a: A & ([T] extends [A[number]] ? unknown : never)) => a

export type MagnetSource =
  | { kind: 'brain'; brain: string }
  | { kind: 'conversation'; conversation: string }
  | { kind: 'connector'; connector: string; location?: string }
  | { kind: 'web'; url?: string; domain?: string }
  | { kind: 'other'; type: string; ref: string }
  | { kind: 'agent-results'; conversation?: string; runtime?: string }
  | { kind: 'file'; collection: string; path?: string }
  | { kind: 'database'; collection: string; table?: string }
export const MAGNET_SOURCE_KINDS = all<MagnetSource['kind']>()(['brain', 'conversation', 'connector', 'web', 'other', 'agent-results', 'file', 'database'])
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
  presentation: { renderer: 'disc'|'ring'|'cards'|'list'|'gallery'; theme?: 'minimal'|'anchored'|'glass'|'floating' } // shared Look only; never placement/level/navigation
  /* M1: each kept, bounds-checked and said (notRunning); only a manual activation of a lone extract is executed. Absent reads as it always did. */
  activation?: { mode: 'manual'|'scheduled'|'event'|'source-change'|'condition'; schedule?: string; event?: string; condition?: string }
  processing?: { operations: Array<{ op: 'extract'|'compare'|'correlate'|'classify'|'transform'|'change-detect'|'other'; name?: string; options?: Record<string, string | number | boolean> }> }
  ai?: { mode: 'none'|'selective'|'local'|'runtime'|'agent'; runtime?: string; model?: string; agent?: string }
  outputs?: Array<'findings'|'structured'|'records'|'relationships'|'proposals'|'notifications'|'work'>
  destinations?: Array<{ kind: 'magnet-conversation'|'brain'|'workspace'|'workflow'; ref?: string }>
  /** Its own Conversation, distinct from any source. Asked for, never set by a reconfigure. */
  conversation?: string | null
}
export const COLLECTION_MODES = all<MagnetConfig['collection']['mode']>()(['one-time', 'scheduled', 'continuous', 'paused'])
export const SYNTHESIS_MODES = all<MagnetConfig['synthesis']['mode']>()(['manual', 'scheduled', 'on-new-information'])
export const RENDERERS = all<MagnetConfig['presentation']['renderer']>()(['disc', 'ring', 'cards', 'list', 'gallery'])
export type MagnetActivation = NonNullable<MagnetConfig['activation']>
export type MagnetOperation = NonNullable<MagnetConfig['processing']>['operations'][number]
export type MagnetAi = NonNullable<MagnetConfig['ai']>
export type MagnetOutput = NonNullable<MagnetConfig['outputs']>[number]
export type MagnetDestination = NonNullable<MagnetConfig['destinations']>[number]
export const ACTIVATION_MODES = all<MagnetActivation['mode']>()(['manual', 'scheduled', 'event', 'source-change', 'condition'])
export const OPERATIONS = all<MagnetOperation['op']>()(['extract', 'compare', 'correlate', 'classify', 'transform', 'change-detect', 'other'])
export const AI_MODES = all<MagnetAi['mode']>()(['none', 'selective', 'local', 'runtime', 'agent'])
export const OUTPUTS = all<MagnetOutput>()(['findings', 'structured', 'records', 'relationships', 'proposals', 'notifications', 'work'])
export const DESTINATIONS = all<MagnetDestination['kind']>()(['magnet-conversation', 'brain', 'workspace', 'workflow'])
/** The bounds §3.7 and §3.10 set on the shared schema (P2 enforces them on the server). */
export const MAGNET_BOUNDS = {
  configs: 50, sources: { min: 1, max: 20 }, phrases: 20, phraseChars: 500, topics: 50, filters: 20, operations: 20,
} as const
/** The named facets. M1's optional ones may be null, which takes one out so it reads absent again. */
export type MagnetConfigChange = Partial<Omit<MagnetConfig, 'id' | 'conversation' | 'activation' | 'processing' | 'ai' | 'outputs' | 'destinations'>>
  & { [K in 'activation' | 'processing' | 'ai' | 'outputs' | 'destinations']?: MagnetConfig[K] | null }
export type MagnetSeed = Omit<MagnetConfig, 'id'>
export type MagnetId = MagnetConfig['id']
/** The new zone's own entry in the current presentation class's record, and nothing
 * else: never the whole DevicePlacement (no order, no other zones' place or level,
 * no updatedAt), so a device cannot send stale placement for zones it is not adding.
 * (The plan writes `level?: SurfaceLevel`, a name it never defines; its level type is Level.) */
export type NewZonePlacement = { place: 'stack'|'sheet'|'launcher'|'dock'; level?: Level; index?: number }
export const NEW_ZONE_PLACEMENT_FIELDS = all<keyof NewZonePlacement>()(['place', 'level', 'index'])
export type MagnetAttach = { zone: MagnetZone; scope?: 'medium'|'compact'; presentation?: NewZonePlacement; base?: Arr }
/** createMagnet: generic magnet.create. Contractually ONE locked operation that writes
 * the config and adds the shared zone (config + shared-zone patch); neither is ever
 * written without the other.
 *
 * With `opts.id` it recreates that config under the fixed id instead of generating one.
 * Recovery of a missing config, Undo of a committed Remove and Redo of an undone create
 * all go through this, so the recovered config always has its stored zone and is never
 * collected as an orphan. */
export type CreateMagnetFn = (seed: MagnetSeed, attach: MagnetAttach, opts?: { id?: MagnetId }) => Promise<MagnetConfig>
/** reconfigure: applies a change to an EXISTING config only. On a missing id it is
 * refused (Availability disabled, code 'state') with a reason whose message points to
 * recovery, which is createMagnet(seed, attach, { id }); it never recreates a config. */
export type ReconfigureFn = (magnetId: MagnetId, change: MagnetConfigChange) => Promise<MagnetConfig>
export type MagnetEnv = { permissions: ReadonlySet<string>; connectors: ReadonlySet<string>; runtime: ReadonlySet<string> }
export type MagnetAvailabilityFn = (config: MagnetConfig, env: MagnetEnv) => ReadonlyMap<ActionId, Availability>  // magnetAvailability: P7

/* ---- §3.10.1 First source adapter: conversation-backed ---- */

export interface MagnetZone {           // saved zone references a config; fetched content is never saved here
  type: 'zone'
  id: `mag-${string}`                   // equals MagnetConfig.id; stable, generated once
  show: 'magnet'
  name?: string
  /* and, given one, its own look, flat as a thread window keeps it (focus/model.ts lookOf) */
  options: { magnet: `mag-${string}`; panel?: string; content?: string; opacity?: number }
  level?: Level                         // v3; a magnet's icon level is a disc at its rect, not the `min` window tab
}
export type MagnetCapability = 'fetch'|'search'|'post'|'file'|'image'|'attachment'|'link'|'form'|'other'
export const MAGNET_CAPABILITIES = all<MagnetCapability>()([
  'fetch', 'search', 'post', 'file', 'image', 'attachment', 'link', 'form', 'other',
])
export type MagnetResult = { source: MagnetSource; kind: string; id: string; value: unknown } // source is never discarded
/** How a source's read went: said per source, so one never fails another. */
export type MagnetSourceStatus = 'ok' | 'partial' | 'unavailable' | 'busy'
/** What a read was asked for and may be abandoned by. `magnet` is whose read it is.
 *  `glance`: a hover's, which never stands beside another read of this client's (route.ts). */
export type MagnetReadAt = { magnet?: MagnetId; signal?: AbortSignal; glance?: boolean }
/** A page of a source's results. `status` absent is ok; `routed`: the server's Magnet route answered it. */
export type MagnetPage = { results: MagnetResult[]; next?: string; status?: MagnetSourceStatus; reason?: string; routed?: boolean }
/** `about` is what the source says of itself and `posts` how many it holds in
 *  all (read from the source, never counted from a copy). `participants`,
 *  `participants_more` and `latest` are a server's when it says them, and read
 *  tolerantly (presentation.ts): absent or malformed draws nothing. */
export type MagnetSummary = { title: string; initial?: string; activity?: number; unread?: number; about?: string; posts?: number; status?: MagnetSourceStatus; reason?: string; routed?: boolean; participants?: unknown; participants_more?: unknown; latest?: unknown }
export interface MagnetSourceAdapter<S extends MagnetSource = MagnetSource> {
  kind: S['kind']
  capabilities(src: S, env: MagnetEnv): ReadonlySet<MagnetCapability>
  fetch(src: S, selection: MagnetSelection, page?: string, at?: MagnetReadAt): Promise<MagnetPage>
  search(src: S, q: string, page?: string, at?: MagnetReadAt): Promise<{ results: MagnetResult[]; next?: string }>
  summary(src: S, at?: MagnetReadAt): Promise<MagnetSummary>
}
export interface MagnetLive { config: MagnetConfig; summaries: Array<{source: MagnetSource; summary: MagnetSummary}>; results: MagnetResult[]; tabs: string[]; statuses?: Array<{ source: MagnetSource; status: MagnetSourceStatus; reason?: string }>; routed?: boolean; more?: boolean }
/** `summaryOnly`: what a disc asks: a title, activity and a count, and no walk of anything.
 *  `glance`: what a hover asks: its page, as a Magnet opened would read it and kept for it. */
export type MagnetLoadOpts = { summaryOnly?: boolean; glance?: boolean; signal?: AbortSignal }
export type UseMagnetFn = (configOrId: MagnetConfig | MagnetConfig['id'], opts?: { summaryOnly?: boolean; glance?: number }) => MagnetLive & { loading: boolean; error?: string; readOn(kind: string, signal?: AbortSignal): Promise<void> } // useMagnet: P7; keyed by config id + revision
// searchConversation(conversation: string, q: string, opts?: { limit?: number; before?: string }): Promise<Hit[]>
//   is P8's, in the client store with its Hit; the conversation adapter wraps it unchanged.
