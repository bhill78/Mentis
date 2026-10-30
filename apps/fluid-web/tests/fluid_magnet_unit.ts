/* SURFACE TENSION P7, STAGE A: THE FIRST INTERACTIVE UNIVERSAL MAGNET
 * (plan adm-b848fa881c8d §3.10, §4 P7). What stage A builds:
 *
 *   * conversation.makeMagnet prepares a seed and goes through the generic
 *     magnet.create path; magnet.create also creates with no conversation
 *     provider; a second Make magnet reveals the first;
 *   * the client's create sends only seed, the id-less zone, the fallback
 *     and op, and takes in a `mag-` id that is not the conversation's;
 *   * the saved zone carries only id, show, name, options and level; the
 *     config is in `magnets`; no fetched content enters the layout;
 *   * the adapter registry dispatches by source kind; the live cache keeps
 *     every result's source, is keyed by Magnet (two Magnets of one
 *     conversation share nothing; two conversations never leak), and a
 *     renderer-only change reads nothing again;
 *   * the conversation adapter's search is P8's searchConversation, unchanged;
 *   * tabs are the ordered intersection, an unsupported selected type kept
 *     with its reason, Search only where a source searches;
 *   * every Magnet reports the same capability ids; only Availability varies,
 *     always with a structured reason; what this build does not run is kept,
 *     said, and never called;
 *   * icon → compact → standard → docked → float → icon by ordinary verbs,
 *     keeping the zone id, the shared renderer and the view state;
 *   * Open as workspace calls nav.openPlace(conversation) and changes no
 *     config; T2 is the registry's list; there is no Magnet-only menu. */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { Holder, toLayout, type Arr } from '../src/fluid/workspace/place'
import { keepSlot, zones, type Node, type Zone } from '../src/fluid/workspace/tree'
import { capsFor, stateIn, transition } from '../src/fluid/surface/transition'
import type { Change, Outcome, SurfaceCtx } from '../src/fluid/surface/types'
import { createRegistry } from '../src/fluid/surface/actions/registry'
import { installProviders } from '../src/fluid/surface/actions/providers'
import { bindOps, type Ops } from '../src/fluid/surface/actions/providers/ops'
import type { ActionCtx, ActionId, ActionTarget } from '../src/fluid/surface/actions/types'
import { setViewState, viewState } from '../src/fluid/surface/viewState'
import type { MagnetConfig, MagnetEnv, MagnetResult, MagnetSource, MagnetSourceAdapter } from '../src/fluid/surface/magnet/types'
import { MAGNET_CHOICES, conversationSeed } from '../src/fluid/surface/magnet/choices'
import {
  BUILD_ENV, MAGNET_ACTIONS, createAdapters, drawnMagnetRect, existingFor, magnetAvailability, newMagnetZone, notRunning, tabsOf,
} from '../src/fluid/surface/magnet/model'
import { createLive, revisionOf } from '../src/fluid/surface/magnet/live'
import { conversationAdapter, SEARCH_PAGE, type ConversationReads, type ObjectRow } from '../src/fluid/surface/magnet/conversation'
import { bindMagnetOps, installMagnets, makeMagnetFor, type MagnetOps } from '../src/fluid/surface/magnet/provider'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }
const flush = async () => { for (let i = 0; i < 6; i++) await new Promise((r) => setTimeout(r, 0)) }
const src = fileURLToPath(new URL('../src/', import.meta.url))
const read = (file: string) => readFileSync(src + file, 'utf8').replace(/\r\n/g, '\n')

const z = (id: string): Zone => ({ type: 'zone', id, show: 'objects', name: id, slot: keepSlot() })
const row = (...kids: Node[]): Node => ({ type: 'split', dir: 'row', sizes: kids.map(() => 1 / kids.length), kids })
const cfg = (id: `mag-${string}`, sources: MagnetSource[] = [{ kind: 'conversation', conversation: 'c1' }], over: Partial<MagnetConfig> = {}): MagnetConfig =>
  ({ id, ...conversationSeed('c1'), sources, ...over })

