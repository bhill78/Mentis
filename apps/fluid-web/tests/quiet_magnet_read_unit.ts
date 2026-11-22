import assert from 'node:assert/strict'
import { test } from 'node:test'
import { discoverMagnets, unsupportedMagnet } from '../src/quiet2/magnets/read'
import { createMagnetResource } from '../src/quiet2/magnets/state'
import { loadWorking, saveWorking, workingKey } from '../src/quiet2/magnets/workingState'
import { BRAIN_PATH, page as binding } from '../src/brainBinding'
import type { MagnetGet, SavedMagnet } from '../src/quiet2/magnets/contract'

const id = 'mag-fixtureA' as const, conversation = 'ent-source111111', home = 'ent-other111111'
const config = { id, sources: [{ kind: 'conversation' as const, conversation }], selection: { informationTypes: ['post', 'file', 'attachment'] as ('post' | 'file' | 'attachment')[] }, collection: { mode: 'one-time' as const }, synthesis: { mode: 'manual' as const }, notifications: { newItems: false, changes: false, failures: false }, presentation: { renderer: 'disc' as const } }
const saved: SavedMagnet = { id, name: 'Retained collection', config }
const zone = { type: 'zone', id, show: 'magnet', name: saved.name, options: { magnet: id } }
const layout = { format: 'mentis.fluid-arrangement', version: 3, tree: zone, magnets: { [id]: config } }
const item = { kind: 'post', id: 'ent-post111111', version: 'ent-version111111', conversation, via: 'home', value: { parts: [{ type: 'text', text: 'Captured words' }] } }
const answer = (results: unknown[] = [item]) => ({ magnet: id, config, activation: { post: 'ent-collected111111', artifact: { ref: 'adm-evidence111111' }, at: 1, state: 'complete' }, page: { sources: [{ source: config.sources[0], key: `conversation:${conversation}`, status: 'ok', results }] } })
const resource = (get: MagnetGet) => createMagnetResource({ id: 'qm1', brainKey: 'origin|fixture|brain-a', saved: { ...saved }, get })

