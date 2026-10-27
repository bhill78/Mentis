/* Unit tests for Fluid F5 store extensions (Stream S1, Selection S2, Switcher needs_you S3, Change feed keys S4).
 */
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
let sessionItems = {}
globalThis.localStorage = { getItem: () => JSON.stringify(kept), setItem: () => {} }
globalThis.sessionStorage = {
  getItem: (k) => sessionItems[k] ?? null,
  setItem: (k, v) => { sessionItems[k] = String(v) },
  removeItem: (k) => { delete sessionItems[k] },
  clear: () => { sessionItems = {} },
}

const { store } = await import('../src/fluid/store.ts')

/* -- mock server setup ----------------------------------------------------- */

let calls = []
let answers = {}
globalThis.fetch = async (path, options = {}) => {
  calls.push({ path, options })
  const url = new URL(path, 'http://localhost')
  const cleanPath = url.pathname.replace('/fluid/api/', '')
  const handler = answers[cleanPath] || answers[url.pathname]
  if (!handler) {
    throw new Error(`Unhandled route in test: ${url.pathname}`)
  }
  const body = await handler(url.searchParams, options)
  return {
    ok: true,
    status: 200,
    json: async () => body,
  }
}

async function testStreamLoadingAndPaging() {
  console.log('Testing S1: Stream loading and paging...')
  const notifications = []
  const unsub = store.subscribe('coll:stream', () => notifications.push('coll:stream'))

  answers['posts'] = (q) => {
    const ids = q.get('ids').split(',')
    return {
      posts: ids.map((id) => ({
        id,
        version: `v-${id}`,
        versions: 1,
        author: 'u1',
        author_name: 'Author 1',
        at: 100,
        edited_at: null,
        deleted: null,
        parts: [{ type: 'text', text: `Body of ${id}` }],
        addressed_to: [],
        home: 'conv-1',
        home_name: 'Conversation 1',
        number: 1,
        reply_to: null,
        reply_to_home: null,
        reply_to_home_name: null,
        reply_to_number: null,
        memberships: [{ conversation: 'conv-1', via: 'home' }],
        expectations: [],
        replies: { count: 0, by_home: {} },
      })),
    }
  }

  answers['collections/stream'] = (q) => {
    const before = q.get('before')
    if (before === 'page-1-cursor') {
      return {
        key: 'stream',
        items: [
          { id: 'p0', home: 'conv-2', at: 50 },
        ],
        before: null,
        after: 'page-1-cursor',
        cursor: 'cur-2',
        limit: 30,
      }
    }
    return {
      key: 'stream',
      items: [
        { id: 'p2', home: 'conv-1', at: 200 },
        { id: 'p1', home: 'conv-1', at: 100 },
      ],
      before: 'page-1-cursor',
      after: null,
      cursor: 'cur-1',
      limit: 30,
    }
  }

  await store.loadStream()
  const coll = store.collections.get('stream')
  assert.ok(coll, 'stream collection should be loaded')
  assert.equal(coll.items.length, 2)
  assert.equal(coll.items[0].id, 'p2', 'newest post should be first')
  assert.equal(coll.items[1].id, 'p1')
  assert.equal(coll.before, 'page-1-cursor')
  assert.ok(notifications.includes('coll:stream'), 'coll:stream notification emitted')
  assert.ok(store.posts.has('p2'), 'post p2 loaded')
  assert.ok(store.posts.has('p1'), 'post p1 loaded')

  // Older page
  await store.olderOfStream()
  const paged = store.collections.get('stream')
  assert.equal(paged.items.length, 3, 'older items appended to stream')
  assert.equal(paged.items[2].id, 'p0')
  assert.equal(paged.before, null, 'before becomes null on last page')
  assert.ok(store.posts.has('p0'), 'post p0 loaded')
  unsub()
}

