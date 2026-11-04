/* THE WORKSPACE CLIENT (package C3), over the accepted doors of
 * docs/magnets/M1-contract.md, with `fetch` answered here:
 *
 *   1. each door's path and body, an operation key on every write;
 *   2. a retry after a lost answer is the same operation; an answered one isn't;
 *   3. 404, 410, 409, 422 and replay each stay what they were;
 *   4. a request from a workspace: `objects` ordered, omitted for the whole
 *      workspace, a destination only where named, and no Magnet ever primary
 *      (mocked in E2's fixed shape: nothing here depends on the server having it);
 *   5. a Magnet in several workspaces is several lists naming one id;
 *   6. the layout is kept under the `wsp-` key, from a start of its own;
 *   7. rows say curated and where it came from, and read no reference. */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import {
  WorkspaceRefusal, addObject, createWorkspace, destinationHeld, destinationOf, destinationOptions, destinationValue, isWorkspaceId,
  listWorkspaces, once, readWorkspace, refusalOf, removeObject, renameWorkspace, reorderObjects, sendRequest, workspaceRequest,
  type Manifest, type WorkspaceObject,
} from '../src/fluid/workspaces/client'
import { add, heldWorkspace, moved, newWorkspace, openWorkspace, remove, reorder } from '../src/fluid/workspaces/state'
import { chosenBy } from '../src/fluid/workspaces/doors'
import ObjectRows, { provenanceWords, type RowActs } from '../src/fluid/workspaces/ObjectRows'
import { Holder, sharedFromKept, toLayout, workspaceStart, workspace, type Arr } from '../src/fluid/workspace/place'
import { zones } from '../src/fluid/workspace/tree'
import { isMagnetZone } from '../src/fluid/surface/magnet/model'
import { store } from '../src/fluid/store'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }
const src = fileURLToPath(new URL('../src/', import.meta.url))
const read = (file: string) => readFileSync(src + file, 'utf8').replace(/\r\n/g, '\n')

/* -- fetch, answered here ---------------------------------------------------------- */
type Asked = { path: string; method: string; body: any; client: string | null }
let asked: Asked[] = []
let answer: (a: Asked) => { status: number; body: unknown } | 'lost' = () => ({ status: 200, body: {} })
globalThis.fetch = (async (url: string, init: RequestInit = {}) => {
  const a: Asked = {
    path: String(url), method: init.method ?? 'GET', body: init.body ? JSON.parse(String(init.body)) : undefined,
    client: new Headers(init.headers).get('X-Mentis-Client'),
  }
  asked.push(a)
  const got = answer(a)
  if (got === 'lost') throw new TypeError('network')
  return new Response(JSON.stringify(got.body), { status: got.status })
}) as typeof fetch
const last = () => asked[asked.length - 1]
const reset = () => { asked = [] }

const WID = 'wsp-00112233aabbccdd'
const MAG = 'mag-00112233445566aa'
const CONV = 'ent-2865e11386f6'
const object = (id: string, kind: string, ref: string, over: Partial<WorkspaceObject> = {}): WorkspaceObject =>
  ({ id, kind, ref, curated: true, provenance: { source: { kind, ref } }, ...over })
const manifest = (over: Partial<Manifest> = {}): Manifest =>
  ({ id: WID, name: 'Reef', revision: 1, created: 1, updated: 1, objects: [], ...over })
const fine = (m: Manifest, more: object = {}) => ({ status: 200, body: { id: m.id, manifest: m, changed: true, replayed: false, ...more } });

