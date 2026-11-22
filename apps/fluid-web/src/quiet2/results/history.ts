/* A RESULT IN THE BROWSER'S OWN HISTORY -- ONLY WHERE IT TAKES THE CENTRE
 * (navigation review adm-d9152e0643d7, B3; owner's navigation work, 2026-11-16
 * and 2026-11-20).
 *
 * THE TWO DEFECTS THIS ANSWERS.
 *   - A SIDE COLUMN IS NOT A PAGE. Opening something beside the conversation
 *     pushed history entries and ran the centre's unsaved-work guards, so
 *     Back walked out of a column the reader was still using, and merely
 *     opening a free column could ask them about a draft they had not left.
 *   - WHAT TAKES THE CENTRE WAS NOT AN ENTRY AT ALL. A maximised result left
 *     nothing behind, so Back left Quiet Chat (on a machine that moves between
 *     TEST and DAY-TO-DAY, to the other server), and closing jumped to the
 *     post the bytes came from rather than back to the reader's own place.
 *
 * THE RULE. A side viewer (`s1`/`s2`) never touches `CentreAt`, never pushes
 * an entry and never invokes a centre guard. Only a CENTRE-DISPLACING
 * transition -- maximising, or taking the centre for a record or a post --
 * becomes one entry, and exactly one: moving, maximising and restoring the
 * same viewer must not stack duplicates (H2).
 *
 * AN ENTRY IS INTENT AND IDENTITY, NOTHING ELSE: which Brain instance, which
 * opening, the exact target, and the Place underneath it. No viewer, no bytes,
 * no draft text, no renderer state, and no address of its own -- a refresh
 * lands on the Place it was over, which is what `address.ts` already does for
 * everything that has no address (an entry inspector, a Turn read from the
 * graph). This is deliberately the shape `space/history.ts` uses for the 3D
 * Brain, so `centreHistory`'s own push, pop, replace and search are exactly
 * what they were.
 *
 * Pure, so every row is checkable without a browser
 * (`tests/quiet2_result_opener_unit.ts`). */
import type { ResultTarget } from './targets'
import { targetKey } from './targets'
import { brainVerdict, type BrainKey, type LaunchPlace } from './launch'

/** WHAT THE CENTRE HOLDS while a result is read there. */
export interface ResultIntent {
  brainKey: BrainKey | null
  /** which opening made it (`launch.ts`): its live launch, where still held */
  opening: number
  target: ResultTarget
  /** the Place it is over, so a refresh and a close both have somewhere true */
  place: LaunchPlace
}

/** One entry of the centre's history, as the page's payload union holds it. */
export type ResultHistory = { result: ResultIntent }

/* THE SAME ENTRY IS THE SAME DATA. `centreHistory.plan` compares entries by
   their JSON, so every entry is built here, in one key order: an entry for the
   same opening of the same target is byte-identical however it was reached,
   which is what lets the existing search walk BACK to it instead of pushing a
   second one. */
export const resultIntent = (brainKey: BrainKey | null, opening: number, target: ResultTarget, place: LaunchPlace): ResultHistory =>
  ({ result: { brainKey, opening, target, place } })

export const isResultHistory = (to: unknown): to is ResultHistory =>
  !!to && typeof to === 'object' && 'result' in (to as object) && !!(to as ResultHistory).result

/** Whether two entries are the same result being read, whatever the opening:
 *  for the host's own "is this mine?" check. */
export const sameResult = (a: ResultIntent, b: ResultIntent) =>
  a.opening === b.opening && targetKey(a.target) === targetKey(b.target)

/* -- where a result is shown ------------------------------------------------ */

/** Where a result is, as the viewer store says (`viewer/viewers.ts` `Where`),
 *  plus the two states that are not open: never opened, and closed. */
export type Shown = 'max' | 's1' | 's2' | 'none'

/** ONLY THE MAXIMISED PLACE DISPLACES THE CENTRE. A column sits beside the
 *  conversation: the centre still holds whatever it held. */
export const entersCentre = (place: Shown) => place === 'max'

/** WHAT ONE TRANSITION DOES TO THE HISTORY (H1, H2):
 *
 *    push     a displacement that was not one before: one entry, once
 *    consume  the displacement is over (restored to a column, or closed):
 *             the entry it owns is given up, and nothing is added
 *    none     a side column, a move between columns, or no change at all
 *
 *  A placement the reader cancelled never reaches here, so an open that was
 *  not made leaves no entry behind. */
export type HistoryStep = 'push' | 'consume' | 'none'

export function historyStep(from: Shown, to: Shown): HistoryStep {
  if (from === to) return 'none'
  if (entersCentre(to)) return 'push'
  if (entersCentre(from)) return 'consume'
  return 'none'
}

/* -- closing ---------------------------------------------------------------- */

/** HOW A CLOSE LEAVES THE HISTORY (B3, item 3).
 *
 *    back        the entry this result owns is the one shown and the launch
 *                Place is directly behind it: one step back, exactly as the
 *                reader's own Back -- so there is never a second push or pop
 *    replace     it owns the entry but the Place is not behind it (a reload,
 *                or a walk that went further): this entry BECOMES the Place,
 *                adding nothing
 *    frame-only  navigation has since left this entry: only the frame closes,
 *                the history is left alone, and the explicit return bar is
 *                what restores the launch -- through the existing guards
 *
 *  `revealPost(source.post)` is not among them: closing returns to where the
 *  reader WAS, never to where the bytes came from. */
export type ClosePlan = 'back' | 'replace' | 'frame-only'

export function closePlan(owns: boolean, placeBehind: boolean): ClosePlan {
  if (!owns) return 'frame-only'
  return placeBehind ? 'back' : 'replace'
}

/** Whether a close that found its own entry gone still owes the reader a way
 *  back: it does, and that is the launch-return bar, not a history move. */
export const keepsReturnBar = (plan: ClosePlan) => plan === 'frame-only'

/* -- landing on an entry again ---------------------------------------------- */

/** WHAT TO DO WITH A RESULT ENTRY THE BROWSER HAS LANDED ON.
 *
 *  FORWARD MUST NOT REOPEN A PRIOR BRAIN'S FILE (B3, item 7): an entry made
 *  against another Brain -- including another INSTANCE of the same corpus, a
 *  copy served elsewhere or one restored in place -- is not replayed at all,
 *  and the Place it was over is what the reader is left on. */
export type ResultResume =
  /** this page's Brain, and the opening's launch is still live: reopen it */
  | { how: 'live'; intent: ResultIntent }
  /** this page's Brain, no live launch (a reload): resolve the target again,
   *  and offer the saved Place as the way back; promise nothing else */
  | { how: 'resolve'; intent: ResultIntent; place: LaunchPlace }
  /** another Brain or another instance: nothing replayed */
  | { how: 'other-brain'; place: LaunchPlace; words: string }

export function resumeResult(h: ResultHistory, now: { brainKey: BrainKey | null; live: (opening: number) => boolean; words: string }): ResultResume {
  const r = h.result
  if (brainVerdict(r.brainKey, now.brainKey) !== 'same') return { how: 'other-brain', place: r.place, words: now.words }
  return now.live(r.opening) ? { how: 'live', intent: r } : { how: 'resolve', intent: r, place: r.place }
}
