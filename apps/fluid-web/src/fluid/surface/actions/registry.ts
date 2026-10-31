/* SURFACE TENSION: THE ONE ACTION REGISTRY (plan adm-b848fa881c8d §3.5, rev 3
 * §2–§5; part P3).
 *
 * Every action, shared and resource-specific, is defined once here and run
 * through `registry.run`: buttons, keys, menus (T2) and the find-an-action
 * palette (T3) all draw `list()` and call the same `run`. It grows from
 * objects/actions.ts, which stays the object row's implementation and is the
 * registry's first client (providers/object.ts).
 *
 *   register(def)        a shared verb, offered to every target its
 *                        `available` does not call absent
 *   provide(kind, defs)  a resource or surface kind's own actions; a provider
 *                        may also give a shared verb's id, which then replaces
 *                        the registered one for that target (one id per list)
 *   list(t, ctx)         T2 = palette: everything not absent, in the fixed
 *                        group order, lead first in its group, disabled
 *                        entries with their reason, "Find an action…" last
 *   primary(t, ctx, n)   T1 by the I-3 rule: the lead action, then shared
 *                        verbs in the host's fixed order, cut at n
 *
 * Browser-free: nothing here touches the DOM, the store or the workspace. */

import type { Availability, CapabilityUnavailable, PlacementKind } from '../types'
import {
  ACTION_GROUPS, RESERVED_VERBS, SHARED_VERBS,
  type ActionCtx, type ActionDef, type ActionId, type ActionRegistry, type ActionTarget, type SharedVerb,
} from './types'

export const AVAILABLE: Availability = { state: 'available' }
export const ABSENT: Availability = { state: 'absent' }
/** Disabled, always with a reason a person can read (§3.4). */
export const disabled = (message: string, code: CapabilityUnavailable['code'] = 'state', retryable = true): Availability =>
  ({ state: 'disabled', reason: { code, message, retryable } })

/** The host a target is drawn in, which decides T1's order (r3 §5.2). */
export type ActionHost = PlacementKind | 'icon' | 'page-bar' | 'post' | 'object'

/** Each host's fixed order of shared verbs for T1, after the lead action.
 *  Close is never here: the chrome draws × itself when Close is available. */
export const HOST_ORDER: Record<ActionHost, readonly SharedVerb[]> = {
  icon: [],
  launcher: ['bringBack', 'open'],
  nested: ['open', 'expand', 'collapse'],
  dock: ['makePrimary', 'focus', 'search', 'fit', 'float', 'keepAsWindow', 'collapse', 'expand'],
  float: ['makePrimary', 'collapse', 'expand', 'keepAsWindow', 'focus', 'dock'],
  'page-root': ['saveLayout', 'restoreLayout', 'undo', 'layouts', 'tidy', 'search'],
  'page-bar': ['saveLayout', 'restoreLayout', 'undo', 'layouts', 'tidy', 'search', 'export'],
  stack: ['expand', 'collapse', 'moveUp', 'moveDown'],
  sheet: ['expand', 'collapse'],
  post: ['open', 'peek', 'focus', 'expand', 'keep'],
  object: ['open', 'peek', 'float', 'keep', 'makePrimary', 'focus'],
}

/** Which host a target is drawn in: its surface's placement, else its
 *  resource (a workspace's bar, a post, an object). */
export function hostOf(t: ActionTarget): ActionHost {
  const s = t.surface?.state
  if (s) return (s.level.override ?? s.level.auto) === 'icon' ? 'icon' : s.placement.kind
  const k = t.resource?.kind
  if (k === 'workspace') return 'page-bar'
  if (k === 'post') return 'post'
  return 'object'
}

const isShared = (id: ActionId): id is SharedVerb => (SHARED_VERBS as readonly string[]).includes(id)
const groupRank = (d: ActionDef) => ACTION_GROUPS.indexOf(d.group)

export interface Listed { def: ActionDef; availability: Availability }

/** The palette's own row: last in every T2, in Details. */
export const FIND_ACTION: ActionId = 'findAction'

