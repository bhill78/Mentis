import { registerHooks } from 'node:module'
import { readFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import assert from 'node:assert/strict'
import test from 'node:test'
import ts from '../node_modules/typescript/lib/typescript.js'
registerHooks({
  resolve(s, c, next) {
    if (s.startsWith('.')) for (const suffix of ['', '.ts', '.tsx', '/index.ts']) {
      const u = new URL(s + suffix, c.parentURL)
      if (existsSync(fileURLToPath(u)) && /\.(tsx?|css)$/.test(u.pathname)) return { url: u.href, shortCircuit: true }
    }
    return next(s, c)
  },
  load(u, c, next) {
    if (u.endsWith('.css')) return { format: 'module', source: '', shortCircuit: true }
    if (/\.tsx?$/.test(u)) return { format: 'module', shortCircuit: true, source: ts.transpileModule(readFileSync(fileURLToPath(u), 'utf8'), { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX } }).outputText.replaceAll('import.meta.env', '{}') }
    return next(u, c)
  },
})
globalThis.localStorage = { getItem: () => null, setItem: () => {}, removeItem: () => {} }
const { createElement: h } = await import('react')
const { renderToStaticMarkup: render } = await import('react-dom/server')
const { ActivityContent, RetainedOutput } = await import('../src/quiet2/activity/RunControls.tsx')
const { RefWordsContext } = await import('../src/experimental/refWords.tsx')
const text = 'BEGIN ' + 'x'.repeat(11000) + ' MIDDLE ' + 'y'.repeat(11000) + ' TAIL'
const recorded = { terminal: 'failed', collected_text: text, error: 'FAILURE ' + 'z'.repeat(500) + ' ERROR TAIL', notes: ['NOTE ' + 'n'.repeat(600) + ' NOTE TAIL'], reply_turn: 'ent-answer', returned_artifacts: ['adm-exact'] }
const draw = (held, more = {}) => render(h(ActivityContent, { state: { feed: { run: 'run', held_here: held, ended_at: 9, events: [], next: 301, recorded, ...more }, entries: [{ id: 'm', seq: 1, kind: 'message', at: 1, text: 'live summary sentinel' }], error: null }, reread() {} }))
test('held runs keep the clipped live summary and full retained output', () => {
  const html = draw(true)
  for (const sentinel of ['live summary sentinel', 'Live activity summary', text, 'ERROR TAIL', 'NOTE TAIL']) assert.ok(html.includes(sentinel), sentinel.slice(0, 40))
  assert.ok(!html.includes('no longer holds'))
})
test('evicted runs expose the same full output and truthful residency', () => {
  const html = draw(false)
  assert.ok(html.includes(text) && html.includes('no longer holds'))
  assert.ok(!html.includes('live summary sentinel'))
})
test('publication pending is distinct from older missing and empty text', () => {
  assert.ok(draw(true, { recorded: undefined }).includes('may still be publishing'))
  assert.ok(draw(true, { recorded: undefined }).includes('Reread recorded end'))
  assert.ok(render(h(RetainedOutput, { recorded: { terminal: 'failed' } })).includes('was not recorded'))
  assert.ok(render(h(RetainedOutput, { recorded: { collected_text: '' } })).includes('recorded empty text'))
})
test('exact identities pass to the host opener; raw output never becomes HTML', () => {
  const calls = []
  const host = { links: s => s, names: s => s, open: (id, words) => { calls.push(id); return h('button', { 'data-ref': id }, words) } }
  const html = render(h(RefWordsContext.Provider, { value: host }, h(RetainedOutput, { recorded: { ...recorded, collected_text: '<img src=x onerror=alert(1)>' } })))
  assert.deepEqual(calls, ['ent-answer', 'adm-exact'])
  assert.ok(html.includes('&lt;img') && !html.includes('<img'))
})

test('full recorded diagnostics survive independently of collector availability', () => {
  const html = render(h(RetainedOutput, { recorded: { terminal: 'failed', collected_text: null,
    runtime_evidence: { error_kind: 'backend_exited', stop_reason: 'non_end_turn' },
    outcome_unclaimed: { kind: 'malformed', why: 'Specific full claim diagnostic tail' } } }))
  for (const words of ['was not recorded', 'backend_exited', 'non_end_turn', 'Specific full claim diagnostic tail']) assert.ok(html.includes(words), words)
})

test('an ended held run never claims nothing has been reported yet', () => {
  const drawEmpty = (ended_at, retained) => render(h(ActivityContent, { state: { feed: { run: 'run', held_here: true, ended_at, recorded: retained, events: [], next: 0 }, entries: [], error: null }, reread() {} }))
  assert.ok(!drawEmpty(9, recorded).includes('Nothing reported yet.'))
  assert.ok(!drawEmpty(9, undefined).includes('Nothing reported yet.'))
  assert.ok(drawEmpty(null, undefined).includes('Nothing reported yet.'))
})

test('multiple artifact actions have distinct names and duplicate identities appear once', () => {
  const calls = []
  const host = { links: s => s, names: s => s, open: (id, words) => { calls.push([id, words]); return h('button', { 'data-ref': id }, words) } }
  render(h(RefWordsContext.Provider, { value: host }, h(RetainedOutput, { recorded: { returned_artifacts: ['adm-one', 'adm-two', 'adm-one'] } })))
  assert.deepEqual(calls, [['adm-one', 'Open returned artifact 1'], ['adm-two', 'Open returned artifact 2']])
})
