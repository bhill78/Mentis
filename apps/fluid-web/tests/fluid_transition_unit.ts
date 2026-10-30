import assert from 'node:assert/strict'
import * as nav from '../src/fluid/nav'
import { CONVERSATION_ID, MAX_FLOATS, type Float } from '../src/fluid/focus/types'
import { pageView } from '../src/fluid/focus/page'
import { Holder, toLayout, type Arr } from '../src/fluid/workspace/place'
import { findZone, keepSlot, followSlot, zones, type Node, type Slot, type Zone } from '../src/fluid/workspace/tree'
import { DECLARED } from '../src/fluid/surface/capabilities'
import { available } from '../src/fluid/surface/available'
import { FLOAT_LIMIT_MESSAGE, capsFor, stateIn, transition } from '../src/fluid/surface/transition'
import { SURFACE_VERBS, type Change, type DevicePlacement, type Outcome, type PresentationClass, type SurfaceCtx, type SurfaceState } from '../src/fluid/surface/types'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }

const z = (id: string, slot: Slot = keepSlot()): Zone => ({ type: 'zone', id, show: 'objects', name: id, slot })
const contentsSlot = (): Slot => ({ follow: false, show: 'objects', items: [], present: 'cards', feed: { source: 'contents' } })
const contents = (): Zone => ({ type: 'zone', id: 'contents', show: 'objects', name: 'Contents', slot: contentsSlot() })
const row = (sizes: number[], kids: Node[]): Node => ({ type: 'split', dir: 'row', sizes, kids })
const floatOf = (zone: Zone, id = `float-${zone.id}`, x = 40): Float => ({ id, zone, x, y: 40, w: 300, h: 200 })

interface Opts { cls?: PresentationClass; page?: string | null; device?: DevicePlacement; closed?: string[]; emphasis?: SurfaceCtx['session']['emphasis'] }
const ctxOf = (arr: Arr, o: Opts = {}): SurfaceCtx => {
  const cls = o.cls ?? 'wide', page = o.page ?? null
  return {
    arr, page, cls, ...(o.device ? { device: o.device } : {}), deviceLocal: { closed: new Set(o.closed ?? []) },
    session: { emphasis: o.emphasis ?? {} }, viewport: { w: 1280, h: 800 }, caps: capsFor(arr, page, cls, o.device),
  }
}
const must = (o: Outcome, what: string): Extract<Outcome, { ok: true }> => {
  if (!o.ok) assert.fail(`${what}: ${o.reason}`)
  checks++
  return o
}
const go = (arr: Arr, id: string, c: Change, o: Opts = {}) => must(transition(ctxOf(arr, o), id, c), `${id} ${JSON.stringify(c)}`)
const stateAt = (arr: Arr, id: string, o: Opts = {}) => stateIn(ctxOf(arr, o), id)
const avail = (arr: Arr, id: string, verb: (typeof SURFACE_VERBS)[number], o: Opts = {}) => {
  const ctx = ctxOf(arr, o)
  return available(verb, stateIn(ctx, id)!, ctx.caps(id), ctx)
}

/* ---- The Contents property (§3.3): the only section floats, and docks back. ---- */
{
  const alone: Arr = { tree: contents(), pages: [] }
  const out = go(alone, 'contents', { prop: 'placement', to: { kind: 'float' } })
  eq(out.layer, 'shared', 'floating is a shared change')
  const leaf = out.arr.tree as Zone
  ok(leaf.type === 'zone' && leaf.id !== 'contents', 'the tree is left one leaf, not the Contents section')
  eq({ ...leaf, id: undefined, name: undefined }, { type: 'zone', id: undefined, show: 'objects', name: undefined, slot: followSlot() }, 'the leaf is the product empty home leaf following what is read')
  const fl = out.arr.focus!.floats!
  eq(fl.length, 1, 'one window')
  eq(fl[0].zone, contents(), 'the window shows the same Contents zone, id unchanged')
  eq(fl[0].origin, { near: leaf.id, side: 'right' }, 'it docks back beside the home leaf, on the right')
  eq(Object.keys(out.arr).sort(), ['focus', 'pages', 'tree'], 'nothing else in the arrangement changed')
  const back = go(out.arr, 'contents', { prop: 'placement', to: { kind: 'dock' } })
  eq(zones(back.arr.tree).map((x) => x.id), [leaf.id, 'contents'], 'dock back restores a two-zone tree with Contents on its side')
  eq(back.arr.focus, undefined, 'and no window remains')
  eq(findZone(back.arr.tree, 'contents'), contents(), 'the zone is the same zone')

  /* Contents beside another section: floats with nothing else rearranged, and docks back in place. */
  const pair: Arr = { tree: row([0.4, 0.6], [z('a'), contents()]), pages: [] }
  const floated = go(pair, 'contents', { prop: 'placement', to: { kind: 'float', rect: { x: 10, y: 20, w: 300, h: 400 } } })
  eq(floated.arr.tree, z('a'), 'the section beside it took its room')
  eq(floated.arr.focus!.floats![0].origin, { near: 'a', side: 'right', share: 0.4 }, 'its origin is the section that grew')
  eq({ ...floated.arr.focus!.floats![0], id: undefined }, { id: undefined, zone: contents(), x: 10, y: 20, w: 300, h: 400, origin: { near: 'a', side: 'right', share: 0.4 } }, 'at the rectangle asked')
  const docked = go(floated.arr, 'contents', { prop: 'placement', to: { kind: 'dock' } })
  eq(docked.arr, pair, 'docking back restores the arrangement exactly')
}

