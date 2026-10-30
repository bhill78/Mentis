import assert from 'node:assert/strict'
import { createElement } from 'react'
import { renderToString } from 'react-dom/server'
import * as surface from '../src/fluid/surface/types'
import * as actions from '../src/fluid/surface/actions/types'
import * as magnet from '../src/fluid/surface/magnet/types'
import { VIEW_RESOURCES, forgetSurface, viewState, useViewState } from '../src/fluid/surface/viewState'
import { transition } from '../src/fluid/surface/transition'
import { presentationClass } from '../src/fluid/frame/narrow'
import type { SurfaceCtx } from '../src/fluid/surface/types'
import type {
  CreateMagnetFn, MagnetAttach, MagnetConfig, MagnetConfigChange, MagnetId, MagnetSeed, NewZonePlacement, ReconfigureFn,
} from '../src/fluid/surface/magnet/types'

/* Compile-time contract (§3.10), checked by `tsc -p tsconfig.test.json` in npm test:
 * a mismatch here fails the type check, not the run. */
type Equal<A, B> = (<T>() => T extends A ? 1 : 2) extends (<T>() => T extends B ? 1 : 2) ? true : false
const isTrue = <T extends true>(t: T) => t
isTrue<Equal<MagnetId, MagnetConfig['id']>>(true)
isTrue<Equal<Parameters<CreateMagnetFn>[1], MagnetAttach>>(true)
isTrue<Equal<NonNullable<Parameters<CreateMagnetFn>[2]>, { id?: MagnetId }>>(true)
isTrue<Equal<Parameters<ReconfigureFn>[0], MagnetId>>(true)
// A complete seed is structurally a change, so "not a seed" is the parameter being exactly MagnetConfigChange.
isTrue<Equal<Parameters<ReconfigureFn>[1], MagnetConfigChange>>(true)
// @ts-expect-error reconfigure takes a change, not MagnetConfigChange | MagnetSeed
isTrue<Equal<Parameters<ReconfigureFn>[1], MagnetConfigChange | MagnetSeed>>(true)
isTrue<Equal<NewZonePlacement['place'], 'stack' | 'sheet' | 'launcher' | 'dock'>>(true)
const seed = {} as MagnetSeed
const attach = { zone: { type: 'zone', id: 'mag-a', show: 'magnet', options: { magnet: 'mag-a' } } } satisfies MagnetAttach
void ((create: CreateMagnetFn) => create(seed, attach, { id: 'mag-a' }))
// @ts-expect-error a magnet id is a mag- id
void ((create: CreateMagnetFn) => create(seed, attach, { id: 'conversation-1' }))
void ((reconfigure: ReconfigureFn) => reconfigure('mag-a', { presentation: { renderer: 'ring' } }))
// @ts-expect-error a change never carries an id
void ((reconfigure: ReconfigureFn) => reconfigure('mag-a', { id: 'mag-b' }))
void ({ place: 'sheet', level: 'compact', index: 0 } satisfies NewZonePlacement)
// @ts-expect-error a new zone's placement has no order
void ({ place: 'sheet', order: [] } satisfies NewZonePlacement)
// @ts-expect-error a new zone's placement has no updatedAt
void ({ place: 'sheet', updatedAt: 0 } satisfies NewZonePlacement)

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const unique = (list: readonly string[], what: string) => eq(new Set(list).size, list.length, what + ' has no repeats')

