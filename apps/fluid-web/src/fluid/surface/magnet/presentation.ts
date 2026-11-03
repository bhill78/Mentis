/* MAGNET PRESENTATION, tolerant across P0 and M1.
 *
 * P0 has only presentation.renderer. M1 adds presentation.theme and may add
 * bounded source-summary signals. Read those additions as unknown data here:
 * a missing field preserves P0, a recognised value is used, and an unknown
 * value is reported unavailable instead of being guessed.
 *
 * A theme is only a default for Fluid's existing Look. Each property stored
 * on a placement wins independently, so setting opacity does not accidentally
 * replace the theme's panel or content treatment. */

import { DEFAULT_APPEARANCE, readAppearance, type Appearance, type Fill } from '../../present/types'

export const MAGNET_THEMES = ['minimal', 'anchored', 'glass', 'floating'] as const
export type MagnetTheme = typeof MAGNET_THEMES[number]

/** Appearance, not position: anchored is the settled solid treatment and
 * floating is the lifted clear-panel treatment used by Fluid windows. */
export const MAGNET_THEME_LOOK: Record<MagnetTheme, Appearance> = {
  minimal: { panel: 'transparent', content: 'transparent', opacity: 0.6 },
  anchored: { panel: 'solid', content: 'tinted', opacity: 1 },
  glass: { panel: 'tinted', content: 'tinted', opacity: 1 },
  floating: { panel: 'transparent', content: 'tinted', opacity: 0.82 },
}

export type ThemeRead =
  | { state: 'absent' }
  | { state: 'available'; theme: MagnetTheme }
  | { state: 'unavailable'; reason: string }

const record = (v: unknown): Record<string, unknown> | null => v != null && typeof v === 'object' && !Array.isArray(v)
  ? v as Record<string, unknown> : null

export function readMagnetTheme(config: unknown): ThemeRead {
  const presentation = record(record(config)?.presentation)
  const value = presentation?.theme
  if (value == null) return { state: 'absent' }
  if (typeof value === 'string' && (MAGNET_THEMES as readonly string[]).includes(value)) {
    return { state: 'available', theme: value as MagnetTheme }
  }
  return { state: 'unavailable', reason: 'Theme unavailable: this Magnet uses a presentation theme this build does not understand.' }
}

export interface MagnetLook {
  appearance: Appearance
  theme: ThemeRead
}

/** Resolve a theme default with a placement's explicit Look over it, one
 * property at a time. Bad or absent placement fields leave that property's
 * default intact; readAppearance supplies the same clamping Fluid uses. */
export function magnetLook(config: unknown, placement: unknown, fallback: Appearance = DEFAULT_APPEARANCE): MagnetLook {
  const theme = readMagnetTheme(config)
  const base = theme.state === 'available' ? MAGNET_THEME_LOOK[theme.theme] : fallback
  const own = record(placement)
  if (!own) return { appearance: { ...base }, theme }
  const partial: Partial<Appearance> = {}
  if (own.panel === 'transparent' || own.panel === 'tinted' || own.panel === 'solid') partial.panel = own.panel as Fill
  if (own.content === 'transparent' || own.content === 'tinted' || own.content === 'solid') partial.content = own.content as Fill
  if (typeof own.opacity === 'number') partial.opacity = own.opacity
  return { appearance: readAppearance(partial, base), theme }
}

export interface SummaryPresence {
  activity: number | null
  participants: number | null
  working: number | null
  participantNames: string[]
  participantNamesMore: number
  workerNames: string[]
  workerNamesMore: number
}

const PEOPLE_SHOWN = 4

const count = (v: unknown): number | null => typeof v === 'number' && Number.isFinite(v) && v >= 0 ? Math.floor(v) : null
const personName = (v: unknown): string | null => {
  if (typeof v === 'string') return v.trim() || null
  const p = record(v)
  if (!p) return null
  for (const key of ['alias', 'name', 'participant_name']) {
    const name = p[key]
    if (typeof name === 'string' && name.trim()) return name.trim()
  }
  return null
}

