import assert from 'node:assert/strict'

/* AN EMPTY WORKSPACE (owner, Turn #1592: "A workspace can be empty, with maybe
 * the chat rail only, and all it has are magnets that a user may Activate
 * individually. They also can move the magnets anywhere on the workspace.").
 *
 *   1. Closing, removing, floating or putting away the LAST surface leaves the
 *      empty page -- never a section following what is read.
 *   2. The empty page is no surface: not listed, not stacked, no target.
 *   3. What comes next takes its place; closing that returns to empty.
 *   4. An empty page is saved and read back empty, by the tab and the Brain.
 *   5. Magnets on an empty page activate one at a time.
 *   6. A Magnet moves anywhere, stays a window, and its place is kept. */
const mem = new Map<string, string>()
;(globalThis as any).sessionStorage = {
  getItem: (k: string) => mem.get(k) ?? null,
  setItem: (k: string, v: string) => { mem.set(k, v) },
  removeItem: (k: string) => { mem.delete(k) },
}
;(globalThis as any).fetch = async () => { throw new Error('offline in a unit test') }

const { dockBack, dockFloat, floatOut, locate, makePrimary, minimize, restore } = await import('../src/fluid/focus/model')
const { surfacesOf, startLens } = await import('../src/fluid/focus/compose')
const { CONVERSATION_ID } = await import('../src/fluid/focus/types')
const { derive } = await import('../src/fluid/focus/narrowView')
const { Holder, fromLayout, toLayout, withoutShared } = await import('../src/fluid/workspace/place')
const { pageLanding } = await import('../src/fluid/workspace/keep')
const { emptyZone, isEmptyTree, isEmptyZone, keepSlot, splitOuter, splitZone, valid, withoutLeaf, zones } = await import('../src/fluid/workspace/tree')
const { EMPTY_HERE, projectVisibleTree, storedTree } = await import('../src/fluid/surface/projection')
const { surfaceIds } = await import('../src/fluid/surface/state')
const { capsFor, stateIn, transition } = await import('../src/fluid/surface/transition')

type Arr = import('../src/fluid/workspace/place').Arr
type Node = import('../src/fluid/workspace/tree').Node
type Zone = import('../src/fluid/workspace/tree').Zone
type Float = import('../src/fluid/focus/types').Float
type Change = import('../src/fluid/surface/types').Change
type Outcome = import('../src/fluid/surface/types').Outcome
type SurfaceCtx = import('../src/fluid/surface/types').SurfaceCtx

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }
const flush = async () => { for (let i = 0; i < 6; i++) await new Promise((r) => setTimeout(r, 0)) }

const z = (id: string): Zone => ({ type: 'zone', id, show: 'objects', name: id, slot: keepSlot() })
const conv = (): Zone => ({ type: 'zone', id: CONVERSATION_ID, show: 'conversation', name: 'Conversation' })
const mag = (id: `mag-${string}`, name: string): Zone => ({ type: 'zone', id, show: 'magnet', name, options: { magnet: id }, level: 'icon' })
const magFloat = (id: `mag-${string}`, name: string, x: number, y: number): Float => ({ id: `w-${id}`, zone: mag(id, name), x, y, w: 360, h: 480 })
const row = (...kids: Node[]): Node => ({ type: 'split', dir: 'row', sizes: kids.map(() => 1 / kids.length), kids })
const T = 1_700_000_000_000

const ctxOf = (arr: Arr, closed: string[] = []): SurfaceCtx => ({
  arr, page: null, cls: 'wide', deviceLocal: { closed: new Set(closed) }, session: { emphasis: {} },
  viewport: { w: 1280, h: 800 }, caps: capsFor(arr, null, 'wide'),
})
const must = (o: Outcome, what: string): Extract<Outcome, { ok: true }> => {
  if (!o.ok) assert.fail(`${what}: ${o.reason}`)
  checks++
  return o
}
const go = (arr: Arr, id: string, c: Change) => must(transition(ctxOf(arr), id, c), `${id} ${JSON.stringify(c)}`)
/** the page holds the empty leaf and nothing that follows or keeps */
const empty = (t: Node, what: string) => {
  ok(isEmptyTree(t), `${what}: the page is empty`)
  ok(!(t as Zone).slot, `${what}: and follows nothing`)
}

/* -- 1. CLOSE THE LAST ------------------------------------------------------- */

