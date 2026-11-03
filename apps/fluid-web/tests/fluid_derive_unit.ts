/* derive(): a medium or compact screen's view of a page (Surface Tension P5,
 * plan §3.7 and §4 P5): with no record it is today's narrow order (the
 * column's conversation, the tree's leaves in tree order, then the floats
 * front first via narrowFloats, standIn for the conversation's own place);
 * a record's missing ids are placed by the rule, its unknown ids skipped;
 * derive never writes. state.ts reads the same rule. */
import assert from 'node:assert/strict'
import { DEFAULT_PLACE, derive, narrowFloats, standIn } from '../src/fluid/focus/narrowView'
import { CONVERSATION_ID, type Float } from '../src/fluid/focus/types'
import { keepSlot, zones, type Node, type Zone } from '../src/fluid/workspace/tree'
import type { Arr } from '../src/fluid/workspace/place'
import { orderIn, stateOf } from '../src/fluid/surface/state'
import type { DevicePlacement } from '../src/fluid/surface/types'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }

const z = (id: string): Zone => ({ type: 'zone', id, show: 'objects', name: id, slot: keepSlot() })
const conv = (): Zone => ({ type: 'zone', id: CONVERSATION_ID, show: 'conversation', name: 'Conversation' })
const row = (...kids: Node[]): Node => ({ type: 'split', dir: 'row', sizes: kids.map(() => 1 / kids.length), kids })
const col = (...kids: Node[]): Node => ({ type: 'split', dir: 'col', sizes: kids.map(() => 1 / kids.length), kids })
const fl = (zone: Zone, id = 'f-' + zone.id): Float => ({ id, zone, x: 0, y: 0, w: 300, h: 200 })
const dp = (order: string[], place: DevicePlacement['place'] = {}, level: DevicePlacement['level'] = {}): DevicePlacement => ({ order, place, level, updatedAt: 5 })
const deepFreeze = <T,>(o: T): T => { if (o && typeof o === 'object') { Object.values(o).forEach(deepFreeze); Object.freeze(o) } return o }

/* today's narrow order, written out the way the narrow screen draws it */
const todays = (a: Arr): string[] => {
  const s = standIn(a)
  const ids = [CONVERSATION_ID,
    ...zones(a.tree).map((x) => (x.show === 'conversation' ? s?.id : x.id)),
    ...narrowFloats(a).map((f) => (f.zone.show === 'conversation' ? s?.id : f.zone.id))]
  return [...new Set(ids.filter((x): x is string => !!x))]
}

/* 1. The desk: the conversation in its column, two sections, two windows. */
const desk: Arr = { tree: row(z('s1'), col(z('s2'), z('s3'))), pages: [], focus: { floats: [fl(z('w1')), fl(z('w2'))] } }
{
  const c = derive(desk, 'compact')
  eq(c.order, ['conv', 's1', 's2', 's3', 'w2', 'w1'], 'compact: the column, the leaves in tree order, the windows front first')
  eq(c.order, todays(desk), "which is today's narrow order")
  eq(c.place, { conv: 'stack', s1: 'stack', s2: 'stack', s3: 'stack', w1: 'stack', w2: 'stack' }, 'compact: all stack cards (as the narrow screen draws them)')
  eq([c.column, c.level], [CONVERSATION_ID, {}], 'the column shows the conversation; no level overrides')
  const m = derive(desk, 'medium')
  eq(m.order, c.order, 'medium has the same order')
  eq(m.place, { conv: 'dock', s1: 'dock', s2: 'dock', s3: 'dock', w1: 'sheet', w2: 'sheet' }, 'medium: sections docked, windows in the sheet')
  eq(DEFAULT_PLACE, {
    medium: { column: 'dock', leaf: 'dock', float: 'sheet', launcher: 'launcher' },
    compact: { column: 'stack', leaf: 'stack', float: 'stack', launcher: 'launcher' },
  }, 'the default place is one table (held open for the owner)')
}

