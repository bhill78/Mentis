/* LOOK & BACKGROUND, AS SETTINGS COLUMNS (owner round 2).
 *
 * The Settings panel replaces the old Arrange sheet and separate Look sheet.
 * This hook builds its Look & background columns using the shared IconMenu
 * component (frame/IconMenu.tsx):
 *
 *   - Theme: Light / Dark / System (pressed state = current)
 *   - Background: thumbnail swatches, tier for all atmospheres, "Make" for custom pictures
 *   - Surfaces: Clear / Quiet / Glass / Solid, Opacity slider in body, Layers tier, Reset
 *   - Opening: Over / Beside
 *
 * Icons first, one-word labels, full meaning in tooltips. All settings retain
 * their existing storage, undo toasts, and effects. */

import { useState, useSyncExternalStore, type ReactNode } from 'react'
import type { IconGroup, IconItem } from './IconMenu'
import './iconMenu.css'
import './lookColumn.css'
import { setTheme, startMaking, useLookControls, useTheme, type LookControls, type Theme } from './look'
import { ATMOSPHERES, type Atmosphere } from '../../atmosphere'
import { UNREACHABLE, type PresentationStore } from '../../picture/store'
import { closeSheet } from './Sheet'
import { showToast } from './toasts'
import { LOOK, atmosphereStyle, isBuiltIn } from './LookSheet'
import { workspace, useArr } from '../workspace/place'
import { objectsOpen, onObjectsOpen, setObjectsOpen } from '../workspace/open'
import type { DetailMode } from '../nav'
import {
  DEFAULT_APPEARANCE,
  F6_APPEARANCE,
  readAppearance,
  type Appearance,
} from '../present'

/* -- Helper icons for the icon menu (restrained, theme tokens) ------------ */

function SunIcon() {
  return (
    <svg viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" aria-hidden="true">
      <circle cx="10" cy="10" r="4" />
      <line x1="10" y1="2" x2="10" y2="4" />
      <line x1="10" y1="16" x2="10" y2="18" />
      <line x1="2" y1="10" x2="4" y2="10" />
      <line x1="16" y1="10" x2="18" y2="10" />
      <line x1="4.3" y1="4.3" x2="5.7" y2="5.7" />
      <line x1="14.3" y1="14.3" x2="15.7" y2="15.7" />
      <line x1="4.3" y1="15.7" x2="5.7" y2="14.3" />
      <line x1="14.3" y1="5.7" x2="15.7" y2="4.3" />
    </svg>
  )
}

function MoonIcon() {
  return (
    <svg viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M15.5 11.5A6.5 6.5 0 1 1 8.5 4.5 5 5 0 0 0 15.5 11.5z" />
    </svg>
  )
}

function SystemIcon() {
  return (
    <svg viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="3" y="3" width="14" height="10" rx="2" />
      <line x1="7" y1="16.5" x2="13" y2="16.5" />
      <line x1="10" y1="13" x2="10" y2="16.5" />
    </svg>
  )
}

function MakeIcon() {
  return (
    <svg viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="3" y="3" width="14" height="14" rx="3" />
      <line x1="10" y1="7" x2="10" y2="13" />
      <line x1="7" y1="10" x2="13" y2="10" />
    </svg>
  )
}

function MoreIcon() {
  return (
    <svg viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
      <rect x="3" y="3" width="5.5" height="5.5" rx="1.5" />
      <rect x="11.5" y="3" width="5.5" height="5.5" rx="1.5" />
      <rect x="3" y="11.5" width="5.5" height="5.5" rx="1.5" />
      <rect x="11.5" y="11.5" width="5.5" height="5.5" rx="1.5" />
    </svg>
  )
}

function ScopePostIcon() {
  return (
    <svg viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M4 4h12a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2H8l-4 3V6a2 2 0 0 1 2-2z" />
    </svg>
  )
}

function ScopeAllIcon() {
  return (
    <svg viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="10" cy="10" r="7" />
      <path d="M3 10h14M10 3a11 11 0 0 1 0 14M10 3a11 11 0 0 0 0 14" />
    </svg>
  )
}

