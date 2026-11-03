/* Arrangement v3 on the client (Surface Tension P2, plan §3.7 and §3.9):
 * the three version gates, toLayout v3, a v2 -> v3 load and save, the
 * Make room precedence, what a full, scoped and shared-zone save SEND, and
 * the missing-config reason a Magnet zone shows without fetching. */
import assert from 'node:assert/strict'
import { Holder, MAGNET_CONFIG_MISSING, fromLayout, storedMagnet, toLayout, withShared, withoutShared, type Arr } from '../src/fluid/workspace/place'
import { keepSlot, zones, type Node, type Zone } from '../src/fluid/workspace/tree'
import { effectiveMakeRoom, withMakeRoom } from '../src/fluid/surface/settings'
import { MAKE_ROOM, type DevicePlacement, type MakeRoom } from '../src/fluid/surface/types'
import type { MagnetConfig, MagnetZone } from '../src/fluid/surface/magnet/types'
import { toastSnapshot } from '../src/fluid/frame/toasts'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const same = (a: unknown, b: unknown, what: string) => { assert.equal(a, b, what); checks++ }
const canon = (v: unknown): string => JSON.stringify(v, (_k, x) =>
  x && typeof x === 'object' && !Array.isArray(x) ? Object.fromEntries(Object.keys(x).sort().map((k) => [k, x[k]])) : x)
const z = (id: string, items: string[] = []): Zone => ({ type: 'zone', id, show: 'objects', name: id, slot: keepSlot(items) })
const row = (...kids: Node[]): Node => ({ type: 'split', dir: 'row', sizes: kids.map(() => 1 / kids.length), kids })
const mz = (id: `mag-${string}`): MagnetZone => ({ type: 'zone', id, show: 'magnet', name: 'Board', options: { magnet: id } })
const magnetIdsForTest = (a: Arr): Set<string> => new Set([
  ...zones(a.tree), ...(a.focus?.floats ?? []).map((f) => f.zone),
].filter((zone) => zone.show === 'magnet').map((zone) => zone.id))
const cfg = (id: `mag-${string}`): MagnetConfig => ({
  id, sources: [{ kind: 'conversation', conversation: 'c1' }], selection: {}, collection: { mode: 'one-time' },
  synthesis: { mode: 'manual' }, notifications: { newItems: false, changes: false, failures: false }, presentation: { renderer: 'disc' },
})
const dp = (order: string[], place: DevicePlacement['place'], level: DevicePlacement['level'] = {}, updatedAt = 1): DevicePlacement =>
  ({ order, place, level, updatedAt })
const flush = async () => { for (let i = 0; i < 6; i++) await new Promise((r) => setTimeout(r, 0)) }

/* -- the network, recorded ---------------------------------------------------- */

type Call = { url: string; method: string; body: Record<string, unknown> | null }
const calls: Call[] = []
let kept: { layout: unknown; saved: number | null } = { layout: null, saved: null }
let answer: (body: Record<string, unknown>) => unknown = () => ({})
let answerStatus = 200
let answerGate: Promise<void> | null = null
;(globalThis as any).fetch = async (url: string, init?: RequestInit) => {
  const method = (init?.method ?? 'GET').toUpperCase()
  const body = init?.body ? JSON.parse(String(init.body)) : null
  calls.push({ url: String(url), method, body })
  if (method === 'POST' && answerGate) await answerGate
  const reply = String(url).endsWith('/layouts') ? { layouts: [], defaults: { home: null, conversation: null, unnamed: null } }
    : method === 'GET' ? kept : answer(body)
  return new Response(JSON.stringify(reply), { status: method === 'GET' ? 200 : answerStatus, headers: { 'Content-Type': 'application/json' } })
}
const posts = () => calls.filter((c) => c.method === 'POST')

/* -- 1. the version gates and toLayout ----------------------------------------- */

