/* THE FRESH READ FOR A POST, A BRAIN RECORD OR A CONVERSATION (P4) -- the
 * other half of `refRead.ts`.
 *
 * `refRead.ts` describes an ARTIFACT again on the press. Until now the other
 * three destinations kept their existing guarded readers, which report the
 * GUARD'S outcome and the NAVIGATION -- not whether the target is still there
 * to be read. So a post deleted since the row was drawn, a conversation
 * permanently deleted, or a record that stopped being readable was found out
 * by ARRIVING at it: the reader had already lost where they were.
 *
 * THE READ IS THE RESULT PAGE THE ROW CAME FROM. `src/work/freshness.ts`
 * re-reads one group of it over the existing route, and decides on the server's
 * own `available`, `opens` and words. Nothing new is asked of the server and no
 * rule about who may read what is decided anywhere on this path: a check can
 * only ever REFUSE an open the row in hand offered.
 *
 * THIS FILE IS ONLY THE SHAPES BETWEEN THE TWO. `freshness.ts` knows nothing of
 * a `ResultDestination`; the opener knows nothing of a Work result page. What a
 * fresh answer is allowed to change is the same as for an artifact: the
 * destination's own availability facts and where it goes. Whether that is still
 * THE SAME THING is `opener.ts`'s `sameThing`, by `targetKey`, exactly as for
 * the artifact route -- so a post that now answers in another conversation is
 * refused there, not silently followed here.
 *
 * PURE, like `targets.ts` beside it: facts in, a destination out. The one read
 * is `freshness.ts`'s. */
import type { Checked, OpenAt, Pressed, ResultOpens } from '../../work/freshness'
import { isResultOpens } from '../../work/freshness'
import type { ResultDestination, ResultTarget } from './targets'
import { actionOf } from './targets'

/** The three actions this check covers. `file` is `refRead.ts`'s; `external`,
 *  `commit` and `unavailable` are not reads of anything. */
export const CHECKED_HERE = new Set<string>(['post', 'record', 'conversation'])

/** WHETHER THIS DESTINATION CAN BE ASKED ABOUT AGAIN. It can only where the
 *  record said which Work and which result group it belongs to: those two are
 *  the page the re-read asks for. A destination that says neither -- a Needs
 *  you reference, a Brain record opened from a link -- keeps exactly the
 *  behaviour it has today, and is not refused for want of a check. */
export function pressedOf(d: ResultDestination, brain: string | null, moves: number): Pressed | null {
  const action = actionOf(d)
  if (!CHECKED_HERE.has(action)) return null
  if (!d.work || !d.group) return null
  const ref = d.target.kind === 'post' ? d.target.post
    : d.target.kind === 'record' ? d.target.ref : ''
  if (!ref) return null
  if (!isResultOpens(action)) return null
  return { expectation: d.work, group: d.group, ref, opens: action as ResultOpens, brain, moves }
}

/** The target the FRESH answer names. Compared against the pressed one by
 *  `opener.ts` (`targetKey`), which refuses anything that is not the same. */
export function targetOf(at: OpenAt): ResultTarget {
  if (at.opens === 'post') return { kind: 'post', conversation: at.conversation, post: at.post }
  if (at.opens === 'conversation') return { kind: 'record', ref: at.conversation }
  return { kind: 'record', ref: at.entry }
}

/** THE DESTINATION WITH WHAT THE FRESH READ ACTUALLY READ, and nothing else
 *  touched -- `freshly` in `mount.ts` for the artifact route, said for these.
 *  The record's own facts (its label, its basis, its Work, where it came from)
 *  are the destination's and are carried through: the re-read answers about
 *  AVAILABILITY and WHERE, which is all it is asked. */
export function freshlyOpen(d: ResultDestination, c: Extract<Checked, { how: 'open' }>): ResultDestination {
  return {
    ...d, target: targetOf(c.at), availability: 'ok', available: true,
    opens: c.at.opens, reason: null,
    label: c.item.inspection?.label || d.label,
  }
}