function ResetIcon() {
  return (
    <svg viewBox="0 0 20 16" width="20" height="16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M4 7A6 6 0 1 1 5.8 12.5" />
      <polyline points="4 3 4 7 8 7" />
    </svg>
  )
}

function SurfaceClearIcon() {
  return (
    <svg viewBox="0 0 20 16" width="20" height="16" aria-hidden="true">
      <rect x="1" y="1" width="18" height="14" rx="2" fill="none" stroke="var(--line-strong)" strokeDasharray="2 2" />
      <rect x="4.5" y="3.5" width="11" height="9" rx="1.5" fill="none" stroke="var(--text-dim)" strokeWidth="1" />
    </svg>
  )
}

function SurfaceQuietIcon() {
  return (
    <svg viewBox="0 0 20 16" width="20" height="16" aria-hidden="true">
      <rect x="1" y="1" width="18" height="14" rx="2" fill="none" stroke="var(--line)" />
      <rect x="4.5" y="3.5" width="11" height="9" rx="1.5" fill="color-mix(in srgb, var(--text) 22%, transparent)" />
    </svg>
  )
}

function SurfaceGlassIcon() {
  return (
    <svg viewBox="0 0 20 16" width="20" height="16" aria-hidden="true">
      <rect x="1" y="1" width="18" height="14" rx="2" fill="color-mix(in srgb, var(--surface) 60%, transparent)" stroke="var(--line)" />
      <rect x="4.5" y="3.5" width="11" height="9" rx="1.5" fill="color-mix(in srgb, var(--text) 18%, transparent)" />
    </svg>
  )
}

function SurfaceSolidIcon() {
  return (
    <svg viewBox="0 0 20 16" width="20" height="16" aria-hidden="true">
      <rect x="1" y="1" width="18" height="14" rx="2" fill="var(--surface-raised)" stroke="var(--line-strong)" />
      <rect x="4.5" y="3.5" width="11" height="9" rx="1.5" fill="var(--surface)" />
    </svg>
  )
}

function LayersIcon() {
  return (
    <svg viewBox="0 0 20 16" width="20" height="16" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M10 2L2 6l8 4 8-4-8-4z" />
      <path d="M2 10l8 4 8-4" />
    </svg>
  )
}

function PanelClearIcon() {
  return (
    <svg viewBox="0 0 20 16" width="20" height="16" aria-hidden="true">
      <rect x="1.5" y="1.5" width="17" height="13" rx="2" fill="none" stroke="var(--line-strong)" strokeDasharray="2 2" strokeWidth="1.2" />
    </svg>
  )
}

function PanelTintedIcon() {
  return (
    <svg viewBox="0 0 20 16" width="20" height="16" aria-hidden="true">
      <rect x="1.5" y="1.5" width="17" height="13" rx="2" fill="color-mix(in srgb, var(--surface) 60%, transparent)" stroke="var(--line)" strokeWidth="1.2" />
    </svg>
  )
}

function PanelSolidIcon() {
  return (
    <svg viewBox="0 0 20 16" width="20" height="16" aria-hidden="true">
      <rect x="1.5" y="1.5" width="17" height="13" rx="2" fill="var(--surface-raised)" stroke="var(--line-strong)" strokeWidth="1.2" />
    </svg>
  )
}

function ContentClearIcon() {
  return (
    <svg viewBox="0 0 20 16" width="20" height="16" aria-hidden="true">
      <rect x="4" y="2.5" width="12" height="11" rx="2" fill="none" stroke="var(--text-dim)" strokeWidth="1.2" />
    </svg>
  )
}

function ContentTintedIcon() {
  return (
    <svg viewBox="0 0 20 16" width="20" height="16" aria-hidden="true">
      <rect x="4" y="2.5" width="12" height="11" rx="2" fill="color-mix(in srgb, var(--text) 22%, transparent)" />
    </svg>
  )
}

