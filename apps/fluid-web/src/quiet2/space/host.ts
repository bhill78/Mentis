/* WHAT THE PAGE GIVES THE GRAPH'S FRAME.
 *
 * The frame (viewer/Viewer.tsx) knows only which session a viewer is bound
 * to. Where a chosen thing is read, and what dragging its card carries, are
 * the PAGE's (Quiet2.tsx): they move the centre column, put the leaving
 * question and walk the browser's history, none of which a renderer or a
 * frame may do. They are handed down here so the graph's host can be drawn
 * wherever the frame draws it -- in a column or maximised -- without the
 * frame learning anything about the Brain. */
import { createContext } from 'react'
import type { DragEvent } from 'react'
import type { SpaceNode } from './contract'

export interface SpaceHostApi {
  /** go where this thing lives (routing.ts decides which reader) */
  onOpen: (node: SpaceNode) => void
  /** the chosen card's drag: exactly the payload Fluid's own places carry
   *  (fluid/brain/address.ts `dragPayload`) */
  onDragChosen: (node: SpaceNode, e: DragEvent) => void
  /** the work row behind a maximised viewer is inert: a graph drawn in a
   *  column there is not visible, and its canvas pauses (addendum §1) */
  inertHost: boolean
}

export const SpaceHostContext = createContext<SpaceHostApi | null>(null)