/* -- the network, recorded ---------------------------------------------------- */

type Call = { url: string; method: string; body: Record<string, any> | null }
const calls: Call[] = []
let kept: { layout: unknown; saved: number | null } = { layout: null, saved: null }
let answer: (body: Record<string, any>) => unknown = () => ({})
;(globalThis as any).fetch = async (url: string, init?: RequestInit) => {
  const method = (init?.method ?? 'GET').toUpperCase()
  const body = init?.body ? JSON.parse(String(init.body)) : null
  calls.push({ url: String(url), method, body })
  const reply = String(url).endsWith('/layouts') ? { layouts: [], defaults: { home: null, conversation: null, unnamed: null } }
    : method === 'GET' ? kept : answer(body)
  return new Response(JSON.stringify(reply), { status: 200, headers: { 'Content-Type': 'application/json' } })
}
const posts = () => calls.filter((c) => c.method === 'POST')

/* -- 1. the client's create: one operation, the server names it ----------------- */

const stored = { format: 'mentis.fluid-arrangement', version: 3, tree: row(z('a'), z('b')) }
kept = { layout: stored, saved: 100 }
const h = new Holder(() => ({ tree: z('start'), pages: [] }))
h.enter('c1', 'conversation')
await flush()
h.edit((a) => ({ ...a, conversation: { width: 444 } }))     // an unrelated unsaved edit
const made = cfg('mag-0123456789abcdef')
answer = (b) => {
  const zone = { ...b.attach.zone, id: made.id, options: { magnet: made.id } }
  return { key: 'c1', saved: 101, magnet: made, layout: { ...stored, focus: { floats: [{ id: 'w-1', zone, x: 24, y: 24, w: 360, h: 480, min: true }] }, magnets: { [made.id]: made } } }
}
const got = await h.createMagnet(conversationSeed('c1'), newMagnetZone('Tidewater'), { wideFallback: MAGNET_CHOICES.wideFallback })
const sent = posts().at(-1)!
ok(sent.url.endsWith('/arrangements/c1/magnets'), 'create posts to the generic Magnet route')
eq(Object.keys(sent.body!).sort(), ['attach', 'op', 'seed', 'wideFallback'], 'it sends the seed, the zone, the fallback and op: nothing else of the tab')
eq(sent.body!.seed, conversationSeed('c1'), 'the seed is a conversation-backed config, without an id')
eq(sent.body!.attach, { zone: { type: 'zone', show: 'magnet', name: 'Tidewater', level: 'icon' } }, 'the zone goes without an id: the server names it')
ok(!JSON.stringify(sent.body).includes('444'), 'the unrelated unsaved edit is not sent')
ok(got.id.startsWith('mag-') && got.id !== 'c1', 'the Magnet is a stable mag- id, never the conversation id')
const float = h.arr.focus?.floats?.find((f) => f.zone.id === got.id)
ok(float, 'the zone is taken in where the Brain put it')
eq(h.arr.conversation?.width, 444, 'the unrelated edit stays in the tab')
eq(h.arr.magnets?.[got.id], made, 'the config is the arrangement\'s magnets snapshot')

/* the saved zone and the layout */
const layout = toLayout(h.arr) as Record<string, any>
const savedZone = layout.focus.floats[0].zone
ok(Object.keys(savedZone).every((k) => ['type', 'id', 'show', 'name', 'options', 'level'].includes(k)), 'the saved zone carries only id, show, name, options and level')
eq(savedZone.options, { magnet: got.id }, 'it names its config, and nothing of its source')
eq(layout.magnets[got.id], made, 'the config is in magnets')
ok(!/"(parts|snippet|text|preview|author_name)"/.test(JSON.stringify(layout)), 'no post, title, file or image content enters the layout')
eq(existingFor(h.arr, 'c1'), got.id, 'the workspace knows its Magnet of c1')
eq(existingFor(h.arr, 'c2'), null, '… and has none of c2')

/* -- 2. the actions: Make magnet, magnet.create, reveal ------------------------- */

