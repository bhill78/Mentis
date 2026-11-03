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
  participantKeys: string[]
  participantNamesMore: number
  workerNames: string[]
  workerKeys: string[]
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

interface PersonIdentity { key: string; name: string | null; nameKey: string | null; order: number }
const personNameKey = (name: string): string => name.replace(/^@/, '').toLowerCase()

const personIdentity = (v: unknown, order: number): PersonIdentity | null => {
  const name = personName(v)
  const p = record(v)
  const stable = p && ['id', 'ref', 'participant_id'].map((key) => p[key]).find((id) => typeof id === 'string' && id.trim())
  if (typeof stable === 'string') return { key: `id:${stable.trim()}`, name, nameKey: name ? personNameKey(name) : null, order }
  if (!name) return null
  const nameKey = personNameKey(name)
  return { key: `name:${nameKey}`, name, nameKey, order }
}

const addPeople = (values: unknown[], people: PersonIdentity[], order: { next: number }): boolean => {
  let usable = false
  for (const value of values) {
    const person = personIdentity(value, order.next++)
    if (person) { people.push(person); usable = true }
  }
  return values.length === 0 || usable
}

/** Prefer a stable id. A bare name merges into it only when exactly one id
 * uses that display name; two ids named alike remain two people, and leave a
 * bare same-name entry separate because its owner is ambiguous. */
const distinctPeople = (values: PersonIdentity[]): PersonIdentity[] => {
  const ids = new Map<string, PersonIdentity>()
  const names = new Map<string, PersonIdentity>()
  for (const person of values) {
    const into = person.key.startsWith('id:') ? ids : names
    const prior = into.get(person.key)
    if (!prior) into.set(person.key, { ...person })
    else {
      prior.order = Math.min(prior.order, person.order)
      if (!prior.name && person.name) { prior.name = person.name; prior.nameKey = person.nameKey }
    }
  }
  const idsByName = new Map<string, PersonIdentity[]>()
  for (const person of ids.values()) if (person.nameKey) {
    const same = idsByName.get(person.nameKey) ?? []
    same.push(person)
    idsByName.set(person.nameKey, same)
  }
  const kept = [...ids.values()]
  for (const person of names.values()) {
    const matching = person.nameKey ? idsByName.get(person.nameKey) ?? [] : []
    if (matching.length === 1) matching[0].order = Math.min(matching[0].order, person.order)
    else kept.push(person)
  }
  return kept.sort((a, b) => a.order - b.order || a.key.localeCompare(b.key))
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
  const participants: PersonIdentity[] = []
  const workers: PersonIdentity[] = []
  const participantOrder = { next: 0 }
  const workerOrder = { next: 0 }
  for (const value of summaries) {
    const s = record(value)
    if (!s) continue
    const at = count(s.activity)
    if (at != null) activity = Math.max(activity ?? 0, at)
    const ps = s.participants
    if (Array.isArray(ps)) {
      if (addPeople(ps, participants, participantOrder)) sawParticipants = true
    } else {
      const n = count(ps)
      if (n != null) { sawParticipants = true; participantTotal = Math.max(participantTotal ?? 0, n) }
    }
    const ws = s.workers ?? s.working
    if (Array.isArray(ws)) {
      if (addPeople(ws, workers, workerOrder)) sawWorkers = true
    } else {
      const n = count(ws)
      if (n != null) { sawWorkers = true; workerTotal = Math.max(workerTotal ?? 0, n) }
    }
  }
  const distinctParticipants = distinctPeople(participants)
  const distinctWorkers = distinctPeople(workers)
  const participantPeople = distinctParticipants.filter((person): person is PersonIdentity & { name: string } => person.name != null)
  const workerPeople = distinctWorkers.filter((person): person is PersonIdentity & { name: string } => person.name != null)
  const participantCount = sawParticipants ? Math.max(participantTotal ?? 0, distinctParticipants.length) : null
  const workerCount = sawWorkers ? Math.max(workerTotal ?? 0, distinctWorkers.length) : null
  return {
    activity,
    participants: participantCount,
    working: workerCount,
    participantNames: participantPeople.slice(0, PEOPLE_SHOWN).map((person) => person.name),
    participantKeys: participantPeople.slice(0, PEOPLE_SHOWN).map((person) => person.key),
    participantNamesMore: Math.max(0, participantPeople.length - PEOPLE_SHOWN),
    workerNames: workerPeople.slice(0, PEOPLE_SHOWN).map((person) => person.name),
    workerKeys: workerPeople.slice(0, PEOPLE_SHOWN).map((person) => person.key),
    workerNamesMore: Math.max(0, workerPeople.length - PEOPLE_SHOWN),
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

export type SummaryCardPosition = Pick<SummaryCardPlacement, 'x' | 'y' | 'flipX' | 'flipY'>

export const sameSummaryCardPosition = (a: SummaryCardPosition, b: SummaryCardPosition): boolean =>
  a.x === b.x && a.y === b.y && a.flipX === b.flipX && a.flipY === b.flipY

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
