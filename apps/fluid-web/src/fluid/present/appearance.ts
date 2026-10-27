/* A ZONE'S LOOK, AS CSS (#187 #7, #188 Appearance; pack section 6).
 *
 * `zoneAppearanceStyle(appearance, theme)` gives the zone wrapper a class
 * and the custom properties present.css reads: the panel's fill and blur,
 * and the content's fill, hover and blur. Every fill is made from the
 * owner's atmosphere's own tokens (#568 4.3) -- its ground, its raised
 * surface, its ink -- so a zone is a veil of the look in force and the
 * picture shows through it in proportion to `opacity`. Nothing here names
 * a colour.
 *
 *   transparent  nothing painted (the default: FW #1, #568 4.5)
 *   tinted       a translucent veil of the atmosphere's ground (F6's glass is
 *                a tinted panel at full opacity)
 *   solid        the atmosphere's raised surface, as opaque as `opacity` says
 *
 * `theme` is the way the ground faces (look.ts): a veil over a light ground
 * is a little denser, as F6's was, so the same opacity reads the same. */

import type { CSSProperties } from 'react'
import type { Appearance } from './types'

const SCHEME: Record<'dark' | 'light', { glass: number; veil: number; wash: number }> = {
  dark: { glass: 0.74, veil: 0.66, wash: 0.05 },
  light: { glass: 0.86, veil: 0.78, wash: 0.04 },
}
const pct = (a: number) => `${Math.round(Math.min(1, Math.max(0, a)) * 1000) / 10}%`
/** `token` at `a` of its strength over whatever is behind it */
const mix = (token: string, a: number) => `color-mix(in srgb, var(${token}) ${pct(a)}, transparent)`
const BLUR = 'blur(var(--on-canvas-blur, 6px))'

export function zoneAppearanceStyle(appearance: Appearance, theme: 'light' | 'dark'): { className: string; style: CSSProperties } {
  const s = SCHEME[theme] ?? SCHEME.dark
  const k = Math.min(1, Math.max(0, appearance.opacity))
  const v: Record<string, string> = {}
  /* the panel */
  if (appearance.panel === 'transparent') {
    v['--zp-bg'] = 'transparent'
    v['--zp-blur'] = 'none'
    /* Words over the bare picture are lifted off it by a halo of the
       atmosphere's own ground: a dark lift on a dark ground, a pale glow on
       a light one -- never a dark shadow under dark words (adm-4a15dff165c4). */
    v['--pz-shade'] = '0 0 2px var(--canvas), 0 0 8px var(--canvas), 0 0 18px ' + mix('--canvas', 0.8)
  } else if (appearance.panel === 'tinted') {
    v['--zp-bg'] = mix('--surface', s.glass * k)
    v['--zp-blur'] = k > 0.05 ? BLUR : 'none'
  } else {
    v['--zp-bg'] = mix('--surface-raised', k)
    v['--zp-blur'] = 'none'
  }
  /* the content. On a painted panel a tint is a wash of the ink (F6's
     cards); on a bare one it is a veil of the ground, so the words are
     readable over the picture without a panel behind them. */
  if (appearance.content === 'transparent') {
    v['--zc-bg'] = 'transparent'
    v['--zc-hover'] = mix('--text', s.wash)
    v['--zc-blur'] = 'none'
  } else if (appearance.content === 'tinted') {
    if (appearance.panel === 'transparent') {
      v['--zc-bg'] = mix('--surface', s.veil * k)
      v['--zc-hover'] = mix('--surface', Math.min(1, s.veil * k + 0.12))
      v['--zc-blur'] = k > 0.05 ? BLUR : 'none'
    } else {
      v['--zc-bg'] = mix('--text', s.wash * k)
      v['--zc-hover'] = mix('--text', s.wash + 0.04)
      v['--zc-blur'] = 'none'
    }
  } else {
    v['--zc-bg'] = mix('--surface-raised', k)
    v['--zc-hover'] = 'var(--surface-raised)'
    v['--zc-blur'] = 'none'
  }
  return {
    className: `pz-appear pz-panel-${appearance.panel} pz-content-${appearance.content}`,
    style: v as CSSProperties,
  }
}
