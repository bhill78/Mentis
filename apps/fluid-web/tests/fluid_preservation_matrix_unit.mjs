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
/* a browser's two storages, as maps (the closed sets, the tab copy, drafts) */
const storage = () => { const m = new Map(); return { getItem: (k) => (m.has(k) ? m.get(k) : null), setItem: (k, v) => { m.set(k, String(v)) }, removeItem: (k) => { m.delete(k) }, get length() { return m.size }, key: (i) => [...m.keys()][i] ?? null, _m: m } }
globalThis.localStorage = storage()
globalThis.sessionStorage = storage()
/* the least DOM the hosts registry (focus/hosts.tsx) needs, counting what it makes */
globalThis.__made = []
const el = () => { const e = { className: '', dataset: {}, style: {}, parentElement: null, setAttribute() {}, addEventListener() {}, appendChild(c) { c.parentElement = e; return c } }; globalThis.__made.push(e); return e }
globalThis.document = { createElement: el, body: el() }
await import('./fluid_preservation_matrix_unit.ts')
