/* M1: THE CONVERSATION ADAPTER THROUGH THE MAGNET READ ROUTE
 * (docs/magnets/M1-contract.md). Per-source status, a cursor per source, a
 * disc that asks only for a summary and walks nothing, abort reaching the
 * read, discs that take turns, and the store path where the route answers 404.
 * Shapes come from the fixtures Python and Rust are held to as well. */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import type { MagnetConfig, MagnetEnv, MagnetSource } from '../src/fluid/surface/magnet/types'
import { MAGNET_SOURCE_KINDS } from '../src/fluid/surface/magnet/types'
import { changeOf, createAdapters, draftProblems, holdingOf, magnetStatus, notRunning, sourceKey } from '../src/fluid/surface/magnet/model'
import { READ_ON_PAGES, createLive } from '../src/fluid/surface/magnet/live'
import { conversationAdapter, objectTypeOf, type ConversationReads, type ObjectRow } from '../src/fluid/surface/magnet/conversation'
import { createMagnetRoute, type RouteGet } from '../src/fluid/surface/magnet/route'
import { MAGNET_CONFIG_MISSING, noteMagnetsUnreadable, storedMagnet, type Arr } from '../src/fluid/workspace/place'

const fixture = (name: string) => JSON.parse(readFileSync(fileURLToPath(new URL(`../../../tests/fixtures/magnet-conformance/${name}`, import.meta.url)), 'utf8'))

const env: MagnetEnv = { permissions: new Set(['read']), connectors: new Set(), runtime: new Set(['one-time']) }
const cfg = (id: string, conversations: string[], over: Partial<MagnetConfig> = {}): MagnetConfig => ({
  id: id as MagnetConfig['id'],
  sources: conversations.map((conversation): MagnetSource => ({ kind: 'conversation', conversation })),
  selection: {}, collection: { mode: 'one-time' }, synthesis: { mode: 'manual' },
  notifications: { newItems: false, changes: false, failures: false }, presentation: { renderer: 'disc' }, ...over,
})

/** A fake store: every read counted, so a walk can't hide. */
function storeOf(route: ReturnType<typeof createMagnetRoute> | undefined) {
  const reads: string[] = []
  const store: ConversationReads = {
    posts: async (c) => { reads.push(`posts(${c})`); return { ids: ['store-post'] } },
    objects: async (c) => { reads.push(`objects(${c})`); return [] },
    search: async () => [],
    about: async (c) => { reads.push(`about(${c})`); return { title: 'From the store', posts: 1 } },
    ...(route ? { route } : {}),
  }
  const adapters = createAdapters()
  adapters.register(conversationAdapter(store))
  return { reads, live: createLive(adapters) }
}

const answers = (fn: (path: string) => { status: number; body: unknown } | Promise<{ status: number; body: unknown }>) => {
  const asked: string[] = []
  const get: RouteGet = async (path) => { asked.push(path); return fn(path) }
  return { asked, get }
}
const summaryAnswer = fixture('summary_answer.json')
const pageAnswer = fixture('page_answer.json')

/* -- a disc asks for a summary, and walks nothing ------------------------------ */
{
  const server = answers(() => ({ status: 200, body: summaryAnswer }))
  const { reads, live } = storeOf(createMagnetRoute(server.get))
  const got = await live.load(cfg('mag-a', ['ent-2865e11386f6', 'ent-4d627d2376e1']), env, { summaryOnly: true })
  assert.deepEqual(reads, [], 'the store read nothing: no posts, no object index')
  assert.equal(server.asked.length, 1, 'two sources share one read')
  assert.match(server.asked[0], /^magnets\/mag-a\/read\?mode=summary$/)
  assert.equal(got.summaries[0].summary.title, 'Tidewater')
  assert.equal(got.summaries[0].summary.posts, 42)
  assert.equal(got.summaries[0].summary.activity, 1793361600.5)
  assert.deepEqual(got.results, [], 'a summary lists nothing')
  assert.deepEqual(got.statuses?.map((s) => s.status), ['ok', 'unavailable'])
  assert.match(got.statuses?.[1].reason ?? '', /not a conversation/)
  const holding = holdingOf(got.results, 42, true)
  assert.deepEqual(holding, [{ type: 'post', count: 42 }], 'the orbit still counts its posts')
  assert.equal(magnetStatus(cfg('mag-a', ['ent-2865e11386f6']), { unread: 0, loading: false, held: 0, off: 0, newer: true }).state, 'new')
}

