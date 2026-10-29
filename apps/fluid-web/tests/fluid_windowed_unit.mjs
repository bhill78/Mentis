/* WINDOWED LOADING, INCREMENTAL UPDATES (the owner's requirement, 2026-10-29).
 *
 * Against a mocked /fluid/api, asserting what must hold:
 *   * a conversation opens on its latest 50, and older pages come 50 at a time;
 *   * a change naming a held conversation, Topic or thread reads only what
 *     lies after the newest held, and the bodies of only the new posts -- a
 *     held post is read again only where the change names it;
 *   * a membership `ended` names is let go without reading the window again;
 *   * where the change cannot be placed safely (an inclusion among the held,
 *     a window short of the newest, `reread`) the window is read again whole,
 *     and the answer is exactly what the server holds. */
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

globalThis.localStorage = { getItem: () => '[]', setItem: () => {} }
const { store } = await import('../src/fluid/store.ts')

let calls = []
let answer = () => { throw new Error('no answer') }
globalThis.fetch = async (path) => {
  calls.push(decodeURIComponent(path))
  const url = new URL(path, 'http://x')
  const body = await answer(url.pathname.replace('/fluid/api/', ''), url.searchParams)
  return { ok: true, status: 200, json: async () => body }
}
const bodiesAsked = []
const posts = (q) => {
  const ids = q.get('ids').split(',')
  bodiesAsked.push(...ids)
  return { posts: ids.map((id) => ({ id, version: 'v', parts: [], memberships: [] })) }
}

/** A collection as the server pages it (tests/fluid_store_unit.mjs's): members
 *  by position, a member's id as a cursor, `from` inclusive; an ended member
 *  keeps its position, so a cursor at one still pages. */
function pager(key, order, members) {
  const pos = (id) => order.indexOf(id)
  return (q) => {
    const limit = Number(q.get('limit'))
    const live = order.filter((id) => members.has(id))
    let chosen
    if (q.get('from')) {
      const at = q.get('from') === 'start' ? -1 : pos(q.get('from'))
      chosen = live.filter((id) => pos(id) >= at).slice(0, limit)
    } else if (q.get('after')) chosen = live.filter((id) => pos(id) > pos(q.get('after'))).slice(0, limit)
    else if (q.get('before')) chosen = live.filter((id) => pos(id) < pos(q.get('before'))).slice(-limit)
    else chosen = live.slice(-limit)
    const first = chosen.length ? live.indexOf(chosen[0]) : (q.get('after') ? live.filter((id) => pos(id) <= pos(q.get('after'))).length : 0)
    const older = first, newer = Math.max(0, live.length - first - chosen.length)
    return { key, items: chosen.map((id) => ({ id })), total: live.length, older, newer,
      before: older ? chosen[0] : null, after: newer ? chosen.at(-1) : null, cursor: 'f1.0.0.0' }
  }
}

const changeOf = (extra) => ({ cursor: 'c-next', posts: [], conversations: [], collections: [], memberships: { added: [], ended: [] }, ...extra })
const collectionReads = () => calls.filter((c) => c.includes('collections/'))
const ids = (key) => store.collections.get(key).items.map((i) => i.id)

/** A conversation of `n` members, opened on its newest page and `pages` older. */
async function opened(id, n, pages = 0) {
  const order = Array.from({ length: n }, (_, i) => `${id}-${i}`)
  const members = new Set(order)
  const key = 'conversation:' + id
  let change = null
  const page = pager(key, order, members)
  answer = (path, q) => path === 'posts' ? posts(q) : path === 'changes' ? change : page(q)
  store.collections.delete(key)
  calls = []
  await store.loadConversation(id)
  for (let i = 0; i < pages; i++) await store.olderOfConversation(id)
  return { order, members, key, setChange: (c) => { change = c } }
}

