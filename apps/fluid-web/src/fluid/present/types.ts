/* THE A/C CONTRACT (completion pack section 6): what a zone body is given.
 *
 * Stream A stores a slot's `present` and `appearance` and hands them, with
 * the zone's pixel size, to `Present`. Stream C draws. Neither changes these
 * shapes without the other. */

/** One object a zone shows (integration of streams A and C: A's shape).
 *  `address` is the address the store keys it under (`live:<post>:<key>` or
 *  an exact address); the rest says where it is shown, so it can be taken
 *  out of a zone or dragged to another. */
export interface ObjectRef {
  address: string
  /** kept in this zone (not merely followed): it can be taken out */
  kept?: boolean
  /** the zone and page it is shown in, for dragging it elsewhere */
  zone?: string
  page?: string
}

/** How a zone shows what it holds (#448, #442 area 2). */
export type PresentMode = 'cards' | 'gallery' | 'slides' | 'list' | 'focus' | 'previews' | 'across'

export const PRESENT_MODES: { mode: PresentMode; label: string; says: string }[] = [
  { mode: 'cards', label: 'Cards', says: 'each object in its own card, sized to the zone' },
  { mode: 'gallery', label: 'Gallery', says: 'a grid of plates, pictures first' },
  { mode: 'slides', label: 'Slides', says: 'one at a time, filling the zone' },
  { mode: 'list', label: 'List', says: 'one line each, quickest to scan' },
  { mode: 'focus', label: 'Focused item', says: 'one large, the rest beside it' },
  { mode: 'previews', label: 'Previews', says: 'several previews at once, each as tall as it needs, down the zone' },
  /* B7: the same previews in one row, scrolled sideways. Added; nothing stored changes. */
  { mode: 'across', label: 'Side by side', says: 'previews in one row across the zone, each as tall as the zone, scrolled sideways' },
]

export const isPresentMode = (m: unknown): m is PresentMode => PRESENT_MODES.some((p) => p.mode === m)

/** A background: none, a wash of the theme, or the theme's surface. */
export type Fill = 'transparent' | 'tinted' | 'solid'

/** A zone's look (#187 #7, #188 Appearance): the panel and the content set
 *  separately; `opacity` (0..1) is how strongly a tinted or solid fill
 *  covers the atmosphere. */
export interface Appearance { panel: Fill; content: Fill; opacity: number }

/** BORDERLESS AND TRANSPARENT BY DEFAULT (FW #1; #568 4.5: "zones need to
 *  respect the user's chosen background ... rather than introducing
 *  competing surface styles"). Nothing painted: the atmosphere throughout,
 *  its own veil keeping the words readable, the zone told apart by its
 *  gutters. A wash, a tint or a solid panel is chosen per zone or place. */
export const DEFAULT_APPEARANCE: Appearance = { panel: 'transparent', content: 'transparent', opacity: 0.6 }

/** F6's glass panels with washed cards, kept as an option (#448: the F6
 *  visual improvements remain). */
export const F6_APPEARANCE: Appearance = { panel: 'tinted', content: 'tinted', opacity: 1 }

export const APPEARANCE_PRESETS: { id: string; label: string; says: string; a: Appearance }[] = [
  { id: 'clear', label: 'Clear', says: 'nothing painted: the atmosphere throughout', a: DEFAULT_APPEARANCE },
  { id: 'quiet', label: 'Quiet', says: 'no panel, a light wash under the content', a: { panel: 'transparent', content: 'tinted', opacity: 0.6 } },
  { id: 'glass', label: 'Glass', says: "F6's look: a glass panel with washed cards", a: F6_APPEARANCE },
  { id: 'solid', label: 'Solid', says: 'an opaque panel and cards, nothing behind', a: { panel: 'solid', content: 'solid', opacity: 1 } },
]

const FILLS: Fill[] = ['transparent', 'tinted', 'solid']
const clamp01 = (n: number) => (Number.isFinite(n) ? Math.min(1, Math.max(0, n)) : DEFAULT_APPEARANCE.opacity)

/** Whatever was stored, read back as an Appearance (a bad field falls back). */
export function readAppearance(v: unknown, fallback: Appearance = DEFAULT_APPEARANCE): Appearance {
  const o = (v && typeof v === 'object' ? v : {}) as Partial<Appearance>
  return {
    panel: FILLS.includes(o.panel as Fill) ? (o.panel as Fill) : fallback.panel,
    content: FILLS.includes(o.content as Fill) ? (o.content as Fill) : fallback.content,
    opacity: typeof o.opacity === 'number' ? clamp01(o.opacity) : fallback.opacity,
  }
}

export interface PresentProps {
  items: ObjectRef[]
  mode: PresentMode
  /** the zone body's size in CSS pixels, as the zone measured it */
  width: number
  height: number
  /** open an object's detail out of the element it was opened from */
  onOpen: (item: ObjectRef, from?: HTMLElement | null) => void
  /** keep it somewhere the reader chooses, offered from `from` */
  onKeep: (item: ObjectRef, from?: HTMLElement | null) => void
  /** take a kept object out of this zone */
  onRemove?: (item: ObjectRef) => void
  /** the zone's look; the zone wrapper applies it (zoneAppearanceStyle) */
  appearance?: Appearance
}
