/* The Fluid client store against a mocked /fluid/api (tests/test_fluid_store.py).
 *
 * The review's three store probes, asserting what must hold:
 *   * a change whose reads fail leaves the cursor where it was, and the next
 *     step reads it again; reading it twice is reading it once;
 *   * a refresh keeps every page a reader loaded, takes new members in and
 *     ended ones out wherever they are -- for a conversation and a thread;
 *   * `objects:<root>` reads a post's objects again at the same version,
 *     for a followed post and for a kept-only object. */
import { registerHooks } from 'node:module'
import { readFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import assert from 'node:assert/strict'
import ts from '../node_modules/typescript/lib/typescript.js'

registerHooks({
  resolve(specifier, context, next) {
    if (specifier.startsWith('.')) {
      for (const suffix of ['.ts', '.tsx', '/index.ts']) {
        const url = new URL(specifier + suffix, context.parentURL)
        if (existsSync(fileURLToPath(url))) return { url: url.href, shortCircuit: true }
      }
    }
    return next(specifier, context)
  },
  load(url, context, next) {
    if (url.endsWith('.css')) return { format: 'module', source: '', shortCircuit: true }
    if (/\.tsx?$/.test(url)) return { format: 'module', shortCircuit: true, source: ts.transpileModule(readFileSync(fileURLToPath(url), 'utf8'), { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX } }).outputText }
    return next(url, context)
  },
})

const kept = []
globalThis.localStorage = { getItem: () => JSON.stringify(kept), setItem: () => {} }
const { store } = await import('../src/fluid/store.ts')

/* -- a mocked server ------------------------------------------------------- */

let calls = []
let answer = () => { throw new Error('no answer') }
globalThis.fetch = async (path) => {
  calls.push(path)
  const url = new URL(path, 'http://x')
  const body = await answer(url.pathname.replace('/fluid/api/', ''), url.searchParams)
  return { ok: true, status: 200, json: async () => body }
}
const post = (id, version) => ({ id, version, parts: [], memberships: [] })
const posts = (q) => ({ posts: q.get('ids').split(',').map((id) => post(id, 'v')) })

/** A collection as the server pages it: members by position, the id of an
 *  edge member as its cursor, `from` inclusive. Ended members keep their
 *  position, so a cursor at one still pages. */
function pager(key, order, members) {
  const pos = { get: (id) => order.indexOf(id) }
  return (q) => {
    const limit = Number(q.get('limit'))
    const live = order.filter((id) => members.has(id))
    let chosen
    if (q.get('from')) {
      const at = q.get('from') === 'start' ? -1 : pos.get(q.get('from'))
      chosen = live.filter((id) => pos.get(id) >= at).slice(0, limit)
    } else if (q.get('after')) chosen = live.filter((id) => pos.get(id) > pos.get(q.get('after'))).slice(0, limit)
    else if (q.get('before')) chosen = live.filter((id) => pos.get(id) < pos.get(q.get('before'))).slice(-limit)
    else chosen = live.slice(-limit)
    // an empty page after a position counts every member as older, as the server does
    const first = chosen.length ? live.indexOf(chosen[0]) : (q.get('after') ? live.length : 0)
    const older = first, newer = Math.max(0, live.length - first - chosen.length)
    return { key, items: chosen.map((id) => ({ id })), total: live.length, older, newer,
      before: older ? chosen[0] : null, after: newer ? chosen.at(-1) : null, cursor: 'f1.0.0.0' }
  }
}

/* -- 1. the cursor moves only when the change's reads succeeded ------------- */