/* -- 1. the latest 50, then 50 at a time ------------------------------------- */
{
  const c = await opened('A', 1100, 1)
  const asked = collectionReads()
  assert.ok(/limit=50(&|$)/.test(asked[0]) && !asked[0].includes('before='), asked[0])
  assert.ok(asked[1].includes('limit=50') && asked[1].includes('before=A-1050'), asked[1])
  assert.equal(ids(c.key).length, 100)
  assert.equal(ids(c.key)[0], 'A-1000')
  assert.equal(store.collections.get(c.key).older, 1000)
  console.log(JSON.stringify({ check: 'latest 50, then 50 older', ok: true }))
}

/* -- 2. a new post: only what lies after the newest held, one body ---------- */
{
  const c = await opened('B', 1100, 1)
  const before = ids(c.key)
  c.order.push('B-new'); c.members.add('B-new')
  c.setChange(changeOf({ collections: [c.key, 'stream'], conversations: ['B'],
    posts: [{ id: 'B-new', version: 'B-new', conversations: ['B'] }],
    memberships: { added: [{ post: 'B-new', conversation: 'B', via: 'home', link: 'l1' }], ended: [] } }))
  store.cursor = 'c-prev'
  calls = []; bodiesAsked.length = 0
  let heard = 0
  const off = store.subscribe('coll:' + c.key, () => heard++)
  await store.step()
  off()
  const asked = collectionReads()
  assert.equal(asked.length, 1, asked.join(' '))
  assert.ok(asked[0].includes('after=B-1099') && asked[0].includes('limit=50'), asked[0])
  assert.deepEqual(bodiesAsked, ['B-new'], 'only the new post is read')
  assert.deepEqual(ids(c.key), [...before, 'B-new'])
  const got = store.collections.get(c.key)
  assert.equal(got.total, 1101); assert.equal(got.newer, 0); assert.equal(got.older, 1000)
  assert.equal(got.before, 'B-1000', 'the older cursor is kept')
  assert.equal(heard, 1)
  assert.equal(store.cursor, 'c-next')
  // the same change told again places nothing twice and notifies nobody
  store.cursor = 'c-prev'
  calls = []; heard = 0
  const off2 = store.subscribe('coll:' + c.key, () => heard++)
  await store.step()
  off2()
  assert.deepEqual(ids(c.key), [...before, 'B-new'])
  assert.equal(collectionReads().length, 1)
  assert.equal(heard, 0, 'nothing moved, nothing redrawn')
  console.log(JSON.stringify({ check: 'new post placed without reading the window again', ok: true }))
}

/* -- 3. an ended membership is let go in place ------------------------------ */
{
  const c = await opened('C', 300)
  const gone = 'C-270'
  c.members.delete(gone)
  c.setChange(changeOf({ collections: [c.key], posts: [{ id: gone, version: gone, conversations: ['C'] }],
    memberships: { added: [], ended: [{ post: gone, conversation: 'C', via: 'linked', link: 'l2' }] } }))
  store.cursor = 'c-prev'
  calls = []; bodiesAsked.length = 0
  await store.step()
  assert.equal(collectionReads().length, 1)
  assert.ok(!collectionReads()[0].includes('from='))
  assert.ok(!ids(c.key).includes(gone))
  assert.equal(ids(c.key).length, 49)
  assert.equal(store.collections.get(c.key).total, 299)
  console.log(JSON.stringify({ check: 'ended membership let go in place', ok: true }))
}