const did: string[] = []
let here: string | null = null
let existing: string | null = null
const config = new Map<string, MagnetConfig>([[made.id, made]])
const ops: MagnetOps = {
  notHere: () => here,
  config: (id) => config.get(id),
  existing: () => existing as any,
  async create(seed, name) { did.push(`create(${JSON.stringify(seed.sources)},${name})`); return { ...seed, id: 'mag-new' } },
  reveal: (id) => { did.push(`reveal(${id})`) },
  current: () => ({ conversation: 'c1', name: 'Tidewater' }),
  conversationName: (c) => (c === 'c1' ? 'Tidewater' : c),
  showTab: (id, tab) => { did.push(`tab(${id},${tab})`) },
  remove: async (id) => { did.push(`remove(${id})`) },
  adapters: () => adapters,
}
/* P3's own operations, inert: only the Magnet's are under test */
const inert: any = new Proxy({}, { get: (_t, k) => (k === 'object' ? inert : () => false) })
bindOps(inert as Ops)
const adapters = createAdapters()
const reads: string[] = []
const rows: ObjectRow[] = [
  { address: 'live:p1:fig', kind: 'figure', title: 'Chart', post: 'p1', number: 1, preview: { type: 'image/png' } },
  { address: 'live:p2:doc', kind: 'block', title: 'Spec.pdf', post: 'p2', number: 2, preview: { type: 'file' } },
  { address: 'live:p3:tbl', kind: 'block', title: 'Table', post: 'p3', number: 3 },
]
const fake: ConversationReads = {
  posts: async (c) => { reads.push(`posts(${c})`); return { ids: [`${c}-p2`, `${c}-p1`] } },
  objects: async (c) => { reads.push(`objects(${c})`); return rows },
  search: async (c, q, opts) => { reads.push(`search(${c},${q},${JSON.stringify(opts)})`); return [{ post: `${c}-p1`, number: 1, snippet: q, at: 1 }] },
  about: async (c) => { reads.push(`about(${c})`); return { title: c === 'c1' ? 'Tidewater' : 'Harbour' } },
}
adapters.register(conversationAdapter(fake))
const r = createRegistry()
installProviders(r)
const cBefore = r.everyDef([{ resource: { address: 'conversation:c1', kind: 'conversation' } }])
ok(!cBefore.some((d) => d.id === 'conversation.makeMagnet'), 'unbound, the conversation offers no Make magnet')
bindMagnetOps(ops)
const calls2: string[] = []
const actx: ActionCtx = { cls: 'wide', input: 'fine', apply: (id, c) => { calls2.push(`apply(${id},${JSON.stringify(c)})`); return { ok: false, reason: 'test' } },
  nav: { open: (a) => calls2.push(`open(${a})`), openPlace: (k) => calls2.push(`openPlace(${k})`), back: () => calls2.push('back') } }
const convT: ActionTarget = { resource: { address: 'conversation:c1', kind: 'conversation' } }
const make = r.list(convT, actx).find((x) => x.def.id === 'conversation.makeMagnet')
eq(make?.availability, { state: 'available' }, 'Make magnet is on the conversation\'s list')
await r.run('conversation.makeMagnet', convT, actx)
eq(did, ['create([{"kind":"conversation","conversation":"c1"}],Tidewater)', 'reveal(mag-new)'], 'Make magnet prepares the seed, creates through the generic path, and shows it')
did.length = 0
existing = made.id
await makeMagnetFor('c1')
eq(did, [`reveal(${made.id})`], 'a second Make magnet reveals the first and makes nothing')
existing = null
did.length = 0
const wsT: ActionTarget = { resource: { address: 'place:c1', kind: 'workspace' } }
await r.run('magnet.create', wsT, actx)
eq(did, ['create([{"kind":"conversation","conversation":"c1"}],Tidewater)', 'reveal(mag-new)'], 'magnet.create makes one with no conversation provider in the way')
here = MAGNET_CHOICES.notHere
const notHere = r.list(convT, actx).find((x) => x.def.id === 'conversation.makeMagnet')!.availability
eq(notHere, { state: 'disabled', reason: { code: 'scope', message: MAGNET_CHOICES.notHere, retryable: false } }, 'outside a conversation\'s workspace it says why, structured')
here = null

