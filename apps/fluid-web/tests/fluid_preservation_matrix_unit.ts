/* THE IDENTITY AND VIEW-STATE MATRIX (Surface Tension P5, plan §4 P5, §3.9).
 *
 * There is no DOM here, so what a surface keeps is asserted where it is
 * kept: view state (viewState.ts), drafts (drafts.ts), the hosts registry
 * (hosts.tsx, against a stand-in document), the Holder, and this browser
 * device's closed sets (deviceLocal.ts, against stand-in storages).
 *
 *  1. Six surfaces, each holding what it holds, through dock -> float,
 *     float -> dock (origin present and absent), launcher -> Bring back, lens
 *     enter/exit, Expand/Collapse and the class switches wide -> medium ->
 *     compact -> wide: the zone id stays, every view-state part reads back,
 *     the draft stays in drafts.ts, the hosts registry keeps one element per
 *     id; a class switch adds no undo step and no ":changed" mark.
 *  2. Close on compact: only the compact closed set of this browser device;
 *     it survives a reload and a new tab, reaches a sibling tab, leaves
 *     another device and the other classes open; Reopen restores it; Remove
 *     from workspace is the shared action, and only it takes the surface out.
 *  3. projectVisibleTree: a closed dock leaf is not drawn, its share goes to
 *     the leaf before it, all closed draws the empty leaf, and the stored tree
 *     never changes but by the reader's own edit.
 *  4. The 12-window bound: closed windows leave the rendered count, not the
 *     stored one. */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { CONVERSATION_ID, MAX_FLOATS, type Float } from '../src/fluid/focus/types'
