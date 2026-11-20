/* A PAGE BOUND TO ONE BRAIN NEVER DECIDES ON ANOTHER, checked without a browser:
 * the first Brain named binds the page; another one named since -- or a write the server
 * refused as another Brain's -- moves it, for good; every write to Mentis names the bound
 * Brain, reads and other addresses are untouched; and a page that never bound sends no Brain,
 * as before. (Nothing here is kept beyond the page.) */
import assert from 'node:assert/strict'
import { createOutbox, type Sent, type StorageLike } from '../src/experimental/decisionOutbox'
import { BRAIN_HEADER, brainKeyOf, confirmBrain, createBinding, guardWrites, guarding, page, refusedAsOtherBrain } from '../src/brainBinding'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }

/* -- what names a Brain ---------------------------------------------------------- */
eq(brainKeyOf({ corpus_id: 'c-1', instance: 'a1' }), 'c-1@a1', 'a Brain is its id and its instance')
eq(brainKeyOf({ corpus_id: 'c-1', instance: null }), null, 'an answer without an instance names no Brain')
eq(brainKeyOf({ corpus_id: '  ', instance: 'a1' }), null, 'nor one without an id')
eq(brainKeyOf(null), null, 'nor nothing')

/* -- binding ------------------------------------------------------------------- */
{
  const b = createBinding()
  let told = 0
  b.subscribe(() => { told++ })
  eq(b.bound(), null, 'nothing is bound before any answer')
  eq(b.saw(null), true, 'an answer naming no Brain decides nothing')
  eq(b.bound(), null, '... and binds nothing')
  eq(b.saw('c-1@a1'), true, 'the first Brain named binds the page')
  eq(b.bound(), 'c-1@a1', '')
  eq(b.saw('c-1@a1'), true, 'the same Brain again is the same Brain')
  eq(b.moved(), false, '')
  eq(b.saw('c-1@b2'), false, 'a copy of it (same id, another instance) is another Brain')
  eq(b.moved(), true, 'and the page has moved')
  eq(b.saw('c-1@a1'), false, 'the original answering again does not unmove it: only a reload does')
  eq(b.bound(), 'c-1@a1', 'what the page names on its writes stays the Brain it was opened on')
  ok(told >= 2, 'whoever draws is told of the binding and of the move')
}
{
  const b = createBinding()
  b.saw('c-1@a1')
  b.move()
  eq(b.moved(), true, 'the server refusing a write as another Brain\'s moves the page')
}

/* -- what the server says ---------------------------------------------------------- */
ok(refusedAsOtherBrain(409, { kind: 'BrainChanged', error: 'x' }), 'a 409 BrainChanged is a refusal as another Brain\'s')
ok(!refusedAsOtherBrain(409, { kind: 'Conflict' }), 'another 409 is not')
ok(!refusedAsOtherBrain(200, { kind: 'BrainChanged' }), 'nor a success')
ok(!refusedAsOtherBrain(409, null), 'nor a 409 without a body')

/* -- every write names the Brain ------------------------------------------------- */
type Call = { url: string; method: string; brain: string | null }
const calls: Call[] = []
let answer: () => Response = () => new Response('{}', { status: 200 })
const g = globalThis as unknown as { window: { fetch: typeof fetch }; location: { origin: string }; fetch: typeof fetch }
g.location = { origin: 'http://127.0.0.1:8780' }
g.window = {
  fetch: (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
    calls.push({ url, method: (init?.method ?? 'GET').toUpperCase(), brain: new Headers(init?.headers).get(BRAIN_HEADER) })
    return answer()
  }) as typeof fetch,
}
g.fetch = (...a: Parameters<typeof fetch>) => g.window.fetch(...a)

