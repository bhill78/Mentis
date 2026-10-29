/* THE OWNER'S THEME AND ATMOSPHERE, applied as production applies them.
 *
 * The theme is the one production keeps (`mentis:theme`, light / dark / the
 * system's); the atmosphere is what the brain's presentation store resolves
 * for this conversation (atmosphere.ts), and is put on the document as
 * `data-atmosphere` exactly as App.tsx puts it there. The frame draws the
 * atmosphere whole -- its tokens, ground, picture and veil (frame.css) --
 * and the theme answers only where the atmosphere leaves it to (#568 4.2).
 *
 * The bar's Look sheet (LookSheet.tsx) changes both, through the same
 * store production uses: the theme in this browser, the atmosphere for this
 * conversation or as the Brain's default. Returns the scheme drawn in. */

import { useEffect, useMemo, useState, useSyncExternalStore } from 'react'
import { ATMOSPHERES, useAtmospheres, type Atmosphere } from '../../atmosphere'
import { usePresentation, type PresentationStore } from '../../picture/store'
import type { Scope } from '../../picture/Maker'

export type Theme = 'light' | 'dark' | 'system'
export type ActivityLook = 'default' | 'console' | 'retro-green' | 'modern' | 'stylish' | 'minimalist'

export const ACTIVITY_LOOKS: { id: ActivityLook; name: string; says: string }[] = [
  { id: 'default', name: 'Default', says: 'Default: the activity panel follows the current Mentis look' },
  { id: 'console', name: 'Console', says: 'Console: a crisp dark operations display' },
  { id: 'retro-green', name: 'Retro', says: 'Retro Green Terminal: green phosphor ink on a deep terminal ground' },
  { id: 'modern', name: 'Modern', says: 'Modern: cool high-contrast surfaces and a clear blue signal' },
  { id: 'stylish', name: 'Stylish', says: 'Stylish: warm plum surfaces with a restrained gold signal' },
  { id: 'minimalist', name: 'Minimalist', says: 'Minimalist: quiet monochrome surfaces with spare separators' },
]

const ACTIVITY_LOOK_KEY = 'mentis:activity-look'

function readActivityLook(): ActivityLook {
  try {
    const value = localStorage.getItem(ACTIVITY_LOOK_KEY)
    if (ACTIVITY_LOOKS.some((look) => look.id === value)) return value as ActivityLook
  } catch { /* storage unavailable: use the default */ }
  return 'default'
}

function readTheme(): Theme {
  try {
    const t = localStorage.getItem('mentis:theme')
    if (t === 'light' || t === 'dark') return t
  } catch { /* storage unavailable: follow the system */ }
  return 'system'
}

const prefersDark = () => !window.matchMedia || window.matchMedia('(prefers-color-scheme: dark)').matches

/** Which way the atmosphere's ground faces, from the colour `--canvas`
 *  resolves to on the document now; null if it cannot be read. */
let probe: HTMLSpanElement | null = null
function groundScheme(): 'dark' | 'light' | null {
  if (!probe) {
    probe = document.createElement('span')
    probe.style.cssText = 'position:absolute;width:0;height:0;overflow:hidden;color:var(--canvas)'
    probe.setAttribute('aria-hidden', 'true')
    document.body.appendChild(probe)
  }
  const m = getComputedStyle(probe).color.match(/[\d.]+/g)
  if (!m || m.length < 3) return null
  const [r, g, b] = m.slice(0, 3).map((x) => Number(x) / 255).map((c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4))
  return 0.2126 * r + 0.7152 * g + 0.0722 * b < 0.25 ? 'dark' : 'light'
}

/* -- the theme, one value for the page, changed here or in another tab ---- */
let theme: Theme = readTheme()
let activityLook: ActivityLook = readActivityLook()
let scheme: 'dark' | 'light' = 'dark'
const heard = new Set<() => void>()
const tell = () => heard.forEach((fn) => fn())
const sub = (fn: () => void) => { heard.add(fn); return () => { heard.delete(fn) } }

/** Choose light, dark or the system's (production's `mentis:theme`). */
export function setTheme(t: Theme) {
  theme = t
  try {
    if (t === 'system') localStorage.removeItem('mentis:theme')
    else localStorage.setItem('mentis:theme', t)
  } catch { /* this page only */ }
  tell()
}
export const useTheme = () => useSyncExternalStore(sub, () => theme)
export const useActivityLook = () => useSyncExternalStore(sub, () => activityLook)

/** Choose the Activity panel's colour treatment without changing its content or layout. */
export function setActivityLook(value: ActivityLook) {
  activityLook = value
  try {
    if (value === 'default') localStorage.removeItem(ACTIVITY_LOOK_KEY)
    else localStorage.setItem(ACTIVITY_LOOK_KEY, value)
  } catch { /* this page only */ }
  tell()
}
/** The scheme the frame draws in now: what a zone's appearance is made for. */
export const useScheme = () => useSyncExternalStore(sub, () => scheme)

/* MAKING A LOOK FROM A PICTURE (#568 4.4; TH #8-#10): production's own
   panel (picture/Maker), opened from the Look sheet's "From a picture…".
   While it is open the frame is drawn in the version being tried -- the
   workspace behind the panel IS the preview, as in production. */