import { Holder, toLayout, type Arr, type DeviceLocalOpts } from '../src/fluid/workspace/place'
import { closeZone, followSlot, keepSlot, splitZone, zones, type Node, type Zone } from '../src/fluid/workspace/tree'
import { FLOAT_LIMIT_MESSAGE, capsFor, stateIn, transition } from '../src/fluid/surface/transition'
import { available } from '../src/fluid/surface/available'
import { findSurface } from '../src/fluid/surface/state'
import { derive } from '../src/fluid/focus/narrowView'
import { setViewState, viewState, type ViewKey } from '../src/fluid/surface/viewState'
import { loadDraft, saveDraft } from '../src/fluid/composer/drafts'
import { emptyDraft } from '../src/composer/draft'
import { hostOf } from '../src/fluid/focus/hosts'
import { CLOSE_HERE, EMPTY_HERE, closeOffered, closedHere, openFloats, projectVisibleTree, stackStep, storedTree } from '../src/fluid/surface/projection'
import { CLOSED_PREFIX, MAX_CLOSED, closedKey, parseClosed } from '../src/fluid/surface/deviceLocal'
import { sectionHost } from '../src/fluid/surface/chromeHosts'
import type { Change, DevicePlacement, PresentationClass, SurfaceCtx } from '../src/fluid/surface/types'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const same = (a: unknown, b: unknown, what: string) => { assert.equal(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }
const bytes = (v: unknown) => JSON.stringify(v)

const z = (id: string, slot = keepSlot()): Zone => ({ type: 'zone', id, show: 'objects', name: id, slot })
const magnet = (id: string): Zone => ({ type: 'zone', id, show: 'magnet', name: 'Board', options: { magnet: id } })
const row = (sizes: number[], kids: Node[]): Node => ({ type: 'split', dir: 'row', sizes, kids })
const col = (sizes: number[], kids: Node[]): Node => ({ type: 'split', dir: 'col', sizes, kids })
const fl = (zone: Zone, x = 40, id = 'f-' + zone.id): Float => ({ id, zone, x, y: 40, w: 320, h: 240 })
const flush = async () => { for (let i = 0; i < 8; i++) await new Promise((r) => setTimeout(r, 0)) }
const deepFreeze = <T,>(o: T): T => { if (o && typeof o === 'object') { Object.values(o).forEach(deepFreeze); Object.freeze(o) } return o }

/* -- the network: a Brain keeping one arrangement per place, POSTs recorded --- */
const kept = new Map<string, unknown>()
const posts: { url: string; body: Record<string, unknown> }[] = []
;(globalThis as any).fetch = async (url: string, init?: RequestInit) => {
  const method = (init?.method ?? 'GET').toUpperCase()
  const u = String(url)
  const key = decodeURIComponent(u.split('/arrangements/')[1] ?? '')
  let reply: unknown
  if (u.endsWith('/layouts')) reply = { layouts: [], defaults: { home: null, conversation: null, unnamed: null } }
  else if (u.includes('/api/brain')) reply = { corpus_id: 'brain-from-server' }
  else if (method === 'GET') reply = kept.has(key) ? { layout: kept.get(key), saved: 100 } : { layout: null, saved: null }
  else {
    const body = JSON.parse(String(init!.body))
    posts.push({ url: u, body })
    if (body.layout) kept.set(key, body.layout)
    reply = { saved: 101, layout: kept.get(key) }
  }
  return new Response(JSON.stringify(reply), { status: 200, headers: { 'Content-Type': 'application/json' } })
}

/** One browser device: its localStorage, shared by its tabs. */
const device = (brain = 'b1') => {
  const m = new Map<string, string>()
  const opts: DeviceLocalOpts = { store: () => ({ getItem: (k) => m.get(k) ?? null, setItem: (k, v) => { m.set(k, v) }, removeItem: (k) => { m.delete(k) } }), brain: async () => brain }
  return { m, opts }
}
const tab = (d: { opts: DeviceLocalOpts }) => new Holder(() => ({ tree: z('start'), pages: [] }), { local: d.opts })

/* =============================================================================
 * 1. Identity and view state, through every kind of move and class switch.
 * ========================================================================== */

/* the six surfaces: the conversation (column) with a draft; a section with a
   scrolled list and in-surface search; a window with a half-filled form
   builder; Present cards with a current item and a fold; Grouped with a group
   open; a magnet with a tab, a search and a scroll */
const desk = (): Arr => ({
  tree: row([0.25, 0.25, 0.25, 0.25], [z('s1'), z('pres', { ...keepSlot(['live:p:1']), present: 'slides' }), z('grp', followSlot()), magnet('mag-x')]),
  pages: [],
  focus: { floats: [fl(z('fw'))] },
})
const IDS = [CONVERSATION_ID, 's1', 'pres', 'grp', 'mag-x', 'fw']
const VIEW: [ViewKey, string, unknown][] = [
  [{ surface: 's1', resource: 'zone:s1' }, 'scroll', 420],
  [{ surface: 's1', resource: 'zone:s1' }, 'search', 'tidewater'],
  [{ surface: 'fw', resource: 'form-draft:fw' }, 'fields', [{ id: 'q1', label: 'Why?', type: 'text' }]],
  [{ surface: 'fw', resource: 'form-draft:fw' }, 'title', 'Half a form'],
  [{ surface: 'pres', resource: 'live:p:1' }, 'current', 'obj-3'],
  [{ surface: 'pres', resource: 'live:p:1' }, 'fold', false],
  [{ surface: 'grp', resource: 'zone:grp' }, 'open', 'group-2'],
  [{ surface: 'mag-x', resource: 'magnet:mag-x' }, 'tab', 'images'],
  [{ surface: 'mag-x', resource: 'magnet:mag-x' }, 'search', 'harbour'],
  [{ surface: 'mag-x', resource: 'magnet:mag-x' }, 'scroll', 1200],
]
for (const [k, part, v] of VIEW) setViewState(k, part, v)
saveDraft('conversation:c-matrix', { ...emptyDraft(), text: 'half a reply' })
const convHost = hostOf(CONVERSATION_ID)
const made = (globalThis as any).__made as unknown[]
const madeBefore = made.length

const holds = (h: Holder, what: string) => {
  for (const id of IDS) {
    const s = stateIn(h.surfaceCtx({ page: null, cls: 'wide' }), id)
    ok(s && s.id === id, `${what}: ${id} is still there, under the same id`)
  }
  for (const [k, part, v] of VIEW) eq(viewState(k, part), v, `${what}: ${k.surface} ${part} reads back`)
  same(loadDraft('conversation:c-matrix').text, 'half a reply', `${what}: the draft is still in drafts.ts`)
  same(hostOf(CONVERSATION_ID), convHost, `${what}: the conversation's one host element is the same`)
  same(made.length, madeBefore, `${what}: no second host element was made`)
}

const d1 = device()
const h = tab(d1)
h.enter('c-matrix', 'conversation')
await flush()
/* a class switch on arrival: nothing is written, nothing is a step */
{
  const mark = () => (globalThis as any).sessionStorage.getItem('mentis.fluid.arr:c-matrix:changed')
  same(mark(), null, 'arrived: no ":changed" mark')
  for (const cls of ['medium', 'compact', 'wide'] as const) {
    const ctx = h.surfaceCtx({ page: null, cls })
    for (const id of zones(h.arr.tree).map((x) => x.id)) stateIn(ctx, id)
    if (cls !== 'wide') derive(h.arr, cls, h.devices[cls])
    eq([h.canUndo(), mark(), h.changed()], [false, null, false], `switching to ${cls}: no undo step, no ":changed" mark, not changed`)
  }
}
h.edit(() => desk())
const env = (cls: PresentationClass = 'wide') => ({ page: null, cls, viewport: { w: 1280, h: 800 } })
const step = (id: string, c: Change, what: string, cls: PresentationClass = 'wide') => {
  const o = h.apply(id, c, env(cls))
  if (!o.ok) assert.fail(`${what}: ${o.reason}`)
  checks++
  holds(h, what)
}
holds(h, 'the desk')
step('s1', { prop: 'placement', to: { kind: 'float' } }, 'dock -> float')
ok(findSurface(h.arr, 's1')!.wide.kind === 'float', 's1 floats')
step('s1', { prop: 'placement', to: { kind: 'dock' } }, 'float -> dock, origin present')
ok(findSurface(h.arr, 's1')!.wide.kind === 'dock', 's1 is docked again')
step('fw', { prop: 'placement', to: { kind: 'dock' } }, 'float -> dock, origin absent')
step('fw', { prop: 'placement', to: { kind: 'float' } }, 'and floats again')
step(CONVERSATION_ID, { prop: 'placement', to: { kind: 'launcher' } }, 'the conversation put away to the launcher')
step(CONVERSATION_ID, { prop: 'placement', to: { kind: 'back' } }, 'and brought back')
step('pres', { prop: 'level', step: 1 }, 'Expand')
step('pres', { prop: 'level', step: -1 }, 'Collapse')
{
  /* the lens is the tab's emphasis (focus/lens.ts draws it): entered and left */
  const ctx = h.surfaceCtx(env())
  const on = transition(ctx, 'pres', { prop: 'emphasis', to: 'lens' })
  ok(on.ok && on.layer === 'session' && on.arr === ctx.arr, 'lens enter is this tab only')
  const off = transition({ ...ctx, session: (on as { session: SurfaceCtx['session'] }).session }, 'pres', { prop: 'emphasis', to: 'none' })
  ok(off.ok && off.layer === 'session' && off.arr === ctx.arr, 'lens exit too')
  holds(h, 'lens enter / exit')
}
{
  /* the class switches, after edits: wide -> medium -> compact -> wide */
  const depth = (h as unknown as { undoStack: unknown[] }).undoStack.length
  const touched = (globalThis as any).sessionStorage.getItem('mentis.fluid.arr:c-matrix:changed')
  const arrBytes = bytes(h.arr)
  for (const cls of ['medium', 'compact', 'wide'] as const) {
    const ctx = h.surfaceCtx(env(cls))
    for (const id of IDS) same(stateIn(ctx, id)?.id, id, `in ${cls}: ${id} keeps its id`)
    if (cls !== 'wide') same(derive(h.arr, cls, h.devices[cls]).order.length >= IDS.length - 1, true, `in ${cls}: derive lists the surfaces`)
    eq([(h as unknown as { undoStack: unknown[] }).undoStack.length, (globalThis as any).sessionStorage.getItem('mentis.fluid.arr:c-matrix:changed'), bytes(h.arr)],
      [depth, touched, arrBytes], `switching to ${cls}: no undo step, the ":changed" mark as it was, the arrangement untouched`)
    holds(h, `class switch to ${cls}`)
  }
}
{
  /* a device placement in compact keeps every identity too */
  step('fw', { prop: 'placement', to: { kind: 'sheet' } }, 'compact: a window as a sheet', 'compact')
  step('s1', { prop: 'order', to: 0 }, 'compact: a section moved up the stack', 'compact')
}
ok(/<Hosted id=\{CONVERSATION_ID\}>/.test(readFileSync(new URL('../src/fluid/Shell.tsx', import.meta.url), 'utf8')), 'the Shell draws the conversation once, into its host')
for (const f of ['workspace/TreeView.tsx', 'workspace/Workspace.tsx', 'focus/NarrowFloats.tsx', 'focus/Floats.tsx', 'surface/ClosedHere.tsx'])
  ok(!readFileSync(new URL('../src/fluid/' + f, import.meta.url), 'utf8').includes('<Hosted'), `${f} draws no second Hosted (it mounts, never hosts)`)

/* =============================================================================
 * 2. Close on compact is this browser device's, and only Remove is shared.
 * ========================================================================== */
{
  kept.set('c-close', toLayout(desk()))
  const phone = device(), desktop = device()
  const t1 = tab(phone), t2 = tab(phone), other = tab(desktop)
  for (const t of [t1, t2, other]) t.enter('c-close', 'conversation')
  await flush()
  const key = (cls: PresentationClass) => closedKey('b1', 'c-close', cls)
  const arrBytes = bytes(t1.arr), devBytes = bytes(t1.devices), postsBefore = posts.length
  const closed = t1.apply('s1', { prop: 'open', to: false }, env('compact'))
  ok(closed.ok && closed.layer === 'device', 'Close on compact applies')
  eq([...t1.closed.compact], ['s1'], 'it is in the compact closed set')
  eq([[...t1.closed.wide], [...t1.closed.medium]], [[], []], 'the other classes stay open')
  eq([phone.m.get(key('compact')), phone.m.has(key('wide')), phone.m.has(key('medium'))], ['["s1"]', false, false],
    'only the compact set is written, to this device\'s localStorage')
  eq([bytes(t1.arr), bytes(t1.devices), posts.length], [arrBytes, devBytes, postsBefore], 'the arrangement, the class records and the Brain are untouched')
  same(t1.canUndo(), false, 'Close is no undo step (Reopen is its way back)')
  ok(findSurface(t1.arr, 's1'), 's1 is still in the arrangement')
  /* a sibling tab of the same browser hears it (the storage event) */
  eq([...t2.closed.compact], [], 'the sibling tab had it open')
  t2.deviceChanged(key('compact'))
  eq([...t2.closed.compact], ['s1'], 'and has it closed once the storage event comes')
  t2.deviceChanged(CLOSED_PREFIX + 'b1:another-place:compact')
  eq([...t2.closed.compact], ['s1'], 'another place\'s event changes nothing here')
  /* a reload or a new tab on this browser */
  const reloaded = tab(phone)
  reloaded.enter('c-close', 'conversation')
  await flush()
  eq([...reloaded.closed.compact], ['s1'], 'a reload or a new tab finds it closed')
  /* another device */
  eq([...other.closed.compact, ...other.closed.wide, ...other.closed.medium], [], 'another device still has it open in every class')
  ok(stateIn(other.surfaceCtx(env('compact')), 's1')!.open, 'and reads it open')
  /* Reopen */
  ok(t1.apply('s1', { prop: 'open', to: true }, env('compact')).ok, 'Reopen applies')
  eq([[...t1.closed.compact], phone.m.has(key('compact'))], [[], false], 'Reopen empties the set (and the key goes)')
  t2.deviceChanged(key('compact'))
  eq([...t2.closed.compact], [], 'the sibling tab hears Reopen too')
  /* Remove from workspace: the explicit shared action */
  t1.apply('s1', { prop: 'open', to: false }, env('compact'))
  t1.apply('s1', { prop: 'open', to: false }, env('wide'))
  ok(findSurface(t1.arr, 's1') && findSurface(other.arr, 's1'), 'closed is not removed: s1 is in both devices\' arrangements')
  same(posts.length, postsBefore, 'and nothing was sent to the Brain')
  const removed = t1.apply('s1', { prop: 'exists', to: false }, env('wide'))
  ok(removed.ok && removed.layer === 'shared', 'Remove from workspace is a shared change')
  same(findSurface(t1.arr, 's1'), null, 'it takes s1 out of the arrangement')
  eq([[...t1.closed.compact], [...t1.closed.wide], phone.m.has(key('compact')), phone.m.has(key('wide'))], [[], [], false, false],
    'and out of every closed set: it is gone, not closed')
  await t1.save('wide')
  const saved = posts.at(-1)!.body.layout as Record<string, unknown>
  ok(!bytes(saved.tree).includes('"s1"'), 'saved, the shared removal reaches the Brain (and so every device)')
  /* the bound, and what is not an id */
  eq([...parseClosed(JSON.stringify([...Array.from({ length: MAX_CLOSED + 5 }, (_, i) => 'z' + i), 7, '../x', '']))].length, MAX_CLOSED, 'a kept set is bounded, ids only')
}

/* =============================================================================
 * 3. projectVisibleTree: drawn without the closed leaves; kept as it was.
 * ========================================================================== */
{
  const a = z('a'), b = z('b'), c = z('c'), d = z('d')
  const S = deepFreeze(row([0.3, 0.3, 0.4], [a, b, c]))
  const before = bytes(S)
  const V = projectVisibleTree(S, new Set(['b']))
  eq(zones(V).map((x) => x.id), ['a', 'c'], 'a closed dock leaf is not drawn')
  ok(Math.abs((V as { sizes: number[] }).sizes[0] - 0.6) < 1e-12 && Math.abs((V as { sizes: number[] }).sizes[1] - 0.4) < 1e-12, 'its share goes to the leaf before it')
  same(projectVisibleTree(S, new Set(['b'])), V, 'the same tree and set draw the same object (an edit is made on what was drawn)')
  same(projectVisibleTree(S, new Set(['nope'])), S, 'nothing closed in it: the tree itself')
  same(storedTree(S, new Set(['b']), V), S, 'no edit: the stored tree itself')
  same(bytes(S), before, 'the stored tree is byte-identical')
  /* a boundary moved on the drawn tree */
  const moved = { ...(V as object), sizes: [0.5, 0.5] } as Node
  const back = storedTree(S, new Set(['b']), moved)
  eq(zones(back).map((x) => x.id), ['a', 'b', 'c'], 'an edit keeps the closed leaf where it was')
  eq((back as { sizes: number[] }).sizes.map((x) => Math.round(x * 1000) / 1000), [0.25, 0.25, 0.5], 'sharing the room of the leaf it gave its share to, as before')
  eq((back as { kids: Node[] }).kids[1], b, 'the same zone, untouched')
  same(bytes(S), before, 'and the stored tree passed in is still byte-identical')
  /* the first leaf: its share went to the one after */
  const F = deepFreeze(row([0.5, 0.5], [a, b]))
  const fv = projectVisibleTree(F, new Set(['a']))
  eq(fv, F.kids[1], 'the first closed: the one after takes all of it')
  const split = splitZone(fv, 'b', 'col', c).tree
  eq(zones(storedTree(F, new Set(['a']), split)).map((x) => x.id), ['a', 'b', 'c'], 'an edit there keeps the closed leaf before it')
  /* nested, and two closed */
  const N = deepFreeze(row([0.5, 0.5], [a, col([0.4, 0.6], [b, c])]))
  const nv = projectVisibleTree(N, new Set(['b']))
  eq(zones(nv).map((x) => x.id), ['a', 'c'], 'a closed leaf in a nested split')
  eq(storedTree(N, new Set(['b']), { ...(nv as object), sizes: [0.3, 0.7] } as Node), row([0.3, 0.7], [a, col([0.4, 0.6], [b, c])]), 'a moved boundary puts it back exactly where it was')
  const M = deepFreeze(row([0.25, 0.25, 0.25, 0.25], [a, b, c, d]))
  const mv = projectVisibleTree(M, new Set(['b', 'd']))
  eq(zones(mv).map((x) => x.id), ['a', 'c'], 'two closed')
  eq(zones(storedTree(M, new Set(['b', 'd']), { ...(mv as object), sizes: [0.4, 0.6] } as Node)).map((x) => x.id), ['a', 'b', 'c', 'd'], 'both put back in order')
  /* the reader's own removal of a drawn leaf is kept; the closed one stays */
  eq(zones(storedTree(S, new Set(['b']), closeZone(V, 'c'))).map((x) => x.id), ['a', 'b'], 'removing a drawn leaf removes it, and only it')
  /* every leaf closed: the product's empty leaf, drawn only */
  const one = deepFreeze(z('a'))
  const ev = projectVisibleTree(one, new Set(['a'])) as Zone
  eq([ev.id, ev.slot], [EMPTY_HERE, followSlot()], 'all closed: the empty leaf following what is read')
  const all = projectVisibleTree(S, new Set(['a', 'b', 'c'])) as Zone
  same(all.id, EMPTY_HERE, 'all of a split closed: the empty leaf too')
  same(storedTree(S, new Set(['a', 'b', 'c']), all), S, 'with no edit the stored tree is itself')
  const used = { ...all, slot: keepSlot(['live:p:9']) }
  const grown = storedTree(S, new Set(['a', 'b', 'c']), used)
  eq(zones(grown).slice(0, 3).map((x) => x.id), ['a', 'b', 'c'], 'something kept in the empty leaf keeps every closed zone')
  ok(zones(grown)[3].id !== EMPTY_HERE && zones(grown)[3].slot!.items[0] === 'live:p:9', 'and becomes a zone of its own')
  /* stacking order and the Reopen list */
  eq(stackStep(['conv', 'w1', 'w2', 'w3'], ['w1', 'w3'], 'w3', -1), 1, 'Move up among the drawn cards goes before the card drawn above')
  eq([stackStep(['w1', 'w2'], ['w1', 'w2'], 'w1', -1), stackStep(['w1', 'w2'], ['w1', 'w2'], 'w2', 1)], [null, null], 'and not past either end')
  eq(closedHere({ tree: S, focus: { floats: [fl(z('w1')), fl(d)] } }, new Set(['b', 'd'])), [{ id: 'b', name: 'b' }, { id: 'd', name: 'd' }], 'the Reopen list names the closed leaves and windows')
}

/* =============================================================================
 * 4. The 12-window bound: the rendered count and the stored count.
 * ========================================================================== */
{
  const full: Arr = { tree: row([0.5, 0.5], [z('s1'), z('s2')]), pages: [], focus: { floats: Array.from({ length: MAX_FLOATS }, (_, i) => fl(z('w' + i), i * 10)) } }
  const closedNow = new Set(['w0', 'w1', 'w2'])
  same(openFloats(full.focus!.floats!, closedNow).length, MAX_FLOATS - 3, 'closed windows are not among those drawn here')
  const ctxOf = (cls: PresentationClass, device?: DevicePlacement): SurfaceCtx => ({ arr: full, page: null, cls, deviceLocal: { closed: closedNow }, ...(device ? { device } : {}),
    session: { emphasis: {} }, viewport: { w: 1280, h: 800 }, caps: capsFor(full, null, cls, device) })
  eq(transition(ctxOf('wide'), 's1', { prop: 'placement', to: { kind: 'float' } }), { ok: false, reason: FLOAT_LIMIT_MESSAGE }, 'the stored count still refuses a 13th window')
  const ctx = ctxOf('wide')
  eq(available('float', stateIn(ctx, 's1')!, ctx.caps('s1'), ctx), { state: 'disabled', reason: { code: 'limit', message: FLOAT_LIMIT_MESSAGE, retryable: true } }, 'Float is disabled with the stored-count reason')
  for (const verb of ['putAway', 'showAsSheet'] as const) {
    const c = ctxOf('compact')
    same(available(verb, stateIn(c, 's1')!, c.caps('s1'), c).state, 'available', `compact ${verb} stays available`)
  }
  const m = ctxOf('medium')
  same(available('showAsSheet', stateIn(m, 's1')!, m.caps('s1'), m).state, 'available', 'medium sheet stays available')
  same(available('dock', stateIn(ctx, 'w5')!, ctx.caps('w5'), ctx).state, 'available', 'and a window can still dock')
}

/* =============================================================================
 * 5. Where × Close is drawn: one rule, and the docked section's host lends it.
 * ========================================================================== */
{
  eq(CLOSE_HERE, { section: ['dock', 'stack', 'sheet'], float: ['float', 'stack', 'sheet'], magnet: ['dock', 'float', 'stack', 'sheet'], conversation: ['stack', 'sheet'] },
    'CLOSE_HERE: the rule held open for the owner')
  eq([closeOffered('section', 'dock'), closeOffered('float', 'float'), closeOffered('conversation', 'dock'), closeOffered('lens', 'dock')], [true, true, false, false],
    'a docked section and a window offer Close here; the conversation\'s own section and the lens do not')
  const ctl = { canSplitRow: true, canSplitCol: true, whyNoSplitRow: null, whyNoSplitCol: null, canMerge: true, canClose: true, split: () => {}, merge: () => {}, close: () => {}, fit: false }
  let ran = 0
  const host = sectionHost(ctl, { closeHere: { run: () => { ran++ } } })
  ok(host.close && host.removeFromWorkspace && host.close !== host.removeFromWorkspace, 'a docked section lends Close (×) apart from Remove from workspace')
  host.close!.run()
  same(ran, 1, 'and × runs the device-local Close')
  same(sectionHost(ctl).close, undefined, 'without it, no × (as P4 left it)')
  for (const f of ['workspace/Zones.tsx', 'conversation/ThreadWindow.tsx'])
    ok(/closeOffered\('section', 'dock'\)[^\n]*closeHere: closeHere\(z\.id\)/.test(readFileSync(new URL('../src/fluid/' + f, import.meta.url), 'utf8')), `${f}: a docked section lends Close here by the rule`)
}

console.log(`fluid preservation matrix: ${checks} checks passed`)
