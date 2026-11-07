/* QUIET CHAT ROUND 5, PACKAGE M: THE MARGIN'S OWN HALF OF THE BOOKMARK.
 *
 * What this suite is for: `rail/Rail.tsx` writes the WHOLE `ReadingBookmark`
 * for a Page (S's envelope merges a map entry by replacing it, never deep
 * merging it), so the one thing this module cannot get wrong is carrying
 * R's half of that entry -- `flow` and `thread` -- through UNTOUCHED while
 * only this module's own `margin` field changes. `withMargin` is that
 * carry-through, the mirror of `reader/ConversationReader.tsx`'s own
 * `NO_MARGIN` default, and it is pure: given rows, not a browser, which is
 * what lets the case that matters -- a margin write that would otherwise
 * silently drop a saved flow or thread -- be checked without one.
 */
import { registerHooks } from 'node:module'
import { readFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import assert from 'node:assert/strict'
import test from 'node:test'
import ts from '../node_modules/typescript/lib/typescript.js'

// The same TS/CSS loader the other client unit suites use; no browser or
// JSX rendering here, only the pure functions `rail/Rail.tsx` exports.
registerHooks({
  resolve(specifier, context, next) {
    if (specifier.startsWith('.')) {
      if (/\.css$/.test(specifier)) {
        return { url: new URL(specifier, context.parentURL).href, shortCircuit: true }
      }
      for (const suffix of ['', '.ts', '.tsx', '/index.ts']) {
        const url = new URL(specifier + suffix, context.parentURL)
        if (suffix && existsSync(fileURLToPath(url))) return { url: url.href, shortCircuit: true }
      }
    }
    return next(specifier, context)
  },
  load(url, context, next) {
    if (/\.css$/.test(url)) return { format: 'module', shortCircuit: true, source: 'export {}' }
    if (/\.tsx?$/.test(url)) return {
      format: 'module', shortCircuit: true,
      source: ts.transpileModule(readFileSync(fileURLToPath(url), 'utf8'), {
        compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
      }).outputText,
    }
    return next(url, context)
  },
})

const { withMargin, emptyMargin } = await import('../src/quiet/rail/Rail.tsx')

const FLOW = { topic: 't1', batch: { after: 3 }, anchor: { post: 'p1', offset: 4 } }
const THREAD = { root: 'r1', target: 'p2', replyTo: 'p2', anchor: null }
const MARGIN = { reading: 'carried', searchOpen: true, query: 'budget', scrollByReading: { carried: 120 } }

test('a margin write with no stored reading yet carries an empty flow and no thread', () => {
  const next = withMargin(null, emptyMargin())
  assert.deepEqual(next.flow, { topic: null, batch: {}, anchor: null })
  assert.equal(next.thread, null)
  assert.deepEqual(next.margin, emptyMargin())
})

test('a margin write carries a stored flow and thread through untouched', () => {
  const stored = { flow: FLOW, thread: THREAD, margin: emptyMargin() }
  const next = withMargin(stored, MARGIN)
  assert.deepEqual(next.flow, FLOW)
  assert.deepEqual(next.thread, THREAD)
  assert.deepEqual(next.margin, MARGIN)
})

test('a margin write never mutates the stored reading it carries through', () => {
  const stored = { flow: FLOW, thread: THREAD, margin: emptyMargin() }
  const before = JSON.stringify(stored)
  withMargin(stored, MARGIN)
  assert.equal(JSON.stringify(stored), before)
})

test('changing only the reading leaves the search box and every scroll entry alone', () => {
  const stored = { flow: FLOW, thread: THREAD, margin: MARGIN }
  const next = withMargin(stored, { ...stored.margin, reading: 'brief' })
  assert.equal(next.margin.reading, 'brief')
  assert.equal(next.margin.searchOpen, true)
  assert.equal(next.margin.query, 'budget')
  assert.deepEqual(next.margin.scrollByReading, { carried: 120 })
})

test('recording one reading\'s scroll keeps every other reading\'s entry', () => {
  const stored = { flow: FLOW, thread: THREAD, margin: { ...MARGIN, scrollByReading: { topics: 40, carried: 120 } } }
  const next = withMargin(stored, {
    ...stored.margin,
    scrollByReading: { ...stored.margin.scrollByReading, carried: 260 },
  })
  assert.deepEqual(next.margin.scrollByReading, { topics: 40, carried: 260 })
})

test('closing the margin is a reading of null, not a dropped bookmark', () => {
  const stored = { flow: FLOW, thread: THREAD, margin: MARGIN }
  const next = withMargin(stored, { ...stored.margin, reading: null })
  assert.equal(next.margin.reading, null)
  assert.deepEqual(next.flow, FLOW)
  assert.deepEqual(next.thread, THREAD)
})

test('emptyMargin is closed, with search shut and nothing scrolled', () => {
  const m = emptyMargin()
  assert.equal(m.reading, null)
  assert.equal(m.searchOpen, false)
  assert.equal(m.query, '')
  assert.deepEqual(m.scrollByReading, {})
})
