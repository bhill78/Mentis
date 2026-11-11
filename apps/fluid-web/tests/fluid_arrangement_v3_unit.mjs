import { registerHooks } from 'node:module'
import { readFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import ts from '../node_modules/typescript/lib/typescript.js'

registerHooks({
  resolve(specifier, context, next) {
    if (specifier.startsWith('.')) for (const suffix of ['.ts', '.tsx', '/index.ts']) {
      const url = new URL(specifier + suffix, context.parentURL)
      if (existsSync(fileURLToPath(url))) return { url: url.href, shortCircuit: true }
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
/* A real tab store, so the Holder's own session copy of a place -- which
   F9's precedence reads before any copy brought to it -- can be seeded and
   read back here. Each case uses its own place key. */
const session = new Map()
globalThis.sessionStorage = {
  getItem: (k) => (session.has(String(k)) ? session.get(String(k)) : null),
  setItem: (k, v) => { session.set(String(k), String(v)) },
  removeItem: (k) => { session.delete(String(k)) },
  clear: () => { session.clear() },
}
globalThis.fetch = async () => { throw new Error('offline in a unit test') }
globalThis.window = { innerWidth: 1200, innerHeight: 800 }

await import('./fluid_arrangement_v3_unit.ts')
