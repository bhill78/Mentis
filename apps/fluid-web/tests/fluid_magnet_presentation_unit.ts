import assert from 'node:assert/strict'
import { MAGNET_THEME_LOOK, magnetLook, readMagnetTheme, summaryPresence } from '../src/fluid/surface/magnet/presentation'

let checks = 0
const eq = (actual: unknown, expected: unknown, message: string) => { assert.deepEqual(actual, expected, message); checks++ }

eq(Object.keys(MAGNET_THEME_LOOK), ['minimal', 'anchored', 'glass', 'floating'], 'all four existing theme names have defaults')
eq(magnetLook({ presentation: { renderer: 'disc', theme: 'glass' } }, null).appearance,
  { panel: 'tinted', content: 'tinted', opacity: 1 }, 'glass maps to Fluid Look')
eq(magnetLook({ presentation: { renderer: 'disc', theme: 'anchored' } }, { content: 'solid', opacity: 0.35 }).appearance,
  { panel: 'solid', content: 'solid', opacity: 0.35 }, 'placement Look overrides the theme property by property')
eq(magnetLook({ presentation: { renderer: 'disc', theme: 'floating' } }, { panel: 'bogus', opacity: 2 }).appearance,
  { panel: 'transparent', content: 'tinted', opacity: 1 }, 'bad placement fields are ignored and opacity uses Fluid clamping')
eq(readMagnetTheme({ presentation: { renderer: 'disc' } }), { state: 'absent' }, 'P0 without theme remains valid')
eq(readMagnetTheme({ presentation: { renderer: 'disc', theme: 'future' } }).state, 'unavailable', 'an unknown theme is unavailable, never guessed')

eq(summaryPresence([{ activity: 12, participants: 3 }, { activity: 20, participants: [{ alias: 'Ada' }, { name: 'Ben' }], workers: [{ alias: 'Ada' }] }]),
  { activity: 20, participants: 5, working: 1, names: ['Ada', 'Ben'] }, 'existing summary signals are bounded and de-duplicated')
eq(summaryPresence([{ participants: 'many', workers: null }, null]),
  { activity: null, participants: null, working: null, names: [] }, 'absent or malformed M1 fields stay unavailable')

console.log(`fluid magnet presentation unit: ${checks} checks passed`)
