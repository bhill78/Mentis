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

export function perspectivesIndicator(): MagnetIndicator {
  return {
    key: 'perspectives', label: 'Perspectives', glyph: '?', value: null,
    detail: 'Perspectives unavailable: no supported Perspectives type exists yet',
    tab: 'Perspectives',
  }
}

export function newInformationIndicator(): MagnetIndicator {
  return {
    key: 'new', label: 'New', glyph: '+', value: null,
    detail: 'New-item count unavailable: no supported new-item total exists yet',
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
 * There is no new-item total yet -- per-viewer notification state is a
 * framework capability that has not been built (ent-5382b85d5f4e), so nothing
 * supplies `newItems` today and the badge truthfully falls back to what the
 * Magnet is actually holding, saying which of the two it shows. When that
 * contract lands it feeds `newItems` here and the badge becomes the new-item
 * count with no further design decision. A count is never invented: unknown
 * and zero both show no badge, and the difference between them is carried in
 * the puck's accessible name. */
export interface MagnetRestingCount {
  /** badge text, capped so a long number cannot widen the puck; null draws no badge */
  value: string | null
  /** what the number counts, so a collected total is never read as a new-item one */
  kind: 'new' | 'collected'
  /** the puck's accessible explanation: exact, uncapped, never fabricated */
  detail: string
}

const tallied = (n: number | null | undefined): number | null =>
  typeof n === 'number' && Number.isFinite(n) && n >= 0 ? n : null
const capped = (n: number): string => (n > 99 ? '99+' : String(n))

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
    detail: `${held} collected item${held === 1 ? '' : 's'}; a new-item count is not available yet`,
  }
}

export interface MagnetIndicatorInputs {
  retained?: boolean
  postsSourceTally: number | null | undefined
  filesLoaded: number
  filesKnown: boolean
  filesPartial: boolean
}

export function magnetIndicators(inputs: MagnetIndicatorInputs): MagnetIndicator[] {
  const indicators = [
    postsIndicator(inputs.postsSourceTally),
    filesIndicator(inputs.filesLoaded, inputs.filesKnown, inputs.filesPartial),
    perspectivesIndicator(),
    newInformationIndicator(),
  ]
  if (inputs.retained) {
    indicators[0] = { ...indicators[0], detail: indicators[0].value === null ? 'How many posts there are is unavailable until something is collected' : `${inputs.postsSourceTally} collected posts in the collection shown` }
    indicators[1] = { ...indicators[1], detail: inputs.filesKnown ? `${inputs.filesLoaded} collected${inputs.filesPartial ? ' · this collection is partial, more may exist' : ''}` : 'How many files there are is unavailable until something is collected' }
  }
  return indicators
}