/* -- 1. each door ------------------------------------------------------------------- */
{
  ok(isWorkspaceId(WID), 'a wsp- id is a workspace key')
  for (const no of [CONV, 'wsp-', 'WSP-1', 'wsp-A', 'home', null, 3]) ok(!isWorkspaceId(no), `${no} is no workspace key`)

  answer = () => ({ status: 200, body: { workspaces: [{ id: WID, name: 'Reef', objects: 2, revision: 3, updated: 9 }, { id: 'wsp-bad', unreadable: 'not JSON' }] } })
  const rows = await listWorkspaces()
  eq(last().path, '/fluid/api/workspaces', 'list: its door')
  eq(last().method, 'GET', 'list: a read')
  eq(last().client, '1', "the client's header, on a read")
  eq(rows[1].unreadable, 'not JSON', 'an unreadable one is listed, saying why')

  answer = () => fine(manifest())
  await readWorkspace(WID)
  eq(last().path, `/fluid/api/workspaces/${WID}`, 'read: its door')

  await createWorkspace()
  eq(last().path, '/fluid/api/workspaces', 'create: its door')
  eq(last().method, 'POST', 'create: a write')
  eq(Object.keys(last().body), ['op'], 'blank is neither objects nor from, and carries no id')
  ok(typeof last().body.op === 'string' && last().body.op, 'create: an operation key')
  eq(last().client, '1', "the client's header, on a write")

  await createWorkspace({ name: 'Reef', from: { magnet: MAG } })
  eq(last().body.from, { magnet: MAG }, 'created from one Magnet')
  eq(last().body.name, 'Reef', 'with its name')
  ok(!('objects' in last().body), 'the seed is the door\'s to write: no object is sent')
  await createWorkspace({ from: { conversation: CONV } })
  eq(last().body.from, { conversation: CONV }, 'created from one Conversation')

  await renameWorkspace(WID, 'Atoll')
  eq([last().path, last().body.name], [`/fluid/api/workspaces/${WID}/rename`, 'Atoll'], 'rename')
  ok(last().body.op, 'rename: an operation key')

  const pick = chosenBy('ent-aaaaaaaaaaaa', 'magnet', MAG)
  await addObject(WID, pick)
  eq(last().path, `/fluid/api/workspaces/${WID}/objects`, 'add: its door')
  eq(last().body.object, { kind: 'magnet', ref: MAG, provenance: { source: { kind: 'participant', ref: 'ent-aaaaaaaaaaaa' }, by: 'ent-aaaaaaaaaaaa' } },
    'add: chosen by somebody, as the manifest says that; no id, no time, no curated of its own')
  ok(last().body.op, 'add: an operation key')

  await removeObject(WID, 'wob-0011223344556677')
  eq(last().path, `/fluid/api/workspaces/${WID}/objects/wob-0011223344556677/remove`, 'remove: its door')
  ok(last().body.op, 'remove: an operation key')

  await reorderObjects(WID, ['wob-b', 'wob-a'])
  eq([last().path, last().body.order], [`/fluid/api/workspaces/${WID}/reorder`, ['wob-b', 'wob-a']], 'reorder: every id, in the new order')
  ok(last().body.op, 'reorder: an operation key')

  eq(moved(['a', 'b', 'c'], 'c', -1), ['a', 'c', 'b'], 'moved up')
  eq(moved(['a', 'b', 'c'], 'a', 2), ['b', 'c', 'a'], 'moved by more than one')
  eq(moved(['a', 'b', 'c'], 'a', -1), ['a', 'b', 'c'], "the first can't go up")
  eq(moved(['a', 'b', 'c'], 'c', 1), ['a', 'b', 'c'], "the last can't go down")
  eq(moved(['a'], 'gone', 1), ['a'], 'one not there moves nothing')
}

/* -- 2. one operation key per occurrence --------------------------------------------- */
{
  reset()
  answer = () => 'lost'
  await assert.rejects(renameWorkspace(WID, 'Lost'), (e: WorkspaceRefusal) => e.refusal === 'lost' && e.status === null)
  const first = last().body.op
  answer = () => fine(manifest({ name: 'Lost' }))
  await renameWorkspace(WID, 'Lost')
  eq(last().body.op, first, 'a retry after a lost answer is the same operation')
  await renameWorkspace(WID, 'Lost')
  ok(last().body.op !== first, 'once answered, the same words again are a new occurrence')

  answer = () => 'lost'
  await assert.rejects(renameWorkspace(WID, 'One'))
  const one = last().body.op
  await assert.rejects(renameWorkspace(WID, 'Other'))
  ok(last().body.op !== one, 'another request never takes a lost one\'s key')

  answer = () => ({ status: 410, body: { error: 'workspace was deleted', kind: 'Gone' } })
  await assert.rejects(renameWorkspace(WID, 'Refused'))
  const refused = last().body.op
  await assert.rejects(renameWorkspace(WID, 'Refused'))
  ok(last().body.op !== refused, 'a key refused is not sent again')

  let tried = 0
  await once('sig', async () => { tried++ })
  eq(tried, 1, 'once runs it once')
}

