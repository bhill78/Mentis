/* Conversation state in the store (reviews of qc-convmgmt, 2026-11-12/13).
 * Ordering is the SERVER's: every row says when its latest state act was
 * recorded (`state_at`, null if it never moved), and the store keeps the
 * newer of what it holds and what arrives -- whatever brought it:
 *  - a page asked before a Trash, answered after it;
 *  - a rename projection computed before a Trash;
 *  - a state learned from another tab through the change feed's ids read,
 *    then an older page;
 *  - two answers from the server out of order;
 * and a state change made here is one at a time per conversation.
 * The rail's list is read as Active when the page asks for it.
 * The server is mocked; responses are held and released by hand. */
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
globalThis.localStorage = { getItem: () => null, setItem: () => {}, removeItem: () => {} }
let sess = {}
globalThis.sessionStorage = { getItem: (k) => sess[k] ?? null, setItem: (k, v) => { sess[k] = String(v) }, removeItem: (k) => { delete sess[k] }, clear: () => { sess = {} } }

const { store } = await import('../src/fluid/store.ts')

/* the mocked server: every state act takes the record's next sequence; its
   wall time is whatever the clock says -- which may step back or tie
   (`CLOCK` fixed), as time.time() can */
let seq = 0
let clock = 1000
let CLOCK = null
const row = (id, state = 'active', at = null, name = id) => ({ id, name, created: 1, posts: 1, included: 0, participants: 1, last_activity: 1, working: 0, needs_you: 0, state, state_at: at, state_by: at ? 'me' : null, state_seq: null })
const server = new Map([['c1', row('c1')], ['c2', row('c2')], ['c3', row('c3')], ['c4', row('c4')], ['c5', row('c5')]])
const move = (id, state) => server.set(id, { ...server.get(id), state, state_at: CLOCK ?? ++clock, state_by: 'me', state_seq: ++seq })
const held = []
const calls = []
let HOLD = 0
const answer = (body) => {
  const res = { ok: true, status: 200, json: async () => body }
  if (HOLD > 0) { HOLD--; return new Promise((resolve) => held.push(() => resolve(res))) }
  return res
}
globalThis.fetch = async (path, options = {}) => {
  const url = new URL(path, 'http://localhost')
  calls.push(url.pathname + url.search)
  const m = url.pathname.match(/^\/fluid\/api\/conversations\/([^/]+)\/(archive|unarchive|trash|restore|name)$/)
  if (m && m[2] === 'name') {
    const name = JSON.parse(options.body).name
    server.set(m[1], { ...server.get(m[1]), name })
    /* the projection is computed NOW, with what the server holds now */
    return answer({ conversation: m[1], name, provisional: false, projection: { ...server.get(m[1]) } })
  }
  if (m) {
    move(m[1], { archive: 'archived', unarchive: 'active', trash: 'trashed', restore: 'active' }[m[2]])
    return answer({ conversation: m[1], state: server.get(m[1]).state, was: 'active', projection: { ...server.get(m[1]) } })
  }
  if (url.pathname === '/fluid/api/conversations') {
    const ids = url.searchParams.get('ids')
    const want = url.searchParams.get('state')
    /* answered with what the server holds WHEN ASKED */
    const rows = ids ? ids.split(',').map((i) => ({ ...server.get(i) }))
      : [...server.values()].filter((c) => !want || c.state === want).map((c) => ({ ...c }))
    return answer(ids ? { conversations: rows } : { conversations: rows, total: rows.length, next: null })
  }
  throw new Error('unhandled ' + url.pathname)
}
const tick = () => new Promise((r) => setTimeout(r, 0))

/* 1. a page asked before Trash, answered after it */
HOLD = 1
const late = store.conversationPage(null, '', 'active')          // asked while c1 is active
await tick()
await store.changeConversationState('c1', 'me', 'trash', 'op-1')
assert.equal(store.conversations.get('c1').state, 'trashed', 'the confirmed state is held')
held.shift()()
const got = await late
assert.equal(store.conversations.get('c1').state, 'trashed', 'a late pre-change page does not revert it')
assert.equal(got.conversations.find((c) => c.id === 'c1')?.state, 'trashed', 'nor does the page it returns')
await store.changeConversationState('c1', 'me', 'restore', 'op-2')
await store.loadConversations(['c1'])
assert.equal(store.conversations.get('c1').state, 'active', 'a Restore is newer than the Trash it undid')