/* -- 4. what cannot be placed is read again, and is exactly the server's ---- */
{
  // an old post included among the held: the count says so
  const c = await opened('D', 300, 1)
  c.order.splice(260, 0, 'D-included'); c.members.add('D-included')
  c.order.push('D-new'); c.members.add('D-new')
  c.setChange(changeOf({ collections: [c.key],
    memberships: { added: [{ post: 'D-included', conversation: 'D', via: 'linked', link: 'l3' },
      { post: 'D-new', conversation: 'D', via: 'home', link: 'l4' }], ended: [] } }))
  store.cursor = 'c-prev'
  calls = []
  await store.step()
  const asked = collectionReads()
  assert.ok(asked.some((x) => x.includes('from=D-200') && x.includes('limit=200')), asked.join(' '))
  const live = c.order.filter((id) => c.members.has(id))
  assert.deepEqual(ids(c.key), live.slice(live.indexOf('D-200')))
  assert.ok(ids(c.key).includes('D-included'))

  // a removal nothing named
  c.members.delete('D-280')
  c.setChange(changeOf({ collections: [c.key] }))
  store.cursor = 'c-prev'
  calls = []
  await store.step()
  assert.ok(collectionReads().some((x) => x.includes('from=')))
  assert.ok(!ids(c.key).includes('D-280'))

  // `reread`: read again whole, never placed
  c.setChange({ cursor: 'c-next', reread: true })
  store.cursor = 'c-prev'
  calls = []
  await store.step()
  assert.ok(collectionReads()[0].includes('from='), collectionReads().join(' '))
  console.log(JSON.stringify({ check: 'unplaceable changes read the window again', ok: true }))
}

/* -- 5. a window around an older post is read again as far as it reached ---- */
{
  const order = Array.from({ length: 300 }, (_, i) => `E-${i}`)
  const members = new Set(order)
  const key = 'conversation:E'
  const page = pager(key, order, members)
  let change = null
  answer = (path, q) => path === 'posts' ? posts(q) : path === 'changes' ? change : page(q)
  await store.conversationAround('E', 'E-100')
  assert.equal(ids(key)[0], 'E-90'); assert.equal(ids(key).at(-1), 'E-149')
  order.push('E-new'); members.add('E-new')
  change = changeOf({ collections: [key], memberships: { added: [{ post: 'E-new', conversation: 'E', via: 'home', link: 'l5' }], ended: [] } })
  store.cursor = 'c-prev'
  calls = []
  await store.step()
  assert.equal(ids(key).at(-1), 'E-149', 'what lies beyond stays newer')
  assert.equal(store.collections.get(key).newer, 151)
  console.log(JSON.stringify({ check: 'window short of the newest is not extended', ok: true }))
}

/* -- 6. a thread and a Topic are placed the same way ------------------------ */
{
  // thread
  const order = Array.from({ length: 80 }, (_, i) => `T-${i}`)
  const members = new Set(order)
  const tpage = pager('thread:T', order, members)
  // topic
  const torder = Array.from({ length: 120 }, (_, i) => `F-${i}`)
  const tmembers = new Set(torder)
  const fkey = 'topic:F:topic1'
  const fpage = pager(fkey, torder, tmembers)
  let change = null
  answer = (path, q) => path === 'posts' ? posts(q) : path === 'changes' ? change
    : path === 'collections/thread' ? tpage(q) : fpage(q)
  await store.loadThread('T')
  await store.loadTopic('F', 'topic1')
  assert.equal(ids(fkey).length, 50, 'a Topic opens on its latest 50')
  order.push('T-new'); members.add('T-new')
  torder.push('F-new'); tmembers.add('F-new')
  change = changeOf({ collections: ['thread:T', 'conversation:F'], conversations: ['F'], threads: ['T'],
    posts: [{ id: 'F-new', version: 'F-new', conversations: ['F'] }, { id: 'T-new', version: 'T-new', conversations: ['X'] }],
    memberships: { added: [{ post: 'F-new', conversation: 'F', via: 'home', link: 'l6' }], ended: [] } })
  store.cursor = 'c-prev'
  calls = []; bodiesAsked.length = 0
  await store.step()
  const asked = collectionReads()
  assert.equal(asked.length, 2, asked.join(' '))
  assert.ok(asked.every((x) => x.includes('after=') && !x.includes('from=')), asked.join(' '))
  assert.equal(ids('thread:T').at(-1), 'T-new')
  assert.equal(ids(fkey).at(-1), 'F-new')
  assert.deepEqual(bodiesAsked.sort(), ['F-new', 'T', 'T-new'], 'only the new posts, and the root the change names (threads)')
  // a post filed among the held Topic posts is read again whole
  torder.splice(100, 0, 'F-filed'); tmembers.add('F-filed')
  change = changeOf({ conversations: ['F'], posts: [{ id: 'F-filed', version: 'F-filed', conversations: ['F'] }] })
  store.cursor = 'c-prev'
  calls = []
  await store.step()
  assert.ok(collectionReads().some((x) => x.includes('from=')))
  assert.ok(ids(fkey).includes('F-filed'))
  console.log(JSON.stringify({ check: 'thread and topic placed incrementally', ok: true }))
}

