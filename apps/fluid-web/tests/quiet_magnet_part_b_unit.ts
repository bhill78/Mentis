import assert from 'node:assert/strict'
import { test } from 'node:test'
import { collectionRows } from '../src/quiet2/magnets/collectionRows'
import { collectionChange, exactFileIssue, supportsManualCollection } from '../src/quiet2/magnets/configuration'
import { unsupportedMagnet } from '../src/quiet2/magnets/read'
import { createMagnetResource } from '../src/quiet2/magnets/state'
import { PerspectiveStore, perspectiveRequest, PERSPECTIVE_ANSWERS_ENABLED, PERSPECTIVE_BLOCK_REASON, type PreparedInquiry } from '../src/quiet2/magnets/perspectives'
import { composerRequest } from '../src/quiet2/magnets/evidence'
import { page as brain } from '../src/brainBinding'
import type { MagnetConfig } from '../src/fluid/surface/magnet/types'

const config: MagnetConfig = { id: 'mag-part-b', sources: [{ kind: 'conversation', conversation: 'ent-source111111' }], selection: {}, collection: { mode: 'one-time' }, synthesis: { mode: 'manual' }, notifications: { newItems: false, changes: false, failures: false }, presentation: { renderer: 'disc' } }
const original = { kind: 'post', id: 'ent-post111111', version: 'ent-version111111', conversation: 'ent-source111111', via: 'home', value: { parts: [{ type: 'text', text: 'Original words' }] } }
const digest = 'a'.repeat(64)
const file = { kind: 'file', id: 'adm-file111111', version: 'adm-file111111', conversation: null, author: null, at: 4, via: 'held-source', value: { ref: 'adm-file111111', digest, collection: 'col-held', path: 'nested/file.txt', text: 'é🙂', offset: 0, end: 6, size: 65540, acquired_at: 4, shortened: true, omitted_bytes: 65534, next_offset: 6, citation: `adm-file111111@${digest.slice(0, 12)}[0:6]` } }
const page = () => ({ sources: [{ source: config.sources[0], key: 'conversation:ent-source111111', status: 'ok', results: [original] }, { source: { kind: 'conversation', conversation: 'ent-other111111' }, key: 'conversation:ent-other111111', status: 'ok', results: [] }, { source: { kind: 'file', collection: 'col-held', path: 'nested/file.txt' }, key: 'file:col-held:nested/file.txt', status: 'partial', reason: 'Shortened', results: [file] }] })
const prepared: PreparedInquiry = { intent: 'ent-intent111111', perspective: 'ent-topic111111', brain: 'brain-a@instance-one', question: { ref: 'adm-question111111', digest, size: 2, media_type: 'application/json' }, manifest: { ref: 'adm-manifest111111', digest, size: 2, media_type: 'application/json' }, records: { ref: 'adm-records111111', digest, size: 2, media_type: 'application/json' }, artifacts: [], parts: [{ type: 'file', ref: 'adm-manifest111111', media_type: 'application/json', alt: 'Perspective evidence' }], reach: 'work', request_op: 'perspective-request:ent-intent111111', text: 'Exact question', closure: { count: 3, bytes: 6 }, disclosure: '' }
function resource() {
  return createMagnetResource({ id: 'qm-partb', brainKey: 'origin|fixture|brain-a', saved: { id: config.id, name: 'Inquiry', config }, get: async () => ({ status: 200, body: { magnet: config.id, config, activation: null, page: null } }) })
}
test('grounded Perspective enabling remains blocked pending the missing execution boundary', () => {
  assert.equal(PERSPECTIVE_ANSWERS_ENABLED, false)
  assert.match(PERSPECTIVE_BLOCK_REASON, /do not enforce/)
})
test('multi-source captured rows preserve held-file byte ranges and original Conversation versions', () => {
  const got = collectionRows(page())
  assert.equal(got.results.length, 2); assert.equal(got.posts, 1); assert.equal(got.status, 'partial')
  assert.equal(got.results[0].version, original.version); assert.equal(got.results[1].conversation, null)
  assert.equal((got.results[1] as any).capturedSourceKey, 'file:col-held:nested/file.txt')
  assert.equal((got.results[1].value as any).text, 'é🙂')
})
test('held-file range corruption, original size mismatch and forged Conversation identity are refused', () => {
  for (const change of [{ end: 5 }, { size: 5 }, { omitted_bytes: 0 }, { citation: 'not-pinned' }, { acquired_at: 5 }]) {
    const p = page(); p.sources[2].results = [{ ...file, value: { ...file.value, ...change } }] as any
    assert.throws(() => collectionRows(p), /range|provenance/)
  }
  const p = page(); (p.sources[2].results[0] as any) = { ...file, conversation: 'ent-fabricated111111' }
  assert.throws(() => collectionRows(p), /range|provenance/)
})
test('legacy path-less unavailable file rows remain inspectable while new collection refuses them', () => {
  const sources: MagnetConfig['sources'] = [...config.sources, { kind: 'file', collection: 'col-held' }]
  assert.equal(unsupportedMagnet({ ...config, sources }, config.id), undefined)
  const old = page(); old.sources[2] = { source: { kind: 'file', collection: 'col-held' }, key: 'file:col-held:', status: 'unavailable', results: [] } as any
  assert.equal(collectionRows(old).results.length, 1)
  assert.throws(() => collectionChange(config, sources, ['post'], '', ''), /Choose one held file/)
})
test('exact file selection refuses expansion, traversal, directories and schema overflow', () => {
  for (const path of ['', '../file', 'folder/', '*.txt', '/absolute', 'C:\\absolute', 'a//b', 'a/./b', 'a'.repeat(301), '[abc].txt', 'nested:stream', ' file.txt', 'file.txt ']) assert.ok(exactFileIssue('col-held', path), path)
  assert.equal(exactFileIssue('col-held', 'nested/file.txt'), null)
  assert.ok(exactFileIssue('bad collection', 'file.txt'))
})
test('reconfiguration preserves unsupported saved selection and modes, with Conversation/type/date bounds', () => {
  const saved = { ...config, selection: { criteria: 'saved semantic criterion' }, collection: { mode: 'paused' as const } }
  const changed = collectionChange(saved, [...config.sources, { kind: 'file', collection: 'col-held', path: 'file.txt' }], ['post', 'image'], '2026-01-01', '')
  assert.equal(changed.selection.criteria, saved.selection.criteria); assert.equal(saved.collection.mode, 'paused'); assert.equal('collection' in changed, false)
  assert.deepEqual(collectionChange(config, [{ kind: 'file', collection: 'col-held', path: 'a' }], ['post'], '', '').sources, [{ kind: 'file', collection: 'col-held', path: 'a' }])
  assert.throws(() => collectionChange(config, [...config.sources, ...config.sources], ['post'], '', ''), /once/)
  assert.throws(() => collectionChange(config, config.sources, ['post'], '2026-02-30', ''), /valid date/)
})