/* Remove from workspace, the last section */
empty(go({ tree: z('a'), pages: [] }, 'a', { prop: 'exists', to: false }).arr.tree, 'Remove the last section')
/* Remove from workspace, one of two: an ordinary removal */
eq(zones(go({ tree: row(z('a'), z('b')), pages: [] }, 'a', { prop: 'exists', to: false }).arr.tree).map((x) => x.id), ['b'], 'Remove one of two leaves the other')
/* the zone's own close (TreeView ctl.close), and a docked thread's */
empty(withoutLeaf(z('a'), 'a'), 'Close the last zone')
const lone = z('a')
same(withoutLeaf(lone, 'other'), lone, 'Close of a zone not there changes nothing')
/* the server's committed removal of a docked Magnet, the last leaf */
const docked: Arr = { tree: mag('mag-only', 'Only'), pages: [] }
empty(withoutShared(docked, 'mag-only').tree, 'A committed Remove of the last docked Magnet')
/* the conversation put away from the last leaf */
const putAway = minimize({ tree: conv(), pages: [] }, T)
empty(putAway.tree, 'Put away the conversation, the last section')
/* the last section floated (Contents on This post) */
const floated = floatOut({ tree: z('a'), pages: [] }, 'a', { x: 10, y: 10, w: 300, h: 200 }, { alone: true })
empty(floated.tree, 'Float the last section')
/* Close here, every leaf: the drawn page is empty, nothing is lost from the stored tree */
const S = row(z('a'), z('b'))
const drawn = projectVisibleTree(S, new Set(['a', 'b'])) as Zone
eq([drawn.id, drawn.show, drawn.slot], [EMPTY_HERE, 'empty', undefined], 'Close here on every section draws the empty page')
same(storedTree(S, new Set(['a', 'b']), drawn), S, 'and keeps every closed section, stored')
/* and nothing was auto-opened anywhere: no window, no column, no primary */
eq(go({ tree: z('a'), pages: [] }, 'a', { prop: 'exists', to: false }).arr.focus, undefined, 'closing the last opens no window in its stead')

/* -- 2. THE EMPTY PAGE IS NO SURFACE ---------------------------------------- */

const bare: Arr = { tree: emptyZone('e1'), pages: [], focus: { column: undefined, minimized: { from: 'column', at: T } } }
eq(surfaceIds(bare), [CONVERSATION_ID], 'the surfaces of an empty page: the conversation (put away) only')
eq(derive(bare, 'compact').order, [CONVERSATION_ID], 'compact stacks no card for the empty page')
eq(surfacesOf(bare).map((s) => s.id), [], 'the lens lists no surface for it')
eq(startLens(bare, 'this-post', { kind: 'object', address: 'live:p:1' }, 'docked').shelfFor.mixed, false, 'nor shelves it beside Focus')
eq(pageLanding(bare.tree), null, 'it is not where a kept object lands')
const bareColumn: Arr = { tree: emptyZone('e1'), pages: [] }
same(makePrimary(bareColumn, 'e1'), bareColumn, 'it cannot be made primary')
eq(transition(ctxOf({ tree: emptyZone('e1'), pages: [] }), 'e1', { prop: 'exists', to: false }).ok, false, 'there is nothing to remove')

/* -- 3. WHAT COMES NEXT TAKES ITS PLACE; CLOSE IT AND THE PAGE IS EMPTY AGAIN --- */

const withWindow: Arr = { tree: emptyZone('e1'), pages: [], focus: { floats: [{ id: 'f1', zone: z('w'), x: 0, y: 0, w: 300, h: 200 }] } }
const docked1 = dockFloat(withWindow, 'f1', 'e1', 'right')
eq(zones(docked1.tree).map((x) => x.id), ['w'], 'a window docked onto the empty page becomes its only section')
eq(docked1.focus, undefined, 'and is no longer a window')
eq(zones(dockFloat(withWindow, 'f1', 'e1', 'center').tree).map((x) => x.id), ['w'], 'docked at its centre, the same')
eq(zones(splitZone(emptyZone('e1'), 'e1', 'row', z('n')).tree).map((x) => x.id), ['n'], 'a split of the empty page is the new section alone')
eq(zones(splitOuter(emptyZone('e1'), 'left', z('n'))).map((x) => x.id), ['n'], 'so is a section added at its edge')
const back = dockBack(floated, floated.focus!.floats![0].id)
eq(zones(back.tree).map((x) => x.id), ['a'], 'Dock back fills the page it left empty')
eq(zones(restore(putAway, 'leaf').tree).map((x) => x.id), [CONVERSATION_ID], 'the conversation brought back as a section is the page again')
empty(go({ tree: zones(back.tree)[0], pages: [] }, 'a', { prop: 'exists', to: false }).arr.tree, 'closing that again returns to empty')

/* -- 4. SAVED AND READ BACK EMPTY ------------------------------------------- */