/* -- 3. a Magnet's list: the shared verbs and its own, one registry --------------- */

const arr: Arr = h.arr
const ctxOf = (a: Arr): SurfaceCtx => ({ arr: a, page: null, cls: 'wide', deviceLocal: { closed: new Set() }, session: { emphasis: {} },
  viewport: { w: 1280, h: 800 }, caps: capsFor(a, null, 'wide') })
const magT = (a: Arr): ActionTarget => ({ resource: { address: 'magnet:' + got.id, kind: 'magnet' },
  surface: { id: got.id, state: stateIn(ctxOf(a), got.id)!, caps: ctxOf(a).caps(got.id) } })
const list = r.list(magT(arr), actx)
const ids = list.map((x) => x.def.id)
for (const id of ['expand', 'dock', 'close', 'removeFromWorkspace', 'magnet.tab', 'search', 'openAsWorkspace', 'magnet.configure', 'magnet.reconfigure', 'findAction'] as ActionId[])
  ok(ids.includes(id), `a Magnet's T2 has ${id}`)
ok(!ids.includes('collapse'), 'at its disc there is nothing smaller')
eq(ids.filter((id) => id === 'removeFromWorkspace').length, 1, 'one Remove from workspace: the Magnet\'s, which removes its zone then its config')
eq(list.find((x) => x.def.id === 'magnet.configure')!.availability.state, 'disabled', 'configuration is listed, disabled with its reason, in this stage')
const before = JSON.stringify(config.get(made.id))
await r.run('openAsWorkspace', magT(arr), actx)
eq(calls2, ['openPlace(c1)'], 'Open as workspace is nav.openPlace(conversation)')
eq(JSON.stringify(config.get(made.id)), before, '… and changes no config')
await r.run('search', magT(arr), actx)
eq(did.at(-1), `tab(${got.id},search)`, 'Search opens its Search tab')
const chrome = read('fluid/surface/magnet/MagnetZone.tsx')
ok(/<(SurfaceChrome|LegacySurfaceChromeBar) target=\{target\}/.test(chrome) && /<ActionMenu target=\{target\}/.test(chrome), 'the Magnet draws the one chrome and the one T2 (the registry\'s list)')
ok(!/IconMenu|windowItems|zoneMenu/.test(chrome), 'there is no Magnet-only menu or toolbar')
ok(read('fluid/surface/actions/providers/index.ts').includes('installMagnets(r)') && read('fluid/surface/magnet/provider.ts').includes("r.provide('magnet', magnetDefs)"),
  'the Magnet provider is P7\'s, installed once')
void installMagnets

/* -- 4. icon → compact → standard → docked → float → icon -------------------------- */