function ContentSolidIcon() {
  return (
    <svg viewBox="0 0 20 16" width="20" height="16" aria-hidden="true">
      <rect x="4" y="2.5" width="12" height="11" rx="2" fill="var(--surface)" stroke="var(--line)" strokeWidth="1" />
    </svg>
  )
}

function OpenOverIcon() {
  return (
    <svg viewBox="0 0 20 16" width="20" height="16" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="2" y="4" width="11" height="10" rx="1.5" strokeDasharray="1.5 1.5" />
      <rect x="7" y="1" width="11" height="10" rx="1.5" fill="var(--canvas)" stroke="currentColor" />
    </svg>
  )
}

function OpenBesideIcon() {
  return (
    <svg viewBox="0 0 20 16" width="20" height="16" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="2" y="2" width="7" height="12" rx="1.5" stroke="currentColor" />
      <rect x="11" y="2" width="7" height="12" rx="1.5" stroke="currentColor" />
    </svg>
  )
}

/* -- Pure helpers --------------------------------------------------------- */

export function atmosphereLabel(id: Atmosphere, name: string): string {
  if (id === 'hailmary') return 'Hail'
  return name.trim().split(/\s+/)[0]
}

export function Swatch({ at, pictures }: { at: Atmosphere; pictures?: PresentationStore }) {
  return <span className="im-swatch" aria-hidden="true" style={atmosphereStyle(at, pictures)} />
}

export { atmosphereStyle } from './LookSheet'

export const sameAppearance = (a: Appearance, b: Appearance) =>
  a.panel === b.panel && a.content === b.content && Math.abs(a.opacity - b.opacity) < 0.005

export interface LookGroupsContext {
  theme: Theme
  onPickTheme: (t: Theme) => void
  controls: LookControls | null
  scope: 'here' | 'brain'
  onSetScope: (s: 'here' | 'brain') => void
  appearance: Appearance
  isDefaultAppearance: boolean
  onPickAppearance: (a: Appearance) => void
  onResetAppearance: () => void
  openMode: DetailMode
  onPickOpenMode: (m: DetailMode) => void
  onChooseAtmosphere: (a: Atmosphere | null) => void
  onStartMaking: () => void
}