/* 2. standIn: something else in the column; the conversation's own leaf shows it. */
{
  const a: Arr = { tree: row(conv(), z('s1')), pages: [], focus: { column: z('held'), floats: [fl(z('w1'))] } }
  eq(standIn(a)?.id, 'held', 'the column holds "held"')
  eq(derive(a, 'compact').order, ['conv', 'held', 's1', 'w1'], "the conversation's leaf is where its stand-in is listed")
  eq(derive(a, 'compact').order, todays(a), "which is today's narrow order")
  const fa: Arr = { tree: z('s1'), pages: [], focus: { column: z('held'), floats: [fl(z('w1')), fl(conv(), 'f-conv')] } }
  eq(derive(fa, 'compact').order, ['conv', 's1', 'held', 'w1'], "the conversation's window, front, is where its stand-in is listed")
  eq(derive(fa, 'medium').place.held, 'sheet', 'there it is a window: a sheet in medium')
  const stub: Arr = { tree: row(conv(), z('s1')), pages: [] }
  eq(derive(stub, 'compact').order, ['conv', 's1'], 'with nothing standing in, the conversation is the column only (its leaf is the stub)')
}

/* 3. Put away: the launcher. */
{
  const a: Arr = { tree: z('s1'), pages: [], focus: { minimized: { from: 'column', at: 1 } } }
  const d = derive(a, 'compact')
  eq([d.order, d.place.conv, d.column], [['conv', 's1'], 'launcher', null], 'the conversation put away stays put away; the column is not it')
}

/* 4. A record: its order for what is still here; missing ids placed by the rule; unknown skipped. */
{
  const rec = dp(['w1', 'gone', 's1'], { s2: 'sheet', gone: 'sheet', w2: 'launcher' }, { s3: 'compact', gone: 'icon' })
  const d = derive(desk, 'compact', rec)
  eq(d.order, ['conv', 'w1', 's1', 's2', 's3', 'w2'],
    "the record's order first; each missing id goes after the one it follows in today's order (conv first: it follows none)")
  eq([d.place.s2, d.place.w2, d.place.s1], ['sheet', 'launcher', 'stack'], "the record's places, else the default")
  eq(d.level, { s3: 'compact' }, "the record's level overrides")
  eq(['gone' in d.place, 'gone' in d.level, d.order.includes('gone')], [false, false, false], 'an id the page no longer has is skipped')
  const docked = derive(desk, 'compact', dp([], { s1: 'dock' }))
  eq(docked.place.s1, 'stack', '"dock" in a compact record is not a compact place: the default is used')
  eq(derive(desk, 'medium', dp([], { s1: 'dock', w1: 'stack' })).place, { conv: 'dock', s1: 'dock', s2: 'dock', s3: 'dock', w1: 'stack', w2: 'sheet' }, 'medium: the record places a window in the stack')
  eq(derive(desk, 'compact', dp(['w2', 's1', 's1'])).order, ['conv', 'w2', 'w1', 's1', 's2', 's3'],
    'a repeated id in the record is read once; w1, missing, follows w2 as it does today')
}

/* 5. derive never writes. */
{
  const a = deepFreeze(JSON.parse(JSON.stringify(desk)) as Arr)
  const rec = deepFreeze(dp(['w1'], { s1: 'sheet' }, { s2: 'expanded' }))
  const before = JSON.stringify([a, rec])
  derive(a, 'compact', rec)
  derive(a, 'medium', rec)
  derive(a, 'compact')
  eq(JSON.stringify([a, rec]), before, 'the page and the record are byte-identical after derive (and frozen throughout)')
}

/* 6. state.ts reads the same rule: the stack order and a window's place. */
{
  eq(orderIn(desk), derive(desk, 'compact').order, "orderIn is derive's order")
  eq(orderIn(desk, dp(['w1'])), derive(desk, 'compact', dp(['w1'])).order, 'with a record too')
  eq(stateOf(desk, 'w1', 'compact')!.placement.kind, 'stack', 'a window reads as a stack card in compact')
  eq(stateOf(desk, 'w1', 'medium')!.placement.kind, 'sheet', 'and as a sheet in medium')
  eq(stateOf(desk, 's2', 'compact')!.placement, { kind: 'stack', index: 2 }, "a section's stack index is its place in derive's order")
}

console.log(`fluid derive: ${checks} checks passed`)