/* ---- origin.near names the sibling that received the share (the floatOut fix). ---- */
{
  const three: Arr = { tree: row([0.2, 0.3, 0.5], [z('a'), z('b'), z('c')]), pages: [] }
  const out = go(three, 'b', { prop: 'placement', to: { kind: 'float' } })
  const sizes = (out.arr.tree as { sizes: number[] }).sizes
  eq(zones(out.arr.tree).map((x) => x.id), ['a', 'c'], 'b left the tree')
  ok(Math.abs(sizes[0] - 0.5) < 1e-12 && Math.abs(sizes[1] - 0.5) < 1e-12, 'a, before it, received its share')
  eq(out.arr.focus!.floats![0].origin!.near, 'a', 'and origin names a, the one that grew')
  eq(out.arr.focus!.floats![0].origin!.side, 'right', 'b was on its right')
  const back = go(out.arr, 'b', { prop: 'placement', to: { kind: 'dock' } })
  eq(zones(back.arr.tree).map((x) => x.id), ['a', 'b', 'c'], 'dock back returns b between a and c')
  ok((back.arr.tree as { sizes: number[] }).sizes.every((s, i) => Math.abs(s - [0.2, 0.3, 0.5][i]) < 1e-12), 'with every share restored')
  const first = go(three, 'a', { prop: 'placement', to: { kind: 'float' } })
  eq(first.arr.focus!.floats![0].origin!.near, 'b', 'the first leaf gives its share to the next, and names it')
  eq(first.arr.focus!.floats![0].origin!.side, 'left', 'on its left')

  /* dock ⇄ float without the origin present: it docks beside the primary place's leaf, or the first. */
  const gone = go(out.arr, 'a', { prop: 'exists', to: false })
  const lost = go(gone.arr, 'b', { prop: 'placement', to: { kind: 'dock' } })
  eq(zones(lost.arr.tree).map((x) => x.id), ['c', 'b'], 'with its origin gone it docks beside the first section')
  eq(lost.arr.focus, undefined, 'and is no longer a window')
  const near = go(out.arr, 'b', { prop: 'placement', to: { kind: 'dock', near: 'c', where: 'left' } })
  eq(zones(near.arr.tree).map((x) => x.id), ['a', 'b', 'c'], 'or wherever it is docked')
}