/* -- discs take turns, and one Magnet's sources share ---------------------------- */
{
  let running = 0, most = 0
  const release: Array<() => void> = []
  const server = answers(() => new Promise((resolve) => {
    running++; most = Math.max(most, running)
    release.push(() => { running--; resolve({ status: 200, body: { sources: [] } }) })
  }))
  const route = createMagnetRoute(server.get)
  const reads = [route.summary('mag-a'), route.summary('mag-b'), route.summary('mag-c'), route.summary('mag-a')]
  await new Promise((r) => setTimeout(r, 0))
  assert.equal(server.asked.length, 1, 'one summary at a time, whatever a screen of discs asks')
  while (release.length) { release.shift()!(); await new Promise((r) => setTimeout(r, 0)) }
  await Promise.all(reads)
  assert.equal(most, 1)
  assert.equal(server.asked.length, 3, 'mag-a was asked once, for both')
}

/* -- abort: a read waiting is dropped, one running is ended ---------------------- */
{
  let seen: AbortSignal | undefined
  let finish: (() => void) | undefined
  const asked: string[] = []
  const route = createMagnetRoute((path, signal) => {
    asked.push(path); seen = signal
    return new Promise((resolve) => { finish = () => resolve({ status: 200, body: { sources: [] } }) })
  })
  const leaving = new AbortController()
  const running = route.summary('mag-run', leaving.signal)
  const waiting = route.summary('mag-wait', leaving.signal)
  await new Promise((r) => setTimeout(r, 0))
  leaving.abort()
  await assert.rejects(running, { name: 'AbortError' })
  await assert.rejects(waiting, { name: 'AbortError' })
  assert.equal(seen?.aborted, true, 'the running read was told: the connection closes and the server stops')
  finish?.()
  await new Promise((r) => setTimeout(r, 0))
  assert.equal(asked.includes('magnets/mag-wait/read?mode=summary'), false, 'the waiting read never went')

  // Someone else still wants it: leaving doesn't end it for them.
  let told: AbortSignal | undefined
  let done: (() => void) | undefined
  const shared = createMagnetRoute((_p, signal) => { told = signal; return new Promise((resolve) => { done = () => resolve({ status: 200, body: { sources: [] } }) }) })
  const gone = new AbortController()
  const one = shared.summary('mag-s', gone.signal)
  const other = shared.summary('mag-s')
  await new Promise((r) => setTimeout(r, 0))
  gone.abort()
  await assert.rejects(one, { name: 'AbortError' })
  assert.equal(told?.aborted, false)
  done?.()
  await other

  // The adapter passes it all the way down, and an abandoned read changes nothing.
  const down = answers(() => { throw new DOMException('gone', 'AbortError') })
  const { live } = storeOf(createMagnetRoute(down.get))
  const quiet = await live.load(cfg('mag-q', ['ent-2865e11386f6']), env, { signal: new AbortController().signal })
  assert.deepEqual(quiet.statuses, [], 'nothing was said of a read nobody wanted')
}