const personIdentity = (v: unknown): { key: string; name: string } | null => {
  const name = personName(v)
  if (!name) return null
  const p = record(v)
  const stable = p && ['id', 'ref', 'participant_id'].map((key) => p[key]).find((id) => typeof id === 'string' && id.trim())
  return { key: typeof stable === 'string' ? `id:${stable.trim()}` : `name:${name.toLocaleLowerCase()}`, name }
}

const addPeople = (values: unknown[], people: Map<string, string>) => {
  for (const value of values) {
    const person = personIdentity(value)
    if (person && !people.has(person.key)) people.set(person.key, person.name)
  }
}

/** Signals only from source summaries already in hand. This never starts a
 * read. Identified people are de-duplicated across sources and roles stay
 * separate. Anonymous numeric totals use the largest source value: summing
 * them could count the same unidentified people more than once. */
export function summaryPresence(summaries: readonly unknown[]): SummaryPresence {
  let activity: number | null = null
  let participantTotal: number | null = null
  let workerTotal: number | null = null
  let sawParticipants = false
  let sawWorkers = false
  const participants = new Map<string, string>()
  const workers = new Map<string, string>()
  for (const value of summaries) {
    const s = record(value)
    if (!s) continue
    const at = count(s.activity)
    if (at != null) activity = Math.max(activity ?? 0, at)
    const ps = s.participants
    if (Array.isArray(ps)) {
      sawParticipants = true
      addPeople(ps, participants)
    } else {
      const n = count(ps)
      if (n != null) { sawParticipants = true; participantTotal = Math.max(participantTotal ?? 0, n) }
    }
    const ws = s.workers ?? s.working
    if (Array.isArray(ws)) {
      sawWorkers = true
      addPeople(ws, workers)
    } else {
      const n = count(ws)
      if (n != null) { sawWorkers = true; workerTotal = Math.max(workerTotal ?? 0, n) }
    }
  }
  const participantNames = [...participants.values()]
  const workerNames = [...workers.values()]
  const participantCount = sawParticipants ? Math.max(participantTotal ?? 0, participants.size) : null
  const workerCount = sawWorkers ? Math.max(workerTotal ?? 0, workers.size) : null
  return {
    activity,
    participants: participantCount,
    working: workerCount,
    participantNames: participantNames.slice(0, PEOPLE_SHOWN),
    participantNamesMore: Math.max(0, participantNames.length - PEOPLE_SHOWN),
    workerNames: workerNames.slice(0, PEOPLE_SHOWN),
    workerNamesMore: Math.max(0, workerNames.length - PEOPLE_SHOWN),
  }
}

export interface SummaryCardPlacement {
  x: number
  y: number
  flipX: boolean
  flipY: boolean
  width: number
  height: number
}

interface RectOrigin { left: number; top: number }
interface Size { width: number; height: number }

/** Place the card from the disc's centre, flipping toward available room and
 * then clamping every edge to the viewport. Coordinates are relative to the
 * disc's containing zone, which is the card's positioned ancestor. */
export function summaryCardPlacement(zone: RectOrigin, viewport: Size, card: Size, disc: number, gutter = 8): SummaryCardPlacement {
  const width = Math.max(0, Math.min(card.width, viewport.width - gutter * 2))
  const height = Math.max(0, Math.min(card.height, viewport.height - gutter * 2))
  const anchorX = zone.left + disc / 2
  const anchorY = zone.top + disc / 2
  const flipX = anchorX + width > viewport.width - gutter
  const flipY = anchorY + height > viewport.height - gutter
  const desiredX = flipX ? anchorX - width : anchorX
  const desiredY = flipY ? anchorY - height : anchorY
  const left = Math.min(Math.max(desiredX, gutter), Math.max(gutter, viewport.width - gutter - width))
  const top = Math.min(Math.max(desiredY, gutter), Math.max(gutter, viewport.height - gutter - height))
  return { x: left - zone.left, y: top - zone.top, flipX, flipY, width, height }
}