/* ---- Every change kind keeps the zone id: section, float, conversation, Page panel, launcher. ---- */
const desk = (): Arr => ({
  tree: row([0.5, 0.5], [z('s1'), z('s2', followSlot())]),
  pages: [{ id: 'p1', title: 'Page', tree: row([0.5, 0.5], [z('pp'), z('pq')]) }],
  focus: { floats: [floatOf(z('w1'))] },
})
const putAway = (): Arr => ({ tree: z('s1'), pages: [], focus: { minimized: { from: 'column', at: 1 } } })
const CHANGES: Change[] = [
  { prop: 'placement', to: { kind: 'float' } }, { prop: 'placement', to: { kind: 'dock' } }, { prop: 'placement', to: { kind: 'column' } },
  { prop: 'placement', to: { kind: 'launcher' } }, { prop: 'placement', to: { kind: 'back' } },
  { prop: 'placement', to: { kind: 'stack', index: 0 } }, { prop: 'placement', to: { kind: 'sheet' } },
  { prop: 'rect', rect: { x: 1, y: 2, w: 300, h: 300 } }, { prop: 'front' },
  { prop: 'level', to: 'compact' }, { prop: 'level', to: 'icon' }, { prop: 'level', step: 1 }, { prop: 'level', step: -1 }, { prop: 'level', to: 'reset' },
  { prop: 'emphasis', to: 'lens' }, { prop: 'emphasis', to: 'fullscreen' }, { prop: 'emphasis', to: 'none' },
  { prop: 'binding', to: 'follow' }, { prop: 'binding', to: 'hold' },
  { prop: 'primary', on: true }, { prop: 'primary', on: false }, { prop: 'order', to: 1 },
  { prop: 'open', to: false }, { prop: 'open', to: true },
]
const cases: { what: string; arr: () => Arr; id: string; page?: string }[] = [
  { what: 'a section', arr: desk, id: 's1' },
  { what: 'a float', arr: desk, id: 'w1' },
  { what: 'the conversation', arr: desk, id: CONVERSATION_ID },
  { what: 'a Page panel', arr: desk, id: 'pp', page: 'p1' },
  { what: 'the conversation in the launcher', arr: putAway, id: CONVERSATION_ID },
]
/* What a change may alter in the surface's own state (rule 1): its own property, and what is derived from it. */
const MAY: Record<Change['prop'], (keyof SurfaceState)[]> = {
  placement: ['placement', 'kind', 'level'], rect: ['placement'], front: [], level: ['level'], emphasis: ['emphasis'],
  binding: ['binding'], primary: ['placement', 'kind'], order: ['placement'], open: ['open'], exists: [],
}
let applied = 0
for (const cls of ['wide', 'medium', 'compact'] as const) for (const c of cases) for (const change of CHANGES) {
  const arr = c.arr()
  const o: Opts = { cls, page: c.page ?? null, ...(change.prop === 'open' && change.to ? { closed: [c.id] } : {}),
    ...(change.prop === 'emphasis' && change.to === 'none' ? { emphasis: { [c.id]: 'fullscreen' } } : {}) }
  const before = stateAt(arr, c.id, o)!
  const out = transition(ctxOf(arr, o), c.id, change)
  const tag = `${cls} ${c.what} ${JSON.stringify(change)}`
  if (!out.ok) { ok(typeof out.reason === 'string' && out.reason.length > 0, `${tag}: refused with a reason`); continue }
  applied++
  const after = stateIn({ ...ctxOf(out.arr, { ...o, device: out.device ?? o.device }),
    deviceLocal: out.deviceLocal ?? { closed: new Set(o.closed ?? []) }, session: out.session ?? { emphasis: o.emphasis ?? {} } }, c.id)
  ok(after, `${tag}: the surface is still there`)
  eq(after!.id, c.id, `${tag}: same zone id`)
  /* one property per call */
  const moved = (Object.keys(before) as (keyof SurfaceState)[]).filter((k) => JSON.stringify(before[k]) !== JSON.stringify(after![k]))
  ok(moved.every((k) => MAY[change.prop].includes(k)), `${tag}: only ${MAY[change.prop].join('/')} changed, not ${moved.join(', ')}`)
  /* the layers (rules 3 and 4) */
  if (out.layer === 'device' || out.layer === 'session') ok(out.arr === arr, `${tag}: a ${out.layer} change returns the arrangement identical`)
  if (out.layer === 'shared') ok(out.device === undefined && out.deviceLocal === undefined, `${tag}: a shared change writes no device record`)
  if (change.prop === 'open') eq([out.layer, !!out.device, !!out.deviceLocal], ['device', false, true], `${tag}: Close/Reopen write only this device's closed set`)
  if (cls !== 'wide' && (change.prop === 'placement' || change.prop === 'level' || change.prop === 'order'))
    eq([out.layer, !!out.device], ['device', true], `${tag}: placement and level in ${cls} write only the class record`)
  if (c.page) eq(out.arr.tree, arr.tree, `${tag}: This post's tree is untouched by a Page change`)
}
ok(applied > 90, `most change kinds apply somewhere (${applied})`)

/* Float/dock on the Page panel act on that Page only. */
{
  const arr = desk()
  const out = go(arr, 'pp', { prop: 'placement', to: { kind: 'float' } }, { page: 'p1' })
  eq(pageView(out.arr, 'p1').focus!.floats![0].zone.id, 'pp', 'the Page panel floats on its Page')
  eq(out.arr.focus, arr.focus, 'This post keeps its own windows')
}