async function testSelectionAndS2() {
  console.log('Testing S2: Selection collection and session storage...')
  const notifications = []
  store.subscribe('coll:selection', () => notifications.push('coll:selection'))
  store.subscribe('selection', () => notifications.push('selection'))

  answers['collections/selection'] = (q) => {
    const ids = q.get('ids').split(',')
    return {
      key: 'selection',
      items: ids.map((id) => ({
        id,
        home: id.startsWith('known') ? 'conv-1' : null,
        known: id.startsWith('known'),
      })),
      cursor: 'sel-cur-1',
    }
  }

  // Empty selection
  const empty = await store.loadSelection([])
  assert.equal(empty.items.length, 0)
  assert.equal(store.collections.get('selection').items.length, 0)

  // Selection with known and unknown IDs
  const loaded = await store.loadSelection(['known-1', 'unknown-2'])
  assert.equal(loaded.items.length, 2)
  assert.equal(loaded.items[0].id, 'known-1')
  assert.equal(loaded.items[0].known, true)
  assert.equal(loaded.items[1].id, 'unknown-2')
  assert.equal(loaded.items[1].known, false)
  assert.ok(store.posts.has('known-1'), 'known post loaded into store.posts')
  assert.ok(!store.posts.has('unknown-2'), 'unknown post not fetched into store.posts')

  // Selection mutations and session storage persistence
  store.clearSelection()
  assert.equal(store.selected.size, 0)
  assert.equal(sessionStorage.getItem('mentis.fluid.selection'), '[]')

  store.toggleSelect('post-a')
  assert.ok(store.selected.has('post-a'))
  assert.equal(store.isSelected('post-a'), true)
  assert.equal(sessionStorage.getItem('mentis.fluid.selection'), JSON.stringify(['post-a']))

  store.toggleSelect('post-b')
  assert.ok(store.selected.has('post-b'))
  assert.equal(store.selected.size, 2)

  store.toggleSelect('post-a')
  assert.ok(!store.selected.has('post-a'))
  assert.equal(store.selected.size, 1)

  store.setSelection(['post-x', 'post-y'])
  assert.equal(store.selected.size, 2)
  assert.ok(store.selected.has('post-x'))
  assert.ok(store.selected.has('post-y'))

  store.clearSelection()
  assert.equal(store.selected.size, 0)
}

async function testSwitcherNeedsYouS3() {
  console.log('Testing S3: Switcher activity list with needs_you...')
  answers['conversations'] = (q) => {
    if (q.get('activity') === '1') {
      return {
        conversations: [
          {
            id: 'conv-1',
            name: 'Conversation 1',
            created: 1000,
            posts: 10,
            included: 2,
            participants: 3,
            last_activity: 1200,
            working: 1,
            needs_you: 4,
          },
          {
            id: 'conv-2',
            name: 'Conversation 2',
            created: 2000,
            posts: 1,
            included: 0,
            participants: 1,
            last_activity: 2100,
            working: 0,
            needs_you: 0,
          },
        ],
      }
    }
    return { conversations: [] }
  }

  await store.loadList()
  assert.ok(store.list, 'store.list loaded')
  assert.equal(store.list.length, 2)
  assert.equal(store.list[0].id, 'conv-1')
  assert.equal(store.list[0].needs_you, 4, 'conv-1 has needs_you: 4')
  assert.equal(store.list[1].id, 'conv-2')
  assert.equal(store.list[1].needs_you, 0, 'conv-2 has needs_you: 0')
  assert.equal(store.conversations.get('conv-1')?.needs_you, 4)
}

async function testChangeFeedKeysS4() {
  console.log('Testing S4: Change feed keys stream and conversations...')
  let streamReloads = 0
  let listReloads = 0

  const origStream = answers['collections/stream']
  answers['collections/stream'] = (q, opts) => {
    streamReloads++
    return origStream(q, opts)
  }

  const origConvs = answers['conversations']
  answers['conversations'] = (q, opts) => {
    if (q.get('activity') === '1') listReloads++
    return origConvs(q, opts)
  }

  // Set initial cursor
  store.cursor = 'cur-0'

  // 1. Change feed with collections: ["stream"]
  answers['changes'] = () => ({
    cursor: 'cur-stream-1',
    collections: ['stream'],
  })
  const prevStreamReloads = streamReloads
  await store.step()
  assert.equal(streamReloads, prevStreamReloads + 1, 'stream collection reloaded when stream key is emitted')
  assert.equal(store.cursor, 'cur-stream-1')

  // 2. Change feed with collections: ["conversations"]
  answers['changes'] = () => ({
    cursor: 'cur-convs-1',
    collections: ['conversations'],
  })
  const prevListReloads = listReloads
  await store.step()
  assert.equal(listReloads, prevListReloads + 1, 'conversation list reloaded when conversations key is emitted')
  assert.equal(store.cursor, 'cur-convs-1')

  // 3. Change feed isolation: an unrelated collection change does NOT reload stream or conversations
  answers['changes'] = () => ({
    cursor: 'cur-unrelated-1',
    collections: ['unrelated:key'],
  })
  const beforeStream = streamReloads
  const beforeList = listReloads
  await store.step()
  assert.equal(streamReloads, beforeStream, 'unrelated change does not reload stream')
  assert.equal(listReloads, beforeList, 'unrelated change does not reload conversations')
  assert.equal(store.cursor, 'cur-unrelated-1')
}

