/* FLUID FOCUS: WHAT A SURFACE SHOWS IS KEPT APART FROM WHERE IT IS
 * (the approved prototype, Mentis-prototypes/fluid-workspace, DESIGN.md 2-3).
 *
 * A conversation's place has three kinds of PLACE a surface can be:
 *
 *   - the COLUMN: where the conversation column is drawn (Shell.tsx), at its
 *     width (`Arr.conversation.width`);
 *   - a LEAF of This post's tree (workspace/tree.ts), at its share;
 *   - a FLOAT over the main area, at its own rectangle.
 *
 * What a place shows is its CONTENT, and every content is a `Zone` record
 * (tree.ts): its id is the content's identity wherever it goes. Three kinds:
 *
 *   - the conversation: `show: 'conversation'` (CONVERSATION_ID); drawn by
 *     the one ConversationColumn, kept mounted and moved between places
 *     (hosts.tsx), so its scroll, draft and open sheets survive;
 *   - a workspace zone: a `slot` (follows what is read, keeps objects), as
 *     today, drawn by Zones.tsx's WorkspaceZone;
 *   - one object: a zone keeping one live address, `keepSlot([a], 'focus')`,
 *     with `options.from` saying where it was taken from ("From Claude's run
 *     · Sources"). Nothing is copied: the address is a reference, so the
 *     Brain record and its provenance are the object's own.
 *
 * PRIMARY is the content shown in the primary place (`FocusArr.primary`);
 * absent, the conversation. Making a content primary:
 *
 *   - both docked (column or leaf): they trade places, and so each other's
 *     position and size; nothing else moves (a two-leaf swap in the tree; a
 *     column and a leaf trade records);
 *   - a float: it and the primary trade CONTENT, not places. The primary
 *     place keeps its slot, the float keeps its exact rectangle, so the
 *     previous primary appears where the float was. Pressing it again on the
 *     same float swaps back; Undo also does.
 *
 * Placement only: all of this is kept in the place's arrangement (place.ts
 * `Arr.focus`), saved like the rest of it, and undone like the rest of it.
 * Nothing here writes to the record. */

import type { Zone } from '../workspace/tree'

/** The conversation's content id, and the show that marks it. */
export const CONVERSATION_ID = 'conv'
export const CONVERSATION_SHOW = 'conversation'

/** Where a float docks back to: beside `near`, on `side`, at `share`. */
export interface Origin { near: string; side: Side; share?: number }
export type Side = 'left' | 'right' | 'top' | 'bottom'
/** Where a drop lands on a section: its centre, or one of its edges. */
export type Where = 'center' | Side

export interface Float {
  /** the float's own id (a place), not its content's */
  id: string
  /** what it shows */
  zone: Zone
  /** px, relative to the main area (`.fx-main`), top-left */
  x: number
  y: number
  w: number
  h: number
  origin?: Origin
}

export interface FocusArr {
  /** the content in the primary place; absent: the conversation */
  primary?: string
  /** what the column place shows; absent: the conversation */
  column?: Zone
  /** the floats, back to front */
  floats?: Float[]
  /** primaries before this one, most recent last (Esc steps back) */
  previous?: string[]
}

/** Where a content is now. */
export type Located =
  | { place: 'column'; zone: Zone }
  | { place: 'leaf'; zone: Zone }
  | { place: 'float'; zone: Zone; float: Float }

export const MIN_FLOAT_W = 220
export const MIN_FLOAT_H = 120
export const MAX_FLOATS = 12

/** What a dragged thing is (drag.ts): a docked section by its content id, a
 *  float by its id, or one object by its live address and where it came from. */
export type Dragged =
  | { type: 'section'; id: string }
  | { type: 'float'; id: string }
  | { type: 'object'; address: string; from?: string }
