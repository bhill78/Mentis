import { registerHooks } from 'node:module'
import { readFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import ts from '../node_modules/typescript/lib/typescript.js'

// The same TS/CSS loader as the other client unit suites: no browser, no API
// mock. react-dom/server renders the real component tree.
registerHooks({
  resolve(specifier, context, next) {
    if (specifier.startsWith('.')) {
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
await import('./quiet_post_unit.ts')