/* -- 3. why not, each its own -------------------------------------------------------- */
{
  const cases: [number, object, string][] = [
    [404, { error: 'no workspace wsp-x', kind: 'NotFound' }, 'missing'],
    [410, { error: 'workspace wsp-x was deleted', kind: 'Gone' }, 'gone'],
    [409, { error: 'not valid JSON', kind: 'Unreadable' }, 'unreadable'],
    [422, { error: 'operation key already used for a different request', kind: 'Conflict', refused: true }, 'conflict'],
    [422, { error: 'this operation key was already used for a different request', op: 'k', first: 'opr-1', refused: true }, 'conflict'],
    [422, { error: 'Missing Magnet', refused: true, reason: { code: 'state' } }, 'declined'],
    [400, { error: 'name: too long' }, 'malformed'],
  ]
  const words = new Set<string>()
  for (const [status, body, kind] of cases) {
    const r = refusalOf(status, body as never)
    eq(r.refusal, kind, `${status} ${JSON.stringify(body)} is ${kind}`)
    eq(r.status, status, 'it keeps its status')
    eq(r.said, (body as { error: string }).error, "it keeps the server's own words")
    ok(r.message.includes((body as { error: string }).error), 'and says them')
    words.add(r.message.split('.')[0])
  }
  eq(new Set(cases.map(([, , k]) => k)).size, 6, 'six distinct refusals')
  ok(words.size >= 5, 'worded apart')
  eq(refusalOf(503, null).refusal, 'lost', 'a server that gave no verdict is not a refusal of the request')

  /* in state: a refusal is held, and one saying it is gone leaves nothing to show */
  answer = () => fine(manifest({ revision: 5, objects: [object('wob-a', 'magnet', MAG)] }))
  await openWorkspace(WID)
  eq(heldWorkspace(WID).manifest?.revision, 5, 'opened')
  answer = () => ({ status: 422, body: { error: 'used', kind: 'Conflict', refused: true } })
  await assert.rejects(remove(WID, 'wob-a'))
  eq(heldWorkspace(WID).refusal?.refusal, 'conflict', 'a conflict is held')
  eq(heldWorkspace(WID).manifest?.revision, 5, 'and leaves what was held')
  answer = () => ({ status: 410, body: { error: 'deleted', kind: 'Gone' } })
  await assert.rejects(remove(WID, 'wob-a'))
  eq(heldWorkspace(WID).refusal?.refusal, 'gone', 'gone is held')
  eq(heldWorkspace(WID).manifest, null, 'and nothing is left to act on')
  answer = () => ({ status: 404, body: { error: 'no such', kind: 'NotFound' } })
  await openWorkspace('wsp-none')
  eq(heldWorkspace('wsp-none').refusal?.refusal, 'missing', 'opening one that isn\'t there says so')
  answer = () => ({ status: 409, body: { error: 'bad', kind: 'Unreadable' } })
  await openWorkspace('wsp-bad')
  eq(heldWorkspace('wsp-bad').refusal?.refusal, 'unreadable', 'opening one that can\'t be read says so')

  /* replay */
  answer = () => fine(manifest({ revision: 6, objects: [object('wob-a', 'magnet', MAG)] }), { changed: false, replayed: true })
  await reorder(WID, ['wob-a'])
  eq(heldWorkspace(WID).replayed, true, 'a replay is told apart from a change')
  answer = () => fine(manifest({ revision: 7, objects: [object('wob-a', 'magnet', MAG)] }))
  await reorder(WID, ['wob-a'])
  eq(heldWorkspace(WID).replayed, false, 'and a change from a replay')

  /* answers out of order */
  answer = () => fine(manifest({ revision: 3 }))
  await openWorkspace(WID)
  eq(heldWorkspace(WID).manifest?.revision, 7, 'an older revision never replaces a newer one')
}

