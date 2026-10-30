/* WHAT THE PROVIDERS CALL (part P3).
 *
 * The providers are browser-free definitions; what an action finally does is
 * one of today's functions, reached through `ops`. appOps.ts binds each one
 * to the function the existing control calls (the same nav, store, api,
 * workspace and lens calls), once, when the shell starts; a unit test binds
 * spies instead. Nothing here reimplements an action.
 *
 * HOSTS. A control drawn today by its own component (a section's ⋯, a
 * window's ⚙) knows how to do what it offers: its ZoneCtl and WindowActs.
 * `hosted(target, host)` lends those to the registry for that target, so its
 * menu is the registry's list and each item runs the host's own function.
 * Once P1's workspace.apply lands and P4's chrome draws targets from
 * SurfaceState, a target without a host runs its surface verbs through
 * ctx.apply alone. */

import type { ActionId, ActionTarget } from '../types'

/** One thing a host offers: what runs, whether it is on, and why not now. */
export interface HostOp {
  run(): void
  /** pressed / current */
  on?: boolean
  /** not now, with why (shown beside the item) */
  off?: string | null
  /** the host's own sentence for it here (a tooltip) */
  says?: string
  /** the same action in two ways, drawn as two items (Split side / below) */
  variants?: readonly { key: string; label: string; says: string; icon?: unknown; run(): void; off?: string | null }[]
}
export type SurfaceHost = Partial<Record<ActionId, HostOp>>

const hosts = new WeakMap<ActionTarget, SurfaceHost>()
/** Lend `host`'s own functions to the registry for `target`. */
export function hosted<T extends ActionTarget>(target: T, host: SurfaceHost): T { hosts.set(target, host); return target }
export const hostOf = (t: ActionTarget): SurfaceHost | undefined => hosts.get(t)

/** A post as the providers need it. */
export interface PostFacts {
  id: string
  home: string | null
  number: number | null
  deleted: boolean
  /** the conversation shown, or null in the Stream */
  here: string | null
  /** shown here by inclusion (it lives elsewhere) */
  included: boolean
}

/** Shell's post actions (render/post.tsx PostActions), as the toolbar uses them. */
export interface PostActs {
  reply?: (id: string) => void
  startSelect: (id: string) => void
  goHome: (conversation: string, post: string) => void
  include?: (id: string) => void
  remove?: (id: string) => void
  busy: boolean
}

/** The workspace Holder (workspace/place.ts), as Arrange uses it. */
export interface HolderOps {
  kind: string
  savedAt: number | null
  save(): Promise<void>
  restoreSaved(): Promise<void>
  undo(): void
  canUndo(): boolean
  reset(): void
}

export interface ObjectOps {
  open(address: string, anchor?: Element | null): void
  peek(address: string, anchor?: Element | null): void
  float(address: string, anchor?: Element | null): void
  keep(address: string, anchor?: Element | null): void
  primary(address: string, anchor?: Element | null): void
  focus(address: string, anchor?: Element | null): void
}

export interface Ops {
  object: ObjectOps
  /** go to a place (a conversation's own, or Home) */
  openPlace(key: string): void
  back(): void
  openAsPage(address: string): void
  /** the element an address is drawn in, for a sheet to grow out of */
  anchorOf(address: string): Element | null
  confirm(question: string): boolean
  toast(text: string): void
  copy(text: string, said: string): Promise<void>
  /* posts */
  post(id: string): PostFacts | null
  postActs(): PostActs | null
  postLink(p: PostFacts): string
  openPostDetails(id: string): void
  openPostFull(id: string): void
  openReplies(id: string): void
  openAddress(id: string, anchor: Element | null): void
  openAnnotate(id: string, anchor: Element | null): void
  exportTurn(id: string): Promise<void>
  /* conversations */
  conversationViews(id: string): void
  following(): boolean
  setFollow(on: boolean): void
  conversationFocused(): boolean
  setConversationFocused(on: boolean): void
  putConversationAway(): void
  bringConversationBack(): void
  conversationPutAway(): boolean
  exportConversation(id: string): Promise<void>
  /* the workspace */
  holder(): HolderOps
  floatsHere(): { count: number; unfolded: number }
  putAllAway(): void
  tidyFloats(): void
  /** a section that follows what is read, added beside the others */
  newFollower(): void
  /* the lens */
  lensOn(): boolean
  exitFocus(): void
  keepLensLayout(): void
  tidyAround(): void
  hideOthers(): void
  /* runs */
  stopRun(run: string): Promise<unknown>
}

const unbound = (name: string) => () => { throw new Error(`${name}: not wired (surface/actions/appOps.ts)`) }
const NONE: Ops = new Proxy({} as Ops, { get: (_, k) => (k === 'object' ? new Proxy({}, { get: (_o, m) => unbound('object.' + String(m)) }) : unbound(String(k))) })

/** What the providers call. */
export let ops: Ops = NONE
/** Bind the operations (appOps.ts at start; tests with spies). */
export function bindOps(o: Ops) { ops = o }