/* -- a page: bounded, its own status and its own cursor --------------------------- */
{
  const server = answers((path) => (path.includes('source=conversation%3Aent-4d627d2376e1')
    ? { status: 200, body: { sources: [{ key: 'conversation:ent-4d627d2376e1', status: 'unavailable', reason: 'the source fails', results: [] }] } }
    : { status: 200, body: pageAnswer }))
  const { reads, live } = storeOf(createMagnetRoute(server.get))
  const c = cfg('mag-p', ['ent-2865e11386f6', 'ent-4d627d2376e1'], { selection: { informationTypes: ['post', 'file'] } })
  const got = await live.load(c, env)
  assert.deepEqual(reads.filter((r) => !r.startsWith('about')), [], 'no store read')
  assert.deepEqual(got.statuses?.map((s) => s.status), ['partial', 'unavailable'], 'one failing never fails the other')
  assert.deepEqual(got.results.map((r) => [r.kind, r.id]), [['post', 'ent-9a06f3b15d72'], ['post', 'ent-7c41d09e2ab3'], ['file', 'live:ent-7c41d09e2ab3:k']])
  const post = got.results[0]
  assert.deepEqual(post.source, c.sources[0], 'a result keeps its source')
  assert.deepEqual(post.value, { post: 'ent-9a06f3b15d72', version: 'ent-e318ca7064bf', conversation: 'ent-2865e11386f6', author: 'ent-b20d8e47f196', at: 1793361601.5 })
  const file = got.results[2].value as ObjectRow & { version: string; author: string }
  assert.equal(file.version, 'ent-7c41d09e2ab3')
  assert.equal(file.author, 'ent-b20d8e47f196')
  assert.equal(file.address, 'live:ent-7c41d09e2ab3:k')
  assert.ok(server.asked.filter((p) => /mode=page/.test(p)).every((p) => /types=post%2Cfile/.test(p)))

  /* the fixture's page is partial: asked again first, since that gets further; each thing once */
  server.asked.length = 0
  const again = await live.more(c, env)
  assert.equal(server.asked.length, 1, 'only the source with a page to read')
  assert.match(server.asked[0], /source=conversation%3Aent-2865e11386f6/)
  assert.doesNotMatch(server.asked[0], /cursor=/, 'a partial page is asked again, not passed')
  assert.equal(again.results.length, 3, 'with nothing shown twice')
}

/* -- a partial page: asked again until it answers whole, then on to the next ---------- */
{
  const row = (id: string) => ({ kind: 'file', id, value: { address: id, kind: 'file', title: id, post: 'p', number: 1 } })
  const script: Array<[string, { status: string; reason?: string; results: object[]; next?: string | null }]> = [
    ['', { status: 'ok', results: [], next: 'c1' }],
    ['c1', { status: 'partial', reason: '16 left', results: [], next: 'c2' }],
    ['c1', { status: 'partial', reason: '12 left', results: [row('live:a')], next: 'c2' }],
    ['c1', { status: 'ok', results: [row('live:a'), row('live:b')], next: 'c2' }],
    ['c2', { status: 'partial', reason: 'it fails', results: [], next: 'c3' }],
    ['c2', { status: 'partial', reason: 'it fails', results: [], next: 'c3' }],
    ['c3', { status: 'ok', results: [], next: null }],
  ]
  const cursors: string[] = []
  const server = answers((path) => {
    if (/mode=summary/.test(path)) return { status: 200, body: { sources: [] } }
    const cursor = new URLSearchParams(path.split('?')[1]).get('cursor') ?? ''
    cursors.push(cursor)
    const step = script[cursors.length - 1]
    assert.equal(cursor, step[0], `ask ${cursors.length} is for the page it should be`)
    return { status: 200, body: { sources: [{ key: 'conversation:ent-2865e11386f6', ...step[1] }] } }
  })
  const { live } = storeOf(createMagnetRoute(server.get))
  const c = cfg('mag-partial', ['ent-2865e11386f6'], { selection: { informationTypes: ['file'] } })
  await live.load(c, env)
  const a = await live.more(c, env)
  assert.equal(a.more, true)
  assert.equal(a.statuses?.[0].status, 'partial')
  assert.equal((await live.load(c, env)).results.length, 0, 'a load past the first page keeps its place')
  assert.equal(cursors.length, 2, 'and reads nothing again')
  const b = await live.more(c, env)
  assert.deepEqual(b.results.map((r) => r.id), ['live:a'], 'asked again, it got further')
  const d = await live.more(c, env)
  assert.deepEqual(d.results.map((r) => r.id), ['live:a', 'live:b'], 'whole now, and each thing once')
  assert.equal(d.statuses?.[0].status, 'ok')
  await live.more(c, env)
  const stuck = await live.more(c, env)
  assert.equal(stuck.more, true, 'a page that got no further is passed: older pages are still there to read')
  const end = await live.more(c, env)
  assert.equal(end.more, undefined, 'read to its end')
  assert.equal(end.statuses?.[0].status, 'partial', 'and it still says what it passed, though the last page was whole')
  assert.equal(end.statuses?.[0].reason, 'it fails')
}

