/* PACKAGE B owns this module: the geometry of one topic's mark, computed from
 * `topics[].turns` rather than hand-tuned per class -- so a selected mark's
 * emphasis is a number the data produces, not only a CSS selector's doing. */

const MIN_THICKNESS = 3
const MAX_THICKNESS = 6
const MIN_LENGTH = 18
const MAX_LENGTH = 42
/** Added to both dimensions when the mark is the selected topic's, on top of
 *  whatever its own turn count already earned it. */
const SELECTED_BONUS = 1

export interface MarkMetrics {
  /** the bar's cross-axis size, in px -- what "thickness" styles. */
  thickness: number
  /** the bar's along-axis extent, in px -- what "height" (in the stacked,
   *  vertical rail) styles. */
  length: number
}

/** `turns` against the busiest topic shown alongside it, `max`. A `max` of
 *  zero -- nothing in the conversation has a turn yet -- draws every mark at
 *  its minimum rather than dividing by zero. */
export function markMetrics(turns: number, max: number, selected: boolean): MarkMetrics {
  const ratio = max > 0 ? Math.min(1, turns / max) : 0
  const bonus = selected ? SELECTED_BONUS : 0
  return {
    thickness: Math.round(MIN_THICKNESS + ratio * (MAX_THICKNESS - MIN_THICKNESS) + bonus),
    length: Math.round(MIN_LENGTH + ratio * (MAX_LENGTH - MIN_LENGTH) + bonus * 2),
  }
}
