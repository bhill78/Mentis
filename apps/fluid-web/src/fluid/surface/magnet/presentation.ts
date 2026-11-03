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
  names: string[]
}

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

/** Signals only from source summaries already in hand. This never starts a
 * read. Counts are summed across sources; named people are de-duplicated. */
export function summaryPresence(summaries: readonly unknown[]): SummaryPresence {
  let activity: number | null = null
  let participants: number | null = null
  let working: number | null = null
  const names = new Set<string>()
  for (const value of summaries) {
    const s = record(value)
    if (!s) continue
    const at = count(s.activity)
    if (at != null) activity = Math.max(activity ?? 0, at)
    const ps = s.participants
    if (Array.isArray(ps)) {
      participants = (participants ?? 0) + ps.length
      for (const p of ps) { const name = personName(p); if (name) names.add(name) }
    } else {
      const n = count(ps)
      if (n != null) participants = (participants ?? 0) + n
    }
    const ws = s.workers ?? s.working
    if (Array.isArray(ws)) {
      working = (working ?? 0) + ws.length
      for (const p of ws) { const name = personName(p); if (name) names.add(name) }
    } else {
      const n = count(ws)
      if (n != null) working = (working ?? 0) + n
    }
  }
  return { activity, participants, working, names: [...names].slice(0, 4) }
}