/* -- reading on: for one type, in bounds, until there is some or nothing is left ------- */
{
  const rowOf = (id: string) => ({ kind: 'file', id, value: { address: id, kind: 'file', title: id, post: 'p', number: 1 } })
  const pages: Record<string, { results: object[]; next: string | null }> = {}
  for (let i = 0; i < 12; i++) pages[i ? `c${i}` : ''] = { results: i === 7 ? [rowOf('live:p:old')] : [], next: i < 11 ? `c${i + 1}` : null }
  const server = answers((path) => {
    if (/mode=summary/.test(path)) return { status: 200, body: { sources: [{ key: 'conversation:ent-2865e11386f6', status: 'ok', summary: { title: 'Long', posts: 240 } }] } }
    const page = pages[new URLSearchParams(path.split('?')[1]).get('cursor') ?? '']
    return { status: 200, body: { sources: [{ key: 'conversation:ent-2865e11386f6', status: 'ok', ...page }] } }
  })
  const { live } = storeOf(createMagnetRoute(server.get))
  const c = cfg('mag-long', ['ent-2865e11386f6'], { selection: { informationTypes: ['file'] } })
  const first = await live.load(c, env)
  assert.equal(first.results.length, 0, 'the newest page has none')
  assert.equal(first.more, true, 'and says its source has more')
  const pagesAsked = () => server.asked.filter((p) => /mode=page/.test(p)).length
  server.asked.length = 0
  const one = await live.readOn(c, env, 'file')
  assert.equal(pagesAsked(), READ_ON_PAGES, 'one go is bounded')
  assert.equal(one.results.length, 0, 'none found yet')
  assert.equal(one.more, true, 'still saying there is more')
  server.asked.length = 0
  const two = await live.readOn(c, env, 'file')
  assert.deepEqual(two.results.map((r) => r.id), ['live:p:old'], 'the next go finds it')
  assert.equal(pagesAsked(), 2, 'and stops when it has')
  const stop = new AbortController()
  stop.abort()
  server.asked.length = 0
  await live.readOn(c, env, 'file', stop.signal)
  assert.equal(pagesAsked(), 0, 'an abandoned read reads nothing')
  const three = await live.readOn(c, env, 'file')
  assert.equal(three.more, undefined, 'at the end of its source it says no more')
  server.asked.length = 0
  await live.readOn(c, env, 'file')
  assert.equal(pagesAsked(), 0, 'with no page left it reads nothing')
}
{
  /* a post heard while an older page is read: what is newest stands, not the older read */
  let release = () => {}
  let hold = false
  const server = answers(async (path) => {
    if (/mode=summary/.test(path)) return { status: 200, body: { sources: [] } }
    const cursor = new URLSearchParams(path.split('?')[1]).get('cursor')
    if (cursor && hold) await new Promise<void>((r) => { release = r })
    return { status: 200, body: { sources: [{ key: 'conversation:ent-2865e11386f6', status: 'ok', next: 'older',
      results: [{ kind: 'post', id: cursor ? 'ent-old' : hold ? 'ent-new' : 'ent-first' }] }] } }
  })
  const { live } = storeOf(createMagnetRoute(server.get))
  const c = cfg('mag-race', ['ent-2865e11386f6'])
  await live.load(c, env)
  hold = true
  const reading = live.more(c, env)
  await new Promise((r) => setTimeout(r, 5))
  live.stale('conversation:ent-2865e11386f6')
  const loading = live.load(c, env)
  await new Promise((r) => setTimeout(r, 5))
  release()
  await reading
  const after = await loading
  assert.deepEqual(after.results.map((r) => r.id), ['ent-new'], 'the older read is let go')
}
{
  /* a busy server ends the go: it is no reason to keep asking */
  let asked = 0
  const server = answers((path) => {
    if (/mode=summary/.test(path)) return { status: 200, body: { sources: [] } }
    asked++
    return asked === 1 ? { status: 200, body: { sources: [{ key: 'conversation:ent-2865e11386f6', status: 'ok', results: [], next: 'c1' }] } } : { status: 503, body: { error: 'busy' } }
  })
  const { live } = storeOf(createMagnetRoute(server.get))
  const c = cfg('mag-busy-on', ['ent-2865e11386f6'])
  await live.load(c, env)
  const got = await live.readOn(c, env, 'file')
  assert.equal(asked, 2, 'one busy answer, and it stops')
  assert.equal(got.statuses?.[0].status, 'busy', 'saying so')
  assert.equal(got.more, true, 'with its place kept')
}

