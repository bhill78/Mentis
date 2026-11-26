import type { MagnetTab } from './contract'

/** Puck indicators: compact, truthful entry points into the open card's tabs.
 * The ring is shown while the card is open -- the card is clicked open, so hover
 * and focus reveal nothing.
 * Never fabricate a count. Unknown stays "unavailable", not zero. */
export interface MagnetIndicator {
  key: 'posts' | 'files' | 'perspectives' | 'new'
  label: string
  glyph: string
  /** short badge text shown on the indicator itself; null when the count is unavailable */
  value: string | null
  /** full truthful explanation, used as the accessible name and tooltip */
  detail: string
  tab: MagnetTab
}

export function postsIndicator(sourceTally: number | null | undefined): MagnetIndicator {
  const known = typeof sourceTally === 'number' && Number.isFinite(sourceTally) && sourceTally >= 0
  return {
    key: 'posts', label: 'Posts', glyph: 'P',
    value: known ? String(sourceTally) : null,
    detail: known ? `${sourceTally} posts reported by the source — a source-wide total, not the loaded selection` : 'Source-wide post total unavailable',
    tab: 'Posts',
  }
}

export function filesIndicator(loaded: number, known: boolean, partial: boolean): MagnetIndicator {
  return {
    key: 'files', label: 'Files', glyph: 'F',
    value: known ? String(loaded) : null,
    detail: !known ? 'Loaded file count unavailable until this collection is read' : `${loaded} loaded${partial ? ', page partial — more may exist' : ''}`,
    tab: 'Files',
  }
}

/** HOW MANY KEPT QUESTIONS THIS MAGNET HOLDS.
 *
 *  Part E owned this file and left this one line for Part F, refusing to
 *  fabricate a count it could not have: a supported Perspectives type did not
 *  exist, so `null` was the truth. It exists now -- a Magnet keeps questions
 *  and the answers standing against them -- so the count is a real number
 *  where the caller has read one, and still `null` where nobody has.
 *
 *  `recorded` is the number of Perspectives the listing read returned. Unknown
 *  stays "unavailable", never zero, exactly as every other indicator's unknown
 *  does. The resting puck's own number is unchanged: it counts new items. */
export function perspectivesIndicator(recorded?: number | null): MagnetIndicator {
  const kept = tallied(recorded)
  return {
    key: 'perspectives', label: 'Perspectives', glyph: '?',
    value: kept === null ? null : String(kept),
    detail: kept === null ? 'Perspectives unavailable: no kept question has been read for this Magnet yet'
      : kept === 0 ? 'No question kept for this Magnet yet; ask one and its answer is kept with it'
      : `${kept} kept ${kept === 1 ? 'question' : 'questions'}, each with the answer standing against it`,
    tab: 'Perspectives',
  }
}

const tallied = (n: number | null | undefined): number | null =>
  typeof n === 'number' && Number.isFinite(n) && n >= 0 ? n : null
const capped = (n: number): string => (n > 99 ? '99+' : String(n))

/** How many of the rows shown are new since this viewer last opened the Magnet.
 *
 * A read of the record, not a guess: the rows in the latest batch whose content
 * identity is absent from the batch this viewer was last shown (`new_since`,
 * served at `collection/new`). Unknown -- no baseline recorded on this device,
 * or one the record will no longer verify -- stays unavailable, as every other
 * indicator's unknown does, and is never shown as 0. */
export function newInformationIndicator(newItems: number | null | undefined): MagnetIndicator {
  const fresh = tallied(newItems)
  return {
    key: 'new', label: 'New', glyph: '+',
    value: fresh === null ? null : String(fresh),
    detail: fresh === null ? 'New items unavailable: no collection this Magnet has shown you is recorded on this device'
      : fresh === 0 ? 'Nothing new since this Magnet was last opened'
      : `${fresh} new item${fresh === 1 ? '' : 's'} since this Magnet was last opened`,
    tab: 'All',
  }
}

/** What the collapsed puck carries at rest.
 *
 * The round-3 mockup (adm-d7d8151ea031) draws the four satellites around the
 * resting puck. The owner's alternative (ent-cdfc682f62eb) is one simple
 * notification count for new items instead, and that is what this is: one
 * number on the puck, nothing else, and nothing at all when there is nothing
 * to report. The ring stays with the open card.
 *
 * `newItems` is now a real number: the server diffs the latest batch's row
 * identities against the batch this viewer was last shown, which the client
 * supplies from the reading position it already persists -- no per-viewer state
 * on the server. A count is still never invented. Where there is no baseline
 * yet, or the record will not verify the one there is, the new-item total is
 * unknown and the badge falls back to what the Magnet is holding, naming which
 * of the two it shows. Unknown and zero both draw no badge, and the difference
 * between them is carried in the puck's accessible name. */
export interface MagnetRestingCount {
  /** badge text, capped so a long number cannot widen the puck; null draws no badge */
  value: string | null
  /** what the number counts, so a collected total is never read as a new-item one */
  kind: 'new' | 'collected'
  /** the puck's accessible explanation: exact, uncapped, never fabricated */
  detail: string
}

export function restingCount(newItems: number | null | undefined, collected: number | null | undefined): MagnetRestingCount {
  const fresh = tallied(newItems)
  if (fresh !== null) return {
    value: fresh > 0 ? capped(fresh) : null, kind: 'new',
    detail: fresh > 0 ? `${fresh} new item${fresh === 1 ? '' : 's'} since this Magnet was last opened` : 'Nothing new since this Magnet was last opened',
  }
  const held = tallied(collected)
  if (held === null) return { value: null, kind: 'collected', detail: 'Nothing has been read into this Magnet yet' }
  return {
    value: held > 0 ? capped(held) : null, kind: 'collected',
    detail: `${held} collected item${held === 1 ? '' : 's'}; how many of them are new is not known on this device`,
  }
}

export interface MagnetIndicatorInputs {
  retained?: boolean
  postsSourceTally: number | null | undefined
  filesLoaded: number
  filesKnown: boolean
  filesPartial: boolean
  /** New rows since the batch this viewer was last shown; `null` is unknown. */
  newItems: number | null | undefined
  /** Kept questions this Magnet holds, where a caller has read them. Omitted
   *  leaves the Perspectives indicator unavailable rather than zero. SEAM:
   *  `Magnet.tsx` is not Part F's file and does not read the Perspective
   *  listing, so nothing supplies this yet; its owner or the integrator wires
   *  `perspectivesOf(resource).snapshot().rows.length` in one line. */
  perspectives?: number | null
}

export function magnetIndicators(inputs: MagnetIndicatorInputs): MagnetIndicator[] {
  const indicators = [
    postsIndicator(inputs.postsSourceTally),
    filesIndicator(inputs.filesLoaded, inputs.filesKnown, inputs.filesPartial),
    perspectivesIndicator(inputs.perspectives),
    newInformationIndicator(inputs.newItems),
  ]
  if (inputs.retained) {
    indicators[0] = { ...indicators[0], detail: indicators[0].value === null ? 'How many posts there are is unavailable until something is collected' : `${inputs.postsSourceTally} collected posts in the collection shown` }
    indicators[1] = { ...indicators[1], detail: inputs.filesKnown ? `${inputs.filesLoaded} collected${inputs.filesPartial ? ' · this collection is partial, more may exist' : ''}` : 'How many files there are is unavailable until something is collected' }
  }
  return indicators
}