test('manual setup changes modes only on explicit choice and preserves source selection and inquiry identity', () => {
  const saved = { ...config, selection: { criteria: 'saved criterion' }, collection: { mode: 'paused' as const }, conversation: 'ent-own111111' }
  const unchanged = collectionChange(saved, saved.sources, ['post'], '', '')
  assert.equal('activation' in unchanged, false)
  const changed = collectionChange(saved, saved.sources, ['post'], '', '', true)
  assert.equal(supportsManualCollection({ ...saved, ...changed }), true)
  assert.deepEqual(changed.sources, saved.sources)
  assert.equal(changed.selection.criteria, saved.selection.criteria)
  assert.equal('conversation' in changed, false)
})

test('empty collection ordinary help has work reach, no implicit evidence and preserves Composer permissions', () => {
  const post = { action: 'ask-participant', text: 'How do I configure this Magnet?', parts: [{ type: 'text', text: 'How do I configure this Magnet?' }], dispatch: [{ participant: 'ent-agent111111', runtime: 'codex', coordinate: false, repository: 'existing-work' }] }
  const out = composerRequest(post, config.id, 'ent-owner111111', null, 'ordinary-empty', null)
  assert.equal((out.parts as any[]).some(p => p.type === 'file'), false)
  const dispatch = (out.dispatch as any[])[0]
  assert.equal(dispatch.reach, 'work'); assert.equal(dispatch.coordinate, false); assert.equal(dispatch.repository, 'existing-work')
  assert.match(dispatch.work, /ordinary Magnet configuration/)
  assert.match(dispatch.work, /Do not retrieve or cite unrelated/)
  assert.doesNotMatch(dispatch.work, /Read it with read_artifact/)
})