const v2 = {
  format: 'mentis.fluid-arrangement', version: 2,
  tree: row(z('a', ['live:p:1']), z('b')),
  pages: [{ id: 'p1', title: 'P1', tree: z('pz', ['brain:ent-1']) }],
  conversation: { width: 480, replies: 300 },
  appearance: { panel: 'tinted', content: 'solid', opacity: 0.5 },
  focus: { floats: [{ id: 'w1', zone: z('f1'), x: 10, y: 20, w: 300, h: 200, min: true }], previous: ['a'] },
  setAside: [z('aside')],
}
const fromV2 = fromLayout(v2)!
same(toLayout(fromV2).version, 3, 'toLayout writes version 3')
eq(canon(toLayout(fromV2)), canon({ ...v2, version: 3 }), 'a v2 arrangement loads unchanged and is saved as v3 carrying everything')
same(fromLayout({ ...v2, version: 1 }) !== null, true, 'fromLayout reads version 1')
same(fromLayout({ ...v2, version: 4 }), null, 'fromLayout still refuses a later version')
same(fromLayout({ ...v2, presentations: { medium: dp(['a'], { a: 'stack' }) } })!.presentations, undefined, 'a v3 field in a v2 document is not read')

const v3 = {
  format: 'mentis.fluid-arrangement', version: 3,
  tree: row({ ...z('a'), level: 'compact' } as Zone, mz('mag-one') as unknown as Zone),
  presentations: { medium: dp(['a', 'mag-one'], { a: 'dock', 'mag-one': 'stack' }, { a: 'expanded' }, 7),
    compact: dp(['mag-one'], { 'mag-one': 'sheet' }, {}, 8) },
  spatial: { makeRoom: 'expand' },
  magnets: { 'mag-one': cfg('mag-one') },
}
const fromV3 = fromLayout(v3)!
eq(canon(toLayout(fromV3)), canon(v3), 'a v3 arrangement round-trips presentations, spatial, zone level and the magnets snapshot')

/* -- 2. Make room: the workspace override, then the global default, then Off -- */

for (const own of [undefined, ...MAKE_ROOM] as (MakeRoom | undefined)[]) {
  for (const global of [undefined, ...MAKE_ROOM] as (MakeRoom | undefined)[]) {
    const a = withMakeRoom({ tree: z('s'), pages: [] }, own)
    same(effectiveMakeRoom(a, global), own ?? global ?? 'off', `effectiveMakeRoom(${own}, ${global})`)
  }
}
same(withMakeRoom({ tree: z('s'), pages: [], spatial: { makeRoom: 'drag' } }, undefined).spatial, undefined, 'clearing the override uses the default')

/* -- 3. a missing configuration: the reason, and no fetch ---------------------- */

{
  const before = calls.length
  const got = storedMagnet(fromV3, 'mag-gone')
  eq(got, { ok: false, reason: MAGNET_CONFIG_MISSING }, 'a Magnet zone without a stored config shows the missing reason')
  eq(MAGNET_CONFIG_MISSING, { code: 'state', message: 'This workspace refers to a Magnet configuration that is missing.', retryable: true }, 'the reason as §3.7 words it')
  eq(storedMagnet(fromV3, 'mag-one'), { ok: true, config: cfg('mag-one') }, 'a stored config is found')
  same(calls.length, before, 'the recovery body fetches nothing')
}

/* -- 4. keepShape and restore accept 3; a later version is left alone ---------- */

const start = (): Arr => ({ tree: z('start'), pages: [] })
{
  kept = { layout: v3, saved: 100 }
  const h = new Holder(start)
  h.enter('ent-v3', 'conversation')
  await flush()
  same(h.from, 'saved', 'a saved v3 arrangement is read')
  same(h.changed(), false, 'and kept as its saved shape (keepShape accepts 3)')
  h.edit((a) => ({ ...a, tree: z('elsewhere') }))
  await h.restoreSaved()
  same(h.arr.tree.type, 'split', 'restore accepts 3')

  kept = { layout: { ...v3, version: 4 }, saved: 100 }
  const later = new Holder(start)
  later.enter('ent-v4', 'conversation')
  await flush()
  const before = posts().length
  await later.save('wide')
  same(posts().length, before, 'a saved later version is never overwritten')
}

/* -- 5. what each save sends ---------------------------------------------------- */