{
  const P = 'ent-p'
  store.posts.set(P, post(P, 'old'))
  store.cursor = 'before-change'
  let failing = true
  answer = (path, q) => {
    if (path === 'changes') {
      assert.equal(q.get('since'), 'before-change')
      return { cursor: 'after-change', posts: [{ id: P, version: 'edited', conversations: [] }], collections: [] }
    }
    if (path === 'posts') {
      if (failing) throw new Error('temporary network failure')
      return { posts: [post(P, 'edited')] }
    }
    throw new Error('unexpected ' + path)
  }
  await assert.rejects(store.step(), /temporary network failure/)
  assert.equal(store.cursor, 'before-change', 'a failed read keeps the cursor')
  assert.equal(store.posts.get(P).version, 'old')
  failing = false
  let heard = 0
  const off = store.subscribe('post:' + P, () => heard++)
  await store.step()
  assert.equal(store.cursor, 'after-change', 'the change is read again, then the cursor moves')
  assert.equal(store.posts.get(P).version, 'edited')
  // the same change applied again is the same state, and nobody re-renders
  store.cursor = 'before-change'
  await store.step()
  assert.equal(store.cursor, 'after-change')
  assert.equal(store.posts.get(P).version, 'edited')
  assert.equal(heard, 1, 'reapplying a change notifies nobody again')
  off()
  store.posts.clear()
  console.log(JSON.stringify({ check: 'cursor after reads', ok: true }))
}

/* -- 1b. an operational act on a held post re-reads its projection --------- */

{
  const P = 'ent-decision-post'
  const FORM = 'opr-decision-form'
  store.posts.set(P, { ...post(P, P), decision_forms: [] })
  store.cursor = 'before-decision-form'
  let rereads = 0
  answer = (path, q) => {
    if (path === 'changes') {
      assert.equal(q.get('since'), 'before-decision-form')
      return { cursor: 'after-decision-form', posts: [{ id: P, version: P, conversations: ['ent-conversation'] }], collections: [] }
    }
    if (path === 'posts') {
      rereads++
      assert.equal(q.get('ids'), P)
      return { posts: [{ ...post(P, P), decision_forms: [FORM] }] }
    }
    throw new Error('unexpected ' + path)
  }
  await store.step()
  assert.equal(rereads, 1, 'a named held post is read again even at the same version')
  assert.deepEqual(store.posts.get(P).decision_forms, [FORM])
  assert.equal(store.cursor, 'after-decision-form')
  store.posts.clear()
  console.log(JSON.stringify({ check: 'decision form on held post appears in place', ok: true }))
}

/* A first change cursor is only safe after the projections already held at
 * that snapshot were read again. */
{
  const P = 'ent-held-before-start'
  const FORM = 'opr-form-before-start'
  store.posts.set(P, { ...post(P, P), decision_forms: [] })
  store.cursor = null
  let fail = true
  answer = (path) => {
    if (path === 'changes') return { cursor: 'start-with-form', start: true }
    if (path === 'posts') {
      if (fail) throw new Error('temporary initial reread failure')
      return { posts: [{ ...post(P, P), decision_forms: [FORM] }] }
    }
    throw new Error('unexpected ' + path)
  }
  await assert.rejects(store.step(), /temporary initial reread failure/)
  assert.equal(store.cursor, null, 'the start cursor waits for its dependent rereads')
  fail = false
  await store.step()
  assert.deepEqual(store.posts.get(P).decision_forms, [FORM])
  assert.equal(store.cursor, 'start-with-form')
  store.posts.clear()
  console.log(JSON.stringify({ check: 'start cursor rereads held posts before advancing', ok: true }))
}

/* -- 2. a refresh keeps the loaded history ---------------------------------- */

