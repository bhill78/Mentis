/* The additions proxy's decisions, with no server and no fixture on disk:
 * what it calls a read, what it calls one of its two writes, and every body
 * it refuses. `node tools/test_quiet_magnet_additions_preview.mjs`
 */
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import {
  FORMAT, MAX_TEXT, REPO, canonicalPath, classify, fixtureOf, forwardHeaders,
  magnetRefusal, postRefusal, rawPath, readOnlyRequest,
} from './quiet-magnet-additions-preview.mjs'

const A = 'ent-aaaaaaaaaaaa', B = 'ent-bbbbbbbbbbbb', C = 'ent-cccccccccccc'
const P1 = 'ent-111111111111', P2 = 'ent-222222222222'
const fixture = { A, B, C, corpusId: 'fixture-corpus', sources: [A, B, C],
  participants: [P1, P2], primary: 'x', root: 'x' }

let passed = 0, failed = 0
const check = (name, fn) => {
  try { fn(); passed++ } catch (error) { failed++; console.error(`FAILED ${name}: ${error.message}`) }
}
const is = (actual, expected, what) => assert.equal(actual, expected, what)

// -- paths ------------------------------------------------------------------

check('rawPath keeps the raw path and drops the query', () => {
  is(rawPath('/fluid/api/posts?x=1'), '/fluid/api/posts')
  is(rawPath('/fluid/api/po%73ts'), '/fluid/api/po%73ts')
})

check('canonicalPath refuses encoded, traversing and doubled paths', () => {
  is(canonicalPath('/fluid/api/posts'), true)
  is(canonicalPath('/fluid/api/po%73ts'), false)
  is(canonicalPath('/fluid/api//posts'), false)
  is(canonicalPath('/fluid/api/./posts'), false)
  is(canonicalPath('/fluid/api/x/../posts'), false)
  is(canonicalPath('/fluid\\api\\posts'), false)
  is(canonicalPath('fluid/api/posts'), false)
})

check('the read rule is the read-only trial\'s, capacity included', () => {
  for (const [method, url, expected] of [
    ['GET', '/fluid/api/magnets/mag-x/read?mode=summary', true],
    ['HEAD', '/api/brain?identity=1', true],
    ['OPTIONS', '/api/brain', true],
    ['POST', '/fluid/api/posts', false],
    ['GET', '/api/capacity', false],
    ['GET', '/api/capacity?all=1', false],
    ['GET', '/api/%63apacity', false],
    ['GET', '/api/capacity/anything', false],
    ['GET', '/api/%', false],
  ]) is(readOnlyRequest(method, url), expected, `${method} ${url}`)
})

// -- what each request is ---------------------------------------------------

check('the two allowed writes are recognised by exact raw path', () => {
  is(classify('POST', '/fluid/api/posts', fixture).kind, 'post')
  is(classify('POST', `/fluid/api/arrangements/${A}/magnets`, fixture).kind, 'magnet')
  is(classify('post', '/fluid/api/posts', fixture).kind, 'post')
})

check('an encoded alias of an allowed write is refused, never forwarded', () => {
  for (const url of ['/fluid/api/po%73ts', '/fluid/api/posts%2f', '/fluid/api//posts',
    '/fluid/api/x/../posts', `/fluid/api/arrangements/${A}/magnets%20`]) {
    const what = classify('POST', url, fixture)
    is(what.kind, 'refuse', url)
    is(what.status, 400, url)
  }
})

check('a trailing slash on an allowed write is not that write', () => {
  is(classify('POST', '/fluid/api/posts/', fixture).kind, 'refuse')
})

check('another arrangement\'s magnet creation is refused', () => {
  is(classify('POST', `/fluid/api/arrangements/${B}/magnets`, fixture).kind, 'refuse')
})