/* A wide full save: v3, without the narrower records the server keeps. */
{
  kept = { layout: v3, saved: 100 }
  const h = new Holder(start)
  h.enter('ent-wide', 'conversation')
  await flush()
  h.edit((a) => ({ ...a, conversation: { width: 512 } }))
  answer = (b) => ({ key: 'ent-wide', saved: 101, layout: { ...(b.layout as object), presentations: v3.presentations } })
  await h.save('wide')
  const sent = posts().at(-1)!
  eq(Object.keys(sent.body!).sort(), ['layout', 'op'], 'a wide Save is a full save')
  same((sent.body!.layout as any).version, 3, 'of a v3 layout')
  same('presentations' in (sent.body!.layout as object), false, 'that never sends the narrower classes\' records')
  eq(h.arr.presentations, fromV3.presentations, 'the records the Brain keeps are taken back in')
  same(h.changed(), false, 'and the place is saved')
}

/* A compact Save: that class's record and nothing else. */
{
  kept = { layout: v3, saved: 100 }
  const h = new Holder(start)
  h.enter('ent-compact', 'conversation')
  await flush()
  const mine = dp(['a', 'mag-one'], { a: 'stack', 'mag-one': 'launcher' }, {}, 9)
  /* this tab's compact record (P5 keeps it in the Holder's `devices`) */
  h.edit((a) => ({ ...a, tree: z('wide-dirty') }))
  h.devices = { ...h.devices, compact: mine }
  answer = (b) => ({ key: 'ent-compact', saved: 102, layout: { ...v3, presentations: { ...v3.presentations, compact: b.presentation } } })
  await h.save('compact')
  const sent = posts().at(-1)!
  eq(Object.keys(sent.body!).sort(), ['op', 'presentation', 'scope'], 'a compact Save is a scoped save')
  same(sent.body!.scope, 'compact', 'of its own class')
  eq(sent.body!.presentation, mine, 'carrying that class\'s record only')
  same(JSON.stringify(sent.body).includes('wide-dirty'), false, 'and no wide snapshot')
  same((h.arr.tree as Zone).id, 'wide-dirty', 'the wide edit stays in this tab')
  same(h.changed(), true, 'still unsaved')
}

/* An absent class record is not an implicit reset. P5 creates these records. */
{
  kept = { layout: v2, saved: 100 }
  const h = new Holder(start)
  h.enter('ent-no-phone', 'conversation')
  await flush()
  const before = posts().length
  await h.save('compact')
  same(posts().length, before, 'an absent phone record sends no scoped save')
  same(toastSnapshot()?.text, 'Nothing was saved for this phone: this tab has no arrangement for that screen size yet.', 'and says honestly that nothing was saved')
}

/* An unreadable stored file is refused without advancing this tab to saved. */
{
  kept = { layout: v2, saved: 100 }
  const h = new Holder(start)
  h.enter('ent-unreadable', 'conversation')
  await flush()
  h.edit((a) => ({ ...a, conversation: { width: 501 } }))
  answerStatus = 409
  answer = () => ({ error: 'the saved arrangement could not be read; it was left as it is', kind: 'Unreadable',
    reason: { code: 'unreadable', message: 'the saved arrangement could not be read; it was left as it is', retryable: false } })
  await h.save('wide')
  same(h.changed(), true, 'an unreadable refusal leaves the tab changed')
  same(toastSnapshot()?.text, "The stored arrangement can't be read and was not overwritten.", 'and explains that the stored copy was not overwritten')
  answerStatus = 200
}