/** Pure builder that assembles the Look & background columns for IconMenu. */
export function buildLookGroups(ctx: LookGroupsContext): IconGroup[] {
  const c = ctx.controls
  const currentAtm = c?.current ?? 'default'
  const ownGround = currentAtm !== 'default'
  const currentName = c?.choices.find((x) => x.id === currentAtm)?.name ?? (isBuiltIn(currentAtm) ? LOOK[currentAtm]?.text ? currentAtm : 'Mentis' : 'Custom')
  const here = ctx.scope === 'here' && !!c?.conversation
  const chosenAtm = here ? (c?.explicit ? c?.current : null) : c?.brain

  /* 1. THEME */
  const themeGroup: IconGroup = {
    title: 'Theme',
    items: [
      {
        id: 'theme-light',
        label: 'Light',
        says: ownGround ? `${currentName} keeps its own colours; Light is for the Mentis look` : 'Light theme: pale ground with dark ink',
        icon: <SunIcon />,
        on: ctx.theme === 'light',
        onPick: () => ctx.onPickTheme('light'),
      },
      {
        id: 'theme-dark',
        label: 'Dark',
        says: ownGround ? `${currentName} keeps its own colours; Dark is for the Mentis look` : 'Dark theme: deep ground with pale ink',
        icon: <MoonIcon />,
        on: ctx.theme === 'dark',
        onPick: () => ctx.onPickTheme('dark'),
      },
      {
        id: 'theme-system',
        label: 'System',
        says: ownGround ? `${currentName} keeps its own colours; System is for the Mentis look` : 'Follow the system appearance',
        icon: <SystemIcon />,
        on: ctx.theme === 'system',
        onPick: () => ctx.onPickTheme('system'),
      },
    ],
  }

  /* 2. BACKGROUND */
  // Deeper tier: all built-ins, pictures, and scope
  const isAtmActive = (id: Atmosphere) => chosenAtm === id || (here && !c?.explicit && currentAtm === id)

  const readyMadeItems: IconItem[] = ATMOSPHERES.map((a) => ({
    id: `tier-atm-${a.id}`,
    label: atmosphereLabel(a.id, a.name),
    says: `${a.name}: ${a.says}`,
    icon: <Swatch at={a.id} pictures={c?.pictures} />,
    on: isAtmActive(a.id),
    onPick: () => ctx.onChooseAtmosphere(a.id),
  }))

  const pictureItems: IconItem[] = [
    ...(c?.pictures.looks ?? []).map((l) => ({
      id: `tier-pic-${l.id}`,
      label: atmosphereLabel(l.id as Atmosphere, l.name),
      says: l.name,
      icon: <Swatch at={l.id as Atmosphere} pictures={c?.pictures} />,
      on: isAtmActive(l.id as Atmosphere),
      onPick: () => ctx.onChooseAtmosphere(l.id as Atmosphere),
    })),
    {
      id: 'tier-pic-make',
      label: 'Make',
      says: 'Make a look from a picture…',
      icon: <MakeIcon />,
      onPick: ctx.onStartMaking,
    },
  ]

  const moreTierGroups: IconGroup[] = [
    {
      title: 'Ready-made',
      items: readyMadeItems,
    },
    {
      title: 'Pictures',
      items: pictureItems,
    },
  ]

  if (c?.conversation) {
    const scopeItems: IconItem[] = [
      {
        id: 'scope-here',
        label: 'Post',
        says: 'Apply atmosphere to this conversation only',
        icon: <ScopePostIcon />,
        on: ctx.scope === 'here',
        onPick: () => ctx.onSetScope('here'),
      },
      {
        id: 'scope-brain',
        label: 'All',
        says: 'Apply atmosphere as Brain default for all conversations',
        icon: <ScopeAllIcon />,
        on: ctx.scope === 'brain',
        onPick: () => ctx.onSetScope('brain'),
      },
    ]
    if (here && c.explicit) {
      scopeItems.push({
        id: 'scope-usual',
        label: 'Usual',
        says: `Go back to the usual look (${c.choices.find((x) => x.id === c.inherited)?.name ?? 'Mentis'})`,
        icon: <ResetIcon />,
        onPick: () => ctx.onChooseAtmosphere(null),
      })
    }
    moreTierGroups.push({
      title: 'Scope',
      items: scopeItems,
    })
  }

  // Primary column: top atmospheres (ensuring current is visible), plus Make and More
  const topIds: Atmosphere[] = ['default', 'nightfall', 'hailmary']
  if (!topIds.includes(currentAtm)) {
    topIds.push(currentAtm)
  } else {
    topIds.push('saltmarsh')
  }

  const primaryAtmItems: IconItem[] = topIds.map((id) => {
    const itemMeta = c?.choices.find((x) => x.id === id) ?? ATMOSPHERES.find((x) => x.id === id)
    const name = itemMeta?.name ?? (id === 'default' ? 'Mentis' : id)
    const says = itemMeta?.says ?? name
    return {
      id: `bg-${id}`,
      label: atmosphereLabel(id, name),
      says: `${name}: ${says}`,
      icon: <Swatch at={id} pictures={c?.pictures} />,
      on: isAtmActive(id),
      onPick: () => ctx.onChooseAtmosphere(id),
    }
  })

  primaryAtmItems.push(
    {
      id: 'bg-make',
      label: 'Make',
      says: 'Make a look from a picture…',
      icon: <MakeIcon />,
      onPick: ctx.onStartMaking,
    },
    {
      id: 'bg-more',
      label: 'More',
      says: 'All atmospheres, pictures, and scope',
      icon: <MoreIcon />,
      tier: moreTierGroups,
    },
  )

  const backgroundGroup: IconGroup = {
    title: 'Background',
    items: primaryAtmItems,
  }

  /* 3. SURFACES */
  const app = ctx.appearance
  const covers = app.panel !== 'transparent' || app.content !== 'transparent'
  const pct = Math.round(app.opacity * 100)

  const panelTreatmentGroup: IconGroup = {
    title: 'Panel',
    items: [
      {
        id: 'panel-clear',
        label: 'Clear',
        says: 'Clear panel: nothing behind the whole zone',
        icon: <PanelClearIcon />,
        on: app.panel === 'transparent',
        onPick: () => ctx.onPickAppearance({ ...app, panel: 'transparent' }),
      },
      {
        id: 'panel-tinted',
        label: 'Tinted',
        says: 'Tinted panel: translucent wash behind the zone',
        icon: <PanelTintedIcon />,
        on: app.panel === 'tinted',
        onPick: () => ctx.onPickAppearance({ ...app, panel: 'tinted' }),
      },
      {
        id: 'panel-solid',
        label: 'Solid',
        says: 'Solid panel: opaque surface behind the zone',
        icon: <PanelSolidIcon />,
        on: app.panel === 'solid',
        onPick: () => ctx.onPickAppearance({ ...app, panel: 'solid' }),
      },
    ],
  }

  const contentTreatmentGroup: IconGroup = {
    title: 'Content',
    items: [
      {
        id: 'content-clear',
        label: 'Clear',
        says: 'Clear content: border outline only behind objects',
        icon: <ContentClearIcon />,
        on: app.content === 'transparent',
        onPick: () => ctx.onPickAppearance({ ...app, content: 'transparent' }),
      },
      {
        id: 'content-tinted',
        label: 'Tinted',
        says: 'Tinted content: light wash under objects',
        icon: <ContentTintedIcon />,
        on: app.content === 'tinted',
        onPick: () => ctx.onPickAppearance({ ...app, content: 'tinted' }),
      },
      {
        id: 'content-solid',
        label: 'Solid',
        says: 'Solid content: opaque cards behind objects',
        icon: <ContentSolidIcon />,
        on: app.content === 'solid',
        onPick: () => ctx.onPickAppearance({ ...app, content: 'solid' }),
      },
    ],
  }

  const surfaceItems: IconItem[] = [
    {
      id: 'surface-clear',
      label: 'Clear',
      says: 'Clear: nothing painted, atmosphere throughout',
      icon: <SurfaceClearIcon />,
      on: sameAppearance(app, DEFAULT_APPEARANCE),
      onPick: () => ctx.onPickAppearance(DEFAULT_APPEARANCE),
    },
    {
      id: 'surface-quiet',
      label: 'Quiet',
      says: 'Quiet: no panel, a light wash under content',
      icon: <SurfaceQuietIcon />,
      on: sameAppearance(app, { panel: 'transparent', content: 'tinted', opacity: 0.6 }),
      onPick: () => ctx.onPickAppearance({ panel: 'transparent', content: 'tinted', opacity: 0.6 }),
    },
    {
      id: 'surface-glass',
      label: 'Glass',
      says: "Glass: glass panel with washed cards",
      icon: <SurfaceGlassIcon />,
      on: sameAppearance(app, F6_APPEARANCE),
      onPick: () => ctx.onPickAppearance(F6_APPEARANCE),
    },
    {
      id: 'surface-solid',
      label: 'Solid',
      says: 'Solid: opaque panel and cards, nothing behind',
      icon: <SurfaceSolidIcon />,
      on: sameAppearance(app, { panel: 'solid', content: 'solid', opacity: 1 }),
      onPick: () => ctx.onPickAppearance({ panel: 'solid', content: 'solid', opacity: 1 }),
    },
    {
      id: 'surface-layers',
      label: 'Layers',
      says: 'Panel and content treatments set separately',
      icon: <LayersIcon />,
      tier: [panelTreatmentGroup, contentTreatmentGroup],
    },
    {
      id: 'surface-reset',
      label: 'Reset',
      says: "Back to Mentis's quiet look",
      icon: <ResetIcon />,
      off: ctx.isDefaultAppearance,
      why: 'already using default look',
      onPick: ctx.onResetAppearance,
    },
  ]

  const opacityBody: ReactNode = (
    <label
      className="im-opacity"
      title={covers ? 'How much of the atmosphere a fill covers' : 'Nothing is filled: opacity has nothing to cover'}
    >
      <span className="im-opacity-label">Opacity</span>
      <input
        type="range"
        className="im-opacity-slider"
        min={0}
        max={100}
        step={5}
        value={pct}
        disabled={!covers}
        aria-label="Surface opacity"
        onChange={(e) => ctx.onPickAppearance({ ...app, opacity: Number(e.target.value) / 100 })}
      />
      <span className="im-opacity-pct">{pct}%</span>
    </label>
  )

  const surfacesGroup: IconGroup = {
    title: 'Surfaces',
    items: surfaceItems,
    body: opacityBody,
  }

  /* 4. OPENING */
  const openingGroup: IconGroup = {
    title: 'Opening',
    items: [
      {
        id: 'open-over',
        label: 'Over',
        says: 'Open objects over the arrangement (replies still open beside This post)',
        icon: <OpenOverIcon />,
        on: ctx.openMode === 'over',
        onPick: () => ctx.onPickOpenMode('over'),
      },
      {
        id: 'open-beside',
        label: 'Beside',
        says: 'Open objects beside This post, keeping the arrangement visible',
        icon: <OpenBesideIcon />,
        on: ctx.openMode === 'aside',
        onPick: () => ctx.onPickOpenMode('aside'),
      },
    ],
  }

  return [themeGroup, backgroundGroup, surfacesGroup, openingGroup]
}