const view = { surface: got.id, resource: 'magnet:' + got.id }
setViewState(view, 'tab', 'search')
setViewState(view, 'q', 'tide')
const go = (a: Arr, c: Change): Arr => {
  const o: Outcome = transition(ctxOf(a), got.id, c)
  if (!o.ok) assert.fail(`${JSON.stringify(c)}: ${o.reason}`)
  checks++
  return o.arr
}
const levelOf = (a: Arr) => { const s = stateIn(ctxOf(a), got.id)!; return s.level.override ?? s.level.auto }
const placeOf = (a: Arr) => stateIn(ctxOf(a), got.id)!.placement.kind
eq([levelOf(arr), placeOf(arr)], ['icon', 'float'], 'a new Magnet is a disc, in a window')
let a = go(arr, { prop: 'level', step: 1 })
eq([levelOf(a), placeOf(a)], ['compact', 'float'], 'Expand: the compact pane')
a = go(a, { prop: 'level', step: 1 })
eq(levelOf(a), 'standard', 'Expand again: standard')
a = go(a, { prop: 'placement', to: { kind: 'dock' } })
eq([levelOf(a), placeOf(a)], ['standard', 'dock'], 'Dock: standard, docked')
ok(zones(a.tree).some((x) => x.id === got.id), '… in the tree, under the same id')
a = go(a, { prop: 'placement', to: { kind: 'float' } })
eq(placeOf(a), 'float', 'Float: a window again')
a = go(go(a, { prop: 'level', step: -1 }), { prop: 'level', step: -1 })
eq(levelOf(a), 'icon', 'Collapse twice: the disc')
const zoneNow = a.focus!.floats!.find((f) => f.zone.id === got.id)!.zone
eq([zoneNow.id, zoneNow.options], [got.id, { magnet: got.id }], 'the zone id and its config never changed')
eq(a.magnets?.[got.id]?.presentation.renderer, 'disc', 'the shared renderer is untouched by placement and level')
eq([viewState(view, 'tab'), viewState(view, 'q')], ['search', 'tide'], 'its tab and query survive every move (view state by its id)')
eq(drawnMagnetRect('icon', { x: 10, y: 20, w: 360, h: 480 }), { x: 10, y: 20, w: MAGNET_CHOICES.disc, h: MAGNET_CHOICES.disc }, 'the disc is drawn at its window\'s corner')
eq(drawnMagnetRect('standard', { x: 10, y: 20, w: 360, h: 480 }), { x: 10, y: 20, w: 360, h: 480 }, 'standard fills the window')

/* -- 5. adapters, tabs and the live cache --------------------------------------- */

const elsewhere: string[] = []
const web: MagnetSourceAdapter = { kind: 'web', capabilities: () => new Set(['fetch', 'search', 'link']),
  fetch: async () => { elsewhere.push('web.fetch'); return { results: [] } }, search: async () => { elsewhere.push('web.search'); return { results: [] } },
  summary: async () => { elsewhere.push('web.summary'); return { title: 'web' } } }
adapters.register(web)
const live = createLive(adapters)

const m1 = cfg('mag-one')
const m2 = cfg('mag-two', undefined, { selection: { informationTypes: ['image'] } })
const l1 = await live.load(m1, BUILD_ENV)
ok(l1.results.every((x) => (x.source as { conversation: string }).conversation === 'c1'), 'every result keeps its source')
eq(l1.results.map((x) => `${x.kind}:${x.id}`), ['post:c1-p2', 'post:c1-p1', 'image:live:p1:fig', 'file:live:p2:doc'], 'posts, then images and files; neither-kind objects are left out')
eq(l1.summaries, [{ source: m1.sources[0], summary: { title: 'Tidewater', initial: 'T' } }], 'its summary: the title and the disc\'s initial')
const l2 = await live.load(m2, BUILD_ENV)
eq(l2.results.map((x) => x.id), ['live:p1:fig'], 'a second Magnet of the same conversation keeps its own selection')
reads.length = 0
await live.load(m1, BUILD_ENV)
eq(reads, [], 'a Magnet loaded again reads nothing it holds')
await live.load({ ...m1, presentation: { renderer: 'gallery' } }, BUILD_ENV)
eq(reads, [], 'a renderer-only change reads nothing')
eq(revisionOf(m1), revisionOf({ ...m1, presentation: { renderer: 'cards' } }), '… its revision is unchanged')
const both = cfg('mag-both', [{ kind: 'conversation', conversation: 'c1' }, { kind: 'conversation', conversation: 'c2' }])
const lb = await live.load(both, BUILD_ENV)
ok(lb.results.filter((x) => x.id.startsWith('c2-')).every((x) => (x.source as { conversation: string }).conversation === 'c2'), 'two conversations never leak into each other\'s source')
reads.length = 0
const hits = await live.search(m1, 'tide', BUILD_ENV)
eq(reads, [`search(c1,tide,{"limit":${SEARCH_PAGE}})`], 'search is P8\'s searchConversation(conversation, q, opts), unchanged')
eq(hits.map((x) => [x.kind, x.id]), [['hit', 'c1-p1']], 'its hits keep their source')
reads.length = 0
await live.search(m2, 'tide', BUILD_ENV)
eq(reads.length, 1, 'two Magnets of one conversation do not share a search')
live.stale('conversation:c1')
reads.length = 0
await live.load(m1, BUILD_ENV)
eq(reads, ['posts(c1)', 'objects(c1)'], 'a change heard for its source reads that source again')

