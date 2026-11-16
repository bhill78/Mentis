/* THE BRAIN BROWSER'S DATA (Manage Brain, round 2) — INTERFACE CONTRACT.
 *
 * Workstream C owns the real implementation of `fetchBrainList` (the Brain's
 * records, through Mentis's own reads) and will replace this file whole at
 * integration. Every other builder imports only what is exported here, by
 * these exact names and shapes — change neither without telling the other
 * two workstreams.
 *
 * `plainStandingLabel` is the one genuinely pure piece (a string mapping
 * from DESIGN-r2.md's "The record, at rest" table) and is kept for real
 * here: Workstream C's own copy must say the same thing, so the two are
 * expected to collide and merge cleanly rather than one deferring to the
 * other. */

export type BrainFilter = 'knowledge' | 'governing' | 'needs-you' | 'all'

export interface BrainRecordSummary {
  id: string
  kind: string                 // e.g. "lesson", "rule", "decision", "persona", ...
  text: string                 // short summary/body text
  standingPlain: string        // e.g. "In effect as knowledge", "Not in effect — proposed by @X, waiting for your decision"
  standingLabel: string        // the short pill word, e.g. "Adopted · knowledge", "Adoption requested · rule"
  governs: boolean
  challenged: boolean
  conversation?: string | null
  turn?: string | null
  number?: number | null
}

export interface BrainRecordDetail extends BrainRecordSummary {
  // Workstream C fills this in fully; for now just extend the summary.
}

// STUB — replaced by Workstream C's real read of the Brain. Returns nothing
// rather than fake rows, so nothing that looks like a real record can reach
// a real screen from this branch.
export async function fetchBrainList(_filter: BrainFilter, _query: string): Promise<BrainRecordSummary[]> {
  return []
}

/** Maps a Ladder `status` (+ whether it governs) to the plain-language
 *  sentence from DESIGN-r2.md's "The record, at rest" table. A status this
 *  function does not recognise reads as `recorded` does: Mentis never
 *  invents a stronger claim than the Ladder made. */
export function plainStandingLabel(status: string, governs: boolean): string {
  switch (status) {
    case 'adopted':
      return governs
        ? 'In effect — agents are given it as a rule'
        : "In effect as knowledge — agents are told it when relevant; it doesn't bind them"
    case 'adoption_requested':
      return 'Not in effect — proposed, waiting for your decision'
    case 'declined':
      return 'Not in effect — declined'
    case 'superseded':
      return 'Not in effect — replaced'
    case 'ended':
    case 'retired':
      return 'Not in effect — ended'
    case 'recorded':
    default:
      return 'Recorded, not adopted — reaches agents only as labelled past experience'
  }
}
