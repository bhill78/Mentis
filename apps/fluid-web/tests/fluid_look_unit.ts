/* Unit tests for LookColumn (Look & background Settings columns).
 * Tests pure helpers, mapping atmospheres, surface presets, tiers, one-word labels,
 * and renders IconMenu with the resulting groups into HTML. */

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import {
  atmosphereLabel,
  atmosphereStyle,
  buildLookGroups,
  sameAppearance,
  type LookGroupsContext,
} from '../src/fluid/frame/LookColumn'
import { IconMenu, type IconGroup, type IconItem } from '../src/fluid/frame/IconMenu'
import { DEFAULT_APPEARANCE, F6_APPEARANCE, type Appearance } from '../src/fluid/present/types'
import { ATMOSPHERES } from '../src/atmosphere'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (v: unknown, what: string) => { assert.ok(v, what); checks++ }

/* =========================================================================
   1. ONE-WORD ATMOSPHERE LABELS
   ========================================================================= */

eq(atmosphereLabel('default', 'Mentis'), 'Mentis', 'Mentis is 1 word')
eq(atmosphereLabel('saltmarsh', 'Harbour'), 'Harbour', 'Harbour is 1 word')
eq(atmosphereLabel('nightfall', 'Nightfall'), 'Nightfall', 'Nightfall is 1 word')
eq(atmosphereLabel('hailmary', 'Hail Mary'), 'Hail', 'Hail Mary is abbreviated to single word Hail')
eq(atmosphereLabel('tidewater', 'Tidewater'), 'Tidewater', 'Tidewater is 1 word')
eq(atmosphereLabel('look-custom' as any, 'Sunset Beach Ocean'), 'Sunset', 'Multi-word custom look names take first word')

/* =========================================================================
   2. APPEARANCE EQUALITY
   ========================================================================= */

ok(sameAppearance(DEFAULT_APPEARANCE, { panel: 'transparent', content: 'transparent', opacity: 0.6 }), 'matches DEFAULT_APPEARANCE')
ok(sameAppearance(F6_APPEARANCE, { panel: 'tinted', content: 'tinted', opacity: 1.0 }), 'matches F6_APPEARANCE')
ok(sameAppearance({ panel: 'solid', content: 'solid', opacity: 0.601 }, { panel: 'solid', content: 'solid', opacity: 0.602 }), 'handles floating point delta < 0.005')
ok(!sameAppearance({ panel: 'solid', content: 'solid', opacity: 0.6 }, { panel: 'solid', content: 'solid', opacity: 0.7 }), 'detects opacity differences')
ok(!sameAppearance({ panel: 'tinted', content: 'solid', opacity: 1 }, { panel: 'solid', content: 'solid', opacity: 1 }), 'detects fill differences')

/* =========================================================================
   3. ATMOSPHERE STYLE COMPUTATION
   ========================================================================= */

const defaultStyle = atmosphereStyle('default')
eq(defaultStyle.backgroundColor, '#fdfcfa', 'default has #fdfcfa ground')

const saltmarshStyle = atmosphereStyle('saltmarsh')
eq(saltmarshStyle.backgroundColor, '#0e1518', 'saltmarsh has #0e1518 ground')
ok(saltmarshStyle.backgroundImage?.includes('radial-gradient'), 'saltmarsh has radial-gradient background')

const nightfallStyle = atmosphereStyle('nightfall')
eq(nightfallStyle.backgroundColor, '#05070d', 'nightfall has #05070d ground')
ok(nightfallStyle.backgroundImage?.includes('/atmospheres/nightfall.jpg'), 'nightfall references nightfall.jpg')

const mockPictures: any = {
  looks: [
    {
      id: 'look-stars',
      name: 'Starry Sky',
      theme: {
        scheme: 'dark',
        wide: { '--canvas': '#001122', '--accent': '#ffcc00' },
      },
    },
  ],
  thumb: (id: string) => `/thumbs/${id}.png`,
}

const customStyle = atmosphereStyle('look-stars' as any, mockPictures)
eq(customStyle.backgroundColor, '#001122', 'custom look uses theme canvas')
ok(customStyle.backgroundImage?.includes('/thumbs/look-stars.png'), 'custom look uses thumb url')

/* =========================================================================
   4. BUILD LOOK GROUPS & CONTRACT VERIFICATION
   ========================================================================= */

let pickedTheme: string | null = null
let pickedActivityLook: string | null = null
let pickedAtm: string | null = null
let pickedAppearance: Appearance | null = null
let resetAppearanceCalled = false
let pickedOpenMode: string | null = null
let startedMaking = false
let currentScope: 'here' | 'brain' = 'here'