let making: Scope | null = null
let previewing: string | null = null
export function startMaking(s: Scope | null) { making = s; if (!s) previewing = null; tell() }
export const useMaking = () => useSyncExternalStore(sub, () => making)
export function setLookPreview(id: string | null) { previewing = id; tell() }
const usePreviewing = () => useSyncExternalStore(sub, () => previewing)

/** What the Look sheet shows and changes: the frame's own presentation
 *  store, so a choice made there is drawn at once. */
export interface LookControls {
  conversation: string | null
  /** the conversation's name, for "chosen for …" */
  scopeName: string
  /** the atmosphere drawn now, and whether it was chosen for this conversation */
  current: Atmosphere
  explicit: boolean
  /** what this conversation falls back to: configured, or the Brain's default */
  inherited: Atmosphere
  /** the Brain's default */
  brain: Atmosphere
  choices: { id: Atmosphere; name: string; says: string }[]
  /** the looks made from pictures, their thumbnails, and saving another */
  pictures: PresentationStore
  /** for this conversation; null returns it to what it inherits */
  choose: (a: Atmosphere | null) => Promise<void>
  chooseBrain: (a: Atmosphere) => Promise<void>
}
let controls: LookControls | null = null
export const useLookControls = () => useSyncExternalStore(sub, () => controls)

export function useLook(conversation: string | null, name: string | null): 'dark' | 'light' {
  const pres = usePresentation()
  const atm = useAtmospheres(pres)
  const t = useTheme()
  const activity = useActivityLook()
  const [systemDark, setSystemDark] = useState(prefersDark)

  /* A theme chosen in production's tab is this page's theme too. */
  useEffect(() => {
    const again = () => {
      const nextTheme = readTheme()
      const nextActivity = readActivityLook()
      let changed = false
      if (nextTheme !== theme) { theme = nextTheme; changed = true }
      if (nextActivity !== activityLook) { activityLook = nextActivity; changed = true }
      if (changed) tell()
    }
    window.addEventListener('storage', again)
    window.addEventListener('focus', again)
    const mq = window.matchMedia?.('(prefers-color-scheme: dark)')
    const sys = () => setSystemDark(prefersDark())
    mq?.addEventListener?.('change', sys)
    return () => {
      window.removeEventListener('storage', again)
      window.removeEventListener('focus', again)
      mq?.removeEventListener?.('change', sys)
    }
  }, [])

  useEffect(() => {
    const root = document.documentElement
    if (t === 'system') root.removeAttribute('data-theme')
    else root.setAttribute('data-theme', t)
  }, [t])

  useEffect(() => {
    const root = document.documentElement
    if (activity === 'default') root.removeAttribute('data-activity-look')
    else root.setAttribute('data-activity-look', activity)
  }, [activity])

  const resolved = atm.resolve(conversation, name).at
  const known = (a: Atmosphere) => !a.startsWith('look-') || pres.looks.some((l) => l.id === a)
  const trying = usePreviewing()
  const shown = (trying as Atmosphere | null) ?? (known(resolved) ? resolved : 'default')
  useEffect(() => {
    const root = document.documentElement
    if (shown === 'default') root.removeAttribute('data-atmosphere')
    else root.setAttribute('data-atmosphere', shown)
  }, [shown])

  /* THE SCHEME DRAWN IS THE GROUND'S (#568 4.2). The theme decides it only
     where the atmosphere leaves the ground to it (Mentis, and any look
     without a ground of its own); a picture atmosphere's own ground -- dark
     under Hail Mary whatever the theme says -- decides it otherwise. Read
     from the ground the document resolves, so a look made from a picture
     answers too. */
  const chosen = t === 'system' ? (systemDark ? 'dark' : 'light') : t
  const [now, setNow] = useState<'dark' | 'light'>(chosen)
  useEffect(() => {
    let raf = requestAnimationFrame(() => {
      raf = requestAnimationFrame(() => setNow(groundScheme() ?? chosen))
    })
    return () => cancelAnimationFrame(raf)
  }, [chosen, shown, pres.looks])
  useEffect(() => { if (scheme !== now) { scheme = now; tell() } }, [now])

  const { explicit } = atm.resolve(conversation, name)
  const inherited = atm.resolve(null, name).at
  const current = known(resolved) ? resolved : 'default'
  const made = useMemo<LookControls>(() => ({
    conversation, scopeName: name ?? 'this conversation', current, explicit, inherited, brain: atm.brain,
    choices: [
      ...ATMOSPHERES.map((a) => ({ id: a.id as Atmosphere, name: a.name, says: a.says })),
      ...pres.looks.map((l) => ({ id: l.id as Atmosphere, name: l.name, says: 'a look made from a picture' })),
    ],
    pictures: pres,
    choose: (a) => (conversation ? atm.set(conversation, a) : atm.setBrain(a ?? 'default')),
    chooseBrain: (a) => atm.setBrain(a),
  }), [conversation, name, current, explicit, inherited, atm, pres])
  useEffect(() => { controls = made; tell() }, [made])
  return now
}