/* -- busy, for the whole request: every source says so, and nothing is held --------- */
{
  const server = answers(() => ({ status: 503, body: { error: 'the background readers are all in use', kind: 'Busy' } }))
  const { reads, live } = storeOf(createMagnetRoute(server.get))
  const c = cfg('mag-busy', ['ent-2865e11386f6'])
  const got = await live.load(c, env)
  assert.deepEqual(reads, [], 'Busy is not a reason to fall back: the store is the same Brain')
  assert.equal(got.routed, true, 'so a disc that was told Busy loads no conversation either')
  assert.equal(got.statuses?.[0].status, 'busy')
  assert.match(got.statuses?.[0].reason ?? '', /in use/)
  server.asked.length = 0
  await live.load(c, env)
  assert.ok(server.asked.length > 0, 'asked again next time: nothing was held')
}

/* -- a later schema: unavailable, never read as this one, never the store's --------- */
{
  const server = answers(() => ({ status: 200, body: { magnet: 'mag-l', unavailable: 'the definition mag-l has schema_version 9', sources: [] } }))
  const { reads, live } = storeOf(createMagnetRoute(server.get))
  const got = await live.load(cfg('mag-l', ['ent-2865e11386f6']), env)
  assert.deepEqual(reads, [])
  assert.equal(got.statuses?.[0].status, 'unavailable')
  assert.match(got.statuses?.[0].reason ?? '', /schema_version 9/)
}

/* -- 404: the store path, as it always was, and not asked again ---------------------- */
{
  const server = answers(() => ({ status: 404, body: { error: 'no such Fluid surface' } }))
  const { reads, live } = storeOf(createMagnetRoute(server.get))
  const c = cfg('mag-py', ['ent-2865e11386f6'])
  const got = await live.load(c, env, { summaryOnly: true })
  assert.deepEqual(got.results.map((r) => r.id), ['store-post'], 'a disc on such a server reads what it always read')
  assert.ok(reads.includes('posts(ent-2865e11386f6)') && reads.includes('objects(ent-2865e11386f6)') && reads.includes('about(ent-2865e11386f6)'))
  assert.equal(got.summaries[0].summary.title, 'From the store')
  const before = server.asked.length
  live.stale('conversation:ent-2865e11386f6')
  await live.load(c, env)
  assert.equal(server.asked.length, before, 'it knows there is no route for this Magnet')
}