test('existing arrangement discovery deduplicates placements without creating anything', async () => {
  const calls: string[] = []
  const rows = await discoverMagnets('ent-origin111111', async (path) => { calls.push(path); return { status: 200, body: { layout: { ...layout, pages: [{ tree: zone }] } } } })
  assert.deepEqual(calls, ['/fluid/api/arrangements/ent-origin111111']); assert.equal(rows.length, 1)
})
test('discovery and unsupported definitions fail honestly', async () => {
  await assert.rejects(discoverMagnets('ent-origin111111', async () => ({ status: 403, body: {} })), /403/)
  assert.match(unsupportedMagnet({ ...config, schema_version: 2 }, id)!, /schema/)
  assert.match(unsupportedMagnet({ ...config, selection: { dates: { after: '2026-02-30' } } }, id)!, /date/)
})
test('opening reads only the durable collection endpoint and preserves captured words and versions', async () => {
  const calls: string[] = [], r = resource(async (path) => { calls.push(path); return { status: 200, body: answer() } })
  await r.read()
  assert.deepEqual(calls, [`/fluid/api/magnets/${id}/collection`])
  assert.deepEqual(r.snapshot().results, [item]); assert.equal(r.snapshot().activation?.artifact.ref, 'adm-evidence111111')
  assert.equal(r.snapshot().title, saved.name)
})
test('linked-in post keeps a different real home while home provenance mismatch is refused', async () => {
  const linked = { ...item, conversation: home, via: 'linked' }
  const r = resource(async () => ({ status: 200, body: answer([linked]) })); await r.read()
  assert.equal(r.snapshot().error, undefined); assert.equal(r.snapshot().results[0].conversation, home)
  const bad = resource(async () => ({ status: 200, body: answer([{ ...linked, via: 'home' }]) })); await bad.read()
  assert.match(bad.snapshot().error!, /inconsistent provenance/); assert.deepEqual(bad.snapshot().results, [])
})
test('an empty retained collection is empty rather than a live source page', async () => {
  const r = resource(async () => ({ status: 200, body: { magnet: id, config, activation: null, page: null } })); await r.read()
  assert.deepEqual(r.snapshot().results, []); assert.equal(r.snapshot().activation, null); assert.equal(r.snapshot().error, undefined)
})
test('missing bytes, mismatched Magnet or source and corrupt provenance never fall back', async () => {
  for (const got of [{ status: 409, body: { error: 'Retained bytes missing' } }, { status: 200, body: { ...answer(), magnet: 'mag-other' } }, { status: 200, body: { ...answer(), page: { sources: [] } } }, { status: 200, body: answer([{ ...item, version: null }]) }]) {
    let calls = 0; const r = resource(async () => { calls++; return got }); await r.read()
    assert.equal(calls, 1); assert.ok(r.snapshot().error); assert.deepEqual(r.snapshot().results, [])
  }
})
test('cancel and dispose reject noncooperative late retained reads', async () => {
  for (const stop of ['cancel', 'dispose'] as const) {
    let done!: (v: { status: number; body: unknown }) => void
    const r = resource(() => new Promise((resolve) => { done = resolve })), pending = r.read()
    r[stop](); done({ status: 200, body: answer() }); await pending
    assert.deepEqual(r.snapshot().results, [])
  }
})
test('Collect uses the Fluid owner projection and a Brain-bound keyed activation', async () => {
  const originalFetch = globalThis.fetch, calls: { path: string; body?: any; headers?: Headers }[] = []
  globalThis.fetch = (async (path: string, init?: RequestInit) => {
    if (path === BRAIN_PATH) return new Response(JSON.stringify({ brain: { corpus_id: 'brain-a', instance: 'instance-one' } }), { status: 200 })
    calls.push({ path, body: JSON.parse(String(init?.body)), headers: new Headers(init?.headers) })
    return new Response(JSON.stringify({ magnet: id, artifact: { ref: 'adm-evidence111111' }, page: { results: 1 } }), { status: 201 })
  }) as typeof fetch
  try {
    const r = resource(async (path) => {
      calls.push({ path })
      if (path === '/fluid/api/participants?limit=1') return { status: 200, body: { me: 'ent-owner111111', participants: [] } }
      if (path === '/api/participants') return { status: 200, body: { participants: [{ participant: 'ent-owner111111' }] } }
      return { status: 200, body: answer() }
    })
    await r.collect!()
    const sent = calls.find((c) => c.path.endsWith('/activate'))!
    assert.equal(sent.body.author, 'ent-owner111111'); assert.ok(sent.body.op)
    assert.equal(sent.headers!.get('X-Mentis-Brain'), 'brain-a@instance-one')
    assert.ok(calls.some((c) => c.path === '/fluid/api/participants?limit=1'))
    assert.ok(!calls.some((c) => c.path === '/api/participants'))
    assert.equal(r.snapshot().activation?.artifact.ref, 'adm-evidence111111')
  } finally { globalThis.fetch = originalFetch }
})
test('working state survives recreation by exact instance and never stores collection content', () => {
  const mem = new Map<string, string>()
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: { getItem: (key: string) => mem.get(key) ?? null, setItem: (key: string, value: string) => mem.set(key, value) } })
  binding.saw('brain-a@instance-one')
  const r = resource(async () => ({ status: 200, body: answer() }))
  r.update({ x: 152, tab: 'Files', expanded: true, inspection: item.id, agentId: 'ent-recipient111111' })
  const again = loadWorking(r.brainKey, id)
  assert.equal(again.x, 152); assert.equal(again.tab, 'Files'); assert.equal(again.inspection, item.id)
  assert.equal(again.agentId, 'ent-recipient111111')
  assert.ok(workingKey(r.brainKey)?.includes('brain-a@instance-one'))
  saveWorking(r.brainKey, id, { ...r.snapshot(), results: [item] })
  assert.ok([...mem.values()].every((v) => !v.includes('Captured words')))
  assert.deepEqual(loadWorking('origin|fixture|other-brain', id), {})
  binding.move(); assert.equal(workingKey(r.brainKey), null); assert.deepEqual(loadWorking(r.brainKey, id), {})
})
