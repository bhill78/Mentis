import { test } from 'node:test'
import assert from 'node:assert/strict'
import { makeMagnet, conversationChoices, listMagnets } from '../src/quiet2/magnets/managementApi'
import { listedMagnets, openableMagnet } from '../src/quiet2/magnets/Management'
import { BRAIN_PATH, page } from '../src/brainBinding'
const A = 'ent-aaaaaaaaaaaa', B = 'ent-bbbbbbbbbbbb', key = 'http://fixture|dev|fixture-corpus'
const at = { key, arrangement: A, source: B, name: 'Observed field notes', op: 'fixture-create-1' }
const answer = (v: unknown, status = 200) => new Response(JSON.stringify(v), { status, headers: { 'Content-Type': 'application/json' } })
const calls: { path: string; init?: RequestInit }[] = []
let postResponse: () => Response = () => answer({ magnet: { id: 'mag-fixture', sources: [{ kind: 'conversation', conversation: B }], selection: {} } })
globalThis.fetch = (async (path: string, init?: RequestInit) => {
  calls.push({ path, init })
  if (path === BRAIN_PATH) return answer({ brain: { corpus_id: 'fixture-corpus', instance: 'instance-one' } })
  if (path.startsWith('/fluid/api/arrangements/') && init?.method !== 'POST') return answer({ layout: { format: 'mentis.fluid-arrangement', version: 2 } })
  return postResponse()
}) as typeof fetch
/** The dispatcher above, kept so a test that installs its own doors (Part G2's
 *  acceptance) can put this one back for the tests that follow it. */