/* ---- The conversation: column ⇄ float ⇄ launcher, id 'conv' throughout. ---- */
{
  const arr: Arr = { tree: z('s1'), pages: [] }
  const fl = go(arr, CONVERSATION_ID, { prop: 'placement', to: { kind: 'float', rect: { x: 5, y: 6, w: 400, h: 500 } } })
  const f = fl.arr.focus!.floats!.find((x) => x.zone.id === CONVERSATION_ID)!
  eq([f.x, f.y, f.w, f.h], [5, 6, 400, 500], 'the conversation floats at the rectangle asked')
  eq(fl.arr.focus!.minimized, undefined, 'and is not left in the launcher')
  const col = go(fl.arr, CONVERSATION_ID, { prop: 'placement', to: { kind: 'column' } })
  eq(col.arr, arr, 'and goes back to its column exactly')
  const away = go(arr, CONVERSATION_ID, { prop: 'placement', to: { kind: 'launcher' } })
  eq(away.arr.focus!.minimized!.from, 'column', 'Put away keeps where it came from')
  eq(stateAt(away.arr, CONVERSATION_ID)!.placement, { kind: 'launcher' }, 'and reads as the launcher placement')
  const back = go(away.arr, CONVERSATION_ID, { prop: 'placement', to: { kind: 'back' } })
  eq(back.arr, arr, 'Bring back returns it where it was')
  eq(transition(ctxOf(arr), CONVERSATION_ID, { prop: 'exists', to: false }).ok, false, 'the conversation is never removed')
}

/* ---- Level: zone level in wide, a window's icon is its tab (min), Reset returns to automatic. ---- */
{
  const arr = desk()
  const up = go(arr, 's1', { prop: 'level', step: 1 })
  eq(findZone(up.arr.tree, 's1')!.level, 'expanded', 'Expand steps standard to expanded')
  eq(transition(ctxOf(up.arr), 's1', { prop: 'level', step: 1 }).ok, false, 'and not past expanded')
  eq(findZone(go(up.arr, 's1', { prop: 'level', to: 'reset' }).arr.tree, 's1'), z('s1'), 'Reset size removes the override')
  const icon = go(go(arr, 'w1', { prop: 'level', step: -1 }).arr, 'w1', { prop: 'level', step: -1 })
  const w = icon.arr.focus!.floats![0]
  eq([w.min, w.zone.level], [true, undefined], 'a window collapsed to icon folds to its tab, with no zone level')
  eq(stateAt(icon.arr, 'w1')!.level, { auto: 'standard', override: 'icon' }, 'and reads as the icon level')
  const open = go(icon.arr, 'w1', { prop: 'level', step: 1 })
  eq([open.arr.focus!.floats![0].min, open.arr.focus!.floats![0].zone.level], [undefined, 'compact'], 'Expand unfolds it to compact')
  const dev = go(arr, 's1', { prop: 'level', to: 'compact' }, { cls: 'compact' })
  eq(dev.device!.level, { s1: 'compact' }, 'in compact the level is the class record’s')
  eq(stateAt(arr, 's1', { cls: 'compact', device: dev.device })!.level.override, 'compact', 'and read back from it')
}

/* ---- Full screen: transient emphasis only; Escape (none) restores it; no bytes change. ---- */
{
  const arr = desk()
  const bytes = JSON.stringify(arr)
  const fs = go(arr, 's1', { prop: 'emphasis', to: 'fullscreen' })
  eq([fs.layer, fs.arr === arr, fs.device, fs.deviceLocal], ['session', true, undefined, undefined], 'full screen is this tab’s, nothing else')
  eq(fs.session, { emphasis: { s1: 'fullscreen' } }, 'it sets only s1’s emphasis')
  const esc = must(transition({ ...ctxOf(arr), session: fs.session! }, 's1', { prop: 'emphasis', to: 'none' }), 'Escape')
  eq(esc.session, { emphasis: {} }, 'Escape restores none')
  eq(JSON.stringify(esc.arr), bytes, 'the arrangement bytes never changed')
  eq(stateIn({ ...ctxOf(arr), session: fs.session! }, 's1')!.placement, stateAt(arr, 's1')!.placement, 'placement unchanged')
  /* one lens, one full screen: another surface's ends */
  const other = must(transition({ ...ctxOf(arr), session: fs.session! }, 's2', { prop: 'emphasis', to: 'fullscreen' }), 'another full screen')
  eq(other.session, { emphasis: { s2: 'fullscreen' } }, 'only one surface is full screen')
  eq(available('fullscreen', stateIn({ ...ctxOf(arr), session: fs.session! }, 's1')!, ctxOf(arr).caps('s1'), { ...ctxOf(arr), session: fs.session! }).state, 'absent', 'Full screen is absent while full screen')
  eq(available('exitFullscreen', stateIn({ ...ctxOf(arr), session: fs.session! }, 's1')!, ctxOf(arr).caps('s1'), { ...ctxOf(arr), session: fs.session! }).state, 'available', 'and Exit full screen is there')
}

