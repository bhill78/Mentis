/* Adapt exact destination identity to the P4 reader and back. The stored
 * inspection/association ref can be a request whose resolved target is a post.
 * Work/group metadata selects association validation; without it the real
 * exact-reference reader validates direct launches. The opener compares the
 * fresh target independently, preserving source and Work provenance.
 */
import type { Checked, OpenAt, Pressed, ResultOpens } from '../../work/freshness'
import { isResultOpens } from '../../work/freshness'
import type { ResultDestination, ResultTarget } from './targets'
import { actionOf } from './targets'

/** The three actions this check covers. `file` is `refRead.ts`'s; `external`,
 *  `commit` and `unavailable` are not reads of anything. */
export const CHECKED_HERE = new Set<string>(['post', 'record', 'conversation'])

/** Preserve the stored reference separately from the resolved target. */
export function pressedOf(d: ResultDestination, brain: string | null, moves: number): Pressed | null {
  const action = actionOf(d)
  if (!CHECKED_HERE.has(action)) return null
  const ref = d.ref || (d.target.kind === 'post' ? d.target.post
    : d.target.kind === 'record' ? d.target.ref : '')
  if (!ref) return null
  if (!isResultOpens(action)) return null
  return { expectation: d.work ?? null, group: d.group ?? null, ref, opens: action as ResultOpens, brain, moves }
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