const ctx: LookGroupsContext = {
  theme: 'dark',
  onPickTheme: (t) => { pickedTheme = t },
  activityLook: 'retro-green',
  onPickActivityLook: (look) => { pickedActivityLook = look },
  controls: {
    conversation: 'conv-123',
    scopeName: 'Sprint Retro',
    current: 'nightfall',
    explicit: true,
    inherited: 'default',
    brain: 'default',
    choices: [
      ...ATMOSPHERES.map((a) => ({ id: a.id, name: a.name, says: a.says })),
      { id: 'look-stars' as any, name: 'Starry Sky', says: 'a look made from a picture' },
    ],
    pictures: mockPictures,
    choose: async (a) => { pickedAtm = a },
    chooseBrain: async (a) => { pickedAtm = a },
  },
  scope: currentScope,
  onSetScope: (s) => { currentScope = s },
  appearance: { panel: 'transparent', content: 'tinted', opacity: 0.6 }, // Quiet
  isDefaultAppearance: false,
  onPickAppearance: (a) => { pickedAppearance = a },
  onResetAppearance: () => { resetAppearanceCalled = true },
  openMode: 'over',
  onPickOpenMode: (m) => { pickedOpenMode = m },
  onChooseAtmosphere: (a) => { pickedAtm = a },
  onStartMaking: () => { startedMaking = true },
}

const groups = buildLookGroups(ctx)

// 5 groups returned
eq(groups.length, 5, 'returns 5 groups')
eq(groups.map((g) => g.title), ['Theme', 'Activity', 'Background', 'Surfaces', 'Opening'], 'groups include Activity in Look settings')

// Check the one-word label rule across ALL items in all groups and tiers
function checkItemContract(it: IconItem, path: string) {
  ok(it.id, `${path}: item must have an id`)
  ok(it.label, `${path}: item must have a label`)
  ok(!it.label.includes(' '), `${path}: item label "${it.label}" must be a single word (owner rule)`)
  ok(it.says, `${path}: item must have tooltip text in says`)
  ok(it.icon, `${path}: item must have an icon`)
  if (it.tier) {
    for (const sub of it.tier) {
      if (sub.items) {
        for (const subIt of sub.items) {
          checkItemContract(subIt, `${path} > ${sub.title ?? 'tier'} > ${subIt.id}`)
        }
      }
    }
  }
}

for (const g of groups) {
  if (g.items) {
    for (const it of g.items) {
      checkItemContract(it, `${g.title} > ${it.id}`)
    }
  }
}

// 4a. Theme group
const themeGroup = groups[0]
eq(themeGroup.items?.length, 3, 'Theme has 3 items: Light, Dark, System')
const darkTheme = themeGroup.items?.find((x) => x.id === 'theme-dark')
ok(darkTheme?.on, 'Dark theme is active when ctx.theme is dark')
const lightTheme = themeGroup.items?.find((x) => x.id === 'theme-light')
ok(!lightTheme?.on, 'Light theme is inactive')
lightTheme?.onPick?.()
eq(pickedTheme, 'light', 'picking light theme invokes callback')

// 4b. Activity group
const activityGroup = groups[1]
eq(activityGroup.items?.map((x) => x.label), ['Default', 'Console', 'Retro', 'Modern', 'Stylish', 'Minimalist'], 'Activity has all six requested looks')
ok(activityGroup.items?.find((x) => x.id === 'activity-retro-green')?.on, 'Retro Green Terminal is active')
activityGroup.items?.find((x) => x.id === 'activity-console')?.onPick?.()
eq(pickedActivityLook, 'console', 'picking an Activity look invokes its callback')

// 4c. Background group
const bgGroup = groups[2]
ok(bgGroup.items && bgGroup.items.length >= 6, 'Background has at least 6 items')
const nightfallItem = bgGroup.items?.find((x) => x.id === 'bg-nightfall')
ok(nightfallItem?.on, 'Nightfall is on because it is current')
nightfallItem?.onPick?.()
eq(pickedAtm, 'nightfall', 'picking nightfall invokes choose callback')

const makeItem = bgGroup.items?.find((x) => x.id === 'bg-make')
ok(makeItem, 'Make item is present')
makeItem?.onPick?.()
ok(startedMaking, 'clicking Make invokes onStartMaking')

const moreItem = bgGroup.items?.find((x) => x.id === 'bg-more')
ok(moreItem?.tier, 'More item has tier')
const moreTiers = moreItem!.tier!
eq(moreTiers.map((t) => t.title), ['Ready-made', 'Pictures', 'Scope'], 'More tier has Ready-made, Pictures, Scope')
const readyMade = moreTiers.find((t) => t.title === 'Ready-made')!
eq(readyMade.items?.length, 11, 'Ready-made tier has all 11 built-in atmospheres')
const scopeTier = moreTiers.find((t) => t.title === 'Scope')!
ok(scopeTier.items?.some((i) => i.id === 'scope-here'), 'Scope tier has Post')
ok(scopeTier.items?.some((i) => i.id === 'scope-brain'), 'Scope tier has All')
ok(scopeTier.items?.some((i) => i.id === 'scope-usual'), 'Scope tier has Usual when explicit')