/* ---- The 12-float limit: float targets disabled with the reason; dock and stack stay. ---- */
{
  const full: Arr = { tree: row([0.5, 0.5], [z('s1'), z('s2', followSlot())]), pages: [],
    focus: { floats: Array.from({ length: MAX_FLOATS }, (_, i) => floatOf(z(`w${i}`), `f${i}`, i * 10)) } }
  const refused = transition(ctxOf(full), 's1', { prop: 'placement', to: { kind: 'float' } })
  eq(refused, { ok: false, reason: FLOAT_LIMIT_MESSAGE }, 'a thirteenth stored window is refused with the reason')
  eq(FLOAT_LIMIT_MESSAGE, '12 stored windows already use every slot; locally closed windows still count. Reopen one or Remove one from the workspace.', 'the reason text')
  eq(avail(full, 's1', 'float'), { state: 'disabled', reason: { code: 'limit', message: FLOAT_LIMIT_MESSAGE, retryable: true } }, 'Float is disabled with it')
  eq(avail(full, 's2', 'keepAsWindow').state, 'disabled', 'Keep as window too: its target is a window')
  eq(avail(full, 'w0', 'dock').state, 'available', 'a window can still dock')
  eq(avail(full, 's1', 'putAway', { cls: 'compact' }).state, 'available', 'and on compact the stack, sheet and launcher stay')
  eq(avail(full, 's1', 'showAsSheet', { cls: 'compact' }).state, 'available', 'a sheet stays available')
  eq(avail(full, 's1', 'float', { closed: ['w0'] }).state, 'disabled', 'a window closed on this device still counts')
}

