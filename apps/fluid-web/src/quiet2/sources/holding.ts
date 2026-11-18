/* WHAT SETTING UP A SOURCE HOLDS, for somebody about to leave it.
 *
 * THE DEFECT THIS ANSWERS (independent review, 2026-11-17): the question was
 * asked from the step the flow said it was on, not from what the flow was
 * actually holding. A name typed on the first step, and a path typed into the
 * picker and not yet used, were on the page and invisible to the guard: the
 * setup vanished without a word. And a take that ENDED after the reader had
 * gone pulled them back out of the conversation they had just chosen.
 *
 * So there is one rule here, in one place, and every setup flow -- a folder,
 * a repository, a database file -- says the same four plain things about
 * itself and lets this decide (`leaving.ts` then decides what is asked):
 *
 *   - something typed or chosen that nothing has recorded
 *   - a preview in hand that has not been taken
 *   - which run, if any, is in flight
 *   - whether the source has been taken (then nothing here is unfinished)
 *
 * WHAT A RUN IN FLIGHT MEANS IS NOT THE SAME FOR BOTH RUNS, and saying it
 * wrongly is what the review caught:
 *
 *   - LOOKING at the source (a plan) answers only this page. Leaving does not
 *     cancel it, but its answer lands nowhere and the reader asks again.
 *   - TAKING the source (a sweep) answers the BRAIN. It is not this page's
 *     to lose: the source is added whether the reader stays or not. Nothing
 *     here would be lost by leaving, so nothing is asked -- it is said. */
import type { RunView } from '../../surfaces/sources/route'
import type { Standing } from '../leaving'

/** What a setup flow holds, in the plainest terms it can give. */
export interface Held {
  /** anything typed or chosen here that nothing has recorded: a name, a path
   *  typed into the picker and not yet used, a file chosen, tables picked */
  typed: boolean
  /** a preview in hand (or a private snapshot taken) that has not been taken */
  preview: boolean
  /** the run in flight, by what the server calls it */
  run: RunView['kind'] | null
  /** the source has been taken: there is nothing unfinished here any more */
  done: boolean
}

export const PAGE = 'Add a source'
export const TAKING = 'Taking the source'
export const LOOKING = 'Looking at the source'
/** where a take lands, whether or not the reader stays for it */
export const LANDS = 'The source is added to the Brain either way.'

/** What Add a source holds now, for `leaving`. */
export function adding(h: Held): Standing | null {
  if (h.done) return null
  const taking = h.run === 'sweep'
  return {
    what: PAGE,
    dirty: !taking && h.typed,
    preview: !taking && h.preview,
    run: h.run
      ? (taking
          ? { what: TAKING, interrupted: false, lands: LANDS }
          : { what: LOOKING, interrupted: true })
      : null,
  }
}

/** WHETHER A SOURCE'S PREVIEW IN HAND IS UNFINISHED WORK. A preview that
 *  would change something is: leaving drops it and nothing was applied. A
 *  REFRESH preview that says "Nothing has changed since the last refresh"
 *  is not -- there is nothing in it to apply, its only buttons are Preview
 *  again and Close, and asking "Leave … unfinished?" about it holds the
 *  reader up over nothing. It still counts where it carries something:
 *  a change of selection (always the reader's own unsaved change), the
 *  first refresh of a place located again (taking it accepts the place), or
 *  decisions the preview is waiting for or the reader has begun to give. */
export function previewHeld(
  pv: { counts: Record<string, number>; binding_changed?: boolean; can_confirm?: boolean } | null | undefined,
  o: { revising: boolean; decisionsDirty: boolean },
): boolean {
  if (!pv) return false
  if (o.revising || o.decisionsDirty || pv.binding_changed || pv.can_confirm === false) return true
  const c = pv.counts
  return (c.new ?? 0) + (c.changed ?? 0) + (c.reappeared ?? 0) + (c.absent ?? 0) > 0
}