/* -- 4. a request from a workspace --------------------------------------------------- */
{
  const said = { author: 'ent-me', parts: [{ type: 'markdown', text: 'Compare these' }], action: 'ask', addressed_to: ['ent-quill'], dispatch: [{ participant: 'ent-quill' }] }

  const whole = workspaceRequest({ ...said, conversation: 'ent-stale', replies_to: 'ent-stale' }, WID, 'op-1')
  eq(whole.from, { workspace: WID }, 'it says where it was started')
  ok(!('conversation' in whole), 'and never a conversation: the door says where it goes')
  ok(!('replies_to' in whole), 'nor a reply')
  ok(!('objects' in whole), 'omitted means the whole workspace')
  ok(!('destination' in whole), 'no destination unless one is named')
  eq(whole.op, 'op-1', 'its operation key')
  eq(whole.parts, said.parts, 'the post is the composer\'s')
  eq(whole.addressed_to, said.addressed_to, 'and who it is addressed to')

  const selected = workspaceRequest(said, WID, 'op-2', { objects: ['wob-c', 'wob-a'] })
  eq(selected.objects, ['wob-c', 'wob-a'], 'the order asked, exactly')
  eq(selected.from, { workspace: WID }, 'beside `from`, which names one thing only')
  eq(Object.keys(selected.from as object), ['workspace'], '`from` keeps its one key')

  eq(workspaceRequest(said, WID, 'o', { objects: [] }).objects, undefined, 'nothing selected is the whole workspace, not an empty selection')

  const toC = workspaceRequest(said, WID, 'op-3', { objects: ['wob-a'], destination: { conversation: CONV } })
  eq(toC.destination, { conversation: CONV }, 'an explicit Conversation overrides')
  const toM = workspaceRequest(said, WID, 'op-4', { destination: { magnet: MAG } })
  eq(toM.destination, { magnet: MAG }, 'an explicit Magnet overrides')

  /* NO PRIMARY MAGNET: the body doesn't depend on what the workspace holds */
  const m = manifest({ objects: [object('wob-1', 'magnet', MAG), object('wob-2', 'magnet', 'mag-00112233445566bb'), object('wob-3', 'conversation', CONV)] })
  eq(workspaceRequest(said, m.id, 'k'), workspaceRequest(said, WID, 'k'), 'what it holds changes nothing of the request')
  const single = workspaceRequest(said, WID, 'k', { objects: ['wob-1'] })
  ok(!('destination' in single), 'selecting one Magnet does not route to it')
  const body = read('fluid/workspaces/client.ts')
  ok(!/manifest/i.test(body.slice(body.indexOf('export function workspaceRequest'))), 'workspaceRequest reads no manifest')

  /* the door */
  reset()
  answer = () => ({ status: 200, body: { post: 'ent-new', replayed: false, route: { rule: 'workspace', conversation: 'ent-own', created: true } } })
  const got = await sendRequest(selected)
  eq(last().path, '/fluid/api/requests', 'its door')
  eq(last().method, 'POST', 'a write')
  eq(last().client, '1', "the client's header")
  eq(last().body, JSON.parse(JSON.stringify(selected)), 'sent as built')
  eq(asked.length, 1, 'once: nothing retries on anybody\'s behalf')
  eq(got.route, { rule: 'workspace', conversation: 'ent-own', created: true }, 'the route answered')

  answer = () => ({ status: 200, body: { post: 'ent-new', replayed: true, route: { rule: 'workspace', conversation: 'ent-own', created: false } } })
  eq((await sendRequest(selected)).replayed, true, 'a replay reads as one')

  for (const [status, kind] of [[404, 'missing'], [410, 'gone'], [409, 'unreadable'], [400, 'malformed']] as const) {
    answer = () => ({ status, body: { error: 'said' } })
    await assert.rejects(sendRequest(selected), (e: WorkspaceRefusal) => e.refusal === kind && e.status === status, `${status} from the request door`)
    checks++
  }
  answer = () => ({ status: 422, body: { error: 'used', op: 'k', first: 'opr-1', refused: true } })
  await assert.rejects(sendRequest(selected), (e: WorkspaceRefusal) => e.refusal === 'conflict', 'a key used for another request')
  checks++
  answer = () => ({ status: 422, body: { error: 'Missing Magnet', refused: true, reason: { code: 'state' } } })
  await assert.rejects(sendRequest(selected), (e: WorkspaceRefusal) => e.refusal === 'declined' && e.message.includes('Missing Magnet'), 'a destination Mentis declines')
  checks++
  answer = () => 'lost'
  await assert.rejects(sendRequest(selected), (e: WorkspaceRefusal) => e.refusal === 'lost', 'no answer')
  checks++

  /* the composer: the same draft and door words; another selection is another key */
  const composer = read('fluid/Composer.tsx')
  ok(composer.includes('asking?.key]'), "the composer's key follows what the request selects")
  ok(composer.includes('await asking.send(bodyOf(d, me, d.topics, fallback), op.current)'), 'it sends the same reading of the draft, under its key')
  ok(/if \(asking\) \{[\s\S]*?return\n\s*\}\n\s*const into = await ensure\(\)/.test(composer), 'a request never makes or settles a Conversation here')
  ok(composer.includes("'/fluid/api/posts'"), 'an ordinary post keeps its door')
  const column = read('fluid/workspaces/Column.tsx')
  ok(column.includes('objects.filter((o) => selected.has(o.id))'), 'the selection reads in the curated order, and only what is still held')
  ok(column.includes('JSON.stringify([chosen, destination])'), 'selection and destination make up the key')

  /* A DESTINATION NO LONGER OFFERED: what the select shows is what is sent. Removed
     through the door and read back from what is held, as the column reads it. */
  const DEST = 'wsp-00112233aabbccee'
  const heldObjects = () => heldWorkspace(DEST).manifest!.objects
  const sending = (named: string) => workspaceRequest(said, DEST, 'k', { destination: destinationOf(destinationHeld(named, heldObjects())) })
  const toMagnet = `magnet:${MAG}`, toConversation = `conversation:${CONV}`
  answer = () => fine(manifest({ id: DEST, revision: 30, objects: [object('wob-m', 'magnet', MAG), object('wob-c', 'conversation', CONV), object('wob-e', 'evidence', 'ent-e')] }))
  await openWorkspace(DEST)
  eq(destinationOptions(heldObjects()).map(destinationValue), [toMagnet, toConversation], 'a Magnet and a Conversation it holds are offered, and nothing else')
  eq(sending(toMagnet).destination, { magnet: MAG }, 'one still offered is sent')
  eq(sending(toConversation).destination, { conversation: CONV }, 'of either kind')
  eq(destinationHeld('evidence:ent-e', heldObjects()), '', 'one never offered is not held')

  answer = () => fine(manifest({ id: DEST, revision: 31, objects: [object('wob-c', 'conversation', CONV), object('wob-e', 'evidence', 'ent-e')] }))
  await remove(DEST, 'wob-m')
  eq(destinationHeld(toMagnet, heldObjects()), '', 'removed: the choice is the workspace\'s own Conversation, as the select then shows')
  ok(!('destination' in sending(toMagnet)), 'and no removed destination is sent')
  eq(sending(toConversation).destination, { conversation: CONV }, 'one still held stays')

  answer = () => fine(manifest({ id: DEST, revision: 32, objects: [object('wob-e', 'evidence', 'ent-e')] }))
  await openWorkspace(DEST)
  ok(!('destination' in sending(toConversation)), 'gone by another tab\'s change, read back: not sent either')
  eq(destinationHeld('', heldObjects()), '', 'none stays none')

  ok(column.includes('const destination = destinationHeld(named, objects)'), 'the column reads the choice through what is offered')
  ok(column.includes('if (named !== destination) setNamed(destination)'), 'and lets it go, so adding it back names nothing')
  ok(column.includes('value={destination} onChange'), 'the select shows that')
  ok(column.includes('destination: destinationOf(destination)'), 'and the request sends that')
}