/* -- Hook implementation for the Settings panel -------------------------- */

export function useLookGroups(): IconGroup[] {
  const theme = useTheme()
  const c = useLookControls()
  const [scope, setScope] = useState<'here' | 'brain'>('here')
  const arr = useArr(workspace)
  const openMode = useSyncExternalStore(onObjectsOpen, objectsOpen)

  const app = readAppearance(arr?.appearance, DEFAULT_APPEARANCE)
  const isDefaultAppearance = !arr?.appearance

  const onPickTheme = (t: Theme) => {
    setTheme(t)
    const currentAtm = c?.current ?? 'default'
    if (currentAtm !== 'default') {
      const name = c?.choices.find((x) => x.id === currentAtm)?.name ?? currentAtm
      const themeLabel = t === 'light' ? 'Light' : t === 'dark' ? 'Dark' : 'System'
      showToast({ text: `${name} keeps its own colours. ${themeLabel} is for the Mentis look.` })
    }
  }

  const onChooseAtmosphere = (a: Atmosphere | null) => {
    if (!c) return
    const here = scope === 'here' && !!c.conversation
    const was = here ? (c.explicit ? c.current : null) : c.brain
    const nameOf = (atm: Atmosphere) => c.choices.find((x) => x.id === atm)?.name ?? 'Mentis'
    const p = here ? c.choose(a) : c.chooseBrain(a ?? 'default')
    p.then(
      () => {
        showToast({
          text: here ? `${c.scopeName} now uses ${nameOf(a ?? c.inherited)}` : `All conversations now use ${nameOf(a ?? 'default')}`,
          action: {
            label: 'Undo',
            run: () => void (here ? c.choose(was) : c.chooseBrain(was ?? 'default')).catch(() => showToast({ text: UNREACHABLE })),
          },
        })
      },
      (e: Error) => {
        showToast({ text: `Could not change the look: ${e.message || UNREACHABLE}` })
      },
    )
  }

  const onStartMaking = () => {
    closeSheet()
    startMaking(scope === 'here' && c?.conversation ? 'conversation' : 'everywhere')
  }

  const onPickAppearance = (next: Appearance) => {
    workspace.edit((x) => ({ ...x, appearance: next }))
  }

  const onResetAppearance = () => {
    workspace.edit(({ appearance: _gone, ...x }) => x, "This place takes Mentis's quiet look again.")
  }

  return buildLookGroups({
    theme,
    onPickTheme,
    controls: c,
    scope,
    onSetScope: setScope,
    appearance: app,
    isDefaultAppearance,
    onPickAppearance,
    onResetAppearance,
    openMode,
    onPickOpenMode: setObjectsOpen,
    onChooseAtmosphere,
    onStartMaking,
  })
}
