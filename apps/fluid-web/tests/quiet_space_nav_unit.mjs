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
    if (/\.tsx?$/.test(url)) {
      const out = ts.transpileModule(readFileSync(fileURLToPath(url), 'utf8'), { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX } }).outputText
      /* Vite's build-time environment (live.ts reads VITE_MENTIS_READONLY) is
         not a thing outside a build: it reads as nothing here, which is what
         a page Mentis itself serves sees. */
      return { format: 'module', shortCircuit: true, source: out.replace(/import\.meta\.env/g, '({})') }
    }
    return next(url, context)
  },
})
globalThis.localStorage = { getItem: () => null, setItem: () => {}, removeItem: () => {} }
await import('./quiet_space_nav_unit.ts')
