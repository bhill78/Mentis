import { registerHooks } from 'node:module'
import { readFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import assert from 'node:assert/strict'
import test from 'node:test'
import ts from '../node_modules/typescript/lib/typescript.js'

// The same TS/TSX loader as the other client unit suites, plus stylesheets:
// Chrome.tsx imports its own CSS, which node cannot read and which this
// suite is not about (quiet_seam_unit.mjs stubs it the same way).
registerHooks({
  resolve(specifier, context, next) {
    if (specifier.startsWith('.')) {
      if (/\.css$/.test(specifier)) return { url: new URL(specifier, context.parentURL).href, shortCircuit: true }
      for (const suffix of ['.ts', '.tsx', '/index.ts']) {
        const url = new URL(specifier + suffix, context.parentURL)
        if (existsSync(fileURLToPath(url))) return { url: url.href, shortCircuit: true }
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

const { markWeight } = await import('../src/quiet/chrome/Chrome.tsx')

const quiet = { turns: 2, awaiting: 0, live_executions: 0 }
const busy = { turns: 40, awaiting: 3, live_executions: 2 }

test('a quieter and a busier conversation compute different weight', () => {
  assert.notEqual(markWeight(quiet), markWeight(busy))
  assert.ok(markWeight(busy) > markWeight(quiet))
})
test('more live executions is never thinner, everything else held equal', () => {
  const none = { turns: 10, awaiting: 1, live_executions: 0 }
  const one = { turns: 10, awaiting: 1, live_executions: 1 }
  const two = { turns: 10, awaiting: 1, live_executions: 2 }
  assert.ok(markWeight(one) >= markWeight(none))
  assert.ok(markWeight(two) >= markWeight(one))
})
test('more turns alone, or more awaiting alone, is never thinner', () => {
  const base = { turns: 5, awaiting: 0, live_executions: 0 }
  assert.ok(markWeight({ ...base, turns: 20 }) >= markWeight(base))
  assert.ok(markWeight({ ...base, awaiting: 2 }) >= markWeight(base))
})
test('weight never falls below the floor nor rises past the ceiling', () => {
  assert.equal(markWeight({ turns: 0, awaiting: 0, live_executions: 0 }), 2)
  assert.ok(markWeight({ turns: 1000, awaiting: 100, live_executions: 100 }) <= 8)
})
