import { registerHooks } from 'node:module'
import { readFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import ts from '../node_modules/typescript/lib/typescript.js'
registerHooks({
  resolve(s, c, next) { if (s.startsWith('.')) for (const suffix of ['.ts', '.tsx', '/index.ts']) { const u = new URL(s + suffix, c.parentURL); if (existsSync(fileURLToPath(u))) return { url: u.href, shortCircuit: true } } return next(s, c) },
  load(u, c, next) {
    if (u.endsWith('.css')) return { format: 'module', source: '', shortCircuit: true }
    if (/\.tsx?$/.test(u)) return { format: 'module', shortCircuit: true, source: ts.transpileModule(readFileSync(fileURLToPath(u), 'utf8'), { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX } }).outputText.replace(/import\.meta\.env/g, '({})') }
    return next(u, c)
  },
})
globalThis.localStorage = { getItem: () => null, setItem: () => {}, removeItem: () => {} }
await import('./quiet_magnet_navigation_unit.ts')
