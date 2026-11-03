/* SURFACE TENSION: LEVELS (plan §3.1, §3.3; part P1).
 *
 * A surface's level is one of four steps, icon · compact · standard ·
 * expanded. Content already sizes itself from its box (present/size.ts:
 * compact · medium · large, and the readable fallback plate); a level is
 * the same four steps under the surface's name for them, so the mapping
 * is one to one and nothing is lost either way. */

import { sizeOf, type Fit } from '../present/size'
import { LEVELS, type Level } from './types'

const FROM_FIT: Record<Fit, Level> = { fallback: 'icon', compact: 'compact', medium: 'standard', large: 'expanded' }
const TO_FIT: Record<Level, Fit> = { icon: 'fallback', compact: 'compact', standard: 'medium', expanded: 'large' }

/** The level size.ts's fit is (lossless: `fitOfLevel(levelOfFit(f)) === f`). */
export const levelOfFit = (f: Fit): Level => FROM_FIT[f]
/** The fit a level is, for content that reads size.ts. */
export const fitOfLevel = (l: Level): Fit => TO_FIT[l]
/** The automatic level of a box `w` content pixels wide. */
export const levelOfWidth = (w: number): Level => levelOfFit(sizeOf(w))

/** The level shown: the override until Reset size, else the automatic one. */
export const levelShown = (l: { auto: Level; override?: Level }): Level => l.override ?? l.auto

/** One step up (+1, Expand) or down (-1, Collapse) among the levels a
 *  surface supports; null at the end of its range. */
export function stepLevel(from: Level, step: 1 | -1, levels: ReadonlySet<Level>): Level | null {
  for (let i = LEVELS.indexOf(from) + step; i >= 0 && i < LEVELS.length; i += step)
    if (levels.has(LEVELS[i])) return LEVELS[i]
  return null
}
