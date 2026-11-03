import assert from 'node:assert/strict'
import { MAGNET_THEME_LOOK, magnetLook, readMagnetTheme, summaryCardPlacement, summaryPresence } from '../src/fluid/surface/magnet/presentation'

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

eq(summaryPresence([
  { activity: 12, participants: [{ id: 'p1', alias: 'Ada' }, { name: 'Ben' }], workers: [{ id: 'p1', alias: 'Ada' }] },
  { activity: 20, participants: [{ id: 'p1', name: 'Ada Lovelace' }, { name: 'Ben' }], workers: [{ id: 'p1', name: 'Ada Lovelace' }] },
]), {
  activity: 20, participants: 2, working: 1,
  participantNames: ['Ada', 'Ben'], participantNamesMore: 0,
  workerNames: ['Ada'], workerNamesMore: 0,
}, 'participants and workers are de-duplicated across sources without mixing roles')
eq(summaryPresence([{ participants: 'many', workers: null }, null]),
  { activity: null, participants: null, working: null, participantNames: [], participantNamesMore: 0, workerNames: [], workerNamesMore: 0 },
  'absent or malformed M1 fields stay unavailable')
eq(summaryPresence([
  { participants: ['Ada', 'Ben', 'Cy', 'Dee', 'Eve', null, 3, {}], workers: 4 },
  { participants: ['Ada', 'Ben'], workers: 2 },
]), {
  activity: null, participants: 5, working: 4,
  participantNames: ['Ada', 'Ben', 'Cy', 'Dee'], participantNamesMore: 1,
  workerNames: [], workerNamesMore: 0,
}, 'malformed people are ignored, display caps are explicit, and anonymous source counts are not summed')

eq(summaryCardPlacement({ left: 40, top: 30 }, { width: 1000, height: 800 }, { width: 320, height: 460 }, 56),
  { x: 28, y: 28, flipX: false, flipY: false, width: 320, height: 460 },
  'a normal card opens from the disc centre when every edge fits')
eq(summaryCardPlacement({ left: 900, top: 700 }, { width: 1000, height: 800 }, { width: 320, height: 460 }, 56),
  { x: -292, y: -432, flipX: true, flipY: true, width: 320, height: 460 },
  'a flipped card opens back from the disc centre when every edge fits')
eq(summaryCardPlacement({ left: 100, top: 300 }, { width: 400, height: 768 }, { width: 320, height: 460 }, 56),
  { x: -92, y: -292, flipX: true, flipY: true, width: 320, height: 460 },
  'a card near central edges is clamped wholly inside the viewport')
eq(summaryCardPlacement({ left: -20, top: -30 }, { width: 300, height: 240 }, { width: 320, height: 460 }, 56),
  { x: 28, y: 38, flipX: false, flipY: false, width: 284, height: 224 },
  'an undersized viewport bounds card size and normal placement at every edge')

console.log(`fluid magnet presentation unit: ${checks} checks passed`)