/* Every runtime companion of the contract's types is there, in the plan's words. */
eq(surface.LEVELS, ['icon', 'compact', 'standard', 'expanded'], 'the four levels')
eq(surface.PRESENTATION_CLASSES, ['wide', 'medium', 'compact'], 'the three presentation classes')
eq(surface.INPUT_MODES, ['fine', 'coarse'], 'the two input modes')
eq(surface.SURFACE_KINDS.length, 9, 'nine surface kinds')
eq(surface.PLACEMENT_KINDS, ['dock', 'float', 'launcher', 'nested', 'page-root', 'stack', 'sheet'], 'placement kinds')
eq(surface.CHANGE_PROPS.length, 10, 'ten change properties')
eq(surface.SURFACE_VERBS.length, 25, 'twenty-five surface verbs')
eq(surface.UNAVAILABLE_CODES, ['source', 'permission', 'connector', 'runtime', 'scope', 'limit', 'state'], 'unavailability codes')
eq(surface.DEVICE_PLACES, ['stack', 'sheet', 'launcher', 'dock'], 'device placements')
eq(surface.MAKE_ROOM, ['off', 'drag', 'expand'], 'Make room settings')
eq(actions.SHARED_VERBS.length, 50, 'fifty shared verbs')
eq(actions.RESERVED_VERBS, ['push', 'pull', 'compare', 'group', 'ungroup'], 'reserved verbs')
eq(actions.SPECIFIC_IDS.length, 28, 'twenty-eight specific actions')
eq(actions.ACTION_GROUPS, ['resource', 'view', 'arrange', 'look', 'share', 'details'], 'the fixed group order')
eq(magnet.MAGNET_SOURCE_KINDS, ['brain', 'conversation', 'connector', 'web', 'other'], 'magnet source kinds')
eq(magnet.INFORMATION_TYPES.length, 7, 'seven information types')
eq(magnet.COLLECTION_MODES, ['one-time', 'scheduled', 'continuous', 'paused'], 'collection modes')
eq(magnet.SYNTHESIS_MODES, ['manual', 'scheduled', 'on-new-information'], 'synthesis modes')
eq(magnet.RENDERERS, ['disc', 'ring', 'cards', 'list', 'gallery'], 'renderers')
eq(magnet.MAGNET_CAPABILITIES.length, 9, 'nine magnet capabilities')
eq(magnet.MAGNET_BOUNDS.configs, 50, 'fifty configs per arrangement')
eq(magnet.NEW_ZONE_PLACEMENT_FIELDS, ['place', 'level', 'index'], "a new zone's placement is its own entry only")
for (const f of ['order', 'updatedAt'] as const)
  eq((magnet.NEW_ZONE_PLACEMENT_FIELDS as readonly string[]).includes(f), false, f + ' is not part of a new zone placement')
const sheet: NewZonePlacement = { place: 'sheet', level: 'compact', index: 0 }
eq(surface.DEVICE_PLACES.includes(sheet.place) && surface.LEVELS.includes(sheet.level!), true, 'its place and level are the device record\'s')
for (const [name, list] of Object.entries({ ...surface, ...actions, ...magnet })) if (Array.isArray(list)) unique(list, name)

/* Full screen, Exit full screen and Reopen are shared verbs (R1). */
for (const v of ['fullscreen', 'exitFullscreen', 'reopen', 'close', 'removeFromWorkspace'] as const) {
  eq(actions.SHARED_VERBS.includes(v), true, v + ' is a shared verb')
  eq((surface.SURFACE_VERBS as readonly string[]).includes(v), true, v + ' is a surface verb')
}
/* Every surface verb is a shared verb; no reserved verb is. */
for (const v of surface.SURFACE_VERBS) eq((actions.SHARED_VERBS as readonly string[]).includes(v), true, v + ' is shared')
for (const v of actions.RESERVED_VERBS) eq((actions.SHARED_VERBS as readonly string[]).includes(v), false, v + ' is reserved')

/* presentationClass: wide above 1024, medium 761–1024, compact 760 and below. */
eq(presentationClass(1025), 'wide', '1025 is wide')
eq(presentationClass(1024), 'medium', '1024 is medium')
eq(presentationClass(761), 'medium', '761 is medium')
eq(presentationClass(760), 'compact', '760 is compact')
eq(presentationClass(320), 'compact', '320 is compact')
eq(presentationClass(2560), 'wide', '2560 is wide')

/* The transition stub says it is a stub. */
assert.throws(() => transition({} as SurfaceCtx, 'z', { prop: 'front' }), /not implemented/); checks++

/* View state: per (surface, resource), the last 8 resources per surface. */
eq(typeof useViewState, 'function', 'the hook is there')
const at = (resource: string) => ({ surface: 's1', resource })
eq(viewState(at('r0'), 'scroll'), undefined, 'nothing held yet')
/* The hook's setter is its only writer: drive it through a server render (no DOM). */
const write = (resource: string, v: number) => {
  let seen: number | undefined
  function Probe() { const [now, set] = useViewState<number>(at(resource), 'scroll', 0); seen = now; set(v); return null }
  renderToString(createElement(Probe))
  return seen
}
eq(write('r0', 40), 0, 'the initial value until something is held')
eq(write('r0', 41), 40, 'then what was held')
write('r0', 40)
eq(viewState(at('r0'), 'scroll'), 40, 'held for its surface and resource')
eq(viewState({ surface: 's2', resource: 'r0' }, 'scroll'), undefined, 'another surface holds its own')
for (let i = 1; i <= VIEW_RESOURCES; i++) write('r' + i, i)
eq(viewState(at('r0'), 'scroll'), undefined, 'the oldest of nine resources is forgotten')
eq(viewState(at('r1'), 'scroll'), 1, 'the other eight are kept')
forgetSurface('s1')
eq(viewState(at('r8'), 'scroll'), undefined, 'Remove from workspace forgets the surface')

console.log(`fluid_surface_contract_unit: ${checks} checks passed`)
