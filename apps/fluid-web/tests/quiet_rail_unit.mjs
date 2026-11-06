import { registerHooks } from 'node:module'
import { readFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import assert from 'node:assert/strict'
import test from 'node:test'
import ts from '../node_modules/typescript/lib/typescript.js'

// The same TS loader as the other client unit suites; no browser or JSX here.
registerHooks({
  resolve(specifier, context, next) {
    if (specifier.startsWith('.')) for (const suffix of ['.ts', '.tsx', '/index.ts']) {
      const url = new URL(specifier + suffix, context.parentURL)
      if (existsSync(fileURLToPath(url))) return { url: url.href, shortCircuit: true }
    }
    return next(specifier, context)
  },
  load(url, context, next) {
    if (/\.tsx?$/.test(url)) return {
      format: 'module', shortCircuit: true,
      source: ts.transpileModule(readFileSync(fileURLToPath(url), 'utf8'), {
        compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
      }).outputText,
    }
    return next(url, context)
  },
})

const { markMetrics } = await import('../src/quiet/rail/marks.ts')

test('a mark with no company draws at its minimum, not NaN', () => {
  const m = markMetrics(0, 0, false)
  assert.ok(Number.isFinite(m.thickness) && Number.isFinite(m.length))
  assert.ok(m.thickness > 0 && m.length > 0)
})

test('thickness and length both grow with a topic\'s own turn count', () => {
  const quiet = markMetrics(1, 20, false)
  const busy = markMetrics(20, 20, false)
  assert.ok(busy.thickness > quiet.thickness, 'a busier topic\'s mark is not thicker')
  assert.ok(busy.length > quiet.length, 'a busier topic\'s mark is not longer')
})

test('two topics with the same turn count draw the same mark, unselected', () => {
  assert.deepEqual(markMetrics(7, 20, false), markMetrics(7, 20, false))
})

test('selection emphasises a mark by a computed amount, not only by colour', () => {
  // Same turns, same `max` -- the only input that differs is `selected`, so
  // any difference below is the selection computing something, not the data.
  const plain = markMetrics(7, 20, false)
  const chosen = markMetrics(7, 20, true)
  assert.ok(chosen.thickness > plain.thickness, 'the selected mark is not computed thicker')
  assert.ok(chosen.length > plain.length, 'the selected mark is not computed longer')
})

test('a quiet topic never outweighs a busy one just by being selected', () => {
  // Selection emphasis is additive and bounded; a lightly-used topic that is
  // selected still reads lighter than an unselected, genuinely busy one.
  const quietSelected = markMetrics(1, 20, true)
  const busyUnselected = markMetrics(20, 20, false)
  assert.ok(quietSelected.thickness < busyUnselected.thickness)
  assert.ok(quietSelected.length < busyUnselected.length)
})
