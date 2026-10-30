/* THE TWO r5 D8 STEP 1 CONTRACT TESTS (Surface Tension P5, plan §4 P5 and
 * owner correction 2):
 *
 *  (a) every Change whose outcome is layer 'device', run in medium and in
 *      compact over a fixture with a tree, three floats, the conversation and
 *      a lens, leaves JSON.stringify(wideFieldsOf(arr)) byte-identical;
 *  (b) every device-placement verb is layer 'device' and changes only this
 *      class's record (the other class's is byte-identical); Close/Reopen
 *      change only the device-local closed set; every shared verb is layer
 *      'shared' and changes no record and no closed set.
 *
 * Both are proved at the pure transition() and again through the Holder
 * (workspace.apply), comparing serialised bytes, never object identity
 * alone. Then a compact Save is shown to be scoped: it sends this class's
 * record and nothing of the wide arrangement. */
import assert from 'node:assert/strict'
import { CONVERSATION_ID, type Float } from '../src/fluid/focus/types'
import { Holder, toLayout, type Arr } from '../src/fluid/workspace/place'
import { followSlot, keepSlot, zones, type Node, type Zone } from '../src/fluid/workspace/tree'
import { capsFor, transition } from '../src/fluid/surface/transition'
import type { Change, DevicePlacement, PresentationClass, SurfaceCtx } from '../src/fluid/surface/types'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const same = (a: unknown, b: unknown, what: string) => { assert.equal(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }

const z = (id: string, slot = keepSlot()): Zone => ({ type: 'zone', id, show: 'objects', name: id, slot })
const row = (sizes: number[], kids: Node[]): Node => ({ type: 'split', dir: 'row', sizes, kids })
const fl = (zone: Zone, x: number): Float => ({ id: 'f-' + zone.id, zone, x, y: 40, w: 300, h: 200 })
const dp = (order: string[], place: DevicePlacement['place'], level: DevicePlacement['level'] = {}, updatedAt = 7): DevicePlacement =>
  ({ order, place, level, updatedAt })

/** The fixture: a tree of two sections, three windows, the conversation in
 *  its column, a Page, a look, boundaries, and both narrower records. */
const fixture = (): Arr => ({
  tree: row([0.4, 0.6], [z('s1'), z('s2', followSlot())]),
  pages: [{ id: 'p1', title: 'Page', tree: z('pp') }],
  conversation: { width: 480, replies: 300 },
  appearance: { panel: 'tinted', content: 'solid', opacity: 0.6 } as Arr['appearance'],
  focus: { floats: [fl(z('w1'), 10), fl(z('w2'), 60), fl(z('w3'), 110)], previous: ['s1'] },
})
const RECORDS = (): { medium: DevicePlacement; compact: DevicePlacement } => ({
  medium: dp(['s2', 'w1'], { w1: 'sheet', s1: 'dock' }, { s2: 'expanded' }),
  compact: dp(['w3', 's1'], { w2: 'launcher' }, { w1: 'compact' }),
})
/** Every wide field of an arrangement, as a full save would write it:
 *  everything but the narrower classes' records. */
const wideFieldsOf = (a: Arr): Record<string, unknown> => { const { presentations: _p, ...rest } = toLayout(a) as Record<string, unknown>; return rest }
const bytes = (v: unknown) => JSON.stringify(v)

const IDS = ['s1', 's2', 'w1', 'w2', 'w3', CONVERSATION_ID]
const CHANGES: Change[] = [
  { prop: 'placement', to: { kind: 'float' } }, { prop: 'placement', to: { kind: 'dock' } }, { prop: 'placement', to: { kind: 'column' } },
  { prop: 'placement', to: { kind: 'launcher' } }, { prop: 'placement', to: { kind: 'back' } },
  { prop: 'placement', to: { kind: 'stack' } }, { prop: 'placement', to: { kind: 'stack', index: 0 } }, { prop: 'placement', to: { kind: 'sheet' } },
  { prop: 'rect', rect: { x: 1, y: 2, w: 300, h: 300 } }, { prop: 'front' },
  { prop: 'level', to: 'compact' }, { prop: 'level', to: 'icon' }, { prop: 'level', to: 'expanded' }, { prop: 'level', step: 1 }, { prop: 'level', step: -1 }, { prop: 'level', to: 'reset' },
  { prop: 'emphasis', to: 'lens' }, { prop: 'emphasis', to: 'fullscreen' }, { prop: 'emphasis', to: 'none' },
  { prop: 'binding', to: 'follow' }, { prop: 'binding', to: 'hold' },
  { prop: 'primary', on: true }, { prop: 'primary', on: false },
  { prop: 'order', to: 0 }, { prop: 'order', to: 3 },
  { prop: 'open', to: false }, { prop: 'open', to: true },
  { prop: 'exists', to: false },
]
/** What each kind of change is, by the plan's layering (§3.2, §3.3 rules 3-4). */
const DEVICE_PLACEMENT = new Set<Change['prop']>(['placement', 'level', 'order'])
const SHARED = new Set<Change['prop']>(['binding', 'primary', 'exists'])

const ctxOf = (arr: Arr, cls: PresentationClass, device: DevicePlacement | undefined, closed: string[], emphasis: SurfaceCtx['session']['emphasis']): SurfaceCtx => ({
  arr, page: null, cls, ...(device ? { device } : {}), deviceLocal: { closed: new Set(closed) },
  session: { emphasis }, viewport: { w: 1280, h: 800 }, caps: capsFor(arr, null, cls, device),
})

/* ---- (a) and (b) at transition(): medium and compact, with a lens on s2. ---- */
let deviceOutcomes = 0, sharedOutcomes = 0, localOutcomes = 0
for (const cls of ['medium', 'compact'] as const) for (const id of IDS) for (const change of CHANGES) {
  const arr = fixture()
  const records = RECORDS()
  const wideBefore = bytes(wideFieldsOf(arr))
  const rawBefore = bytes(arr)
  const reopening = change.prop === 'open' && change.to
  const out = transition(ctxOf(arr, cls, records[cls], reopening ? [id] : [], { s2: 'lens', ...(change.prop === 'emphasis' && change.to === 'none' ? { [id]: 'fullscreen' } : {}) }), id, change)
  const tag = `${cls} ${id} ${JSON.stringify(change)}`
  if (!out.ok) { ok(out.reason.length > 0, `${tag}: refused with a reason`); continue }
  /* the input is never written, whatever the layer */
  same(bytes(arr), rawBefore, `${tag}: the arrangement passed in is unchanged`)
  same(bytes(records), bytes(RECORDS()), `${tag}: the records passed in are unchanged`)
  if (out.layer === 'device') {
    deviceOutcomes++
    /* (a) */
    same(bytes(wideFieldsOf(out.arr)), wideBefore, `${tag}: (a) wide fields byte-identical after a device outcome`)
    same(bytes(out.arr), rawBefore, `${tag}: (a) and the whole arrangement it returns too`)
  }
  /* (b) */
  if (DEVICE_PLACEMENT.has(change.prop)) {
    eq([out.layer, !!out.device, out.deviceLocal], ['device', true, undefined], `${tag}: (b) a device-placement verb writes only this class's record`)
  } else if (change.prop === 'open') {
    localOutcomes++
    eq([out.layer, out.device, !!out.deviceLocal], ['device', undefined, true], `${tag}: (b) Close/Reopen write only the device-local closed set`)
    eq([...out.deviceLocal!.closed].includes(id), !change.to, `${tag}: (b) and it is ${change.to ? 'reopened' : 'closed'} there`)
  } else if (SHARED.has(change.prop)) {
    sharedOutcomes++
    eq([out.layer, out.device, out.deviceLocal], ['shared', undefined, undefined], `${tag}: (b) a shared verb is layer shared, with no record and no closed set`)
  } else {
    eq([out.layer, out.device, out.deviceLocal], ['session', undefined, undefined], `${tag}: emphasis is this tab's only`)
  }
}
ok(deviceOutcomes >= 60, `(a) was exercised on many device outcomes (${deviceOutcomes})`)
ok(sharedOutcomes >= 6 && localOutcomes >= 12, `(b) shared (${sharedOutcomes}) and Close/Reopen (${localOutcomes}) were exercised`)

/* ---- wide: placement and level are shared there, and never touch a record. ---- */
for (const id of IDS) for (const change of CHANGES) {
  const arr = fixture()
  const out = transition(ctxOf(arr, 'wide', undefined, change.prop === 'open' && change.to ? [id] : [], {}), id, change)
  if (!out.ok) continue
  if (change.prop === 'open') eq([out.layer, out.device], ['device', undefined], `wide ${id} ${JSON.stringify(change)}: Close is device-local in wide too`)
  else if (out.layer === 'shared') eq([out.device, out.deviceLocal], [undefined, undefined], `wide ${id} ${JSON.stringify(change)}: a shared outcome writes no record`)
}

/* ---- (a) and (b) again, through the Holder: what is kept, byte for byte. ---- */
const local = () => { const m = new Map<string, string>(); return { store: () => ({ getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => { m.set(k, v) }, removeItem: (k: string) => { m.delete(k) } }), brain: async () => 'brain-1', m } }
let holderRuns = 0
for (const cls of ['wide', 'medium', 'compact'] as const) for (const id of IDS) for (const change of CHANGES) {
  if (change.prop === 'emphasis') continue                          // the lens module's, and this tab's (covered above)
  const h = new Holder(() => ({ tree: z('start'), pages: [] }), { local: local() })
  h.arr = fixture()
  h.devices = RECORDS()
  const others = (['wide', 'medium', 'compact'] as const).filter((c) => c !== cls)
  /* each class has something closed already (not a surface the loop moves) */
  h.closed = { wide: new Set(['x-wide']), medium: new Set(['x-medium']), compact: new Set(['x-compact']) }
  if (change.prop === 'open' && change.to) h.closed = { ...h.closed, [cls]: new Set([id]) }
  const before = { wide: bytes(wideFieldsOf(h.arr)), raw: bytes(h.arr), medium: bytes(h.devices.medium), compact: bytes(h.devices.compact),
    closed: Object.fromEntries((['wide', 'medium', 'compact'] as const).map((c) => [c, bytes([...h.closed[c]])])) }
  const out = h.apply(id, change, { page: null, cls, viewport: { w: 1280, h: 800 } })
  const tag = `Holder ${cls} ${id} ${JSON.stringify(change)}`
  if (!out.ok) continue
  holderRuns++
  const otherRecords = (['medium', 'compact'] as const).filter((c) => c !== cls)
  if (out.layer === 'device' && change.prop !== 'open') {
    same(bytes(wideFieldsOf(h.arr)), before.wide, `${tag}: (a) the kept arrangement's wide fields are byte-identical`)
    same(bytes(h.arr), before.raw, `${tag}: (a) and so is the whole kept arrangement`)
    for (const c of otherRecords) same(bytes(h.devices[c]), before[c], `${tag}: (b) the ${c} record is byte-identical`)
    ok(bytes(h.devices[cls as 'medium' | 'compact']) !== before[cls as 'medium' | 'compact'], `${tag}: (b) only this class's record changed`)
    for (const c of ['wide', 'medium', 'compact'] as const) same(bytes([...h.closed[c]]), before.closed[c], `${tag}: no closed set changed`)
  } else if (change.prop === 'open') {
    same(bytes(h.arr), before.raw, `${tag}: (b) Close/Reopen leave the arrangement byte-identical`)
    eq([bytes(h.devices.medium), bytes(h.devices.compact)], [before.medium, before.compact], `${tag}: (b) and both records`)
    for (const c of others) same(bytes([...h.closed[c]]), before.closed[c], `${tag}: (b) and the ${c} closed set`)
    ok(bytes([...h.closed[cls]]) !== before.closed[cls], `${tag}: (b) only this class's closed set changed`)
  } else {
    same(out.layer, 'shared', `${tag}: what is not device or session is shared`)
    eq([bytes(h.devices.medium), bytes(h.devices.compact)], [before.medium, before.compact], `${tag}: (b) a shared verb changes no record`)
    for (const c of ['wide', 'medium', 'compact'] as const) same(bytes([...h.closed[c]]), before.closed[c], `${tag}: (b) and no closed set`)
  }
}
ok(holderRuns > 60, `the Holder ran many of them (${holderRuns})`)

/* ---- A compact Save is scoped: this class's record, nothing wide. ---- */
{
  type Call = { url: string; method: string; body: Record<string, unknown> | null }
  const calls: Call[] = []
  const stored = { ...toLayout(fixture()), presentations: RECORDS() }
  ;(globalThis as any).fetch = async (url: string, init?: RequestInit) => {
    const method = (init?.method ?? 'GET').toUpperCase()
    const body = init?.body ? JSON.parse(String(init.body)) : null
    calls.push({ url: String(url), method, body })
    const reply = String(url).endsWith('/layouts') ? { layouts: [], defaults: { home: null, conversation: null, unnamed: null } }
      : method === 'GET' ? { layout: stored, saved: 100 }
      : body.layout ? { saved: 101, layout: { ...body.layout, presentations: stored.presentations } }
      : { saved: 101, layout: { ...stored, presentations: { ...stored.presentations, [body.scope]: body.presentation } } }
    return new Response(JSON.stringify(reply), { status: 200, headers: { 'Content-Type': 'application/json' } })
  }
  const flush = async () => { for (let i = 0; i < 6; i++) await new Promise((r) => setTimeout(r, 0)) }
  const h = new Holder(() => ({ tree: z('start'), pages: [] }), { local: local() })
  h.enter('c-scoped', 'conversation')
  await flush()
  eq(h.devices, RECORDS(), 'the records the Brain keeps are this tab\'s on arrival')
  same(h.changed(), false, 'and the place reads as saved')
  /* a wide edit left unsaved, then a phone reorder */
  h.edit((a) => ({ ...a, conversation: { width: 999 } }))
  const wideTab = bytes(wideFieldsOf(h.arr))
  const moved = h.apply('s2', { prop: 'order', to: 0 }, { page: null, cls: 'compact' })
  ok(moved.ok, 'a phone reorder applies')
  same(bytes(wideFieldsOf(h.arr)), wideTab, 'it left the wide arrangement byte-identical')
  same(bytes(h.devices.medium), bytes(RECORDS().medium), 'and the tablet record')
  await h.save('compact')
  const sent = calls.filter((c) => c.method === 'POST').at(-1)!
  eq(Object.keys(sent.body!).sort(), ['op', 'presentation', 'scope'], 'a phone Save is a scoped save')
  same(sent.body!.scope, 'compact', 'of the compact class')
  eq(sent.body!.presentation, h.devices.compact, "carrying this tab's compact record")
  eq((sent.body!.presentation as DevicePlacement).order.slice(0, 1), ['s2'], 'with the reorder in it')
  ok(!JSON.stringify(sent.body).includes('999') && !('layout' in sent.body!) && !('tree' in sent.body!), 'and nothing of the wide arrangement, saved or not')
  same(bytes(wideFieldsOf(h.arr)), wideTab, 'the unsaved wide edit stays in this tab, byte for byte')
  same(bytes(h.devices.medium), bytes(RECORDS().medium), 'the tablet record is untouched by the phone Save')
  same(h.changed(), true, 'and the place is still changed (the wide edit)')
  /* an explicit reset of the phone record: one scoped save with null */
  await h.resetClass('compact')
  const reset = calls.filter((c) => c.method === 'POST').at(-1)!
  eq([reset.body!.scope, reset.body!.presentation, Object.keys(reset.body!).sort()], ['compact', null, ['op', 'presentation', 'scope']], 'Reset sends null for that class only')
  same(h.devices.compact, undefined, 'and this tab forgets the phone record')
  same(bytes(h.devices.medium), bytes(RECORDS().medium), 'keeping the tablet record')
  /* zones are named in the tree only by the wide arrangement */
  ok(zones(h.arr.tree).map((x) => x.id).join() === 's1,s2', 'the tree is still the desk tree')

  /* A wide Save sends no record, and leaves a phone record changed in this tab as this tab has it. */
  const d = new Holder(() => ({ tree: z('start'), pages: [] }), { local: local() })
  d.enter('c-desk', 'conversation')
  await flush()
  ok(d.apply('w1', { prop: 'placement', to: { kind: 'launcher' } }, { page: null, cls: 'compact' }).ok, 'a phone change, unsaved')
  const phone = bytes(d.devices.compact)
  d.edit((a) => ({ ...a, conversation: { width: 640 } }))
  await d.save('wide')
  const full = calls.filter((c) => c.method === 'POST').at(-1)!
  eq([Object.keys(full.body!).sort(), 'presentations' in (full.body!.layout as object)], [['layout', 'op'], false], 'a desk Save is a full save without any class record')
  same(bytes(d.devices.compact), phone, 'the unsaved phone change stays in this tab')
  same(bytes(d.devices.medium), bytes(RECORDS().medium), 'the tablet record, unchanged here, is what the Brain keeps')
  same(d.changed(), true, 'and the place is still changed, by the phone record')
}

console.log(`fluid device contract: ${checks} checks passed`)