/* A phone removal and addition are projected into a stale desk after Save. */
{
  kept = { layout: v3, saved: 100 }
  const removed = new Holder(start)
  removed.enter('ent-phone-removed', 'conversation')
  await flush()
  removed.edit((a) => ({ ...a, conversation: { width: 502 } }))
  answer = (b) => ({ key: 'ent-phone-removed', saved: 101,
    layout: toLayout(withoutShared(fromLayout(b.layout)!, 'mag-one')) })
  await removed.save('wide')
  same(magnetIdsForTest(removed.arr).has('mag-one'), false, 'a phone-removed Magnet leaves the desk tree after Save')
  same(removed.changed(), false, 'the reconciled desk is marked saved')

  const noMagnet = { ...v3, tree: z('a'), presentations: undefined, magnets: undefined }
  kept = { layout: noMagnet, saved: 110 }
  const added = new Holder(start)
  added.enter('ent-phone-added', 'conversation')
  await flush()
  added.edit((a) => ({ ...a, conversation: { width: 503 } }))
  const addedZone = mz('mag-added') as unknown as Zone
  answer = (b) => ({ key: 'ent-phone-added', saved: 111, layout: {
    ...(b.layout as object),
    focus: { floats: [{ id: 'w-added', zone: addedZone, x: 24, y: 24, w: 360, h: 480, min: true }] },
    magnets: { 'mag-added': cfg('mag-added') },
  } })
  await added.save('wide')
  same(magnetIdsForTest(added.arr).has('mag-added'), true, 'a phone-added Magnet enters the desk tree after Save')
  same(added.changed(), false, 'the desk is saved only after its tree matches')

  /* A later tab edit is not replaced by the response; shared membership is
     still projected, and the later edit remains unsaved. */
  kept = { layout: noMagnet, saved: 120 }
  const later = new Holder(start)
  later.enter('ent-phone-added-later-edit', 'conversation')
  await flush()
  later.edit((a) => ({ ...a, conversation: { width: 510 } }))
  let releaseAnswer!: () => void
  answerGate = new Promise<void>((resolve) => { releaseAnswer = resolve })
  answer = (b) => ({ key: 'ent-phone-added-later-edit', saved: 121, layout: {
    ...(b.layout as object),
    focus: { floats: [{ id: 'w-added', zone: addedZone, x: 24, y: 24, w: 360, h: 480, min: true }] },
    magnets: { 'mag-added': cfg('mag-added') },
  } })
  const saving = later.save('wide')
  await flush()
  later.edit((a) => ({ ...a, conversation: { width: 511 } }))
  releaseAnswer()
  await saving
  answerGate = null
  same(later.arr.conversation?.width, 511, 'an edit made after Save stays in the tab')
  same(magnetIdsForTest(later.arr).has('mag-added'), true, 'the concurrent phone addition is still projected')
  same(later.changed(), true, 'the later edit remains unsaved')

  /* The Brain may restore a Magnet outside the docked tree or a window. A
     response for that older snapshot must not replace edits made meanwhile. */
  kept = { layout: noMagnet, saved: 130 }
  const restoredAside = new Holder(start)
  restoredAside.enter('ent-phone-restored-aside-later-edit', 'conversation')
  await flush()
  restoredAside.edit((a) => ({ ...a, conversation: { width: 520 } }))
  answerGate = new Promise<void>((resolve) => { releaseAnswer = resolve })
  answer = (b) => ({ key: 'ent-phone-restored-aside-later-edit', saved: 131, layout: {
    ...(b.layout as object), setAside: [addedZone], magnets: { 'mag-added': cfg('mag-added') },
  } })
  const savingAside = restoredAside.save('wide')
  await flush()
  restoredAside.edit((a) => ({ ...a, conversation: { width: 521 } }))
  releaseAnswer()
  await savingAside
  answerGate = null
  same(restoredAside.arr.conversation?.width, 521, 'a later edit survives when the Brain restores a set-aside Magnet')
  same(restoredAside.arr.setAside?.some((zone) => zone.id === 'mag-added'), true, 'the restored Magnet is reconciled set aside')
  same(restoredAside.changed(), true, 'the later edit keeps the restored tab changed')
  same(toastSnapshot()?.text, 'Saved this arrangement as it was when you pressed Save; what you changed since is still only in this tab.', 'the toast says the later edit is still tab-only')

  /* When the kept Magnet cannot be projected at all (a page this tab does not
     have), a tab edited during Save keeps its edit instead of the kept copy. */
  kept = { layout: noMagnet, saved: 140 }
  const unprojected = new Holder(start)
  unprojected.enter('ent-phone-restored-page-later-edit', 'conversation')
  await flush()
  unprojected.edit((a) => ({ ...a, conversation: { width: 530 } }))
  answerGate = new Promise<void>((resolve) => { releaseAnswer = resolve })
  answer = (b) => ({ key: 'ent-phone-restored-page-later-edit', saved: 141, layout: {
    ...(b.layout as object), pages: [{ id: 'p-elsewhere', title: 'Elsewhere', tree: row(z('p-start'), addedZone) }],
    magnets: { 'mag-added': cfg('mag-added') },
  } })
  const savingPage = unprojected.save('wide')
  await flush()
  unprojected.edit((a) => ({ ...a, conversation: { width: 531 } }))
  releaseAnswer()
  await savingPage
  answerGate = null
  same(unprojected.arr.conversation?.width, 531, 'a later edit survives a Magnet the tab cannot place')
  same(unprojected.changed(), true, 'and the tab stays changed')
  same(toastSnapshot()?.text, 'Saved this arrangement as it was when you pressed Save; what you changed since is still only in this tab.', 'the toast says the later edit is still tab-only')

  /* A zone-limit refusal on a full save leaves the tab changed and says so. */
  kept = { layout: noMagnet, saved: 150 }
  const full = new Holder(start)
  full.enter('ent-full-limit', 'conversation')
  await flush()
  full.edit((a) => ({ ...a, conversation: { width: 540 } }))
  answerStatus = 422
  answer = () => ({ error: 'this workspace already has 12 zones', refused: true, key: 'ent-full-limit',
    reason: { code: 'limit', message: 'this workspace already has 12 zones', retryable: true } })
  await full.save('wide')
  answerStatus = 200
  same(full.changed(), true, 'a limit refusal leaves the tab changed')
  same(toastSnapshot()?.text, 'Not saved: this workspace already has 12 zones. Your changes are still only in this tab.', 'and says why it was not saved')
}

