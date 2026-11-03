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

let asked
globalThis.fetch = async (path) => {
  asked = new URL(path, 'http://localhost')
  return { ok: true, status: 200, json: async () => ({ hits: [
    { post: 'ent-hit', number: 4, snippet: 'the needle', at: 12 },
  ], more: false }) }
}

const { searchConversation } = await import('../src/fluid/store.ts')
const hits = await searchConversation('ent-conv & one', 'two words?', {
  limit: 7,
  before: 'ent-before',
})

assert.deepEqual(hits, [{ post: 'ent-hit', number: 4, snippet: 'the needle', at: 12 }])
assert.equal(asked.pathname, '/fluid/api/search')
assert.equal(asked.searchParams.get('conversation'), 'ent-conv & one')
assert.equal(asked.searchParams.get('q'), 'two words?')
assert.equal(asked.searchParams.get('limit'), '7')
assert.equal(asked.searchParams.get('before'), 'ent-before')