check('every other write is refused with 403', () => {
  for (const [method, url] of [
    ['POST', '/fluid/api/posts/ent-1/edit'], ['POST', '/fluid/api/posts/ent-1/delete'],
    ['POST', '/fluid/api/posts/ent-1/comments'], ['POST', '/fluid/api/posts/ent-1/address'],
    ['POST', '/fluid/api/requests'], ['POST', '/fluid/api/conversations'],
    ['POST', `/fluid/api/arrangements/${A}`], ['POST', `/fluid/api/arrangements/${A}/magnets/mag-1/remove`],
    ['POST', '/fluid/api/magnets/mag-1/activate'], ['POST', '/fluid/api/magnets/mag-1/conversation'],
    ['POST', '/api/worker'], ['POST', '/api/owner/login'], ['PUT', '/fluid/api/posts'],
    ['DELETE', '/fluid/api/posts'], ['PATCH', '/fluid/api/posts'],
  ]) {
    const what = classify(method, url, fixture)
    is(what.kind, 'refuse', `${method} ${url}`)
    is(what.status, 403, `${method} ${url}`)
  }
})

check('capacity is refused as a read too', () => {
  is(classify('GET', '/api/capacity', fixture).kind, 'refuse')
})

check('ordinary reads and the built page are told apart', () => {
  is(classify('GET', '/fluid/api/conversations/' + C, fixture).kind, 'read')
  is(classify('GET', '/api/brain?identity=1', fixture).kind, 'read')
  is(classify('GET', '/assets/index.js', fixture).kind, 'ui')
  is(classify('GET', '/quiet2', fixture).kind, 'ui')
})

// -- a fixture post ---------------------------------------------------------

const good = { conversation: C, author: P1, text: 'a fixture note', op: 'op-1' }

check('a record-only post into C is accepted', () => {
  is(postRefusal(good, fixture), null)
  is(postRefusal({ ...good, action: 'record-only' }, fixture), null)
  is(postRefusal({ ...good, replies_to: 'ent-999999999999' }, fixture), null)
})

check('a post into any other Conversation is refused', () => {
  for (const cid of [A, B, 'ent-999999999999', undefined, null, 42])
    assert.ok(postRefusal({ ...good, conversation: cid }, fixture), String(cid))
})

check('asks, dispatch, addressing, parts and choices are refused', () => {
  for (const extra of [
    { action: 'ask-mentis' }, { action: 'ask-participant' },
    { dispatch: [{ participant: P2 }] }, { addressed_to: [P2] },
    { parts: [{ type: 'text', text: 'x' }] }, { chose: { expectation: 'opr-1' } },
    { topics: ['ent-1'] }, { governed: [] }, { requires: ['call_mentis_tools'] },
    { ask_mentis: {} },
  ]) assert.ok(postRefusal({ ...good, ...extra }, fixture), JSON.stringify(extra))
})

check('an author who is not a fixture participant is refused', () => {
  assert.ok(postRefusal({ ...good, author: 'ent-999999999999' }, fixture))
  assert.ok(postRefusal({ ...good, author: 'human:brian' }, fixture))
  assert.ok(postRefusal({ ...good, author: undefined }, fixture))
})

check('empty, oversize and non-plain text is refused', () => {
  assert.ok(postRefusal({ ...good, text: '' }, fixture))
  assert.ok(postRefusal({ ...good, text: '   ' }, fixture))
  assert.ok(postRefusal({ ...good, text: 'x'.repeat(MAX_TEXT + 1) }, fixture))
  assert.ok(postRefusal({ ...good, text: 'a\u0000b' }, fixture))
  is(postRefusal({ ...good, text: 'two\nlines\tand a tab' }, fixture), null)
})

check('a write without a stable operation key is refused', () => {
  assert.ok(postRefusal({ ...good, op: undefined }, fixture))
  assert.ok(postRefusal({ ...good, op: '' }, fixture))
})

check('a body that is not an object is refused', () => {
  for (const body of [null, 'text', 42, [], undefined])
    assert.ok(postRefusal(body, fixture), JSON.stringify(body ?? null))
})

// -- a fixture Magnet creation ----------------------------------------------

