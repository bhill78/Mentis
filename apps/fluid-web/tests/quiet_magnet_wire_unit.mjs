import { registerHooks } from 'node:module'
import { readFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import ts from '../node_modules/typescript/lib/typescript.js'
import { test } from 'node:test'
import assert from 'node:assert/strict'
registerHooks({
  resolve(specifier, context, next) {
    if (specifier.startsWith('.')) for (const suffix of ['.ts', '.tsx', '/index.ts']) {
      const url = new URL(specifier + suffix, context.parentURL)
      if (existsSync(fileURLToPath(url))) return { url: url.href, shortCircuit: true }
    }
    return next(specifier, context)
  },
  load(url, context, next) {
    if (url.endsWith('.css')) return { format: 'module', source: '', shortCircuit: true }
    if (/\.tsx?$/.test(url)) return { format: 'module', shortCircuit: true, source: ts.transpileModule(readFileSync(fileURLToPath(url), 'utf8'), { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX } }).outputText }
    return next(url, context)
  },
})
const { createMiniConversation, PARTICIPANTS_PATH, forgetMiniDrafts } = await import('../src/quiet2/magnets/conversation.ts')
const { MANAGED_REQUEST_DOOR } = await import('../src/quiet2/magnets/contract.ts')
const { makeMagnet } = await import('../src/quiet2/magnets/managementApi.ts')
const { createBinding, BRAIN_PATH } = await import('../src/brainBinding.ts')
const { magnetRefusal } = await import('../../../tools/quiet-magnet-additions-preview.mjs')
const A = 'ent-aaaaaaaaaaaa', B = 'ent-bbbbbbbbbbbb', C = 'ent-cccccccccccc', owner = 'ent-111111111111'
const fixture = { A, B, C, corpusId: 'wire-fixture', sources: [A, B, C], participants: [owner] }
const resource = { id: 'mg99', brainKey: 'http://fixture|dev|wire-fixture', saved: { id: 'mag-fixture', name: 'Fixture', config: { id: 'mag-fixture', conversation: C, sources: [{ kind: 'conversation', conversation: B }], selection: {} } } }
/* THE MANAGED DOOR, AND THE EXACT BODY IT IS GIVEN. `MANAGED_REQUEST_DOOR` is
 * the one door a managed send uses: "there is no /posts fallback and no silent
 * context loss" (contract.ts section 2). This vector used to assert the post door and
 * the gated fixture proxy's `postRefusal`; the proxy forwards the post door
 * only, so it no longer fronts this send at all, and what is worth pinning
 * here is the body itself -- routed by `from.magnet` with the server resolving
 * the destination, the authored words as the only part, record-only, nothing
 * dispatched and nothing asked. */
test('the mini sender sends the exact managed record-only request to the one door', async () => {
  forgetMiniDrafts()
  const binding = createBinding(); binding.saw('wire-fixture@one')
  let captured
  const mini = createMiniConversation({ resource, canWrite: true, binding, now: async () => binding.bound(), op: () => 'wire-fixture-post',
    get: async (path) => ({ status: 200, body: path === PARTICIPANTS_PATH ? { me: owner } : { id: C, conversation: C, name: 'Fixture', participants: [], topics: [], turns: [], turns_total: 0, owed: [] } }),
    post: async (path, body, headers) => { captured = { path, body, headers }; return { status: 200, body: { post: 'ent-222222222222', number: 1 } } },
  })
  mini.draft('Fixture message')
  await mini.send()
  assert.equal(captured.path, MANAGED_REQUEST_DOOR)
  assert.equal(captured.headers['X-Mentis-Brain'], 'wire-fixture@one')
  assert.deepEqual(captured.body, {
    from: { magnet: 'mag-fixture' },
    author: owner,
    text: 'Fixture message',
    parts: [{ type: 'text', text: 'Fixture message' }],
    action: 'record-only',
    dispatch: [],
    op: 'wire-fixture-post',
  })
  // NOTHING NAMES ITS OWN ROUTE, and nothing carries the retired adapter: the
  // door refuses a declared `conversation`, a `_magnet*` key or generated work.
  assert.equal('conversation' in captured.body, false)
  assert.equal(Object.keys(captured.body).some((k) => k.startsWith('_magnet')), false)
  mini.dispose(); forgetMiniDrafts()
})
test('Management produces the exact atomic creation body admitted by the fixture gate', async () => {
  let body
  globalThis.fetch = async (path, init) => {
    let out
    if (path === BRAIN_PATH) out = { brain: { corpus_id: 'wire-fixture', instance: 'one' } }
    else if (init?.method === 'POST') { body = JSON.parse(init.body); out = { magnet: { id: 'mag-new-fixture', sources: [{ kind: 'conversation', conversation: B }], selection: {} } } }
    else out = { layout: { format: 'mentis.fluid-arrangement', version: 2 } }
    return new Response(JSON.stringify(out), { status: 200, headers: { 'Content-Type': 'application/json' } })
  }
  await makeMagnet({ key: resource.brainKey, arrangement: A, source: B, name: 'Fixture new Magnet', op: 'wire-fixture-create', manual: false })
  assert.equal(magnetRefusal(body, fixture), null)
})