async function testDropStreamWhenNotShowing() {
  console.log('Testing opr-d47cdd0755d9: dropStream stops stream reload on changes...')
  let streamReloads = 0
  const origStream = answers['collections/stream']
  answers['collections/stream'] = (q, opts) => {
    streamReloads++
    return origStream(q, opts)
  }

  // Load stream
  await store.loadStream()
  assert.ok(store.collections.has('stream'), 'stream collection loaded')

  // Drop stream (view unmounted, nothing showing it)
  store.dropStream()
  assert.ok(!store.collections.has('stream'), 'stream collection dropped')

  // Emitting stream key in changes does NOT reload stream when dropped and not listened to
  answers['changes'] = () => ({
    cursor: 'cur-drop-stream-1',
    collections: ['stream', 'conversation:conv-1'],
  })
  const prevReloads = streamReloads
  await store.step()
  assert.equal(streamReloads, prevReloads, 'stream is NOT reloaded after dropStream')

  // Load stream so it is active
  await store.loadStream()
  assert.ok(store.collections.has('stream'), 'stream loaded')
  assert.equal(store.streamDropped, false, 'stream is active')

  // In-flight stream reload still on the wire when dropStream is called
  let delayedResolve = null
  answers['collections/stream'] = (q, opts) => {
    streamReloads++
    return new Promise((resolve) => {
      delayedResolve = () => resolve(origStream(q, opts))
    })
  }
  const inFlightPromise = store.loadStream(true)
  await new Promise((r) => setTimeout(r, 10))
  assert.ok(delayedResolve !== null, 'stream request is in-flight')
  store.dropStream()
  assert.ok(!store.collections.has('stream'), 'stream dropped immediately')
  assert.equal(store.streamDropped, true, 'store marks streamDropped true')

  // Delayed response arrives AFTER dropStream
  delayedResolve()
  await inFlightPromise
  assert.ok(!store.collections.has('stream'), 'late answer was discarded and did not re-add stream')

  // Subsequent changes do NOT reload stream
  answers['collections/stream'] = (q, opts) => {
    streamReloads++
    return origStream(q, opts)
  }
  answers['changes'] = () => ({
    cursor: 'cur-drop-stream-2',
    collections: ['stream'],
  })
  const prevBeforeChanges = streamReloads
  await store.step()
  assert.equal(streamReloads, prevBeforeChanges, 'changes do NOT reload stream after late response discarded')

  // In-flight olderOfStream arriving after dropStream
  await store.loadStream()
  assert.ok(store.collections.has('stream'), 'reopened stream')
  delayedResolve = null
  answers['collections/stream'] = (q, opts) => {
    streamReloads++
    return new Promise((resolve) => {
      delayedResolve = () => resolve(origStream(q, opts))
    })
  }
  const inFlightOlder = store.olderOfStream()
  await new Promise((r) => setTimeout(r, 10))
  assert.ok(delayedResolve !== null, 'olderOfStream request is in-flight')
  store.dropStream()
  assert.ok(!store.collections.has('stream'), 'dropped before older arrived')
  delayedResolve()
  await inFlightOlder
  assert.ok(!store.collections.has('stream'), 'late older page discarded')

  // Re-opening stream reloads it fresh
  answers['collections/stream'] = (q, opts) => {
    streamReloads++
    return origStream(q, opts)
  }
  await store.loadStream()
  assert.ok(store.collections.has('stream'), 'stream collection reloaded fresh when view opens')
  assert.equal(store.streamDropped, false, 'streamDropped is false on reopen')
}

async function run() {
  await testStreamLoadingAndPaging()
  await testSelectionAndS2()
  await testSwitcherNeedsYouS3()
  await testChangeFeedKeysS4()
  await testDropStreamWhenNotShowing()
  console.log('All F5 store unit tests passed cleanly!')
}

run().catch((err) => {
  console.error('Test failed:', err)
  process.exit(1)
})
