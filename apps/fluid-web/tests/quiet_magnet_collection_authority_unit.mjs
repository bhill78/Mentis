import { registerHooks } from 'node:module'
import { readFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import ts from '../node_modules/typescript/lib/typescript.js'
globalThis.__ccProbe__ = { calls: [] }
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
    /* THE EMBEDDED PANEL IS SUBSTITUTED BY A PROBE, not mocked by rewriting
     * `EvidenceViews` itself: `CollectionConfiguration`'s own `Save` gating
     * only resolves through an effect (`findConfigurationLocation`) a static
     * render never runs, which would make the real panel's `disabled`
     * attribute refuse every save regardless of `canWrite` and hide the
     * seam this test exists to check. The probe records exactly what it was
     * given and gates its own stand-in save button on `canWrite` alone. */
    if (url.endsWith('/CollectionConfiguration.tsx')) {
      // The probe substitutes the real panel's source entirely.
      return { format: 'module', shortCircuit: true, source: `
        import { createElement } from 'react'
        export default function CollectionConfigurationProbe(p) {
          globalThis.__ccProbe__.calls.push(p)
          return createElement('button', { type: 'button', disabled: !p.canWrite('home'), 'data-probe-save': '' }, 'Save collection configuration')
        }
      ` }
    }
    if (/\.tsx?$/.test(url)) return { format: 'module', shortCircuit: true, source: ts.transpileModule(readFileSync(fileURLToPath(url), 'utf8'), { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX } }).outputText }
    return next(url, context)
  },
})
await import('./quiet_magnet_collection_authority_unit.ts')