for (const shape of ['conversation', 'thread']) {
  calls = []
  const order = Array.from({ length: 250 }, (_, i) => `m${i}`)
  // an old post included later sits in stream order, deep in the history
  order.splice(51, 0, 'x-included')
  const members = new Set(order.filter((id) => id !== 'x-included'))
  const key = `${shape}:H`
  const page = pager(key, order, members)
  answer = (path, q) => (path === 'posts' ? posts(q) : page(q))
  const load = (wide) => (shape === 'conversation' ? store.loadConversation('H', wide) : store.loadThread('H', wide))
  const older = () => (shape === 'conversation' ? store.olderOfConversation('H') : store.olderOfThread('H'))
  await load(false)
  while (store.collections.get(key).items.length < 240) await older()
  const held = store.collections.get(key)
  assert.equal(held.items.length, 240)
  assert.equal(held.items[0].id, 'm10')
  // the record moves: a new post, an inclusion deep in history, an ended membership
  members.add('m250')
  order.push('m250')
  members.add('x-included')
  members.delete('m100')
  calls = []
  await load(true)
  const want = order.filter((id) => members.has(id)).slice(order.filter((id) => members.has(id)).indexOf('m10'))
  const got = store.collections.get(key)
  assert.deepEqual(got.items.map((i) => i.id), want, `${shape}: what is held, read again`)
  assert.equal(got.items.length, 241)
  assert.ok(got.items.some((i) => i.id === 'x-included'))
  assert.ok(!got.items.some((i) => i.id === 'm100'))
  assert.equal(got.older, 10)
  assert.equal(got.before, 'm10')
  assert.equal(got.newer, 0)
  const asked = calls.filter((c) => c.includes('collections/'))
  assert.ok(asked[0].includes('from=m10') && asked[0].includes('limit=200'), asked[0])
  assert.ok(asked.slice(1).every((c) => c.includes('after=')), asked.join(' '))
  // and older paging carries on from where the reader was
  await older()
  assert.equal(store.collections.get(key).items[0].id, 'm0')
  assert.equal(store.collections.get(key).older, 0)
  // a collection held from its start is read again from its start
  members.add('m251'); order.push('m251')
  calls = []
  await load(true)
  assert.ok(calls.find((c) => c.includes('collections/')).includes('from=start'))
  assert.equal(store.collections.get(key).items.length, 252)
  console.log(JSON.stringify({ check: `${shape} refresh keeps history`, held: 240, after: 241, requests: asked.length }))
}

/* -- 3. objects:<root> reads a post's objects again at the same version ----- */

{
  const root = 'ent-review'
  const loose = 'ent-kept'
  const listed = (n) => ({ version: root, extracted: true, objects: Array.from({ length: n }, (_, i) => ({ key: `k${i}`, part: 0, address: { exact: `exact:${root}:0:k${i}`, live: `live:${root}:k${i}` } })) })
  store.postObjects.set(root, { post: root, version: root, addresses: [`live:${root}:k0`], extracted: true })
  store.kept = [`live:${loose}:t`]
  store.objects.set(`live:${loose}:t`, { address: `live:${loose}:t`, object: { key: 't', version: loose, post: loose } })
  store.cursor = 'f1.1.0.0'
  let named = []
  answer = (path, q) => {
    if (path === 'changes') return { cursor: 'f1.1.1.0', posts: [{ id: root, version: root, conversations: [] }, { id: loose, version: loose, conversations: [] }], collections: named }
    if (path === 'objects') return listed(2)
    if (path.startsWith('objects/')) return { post: loose, version: loose, object: { key: 't', title: 'returned later' } }
    throw new Error('unexpected ' + path)
  }
  // the same version and no objects key: nothing is read again
  calls = []
  await store.step()
  assert.equal(calls.filter((c) => c.includes('objects')).length, 0)
  // a late return names objects:<root>: both are read again
  named = [`objects:${root}`, `objects:${loose}`]
  store.cursor = 'f1.1.0.0'
  calls = []
  await store.step()
  assert.ok(calls.some((c) => c.includes('objects?post=' + root)), calls.join(' '))
  assert.ok(calls.some((c) => c.includes('objects/' + encodeURIComponent(`live:${loose}:t`))), calls.join(' '))
  assert.deepEqual(store.postObjects.get(root).addresses, [`live:${root}:k0`, `live:${root}:k1`])
  assert.equal(store.objects.get(`live:${loose}:t`).object.title, 'returned later')
  assert.equal(store.cursor, 'f1.1.1.0')
  console.log(JSON.stringify({ check: 'objects key at the same version', ok: true }))
}

/* -- 3b. what Home keeps is read again when its post changes, as the
 *        workspace's is; neither place clears the other's (opr-1da1081bab59) */

