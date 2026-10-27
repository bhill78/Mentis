/* ------------------------------------------------------------------------ *
 * HOW MANY GOVERNANCE ASKS ARE OWED IN ONE CONVERSATION (I-3, the chip's dot).
 *
 * Pure, so the answer can be checked without a browser: given what
 * `/api/owed` says this person owes and the Turns those asks were made in,
 * count the asks made in this Conversation whose expectation NAMES MATERIAL.
 * Nothing here can see a proposal, because a proposal asks nothing of anybody;
 * that is what keeps the dot from ever being driven by one.
 * ------------------------------------------------------------------------ */

/** Only what this needs of an `/api/owed` row. */
export interface OwedHere {
  expectation: string
  conversation: string | null
  turn: string | null
}

/** Only what this needs of a Turn: its expectations and what each names. A
 *  Turn that could not be read is null and contributes nothing. */
export interface TurnNaming {
  expectations?: { id: string; material?: string[] }[]
}

export function governanceAsksIn(
  owed: OwedHere[],
  turns: (TurnNaming | null)[],
  conversation: string,
): number {
  const open = new Set(owed.filter((r) => r.conversation === conversation).map((r) => r.expectation))
  let n = 0
  const counted = new Set<string>()
  for (const turn of turns)
    for (const e of turn?.expectations ?? [])
      if (open.has(e.id) && !counted.has(e.id) && (e.material ?? []).length > 0) {
        counted.add(e.id)
        n++
      }
  return n
}
