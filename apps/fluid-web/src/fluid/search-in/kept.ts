/* FOCUS SEARCH FOLLOWS ITS CONTENT (search-in/, Fluid Focus B).
 *
 * A search belongs to what is searched, not to the place drawing it: a zone
 * moved from a leaf into a float or into Primary is drawn by a new component,
 * and its open bar, query, options and current match come with it. Held here
 * by content id (a zone's id; the conversation's CONVERSATION_ID), for this
 * page's life only -- presentation, never saved, never the record. Closing
 * the bar forgets it. Pure: no DOM, no React (tests/fluid_search_in_unit). */

export interface KeptSearch {
  q: string
  re: boolean
  cs: boolean
  /** the current match, 0-based; -1 while there are none */
  index: number
}

const kept = new Map<string, KeptSearch>()

/** The search content `id` has open, or null. */
export const keptSearch = (id: string | undefined): KeptSearch | null => (id ? kept.get(id) ?? null : null)

/** Open (or update) content `id`'s search. */
export function keepSearch(id: string | undefined, patch: Partial<KeptSearch>): void {
  if (!id) return
  kept.set(id, { ...(kept.get(id) ?? { q: '', re: false, cs: false, index: -1 }), ...patch })
}

/** The owner closed it: nothing is kept. */
export function forgetSearch(id: string | undefined): void {
  if (id) kept.delete(id)
}