/* -- a read that throws is that source's, not the Magnet's --------------------------- */
{
  const server = answers((path) => (path.includes('ent-0f1e2d3c4b5a') ? { status: 500, body: { error: 'it broke' } } : { status: 200, body: { sources: [{ key: 'conversation:ent-2865e11386f6', status: 'ok', results: [] }] } }))
  const { live } = storeOf(createMagnetRoute(server.get))
  const got = await live.load(cfg('mag-x', ['ent-2865e11386f6', 'ent-0f1e2d3c4b5a'], { selection: { informationTypes: ['post'] } }), env, {})
  assert.equal(got.statuses?.find((s) => sourceKey(s.source) === 'conversation:ent-2865e11386f6')?.status, 'ok')
  assert.equal(got.statuses?.find((s) => sourceKey(s.source) === 'conversation:ent-0f1e2d3c4b5a')?.reason, 'it broke')
}

/* -- a definition the server could not read is said as it is, not as missing ---------- */
{
  noteMagnetsUnreadable({ 'mag-later': 'the definition has schema_version 9' })
  const arr = { magnets: {} } as unknown as Arr
  const said = storedMagnet(arr, 'mag-later')
  assert.ok(!said.ok && said.reason.message === 'the definition has schema_version 9' && !said.reason.retryable)
  const gone = storedMagnet(arr, 'mag-gone')
  assert.ok(!gone.ok && gone.reason === MAGNET_CONFIG_MISSING)
}

/* -- the shared fixtures: object types and source keys ------------------------------- */
{
  for (const row of fixture('object_types.json') as Array<{ row: ObjectRow; want: string[]; type: string | null }>)
    assert.equal(objectTypeOf(row.row, new Set(row.want)), row.type, JSON.stringify(row))
  for (const { source, key } of fixture('source_keys.json') as Array<{ source: MagnetSource; key: string }>) {
    assert.equal(sourceKey(source), key)
    assert.ok((MAGNET_SOURCE_KINDS as readonly string[]).includes(source.kind))
  }
  for (const { sources } of fixture('definitions.json').repeated_sources as MagnetConfig[])
    assert.ok(draftProblems({ ...cfg('mag-d', []), sources }).includes('A Magnet reads each source once.'), JSON.stringify(sources))
  for (const { sources } of fixture('definitions.json').readable as MagnetConfig[])
    assert.equal(draftProblems({ ...cfg('mag-d', []), sources }).includes('A Magnet reads each source once.'), false)
}

/* -- M1's facets: said, never run, and a reconfigure names none of a Magnet's own ----- */
{
  const adapters = createAdapters()
  const c = cfg('mag-f', ['ent-2865e11386f6'], {
    activation: { mode: 'scheduled', schedule: 'PT1H' }, processing: { operations: [{ op: 'extract' }] },
    ai: { mode: 'local', model: 'm' }, outputs: ['findings'], destinations: [{ kind: 'brain' }],
    presentation: { renderer: 'disc', theme: 'glass' },
  })
  const said = notRunning(c, env, adapters).map((x) => x.facet)
  for (const f of ['activation', 'processing', 'ai', 'outputs', 'destinations']) assert.ok(said.includes(f), f)
  assert.equal(said.includes('presentation'), false, 'a theme this build knows is drawn, so it is not said to be kept undrawn')
  const words = (facet: string) => notRunning(c, env, adapters).find((x) => x.facet === facet)?.reason.message
  assert.equal(words('processing'), 'Its processing steps are kept in order. Only a manual activation of a lone extract step runs, and only where nothing else this Magnet asks rules it out: it materializes one bounded M1 page in this Magnet’s own Conversation. Schedules, events, continuous collection and other operations do not run.', 'manual activation of extract is what runs, and nothing else')
  assert.equal(words('outputs'), 'Its outputs are kept. A manual activation of extract records its page; nothing else produces an output in this build.', 'what that activation produces')
  assert.equal(words('destinations'), 'Its destinations are kept. A manual activation of extract writes to this Magnet’s own Conversation; nothing is delivered anywhere else in this build.', 'where that activation writes')
  const plain = cfg('mag-g', ['ent-2865e11386f6'], { ai: { mode: 'none' }, activation: { mode: 'manual' } })
  assert.equal(notRunning(plain, env, adapters).some((x) => x.facet === 'ai' || x.facet === 'activation'), false, 'the defaults ask nothing')
  const { id: _id, ...seed } = { ...c, conversation: 'ent-3d95a7c1e864' }
  assert.deepEqual(changeOf({ ...c, conversation: 'ent-3d95a7c1e864' }, { ...seed, conversation: 'ent-6ab2f40d9c17' }), {}, 'a Magnet\'s own Conversation is never in a change')
  assert.deepEqual(changeOf(c, { ...seed, ai: { mode: 'agent' } }), { ai: { mode: 'agent' } })
}

