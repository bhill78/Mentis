/* THE REAL HISTORY HOOK, AND THE HAND-OFF'S OWN WRAPPERS, RUN AS CODE.
 *
 * Re-review `adm-d84456fd4c3c` blocked three things that were still ORDER AND
 * WIRING left to prose in `results/HOST-INTEGRATION.md` (B4.2, B4.3, B4.4). So
 * this runner does what that review did: it takes the declarations out of that
 * Markdown file with the TypeScript AST, transpiles each one, and hands them to
 * the checks beside it -- which compose them with the REAL `usePlaces` and
 * `useCentreHistory` over a synthetic `history`/`popstate`. A wrapper that
 * stops composing now fails a test.
 *
 * WHAT IS SUBSTITUTED, AND NOTHING ELSE:
 *   - `react`'s `useRef`/`useEffect`, for `places.ts` and `centreHistory.ts`
 *     only: there is no renderer here, so the hook's refs are plain boxes and
 *     its one effect is run by hand. Everything the hook then DOES -- its
 *     trail, its plan, its pop handling, its asking -- is its own.
 *   - Vite's `import.meta.env`, read as empty, exactly as the sibling runners
 *     do (the viewer store reaches `prefs.ts` -> `live.ts`).
 *   - `localStorage`.
 * There is no DOM, no React, no browser, no server and no byte. */
import { registerHooks } from 'node:module'
import { readFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import ts from '../node_modules/typescript/lib/typescript.js'

const REACT = 'data:text/javascript,' + encodeURIComponent(
  'export const useRef = (v) => ({ current: v });'
  + 'export const useEffect = (f) => { globalThis.pendingEffects.push(f) };')

globalThis.pendingEffects = []

registerHooks({
  resolve(specifier, context, next) {
    if (specifier === 'react' && /\/(places|centreHistory)\.ts$/.test(context.parentURL ?? '')) {
      return { url: REACT, shortCircuit: true }
    }
    if (specifier.startsWith('.')) for (const suffix of ['.ts', '.tsx', '/index.ts']) {
      const url = new URL(specifier + suffix, context.parentURL)
      if (existsSync(fileURLToPath(url))) return { url: url.href, shortCircuit: true }
    }
    return next(specifier, context)
  },
  load(url, context, next) {
    if (url.endsWith('.css')) return { format: 'module', source: '', shortCircuit: true }
    if (/\.tsx?$/.test(url)) {
      const source = readFileSync(fileURLToPath(url), 'utf8').replaceAll('import.meta.env', '({})')
      return {
        format: 'module',
        shortCircuit: true,
        source: ts.transpileModule(source, {
          compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
        }).outputText,
      }
    }
    return next(url, context)
  },
})

globalThis.localStorage = { getItem: () => null, setItem: () => {}, removeItem: () => {} }

/* -- the hand-off's own declarations, taken from the Markdown it is in ------- */

const handoffPath = new URL('../src/quiet2/results/HOST-INTEGRATION.md', import.meta.url)
const fences = [...readFileSync(handoffPath, 'utf8').matchAll(/```tsx\r?\n([\s\S]*?)```/g)].map((m) => m[1]).join('\n')

/** the initializer of `const <name> = …`, as written in the hand-off */
function declaration(name, source = fences) {
  const file = ts.createSourceFile('handoff.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
  let found = null
  const visit = (node) => {
    if (ts.isVariableDeclaration(node) && node.name.getText(file) === name) found = node.initializer
    ts.forEachChild(node, visit)
  }
  visit(file)
  if (!found) throw new Error(`HOST-INTEGRATION.md declares no ${name}`)
  return found.getText(file)
}

/** one member of the hand-off's `resultPage`, as written there */
function member(name) {
  const source = `const only = ${declaration('resultPage')}`
  const file = ts.createSourceFile('handoff.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
  const object = file.statements[0].declarationList.declarations[0].initializer
  const property = object.properties.find((p) => p.name?.getText(file) === name)
  if (!property) throw new Error(`resultPage has no ${name}`)
  return property.initializer.getText(file)
}

/** that exact expression, evaluated with the things the page would give it */
function evaluate(expression, deps) {
  const js = ts.transpileModule(`const extracted = ${expression}`, {
    compilerOptions: { target: ts.ScriptTarget.ES2022 },
  }).outputText
  return new Function(...Object.keys(deps), `${js}; return extracted`)(...Object.values(deps))
}

globalThis.handoff = {
  text: (name) => declaration(name),
  declaration: (name, deps) => evaluate(declaration(name), deps),
  member: (name, deps) => evaluate(member(name), deps),
}

await import('./quiet2_result_history_unit.ts')