/* -- 7. a held post is read again only where the change names it ----------- */
{
  const c = await opened('G', 120)
  const named = 'G-100'
  c.order.push('G-new'); c.members.add('G-new')
  c.setChange(changeOf({ collections: [c.key],
    posts: [{ id: named, version: 'edited', conversations: ['G'] }, { id: 'G-new', version: 'G-new', conversations: ['G'] }],
    memberships: { added: [{ post: 'G-new', conversation: 'G', via: 'home', link: 'l7' }], ended: [] } }))
  store.cursor = 'c-prev'
  bodiesAsked.length = 0
  await store.step()
  assert.deepEqual(bodiesAsked.sort(), [named, 'G-new'].sort(), bodiesAsked.join(' '))
  console.log(JSON.stringify({ check: 'held bodies read only when named', ok: true }))
}

/* -- 8. a conversation's object index is moved in place, not walked again --- */
{
  const O = 'O'
  store.conversationObjects.set(O, { conversation: O, posts: ['O-1', 'O-2'], fresh: [],
    objects: [{ address: 'live:O-1:k', exact: 'exact:O-1:0:k', kind: 'block', title: 'old', post: 'O-1', number: 1, reply_to_number: null, home: O }] })
  let change = null, walked = 0
  const row = (p) => ({ address: `live:${p}:k`, exact: `exact:${p}:0:k`, kind: 'block', title: p, post: p, number: 9, reply_to_number: null, home: O, preview: { key: 'k', kind: 'block' } })
  answer = (path, q) => {
    if (path === 'changes') return change
    if (path === 'posts') return posts(q)
    if (path === 'objects') {
      if (!q.get('before')) return { objects: [row('O-new')], posts: ['O-new', 'O-2'], before: 'p2' }
      walked++
      return { objects: [row('O-1')], posts: ['O-1'], before: null }
    }
    throw new Error('unexpected ' + path)
  }
  const objectReads = () => calls.filter((c) => c.includes('objects?')).length
  // a run's act names the conversation, and no post of it: nothing is read
  change = changeOf({ conversations: [O] })
  store.cursor = 'c-prev'; calls = []
  await store.step()
  assert.equal(objectReads(), 0, calls.join(' '))
  // a new post: the newest page only, its rows in place of its threads'
  change = changeOf({ conversations: [O], posts: [{ id: 'O-new', version: 'O-new', conversations: [O] }] })
  store.cursor = 'c-prev'; calls = []
  await store.step()
  assert.equal(objectReads(), 1, calls.join(' '))
  assert.deepEqual(store.conversationObjects.get(O).objects.map((o) => o.post), ['O-new', 'O-1'])
  assert.deepEqual(store.conversationObjects.get(O).fresh, ['live:O-new:k'])
  // an edit far back, outside the newest page: walked again whole
  change = changeOf({ conversations: [O], posts: [{ id: 'O-1', version: 'edited', conversations: [O] }] })
  store.cursor = 'c-prev'; calls = []
  await store.step()
  assert.equal(walked, 1)
  assert.deepEqual(store.conversationObjects.get(O).objects.map((o) => o.post), ['O-new', 'O-1'])
  store.conversationObjects.delete(O)
  console.log(JSON.stringify({ check: 'object index moved in place', ok: true }))
}