const baseFetch = globalThis.fetch
test('creation confirms identity and reuses the atomic supported door and seed', async () => {
  calls.length = 0
  const got = await makeMagnet(at)
  assert.equal(got.id, 'mag-fixture'); assert.equal(got.reason, undefined)
  assert.equal(calls.length, 3); assert.equal(calls[0].path, BRAIN_PATH)
  const sent = calls[2], body = JSON.parse(sent.init!.body as string)
  assert.equal(sent.path, `/fluid/api/arrangements/${A}/magnets`)
  assert.equal(new Headers(sent.init!.headers).get('X-Mentis-Brain'), 'fixture-corpus@instance-one')
  assert.deepEqual(body.seed.sources, [{ kind: 'conversation', conversation: B }])
  assert.equal(body.seed.conversation, undefined); assert.equal(body.id, undefined)
  assert.deepEqual(body.seed.activation, { mode: 'manual' }); assert.deepEqual(body.seed.processing, { operations: [{ op: 'extract' }] }); assert.equal(body.attach.base, undefined)
  assert.equal(body.attach.zone.show, 'magnet'); assert.equal(body.op, at.op)
})
test('independent creation uses Brain Home without a container Conversation', async () => {
  calls.length = 0; postResponse = () => answer({ magnet: { id: 'mag-home', sources: [{ kind: 'conversation', conversation: B }], selection: {} } })
  const got = await makeMagnet({ ...at, arrangement: 'home', op: 'fixture-home-create' })
  assert.equal(got.id, 'mag-home')
  assert.equal(calls[1].path, '/fluid/api/arrangements/home')
  assert.equal(calls[2].path, '/fluid/api/arrangements/home/magnets')
})
test('a Magnet is created from a name alone, with no configured source', async () => {
  calls.length = 0
  postResponse = () => answer({ magnet: { id: 'mag-idea', sources: [], selection: {}, identity: { name: 'An idea' } } })
  const got = await makeMagnet({ ...at, source: '', name: 'An idea', op: 'fixture-idea-create' })
  assert.equal(got.id, 'mag-idea'); assert.equal(got.reason, undefined)
  const body = JSON.parse(calls[2].init!.body as string)
  assert.deepEqual(body.seed.sources, [], 'none is sent as none; nothing is substituted')
  assert.deepEqual(body.seed.identity, { name: 'An idea' }, 'the name goes in the definition, not only on the zone')
  assert.equal(body.attach.zone.name, 'An idea')
  // An answer that quietly configured a source is not the creation that was asked for.
  postResponse = () => answer({ magnet: { id: 'mag-idea', sources: [{ kind: 'conversation', conversation: B }], selection: {} } })
  await assert.rejects(makeMagnet({ ...at, source: '', name: 'An idea', op: 'fixture-idea-create-2' }), /different Brain or source/)
  // And one asked for with a source still has to come back with exactly that one.
  postResponse = () => answer({ magnet: { id: 'mag-idea', sources: [], selection: {} } })
  await assert.rejects(makeMagnet({ ...at, op: 'fixture-idea-create-3' }), /different Brain or source/)
  postResponse = () => answer({ magnet: { id: 'mag-fixture', sources: [{ kind: 'conversation', conversation: B }], selection: {} } })
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
test('the definition catalogue is read directly and preserves unavailable rows', async () => {
  calls.length = 0
  postResponse = () => answer({ magnets: [
    { id: 'mag-alpha', name: 'Alpha', config: { id: 'mag-alpha', sources: [{ kind: 'conversation', conversation: A }], selection: {} } },
    { id: 'mag-broken', name: 'Broken', reason: 'definition unreadable' },
    { id: 'not-a-magnet', name: 'Ignored' },
  ] })
  const got = await listMagnets(new AbortController().signal)
  assert.equal(calls[0].path, '/fluid/api/magnets')
  assert.deepEqual(got.map((row) => [row.id, row.reason]), [['mag-alpha', undefined], ['mag-broken', 'definition unreadable']])
})
test('list search, availability selection and open eligibility share one rule', () => {
  const available = { id: 'mag-alpha' as const, name: 'Field Notes', config: {
    id: 'mag-alpha' as const, sources: [{ kind: 'conversation' as const, conversation: A }], selection: {},
    collection: { mode: 'one-time' as const }, synthesis: { mode: 'manual' as const },
    notifications: { newItems: false, changes: false, failures: false }, presentation: { renderer: 'disc' as const },
  } }
  const unavailable = { id: 'mag-beta' as const, name: 'Archive', reason: 'unreadable' }
  assert.deepEqual(listedMagnets([available, unavailable], 'notes', 'all').map((row) => row.id), ['mag-alpha'])
  assert.deepEqual(listedMagnets([available, unavailable], '', 'unavailable').map((row) => row.id), ['mag-beta'])
  assert.equal(openableMagnet(available), true)
  assert.equal(openableMagnet(unavailable), false)
})
test('a successful response for a different source is not opened', async () => {
  postResponse = () => answer({ magnet: { id: 'mag-fixture', sources: [{ kind: 'conversation', conversation: A }], selection: {} } })
  await assert.rejects(makeMagnet(at), /different Brain or source/)
})
/* -- PART G2: ONE SENTENCE, ONE PRESS ------------------------------------------
 *
 * The owner's correction `ent-8a4357b5f7fc`: "Purpose-driven creation should
 * lead directly to activation and useful results, without requiring the user to
 * navigate several configuration screens." What is proved here: the proposal is
 * a read, one acceptance runs the three existing doors in order, an empty or
 * failed first collection says so in plain words, and nothing creation shows is
 * a raw identifier, a JSON blob or an internal mode word. */
import { renderToStaticMarkup } from 'react-dom/server'
import { createElement } from 'react'
import { acceptProposal, proposeMagnet, NOTHING_TO_COLLECT_YET, type MagnetProposal } from '../src/quiet2/magnets/managementApi'
import Management, { sourceSummary, followsWhat } from '../src/quiet2/magnets/Management'

const PROPOSAL: MagnetProposal = {
  sentence: 'the solid electrolytes work every day',
  name: 'The solid electrolytes work',
  sources: [{ kind: 'conversation', conversation: A }] as unknown as MagnetProposal['sources'],
  selection: { criteria: 'the solid electrolytes work every day', informationTypes: ['post', 'file'] },
  cadence: { mode: 'scheduled', schedule: 'P1D' },
  words: { sources: 'Solid electrolytes', collect: 'Posts, files, images and attachments', cadence: 'Every day' },
  listed: [{ title: 'Solid electrolytes', says: 'Conversation and its attachments' }],
  seed: {
    sources: [{ kind: 'conversation', conversation: A }],
    selection: { criteria: 'the solid electrolytes work every day' },
    collection: { mode: 'one-time' }, synthesis: { mode: 'manual' },
    notifications: { newItems: false, changes: false, failures: false },
    presentation: { renderer: 'disc' }, activation: { mode: 'manual' },
    processing: { operations: [{ op: 'extract' }] },
  },
  change: { identity: { name: 'The solid electrolytes work' }, sources: [{ kind: 'conversation', conversation: A }] },
  unavailable: [{ title: 'Harbour feeds', kind: 'rss-atom', why: 'the RSS / Atom connector is not available yet' }],
}

/** The doors an acceptance is allowed to use, and nothing else. */
function acceptance(opts: { results?: number; activateFails?: boolean; sources?: unknown[] } = {}) {
  const sources = opts.sources ?? (PROPOSAL.seed.sources as unknown[])
  const made = { id: 'mag-followed', sources, selection: {}, identity: { name: PROPOSAL.name }, collection: { mode: 'one-time' } }
  globalThis.fetch = (async (path: string, init?: RequestInit) => {
    calls.push({ path, init })
    if (path === BRAIN_PATH) return answer({ brain: { corpus_id: 'fixture-corpus', instance: 'instance-one' } })
    if (path.startsWith('/fluid/api/participants')) return answer({ me: 'ent-ownerownerow' })
    if (path.endsWith('/magnets') && init?.method === 'POST') return answer({ magnet: made })
    if (path.endsWith('/activate')) return opts.activateFails
      ? answer({ error: 'The source was busy.', refused: true }, 422)
      : answer({ magnet: made.id, artifact: { ref: 'adm-aaaaaaaaaaaa' }, page: { results: opts.results ?? 3 }, conversation: B })
    if (path.endsWith('/reconfigure')) return answer({ magnet: { ...made, collection: PROPOSAL.cadence } })
    if (path.startsWith('/fluid/api/arrangements/')) return answer({ layout: { format: 'mentis.fluid-arrangement', version: 2 } })
    return answer({ error: 'no door here' }, 404)
  }) as typeof fetch
}

test('a sentence is proposed by a read, and asking writes nothing', async () => {
  calls.length = 0
  globalThis.fetch = (async (path: string, init?: RequestInit) => {
    calls.push({ path, init })
    return answer({ proposal: PROPOSAL })
  }) as typeof fetch
  const got = await proposeMagnet('  the solid electrolytes work every day  ')
  assert.equal(calls.length, 1, 'one request, and no arrangement read or Brain write')
  assert.equal(calls[0].path, '/fluid/api/magnets/propose')
  assert.deepEqual(JSON.parse(calls[0].init!.body as string), { sentence: 'the solid electrolytes work every day' })
  assert.equal(got.name, PROPOSAL.name)
  assert.equal(got.words.cadence, 'Every day')
  assert.deepEqual(got.listed, PROPOSAL.listed)
  calls.length = 0
  await assert.rejects(proposeMagnet('   '), /one sentence/)
  assert.equal(calls.length, 0, 'a blank sentence never reaches the server')
})

test('one acceptance applies the configuration, collects, and turns refresh on', async () => {
  calls.length = 0; acceptance()
  const done = await acceptProposal({ key, arrangement: 'home', proposal: PROPOSAL, op: 'g2-accept-1' })
  const posted = calls.filter((c) => c.init?.method === 'POST').map((c) => c.path)
  // The three existing doors, in order. No new accept door, and no settings step.
  assert.deepEqual(posted, [
    '/fluid/api/arrangements/home/magnets',
    '/fluid/api/magnets/mag-followed/activate',
    '/fluid/api/arrangements/home/magnets/mag-followed/reconfigure',
  ])
  // The proposal's own checked seed is what was sent, with the name written in.
  const body = JSON.parse(calls.find((c) => c.path.endsWith('/magnets') && c.init?.method === 'POST')!.init!.body as string)
  assert.deepEqual(body.seed.sources, PROPOSAL.seed.sources)
  assert.deepEqual(body.seed.identity, { name: PROPOSAL.name })
  assert.equal(body.seed.collection.mode, 'one-time', 'the first collection runs from the one-time facets')
  // And the cadence lands after it, as its own facet.
  const cadence = JSON.parse(calls.find((c) => c.path.endsWith('/reconfigure'))!.init!.body as string)
  assert.deepEqual(cadence.change, { collection: { mode: 'scheduled', schedule: 'P1D' } })
  assert.equal(done.collected, 3)
  assert.equal(done.refreshing, true)
  assert.equal(done.words, 'Collected 3 items. Every day.')
  assert.equal(done.saved.config!.collection.mode, 'scheduled', 'the returned definition carries the cadence')
})

test('an empty or failed first collection is said in plain words, never silently', async () => {
  calls.length = 0; acceptance({ results: 0 })
  const empty = await acceptProposal({ key, arrangement: 'home', proposal: PROPOSAL, op: 'g2-accept-2' })
  assert.equal(empty.collected, 0)
  assert.match(empty.words, /Nothing was collected/)
  assert.match(empty.words, /Open Sources/, 'the one thing to do about it')
  assert.match(empty.words, /every day/, 'and that it will look again on its own')

  calls.length = 0; acceptance({ activateFails: true })
  const failed = await acceptProposal({ key, arrangement: 'home', proposal: PROPOSAL, op: 'g2-accept-3' })
  assert.equal(failed.collected, null)
  assert.match(failed.words, /The source was busy\./)
  assert.match(failed.words, /try again on its own/)
  // The Magnet exists and is returned: a failed collection is not a failed creation.
  assert.equal(failed.saved.id, 'mag-followed')

  calls.length = 0; acceptance({ sources: [] })
  const none = await acceptProposal({ key, arrangement: 'home', op: 'g2-accept-4',
    proposal: { ...PROPOSAL, sources: [], seed: { ...PROPOSAL.seed, sources: [] } } })
  assert.equal(none.collected, null)
  assert.equal(none.words, NOTHING_TO_COLLECT_YET)
  assert.equal(none.refreshing, false, 'nothing to refresh, so no cadence is sent')
  assert.equal(calls.filter((c) => c.path.endsWith('/activate')).length, 0, 'nothing is collected from no sources')
})

test('Magnet Management shows no raw identifier, blob or internal mode word', () => {
  const html = renderToStaticMarkup(createElement(Management, {
    open: true, brainKey: key, conversation: null, canCreate: () => true, fixture: false,
    onOpen: () => {}, onClose: () => {},
  }))
  // The way in is said in the owner's words, not the schema's.
  assert.ok(html.includes('Follow something new'), html.slice(0, 400))
  for (const gone of ['mag-', 'ent-', 'one-time', 'JSON', 'Saved location', 'Synthesis']) {
    assert.ok(!html.includes(gone), gone + ' still appears in Magnet Management')
  }
})

test('a source is described by what it is, not by its schema kind', () => {
  const config = {
    id: 'mag-a' as const, selection: { criteria: 'the tide work' },
    sources: [{ kind: 'conversation' as const, conversation: A }],
    collection: { mode: 'scheduled' as const, schedule: 'P1D' },
    synthesis: { mode: 'manual' as const },
    notifications: { newItems: false, changes: false, failures: false },
    presentation: { renderer: 'disc' as const },
  }
  assert.equal(sourceSummary(config), '1 source · Conversations')
  assert.equal(followsWhat(config), 'the tide work')
  assert.equal(sourceSummary({ ...config, sources: [] }), 'Nothing yet · ready to converse')
  assert.equal(sourceSummary(undefined), 'Unavailable here')
})

/* Last, because it retires this page's binding for good: anything after it
   cannot confirm a Brain, which is the point of it. */
test('a Brain-change refusal retires subsequent creation authority', async () => {
  globalThis.fetch = baseFetch
  postResponse = () => answer({ kind: 'BrainChanged', error: 'different Brain' }, 409)
  await assert.rejects(makeMagnet(at), /different Brain/)
  assert.equal(page.moved(), true)
  calls.length = 0; await assert.rejects(makeMagnet(at))
  assert.equal(calls.filter((c) => c.init?.method === 'POST').length, 0)
})
