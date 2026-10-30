/* SURFACE TENSION: ACTIONS (plan adm-15951b3daacc §3.5, rev 3 §2–§5; part P0).
 *
 * One registry for every action, shared and resource-specific; buttons,
 * keys, menus and the palette all run through it. Types word for word from
 * the plan, with each verb list as its runtime companion. The registry
 * itself is P3's (F/surface/actions/registry.ts). */

import type {
  Availability, Change, InputMode, Outcome, PresentationClass, ResourceCapabilities, ResourceRef,
  SurfaceCapabilities, SurfaceState, ZoneId,
} from '../types'

/** Every member of the union T, and nothing else, as a list. */
const all = <T,>() => <const A extends readonly T[]>(a: A & ([T] extends [A[number]] ? unknown : never)) => a

export type SharedVerb =
  | 'open' | 'peek' | 'openAsWorkspace' | 'expand' | 'collapse' | 'resetSize' | 'dock' | 'float'
  | 'makePrimary' | 'back' | 'focus' | 'exitFocus' | 'fullscreen' | 'exitFullscreen'
  | 'putAway' | 'bringBack' | 'close' | 'reopen' | 'removeFromWorkspace' | 'search'
  | 'filter' | 'present' | 'keep' | 'keepAsWindow' | 'follow' | 'hold' | 'newFollower' | 'export'
  | 'details' | 'settings' | 'copyLink' | 'bringToFront' | 'tidy' | 'tidyAround' | 'fit' | 'split' | 'merge'
  | 'saveLayout' | 'restoreLayout' | 'undo' | 'resetPlace' | 'putAllAway' | 'layouts' | 'sketch'
  | 'makeRoom' | 'keepArrangement' | 'moveUp' | 'moveDown' | 'showAsSheet' | 'findAction'
export const SHARED_VERBS = all<SharedVerb>()([
  'open', 'peek', 'openAsWorkspace', 'expand', 'collapse', 'resetSize', 'dock', 'float',
  'makePrimary', 'back', 'focus', 'exitFocus', 'fullscreen', 'exitFullscreen',
  'putAway', 'bringBack', 'close', 'reopen', 'removeFromWorkspace', 'search',
  'filter', 'present', 'keep', 'keepAsWindow', 'follow', 'hold', 'newFollower', 'export',
  'details', 'settings', 'copyLink', 'bringToFront', 'tidy', 'tidyAround', 'fit', 'split', 'merge',
  'saveLayout', 'restoreLayout', 'undo', 'resetPlace', 'putAllAway', 'layouts', 'sketch',
  'makeRoom', 'keepArrangement', 'moveUp', 'moveDown', 'showAsSheet', 'findAction',
])
// Reserved and NOT registered in this build: 'push' | 'pull' | 'compare' | 'group' | 'ungroup'
export const RESERVED_VERBS = ['push', 'pull', 'compare', 'group', 'ungroup'] as const
export type SpecificId =
  | 'post.reply' | 'post.address' | 'post.annotate' | 'post.select' | 'post.include' | 'post.removeInclusion'
  | 'post.carries' | 'thread.replies'
  | 'conversation.views' | 'conversation.own' | 'conversation.newHere' | 'conversation.topics'
  | 'conversation.makeMagnet'
  | 'form.edit' | 'form.validate' | 'form.markReady' | 'form.history'
  | 'file.download' | 'link.openExternal' | 'run.stop' | 'run.consent'
  | 'magnet.create' | 'magnet.tab' | 'magnet.configure' | 'magnet.reconfigure'    // same registry, never a separate Magnet toolbar
export const SPECIFIC_IDS = all<SpecificId>()([
  'post.reply', 'post.address', 'post.annotate', 'post.select', 'post.include', 'post.removeInclusion',
  'post.carries', 'thread.replies',
  'conversation.views', 'conversation.own', 'conversation.newHere', 'conversation.topics',
  'conversation.makeMagnet',
  'form.edit', 'form.validate', 'form.markReady', 'form.history',
  'file.download', 'link.openExternal', 'run.stop', 'run.consent',
  'magnet.create', 'magnet.tab', 'magnet.configure', 'magnet.reconfigure',
])
export type ActionId = SharedVerb | SpecificId

export type ActionGroup = 'resource' | 'view' | 'arrange' | 'look' | 'share' | 'details'
/** The fixed group order of T2 and the palette. */
export const ACTION_GROUPS = all<ActionGroup>()(['resource', 'view', 'arrange', 'look', 'share', 'details'])
export interface SurfaceRef { id: ZoneId; state: SurfaceState; caps: SurfaceCapabilities }
export interface ActionTarget { resource?: ResourceRef & { caps?: ResourceCapabilities }; surface?: SurfaceRef; selection?: ResourceRef[] }
export interface ActionCtx {
  cls: PresentationClass
  input: InputMode
  apply: (id: ZoneId, c: Change) => Outcome      // = workspace.apply; the only way a surface verb moves anything
  nav: { open(a: string): void; openPlace(key: string): void; back(): void }
}
export interface ActionDef {
  id: ActionId
  plane: 'resource' | 'surface'
  writes: 'none' | 'placement' | 'record'        // 'record' goes through Governance exactly as today
  label: string
  glyph?: string                                 // one glyph per verb, never reused (r3 §2.3)
  shortcut?: string
  synonyms: readonly string[]                    // old words: 'minimise', 'restore', 'pin as tab', 'open another', …
  group: ActionGroup
  lead?: boolean                                 // at most one per resource kind (r3 §4)
  multi?: 'each' | 'together' | 'no'
  available(t: ActionTarget, ctx: ActionCtx): Availability
  run(t: ActionTarget, ctx: ActionCtx): void | Promise<void>
}
export interface ActionRegistry {
  register(def: ActionDef): void                                       // shared verbs
  provide(kind: string, defs: (t: ActionTarget) => ActionDef[]): void  // resource-specific providers
  list(t: ActionTarget, ctx: ActionCtx): Array<{ def: ActionDef; availability: Availability }>
      // = T2 = palette source. Excludes 'absent'. Fixed group order resource·view·arrange·look·share·details
  primary(t: ActionTarget, ctx: ActionCtx, budget: number): ActionDef[]
      // I-3 rule: lead action, then shared verbs in the host's fixed order, cut at budget; never includes ⋯
  run(id: ActionId, t: ActionTarget, ctx: ActionCtx): Promise<void>  // the only entry point; buttons, keys, menus, palette
}
// export const registry: ActionRegistry   // F/surface/actions/registry.ts, one instance (P3)