const seed = {
  sources: [{ kind: 'conversation', conversation: B }],
  selection: { informationTypes: ['post'] },
  collection: { mode: 'one-time' },
  synthesis: { mode: 'manual' },
  notifications: { newItems: false, changes: false, failures: false },
  presentation: { renderer: 'disc' },
}
const create = { seed, attach: { zone: { type: 'zone', show: 'magnet', name: 'Fixture' } }, op: 'op-2' }

check('a single-Conversation one-time Magnet is accepted', () => {
  is(magnetRefusal(create, fixture), null)
  is(magnetRefusal({ ...create, seed: { ...seed, sources: [{ kind: 'conversation', conversation: C }] } }, fixture), null)
  is(magnetRefusal({ ...create, seed: { ...seed, selection: { informationTypes: ['post', 'file', 'image', 'attachment'], dates: { after: '2026-01-01T00:00:00Z' } } } }, fixture), null)
})

check('a source outside this fixture, or more than one, is refused', () => {
  for (const sources of [
    [{ kind: 'conversation', conversation: 'ent-999999999999' }],
    [{ kind: 'conversation', conversation: B }, { kind: 'conversation', conversation: C }],
    [{ kind: 'brain', brain: B }], [{ kind: 'web', url: 'https://example.com' }],
    [{ kind: 'agent-results', conversation: B }], [],
    [{ kind: 'conversation', conversation: B, location: 'x' }],
  ]) assert.ok(magnetRefusal({ ...create, seed: { ...seed, sources } }, fixture), JSON.stringify(sources))
})

check('a configuration that would run something is refused', () => {
  for (const change of [
    { collection: { mode: 'continuous' } }, { collection: { mode: 'scheduled' } },
    { synthesis: { mode: 'on-new-information' } }, { synthesis: { mode: 'scheduled' } },
    { notifications: { newItems: true, changes: false, failures: false } },
    { notifications: { newItems: false, changes: false } },
    { selection: { informationTypes: ['link'] } },
    { selection: { informationTypes: [] } },
    { selection: { informationTypes: ['post', 'post'] } },
    { selection: { informationTypes: ['post'], dates: { after: 'yesterday' } } },
    { presentation: { renderer: 'fireworks' } },
    { destinations: [] }, { operations: [] }, { conversation: C },
  ]) assert.ok(magnetRefusal({ ...create, seed: { ...seed, ...change } }, fixture), JSON.stringify(change))
})

check('a fixed id, a wide fallback and an extra attach are refused', () => {
  assert.ok(magnetRefusal({ ...create, id: 'mag-1' }, fixture))
  assert.ok(magnetRefusal({ ...create, wideFallback: 'launcher' }, fixture))
  assert.ok(magnetRefusal({ ...create, attach: { ...create.attach, base: {} } }, fixture))
  assert.ok(magnetRefusal({ ...create, attach: { zone: { type: 'zone', show: 'objects', name: 'x' } } }, fixture))
  assert.ok(magnetRefusal({ ...create, attach: { zone: { type: 'zone', show: 'magnet', name: 'x'.repeat(81) } } }, fixture))
  assert.ok(magnetRefusal({ ...create, op: '' }, fixture))
})

// -- what is forwarded ------------------------------------------------------

check('credentials, grants and method overrides never reach the server', () => {
  const sent = forwardHeaders({
    host: '127.0.0.1:1', authorization: 'Bearer secret', cookie: 'mentis=secret',
    'proxy-authorization': 'Basic x', 'x-mentis-worker': 'grant',
    'x-http-method-override': 'DELETE', 'x-method-override': 'DELETE',
    'x-q2-brain': 'other', 'x-forwarded-for': '10.0.0.1', 'x-forwarded-host': 'evil',
    'x-forwarded-proto': 'https', 'x-real-ip': '10.0.0.1', via: '1.1 proxy',
    forwarded: 'for=10.0.0.1', origin: 'http://127.0.0.1:1',
    referer: 'http://127.0.0.1:1/quiet2', 'content-length': '12',
    'transfer-encoding': 'chunked', 'x-mentis-brain': 'fixture-corpus@abc',
    'content-type': 'application/json',
  }, { host: '127.0.0.1:2', write: true })
  for (const gone of ['authorization', 'cookie', 'proxy-authorization', 'x-mentis-worker',
    'x-http-method-override', 'x-method-override', 'x-q2-brain', 'x-forwarded-for',
    'x-forwarded-host', 'x-forwarded-proto', 'x-real-ip', 'via', 'forwarded',
    'origin', 'referer', 'content-length', 'transfer-encoding'])
    is(sent[gone], undefined, gone)
  is(sent['x-mentis-brain'], 'fixture-corpus@abc', 'the page\'s Brain binding is preserved')
  is(sent.host, '127.0.0.1:2')
  is(sent['x-mentis-client'], '1')
  is(sent['content-type'], 'application/json')
})

