/* Unit tests for Fluid F4b Home store extensions against the F4 contract.
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
globalThis.localStorage = { getItem: () => JSON.stringify(kept), setItem: () => {} }
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

async function testStoreWorkAndRuns() {
  const notifications = []
  store.subscribe('work:w1', () => notifications.push('work:w1'))
  store.subscribe('work:w2', () => notifications.push('work:w2'))
  store.subscribe('run:r1', () => notifications.push('run:r1'))

  answers['work'] = (q) => {
    const ids = q.get('ids').split(',')
    return {
      work: ids.map((id) => ({
        id,
        what: `Task ${id}`,
        state: 'in-flight',
        carrier: 'user-1',
        carrier_name: '@user',
        conversation: 'conv-1',
        conversation_name: 'Conversation 1',
        post: `p-${id}`,
        post_number: 1,
        runs: [],
        updated_at: 1000,
      })),
    }
  }

  answers['runs'] = (q) => {
    const ids = q.get('ids').split(',')
    return {
      runs: ids.map((id) => ({
        id,
        runtime: 'python3',
        model: 'model-a',
        participant: 'ent-agent',
        participant_name: '@agent',
        conversation: 'conv-1',
        post: 'p-1',
        state: 'completed',
        started_at: 1000,
        ended_at: 1050,
      })),
    }
  }

  const loadedWork = await store.loadWork(['w1', 'w2'])
  assert.equal(loadedWork.length, 2)
  assert.equal(loadedWork[0].id, 'w1')
  assert.equal(loadedWork[1].id, 'w2')
  assert.ok(notifications.includes('work:w1'))
  assert.ok(notifications.includes('work:w2'))

  const loadedRuns = await store.loadRuns(['r1'])
  assert.equal(loadedRuns.length, 1)
  assert.equal(loadedRuns[0].id, 'r1')
  assert.ok(notifications.includes('run:r1'))
}

async function testStoreHomeEndpoints() {
  answers['home/needs-you'] = () => ({
    items: ['w1'],
    before: null,
    cursor: 'c-ny-1',
  })

  answers['home/work'] = (q) => ({
    items: ['w1', 'w2'],
    before: null,
    counts: { all: 2, 'in-flight': 2, 'needs-you': 0 },
    cursor: 'c-work-1',
  })

  answers['home/activity'] = () => ({
    items: ['r1'],
    cursor: 'c-act-1',
  })

  answers['home/briefing'] = (q) => ({
    period: q.get('period') || 'morning',
    items: [{ post: 'p-1', conversation: 'conv-1', line: 'Briefing line 1' }],
    cursor: 'c-br-1',
  })

  answers['home/for-you'] = () => ({
    items: ['p-1'],
    before: null,
    cursor: 'c-fy-1',
  })

  answers['posts'] = () => ({
    posts: [{ id: 'p-1', version: 'v-1', parts: [{ type: 'text', text: 'Hello' }], memberships: [] }],
  })

  const ny = await store.loadHomeNeedsYou()
  assert.deepEqual(ny.items, ['w1'])

  const hw = await store.loadHomeWork('in-flight')
  assert.deepEqual(hw.items, ['w1', 'w2'])
  assert.equal(hw.counts['in-flight'], 2)

  const act = await store.loadHomeActivity()
  assert.deepEqual(act.items, ['r1'])

  const br = await store.loadHomeBriefing('lunch')
  assert.equal(br.period, 'lunch')
  assert.equal(br.items[0].line, 'Briefing line 1')

  answers['home/briefing'] = (q) => {
    assert.equal(q.get('period'), null, 'no period param sent when unpicked')
    return {
      period: 'morning',
      items: [{ post: 'p-1', conversation: 'conv-1', line: 'Briefing line 1' }],
      cursor: 'c-br-2',
    }
  }
  const brDefault = await store.loadHomeBriefing()
  assert.equal(brDefault.period, 'morning')

  const fy = await store.loadHomeForYou()
  assert.deepEqual(fy.items, ['p-1'])
}

async function testArrangements() {
  let saved = null
  answers['arrangements/home'] = (_q, options) => {
    if (options.method === 'POST') {
      const body = JSON.parse(options.body)
      saved = body.layout
      return { layout: saved, cursor: 'c-arr-1' }
    }
    return { layout: saved }
  }

  const initial = await store.loadArrangement('home')
  assert.equal(initial, null)

  const layoutToSave = {
    format: 'mentis.fluid-arrangement',
    version: 1,
    tree: {
      type: 'split',
      dir: 'col',
      sizes: [0.5, 0.5],
      kids: [
        { type: 'zone', id: 'briefing', show: 'briefing', options: { period: 'lunch' } },
        { type: 'zone', id: 'work', show: 'work', options: { tab: 'in-flight' } },
      ],
    },
  }
  const saveRes = await store.saveArrangement('home', layoutToSave)
  assert.deepEqual(saveRes.layout, layoutToSave)

  const restored = await store.loadArrangement('home')
  assert.deepEqual(restored, layoutToSave)
}

async function testChangeFeedNotificationIsolation() {
  store.cursor = 'f1.1.0.0'
  const work1Notified = []
  const work2Notified = []
  const homeWorkNotified = []
  const briefingNotified = []

  const stops = [
    store.subscribe('work:w1', () => work1Notified.push(Date.now())),
    store.subscribe('work:w2', () => work2Notified.push(Date.now())),
    store.subscribe('coll:home:work', () => homeWorkNotified.push(Date.now())),
    store.subscribe('coll:home:briefing', () => briefingNotified.push(Date.now())),
  ]

  // Change only work:w1 via changes.entities
  answers['changes'] = () => ({
    cursor: 'f1.2.0.0',
    entities: ['work:w1'],
  })

  await store.step()

  assert.equal(work1Notified.length, 1, 'work:w1 was updated')
  assert.equal(work2Notified.length, 0, 'work:w2 was untouched')
  assert.equal(homeWorkNotified.length, 0, 'home:work collection was untouched')
  assert.equal(briefingNotified.length, 0, 'home:briefing was untouched')

  // Change only home:briefing via changes.collections
  answers['changes'] = () => ({
    cursor: 'f1.3.0.0',
    collections: ['home:briefing'],
  })

  await store.step()

  assert.equal(work1Notified.length, 1, 'work:w1 was untouched on briefing change')
  assert.equal(briefingNotified.length, 1, 'briefing collection was notified')
  stops.forEach((stop) => stop())
}

async function testCommandAndFeedErrorSlots() {
  store.setError('Layout save refused: probe refusal')
  assert.equal(store.commandError, 'Layout save refused: probe refusal')
  assert.equal(store.error, 'Layout save refused: probe refusal')

  answers['changes'] = () => ({
    cursor: 'f1.4.0.0',
    collections: [],
  })

  await store.step()

  // Successful feed step does not wipe command error
  assert.equal(store.commandError, 'Layout save refused: probe refusal')
  assert.equal(store.error, 'Layout save refused: probe refusal')

  // Dismissing clears command error
  store.setError(null)
  assert.equal(store.commandError, null)
  assert.equal(store.error, null)
}

async function testUnshownHomeIsNotReadAgain() {
  /* Home answers no zone shows are let go, and a change naming them reads
     nothing for nobody (2026-10-27: home/work cost 3.3 s a read on the live
     Brain, re-read on every record move once Home had ever been opened). */
  store.cursor = 'f1.5.0.0'
  answers['home/work'] = () => ({ key: 'home:work', state: 'all', items: [], counts: {}, cursor: 'f1.5.0.0' })
  answers['home/activity'] = () => ({ items: [], cursor: 'f1.5.0.0' })
  await store.loadHomeWork('all')
  await store.loadHomeActivity()
  calls = []
  answers['changes'] = () => ({ cursor: 'f1.6.0.0', collections: ['home:work', 'home:activity'] })
  await store.step()
  const homeReads = calls.filter((c) => /home\/(work|activity)/.test(c.path))
  assert.equal(homeReads.length, 0, 'nothing shows Home, so Home is not read again')
  assert.equal(store.homeWork.size, 0, 'an unshown Home work answer is let go')
  assert.equal(store.homeActivity, null, 'an unshown Home activity answer is let go')

  /* Shown, it is read again exactly as before. */
  const stop = store.subscribe('coll:home:work:all', () => {})
  await store.loadHomeWork('all')
  calls = []
  answers['changes'] = () => ({ cursor: 'f1.7.0.0', collections: ['home:work'] })
  await store.step()
  assert.equal(calls.filter((c) => /home\/work/.test(c.path)).length, 1, 'a shown Home work state is read again')
  stop()
}

async function main() {
  console.log('Testing work and runs loading...')
  await testStoreWorkAndRuns()
  console.log('Testing home contract endpoints...')
  await testStoreHomeEndpoints()
  console.log('Testing arrangements persistence...')
  await testArrangements()
  console.log('Testing change feed notification isolation...')
  await testChangeFeedNotificationIsolation()
  console.log('Testing command and feed error slots...')
  await testCommandAndFeedErrorSlots()
  console.log('Testing unshown Home is not read again...')
  await testUnshownHomeIsNotReadAgain()
  console.log('All F4b store unit tests passed cleanly!')
}

await main()