const emptyArr: Arr = { tree: emptyZone('empty-1'), pages: [], focus: { floats: [magFloat('mag-a', 'Alpha', 900, 600)] } }
const layout = toLayout(emptyArr)
ok(valid(layout.tree), 'the empty page is a valid tree')
eq(layout.tree, { type: 'zone', id: 'empty-1', show: 'empty', name: 'Empty' }, 'saved as the empty leaf: no slot, nothing followed')
const read = fromLayout(JSON.parse(JSON.stringify(layout)))!
ok(read, 'read back, it is not refused as missing or broken')
eq(read.tree, emptyArr.tree, 'read back empty')
eq(read.focus?.floats?.map((f) => [f.zone.id, f.x, f.y, f.zone.level]), [['mag-a', 900, 600, 'icon']], 'its Magnet where it was, still a disc')
/* through the tab's copy: a reload of an intentionally empty page stays empty */
const h1 = new Holder(() => ({ tree: z('start'), pages: [] }))
h1.enter('place-empty', 'conversation')
await flush()
h1.edit((a) => ({ ...a, tree: withoutLeaf(a.tree, 'start') }), 'Closed start.')
empty(h1.arr.tree, 'closed in the workspace')
const h2 = new Holder(() => ({ tree: z('start'), pages: [] }))
h2.enter('place-empty', 'conversation')
await flush()
eq(h2.from, 'session', 'the reload reads the tab copy')
empty(h2.arr.tree, 'the reload is empty, not the product start')
eq(zones(h2.arr.tree).length, 1, 'with no section substituted')

/* -- 5. MAGNETS ACTIVATE ONE AT A TIME -------------------------------------- */

const two: Arr = { tree: emptyZone('empty-2'), pages: [], focus: { floats: [magFloat('mag-a', 'Alpha', 40, 40), magFloat('mag-b', 'Beta', 600, 300)] } }
const lv = (a: Arr, id: string) => stateIn(ctxOf(a), id)!.level.override ?? stateIn(ctxOf(a), id)!.level.auto
eq([lv(two, 'mag-a'), lv(two, 'mag-b')], ['icon', 'icon'], 'two dormant Magnets')
const oneOn = go(two, 'mag-a', { prop: 'level', step: 1 }).arr
ok(lv(oneOn, 'mag-a') !== 'icon', 'activating Alpha opens Alpha')
eq(lv(oneOn, 'mag-b'), 'icon', 'and leaves Beta a disc')
eq(oneOn.focus!.floats!.find((f) => f.zone.id === 'mag-b'), two.focus!.floats![1], 'Beta byte for byte unchanged')
empty(oneOn.tree, 'activating a Magnet opens no section')
eq(oneOn.focus!.floats!.length, 2, 'and no other window')
const bothOn = go(oneOn, 'mag-b', { prop: 'level', step: 1 }).arr
ok(lv(bothOn, 'mag-a') !== 'icon' && lv(bothOn, 'mag-b') !== 'icon', 'each is activated on its own')
const alphaOff = go(bothOn, 'mag-a', { prop: 'level', to: 'icon' }).arr
eq([lv(alphaOff, 'mag-a'), lv(alphaOff, 'mag-b')], ['icon', lv(bothOn, 'mag-b')], 'putting one back leaves the other open')
const alphaGone = go(oneOn, 'mag-a', { prop: 'exists', to: false }).arr
empty(alphaGone.tree, 'removing the activated Magnet returns to the empty page')
eq(alphaGone.focus!.floats!.map((f) => f.zone.id), ['mag-b'], 'with the other Magnet still there')

/* -- 6. A MAGNET MOVES ANYWHERE, STAYS A WINDOW, AND ITS PLACE IS KEPT ------- */

const far = { x: 1100, y: 640, w: 360, h: 480 }
const moved = go(two, 'mag-b', { prop: 'rect', rect: far }).arr
const mb = moved.focus!.floats!.find((f) => f.zone.id === 'mag-b')!
eq([mb.x, mb.y, mb.w, mb.h], [far.x, far.y, far.w, far.h], 'Beta is where it was put')
eq(locate(moved, 'mag-b')?.place, 'float', 'still a window: nothing docks it')
empty(moved.tree, 'and the page is still empty')
eq(moved.focus!.floats!.find((f) => f.zone.id === 'mag-a'), two.focus!.floats![0], 'Alpha did not move')
const movedBack = fromLayout(JSON.parse(JSON.stringify(toLayout(moved))))!
eq(movedBack.focus!.floats!.find((f) => f.zone.id === 'mag-b'), mb, 'its place is saved and read back')
/* through the tab's copy too */
const h3 = new Holder(() => ({ tree: z('start'), pages: [] }))
h3.enter('place-magnets', 'conversation')
await flush()
h3.edit(() => two)
h3.edit((a) => go(a, 'mag-b', { prop: 'rect', rect: far }).arr)
const h4 = new Holder(() => ({ tree: z('start'), pages: [] }))
h4.enter('place-magnets', 'conversation')
await flush()
const kept4 = h4.arr.focus!.floats!.find((f) => f.zone.id === 'mag-b')!
eq([kept4.x, kept4.y, kept4.zone.level], [far.x, far.y, 'icon'], 'a reload keeps the Magnet where it was moved, dormant')
empty(h4.arr.tree, 'on its empty page')
ok(zones(h4.arr.tree).every(isEmptyZone), 'with no section created for it')

console.log(`fluid empty workspace: ${checks} checks passed`)

function same(a: unknown, b: unknown, what: string) { assert.equal(a, b, what); checks++ }
