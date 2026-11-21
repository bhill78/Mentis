import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFileSync } from 'node:fs'
import { discoverMagnets, unsupportedMagnet } from '../src/quiet2/magnets/read'
import { createMagnetResource } from '../src/quiet2/magnets/state'
import type { MagnetGet, SavedMagnet } from '../src/quiet2/magnets/contract'

const id = 'mag-fixtureA' as const, conversation = 'ent-source111111'
const config = { id, sources: [{ kind: 'conversation' as const, conversation }], selection: { informationTypes: ['post', 'file', 'attachment'] as ('post' | 'file' | 'attachment')[] }, collection: { mode: 'one-time' as const }, synthesis: { mode: 'manual' as const }, notifications: { newItems: false, changes: false, failures: false }, presentation: { renderer: 'disc' as const } }
const saved: SavedMagnet = { id, name: 'Fixture collection', config }
const zone = { type: 'zone', id, show: 'magnet', name: saved.name, options: { magnet: id } }
const layout = { format: 'mentis.fluid-arrangement', version: 3, tree: zone, magnets: { [id]: config } }
const ok: MagnetGet = async () => ({ status: 200, body: { layout, saved: 1 } })
const page = (results: unknown[], next?: string) => ({ magnet: id, sources: [{ key: `conversation:${conversation}`, status: 'ok', results, next }] })
const summary = { magnet: id, sources: [{ key: `conversation:${conversation}`, status: 'ok', summary: { title: 'Source title', posts: 32 } }] }
const resource = (get: MagnetGet) => createMagnetResource({ id: 'qm1', brainKey: 'origin|fixture|brain-a', saved, get })