const run = async () => {
  eq(guarding(), false, 'a page that never guards (Fluid) is not a guarding page')
  guardWrites()
  eq(guarding(), true, 'Quiet Chat guards')
  const w = g.window.fetch
  /* A WRITE BEFORE THE PAGE IS BOUND waits for the binding; where the server cannot say which
     Brain it serves, the write is not sent at all */
  answer = () => new Response('{}', { status: 200 })                 // says no Brain
  const before = calls.length
  const refused = await w('/api/conversations/c/turns', { method: 'POST', body: '{}' })
  eq(refused.status, 409, 'refused here')
  eq((await refused.json()).kind, 'BrainUnconfirmed', 'as not confirmed')
  eq(calls.slice(before).filter((c) => c.method === 'POST').length, 0, 'and never sent')
  eq(calls.slice(before).filter((c) => c.url.endsWith('/needs-you/brain')).length, 2, 'after asking which Brain, twice')
  /* the binding arrives while the write waits: the write names it */
  let asked = 0
  answer = () => (++asked === 1
    ? new Response(JSON.stringify({ brain: { corpus_id: 'c-1', instance: 'a1' } }), { status: 200 })
    : new Response('{}', { status: 201 }))
  await w('/api/conversations/c/turns', { method: 'POST', body: '{}' })
  eq(calls.at(-1)!.method, 'POST', 'sent once bound')
  eq(calls.at(-1)!.brain, 'c-1@a1', 'naming the Brain it waited for')

  /* binding by asking the server which Brain it serves */
  answer = () => new Response(JSON.stringify({ brain: { corpus_id: 'c-1', instance: 'a1' } }), { status: 200 })
  eq(await confirmBrain(w), true, 'the server serves the Brain the page binds to')
  eq(page.bound(), 'c-1@a1', '')
  answer = () => new Response('{}', { status: 201 })
  await w('/api/conversations/c/turns', { method: 'POST', body: '{}' })
  eq(calls.at(-1)!.brain, 'c-1@a1', 'a write names the Brain the page is bound to')
  await w('http://127.0.0.1:8780/fluid/api/conversations', { method: 'POST', body: '{}' })
  eq(calls.at(-1)!.brain, 'c-1@a1', 'so does one to Fluid\'s command door, by its full address')
  await w('/api/conversations/c', { method: 'GET' })
  eq(calls.at(-1)!.brain, null, 'a read is untouched')
  await w('/owner/login', { method: 'POST', body: '{}' })
  eq(calls.at(-1)!.brain, null, 'an address that is not Mentis\'s API is untouched')

  /* the server refuses a write as another Brain's: the page moves */
  answer = () => new Response(JSON.stringify({ kind: 'BrainChanged', error: 'Nothing was recorded' }), { status: 409 })
  const res = await w('/api/conversations/c/turns', { method: 'POST', body: '{}' })
  eq(res.status, 409, 'the caller still sees the refusal')
  eq(await res.json(), { kind: 'BrainChanged', error: 'Nothing was recorded' }, 'with its body intact')
  eq(page.moved(), true, 'and the page has moved')

  /* the server says it serves another Brain when asked */
  answer = () => new Response(JSON.stringify({ brain: { corpus_id: 'c-1', instance: 'b2' } }), { status: 200 })
  eq(await confirmBrain(w), false, 'asked again, another Brain answers: not confirmed')
  answer = () => new Response('oops', { status: 500 })
  eq(await confirmBrain(w), null, 'a server that cannot say decides nothing')
  answer = () => { throw new Error('offline') }
  eq(await confirmBrain(w), null, 'nor one that cannot be reached')

  answer = () => new Response('{}', { status: 201 })
  guardWrites()
  await w('/api/x', { method: 'POST' })
  eq(calls.filter((c) => c.url === '/api/x').length, 1, 'guarding twice wraps once')

  /* -- what was sent is kept per Brain ---------------------------------------------- */
  const mem = new Map<string, string>()
  const store: StorageLike = {
    getItem: (k) => mem.get(k) ?? null, setItem: (k, v) => { mem.set(k, v) }, removeItem: (k) => { mem.delete(k) },
    get length() { return mem.size }, key: (i) => [...mem.keys()][i] ?? null,
  }
  const sent = (ask: string, op: string): Sent => ({ ask, op, conversation: 'c', author: 'me', body: { op }, pick: null, text: 'words',
    label: null, continued: false, phase: 'unknown', at: 0, turn: null, number: null, dispatched: null, did: null, why: null, kept: true })
  const fluid = createOutbox(store), onA = createOutbox(store, 'c-1@a1'), onB = createOutbox(store, 'c-1@b2')
  fluid.put(sent('opr-q', 'k-fluid'))
  onA.put(sent('opr-q', 'k-a'))
  onB.put(sent('opr-q', 'k-b'))
  eq(fluid.get('opr-q')?.op, 'k-fluid', 'a page bound to no Brain keeps its own, as before')
  eq(onA.get('opr-q')?.op, 'k-a', 'the answer Brain A keeps for a question is A’s')
  eq(onB.get('opr-q')?.op, 'k-b', 'and the one B keeps for the same question id is B’s: neither overwrote the other')
  eq(onA.get('opr-q')?.brain, 'c-1@a1', 'each is kept with the Brain it was made on')
  eq(onA.all().map((x) => x.op), ['k-a'], 'A sees only its own')
  eq(onB.all().map((x) => x.op), ['k-b'], 'B sees only its own: never A’s, never the unscoped')
  eq(fluid.all().map((x) => x.op), ['k-fluid'], 'and the unscoped box sees no Brain’s')
  onB.drop('opr-q')
  eq(onA.get('opr-q')?.op, 'k-a', 'B dropping its own leaves A’s')
  eq(fluid.get('opr-q')?.op, 'k-fluid', 'and the unscoped one')

  console.log(`brain_binding_unit: ${checks} checks passed`)
}
await run()