{
  const ws = 'ent-wskept'
  const home = 'ent-homekept'
  store.kept = []
  store.postObjects.clear()
  for (const p of [ws, home]) store.objects.set(`live:${p}:t`, { address: `live:${p}:t`, object: { key: 't', version: 'v1', post: p } })
  store.setHeld([`live:${home}:t`], 'home')
  store.setHeld([`live:${ws}:t`], 'workspace')
  // the workspace says again what it holds -- Home's stays held
  store.setHeld([`live:${ws}:t`], 'workspace')
  assert.deepEqual([...store.held].sort(), [`live:${home}:t`, `live:${ws}:t`].sort())
  store.cursor = 'h0'
  answer = (path) => {
    if (path === 'changes') return { cursor: 'h1', posts: [{ id: home, version: 'v2', conversations: [] }], collections: [] }
    if (path.startsWith('objects/')) return { post: home, version: 'v2', object: { key: 't', title: 'changed on Home' } }
    throw new Error('unexpected ' + path)
  }
  calls = []
  await store.step()
  assert.ok(calls.some((c) => c.includes('objects/' + encodeURIComponent(`live:${home}:t`))), calls.join(' '))
  assert.ok(!calls.some((c) => c.includes('objects/' + encodeURIComponent(`live:${ws}:t`))), calls.join(' '))
  assert.equal(store.objects.get(`live:${home}:t`).object.title, 'changed on Home')
  store.setHeld([], 'home')
  store.setHeld([], 'workspace')
  console.log(JSON.stringify({ check: "Home's kept objects read again", ok: true }))
}

/* -- 4. a post's catch-up waits for the loop's step, and a failed step ------
 *       leaves the next one the same change (F2's serialized steps over the
 *       repair's cursor rule) */

{
  const P = 'ent-held'
  const Q = 'ent-mine'
  const tick = () => new Promise((r) => setTimeout(r, 5))
  const run = async (failFirst) => {
    store.posts.clear()
    store.postObjects.clear()
    store.kept = []
    store.posts.set(P, post(P, 'old'))
    store.cursor = 'c0'
    const since = []
    let inFlight = 0, overlap = false, fail = failFirst
    answer = async (path, q) => {
      if (path === 'changes') {
        if (inFlight++) overlap = true
        since.push(q.get('since'))
        await tick()
        inFlight--
        return q.get('since') === 'c0'
          ? { cursor: 'c1', posts: [{ id: P, version: 'edited', conversations: [] }], collections: [] }
          : { cursor: 'c1', posts: [], collections: [] }
      }
      if (path === 'posts') {
        await tick()
        if (fail && q.get('ids') === P) { fail = false; throw new Error('temporary network failure') }
        return { posts: q.get('ids').split(',').map((id) => post(id, id === P ? 'edited' : 'v')) }
      }
      throw new Error('unexpected ' + path)
    }
    // the 1.2 s loop and the composer's catch-up, started together
    const loop = store.step()
    const caught = store.posted(Q, 'ent-conv', null)
    const [l, c] = await Promise.allSettled([loop, caught])
    return { since, overlap, l, c }
  }

  let r = await run(false)
  assert.equal(r.overlap, false, 'two steps never read the change feed at once')
  assert.deepEqual(r.since, ['c0', 'c1'], 'the catch-up steps from where the loop left the cursor')
  assert.equal(r.l.status, 'fulfilled')
  assert.equal(r.c.status, 'fulfilled')
  assert.equal(store.cursor, 'c1')
  assert.equal(store.posts.get(P).version, 'edited')
  assert.ok(store.posts.has(Q), 'the post appears without a reload')

  r = await run(true)
  assert.equal(r.overlap, false)
  assert.equal(r.l.status, 'rejected', 'the loop step whose read failed rejects')
  assert.deepEqual(r.since, ['c0', 'c0'], 'the failed step left the cursor, so the next step is told the same change')
  assert.equal(r.c.status, 'fulfilled', 'a failed step does not wedge the steps after it')
  assert.equal(store.cursor, 'c1')
  assert.equal(store.posts.get(P).version, 'edited')
  assert.ok(store.posts.has(Q))
  store.posts.clear()
  console.log(JSON.stringify({ check: 'serialized steps keep the cursor rule', ok: true }))
}

