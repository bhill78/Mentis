import { registerHooks } from 'node:module'
import { readFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import ts from '../node_modules/typescript/lib/typescript.js'
// In-memory TS loader: no application server, fixture State, or subprocess.
// The frame is drawn with react-dom/server, which asks every external store
// for a server snapshot; here the client's snapshot stands for it.
const SES = /import \{([^}]*)\buseSyncExternalStore\b([^}]*)\} from 'react'/
const ssr = (out) => SES.test(out)
  ? out.replace(SES, "import {$1useSyncExternalStore as __uSES$2} from 'react'") + '\nfunction useSyncExternalStore(s, g, h) { return __uSES(s, g, h ?? g) }\n'
  : out
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
    if (/\.tsx?$/.test(url)) return { format: 'module', shortCircuit: true, source: ssr(ts.transpileModule(readFileSync(fileURLToPath(url), 'utf8'), { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX } }).outputText) }
    return next(url, context)
  },
})
// a phone held in portrait: compact, coarse, nothing hovers (frame/narrow.ts reads it on load)
globalThis.innerWidth = 390; globalThis.innerHeight = 844
globalThis.matchMedia = (q) => ({ matches: /max-width|coarse|hover: none/.test(q), addEventListener() {} })
await import('./fluid_narrow_discs_unit.ts')
