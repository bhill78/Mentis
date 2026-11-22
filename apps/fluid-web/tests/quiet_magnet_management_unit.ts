import { test } from 'node:test'
import assert from 'node:assert/strict'
import { makeMagnet, conversationChoices } from '../src/quiet2/magnets/managementApi'
import { BRAIN_PATH, page } from '../src/brainBinding'
const A = 'ent-aaaaaaaaaaaa', B = 'ent-bbbbbbbbbbbb', key = 'http://fixture|dev|fixture-corpus'
const at = { key, arrangement: A, source: B, name: 'Observed field notes', op: 'fixture-create-1' }
const answer = (v: unknown, status = 200) => new Response(JSON.stringify(v), { status, headers: { 'Content-Type': 'application/json' } })
const calls: { path: string; init?: RequestInit }[] = []
let postResponse: () => Response = () => answer({ magnet: { id: 'mag-fixture', sources: [{ kind: 'conversation', conversation: B }], selection: {} } })
globalThis.fetch = (async (path: string, init?: RequestInit) => {
  calls.push({ path, init })
  if (path === BRAIN_PATH) return answer({ brain: { corpus_id: 'fixture-corpus', instance: 'instance-one' } })
  return postResponse()
}) as typeof fetch
test('creation confirms identity and reuses the atomic supported door and seed', async () => {
  calls.length = 0
  const got = await makeMagnet(at)
  assert.equal(got.id, 'mag-fixture'); assert.equal(got.reason, undefined)
  assert.equal(calls.length, 2); assert.equal(calls[0].path, BRAIN_PATH)
  const sent = calls[1], body = JSON.parse(sent.init!.body as string)
  assert.equal(sent.path, `/fluid/api/arrangements/${A}/magnets`)
  assert.equal(new Headers(sent.init!.headers).get('X-Mentis-Brain'), 'fixture-corpus@instance-one')
  assert.deepEqual(body.seed.sources, [{ kind: 'conversation', conversation: B }])
  assert.equal(body.seed.conversation, undefined); assert.equal(body.id, undefined)
  assert.equal(body.attach.zone.show, 'magnet'); assert.equal(body.op, at.op)
})
test('invalid references or an unknown resource Brain send no mutation', async () => {
  calls.length = 0
  await assert.rejects(makeMagnet({ ...at, source: '../elsewhere' }))
  assert.equal(calls.length, 0)
  await assert.rejects(makeMagnet({ ...at, key: 'http://fixture|dev|other' }))
  assert.equal(calls.filter((c) => c.init?.method === 'POST').length, 0)
})
test('an uncertain create result is not retried automatically', async () => {
  calls.length = 0; postResponse = () => answer({ error: 'result not available' }, 503)
  await assert.rejects(makeMagnet(at), /result not available/)
  assert.equal(calls.filter((c) => c.init?.method === 'POST').length, 1)
})
test('Conversation discovery is explicitly paged and searches the supported endpoint', async () => {
  calls.length = 0; postResponse = () => answer({ conversations: [{ id: A, name: 'Origin' }, { id: 'invalid', name: 'No' }], next: B })
  const got = await conversationChoices('field & notes', A, new AbortController().signal)
  assert.deepEqual(got.rows, [{ id: A, name: 'Origin' }]); assert.equal(got.next, B)
  const url = new URL(calls[0].path, 'http://fixture')
  assert.equal(url.pathname, '/fluid/api/conversations'); assert.equal(url.searchParams.get('q'), 'field & notes')
  assert.equal(url.searchParams.get('limit'), '40'); assert.equal(url.searchParams.get('cursor'), A)
})
test('a Brain-change refusal retires subsequent creation authority', async () => {
  postResponse = () => answer({ kind: 'BrainChanged', error: 'different Brain' }, 409)
  await assert.rejects(makeMagnet(at), /different Brain/)
  assert.equal(page.moved(), true)
  calls.length = 0; await assert.rejects(makeMagnet(at))
  assert.equal(calls.filter((c) => c.init?.method === 'POST').length, 0)
})