/* -- what a manual activation runs is not said to be not running; what it refuses still is.
 *    The rows are the ones Python's refusals are held to. ------------------------------- */
{
  const adapters = createAdapters()
  adapters.register(conversationAdapter({ posts: async () => ({ ids: [] }), objects: async () => [], search: async () => [], about: async () => ({ title: 'T', posts: 0 }) }))
  const said = (c: MagnetConfig) => notRunning(c, env, adapters).map((x) => x.facet)
  const limited = (c: MagnetConfig) => magnetStatus(c, { unread: 0, loading: false, held: 0, off: said(c).length }).limited
  const asks: Array<'processing' | 'outputs' | 'destinations'> = ['processing', 'outputs', 'destinations']
  const rows = fixture('activation/definitions.json').executable as Array<{ id: string; definition: MagnetConfig; answer: string }>
  assert.ok(rows.some((r) => r.answer === 'ready') && rows.some((r) => r.answer !== 'ready'))
  for (const { id, definition, answer } of rows) {
    const asked = asks.filter((f) => (f === 'processing' ? definition.processing?.operations : definition[f])?.length)
    if (answer === 'ready') assert.deepEqual(said(definition).filter((f) => asks.includes(f as typeof asks[number])), [], `${id}: it runs, so nothing it runs is said`)
    else for (const f of asked) assert.ok(said(definition).includes(f), `${id}: ${answer}, so ${f} is still said`)
  }

  const runnable = cfg('mag-r', ['ent-2865e11386f6'], {
    activation: { mode: 'manual' }, processing: { operations: [{ op: 'extract', name: 'Read the thread', options: { mode: 'm1-page' } }] },
    ai: { mode: 'none' }, outputs: ['records'], destinations: [{ kind: 'magnet-conversation' }],
  })
  assert.deepEqual(said(runnable), [], 'every facet of a fully runnable Magnet runs')
  assert.equal(limited(runnable), false, 'so it is not limited')

  const finding = { ...runnable, outputs: ['findings'] } as MagnetConfig
  assert.deepEqual(said(finding), ['processing', 'outputs', 'destinations'], 'one output it refuses, and nothing of it runs')
  assert.equal(limited(finding), true, 'so it is limited')
  const unsaid = { ...runnable, outputs: [] } as MagnetConfig
  assert.deepEqual(said(unsaid), ['processing', 'destinations'], 'an empty output list is refused, not absent')
  assert.equal(limited(unsaid), true)
  const { activation: _activation, ...noActivation } = runnable
  assert.equal(said(noActivation).includes('processing'), true, 'absent activation is not manual')

  /* it runs beside these, and they are what it does not apply: each still said */
  const beside = { ...runnable, sources: [...runnable.sources, { kind: 'web', url: 'https://example.com/' }] } as MagnetConfig
  assert.deepEqual(said(beside), ['source'], 'a source it cannot read is still said')
  assert.equal(limited(beside), true)
  assert.deepEqual(said({ ...runnable, selection: { phrases: ['tide'] } }), ['selection'], 'a selection it does not apply is still said')
}

console.log('fluid_magnet_route_unit: ok')
