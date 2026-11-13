/* Conversation state in the store (review of qc-convmgmt, 2026-11-12):
 *  - a list response asked BEFORE a confirmed Archive/Trash never puts the
 *    conversation back to its old state (late pre-change response);
 *  - the rail's list is read as Active when the page asks for it, so recent
 *    archived/trashed conversations never take older active ones' places.
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

const row = (id, state = 'active', name = id) => ({ id, name, created: 1, posts: 1, included: 0, participants: 1, last_activity: 1, working: 0, needs_you: 0, state, state_at: state === 'active' ? null : 2, state_by: null })
/* the mocked server: what it holds now, and responses held until released */
const server = new Map([['c1', row('c1')], ['c2', row('c2')]])
const held = []
const calls = []
globalThis.fetch = async (path, options = {}) => {
  const url = new URL(path, 'http://localhost')
  calls.push(url.pathname + url.search)
  const m = url.pathname.match(/^\/fluid\/api\/conversations\/([^/]+)\/(archive|unarchive|trash|restore)$/)
  let body
  const rn = url.pathname.match(/^\/fluid\/api\/conversations\/([^/]+)\/name$/)
  if (rn) {
    const name = JSON.parse(options.body).name
    server.set(rn[1], { ...server.get(rn[1]), name })
    /* the projection is computed NOW, with the state the server holds now */
    body = { conversation: rn[1], name, provisional: false, projection: { ...server.get(rn[1]) } }
    if (globalThis.HOLD_NEXT) {
      globalThis.HOLD_NEXT = false
      return new Promise((resolve) => held.push(() => resolve({ ok: true, status: 200, json: async () => body })))
    }
    return { ok: true, status: 200, json: async () => body }
  }
  if (m) {
    const next = { archive: 'archived', unarchive: 'active', trash: 'trashed', restore: 'active' }[m[2]]
    server.set(m[1], row(m[1], next))
    body = { conversation: m[1], state: next, was: 'active', projection: server.get(m[1]) }
  } else if (url.pathname === '/fluid/api/conversations') {
    const want = url.searchParams.get('state')
    /* answered with what the server holds WHEN ASKED */
    const rows = [...server.values()].filter((c) => !want || c.state === want).map((c) => ({ ...c }))
    body = { conversations: rows, total: rows.length, next: null }
    if (url.searchParams.get('hold') !== null || globalThis.HOLD_NEXT) {
      globalThis.HOLD_NEXT = false
      return new Promise((resolve) => held.push(() => resolve({ ok: true, status: 200, json: async () => body })))
    }
  } else {
    throw new Error('unhandled ' + url.pathname)
  }
  return { ok: true, status: 200, json: async () => body }
}

/* 1. a list page asked before Trash, answered after it */
globalThis.HOLD_NEXT = true
const late = store.conversationPage(null, '', 'active')     // asked while c1 is active
await new Promise((r) => setTimeout(r, 0))
await store.changeConversationState('c1', 'me', 'trash', 'op-1')
assert.equal(store.conversations.get('c1').state, 'trashed', 'the confirmed state is held')
held.shift()()                                               // the old answer arrives now
const got = await late
assert.equal(store.conversations.get('c1').state, 'trashed', 'a late pre-change answer does not revert it')
assert.equal(got.conversations.find((c) => c.id === 'c1')?.state, 'trashed', 'nor does the page it returns')
/* a read asked after the change takes the server's answer as usual */
await store.changeConversationState('c1', 'me', 'restore', 'op-2')
await store.loadConversations(['c1'])
assert.equal(store.conversations.get('c1').state, 'active')

/* 2. the rail's list asked as Active */
store.listState = 'active'
await store.changeConversationState('c2', 'me', 'archive', 'op-3')
await store.loadList()
assert.ok(calls.some((c) => c.startsWith('/fluid/api/conversations?activity=1&limit=40&state=active')), calls.join('\n'))
assert.deepEqual(store.list.map((c) => c.id), ['c1'], 'the rail holds active conversations only')
/* a late unfiltered/older answer for the rail cannot bring an archived one back */
globalThis.HOLD_NEXT = true
server.set('c2', row('c2', 'active'))                        // the server says active when asked...
const lateList = store.loadList()
await new Promise((r) => setTimeout(r, 0))
await store.changeConversationState('c2', 'me', 'archive', 'op-4') // ...then it is archived here
held.shift()()
await lateList
assert.equal(store.conversations.get('c2').state, 'archived')
assert.ok(!store.list.some((c) => c.id === 'c2'), 'the late rail answer drops it from the Active list')

/* 3. a command's projection computed before a confirmed Trash (a rename
   answered late) keeps the name it brings but not the state it carried */
await store.changeConversationState('c1', 'me', 'restore', 'op-5').catch(() => {})
await store.loadConversations(['c1'])
globalThis.HOLD_NEXT = true
const renaming = store.renameConversation('c1', 'me', 'c1 renamed', 'op-6')
await new Promise((r) => setTimeout(r, 0))
await store.changeConversationState('c1', 'me', 'trash', 'op-7')
assert.equal(store.conversations.get('c1').state, 'trashed')
held.shift()()
await renaming
assert.equal(store.conversations.get('c1').state, 'trashed', 'a late rename projection does not revert Trash')
assert.equal(store.conversations.get('c1').name, 'c1 renamed', 'it still brings its name')
console.log('quiet2 conversation state in the store: ok')
