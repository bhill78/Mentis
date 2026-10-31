/* THE MAGNET'S ICONS (owner Turn #1592: "magnets need much better icons").
 *
 * One small line-drawn set, in currentColor, for what a Magnet reads (its
 * source badge), what it holds (the summary's and the orbit's categories) and
 * how it is (its status badge). Drawn at 16 px on a 16 px grid; the stroke
 * scales with the size it is drawn at. Decorative: whatever an icon says is
 * also said in words (aria-label, title) where it is used. */

import type { InformationType, MagnetState, SourceGlyph } from './model'

const PATHS: Record<SourceGlyph | InformationType | 'paused' | 'error' | 'limited' | 'magnet', string> = {
  /* sources */
  conversation: 'M2.5 3.5h11v7h-6l-3 2.5v-2.5h-2z',
  brain: 'M8 3.2a2.4 2.4 0 0 0-4.3 1.4 2.4 2.4 0 0 0-1 4.3 2.4 2.4 0 0 0 3 3.3A2.2 2.2 0 0 0 8 12.8M8 3.2a2.4 2.4 0 0 1 4.3 1.4 2.4 2.4 0 0 1 1 4.3 2.4 2.4 0 0 1-3 3.3A2.2 2.2 0 0 1 8 12.8M8 3.2v9.6',
  connector: 'M5.5 2v3.5M10.5 2v3.5M3.5 5.5h9v2.5a4.5 4.5 0 0 1-9 0zM8 12.5V15',
  web: 'M8 2a6 6 0 1 0 0 12A6 6 0 0 0 8 2zM2 8h12M8 2c-2 2-2 10 0 12M8 2c2 2 2 10 0 12',
  other: 'M3 3h10v10H3zM6 8h4',
  mixed: 'M2.5 5.5h7v7h-7zM6.5 3.5h7v7',
  /* what it holds */
  post: 'M2.5 3.5h11v7h-6l-3 2.5v-2.5h-2zM5 6h6M5 8h4',
  file: 'M4 2h5l3.5 3.5V14H4zM9 2v3.5h3.5',
  image: 'M2.5 3.5h11v9h-11zM2.5 10.5l3.5-3.5 3 3 2-2 2.5 2.5M10.5 6.2a.8.8 0 1 0 0-.01',
  attachment: 'M11 5.5 6.2 10.3a1.6 1.6 0 0 1-2.3-2.3l5.2-5.2a2.7 2.7 0 0 1 3.8 3.8l-5.4 5.4a3.8 3.8 0 0 1-5.4-5.4L6.5 2.2',
  link: 'M6.8 9.2a2.8 2.8 0 0 0 4 0l2-2a2.8 2.8 0 0 0-4-4l-.9.9M9.2 6.8a2.8 2.8 0 0 0-4 0l-2 2a2.8 2.8 0 0 0 4 4l.9-.9',
  form: 'M3 2.5h10v11H3zM5.5 6l1 1 2-2M5.5 10.5l1 1 2-2M10 6h1M10 10.5h1',
  /* how it is */
  paused: 'M5.5 4v8M10.5 4v8',
  error: 'M8 3.5v5.5M8 11.5v1',
  limited: 'M8 2.5 14 13H2zM8 6.5v3M8 11v.5',
  magnet: 'M4 2.5v6a4 4 0 0 0 8 0v-6M4 5.5h2.5M9.5 5.5H12M6.5 2.5v6a1.5 1.5 0 0 0 3 0v-6',
}

export type IconName = keyof typeof PATHS

export function Icon({ name, size = 16, className }: { name: IconName; size?: number; className?: string }) {
  return <svg className={'mg-icon' + (className ? ' ' + className : '')} width={size} height={size} viewBox="0 0 16 16" aria-hidden="true" focusable="false"
    fill="none" stroke="currentColor" strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round"><path d={PATHS[name]} /></svg>
}

/** The status badge's icon, where its state has one. */
export const stateIcon = (s: MagnetState, limited: boolean): IconName | null =>
  s === 'error' || s === 'missing' ? 'error' : s === 'paused' ? 'paused' : limited ? 'limited' : null