test('discovery reads current conversation only; repeated saved placements deduplicate', async () => {
  const calls: string[] = []
  const rows = await discoverMagnets('ent-origin111111', async (path) => { calls.push(path); return { status: 200, body: { layout: { ...layout, pages: [{ tree: zone }] } } } })
  assert.deepEqual(calls, ['/fluid/api/arrangements/ent-origin111111'])
  assert.equal(rows.length, 1); assert.equal(rows[0].config?.sources[0].kind, 'conversation')
})
test('absent arrangement is empty; unreadable/later format and route errors explain', async () => {
  assert.deepEqual(await discoverMagnets('ent-origin111111', async () => ({ status: 200, body: { layout: null } })), [])
  await assert.rejects(discoverMagnets('ent-origin111111', async () => ({ status: 403, body: {} })), /403/)
  await assert.rejects(discoverMagnets('ent-origin111111', async () => ({ status: 200, body: { layout: { ...layout, version: 4 } } })), /format/)
  await assert.rejects(discoverMagnets('home', ok), /conversation/)
})
test('missing and later schema definitions remain explicit rows beside supported rows', async () => {
  const rows = await discoverMagnets('ent-origin111111', async () => ({ status: 200, body: { layout: { ...layout, tree: { type: 'split', kids: [zone, { ...zone, id: 'mag-missing', options: { magnet: 'mag-missing' } }, { ...zone, id: 'mag-later', options: { magnet: 'mag-later' } }] } }, magnets_unreadable: { 'mag-later': 'later schema 2' } } }))
  assert.equal(rows.length, 3); assert.equal(rows[0].reason, undefined); assert.match(rows[1].reason!, /missing/); assert.equal(rows[2].reason, 'later schema 2')
})
test('supported scope validates dates, source and selected types without treating own Conversation as source', () => {
  assert.equal(unsupportedMagnet(config, id), undefined)
  assert.match(unsupportedMagnet({ ...config, schema_version: 2 }, id)!, /schema/)
  assert.match(unsupportedMagnet({ ...config, sources: [config.sources[0], config.sources[0]] }, id)!, /one source/)
  assert.match(unsupportedMagnet({ ...config, selection: { informationTypes: ['form'] } }, id)!, /other information/)
  assert.match(unsupportedMagnet({ ...config, selection: { dates: { after: 'not a date' } } }, id)!, /date/)
  assert.match(unsupportedMagnet({ ...config, selection: { dates: { after: '2026-02-30' } } }, id)!, /date/)
  assert.match(unsupportedMagnet({ ...config, selection: { dates: { after: '2026-12-01', before: '2026-01-01' } } }, id)!, /end before/)
  assert.equal(unsupportedMagnet({ ...config, selection: { dates: { after: '2026-01-01' }, criteria: 'kept, unapplied' } }, id), undefined)
})
test('bounded summary then page; demand paging keeps versions/provenance and source-wide tally', async () => {
  const calls: string[] = []
  const r = resource(async (path) => { calls.push(path); return { status: 200, body: path.includes('mode=summary') ? summary : calls.length === 2 ? page([{ kind: 'post', id: 'ent-post111111', version: 'v1', conversation, number: 32 }], 'next-one') : page([{ kind: 'post', id: 'ent-post111111', version: 'v2', conversation }, { kind: 'file', id: 'adm-file111111', post: 'ent-post111111', conversation }]) } })
  await r.read(); assert.equal(calls.length, 2); assert.equal(r.snapshot().summary?.summary?.posts, 32); assert.equal(r.snapshot().results.length, 1)
  await r.read(true); assert.equal(calls.length, 3); assert.match(calls[2], /cursor=next-one/); assert.equal(r.snapshot().results.length, 2); assert.equal(r.snapshot().results[0].version, 'v2'); assert.equal(r.snapshot().results[1].post, 'ent-post111111')
  await r.read(true); assert.equal(calls.length, 3); assert.equal(r.snapshot().next, undefined)
  assert.ok(calls.every((p) => p.startsWith(`/fluid/api/magnets/${id}/read?`))); r.dispose()
})
test('no route, denied read, busy and later schema never fall back to another reader', async () => {
  for (const status of [404, 403]) { const calls: string[] = []; const r = resource(async (path) => { calls.push(path); return { status, body: {} } }); await r.read(); assert.equal(calls.length, 1); assert.match(r.snapshot().error!, new RegExp(String(status))); assert.deepEqual(r.snapshot().results, []); r.dispose() }
  const busy = resource(async () => ({ status: 503, body: { error: 'busy fixture' } })); await busy.read(); assert.equal(busy.snapshot().status, 'busy'); assert.equal(busy.snapshot().summary?.summary?.posts, undefined); busy.dispose()
  const later = resource(async () => ({ status: 200, body: { magnet: id, unavailable: 'later schema', sources: [] } })); await later.read(); assert.equal(later.snapshot().status, 'unavailable'); assert.equal(later.snapshot().reason, 'later schema'); later.dispose()
})
test('partial results keep their partial status/cursor; failed more never becomes complete or zero', async () => {
  let calls = 0
  const r = resource(async (path) => ({ status: ++calls > 2 ? 503 : 200, body: path.includes('mode=summary') ? summary : { magnet: id, sources: [{ ...page([{ kind: 'post', id: 'ent-post111111', conversation }], 'next').sources[0], status: 'partial', reason: 'bounded read' }] } }))
  await r.read(); assert.equal(r.snapshot().status, 'partial'); assert.equal(r.snapshot().next, 'next'); assert.equal(r.snapshot().results.length, 1)
  await r.read(true); assert.equal(r.snapshot().status, 'busy'); assert.equal(r.snapshot().next, 'next'); assert.equal(r.snapshot().results.length, 1); r.dispose()
})
test('Magnet/source mismatch and repeated cursor fail closed', async () => {
  const wrong = resource(async () => ({ status: 200, body: { ...summary, magnet: 'mag-other' } })); await wrong.read(); assert.match(wrong.snapshot().error!, /match/); wrong.dispose()
  const otherSource = resource(async () => ({ status: 200, body: { magnet: id, sources: [{ key: 'conversation:ent-other111111', status: 'ok' }] } })); await otherSource.read(); assert.match(otherSource.snapshot().error!, /source/); otherSource.dispose()
  const r = resource(async (path) => ({ status: 200, body: path.includes('mode=summary') ? summary : page([], 'same') })); await r.read(); await r.read(true); assert.match(r.snapshot().error!, /same cursor/); r.dispose()
})
test('cancel, disposal and Brain lifetime reject even noncooperative late completions', async () => {
  let answer!: (v: { status: number; body: unknown }) => void
  const r = resource(() => new Promise((resolve) => { answer = resolve }))
  const pending = r.read(); r.cancel(); answer({ status: 200, body: summary }); await pending
  assert.equal(r.snapshot().summary, undefined); assert.equal(r.snapshot().loading, false)
  const pendingAgain = r.read(); r.dispose(); r.dispose(); answer({ status: 200, body: summary }); await pendingAgain
  assert.equal(r.snapshot().summary, undefined); assert.deepEqual(r.snapshot().results, [])
  assert.throws(() => createMagnetResource({ id: 'qm2', brainKey: '', saved, get: ok }), /unknown/)
})
test('two Magnets and two Brains cannot share resource state, cursors or late results', async () => {
  const a = resource(async (path) => ({ status: 200, body: path.includes('mode=summary') ? summary : page([{ kind: 'post', id: 'ent-post111111', conversation }], 'a-next') }))
  const second = { ...saved, id: 'mag-fixtureB' as const, config: { ...config, id: 'mag-fixtureB' as const } }
  const b = createMagnetResource({ id: 'qm2', brainKey: 'origin|fixture|brain-b', saved: second, get: async () => ({ status: 404, body: {} }) })
  await a.read(); await b.read(); a.update({ x: 99, tab: 'Files' }); assert.equal(b.snapshot().x, 32); assert.equal(b.snapshot().tab, 'Overview'); assert.equal(b.snapshot().next, undefined); assert.deepEqual(b.snapshot().results, []); assert.equal(a.snapshot().next, 'a-next'); a.dispose(); b.dispose()
})
test('feature model has no runtime workspace, synthesis, mutation or persistent seen dependency', () => {
  for (const name of ['read', 'state']) {
    const code = readFileSync(new URL(`../src/quiet2/magnets/${name}.ts`, import.meta.url), 'utf8')
    assert.doesNotMatch(code, /localStorage|markSeen|seenAt|useMagnet|from ['"][^'"]*workspace|method:\s*['"]POST/)
  }
})
test('malformed summaries, reasons and refusals cannot masquerade as readable data', async () => {
  for (const body of [
    { magnet: id, unavailable: {}, sources: [] },
    { magnet: id, sources: [{ key: `conversation:${conversation}`, status: 'unavailable', reason: {} }] },
    { magnet: id, sources: [{ key: `conversation:${conversation}`, status: 'ok', summary: { title: {}, posts: 2 } }] },
    { magnet: id, sources: [{ key: `conversation:${conversation}`, status: 'ok', summary: { title: 'valid', posts: '2' } }] },
  ]) {
    const r = resource(async () => ({ status: 200, body })); await r.read(); assert.ok(r.snapshot().error); assert.equal(r.snapshot().summary, undefined); assert.equal(r.snapshot().results.length, 0); r.dispose()
  }
})
test('abandoned arrangement discovery rejects a late answer without leaking rows', async () => {
  const abort = new AbortController()
  const rows = discoverMagnets('ent-origin111111', async () => { abort.abort(); return { status: 200, body: { layout } } }, abort.signal)
  await assert.rejects(rows, (e: Error) => e.name === 'AbortError')
})
test('partial first page explicitly retries without a cursor before Load more can advance', async () => {
  const calls: string[] = []
  let pages = 0
  const r = resource(async (path) => {
    calls.push(path)
    if (path.includes('mode=summary')) return { status: 200, body: summary }
    pages++
    const body = page(pages === 1 ? [] : [{ kind: 'file', id: 'adm-file111111', post: 'ent-post111111', conversation }], 'second-page')
    if (pages === 1) Object.assign(body.sources[0], { status: 'partial', reason: '17 posts objects not read yet; ask again' })
    return { status: 200, body }
  })
  await r.read(); assert.equal(r.snapshot().status, 'partial'); assert.equal(r.snapshot().next, 'second-page'); assert.equal(r.snapshot().results.length, 0)
  await r.read(true); assert.equal(r.snapshot().status, 'ok'); assert.equal(r.snapshot().results.length, 1); assert.equal(calls.length, 3); assert.doesNotMatch(calls[2], /cursor=/)
  await r.read(true); assert.match(calls[3], /cursor=second-page/); r.dispose()
})
test('partial last page retries with read(false) even without next and preserves merged prior results', async () => {
  const calls: string[] = []
  let pages = 0
  const r = resource(async (path) => {
    calls.push(path)
    if (path.includes('mode=summary')) return { status: 200, body: summary }
    pages++
    if (pages === 1) return { status: 200, body: page([{ kind: 'post', id: 'ent-first111111', conversation }], 'last-page') }
    const body = page([{ kind: 'file', id: pages === 2 ? 'adm-file111111' : 'adm-file222222', post: 'ent-post111111', conversation }])
    if (pages === 2) Object.assign(body.sources[0], { status: 'partial', reason: 'objects not read yet; ask again' })
    return { status: 200, body }
  })
  await r.read(); await r.read(true); assert.equal(r.snapshot().status, 'partial'); assert.equal(r.snapshot().next, undefined); assert.equal(r.snapshot().results.length, 2)
  await r.read(false); assert.match(calls[3], /cursor=last-page/); assert.equal(r.snapshot().status, 'ok'); assert.equal(r.snapshot().results.length, 3); assert.equal(calls.filter((p) => p.includes('mode=summary')).length, 1)
  await r.read(true); assert.equal(calls.length, 4); r.dispose()
})
test('busy and failed later page retries keep the original input cursor and accumulated results', async () => {
  const calls: string[] = []
  let pages = 0
  const r = resource(async (path) => {
    calls.push(path)
    if (path.includes('mode=summary')) return { status: 200, body: summary }
    pages++
    if (pages === 1) return { status: 200, body: page([{ kind: 'post', id: 'ent-first111111', conversation }], 'later-page') }
    if (pages === 2) return { status: 503, body: { error: 'busy' } }
    if (pages === 3) return { status: 502, body: {} }
    return { status: 200, body: page([{ kind: 'post', id: 'ent-second111111', conversation }]) }
  })
  await r.read(); await r.read(true); assert.equal(r.snapshot().status, 'busy'); assert.equal(r.snapshot().results.length, 1); assert.equal(r.snapshot().next, 'later-page')
  await r.read(false); assert.match(r.snapshot().error!, /502/); assert.equal(r.snapshot().results.length, 1)
  await r.read(true); assert.equal(r.snapshot().results.length, 2); assert.equal(r.snapshot().next, undefined)
  for (const path of calls.slice(2)) assert.match(path, /cursor=later-page/)
  assert.equal(calls.filter((p) => p.includes('mode=summary')).length, 1); r.dispose()
})
