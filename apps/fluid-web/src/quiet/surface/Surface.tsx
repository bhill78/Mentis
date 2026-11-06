/* PACKAGE G owns this module: the painted ground every other package sits
   on. It mounts the `.qc` element the rest of the shell is laid out by --
   that element and the class it carries do not change -- and paints it by
   calling production's own `useLook` (fluid/frame/look.ts), the same hook
   Fluid's Shell draws its frame with. An atmosphere is defined once, in
   atmosphere.css's `:root[data-atmosphere=...]` token blocks, which already
   reach `/quiet`; nothing here edits that file, and nothing here duplicates
   what it declares.

   `useLook` also publishes the shared `LookControls` store BackgroundControl
   reads (`useLookControls`), the same split Shell.tsx and LookSheet.tsx use:
   one component calls the hook that paints the frame, another reads the
   store it leaves behind. Surface mounts outside QuietChat's own state and
   is handed no conversation prop -- the seam's `SurfaceView` contract is
   `{ children }` only -- so it keeps its own small copy of the address,
   the way QuietChat.tsx keeps its own. */
import { useEffect, useRef, useState, useSyncExternalStore, type CSSProperties, type ReactNode } from 'react'
import { readAddress } from '../../address'
import { useLook } from '../../fluid/frame/look'
import './surface.css'

export type SurfaceTreatment = 'solid' | 'glass'

const TREATMENT_KEY = 'mentis:quiet-surface'

function readTreatment(): SurfaceTreatment {
  try {
    const v = localStorage.getItem(TREATMENT_KEY)
    if (v === 'solid' || v === 'glass') return v
  } catch { /* storage unavailable: solid is what Quiet always drew */ }
  return 'solid'
}

/* -- the surface treatment, one value for the page, read by BackgroundControl */
let treatment: SurfaceTreatment = readTreatment()
const heard = new Set<() => void>()
const tell = () => heard.forEach((fn) => fn())
const sub = (fn: () => void) => { heard.add(fn); return () => { heard.delete(fn) } }

/** Choose solid or glass for the ground every atmosphere paints under `.qc`,
 *  and persist it the way the theme is persisted: this browser, every page. */
export function setSurfaceTreatment(t: SurfaceTreatment) {
  treatment = t
  try { localStorage.setItem(TREATMENT_KEY, t) } catch { /* this page only */ }
  tell()
}
export const useSurfaceTreatment = () => useSyncExternalStore(sub, () => treatment)
/** The same value, read without a React tree -- for anything that is not a
 *  component, including `tests/quiet_surface_unit.mjs`. */
export const getSurfaceTreatment = () => treatment

const APPEARANCE_KEY = 'mentis:quiet-appearance'
type Appearance = {
  solidOpacity: number; glassOpacity: number; blur: number
  pinHeader: boolean; pinMargins: boolean
}
const defaults: Appearance = {
  solidOpacity: 86, glassOpacity: 76, blur: 18, pinHeader: false, pinMargins: false,
}
const bounded = (value: unknown, fallback: number, max: number) =>
  typeof value === 'number' && Number.isFinite(value) ? Math.max(0, Math.min(max, value)) : fallback
function readAppearance(): Appearance {
  try {
    const saved = JSON.parse(localStorage.getItem(APPEARANCE_KEY) ?? '{}') ?? {}
    return {
      solidOpacity: bounded(saved.solidOpacity, defaults.solidOpacity, 100),
      glassOpacity: bounded(saved.glassOpacity, defaults.glassOpacity, 100),
      blur: bounded(saved.blur, defaults.blur, 32),
      pinHeader: saved.pinHeader === true, pinMargins: saved.pinMargins === true,
    }
  } catch { return { ...defaults } }
}
let appearance = readAppearance()
export function setSurfaceAppearance(change: Partial<Appearance>) {
  appearance = {
    solidOpacity: bounded(change.solidOpacity, appearance.solidOpacity, 100),
    glassOpacity: bounded(change.glassOpacity, appearance.glassOpacity, 100),
    blur: bounded(change.blur, appearance.blur, 32),
    pinHeader: change.pinHeader ?? appearance.pinHeader,
    pinMargins: change.pinMargins ?? appearance.pinMargins,
  }
  try { localStorage.setItem(APPEARANCE_KEY, JSON.stringify(appearance)) } catch { /* this page only */ }
  tell()
}
export const getSurfaceAppearance = () => appearance
export const useSurfaceAppearance = () => useSyncExternalStore(sub, getSurfaceAppearance)

/** Which conversation the atmosphere resolves for, kept the same way
 *  QuietChat.tsx keeps it -- Surface has no prop for it. */
function useConversation() {
  const [conversation, setConversation] = useState(() => readAddress().conversation)
  useEffect(() => {
    const changed = () => setConversation(readAddress().conversation)
    window.addEventListener('hashchange', changed)
    return () => window.removeEventListener('hashchange', changed)
  }, [])
  return conversation
}

export default function Surface({ children }: { children: ReactNode }) {
  const conversation = useConversation()
  useLook(conversation, null)
  const surface = useSurfaceTreatment()
  const look = useSurfaceAppearance()
  const root = useRef<HTMLDivElement>(null)
  // Pinned margins clear the compact header's actual height, including wrapping
  // and browser zoom. Drawers are outside that row and continue to scroll.
  useEffect(() => {
    const header = root.current?.querySelector<HTMLElement>('.qc-global')
    if (!header) return
    const measure = () => root.current?.style.setProperty('--qc-header-height', `${header.getBoundingClientRect().height}px`)
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(header)
    return () => observer.disconnect()
  }, [])
  /* The dock sticks to the viewport's bottom edge with nothing pinning its
     top, so at any scroll position it rises as high as the heading above
     it has scrolled -- never higher. Its cap (layout.css, composer.css)
     must not exceed that room, or a tall composer (settings open, a draft
     at its growth cap) renders past the fold with nothing to scroll it
     into view. `.qc-heading`'s own bottom edge, read live, already carries
     the scroll position and any header pinning; re-measured on scroll and
     resize, and whenever the heading is replaced (a new conversation) or
     resized (its content changing, e.g. a wrapped topic name). */
  useEffect(() => {
    const el = root.current
    if (!el) return
    let observer: ResizeObserver | null = null
    let observed: Element | null = null
    const measure = () => {
      const heading = el.querySelector<HTMLElement>('.qc-heading')
      if (!heading) { el.style.removeProperty('--qc-dock-room'); return }
      if (heading !== observed) {
        observer?.disconnect()
        observer = new ResizeObserver(measure)
        observer.observe(heading)
        observed = heading
      }
      const room = window.innerHeight - heading.getBoundingClientRect().bottom - 24
      el.style.setProperty('--qc-dock-room', `${Math.max(0, room)}px`)
    }
    measure()
    const mutations = new MutationObserver(measure)
    mutations.observe(el, { childList: true, subtree: true })
    window.addEventListener('scroll', measure, { passive: true })
    window.addEventListener('resize', measure)
    return () => {
      observer?.disconnect()
      mutations.disconnect()
      window.removeEventListener('scroll', measure)
      window.removeEventListener('resize', measure)
    }
  }, [])
  const style = {
    '--qc-surface-opacity': (surface === 'solid' ? look.solidOpacity : look.glassOpacity) / 100,
    '--qc-glass-blur': `${look.blur}px`,
  } as CSSProperties
  return <div ref={root} className="qc" data-surface={surface} data-pin-header={look.pinHeader}
    data-pin-margins={look.pinMargins} style={style}>{children}</div>
}