/* -- 5. conversation:<id> change refreshes its name and provisional flag --- */

{
  const C = 'ent-conv-test'
  store.conversations.clear()
  store.conversations.set(C, {
    id: C,
    name: 'Unnamed 2026-10-18T12:00:00',
    provisional: true,
    created: 1000,
    posts: 1,
    included: 0,
    participants: 1,
    last_activity: 1000,
    working: 0,
  })
  store.cursor = 'c-before-rename'
  let notified = false
  const off = store.subscribe('conv:' + C, () => { notified = true })
  answer = (path, q) => {
    if (path === 'changes') {
      return {
        cursor: 'c-after-rename',
        posts: [],
        collections: [`conversation:${C}`],
      }
    }
    if (path === 'conversations') {
      assert.equal(q.get('ids'), C)
      return {
        conversations: [{
          id: C,
          name: 'Renamed Project',
          provisional: false,
          created: 1000,
          posts: 1,
          included: 0,
          participants: 1,
          last_activity: 1000,
          working: 0,
        }],
      }
    }
    throw new Error('unexpected ' + path)
  }
  await store.step()
  assert.equal(store.cursor, 'c-after-rename')
  assert.equal(store.conversations.get(C).name, 'Renamed Project')
  assert.equal(store.conversations.get(C).provisional, false)
  assert.ok(notified, 'rename notifies listeners of the conversation')
  off()
  console.log(JSON.stringify({ check: 'conversation:<id> change refreshes name and provisional', ok: true }))
}

/* -- 6. only a provisional conversation's name is read as "Unnamed · started"
 *       (opr-7fb501067641): never a post's text, an object's title, or a
 *       chosen name that reads the same ---------------------------------------- */

{
  const RAW = 'Unnamed 2026-10-20T04:06:34Z'
  const U = 'ent-unnamed', N = 'ent-chosen', P = 'ent-says-it', R = 'ent-elsewhere'
  const conv = (id, provisional) => ({ id, name: RAW, provisional, created: 1, posts: 1, included: 0, participants: 1, last_activity: 1, working: 0 })
  store.conversations.clear(); store.posts.clear(); store.list = null
  answer = (path, q) => {
    if (path === 'conversations') return { conversations: [conv(U, true), conv(N, false)] }
    if (path === 'posts') return { posts: q.get('ids').split(',').map((id) => ({
      ...post(id, 'v'), parts: [{ type: 'text', text: RAW }, { type: 'image', ref: 'adm-x', alt: RAW }],
      home: id === P ? U : N, home_name: RAW, reply_to: 'ent-parent', reply_to_home: id === P ? N : U, reply_to_home_name: RAW,
      memberships: [{ conversation: id === P ? U : N, via: 'home' }, { conversation: U, via: 'linked', name: RAW }, { conversation: N, via: 'linked', name: RAW }],
    })) }
    if (path === 'objects') return { version: 'v', extracted: true, objects: [{ key: 'k', part: 0, title: RAW, address: { exact: 'exact:v:0:k', live: `live:${P}:k` } }] }
    throw new Error('unexpected ' + path)
  }
  // a post read before the list says which conversations are provisional
  await store.loadPosts([R])
  assert.equal(store.posts.get(R).reply_to_home_name, RAW, 'not yet known provisional: as the record has it')
  await store.loadList()
  await store.loadPosts([P])
  await store.loadObjects(P, true)
  const u = store.conversations.get(U).name, n = store.conversations.get(N).name
  assert.match(u, /^Unnamed · started /, 'a provisional conversation reads as when it was started')
  assert.match(u, /\d:\d\d:\d\d/, 'with its seconds, so two started in one minute read apart')
  assert.equal(n, RAW, 'a name somebody chose is never rewritten, though it reads the same')
  const p = store.posts.get(P)
  assert.equal(p.parts[0].text, RAW, "a post's text is never rewritten")
  assert.equal(p.parts[1].alt, RAW, "an attachment's name is never rewritten")
  assert.equal(p.home_name, u, 'its home, provisional, is named as the conversation reads')
  assert.equal(p.reply_to_home_name, RAW, "its parent's home has a chosen name")
  assert.deepEqual(p.memberships.filter((m) => m.name).map((m) => m.name), [u, RAW])
  assert.equal(store.objects.get(`live:${P}:k`).object.title, RAW, "an object's title is never rewritten")
  assert.equal(store.posts.get(R).reply_to_home_name, u, 'a post held before the list arrived is shown so once it does')
  assert.equal(store.posts.get(R).parts[0].text, RAW)
  // two started in the same minute read apart
  const { readableName } = await import('../src/fluid/store.ts')
  assert.notEqual(readableName('Unnamed 2026-10-20T04:06:34Z'), readableName('Unnamed 2026-10-20T04:06:51Z'))
  store.conversations.clear(); store.posts.clear(); store.postObjects.clear(); store.objects.clear(); store.list = null
  console.log(JSON.stringify({ check: 'only provisional names are read readably', ok: true }))
}