// -- the manifest gate ------------------------------------------------------

const manifest = {
  format: FORMAT, setup_closed: true,
  primary: { corpus_id: 'fixture-corpus', instance: '0123456789abcdef', A, B, C, arrangement_key: A },
  writes_allowed: { conversation: C, arrangement: A, magnet_sources: [A, B, C], participants: [P1, P2] },
}
const here = path.join(REPO, '.preview', `unit-${process.pid}`)
fs.mkdirSync(path.join(here, 'primary'), { recursive: true })
fs.writeFileSync(path.join(here, 'primary', 'corpus.db'), '')

check('a completed fixture manifest inside this checkout is read', () => {
  const read = fixtureOf(manifest, here)
  is(read.corpusId, 'fixture-corpus')
  is(read.binding, 'fixture-corpus@0123456789abcdef')
  is(read.C, C)
  is(read.A, A)
  assert.deepEqual(read.participants, [P1, P2])
})

check('a manifest outside this checkout is refused', () => {
  assert.throws(() => fixtureOf(manifest, 'C:\\Users\\someone\\elsewhere'), /inside this checkout/)
})

check('a live or installed Brain path is refused', () => {
  assert.throws(() => fixtureOf(manifest, path.join(REPO, 'AppData', 'x')),
    /installed or live Brain path|inside this checkout/)
})

check('a half-seeded or foreign manifest is refused', () => {
  assert.throws(() => fixtureOf({ ...manifest, setup_closed: false }, here), /setup has not completed/)
  assert.throws(() => fixtureOf({ ...manifest, format: 'quiet-magnet-disposable-fixture-v1' }, here), /not a .* manifest/)
  assert.throws(() => fixtureOf(null, here), /not a .* manifest/)
})

check('allowed writes that the seed does not name are refused', () => {
  assert.throws(() => fixtureOf({ ...manifest, writes_allowed: { ...manifest.writes_allowed, conversation: B } }, here),
    /the seeded fixture does not/)
  assert.throws(() => fixtureOf({ ...manifest, writes_allowed: { ...manifest.writes_allowed, arrangement: B } }, here),
    /the seeded fixture does not/)
  assert.throws(() => fixtureOf({ ...manifest, writes_allowed: { ...manifest.writes_allowed, participants: [] } }, here),
    /no allowed sources or participants/)
})

check('a fixture with no Brain where the manifest sits is refused', () => {
  const empty = path.join(REPO, '.preview', `unit-empty-${process.pid}`)
  fs.mkdirSync(empty, { recursive: true })
  assert.throws(() => fixtureOf(manifest, empty), /no fixture Brain/)
  fs.rmSync(empty, { recursive: true, force: true })
})

check('a fixture with no certain pinned instance is refused', () => {
  for (const instance of [undefined, null, '', 'stale-instance', '0123456789abcdef@copy'])
    assert.throws(() => fixtureOf({ ...manifest, primary: { ...manifest.primary, instance } }, here),
      /fixture instance/)
})

fs.rmSync(here, { recursive: true, force: true })

console.log(`${passed} passed, ${failed} failed, 0 skipped, 0 errors`)
process.exit(failed ? 1 : 0)