export function createRegistry(): ActionRegistry & {
  /** every definition the registry can offer to `t`, before availability */
  defsFor(t: ActionTarget): ActionDef[]
  /** every definition registered or provided for `targets` (the glyph rule's test) */
  everyDef(targets: readonly ActionTarget[]): ActionDef[]
  /** forget everything (tests) */
  reset(): void
} {
  let shared: ActionDef[] = []
  let providers = new Map<string, Array<(t: ActionTarget) => ActionDef[]>>()

  const keysOf = (t: ActionTarget) => {
    const ks: string[] = []
    if (t.resource?.kind) ks.push(t.resource.kind)
    if (t.surface) ks.push('surface:' + t.surface.state.kind)
    if (t.selection?.length) ks.push('selection')
    return ks
  }

  function defsFor(t: ActionTarget): ActionDef[] {
    const byId = new Map<ActionId, ActionDef>()
    for (const d of shared) byId.set(d.id, d)
    const seen = new Set<(t: ActionTarget) => ActionDef[]>()
    for (const k of keysOf(t)) for (const p of providers.get(k) ?? []) {
      if (seen.has(p)) continue
      seen.add(p)
      for (const d of p(t)) byId.set(d.id, d)
    }
    return [...byId.values()]
  }

  function list(t: ActionTarget, ctx: ActionCtx): Listed[] {
    const out: Listed[] = []
    const order = new Map<ActionId, number>()
    defsFor(t).forEach((d, i) => order.set(d.id, i))
    for (const def of defsFor(t)) {
      const availability = def.available(t, ctx)
      if (availability.state === 'absent') continue
      if (availability.state === 'disabled' && !availability.reason?.message) throw new Error(`${def.id}: disabled without a reason`)
      out.push({ def, availability })
    }
    const rank = (x: Listed) => (x.def.id === FIND_ACTION ? ACTION_GROUPS.length : groupRank(x.def))
    return out.sort((a, b) => rank(a) - rank(b)
      || Number(!!b.def.lead) - Number(!!a.def.lead)
      || order.get(a.def.id)! - order.get(b.def.id)!)
  }

  function primary(t: ActionTarget, ctx: ActionCtx, budget: number): ActionDef[] {
    if (budget <= 0) return []
    const avail = list(t, ctx).filter((x) => x.availability.state === 'available').map((x) => x.def)
    const out: ActionDef[] = []
    const lead = avail.find((d) => d.lead)
    if (lead) out.push(lead)
    for (const id of HOST_ORDER[hostOf(t)]) {
      if (out.length >= budget) break
      const d = avail.find((x) => x.id === id)
      if (d && !out.includes(d)) out.push(d)
    }
    return out.slice(0, budget)
  }

  async function run(id: ActionId, t: ActionTarget, ctx: ActionCtx): Promise<void> {
    const def = defsFor(t).find((d) => d.id === id)
    if (!def) throw new Error(`No action ${id} here`)
    const a = def.available(t, ctx)
    if (a.state === 'absent') throw new Error(`${def.label} does not apply here`)
    if (a.state === 'disabled') throw new Error(a.reason.message)
    await def.run(t, ctx)
  }

  return {
    register(def) {
      if (!isShared(def.id)) throw new Error(`${def.id} is not a shared verb: provide it for its kind`)
      if ((RESERVED_VERBS as readonly string[]).includes(def.id)) throw new Error(`${def.id} is reserved`)
      shared = [...shared.filter((d) => d.id !== def.id), def]
    },
    provide(kind, defs) {
      providers.set(kind, [...(providers.get(kind) ?? []), defs])
    },
    list, primary, run, defsFor,
    everyDef(targets) {
      const all = new Map<string, ActionDef>()
      for (const t of targets) for (const d of defsFor(t)) all.set(d.id + '\u0000' + (d.glyph ?? ''), d)
      return [...all.values()]
    },
    reset() { shared = []; providers = new Map() },
  }
}

/** The one instance (§3.5). Providers register into it from providers/index.ts. */
export const registry = createRegistry()

/* -- the palette's matching (T3, r3 §5.3) ----------------------------------- */

const fold = (s: string) => s.toLowerCase().replace(/[…_.\-]+/g, ' ').replace(/\s+/g, ' ').trim()

/** Whether `def` answers `query`: every word of the query in its label or one
 *  synonym (so "minimise" finds Collapse and Put away). */
export function matches(def: ActionDef, query: string): boolean {
  const q = fold(query)
  if (!q) return true
  const words = q.split(' ')
  return [def.label, ...def.synonyms].some((s) => { const f = fold(s); return words.every((w) => f.includes(w)) })
}

/** The palette's rows for `query`: the T2 list, narrowed by label and
 *  synonyms. With no query it is exactly the T2 list. */
export function paletteList(rows: readonly Listed[], query: string): Listed[] {
  return rows.filter((x) => matches(x.def, query))
}

/** Ctrl/⌘+K opens the palette. Plain "/" stays the global resource search;
 *  Ctrl/⌘+Shift+K is the composer's Link (composer/marks.ts). */
export function isFindActionKey(e: { key: string; ctrlKey?: boolean; metaKey?: boolean; altKey?: boolean; shiftKey?: boolean }): boolean {
  return (e.key === 'k' || e.key === 'K') && !!(e.ctrlKey || e.metaKey) && !e.altKey && !e.shiftKey
}

/** Ctrl/⌘+K wherever Mentis has focus, a text field included: the palette
 *  opens (or closes), and the browser's own use of the key -- the address
 *  bar's search in Chrome, Edge and Firefox -- is refused. Run in the capture
 *  phase (ActionMenu.tsx), so no handler under it that stops a key's
 *  propagation can hand the key back to the browser (owner, Turn #1458). */
export function findActionKey(e: { key: string; ctrlKey?: boolean; metaKey?: boolean; altKey?: boolean; shiftKey?: boolean; preventDefault(): void },
  toggle: () => void): boolean {
  if (!isFindActionKey(e)) return false
  e.preventDefault()
  toggle()
  return true
}