/* ---- available(): r3 §2.2 "Absent when", as derived. ---- */
{
  const arr = desk()
  const away = putAway()
  const S = (id: string, o: Opts = {}) => stateAt(id === CONVERSATION_ID && o.page === 'away' ? away : arr, id, o)!
  const A = (verb: (typeof SURFACE_VERBS)[number], s: SurfaceState, caps = ctxOf(arr).caps(s.id === CONVERSATION_ID && s.placement.kind === 'launcher' ? 's1' : s.id), ctx = ctxOf(arr)) =>
    available(verb, s, caps, ctx).state
  const expanded = { ...S('s1'), level: { auto: 'standard' as const, override: 'expanded' as const } }
  eq(A('expand', expanded), 'absent', 'Expand: absent at expanded (use Open as Workspace)')
  const iconic = { ...S('w1'), level: { auto: 'standard' as const, override: 'icon' as const } }
  eq(A('collapse', iconic), 'absent', 'Collapse: absent at icon')
  const lensed = { ...S('s1'), emphasis: 'lens' as const }
  eq([A('dock', lensed), A('float', lensed)], ['absent', 'absent'], 'Dock / Float: absent on the lens')
  const tile = stateAt(away, CONVERSATION_ID)!
  const tileCtx = ctxOf(away)
  eq([available('dock', tile, tileCtx.caps(CONVERSATION_ID), tileCtx).state, available('float', tile, tileCtx.caps(CONVERSATION_ID), tileCtx).state], ['absent', 'absent'], 'Dock / Float: absent in the launcher')
  eq(available('bringBack', tile, tileCtx.caps(CONVERSATION_ID), tileCtx).state, 'available', 'Bring back is how it leaves the launcher')
  const root: SurfaceState = { ...S('pp', { page: 'p1' }), kind: 'page-panel', placement: { kind: 'page-root', page: 'p1' } }
  eq([A('dock', root, DECLARED['page-panel']), A('float', root, DECLARED['page-panel'])], ['absent', 'absent'], 'Dock / Float: absent on a Page root')
  eq(available('makePrimary', tile, tileCtx.caps(CONVERSATION_ID), tileCtx).state, 'absent', 'Make primary: absent in the launcher')
  eq(A('focus', S('s1')), 'available', 'Focus: never absent where focusable')
  eq(A('putAway', S('s1')), 'absent', 'Put away: absent for a section in wide (no launcher for it there)')
  eq(A('putAway', S(CONVERSATION_ID)), 'available', 'and available for the conversation')
  eq(A('close', S('s1')), 'available', 'Close: never absent where closable')
  eq(A('follow', S('w1')), 'absent', 'Follow: absent on a window (r3 step 3 deferred)')
  eq(available('follow', tile, DECLARED['launcher-tile'], tileCtx).state, 'absent', 'Follow: absent on a launcher icon')
  eq(A('follow', S('s1'), DECLARED.lens), 'absent', 'Follow: absent on the lens')
  eq(A('follow', S('s2')), 'absent', 'Follow: absent where it already follows')
  eq(A('hold', S('s2')), 'available', 'Hold: available on a follower')
  eq(A('hold', S('s1')), 'absent', 'Hold: absent on what is already held')
  const card: SurfaceState = { ...S('s1'), kind: 'nested-card', placement: { kind: 'nested', parent: 's2' } }
  eq(A('newFollower', card, DECLARED['nested-card']), 'absent', 'New follower: absent below section level')
  eq(A('newFollower', S('s1')), 'available', 'and available on a section')
  eq(A('removeFromWorkspace', S(CONVERSATION_ID)), 'absent', 'Remove from workspace: never the conversation')
  eq(A('removeFromWorkspace', S('s1')), 'available', 'Remove from workspace: a section')
  eq(A('moveUp', S('s1')), 'absent', 'Move up/down: absent in wide')
  const closed = { ...S('s1'), open: false }
  eq(SURFACE_VERBS.filter((v) => A(v, closed) !== 'absent'), ['reopen', 'removeFromWorkspace'], 'a surface closed here offers only Reopen and Remove')

  /* Every disabled answer carries a reason, in every class, for every case. */
  const every: [Arr, string, Opts][] = [
    ...['s1', 's2', 'w1', CONVERSATION_ID].flatMap((id) => (['wide', 'medium', 'compact'] as const).map((cls): [Arr, string, Opts] => [arr, id, { cls }])),
    [arr, 'pp', { page: 'p1' }], [away, CONVERSATION_ID, {}], [away, CONVERSATION_ID, { cls: 'compact' }],
  ]
  let disabledSeen = 0
  for (const [a, id, o] of every) for (const v of SURFACE_VERBS) {
    const r = avail(a, id, v, o)
    if (r.state !== 'disabled') continue
    disabledSeen++
    ok(r.reason.message.length > 0 && typeof r.reason.retryable === 'boolean', `${id} ${v}: disabled with a reason`)
  }
  ok(disabledSeen > 5, `disabled answers were exercised (${disabledSeen})`)
  eq(avail(arr, 's1', 'resetSize'), { state: 'disabled', reason: { code: 'state', message: 'It is already at its automatic size.', retryable: true } }, 'Reset size without an override says why')
  eq(avail(arr, 'w1', 'bringToFront').state, 'disabled', 'Bring to front: disabled when already in front')
  eq(avail(arr, CONVERSATION_ID, 'expand').state, 'disabled', 'the conversation column: size changes say why')
  eq(avail(arr, 's1', 'back').state, 'disabled', 'Back: disabled with nothing earlier')
  eq(avail(arr, 's1', 'float', { cls: 'medium' }).state, 'absent', 'Float: absent in medium')
  eq(avail(arr, 's1', 'dock', { cls: 'compact' }).state, 'absent', 'Dock: absent in compact')
}

/* ---- Binding: Follow and Hold on sections, through slot.follow / slot.pin. ---- */
{
  const arr = desk()
  eq(transition(ctxOf(arr), 's2', { prop: 'binding', to: 'hold' }), { ok: false, reason: 'Nothing is being read to hold.' }, 'Hold with nothing read says so')
  nav.read('c1', 'post-9', 9)
  const held = go(arr, 's2', { prop: 'binding', to: 'hold' })
  eq(findZone(held.arr.tree, 's2')!.slot!.pin, 'post-9', 'Hold keeps the post read (slot.pin)')
  eq(stateAt(held.arr, 's2')!.binding, { mode: 'held', resource: { address: 'post:post-9', kind: 'post' } }, 'and reads as held')
  const follows = go(held.arr, 's2', { prop: 'binding', to: 'follow' })
  eq(findZone(follows.arr.tree, 's2')!.slot, followSlot(), 'Follow undoes it')
  eq(transition(ctxOf(arr), 'w1', { prop: 'binding', to: 'follow' }).ok, false, 'a window does not follow in this build')
}