// 4d. Surfaces group
const surfacesGroup = groups[3]
eq(surfacesGroup.items?.length, 6, 'Surfaces has 6 items (Clear, Quiet, Glass, Solid, Layers, Reset)')
const quietItem = surfacesGroup.items?.find((x) => x.id === 'surface-quiet')
ok(quietItem?.on, 'Quiet preset is on matching current appearance')
const clearItem = surfacesGroup.items?.find((x) => x.id === 'surface-clear')
clearItem?.onPick?.()
eq(pickedAppearance, DEFAULT_APPEARANCE, 'picking Clear calls onPickAppearance with DEFAULT_APPEARANCE')

const resetItem = surfacesGroup.items?.find((x) => x.id === 'surface-reset')
ok(!resetItem?.off, 'Reset is enabled when isDefaultAppearance is false')
resetItem?.onPick?.()
ok(resetAppearanceCalled, 'clicking Reset calls onResetAppearance')

const layersItem = surfacesGroup.items?.find((x) => x.id === 'surface-treatments' || x.id === 'surface-layers')
ok(layersItem?.tier, 'Layers item has tier for panel and content treatments')
eq(layersItem!.tier!.map((t) => t.title), ['Panel', 'Content'], 'Layers tier has Panel and Content columns')
const panelCol = layersItem!.tier![0]
eq(panelCol.items?.length, 3, 'Panel column has Clear, Tinted, Solid')
ok(panelCol.items?.find((i) => i.id === 'panel-clear')?.on, 'Panel Clear is on')
const contentCol = layersItem!.tier![1]
eq(contentCol.items?.length, 3, 'Content column has Clear, Tinted, Solid')
ok(contentCol.items?.find((i) => i.id === 'content-tinted')?.on, 'Content Tinted is on')

// Check opacity slider in surfaces body
ok(surfacesGroup.body, 'Surfaces has body with opacity slider')

// 4e. Opening group
const openGroup = groups[4]
eq(openGroup.items?.length, 2, 'Opening has 2 items: Over, Beside')
const overItem = openGroup.items?.find((x) => x.id === 'open-over')
ok(overItem?.on, 'Over is on when openMode is over')
const besideItem = openGroup.items?.find((x) => x.id === 'open-beside')
ok(!besideItem?.on, 'Beside is inactive')
besideItem?.onPick?.()
eq(pickedOpenMode, 'aside', 'picking beside invokes callback')

/* =========================================================================
   5. RENDER ICONMENU WITH GROUPS INTO HTML VIA REACT-DOM/SERVER
   ========================================================================= */

const html = renderToStaticMarkup(React.createElement(IconMenu, { groups, label: 'Settings' }))

ok(html.includes('role="menu"'), 'renders root menu role')
ok(html.includes('Theme'), 'renders Theme column heading')
ok(html.includes('Activity'), 'renders Activity column heading')
ok(html.includes('Background'), 'renders Background column heading')
ok(html.includes('Surfaces'), 'renders Surfaces column heading')
ok(html.includes('Opening'), 'renders Opening column heading')
ok(html.includes('im-opacity-slider'), 'renders opacity slider in body')
ok(html.includes('data-item="theme-dark"'), 'renders theme items with data-item')
ok(html.includes('data-item="activity-retro-green"'), 'renders Activity look items with data-item')
ok(html.includes('aria-pressed="true"'), 'renders pressed state on active items')

/* =========================================================================
   6. ACTIVITY LOOKS ARE TOKEN-ONLY
   ========================================================================= */

const activityCss = readFileSync(fileURLToPath(new URL('../src/fluid/frame/bar.css', import.meta.url)), 'utf8')
for (const id of ['default', 'console', 'retro-green', 'modern', 'stylish', 'minimalist']) {
  const marker = `.im-act-swatch[data-activity-look='${id}']`
  const start = activityCss.indexOf(marker)
  ok(start >= 0, `${id} has an Activity token assignment`)
  const body = activityCss.slice(activityCss.indexOf('{', start) + 1, activityCss.indexOf('}', start))
  const declarations = body.split(';').map((line) => line.trim()).filter(Boolean)
  ok(declarations.length >= 10, `${id} supplies the complete Activity palette`)
  ok(declarations.every((line) => line.startsWith('--act-')), `${id} changes only --act-* tokens`)
}
ok(activityCss.includes('.fx-pop.fb-activity {'), 'Activity sheet consumes its palette in one shared rule')
ok(activityCss.includes('background: var(--act-sheet-bg)'), 'Activity sheet background consumes a token')

console.log(`fluid_look_unit: ok (${checks} checks passed)`)
