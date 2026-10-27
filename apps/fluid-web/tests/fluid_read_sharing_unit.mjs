/* Fluid's read sharing (ui/src/fluid/store.ts) against a mocked fetch
 * (tests/test_fluid_perf_pass.py).
 *
 * What must hold:
 *   * a read asked while the same read is on its way waits for that one;
 *   * never across a write: a read asked after a write began -- or after
 *     it ended -- is a new read, never one that may predate the write;
 *   * nor across a write made elsewhere: a change step that reports
 *     movement never re-reads by joining a read begun before it (the
 *     review's scenario: Needs you read in flight, an agent asks the owner,
 *     the step's re-read must see the ask);
 *   * a finished read is not kept: asking again reads again;
 *   * `whenQuiet` waits for the store's reads in flight to end. */
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

globalThis.localStorage = { getItem: () => null, setItem: () => {} }

/* -- a server whose answers are released by hand --------------------------- */
const calls = []
const waiting = []
let served = 0
/* What answers: the hand-released server below, unless a section swaps it. */
let handler = null
globalThis.fetch = (path, init) => handler ? handler(path, init) : held(path, init)
const held = (path, init) => {
  calls.push({ path: String(path), method: (init?.method ?? 'GET').toUpperCase() })
  return new Promise((resolve) => {
    waiting.push(() => {
      served += 1
      resolve({ ok: true, status: 200, json: async () => ({ items: [], n: served, period: 'evening' }) })
    })
  })
}
const releaseAll = async () => {
  while (waiting.length) waiting.shift()()
  for (let i = 0; i < 5; i++) await new Promise((r) => setTimeout(r, 0))
}
/* The page's own window; Fluid must not replace its fetch. */
globalThis.window = globalThis
const browserFetch = globalThis.fetch

const { store, whenQuiet, readEpoch } = await import('../src/fluid/store.ts')
const { fluidFetch } = await import('../src/fluid/http.ts')
assert.equal(globalThis.fetch, browserFetch, 'importing Fluid does not patch window.fetch')
const reads = (p) => calls.filter((c) => c.method === 'GET' && c.path.includes(p)).length

/* -- 1. one read in flight per question ------------------------------------ */
{
  const a = store.loadHomeBriefing()
  const b = store.loadHomeBriefing()
  const c = store.loadHomeForYou()
  assert.equal(reads('home/briefing'), 1, 'two zones asking at once share one read')
  assert.equal(reads('home/for-you'), 1)
  await releaseAll()
  const [x, y] = await Promise.all([a, b, c])
  assert.equal(x.n, y.n, 'both askers have the one answer')
}

/* -- 2. a finished read is not kept ---------------------------------------- */
{
  const before = reads('home/briefing')
  const p = store.loadHomeBriefing()
  assert.equal(reads('home/briefing'), before + 1, 'asked again after it ended: read again')
  await releaseAll()
  await p
}

/* -- 3. never across a write ------------------------------------------------ */
{
  const before = reads('home/briefing')
  const e0 = readEpoch()
  const first = store.loadHomeBriefing()
  const write = fluidFetch('/fluid/api/posts', { method: 'POST', body: '{}' })
  assert.ok(readEpoch() > e0, 'a write starting moves the epoch')
  const second = store.loadHomeBriefing()
  assert.equal(reads('home/briefing'), before + 2, 'a read asked after a write began is a new read')
  /* the write ends while a read asked during it is still on its way */
  const during = readEpoch()
  waiting.splice(1, 1)[0]()                       // the write's answer
  await write
  assert.ok(readEpoch() > during, 'a write ending moves the epoch again')
  const third = store.loadHomeBriefing()
  assert.equal(reads('home/briefing'), before + 3, 'a read asked after the write ended is a new read')
  await releaseAll()
  await Promise.all([first, second, third])
}

/* -- 4. whenQuiet waits for the reads in flight ----------------------------- */
{
  let quiet = false
  const p = store.loadHomeBriefing()
  const q = whenQuiet(50, 5000).then(() => { quiet = true })
  await new Promise((r) => setTimeout(r, 200))
  assert.equal(quiet, false, 'not quiet while a read is on its way')
  await releaseAll()
  await p
  await q
  assert.equal(quiet, true, 'quiet once it has ended')
}

/* -- 5. never across a write made elsewhere (the review's scenario) ---------
   The server answers with the record as it stands when the request ARRIVES.
   Home's Needs you read is on its way; an agent then asks the owner
   something; the change feed reports `home:needs-you`. The step's re-read
   must be a new read, and what the store holds must be the ask. */
{
  let record = 'before'
  const queue = []
  const gets = []
  handler = (path, init) => {
    const url = new URL(String(path), 'http://x')
    const p = url.pathname.replace('/fluid/api/', '')
    if ((init?.method ?? 'GET') !== 'GET') return Promise.resolve({ ok: true, status: 200, json: async () => ({}) })
    gets.push(p)
    const seen = record                              // as the request arrives
    let body
    if (p === 'changes') body = { cursor: 'c2', collections: ['home:needs-you'] }
    else if (p === 'home/needs-you') body = { key: 'home:needs-you', items: [], seen, cursor: 'x' }
    else body = { items: [], needs: [], asks: [] }
    return new Promise((resolve) => queue.push({ p, go: () => resolve({ ok: true, status: 200, json: async () => body }) }))
  }
  const flush = async () => {
    for (let i = 0; i < 20; i++) {
      while (queue.length) queue.shift().go()
      await new Promise((r) => setTimeout(r, 0))
    }
  }
  /* Answer only the change feed, leaving every other read on its way. */
  const feedOnly = async () => {
    for (let i = 0; i < 20; i++) {
      const at = queue.findIndex((q) => q.p === 'changes')
      if (at >= 0) queue.splice(at, 1)[0].go()
      await new Promise((r) => setTimeout(r, 0))
    }
  }
  store.cursor = 'c1'
  // the Needs you zone is on screen: Home is read again only while a zone
  // shows it (store.dropUnshownHome)
  const shown = store.subscribe('coll:home:needs-you', () => {})
  store.homeNeedsYou = { key: 'home:needs-you', items: [], cursor: 'x' }
  const early = store.loadHomeNeedsYou()            // in flight: arrived before the ask
  record = 'after'                                   // an agent asks the owner
  const step = store.step()
  await feedOnly()                                   // the feed answers; Needs you is still on its way
  await flush()
  await Promise.all([early, step])
  await flush()
  assert.equal(gets.filter((p) => p === 'home/needs-you').length, 2,
    'the step re-read Needs you itself, not by joining the read begun before the ask')
  assert.equal(store.homeNeedsYou.seen, 'after', 'Needs you holds the ask')
  assert.equal(store.cursor, 'c2')

  /* and startup sharing is kept: with nothing moved, two asks share one read */
  gets.length = 0
  const a = store.loadHomeNeedsYou(); const b = store.loadHomeNeedsYou()
  await flush(); await Promise.all([a, b])
  assert.equal(gets.filter((p) => p === 'home/needs-you').length, 1)
  shown()
  handler = null
}

/* -- 6. whenQuiet counts reads, not what a write cleared --------------------- */
{
  let quiet = false
  const p = store.loadHomeBriefing()
  const write = fluidFetch('/fluid/api/posts', { method: 'POST', body: '{}' })
  const q = whenQuiet(50, 5000).then(() => { quiet = true })
  await new Promise((r) => setTimeout(r, 200))
  assert.equal(quiet, false, 'a write does not make a read on its way look finished')
  await releaseAll()
  await Promise.all([p, write, q])
  assert.equal(quiet, true)
}

console.log('ok')
