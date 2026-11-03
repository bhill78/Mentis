/* SURFACE COMPOSITION: THE CONTRACT, PROVED BY THE COMPILER (owner Turn #1512;
 * plan ent-2d8422d49d7c, package 1). Checked by `npm run typecheck:tests`
 * (tsconfig.test.json); nothing here runs.
 *
 *   * a body-bearing SurfaceChrome at full, minimal and hidden;
 *   * a rich ReactNode title beside a plain label;
 *   * header and footer regions carrying content and registry action ids;
 *   * the Page bar as the one bar-only surface (SurfaceBar);
 *   * a SurfaceChrome without a body does not compile;
 *   * SurfaceBar cannot take a body, a header or a footer;
 *   * a region action must be a registry id;
 *   * P4's header-only chrome is gone (package 5): neither
 *     LegacySurfaceChromeBar, its props, nor the header-only FloatingHeader
 *     exists to be called. */
import { createElement, type ReactNode } from 'react'
import type { ActionTarget } from '../src/fluid/surface/actions/types'
import type { SurfaceBarProps, SurfaceChromeProps, SurfaceRegion } from '../src/fluid/surface/types'
import { SurfaceBar, SurfaceChrome } from '../src/fluid/surface/SurfaceChrome'
import * as chromeModule from '../src/fluid/surface/SurfaceChrome'
import type * as surfaceTypes from '../src/fluid/surface/types'
import * as floatingModule from '../src/fluid/focus/FloatingHeader'

declare const target: ActionTarget
declare const rich: ReactNode
const grip = { onPointerDown() {} }

/* -- valid -------------------------------------------------------------------- */
const full: SurfaceChromeProps = { target, placement: 'float', level: 'standard', label: 'Notes', title: rich, body: rich, grip }
const minimal: SurfaceChromeProps = {
  target, placement: 'dock', level: 'standard', label: 'Activity', title: 'Activity', body: rich, visibility: 'minimal',
  header: { content: rich, actions: ['run.stop'] },
}
const hidden: SurfaceChromeProps = {
  target, placement: 'launcher', level: 'icon', label: 'Conversations', title: null, body: rich, bodyIsControl: true, visibility: 'hidden',
}
const form: SurfaceChromeProps = {
  target, placement: 'float', level: 'standard', label: 'Form', title: rich, body: rich,
  footer: { content: rich, actions: ['form.validate', 'form.markReady'] },
}
const bar: SurfaceBarProps = { variant: 'page-bar', target, level: 'standard', label: 'Home', title: rich, extra: rich }
const region: SurfaceRegion = {}
void [full, minimal, hidden, form, bar, region]

/* the components take exactly these */
void createElement(SurfaceChrome, full)
void createElement(SurfaceBar, bar)

/* -- invalid ------------------------------------------------------------------ */
// @ts-expect-error a SurfaceChrome has a body: a surface is its body
const noBody: SurfaceChromeProps = { target, placement: 'float', level: 'standard', label: 'Notes', title: rich }
// @ts-expect-error a SurfaceChrome has a plain label beside its rich title
const noLabel: SurfaceChromeProps = { target, placement: 'float', level: 'standard', title: rich, body: rich }
// @ts-expect-error the Page bar is the bar-only exception: it has no body
const barBody: SurfaceBarProps = { variant: 'page-bar', target, level: 'standard', label: 'Home', title: rich, body: rich }
// @ts-expect-error the Page bar has no header region
const barHeader: SurfaceBarProps = { variant: 'page-bar', target, level: 'standard', label: 'Home', title: rich, header: { content: rich } }
// @ts-expect-error the Page bar has no footer region
const barFooter: SurfaceBarProps = { variant: 'page-bar', target, level: 'standard', label: 'Home', title: rich, footer: { content: rich } }
// @ts-expect-error SurfaceBar is only the Page bar
const otherBar: SurfaceBarProps = { variant: 'window', target, level: 'standard', label: 'Notes', title: rich }
// @ts-expect-error the page bar is SurfaceBar's, not a SurfaceChrome placement
const pageBarFrame: SurfaceChromeProps = { target, placement: 'page-bar', level: 'standard', label: 'Home', title: rich, body: rich }
// @ts-expect-error a region action is a registry id, not a callback or a made-up word
const callback: SurfaceRegion = { actions: [() => {}] }
// @ts-expect-error a region action is a registry id
const unknownId: SurfaceRegion = { actions: ['save'] }
// @ts-expect-error a visibility is full, minimal or hidden
const loud: SurfaceChromeProps = { ...full, visibility: 'loud' }
void [noBody, noLabel, barBody, barHeader, barFooter, otherBar, pageBarFrame, callback, unknownId, loud]

/* -- removed in package 5 ------------------------------------------------------ */
// @ts-expect-error the header-only legacy adapter is removed: every surface is a frame or the Page bar
void chromeModule.LegacySurfaceChromeBar
// @ts-expect-error its props went with it
type LegacyProps = surfaceTypes.LegacySurfaceChromeBarProps
// @ts-expect-error the header-only window head is removed: FloatingFrame is the floating surface's frame
void floatingModule.FloatingHeader
void [chromeModule.SurfaceChrome, floatingModule.FloatingFrame, null as unknown as LegacyProps]