/* Make magnet from compact, nothing stored yet: the patch, the named id's
 * entry and the resolved base -- never the session's dirty state. */
{
  kept = { layout: null, saved: null }
  const h = new Holder(start)
  h.enter('ent-new', 'conversation')
  await flush()
  h.edit((a) => ({ ...a, tree: row(z('start'), z('wide-dirty')), conversation: { width: 333 },
    spatial: { makeRoom: 'drag' } }))
  /* a pending compact record in this tab (P5 keeps it in the Holder's `devices`) */
  h.devices = { compact: dp(['other-zone'], { 'other-zone': 'sheet' }, {}, 3) }
  const zone = mz('mag-new') as unknown as Zone
  const committed = {
    format: 'mentis.fluid-arrangement', version: 3, tree: z('start'),
    focus: { floats: [{ id: 'w-1', zone, x: 24, y: 24, w: 360, h: 480, min: true }] },
    presentations: { compact: dp(['mag-new'], { 'mag-new': 'stack' }, {}, 50) },
    magnets: { 'mag-new': cfg('mag-new') },
  }
  answer = () => ({ key: 'ent-new', saved: 103, layout: committed })
  await h.patchShared({ op: 'add', zone }, { scope: 'compact', presentation: { place: 'stack' } })
  const sent = posts().at(-1)!
  eq(Object.keys(sent.body!).sort(), ['base', 'op', 'presentation', 'scope', 'sharedZone'], 'the patch carries only sharedZone, scope, the named entry, base and op')
  eq(sent.body!.sharedZone, { op: 'add', zone }, 'the one shared zone')
  eq(sent.body!.presentation, { place: 'stack' }, 'only the named id\'s own placement')
  eq(sent.body!.base, toLayout(start()), 'the base is the resolved tier, before unsaved edits')
  for (const dirty of ['wide-dirty', 'other-zone', '333', 'drag']) {
    same(JSON.stringify(sent.body).includes(dirty), false, `unrelated dirty state (${dirty}) is not submitted`)
  }
  eq(zones(h.arr.tree).map((x) => x.id), ['start', 'wide-dirty'], 'the dirty wide tree stays in this tab')
  same(h.arr.focus?.floats?.[0]?.zone.id, 'mag-new', 'the committed zone is projected where the Brain put it')
  eq(h.devices.compact?.order, ['mag-new', 'other-zone'], 'with its own entry beside the pending ones')
  eq(h.devices.compact?.place, { 'other-zone': 'sheet', 'mag-new': 'stack' }, 'pending entries kept')
  eq(h.arr.magnets, committed.magnets, 'the magnets snapshot is the Brain\'s')
  same(h.arr.spatial?.makeRoom, 'drag', 'pending spatial kept')
  same(h.changed(), true, 'the other edits are still unsaved')

  /* Remove from workspace, now that something is stored: no base. */
  const removed = { ...committed, focus: undefined, presentations: { compact: dp([], {}, {}, 51) } }
  answer = () => ({ key: 'ent-new', saved: 104, layout: removed })
  await h.patchShared({ op: 'remove', id: 'mag-new' }, { scope: 'compact' })
  const gone = posts().at(-1)!
  eq(Object.keys(gone.body!).sort(), ['op', 'scope', 'sharedZone'], 'a remove carries the named id only')
  eq(gone.body!.sharedZone, { op: 'remove', id: 'mag-new' }, 'the one shared zone')
  same(h.arr.focus?.floats, undefined, 'its window is gone here')
  eq(h.devices.compact?.order, ['other-zone'], 'its entry is gone; the pending one stays')
  eq(zones(h.arr.tree).map((x) => x.id), ['start', 'wide-dirty'], 'the dirty wide tree still stays')
}