/* -- 5. a Magnet in several workspaces ------------------------------------------------ */
{
  const seen: Record<string, Manifest> = {}
  answer = (a) => {
    const m = manifest({ id: a.body.from ? `wsp-${Object.keys(seen).length}a` : WID, name: a.body.name ?? '', objects: [object('wob-m', 'magnet', MAG)] })
    seen[m.id] = m
    return fine(m)
  }
  const one = await newWorkspace({ name: 'One', from: { magnet: MAG } })
  const two = await newWorkspace({ name: 'Two', from: { magnet: MAG } })
  ok(one.id !== two.id, 'two workspaces')
  const ones = heldWorkspace(one.id).manifest!.objects, twos = heldWorkspace(two.id).manifest!.objects
  eq(ones[0].ref, twos[0].ref, 'naming one Magnet')
  eq(Object.keys(ones[0]).sort(), ['curated', 'id', 'kind', 'provenance', 'ref'], 'a reference, with nothing of the Magnet in it')
  const state = read('fluid/workspaces/state.ts')
  ok(!/MagnetConfig|magnets\b/.test(state.replace(/\/\*[\s\S]*?\*\//g, '')), 'state holds no Magnet')

  /* an unknown field kept stays kept, a later V1's */
  answer = () => fine(manifest({ revision: 20, objects: [object('wob-z', 'other', 'x', { later: { a: 1 } })], later: 'kept' }))
  await add(WID, chosenBy('ent-aaaaaaaaaaaa', 'other', 'x'))
  eq(heldWorkspace(WID).manifest?.later, 'kept', 'unknown manifest fields are kept')
  eq(heldWorkspace(WID).manifest?.objects[0].later, { a: 1 }, 'unknown object fields are kept')
}

/* -- 6. its layout, under its own key -------------------------------------------------- */
{
  eq(toLayout(workspaceStart()).version, 3, 'a start the server can take as `base`')
  ok(zones(workspaceStart().tree).every((z) => !z.slot?.follow), 'it follows nothing: nothing is read there')
  ok(!zones(workspaceStart().tree).some(isMagnetZone), 'and draws no Magnet of its own choosing')

  reset()
  answer = (a) => {
    if (a.path.includes('/layouts')) return { status: 200, body: { layouts: [{ id: 'conv', name: 'Conversation default', layout: { version: 3, tree: { type: 'zone', id: 'x', show: 'conversation', follow: false, items: [] }, pages: [] } }], defaults: { conversation: 'conv' } } }
    return { status: 200, body: { layout: null, saved: null } }
  }
  const h = new Holder((k) => (k === 'workspace' ? workspaceStart() : { tree: { type: 'zone', id: 'product' } as never, pages: [] }), { local: { store: () => null as never, brain: () => Promise.resolve(null) } })
  h.enter(WID, 'workspace')
  await new Promise((r) => setTimeout(r, 10))
  ok(asked.some((a) => a.path === `/fluid/api/arrangements/${WID}`), 'its layout is read under the wsp- key')
  ok(!asked.some((a) => a.path.includes('conversations') || a.path.includes('collections')), 'and no Conversation door is asked of it')
  eq(h.from, 'product', "a conversation's default layout is not a workspace's")
  ok(h.ready, 'it settles')

  reset()
  answer = (a) => a.method === 'POST'
    ? { status: 200, body: { saved: 11, layout: { ...(a.body.layout as object) } } }
    : { status: 200, body: { layout: null, saved: null } }
  await h.save('wide')
  eq(last().path, `/fluid/api/arrangements/${WID}`, 'and saved under it')
  ok(last().body.op, 'with an operation key')
  ok(!('objects' in last().body.layout), 'a layout never carries the manifest')
  eq(h.savedAt, 11, 'the place keeps what the Brain keeps')

  for (const status of [404, 410, 409]) {
    answer = () => ({ status, body: { error: 'no', kind: 'Gone' } })
    await h.save('wide')
    checks++ /* said in a toast; the save neither throws nor claims it was kept */
    eq(h.savedAt, 11, `${status}: nothing claims to be saved`)
  }

  /* a Magnet already defined is placed as it stands, under its id: no seed, no copy */
  reset()
  answer = () => ({ status: 200, body: { saved: 12, layout: { version: 3, tree: { type: 'zone', id: 'a', show: 'objects', follow: false, items: [] }, pages: [] }, magnet: { id: MAG } } })
  await h.createMagnet(null, { type: 'zone', show: 'magnet', name: 'Reef', level: 'icon' }, { id: MAG, wideFallback: 'launcher' })
  eq(last().path, `/fluid/api/arrangements/${WID}/magnets`, 'its Magnet route, under the key')
  eq(last().body.id, MAG, 'by its id')
  ok(!('seed' in last().body), 'with nothing to write')

  /* a section still drawn for the place left asks no Conversation door of a wsp- id */
  reset()
  await store.loadConversationObjects(WID)
  eq(asked.length, 0, 'a workspace key is no Conversation')

  /* a conversation's holder is as it was */
  ok(workspace.kind !== 'workspace', 'the shared holder is untouched by this test')
  const shell = read('fluid/Shell.tsx')
  ok(shell.includes("workspace.enter(a.w, 'workspace')"), 'a reload enters the workspace by its key')
  ok(shell.includes('<WorkspaceColumn key={shownWorkspace}'), 'drawn where a column goes')
  ok(!/new Holder|createPortal/.test(read('fluid/workspaces/Column.tsx')), 'no second holder or window system')
  ok(/import \{ Floats|<Floats \/>/.test(shell), 'the one Floats')
}

/* -- 6b. a tab's kept copy and the Magnets the Brain keeps ---------------------------------- */
{
  const mem = new Map<string, string>()
  const was = globalThis.sessionStorage
  globalThis.sessionStorage = { getItem: (k: string) => mem.get(k) ?? null, setItem: (k: string, v: string) => { mem.set(k, v) }, removeItem: (k: string) => { mem.delete(k) } } as Storage
  const zoneOf = (id: string) => ({ type: 'zone', id, show: 'magnet', name: id, options: { magnet: id }, level: 'icon' })
  const floatOf = (id: string, x: number) => ({ id: `w-${id}`, zone: zoneOf(id), x, y: 20, w: 360, h: 480 })
  const cfgOf = (id: string, renderer = 'disc') => ({ id, sources: [{ kind: 'conversation', conversation: CONV }], selection: {}, collection: { mode: 'one-time' }, synthesis: { mode: 'manual' },
    notifications: { newItems: false, changes: false, failures: false }, presentation: { renderer } })
  const layoutOf = (floats: Array<[string, number]>, renderer = 'disc', more: object = {}) => ({ format: 'mentis.fluid-arrangement', version: 3, tree: toLayout(workspaceStart()).tree, pages: [],
    focus: { floats: floats.map(([id, x]) => floatOf(id, x)) }, magnets: Object.fromEntries(floats.map(([id]) => [id, cfgOf(id, renderer)])), ...more })
  const session = `mentis.fluid.arr:${WID}`
  const holder = () => new Holder(() => workspaceStart(), { local: { store: () => null as never, brain: () => Promise.resolve(null) } })
  const place = (h: Holder) => (h.arr.focus?.floats ?? []).map((f) => [f.zone.id, f.x])
  const settled = () => new Promise((r) => setTimeout(r, 10))
  let kept: object | 'down' = layoutOf([['mag-a', 100], ['mag-b', 200]])
  answer = (a) => a.path.includes('/layouts') ? { status: 200, body: { layouts: [], defaults: {} } }
    : kept === 'down' ? 'lost' : { status: 200, body: { layout: kept, saved: 5 } }

  /* a copy the reader never changed: another browser's Magnet is here after a reload */
  mem.set(session, JSON.stringify(layoutOf([['mag-a', 100]])))
  let h = holder()
  h.enter(WID, 'workspace')
  eq(place(h), [['mag-a', 100]], 'it arrives on its copy, not a blank wait')
  await settled()
  eq(place(h), [['mag-a', 100], ['mag-b', 200]], 'an untouched copy shows what the Brain keeps')
  eq(h.from, 'saved', 'and says so')
  ok(!h.changed(), 'with nothing to save')
  ok(JSON.parse(mem.get(session)!).magnets['mag-b'], 'and the copy is now that, for the next reload')

  /* a copy the reader moved a Magnet in: its place stays, the rest is the Brain's */
  mem.set(session, JSON.stringify(layoutOf([['mag-a', 777], ['mag-gone', 300]])))
  mem.set(session + ':changed', '1')
  kept = layoutOf([['mag-a', 100], ['mag-b', 200]], 'list')
  h = holder()
  h.enter(WID, 'workspace')
  await settled()
  eq(place(h), [['mag-a', 777], ['mag-b', 200]], 'its own position kept; added elsewhere in; removed elsewhere out')
  eq(h.arr.magnets?.['mag-a']?.presentation.renderer, 'list', 'a definition is the server\'s, here too')
  ok(!h.arr.magnets?.['mag-gone'], 'one gone is gone')
  ok(h.changed(), 'its own placement is still its own to save or not')
  const copy = JSON.parse(mem.get(session)!)
  eq(copy.focus.floats.map((f: { zone: { id: string }; x: number }) => [f.zone.id, f.x]), [['mag-a', 777], ['mag-b', 200]], 'and the next reload starts from that')
  eq(mem.get(session + ':changed'), '1', 'still this tab\'s own')

  /* the server can't be read: nothing is taken away */
  mem.set(session, JSON.stringify(layoutOf([['mag-a', 777]])))
  kept = 'down'
  h = holder()
  h.enter(WID, 'workspace')
  await settled()
  eq(place(h), [['mag-a', 777]], 'no answer takes nothing away')
  mem.clear()

  /* where it can't be put as the server has it, it is kept, not lost */
  const arrOf = (floats: Array<[string, number]>, more: object = {}): Arr => ({ tree: workspaceStart().tree, pages: [], focus: { floats: floats.map(([id, x]) => floatOf(id, x)) as never }, ...more })
  const full = Array.from({ length: 12 }, (_, i): [string, number] => [`ent-w${i}`, i]).map(([id, x]) => floatOf(id, x)).map((f) => ({ ...f, zone: { ...f.zone, show: 'objects', options: undefined } }))
  const crowded = sharedFromKept({ tree: workspaceStart().tree, pages: [], focus: { floats: full as never } }, arrOf([['mag-new', 5]], { magnets: { 'mag-new': cfgOf('mag-new') } }))
  eq(crowded.setAside?.map((z) => z.id), ['mag-new'], 'every window slot taken: it waits set aside')
  eq(crowded.focus?.floats?.length, 12, 'and no window was displaced')

  /* a window pinned to the reader is no part of what this place keeps */
  const pinned = arrOf([])
  pinned.focus = { floats: [{ ...floatOf('mag-pinned', 9), pinned: true }] as never }
  eq(sharedFromKept(pinned, arrOf([])).focus?.floats?.map((f) => f.zone.id), ['mag-pinned'], 'a travelling Magnet stays with the reader')

  /* each screen size's own record */
  const rec = (order: string[], at = 1) => ({ order, place: Object.fromEntries(order.map((z) => [z, 'stack'])), level: {}, updatedAt: at })
  const narrow = sharedFromKept(arrOf([['mag-a', 1]], { presentations: { medium: rec(['mag-a', 'ent-own']) } }),
    arrOf([['mag-a', 1], ['mag-b', 2]], { presentations: { medium: rec(['mag-a', 'mag-b'], 2), compact: rec(['mag-b'], 2) } }))
  eq(narrow.presentations?.medium?.order, ['mag-a', 'mag-b', 'ent-own'], 'a record it holds gains what it lacks and keeps its own')
  eq(narrow.presentations?.compact?.order, ['mag-b'], 'with no record, it follows the Brain')
  globalThis.sessionStorage = was
}

/* -- 7. what a row says ------------------------------------------------------------------ */
{
  const objects = [
    object('wob-m', 'magnet', MAG),
    object('wob-c', 'conversation', CONV, { provenance: { source: { kind: 'participant', ref: 'ent-aaaaaaaaaaaa' }, by: 'ent-aaaaaaaaaaaa' } }),
    object('wob-e', 'evidence', 'live:ent-1:k', { provenance: { source: { kind: 'magnet', ref: MAG }, by: 'ent-aaaaaaaaaaaa' } }),
  ]
  eq(provenanceWords(objects[0]), `from magnet ${MAG}`, 'from what it started from')
  eq(provenanceWords(objects[1]), 'chosen by ent-aaaaaaaaaaaa', 'chosen by somebody')
  eq(provenanceWords(objects[2]), `from magnet ${MAG}, by ent-aaaaaaaaaaaa`, 'found through a Magnet, by somebody')

  reset()
  const acts: RowActs = {
    selected: new Set(['wob-c']), busy: false, toggle() {}, move() {}, drop() {}, remove() {},
    open: () => null, known: (o) => (o.id === 'wob-c' ? 'Tidewater' : null),
  }
  const html = renderToStaticMarkup(createElement(ObjectRows, { objects, acts }))
  eq((html.match(/wo-curated/g) ?? []).length, 3, 'every row says curated')
  ok(html.includes('Tidewater') && html.includes(CONV), 'a known name, and the reference still shown')
  ok(html.includes(`from magnet ${MAG}`), 'provenance drawn')
  ok((html.indexOf('wob-m') < html.indexOf('wob-c')) && (html.indexOf('wob-c') < html.indexOf('wob-e')), 'in the curated order')
  ok(!/valid|verified|authoritative|standing/i.test(html), 'nothing here claims standing for a reference')
  eq(asked.length, 0, 'drawing rows reads nothing')
  ok(!/authority|\bgranted\b/i.test(html), 'and claims no authority')
}

/* -- 8. the shared registry -------------------------------------------------------------- */
{
  const provider = read('fluid/surface/magnet/provider.ts')
  ok(provider.includes("word('magnet.toWorkspace'"), "a Magnet's way into a workspace is in the one registry")
  ok(provider.includes("word('conversation.toWorkspace'"), "and a conversation's")
  const switcher = read('fluid/conversation/Switcher.tsx')
  ok(switcher.includes('<WorkspaceRows'), 'workspaces are reached from the one switcher')
  /* D2 and a Conversation's own workspace keep their rules */
  ok(read('fluid/surface/magnet/choices.ts').includes("onlyIn: 'conversation' as const"), 'Make magnet stays where it was')
  ok(read('fluid/workspace/Workspace.tsx').includes("provisional ? 'unnamed' : 'conversation'"), "a conversation's place is what it was")
}

console.log(`fluid_workspaces_unit: ${checks} checks`)