test('ordinary inquiry help never attaches an available batch or dispatches a grounded Perspective', () => {
  const out = composerRequest({ action: 'ask-participant', text: 'Help refine this hypothesis', parts: [], _magnetAssistance: { perspective: { perspective: 'ent-lens111111', name: 'Lens', question: 'A hypothesis', revision: 'adm-question111111' } }, dispatch: [{ participant: 'ent-agent111111' }] }, config.id, 'ent-owner111111', null, 'ordinary-lens', { post: 'ent-batch111111', artifact: { ref: 'adm-batch111111', digest, size: 10, media_type: 'application/json' }, at: 1 })
  assert.equal('_magnetAssistance' in out, false)
  assert.equal((out.parts as any[]).some(p => p.type === 'file'), false)
  assert.match((out.dispatch as any[])[0].work, /A hypothesis/)
  assert.match((out.dispatch as any[])[0].work, /grounded Perspective execution is disabled/)
})

test('ordinary Ask Mentis preserves Work controls and explicitly narrows intake artifacts to work', () => {
  const out = composerRequest({ action: 'ask-mentis', text: 'Help configure this', parts: [], dispatch: [], ask_mentis: { coordinate: false, consent: { mode: 'ask' } } }, config.id, 'ent-owner111111', null, 'ordinary-intake', null)
  assert.deepEqual(out.ask_mentis, { coordinate: false, consent: { mode: 'ask' }, reach: 'work' })
  assert.equal((out.parts as any[]).some(p => p.type === 'file'), false)
})
test('editing other collection fields preserves timestamp precision and orders timezone offsets by their actual time', () => {
  const after = '2026-01-01T23:30:00-05:00', before = '2026-01-02T06:00:00+00:00'
  const changed = collectionChange(config, config.sources, ['post'], after, before)
  assert.equal(changed.selection.dates.after, after); assert.equal(changed.selection.dates.before, before)
  assert.throws(() => collectionChange(config, config.sources, ['post'], '2026-01-02T01:00:00-05:00', '2026-01-02T02:00:00+00:00'), /end date/)
  assert.throws(() => collectionChange(config, config.sources, ['post'], '2026-02-30T12:00:00Z', ''), /valid date/)
})
test('historical page remains frozen when the current collection definition changes', async () => {
  const changed = { ...config, sources: [{ kind: 'conversation' as const, conversation: 'ent-new111111' }] }
  const r = createMagnetResource({ id: 'history', brainKey: 'origin|fixture|brain-a', saved: { id: config.id, name: 'History', config: changed }, get: async () => ({ status: 200, body: { magnet: config.id, config: changed, activation: { post: 'ent-captured111111', artifact: { ref: 'adm-batch111111', digest } }, page: page() } }) })
  await r.read(); assert.equal(r.snapshot().error, undefined); assert.equal(r.snapshot().results[0].version, original.version); assert.equal(r.saved.config?.sources[0].kind, 'conversation')
})
test('an explicit historical batch read refuses a substituted latest artifact', async () => {
  const calls: string[] = [], r = createMagnetResource({ id: 'history', brainKey: 'origin|fixture|brain-a', saved: { id: config.id, name: 'History', config }, get: async (path) => { calls.push(path); return { status: 200, body: { magnet: config.id, config, activation: { post: 'ent-captured111111', artifact: { ref: 'adm-other111111', digest } }, page: page() } } } })
  await r.selectBatch!({ ref: 'adm-batch111111', digest }); assert.match(calls[0], /batch=adm-batch111111/); assert.match(r.snapshot().error!, /historical read/); assert.equal(r.snapshot().activation, null)
})
test('Perspective Composer routing sends actual package parts and keeps Work permissions and original send key', () => {
  const routed = composerRequest(perspectiveRequest({ action: 'ask-participant', text: 'Exact question', parts: [{ type: 'text', text: 'Exact question' }, { type: 'file', ref: 'adm-extra111111' }], dispatch: [{ participant: 'ent-agent111111', runtime: 'codex', coordinate: true, reach: 'conversation' }] }, prepared), config.id, 'ent-owner111111', 'ent-reply111111', prepared.request_op, null)
  assert.equal(routed.op, prepared.request_op); assert.equal(routed.replies_to, 'ent-reply111111'); assert.equal('_magnetPerspective' in routed, false)
  assert.deepEqual((routed.parts as any[]).filter((p) => p.type === 'file').map((p) => p.ref), ['adm-extra111111', 'adm-manifest111111'])
  assert.equal((routed.dispatch as any[])[0].coordinate, true); assert.equal((routed.dispatch as any[])[0].reach, 'work'); assert.equal((routed.dispatch as any[])[0].runtime, 'codex')
})
test('durable server history pagination recovers the original unresolved package without a new question write', async () => {
  brain.saw('brain-a@instance-one')
  const store = new PerspectiveStore(resource()), calls: string[] = []
  store.update({ selected: prepared.perspective, rows: [{ perspective: prepared.perspective, name: 'Lens', retired: false, question: prepared.question, events: 120 }] })
  store.get = async (tail) => { calls.push(tail); if (tail.includes('/intents/')) return { prepared, binding: null, answers: [] }; return { events: tail.includes('cursor=next') ? [{ post: prepared.intent, event: 'prepared' }] : [], next: tail.includes('cursor=next') ? null : 'next' } }
  store.write = async () => { throw new Error('must not write a replacement question') }
  const got = await store.prepare(prepared.text, 'new-composer-key')
  assert.equal(got.request_op, prepared.request_op); assert.equal(calls.length, 3); assert.equal(store.snapshot().historyComplete, true)
  await assert.rejects(store.prepare('Changed question', 'another-key'), /earlier frozen inquiry/)
})
test('a lens change during preparation prevents a different question from being sent', async () => {
  brain.saw('brain-a@instance-one')
  const store = new PerspectiveStore(resource()); store.update({ selected: prepared.perspective })
  let done!: () => void; store.completeHistory = () => new Promise<void>((resolve) => { done = resolve })
  const pending = store.prepare('Question', 'key'); store.update({ selected: 'ent-other111111' }); done()
  await assert.rejects(pending, /Perspective changed/)
})
test('Perspective store refuses a late response after Brain replacement', async () => {
  brain.saw('brain-a@instance-one')
  const store = new PerspectiveStore(resource()), originalFetch = globalThis.fetch
  let finish!: (r: Response) => void
  globalThis.fetch = (() => new Promise<Response>((resolve) => { finish = resolve })) as typeof fetch
  try { const pending = store.get(); brain.move(); finish(new Response(JSON.stringify({ brain: 'brain-a@instance-one' }), { status: 200 })); await assert.rejects(pending, /late Perspective/); await assert.rejects(store.get(), /another Brain/) }
  finally { globalThis.fetch = originalFetch; brain.saw('brain-a@instance-one') }
})
