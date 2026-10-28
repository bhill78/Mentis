/* FOCUS: THE TEMPORARY ATTENTION STATE (owner's final consolidation brief §2-4).
 *
 * SHARED INTERFACE -- the Focus workstream implements it; everyone else only
 * calls it. A per-Page LENS computed from the arrangement and never written to
 * it (the fluid-focus "B model with A's controls"):
 *
 *   - entering Focus gives the target the Page's largest useful working area,
 *     the FOCUS AREA, in the remembered presentation;
 *   - while Focus is on, focusing something else REPLACES the content of the
 *     same Focus area: its geometry and the presentation stay put;
 *   - Esc steps back through this Page's Focus history; Restore returns
 *     straight to the original arrangement; "Keep this layout" turns the
 *     composition into one ordinary arrangement edit (still unsaved);
 *   - nothing here is saved with the place.
 *
 * Presentations: Docked, Floating, Mixed, Only Focus. The last one chosen is
 * remembered per browser (`mentis.fluid.focus-presentation`). */

export type FocusPresentation = 'docked' | 'floating' | 'mixed' | 'only'

export const PRESENTATIONS: { id: FocusPresentation; icon: string; label: string; says: string }[] = [
  { id: 'docked', icon: '▥', label: 'Docked', says: 'Focus in the main area; docked sections stay organised around it' },
  { id: 'floating', icon: '⧉', label: 'Floating', says: 'Focus in the main area; floating windows stay movable around it' },
  { id: 'mixed', icon: '◫', label: 'Mixed', says: 'Docked sections and floating windows both stay, each behaving as itself' },
  { id: 'only', icon: '▣', label: 'Only Focus', says: 'Focus fills the Page; everything else is hidden until you reveal it' },
]

/** What Focus is on: a surface already on the Page, or one object. */
export type FocusTarget =
  | { kind: 'surface'; id: string; title?: string }
  | { kind: 'object'; address: string; title?: string; from?: string }

export interface LensState {
  page: string
  target: FocusTarget
  presentation: FocusPresentation
  /** earlier targets on this Page, newest last: Esc steps back through them */
  history: FocusTarget[]
}

const KEY = 'mentis.fluid.focus-presentation'
let lastPresentation: FocusPresentation = (() => {
  try { const v = localStorage.getItem(KEY); return (PRESENTATIONS.some((p) => p.id === v) ? v : 'mixed') as FocusPresentation } catch { return 'mixed' }
})()
export const rememberedPresentation = () => lastPresentation
export function rememberPresentation(p: FocusPresentation) {
  lastPresentation = p
  try { localStorage.setItem(KEY, p) } catch { /* not kept: this tab still uses it */ }
}

/* -- the implementation is provided by the Focus workstream ----------------
   Until it is merged, these are inert so callers compile and run. */
export interface LensImpl {
  enter(target: FocusTarget, presentation?: FocusPresentation): void
  setPresentation(p: FocusPresentation): void
  stepBack(): boolean
  restore(): void
  keepLayout(): void
  current(page?: string): LensState | null
  subscribe(fn: () => void): () => void
}
const inert: LensImpl = {
  enter: () => {}, setPresentation: (p) => rememberPresentation(p), stepBack: () => false,
  restore: () => {}, keepLayout: () => {}, current: () => null, subscribe: () => () => {},
}
let impl: LensImpl = inert
export function provideLens(i: LensImpl) { impl = i }
export const lens: LensImpl = {
  enter: (t, p) => impl.enter(t, p), setPresentation: (p) => impl.setPresentation(p),
  stepBack: () => impl.stepBack(), restore: () => impl.restore(), keepLayout: () => impl.keepLayout(),
  current: (page) => impl.current(page), subscribe: (fn) => impl.subscribe(fn),
}