/* tabs */
eq(tabsOf(m1, BUILD_ENV, adapters).map((t) => [t.id, t.availability.state]), [['post', 'available'], ['file', 'available'], ['image', 'available'], ['search', 'available']],
  'tabs: the selected types the sources can show, in order, then Search')
const forms = cfg('mag-forms', undefined, { selection: { informationTypes: ['form', 'post'] } })
const ft = tabsOf(forms, BUILD_ENV, adapters)
eq(ft.map((t) => t.id), ['post', 'form', 'search'], 'an unsupported selected type stays, in the fixed order')
const formTab = ft.find((t) => t.id === 'form')!.availability
ok(formTab.state === 'disabled' && formTab.reason.code === 'source' && formTab.reason.message.length > 0, '… disabled, with a structured reason')

/* -- 6. one capability set; what is not run -------------------------------------- */

const env = (o: Partial<MagnetEnv> = {}): MagnetEnv => ({ ...BUILD_ENV, ...o })
const matrix: Array<[string, MagnetConfig, MagnetEnv]> = [
  ['conversation', m1, env()],
  ['no read', m1, env({ permissions: new Set() })],
  ['connector', cfg('mag-c', [{ kind: 'connector', connector: 'drive' }]), env()],
  ['connector present', cfg('mag-c2', [{ kind: 'connector', connector: 'drive' }]), env({ connectors: new Set(['drive']) })],
  ['web', cfg('mag-w', [{ kind: 'web', domain: 'example.org' }]), env()],
  ['two sources', both, env()],
]
for (const [what, c, e] of matrix) {
  const av = magnetAvailability(c, e, adapters)
  eq([...av.keys()], [...MAGNET_ACTIONS], `${what}: the same capability ids`)
  for (const [id, x] of av) if (x.state === 'disabled') ok(x.reason.code && x.reason.message, `${what}: ${id} is disabled with a structured reason`)
}
eq(magnetAvailability(m1, BUILD_ENV, adapters).get('openAsWorkspace'), { state: 'available' }, 'one conversation: Open as workspace')
eq((magnetAvailability(both, BUILD_ENV, adapters).get('openAsWorkspace') as any).reason.code, 'scope', 'two conversations: not yet, with why')
eq((magnetAvailability(matrix[2][1], BUILD_ENV, adapters).get('search') as any).reason.code, 'connector', 'a missing connector says so')
eq((magnetAvailability(m1, env({ permissions: new Set() }), adapters).get('magnet.tab') as any).reason.code, 'permission', 'no read permission says so')

const asked = cfg('mag-asked', [{ kind: 'conversation', conversation: 'c1' }, { kind: 'web', url: 'https://example.org' }, { kind: 'connector', connector: 'drive' }], {
  collection: { mode: 'continuous' }, synthesis: { mode: 'on-new-information' }, notifications: { newItems: true, changes: false, failures: true },
})
eq(notRunning(asked, BUILD_ENV, adapters).map((x) => [x.facet, x.reason.code]),
  [['source', 'source'], ['source', 'connector'], ['collection', 'runtime'], ['synthesis', 'runtime'], ['notifications', 'runtime']],
  'web, connector, continuous collection, synthesis and notifications are kept and said, each with its reason')
eq(notRunning(m1, BUILD_ENV, adapters), [], 'a plain conversation Magnet runs as asked')
elsewhere.length = 0
reads.length = 0
const la = await live.load(asked, BUILD_ENV)
await live.search(asked, 'x', BUILD_ENV)
eq(elsewhere, [], 'nothing is called for the web source')
ok(reads.every((x) => /\(c1[,)]/.test(x)), 'only the conversation is read')
ok(la.results.every((x) => x.source.kind === 'conversation'), 'and only its results are shown')

console.log(`fluid magnet: ${checks} checks passed`)
