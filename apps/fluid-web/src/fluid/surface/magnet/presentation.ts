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

/** Whether a source says it names only some of its participants. */
export const participantsBeyond = (summaries: readonly unknown[]): boolean =>
  summaries.some((s) => record(s)?.participants_more === true)

/** A post's Markdown as plain words, for a line a person glances at: a link's
 *  label and not its address, no marks, a local file by its name. A server's
 *  preview is cut at a length, so a link or a mark may stop halfway. */
export function plainWords(text: string): string {
  return text.replace(/\r\n?/g, '\n')
    /* a block a post carries says nothing here, cut short or not; a code block's words do */
    .replace(/^ {0,3}(`{3,}|~{3,})[^\n]*\bversion=\d[^\n]*\n[\s\S]*?(?:^ {0,3}\1[`~]*[ \t]*$|(?![\s\S]))/gm, ' ')
    .replace(/^ {0,3}(?:`{3,}|~{3,})[^\n]*$/gm, ' ')
    .replace(/!?\[([^\]\n]*)\]\([^)\n]*(?:\)|$)/gm, '$1')
    .replace(/!?\[([^\]\n]*)\]\[[^\]\n]*(?:\]|$)/gm, '$1')
    .replace(/!?\[([^\]\n]*)$/gm, '$1')
    .replace(/<((?:https?|file):[^>\s]*)>/g, '$1')
    .replace(/\bfile:\/\/\/?[^\s)]*/g, (u) => u.replace(/[/\\]+$/, '').split(/[/\\]/).pop() ?? '')
    .replace(/^ {0,3}(?:[-*_][ \t]*){3,}$/gm, ' ')
    .replace(/^ {0,3}(?:#{1,6}[ \t]+|>[ \t]?|[-*+][ \t]+|\d+[.)][ \t]+)+/gm, '')
    .replace(/`+/g, '')
    .replace(/(\*\*|__|~~)(?=\S)([\s\S]*?\S)\1/g, '$2')
    .replace(/(^|[\s(])[*_](?=\S)([^*_\n]*?\S)[*_](?=$|[\s).,;:!?])/gm, '$1$2')
    .replace(/(?:\*\*|~~)/g, '')
    .replace(/^\||\|$/gm, '').replace(/\s\|\s/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

/** Who has posted among what is already held, by name, most recent first:
 *  never read for, and no more than who these posts say. For a source that names
 *  nobody. `posts` looks a post up where the client holds it. */
export function authorsHeld(results: readonly { kind: string; id: string }[], posts: (id: string) => { author?: string; author_name?: string } | undefined): { names: string[]; keys: string[]; more: number } {
  const seen = new Map<string, string>()
  for (const r of results) {
    if (r.kind !== 'post') continue
    const p = posts(r.id)
    const name = p?.author_name?.trim()
    if (name) seen.set(p?.author ?? name, seen.get(p?.author ?? name) ?? name)
  }
  const all = [...seen.entries()]
  return { names: all.slice(0, PEOPLE_SHOWN).map(([, name]) => name), keys: all.slice(0, PEOPLE_SHOWN).map(([key]) => key), more: Math.max(0, all.length - PEOPLE_SHOWN) }
}

export interface LatestFinding { id: string; at: number | null; author: string | null; preview: string | null }

/** The newest source's `latest`, or null when none says one. A summary gives
 *  its author as an id: named only where that source's participants name it,
 *  and never drawn as a bare id. A deleted post or one of no words has no preview. */
export function summaryLatest(summaries: readonly unknown[]): LatestFinding | null {
  let best: LatestFinding | null = null
  for (const value of summaries) {
    const s = record(value)
    const l = record(s?.latest)
    if (!s || !l || typeof l.id !== 'string' || !l.id) continue
    const at = typeof l.at === 'number' && Number.isFinite(l.at) ? l.at : null
    if (best && (best.at ?? -Infinity) >= (at ?? -Infinity)) continue
    const people = Array.isArray(s.participants) ? s.participants : []
    const named = people.map(record).find((p) => p?.id === l.author)
    const preview = typeof l.preview === 'string' ? plainWords(l.preview) || null : null
    best = { id: l.id, at, author: named ? personName(named) : null, preview }
  }
  return best
}

/** How far from the disc's centre its preview stands: clear of the orbit. */
export const PREVIEW_REACH = 48

export type PreviewSide = 'right' | 'left' | 'below' | 'above'
export interface PreviewPosition { x: number; y: number; side: PreviewSide }

export const samePreviewPosition = (a: PreviewPosition, b: PreviewPosition): boolean =>
  a.x === b.x && a.y === b.y && a.side === b.side

/** Place a preview around the disc, covering none of it where any side has
 *  room: beside it first, then below or above, then wherever it can be held
 *  inside `room`: the part of the viewport nothing else is drawn over (the
 *  app's bar stands above the main area, so a preview under it could not be
 *  seen). All in viewport coordinates; the answer is relative to the zone,
 *  its positioned ancestor. */
export function previewPlacement(zone: RectOrigin, disc: RectOrigin & Size, room: Size & Partial<RectOrigin>, card: Size, gutter = 8): PreviewPosition {
  const minX = (room.left ?? 0) + gutter, minY = (room.top ?? 0) + gutter
  const maxX = (room.left ?? 0) + room.width - gutter, maxY = (room.top ?? 0) + room.height - gutter
  const width = Math.min(card.width, maxX - minX)
  const height = Math.min(card.height, maxY - minY)
  const cx = disc.left + disc.width / 2
  const cy = disc.top + disc.height / 2
  const fitsX = (x: number) => x >= minX && x + width <= maxX
  const fitsY = (y: number) => y >= minY && y + height <= maxY
  const beside = { right: cx + PREVIEW_REACH, left: cx - PREVIEW_REACH - width }
  const atY = { below: cy + PREVIEW_REACH, above: cy - PREVIEW_REACH - height }
  const side: PreviewSide = fitsX(beside.right) ? 'right' : fitsX(beside.left) ? 'left' : fitsY(atY.below) ? 'below' : fitsY(atY.above) ? 'above' : 'right'
  const wantX = side === 'right' || side === 'left' ? beside[side] : cx - width / 2
  const wantY = side === 'below' || side === 'above' ? atY[side] : cy - height / 2
  const left = Math.min(Math.max(wantX, minX), Math.max(minX, maxX - width))
  const top = Math.min(Math.max(wantY, minY), Math.max(minY, maxY - height))
  return { x: left - zone.left, y: top - zone.top, side }
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
