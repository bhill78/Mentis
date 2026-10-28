import { qs, useApi } from '../../api'
import type { SpaceNode } from './layout'

/* ------------------------------------------------------------------------ *
 * WHAT IS CHOSEN, AND WHAT IT SAYS -- held apart from anything that shows it.
 *
 * The 3D Brain sends one short line per star; the thing somebody chose is
 * worth more than that (owner, 2026-10-10: what it is AND what it says -- a
 * Decision and what was decided, and why), so its fuller words are asked for
 * once, on choosing, from `/api/space/said`.
 *
 * KEPT OUT OF THE CARD ON PURPOSE. A details pane is coming (owner: "do not
 * make any changes that prevent that"). The selection lives in SpaceSurface
 * and this hook turns it into data; the card is one reader of it, and a pane
 * beside the canvas would be another reading the same thing.
 * ------------------------------------------------------------------------ */

export interface SaidOf {
  entry: string
  said: string | null
  deleted: boolean
  edited: boolean
}

export interface Chosen {
  node: SpaceNode
  /** its fuller words once they have arrived; the one-line summary until then */
  said: string | null
  /** true while the fuller words are still being read */
  reading: boolean
}

export function useChosen(node: SpaceNode | null): Chosen | null {
  const got = useApi<SaidOf>(node ? `/api/space/said${qs({ entry: node.entry })}` : null, { live: false })
  if (!node) return null
  const mine = got.data && got.data.entry === node.entry ? got.data : null
  return {
    node,
    said: mine ? mine.said : node.deleted ? null : node.summary,
    reading: !mine && !got.error,
  }
}