/* ---- Medium and compact: device records only; order; sheet; launcher. ---- */
{
  const arr = desk()
  const sheet = go(arr, 's1', { prop: 'placement', to: { kind: 'sheet' } }, { cls: 'compact' })
  ok(sheet.arr === arr, 'the arrangement is identical')
  eq(sheet.device!.place, { s1: 'sheet' }, 'the class record places it')
  eq(stateAt(arr, 's1', { cls: 'compact', device: sheet.device })!.placement, { kind: 'sheet' }, 'and the state reads it back')
  const order = go(arr, 's1', { prop: 'order', to: 2 }, { cls: 'compact' })
  eq(order.device!.order, [CONVERSATION_ID, 's2', 's1', 'w1'], 'order moves it in the stack')
  eq(transition(ctxOf(arr, { cls: 'medium' }), 's1', { prop: 'placement', to: { kind: 'float' } }).ok, false, 'no float in medium')
  const away = go(arr, 's1', { prop: 'placement', to: { kind: 'launcher' } }, { cls: 'compact' })
  const back = go(arr, 's1', { prop: 'placement', to: { kind: 'back' } }, { cls: 'compact', device: away.device })
  eq(back.device!.place.s1, 'stack', 'brought back to the stack')
  const closed = go(arr, 's1', { prop: 'open', to: false }, { cls: 'compact' })
  eq([...closed.deviceLocal!.closed], ['s1'], 'Close adds it to this device’s closed set')
  eq(stateAt(arr, 's1', { cls: 'compact', closed: ['s1'] })!.open, false, 'and it reads closed')
  eq(stateAt(arr, 's1', { cls: 'wide' })!.open, true, 'a set for another class is another set')
}

/* ---- Holder.apply: one undo step per arrangement or class-record change. ---- */
{
  const h = new Holder(() => ({ tree: z('start'), pages: [] }))
  const arr = desk()
  h.arr = arr
  const env = { page: null, cls: 'wide' as const, viewport: { w: 1280, h: 800 } }
  const o = h.apply('s1', { prop: 'placement', to: { kind: 'float' } }, env)
  ok(o.ok && h.arr !== arr, 'apply commits the outcome')
  eq([h.canUndo(), h.undoLabel()], [true, (o as { label: string }).label], 'as one undo step named by its label')
  h.undo()
  eq([h.arr, h.canUndo()], [arr, false], 'Undo takes back exactly that step')
  const refused = h.apply('nope', { prop: 'front' }, env)
  eq([refused.ok, h.canUndo()], [false, false], 'a refused change leaves no step')
  const sheet = h.apply('s1', { prop: 'placement', to: { kind: 'sheet' } }, { ...env, cls: 'compact' })
  ok(sheet.ok && h.arr === arr, 'a compact placement leaves the arrangement identical')
  eq(h.devices.compact!.place, { s1: 'sheet' }, 'and is kept in the class record')
  eq(h.canUndo(), true, 'as one undo step')
  h.undo()
  eq(h.devices, {}, 'which Undo takes back')
  h.apply('s1', { prop: 'open', to: false }, { ...env, cls: 'compact' })
  eq([[...h.closed.compact], [...h.closed.wide], h.canUndo()], [['s1'], [], false], 'Close is this device’s, per class, and no undo step')
  h.apply('s1', { prop: 'emphasis', to: 'fullscreen' }, env)
  eq([h.emphasis, h.arr === arr, h.canUndo()], [{ s1: 'fullscreen' }, true, false], 'full screen is this tab’s, no step, no bytes')
  eq(JSON.stringify(toLayout(h.arr)), JSON.stringify(toLayout(arr)), 'the layout saved is unchanged')
  h.apply('s1', { prop: 'emphasis', to: 'none' }, env)
  eq(h.emphasis, {}, 'Escape ends it')
}

console.log(`fluid transition: ${checks} checks passed`)
