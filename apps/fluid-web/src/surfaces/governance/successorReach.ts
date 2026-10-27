import type { ProposedSideRead } from '../../api'

/* ------------------------------------------------------------------------ *
 * WHAT A PROPOSED SUCCESSOR REACHES, SAID PER STATE.
 *
 * A row under `proposed.successors` is NOT always still a candidate. The
 * proposal link is deliberately left in the record for ever — approving one
 * candidate does not withdraw it and does not withdraw its competitors — so
 * the same list keeps carrying a successor after it has been established on
 * its own, after it has ended, and after something else replaced it before
 * anybody established it. The read says which: `state` is the server's own
 * classification and `stands` is the fact behind it.
 *
 * Saying "reaches nobody" over every one of them therefore states, as fact,
 * the opposite of what the read says about three of the four states. It was
 * doing so beside a button that already branched on exactly this field: the
 * code held the fact and used it to decide whether to offer an act, but not
 * to decide what to say. THE SENTENCE AND THE BUTTON NOW ASK THE SAME
 * QUESTION OF THE SAME FIELD.
 *
 * NOTHING HERE CLAIMS A SUPERSESSION. That a successor stands says nothing
 * about whether it ended any particular predecessor: those are two facts on
 * two relations, and `superseded_by` is the one that answers it. So the
 * `stands` wording stops at what is known.
 * ------------------------------------------------------------------------ */

export type SuccessorState = ProposedSideRead['items'][number]['state']

/** The chip beside the candidate's name — the four exclusive words, said the
 *  way the register says them so two surfaces cannot disagree about one
 *  item. Only a candidate reaches nobody. */
export const SUCCESSOR_CHIP: Record<SuccessorState, string> = {
  candidate: 'reaches nobody',
  stands: 'stands',
  ended: 'ended',
  replaced: 'replaced before establishment',
}

/** The sentence under a proposal card. `said` is what the PREDECESSOR is
 *  called, because the candidate's state is only half of what a reader is
 *  here for: the other half is what it means for the item in front of them.
 *  `predecessorStands` is read from the record rather than assumed — the
 *  panel goes on showing proposals after the row it is about has ended —
 *  and `null` is the third answer: a Kind that never declared whether
 *  standing is meaningful for its entries has no standing to report, which
 *  is not the same as not standing. Nothing is said about it. */
export function successorReach(
  state: SuccessorState,
  said: string,
  predecessorStands: boolean | null,
): string {
  const meanwhile =
    predecessorStands === null
      ? ''
      : predecessorStands
        ? ` ${said} keeps standing meanwhile.`
        : ` ${said} no longer stands, so establishing this would end nothing further.`
  switch (state) {
    case 'candidate':
      return `The replacement reaches nobody until established.${meanwhile}`
    case 'stands':
      /* Established, and therefore reaching whoever it is placed among. What
         it has actually ended is `superseded_by` and is not read from here. */
      return `The replacement was established and stands. What it has ended, if anything, is written separately.`
    case 'ended':
      return `The replacement was established and has since ended, so it reaches nobody now.`
    case 'replaced':
      return `The replacement was itself replaced before anybody established it, so it never reached anybody.`
  }
}
