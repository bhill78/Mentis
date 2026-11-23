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
    indicators[0] = { ...indicators[0], detail: indicators[0].value === null ? 'Retained post count unavailable until a batch is collected' : `${inputs.postsSourceTally} posts retained in the most recent bounded batch` }
    indicators[1] = { ...indicators[1], detail: inputs.filesKnown ? `${inputs.filesLoaded} retained${inputs.filesPartial ? ', batch partial — more may exist' : ''}` : 'Retained file count unavailable until a batch is collected' }
  }
  return indicators
}