/* 2. a rename projection computed before a Trash keeps its name, not its state */
HOLD = 1
const renaming = store.renameConversation('c1', 'me', 'c1 renamed', 'op-3')
await tick()
await store.changeConversationState('c1', 'me', 'trash', 'op-4')
held.shift()()
await renaming
assert.equal(store.conversations.get('c1').state, 'trashed', 'a late rename projection does not revert Trash')
assert.equal(store.conversations.get('c1').name, 'c1 renamed', 'it still brings its name')

/* 3. state learned from another tab through the change feed, then an older page */
HOLD = 1
const old = store.conversationPage(null, '', 'active')          // c2 active, never moved
await tick()
move('c2', 'trashed')                                           // another tab trashes it
await store.loadConversations(['c2'])                           // the feed's ids read
assert.equal(store.conversations.get('c2').state, 'trashed')
held.shift()()
await old
assert.equal(store.conversations.get('c2').state, 'trashed', 'an older page does not undo what the feed brought')
/* and the other way round: a Restore elsewhere, then an older Trash answer */
HOLD = 1
const older = store.conversationPage(null, '', 'trashed')       // c2 trashed (older time)
await tick()
move('c2', 'active')
await store.loadConversations(['c2'])
held.shift()()
await older
assert.equal(store.conversations.get('c2').state, 'active', 'a Restore learned from the feed holds against an older Trash')

/* 4. one state change at a time per conversation */
HOLD = 1
const archiving = store.changeConversationState('c3', 'me', 'archive', 'op-5')
await tick()
assert.equal(store.changingState('c3'), true)
await assert.rejects(store.changeConversationState('c3', 'me', 'trash', 'op-6'), /still being made/)
held.shift()()
await archiving
assert.equal(store.changingState('c3'), false)
assert.equal(store.conversations.get('c3').state, 'archived')
/* two answers out of order (another tab's Trash read first, this page's
   older Archive answer later): the newer state stands */
HOLD = 1
const ids1 = store.loadConversations(['c3'])                    // asked: archived
await tick()
move('c3', 'trashed')
await store.loadConversations(['c3', 'c1'])                    // a fresh read (not joined to the held one)
held.shift()()
await ids1
assert.equal(store.conversations.get('c3').state, 'trashed')

/* 5. THE CLOCK STEPS BACK: an Unarchive at T, then a Trash recorded at T-1.
   The record's order says Trash is newer; the store must too. */
CLOCK = 5000
await store.changeConversationState('c4', 'me', 'archive', 'op-c1')
await store.changeConversationState('c4', 'me', 'unarchive', 'op-c2')
CLOCK = 4999
await store.changeConversationState('c4', 'me', 'trash', 'op-c3')
assert.equal(store.conversations.get('c4').state, 'trashed', 'a Trash with an earlier clock is still the newer state')
await store.loadConversations(['c4'])
assert.equal(store.conversations.get('c4').state, 'trashed', 'and a fresh read keeps it')
/* THE CLOCK TIES: Unarchive and Trash at the same time; an older page
   answered late does not revert the Trash */
CLOCK = 6000
await store.changeConversationState('c5', 'me', 'archive', 'op-t1')
await store.changeConversationState('c5', 'me', 'unarchive', 'op-t2')
HOLD = 1
const tiePage = store.conversationPage(null, '', 'active')     // asked: c5 active at 6000
await tick()
await store.changeConversationState('c5', 'me', 'trash', 'op-t3') // also at 6000
held.shift()()
await tiePage
assert.equal(store.conversations.get('c5').state, 'trashed', 'a tie in wall time does not let an older page win')
assert.equal(store.conversations.get('c5').state_at, 6000, 'state_at stays for showing')
CLOCK = null

/* 6. the rail's list asked as Active */
store.listState = 'active'
await store.loadList()
assert.ok(calls.some((c) => c.startsWith('/fluid/api/conversations?activity=1&limit=40&state=active')), calls.join('\n'))
assert.deepEqual(store.list.map((c) => c.id), [...server.values()].filter((c) => c.state === 'active').map((c) => c.id), 'the rail holds active conversations only')
await store.changeConversationState('c2', 'me', 'trash', 'op-7').catch(() => {})
await store.loadList()                                          // its own follow-up read settles first
for (let i = 0; i < 5; i++) await tick()
HOLD = 1
move('c1', 'active')                                            // brought back elsewhere
const lateList = store.loadList()                               // asked: c1 active, c2...
await tick()
await store.changeConversationState('c1', 'me', 'archive', 'op-8') // archived here, newer
held.shift()()
await lateList
assert.equal(store.conversations.get('c1').state, 'archived')
assert.ok(!store.list.some((c) => c.id === 'c1'), 'the late rail answer drops it from the Active list')
console.log('quiet2 conversation state in the store: ok')
