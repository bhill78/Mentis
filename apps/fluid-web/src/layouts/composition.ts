/* ------------------------------------------------------------------------ *
 * WHAT THE CANVAS IS SHOWING, AS A COMPOSITION RATHER THAN A SET OF PANES.
 *
 * Mark IV's first workspace let seven surfaces be switched on independently
 * and laid each one out as another column. That is a pane compositor: the
 * person is asked where every surface goes, columns accumulate until they no
 * longer fit, and the interface needs a rule for which one "gives way".
 *
 * This is the other model. The canvas has ONE PRIMARY PRESENTATION at a
 * chosen BREADTH, and depth opens as a STACK rather than as more columns.
 * Nothing here is a durable fact and nothing is ever sent anywhere: it is
 * navigation state, exactly like the Place it lives in.
 * ------------------------------------------------------------------------ */

import type { Id } from '../api'

/** How much canvas the current primary presentation is given. It is a
 *  property of the PRESENTATION, not of a conversation pane: a map, a graph
 *  or a rendered artifact may legitimately want far more room than prose. */
export type Breadth = 'compact' | 'normal' | 'wide'

export const BREADTHS: Breadth[] = ['compact', 'normal', 'wide']

/** The reading measure each breadth gives the primary presentation. Prose
 *  stops widening at its own comfortable measure; everything else uses the
 *  room. */
export const MEASURE: Record<Breadth, string> = {
  compact: 'min(52ch, 100%)',
  normal: 'min(68ch, 100%)',
  wide: '100%',
}

/** What is holding the centre of the canvas. Conversation is the normal
 *  working presentation; it is not a permanent centre pane. */
export type Primary = 'conversation' | 'graph' | 'media'

/** The three resolutions of ONE scoped operational history.
 *
 *    glance      a very quiet vertical spine beside the conversation
 *    structure   the causal graph, grown leftward from that spine
 *    explanation the same history in words
 *
 * They are not three surfaces. Scope follows the current Conversation/Topic
 * automatically, so none of them carries a scope control of its own. */
export type Resolution = 'glance' | 'structure' | 'explanation'

/** One layer of contextual depth. Only the top of the stack is drawn.
 *
 *  A stack rather than a set is the whole point: opening Media from a Thread
 *  REPLACES the thread in the contextual region and closing it RETURNS to the
 *  thread, instead of standing Conversation, Thread and Media side by side. */
export type Layer =
  | { kind: 'thread'; id: Id }
  | { kind: 'media'; key: string | null }
  | { kind: 'details'; turn: Id }
  /** a durable Entry, inspected. A Kind card is a door and this is the room
   *  behind it: the same contextual region, one depth further in, so moving
   *  from a Finding to what it was derived from never opens a column. */
  | { kind: 'entry'; id: Id }

export type LayerKind = Layer['kind']

export const topOf = (stack: Layer[]): Layer | null => stack[stack.length - 1] ?? null

/** Push a layer, or replace the top when it is already that kind — so
 *  stepping from one image to another, or one turn's details to another's,
 *  never deepens the stack. */
export function push(stack: Layer[], next: Layer): Layer[] {
  const top = topOf(stack)
  if (top && top.kind === next.kind) return [...stack.slice(0, -1), next]
  return [...stack, next]
}

/** Close the top layer and return to whatever was under it. */
export const pop = (stack: Layer[]): Layer[] => stack.slice(0, -1)

/** Drop every layer of one kind, wherever it sits — what closing a surface
 *  from the workspace control means, as against stepping back out of it. */
export const without = (stack: Layer[], kind: LayerKind): Layer[] =>
  stack.filter((l) => l.kind !== kind)

export const holds = (stack: Layer[], kind: LayerKind): boolean =>
  stack.some((l) => l.kind === kind)

/** The contextual layer's own width. The brief's range, clamped to what the
 *  viewport can actually spare so the primary presentation is never crushed
 *  to reach it. */
export const CONTEXT_MIN = 380
export const CONTEXT_MAX = 480
export const contextWidth = (room: number): number =>
  Math.max(300, Math.min(CONTEXT_MAX, Math.min(CONTEXT_MIN + 40, room - 420)))

/** What the top layer is called, for the contextual region's own quiet
 *  identity line and for its accessible name. */
export const layerLabel = (l: Layer): string =>
  l.kind === 'thread' ? 'Thread' : l.kind === 'media' ? 'Media' : 'Details'
