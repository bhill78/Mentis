// Execute the shipped Work hook -> useApi -> request -> fluidFetch seam.
// React's state/effect lifecycle is adapted here; this is not a DOM test.
// Based on the independent B1 reproducer in adm-d665a4fc84f2, with dependency
// tracking, path transitions, and a cursor-owning consumer's fresh read.
import { registerHooks } from 'node:module'
import { existsSync, readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import assert from 'node:assert/strict'
import test from 'node:test'
import ts from '../node_modules/typescript/lib/typescript.js'

registerHooks({
  resolve(specifier, context, next) {
    if (specifier === 'react') return { url: 'work-test:react', shortCircuit: true }
    if (specifier.startsWith('.')) for (const suffix of ['.ts', '.tsx', '/index.ts']) {
      const url = new URL(specifier + suffix, context.parentURL)
      if (existsSync(fileURLToPath(url))) return { url: url.href, shortCircuit: true }
    }
    return next(specifier, context)
  },
  load(url, context, next) {
    if (url === 'work-test:react') return { format: 'module', shortCircuit: true, source: `
      const h = () => globalThis.__workHooks;
      export const useState = v => h().state(v);
      export const useRef = v => h().ref(v);
      export const useEffect = (f, deps) => h().effect(f, deps);
      export const useCallback = f => f;
    ` }
    if (/\.tsx?$/.test(url)) return { format: 'module', shortCircuit: true,
      source: ts.transpileModule(readFileSync(fileURLToPath(url), 'utf8'), {
        compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
      }).outputText }
    return next(url, context)
  },
})

globalThis.window = { setTimeout, clearTimeout }
const { read, useApi, ResultsRefreshRequired } = await import('../src/api.ts')
const { workDetailPath, useWorkDetail } = await import('../src/work/api.ts')
const settle = () => new Promise(r => setTimeout(r, 10))
const json = (body, status = 200) => new Response(JSON.stringify(body), { status })
const refusal = () => json({ error: 'same words', kind: 'ResultsRefreshRequired', refresh_results: true }, 409)

function hooks() {
  const values = [], refs = [], effects = []
  let stateCursor, refCursor, effectCursor, pending
  const h = {
    state(v) {
      const n = stateCursor++
      if (!(n in values)) values[n] = v
      return [values[n], v => { values[n] = typeof v === 'function' ? v(values[n]) : v }]
    },
    ref(v) { return refs[refCursor++] ??= { current: v } },
    effect(f, deps) {
      const n = effectCursor++, old = effects[n]
      if (!old || deps.some((v, i) => !Object.is(v, old.deps[i]))) {
        pending.push(() => { old?.cleanup?.(); effects[n] = { deps, cleanup: f() } })
      }
    },
    render(f) {
      globalThis.__workHooks = h
      stateCursor = refCursor = effectCursor = 0
      pending = []
      const result = f()
      for (const run of pending) run()
      return result
    },
    close() { for (const e of effects) e?.cleanup?.() },
  }
  return h
}

test('detail path encodes exact opaque group and item cursors', () => {
  for (const paging of [
    { resultsBefore: 'opaque+/=&' },
    { resultGroup: 'ent-g?x', itemsAfter: 'opaque+/=&' },
  ]) {
    const u = new URL(workDetailPath('opr-a/b', 'ent-x&y', paging), 'http://fixture')
    assert.equal(u.pathname, '/api/work/opr-a%2Fb')
    assert.equal(u.searchParams.get('viewer'), 'ent-x&y')
    if (paging.resultsBefore) assert.equal(u.searchParams.get('results_before'), paging.resultsBefore)
    else {
      assert.equal(u.searchParams.get('result_group'), paging.resultGroup)
      assert.equal(u.searchParams.get('items_after'), paging.itemsAfter)
    }
  }
})

test('direct shared read still throws the typed refresh refusal', async () => {
  globalThis.fetch = async () => refusal()
  await assert.rejects(read('/api/work/opr-direct'), e =>
    e instanceof ResultsRefreshRequired && e.kind === 'ResultsRefreshRequired')
})

for (const paging of [
  { resultsBefore: 'old-groups+/=' },
  { resultGroup: 'ent-exact-group', itemsAfter: 'old-items+/=' },
]) test(`${Object.keys(paging)[0]}: refuse stale page, discard cursors, replace with fresh first page`, async () => {
  const h = hooks(), requests = []
  const first = { result_groups: { groups: [{ id: 'old-first' }] } }
  const fresh = { result_groups: { groups: [{ id: 'new-first' }] } }
  let cursors = {}, finishFresh
  globalThis.fetch = async (path, init) => {
    requests.push({ path, init })
    if (requests.length === 1) return json(first)
    if (requests.length === 2) return refusal()
    return new Promise(resolve => { finishFresh = () => resolve(json(fresh)) })
  }
  const render = () => h.render(() => useWorkDetail('opr-paged', 'ent-owner', { runs: false, ...cursors }))
  try {
    render(); await settle()
    assert.deepEqual(render().data, first)
    cursors = paging
    render(); await settle()
    const stale = render()
    assert.equal(stale.errorKind, 'ResultsRefreshRequired')
    assert.equal(stale.error, 'same words')
    assert.equal(stale.loading, false)
    assert.deepEqual(stale.data, first, 'refusal is not a new or empty page')
    assert.equal(requests.length, 2, 'the hook does not retry stale cursors automatically')

    // The consumer acts on the discriminator only, replacing all paging
    // options. reload() would intentionally retry the same stale URL.
    if (stale.errorKind === 'ResultsRefreshRequired') cursors = {}
    const opening = render()
    assert.equal(opening.errorKind, null, 'old refusal cannot apply to the fresh path')
    assert.equal(requests.length, 3)
    assert.equal(requests[1].path, workDetailPath('opr-paged', 'ent-owner', paging))
    assert.equal(requests[2].path, workDetailPath('opr-paged', 'ent-owner'))
    for (const { init } of requests) assert.equal(init.headers['X-Mentis-Client'], '1')
    finishFresh(); await settle()
    const current = render()
    assert.deepEqual(current.data, fresh)
    assert.equal(current.errorKind, null)
    assert.equal(current.error, null)
    assert.equal(current.loading, false)
  } finally { h.close() }
})

for (const [status, kind] of [[409, 'OtherConflict'], [500, 'ResultsRefreshRequired']]) {
  test(`generic useApi ${status}/${kind} keeps string errors and same-path reload`, async () => {
    const h = hooks(), requests = []
    globalThis.fetch = async path => {
      requests.push(path)
      return requests.length === 1 ? json({ error: 'same words', kind }, status) : json({ ok: true })
    }
    const render = () => h.render(() => useApi('/api/generic', { live: false }))
    try {
      render(); await settle()
      const failed = render()
      assert.equal(failed.error, 'same words')
      assert.equal(failed.errorKind, null, 'text or kind alone cannot classify a refusal')
      failed.reload(); render(); await settle()
      assert.deepEqual(render().data, { ok: true })
      assert.equal(render().error, null)
      assert.deepEqual(requests, ['/api/generic', '/api/generic'])
    } finally { h.close() }
  })
}

test('a refusal belongs to its Work path, clears on success, and clears when disabled', async () => {
  const h = hooks()
  let expectation = 'opr-old', succeed = false
  globalThis.fetch = async () => succeed ? json({ ok: true }) : refusal()
  const render = () => h.render(() => useWorkDetail(expectation, 'ent-owner', { runs: false }))
  try {
    render(); await settle()
    assert.equal(render().errorKind, 'ResultsRefreshRequired')
    // Success at the same path must clear the structured refusal too.
    succeed = true
    render().reload(); render(); await settle()
    assert.equal(render().errorKind, null)
    succeed = false
    render().reload(); render(); await settle()
    assert.equal(render().errorKind, 'ResultsRefreshRequired')
    expectation = 'opr-other'
    assert.equal(render().errorKind, null)
    await settle()
    assert.equal(render().errorKind, 'ResultsRefreshRequired')
    expectation = null
    assert.equal(render().errorKind, null)
    assert.equal(render().data, null)
    assert.equal(render().error, null)
  } finally { h.close() }
})

test('generic error retention and ownErrors filtering retain their existing behavior', async () => {
  const h = hooks()
  let path = '/api/old', ownErrors = false
  globalThis.fetch = async () => json({ error: 'ordinary failure' }, 503)
  const render = () => h.render(() => useApi(path, { live: false, ownErrors }))
  try {
    render(); await settle()
    assert.equal(render().error, 'ordinary failure')
    path = '/api/new'
    assert.equal(render().error, 'ordinary failure')
    ownErrors = true
    assert.equal(render().error, null)
    await settle()
    assert.equal(render().error, 'ordinary failure')
    assert.equal(render().errorKind, null)
  } finally { h.close() }
})