/* -- 6. the projections on their own -------------------------------------------- */

{
  const a: Arr = {
    tree: row(z('s'), mz('mag-x') as unknown as Zone), pages: [{ id: 'p', title: 'P', tree: mz('mag-x') as unknown as Zone }],
    focus: { primary: 'mag-x', previous: ['s', 'mag-x'] },
    presentations: { medium: dp(['mag-x', 's'], { 'mag-x': 'dock', s: 'stack' }, { 'mag-x': 'icon' }) },
  }
  const out = withoutShared(a, 'mag-x')
  eq(zones(out.tree).map((x) => x.id), ['s'], 'removed from the tree; the neighbour takes its room')
  same(zones(out.pages[0].tree).length === 1 && zones(out.pages[0].tree)[0].id !== 'mag-x', true, 'a page left empty gets the empty home leaf')
  eq(out.focus, { previous: ['s'] }, 'primary and history no longer name it')
  eq(out.presentations?.medium, dp(['s'], { s: 'stack' }), 'nor does any class record')

  const docked: Arr = { tree: row(z('s'), mz('mag-y') as unknown as Zone), pages: [], magnets: { 'mag-y': cfg('mag-y') } }
  const into = withShared({ tree: z('s'), pages: [] }, docked, 'mag-y')
  eq(zones(into.tree).map((x) => x.id), ['s', 'mag-y'], 'a zone the Brain docked is docked here too')

  const setAside = mz('mag-aside') as unknown as Zone
  const asideInto = withShared({ tree: z('s'), pages: [] }, { tree: z('s'), pages: [], setAside: [setAside] }, 'mag-aside')
  eq(asideInto.setAside?.map((x) => x.id), ['mag-aside'], 'a zone the Brain set aside is set aside here too')

  const column = mz('mag-column') as unknown as Zone
  const columnInto = withShared({ tree: z('s'), pages: [] }, { tree: z('s'), pages: [], focus: { column } }, 'mag-column')
  same(columnInto.focus?.column?.id, 'mag-column', 'a zone the Brain put in the column is put in the column here too')

  const pageZone = mz('mag-page') as unknown as Zone
  const pageInto = withShared(
    { tree: z('s'), pages: [{ id: 'p', title: 'P', tree: z('p-start') }] },
    { tree: z('s'), pages: [{ id: 'p', title: 'P', tree: row(z('p-start'), pageZone) }] },
    'mag-page',
  )
  eq(zones(pageInto.pages[0].tree).map((x) => x.id), ['p-start', 'mag-page'], 'a zone the Brain put on a page is put on that page here too')
  assert.throws(() => withShared({ tree: z('s'), pages: [] }, { tree: z('s'), pages: [] }, 'mag-none'), /keeps no zone/)
  checks++
}

console.log(`fluid_arrangement_v3_unit: ${checks} checks passed`)