/* -- 7. a window's refresh stays bounded when its newest member is removed
 *       (opr-4a5a62c8ae1c) ------------------------------------------------------ */

for (const removeEnd of [false, true]) {
  const order = Array.from({ length: 120 }, (_, i) => `w${i}`)
  const members = new Set(order)
  const key = 'conversation:W'
  const page = pager(key, order, members)
  answer = (path, q) => (path === 'posts' ? posts(q) : page(q))
  store.collections.delete(key)
  await store.conversationAround('W', 'w40')
  const held = store.collections.get(key)
  const end = held.items.at(-1).id
  assert.equal(held.items[0].id, 'w30'); assert.equal(end, 'w69'); assert.equal(held.newer, 50)
  // the record moves: new posts at the newest end, a member inside the window ends
  for (const id of ['w120', 'w121']) { order.push(id); members.add(id) }
  members.delete('w50')
  if (removeEnd) members.delete(end)
  calls = []
  await store.loadConversation('W', true)
  const got = store.collections.get(key)
  const want = order.filter((id) => members.has(id) && order.indexOf(id) >= 30 && order.indexOf(id) <= 69)
  assert.deepEqual(got.items.map((i) => i.id), want, `${removeEnd ? 'its end removed' : 'its end present'}: read again as far as it reached`)
  assert.equal(got.newer, 52, 'what lies beyond stays newer, to scroll to')
  assert.equal(got.after, end, 'the window ends at the same position')
  assert.equal(got.older, 30)
  assert.ok(calls.filter((c) => c.includes('collections/')).length <= 2, calls.join(' '))
  // and paging newer carries on from that position
  await store.newerOfConversation('W')
  assert.equal(store.collections.get(key).items.at(-1 - 0).id, 'w99')
  assert.ok(!store.collections.get(key).items.some((i) => i.id === 'w50'))
  console.log(JSON.stringify({ check: `window refresh bounded, end ${removeEnd ? 'removed' : 'present'}`, ok: true }))
}

/* -- 8. commands store the server's canonical projection ------------------ */

{
  const C = 'ent-canonical'
  const projection = {
    id: C, name: 'Canonical', provisional: true, created: 123.25,
    posts: 0, included: 0, participants: 1, last_activity: null,
    working: 0, needs_you: null,
  }
  store.list = null
  store.conversations.delete(C)
  answer = (path) => {
    if (path === 'conversations') return {
      conversation: C, name: 'Canonical', provisional: true,
      projection, cursor: 'f1.2.0.0',
    }
    throw new Error('unexpected ' + path)
  }
  const got = await store.createConversation('human:owner', 'op-canonical')
  assert.equal(got.conversation, C)
  assert.deepEqual(store.conversations.get(C), projection,
    'the command projection is stored verbatim; no client timestamp or count is invented')
  store.conversations.delete(C)
  console.log(JSON.stringify({ check: 'canonical command projection', ok: true }))
}

console.log('ok')
