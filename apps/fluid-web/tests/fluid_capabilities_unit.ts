import assert from 'node:assert/strict'
import { CONVERSATION_ID } from '../src/fluid/focus/types'
import { keepSlot, type Zone } from '../src/fluid/workspace/tree'
import {
  DECLARED, capabilitiesOf, intersect, placementsIn, resourceCapabilitiesOf, spatialIn, surfaceKindOf,
} from '../src/fluid/surface/capabilities'
import { fitOfLevel, levelOfFit, levelOfWidth, levelShown, stepLevel } from '../src/fluid/surface/levels'
import { sizeOf, type Fit } from '../src/fluid/present/size'
import { Holder } from '../src/fluid/workspace/place'
import { LEVELS, SURFACE_KINDS, type Level, type Placement, type ResourceCapabilities } from '../src/fluid/surface/types'
import { presentationClass } from '../src/fluid/frame/narrow'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }

const section: Zone = { type: 'zone', id: 's', show: 'objects', name: 'S', slot: keepSlot() }
const conv: Zone = { type: 'zone', id: CONVERSATION_ID, show: 'conversation', name: 'Conversation' }
const magnet: Zone = { type: 'zone', id: 'mag-1', show: 'magnet', options: { magnet: 'mag-1' } }
const run: Zone = { type: 'zone', id: 'run-1', show: 'run', options: { run: 'r', who: 'A' } }
const dock: Placement = { kind: 'dock', in: 'tree', page: null }
const float: Placement = { kind: 'float', floatId: 'f', rect: { x: 0, y: 0, w: 300, h: 200 } }

/* ---- The kind: content first, then placement. ---- */
eq(surfaceKindOf(section, dock), 'section', 'a docked zone is a section')
eq(surfaceKindOf(section, float), 'float', 'the same zone floating is a float')
eq(surfaceKindOf(section, { kind: 'launcher' }), 'launcher-tile', 'in the launcher, a tile')
eq(surfaceKindOf(section, { kind: 'nested', parent: 'p' }), 'nested-card', 'nested, a card')
eq(surfaceKindOf(section, { kind: 'page-root', page: 'p1' }), 'page-panel', 'a Page root, a Page panel')
for (const where of [dock, float, { kind: 'launcher' } as Placement]) eq(surfaceKindOf(conv, where), 'conversation', `the conversation is itself ${where.kind}`)
eq(surfaceKindOf(magnet, float), 'magnet', 'a magnet is itself wherever it is')
eq(Object.keys(DECLARED).sort(), [...SURFACE_KINDS].sort(), 'every kind is declared')

/* ---- The intersection rule. ---- */
const narrowRes: ResourceCapabilities = { ...resourceCapabilitiesOf(section), levels: new Set<Level>(['compact', 'standard', 'expanded']), minBy: { standard: { w: 500, h: 100 }, expanded: { w: 100, h: 900 } } }
const both = intersect(DECLARED.float, narrowRes)
eq([...both.levels], ['compact', 'standard', 'expanded'], 'levels are those both allow')
eq(both.size.min.standard, { w: 500, h: 140 }, 'each level’s minimum is the larger of the two, per axis')
eq(both.size.min.expanded, { w: 360, h: 900 }, 'on both axes')
eq(both.size.min.icon, DECLARED.float.size.min.icon, 'a level the resource says nothing of keeps the kind’s minimum')
eq([...intersect(DECLARED['page-panel'], narrowRes).levels], ['standard', 'expanded'], 'a narrower kind narrows the resource')
eq([...intersect(DECLARED['launcher-tile'], narrowRes).levels], [], 'nothing both allow is nothing')
ok(capabilitiesOf(section, dock).canFollow, 'a section with a slot can follow')
eq(capabilitiesOf(run, dock).canFollow, false, 'a zone with no slot has nothing to follow with')
eq(capabilitiesOf(section, float).canFollow, false, 'a float does not follow in this build')
eq(capabilitiesOf(conv, float).maxInstances, 1, 'the conversation is one')
eq(capabilitiesOf(conv, float).yield, 'never', 'and is never displaced')
eq(capabilitiesOf(section, dock).yield, 'never', 'a docked section is ground')
eq(resourceCapabilitiesOf(conv).holdsWorkingState, true, 'the conversation holds a draft')

/* ---- placementsBy: no float in medium or compact, for any kind; no dock in compact. ---- */
for (const k of SURFACE_KINDS) {
  ok(!DECLARED[k].placementsBy.medium.has('float') && !DECLARED[k].placementsBy.compact.has('float'), `${k}: no float outside wide`)
  ok(!DECLARED[k].placementsBy.compact.has('dock'), `${k}: no dock in compact`)
  ok(![...DECLARED[k].placementsBy.wide].some((p) => p === 'stack' || p === 'sheet'), `${k}: no stack or sheet in wide`)
}
eq([...placementsIn(capabilitiesOf(section, dock), 'wide')], ['dock', 'float'], 'a section in wide docks or floats')
eq([...placementsIn(capabilitiesOf(conv, dock), 'wide')], ['dock', 'float', 'launcher'], 'the conversation also goes to the launcher')
eq([...placementsIn(capabilitiesOf(section, dock), 'compact')], ['stack', 'sheet', 'launcher'], 'compact stacks')

/* ---- snap, yield and movement are read in wide only. ---- */
const fl = capabilitiesOf(section, float)
eq(spatialIn(fl, 'wide'), { movement: 'free', yield: 'slide', snap: true }, 'wide reads them as declared')
for (const cls of ['medium', 'compact'] as const) eq(spatialIn(fl, cls), { movement: 'fixed', yield: 'never', snap: false }, `${cls} ignores them`)
eq(spatialIn(capabilitiesOf(magnet, float), 'compact').yield, 'never', 'a magnet does not fold aside in compact')

/* ---- Levels from size.ts, losslessly. ---- */
const fits: Fit[] = ['fallback', 'compact', 'medium', 'large']
eq(fits.map(levelOfFit), [...LEVELS], 'each fit is one level, in order')
for (const f of fits) eq(fitOfLevel(levelOfFit(f)), f, `${f} round-trips`)
for (const l of LEVELS) eq(levelOfFit(fitOfLevel(l)), l, `${l} round-trips`)
for (const w of [0, 120, 299, 300, 599, 600, 1600]) eq(fitOfLevel(levelOfWidth(w)), sizeOf(w), `a box ${w} wide is size.ts's band`)
eq(stepLevel('standard', 1, new Set(LEVELS)), 'expanded', 'Expand steps up')
eq(stepLevel('standard', -1, new Set<Level>(['icon', 'standard'])), 'icon', 'Collapse skips what is not supported')
eq(stepLevel('expanded', 1, new Set(LEVELS)), null, 'nothing past expanded')
eq(stepLevel('icon', -1, new Set(LEVELS)), null, 'nothing below icon')
eq(levelShown({ auto: 'standard', override: 'compact' }), 'compact', 'the override wins until Reset size')

/* ---- place.ts reads the class by narrow.ts's rule (it cannot import it: a cycle). ---- */
const holder = new Holder(() => ({ tree: section, pages: [] }))
for (const w of [2560, 1025, 1024, 900, 761, 760, 320]) {
  ;(globalThis as { innerWidth?: number }).innerWidth = w
  eq(holder.surfaceCtx({ page: null }).cls, presentationClass(w), `a window ${w} wide is ${presentationClass(w)} to the Holder too`)
}
delete (globalThis as { innerWidth?: number }).innerWidth

console.log(`fluid capabilities: ${checks} checks passed`)
