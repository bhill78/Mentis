/* WHICH TARGET THE PALETTE AND Ctrl/⌘+K SPEAK FOR (rev 3 §5.3; part P3).
 *
 * The palette searches exactly the registry's list for one target: the
 * selection, else the surface last pointed at or focused, else the
 * workspace. Hosts say which surface that is with `pointAt` (a section's
 * menu does as it is built); the shell gives the workspace's target as the
 * fallback. Browser-free. */

import type { ActionCtx, ActionTarget } from './types'

export interface Aimed { target: ActionTarget; ctx: ActionCtx; name: string }

let pointed: Aimed | null = null
let fallback: (() => Aimed | null) | null = null
let open: Aimed | null = null
const listeners = new Set<() => void>()
const emit = () => { for (const fn of [...listeners]) fn() }

/** The surface the person last pointed at or focused. */
export function pointAt(a: Aimed | null) { pointed = a }
/** What the palette speaks for when nothing is pointed at (the workspace). */
export function aimFallback(f: (() => Aimed | null) | null) { fallback = f }
/** What Ctrl/⌘+K would act on now. */
export const aimed = (): Aimed | null => pointed ?? fallback?.() ?? null

/** Open the palette for `a` (Find an action…, or Ctrl/⌘+K). */
export function openPalette(a: Aimed | null = aimed()) { open = a; emit() }
export function closePalette() { if (open) { open = null; emit() } }
export const paletteOpen = (): Aimed | null => open
export function subscribePalette(fn: () => void) { listeners.add(fn); return () => { listeners.delete(fn) } }
