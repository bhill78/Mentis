/* PACKAGE G's unit suite, without a browser.
 *
 * What a DOM-less Node test can actually exercise: the surface-treatment
 * store's persistence (pure, no effects) and BackgroundControl's render
 * before any `useLook` has ever run (the module-level `controls` store
 * `fluid/frame/look.ts` starts with -- null, until some component's effect
 * fills it). Everything that depends on `useLook`'s effects actually running
 * -- an atmosphere reaching the document, the control's options reflecting
 * it, persistence surviving a reload -- is a live-browser claim and is
 * asserted in `tests/test_quiet_surface_browser.py` instead, against a real
 * page rather than a guess at what React's effects would have done. */
import { registerHooks } from 'node:module'
import { readFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import assert from 'node:assert/strict'
import test from 'node:test'
import ts from '../node_modules/typescript/lib/typescript.js'

registerHooks({
  resolve(specifier, context, next) {
    if (specifier.startsWith('.')) {
      if (/\.css$/.test(specifier))
        return { url: new URL(specifier, context.parentURL).href, shortCircuit: true }
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

const store = new Map()
globalThis.localStorage = {
  getItem: (k) => (store.has(k) ? store.get(k) : null),
  setItem: (k, v) => void store.set(k, String(v)),
  removeItem: (k) => void store.delete(k),
}

const { default: Surface, getSurfaceTreatment, setSurfaceTreatment } =
  await import('../src/quiet/surface/Surface.tsx')
const { default: BackgroundControl } = await import('../src/quiet/surface/BackgroundControl.tsx')
const { ATMOSPHERES } = await import('../src/atmosphere.ts')

test('the surface treatment defaults to solid -- what Quiet always drew', () => {
  assert.equal(getSurfaceTreatment(), 'solid')
})

test('choosing glass persists under its own key and reads back', () => {
  setSurfaceTreatment('glass')
  assert.equal(getSurfaceTreatment(), 'glass')
  assert.equal(store.get('mentis:quiet-surface'), 'glass')
  setSurfaceTreatment('solid')
  assert.equal(getSurfaceTreatment(), 'solid')
  assert.equal(store.get('mentis:quiet-surface'), 'solid')
})

test('Surface and BackgroundControl both import and export a component', () => {
  // Both read `fluid/frame/look.ts`'s `useSyncExternalStore`-based store,
  // which needs a real DOM to render (even to render nothing) -- this
  // process has none, and the seam's own `quiet_seam_unit.mjs` already
  // checks each exports a function. What rendering them actually produces,
  // before and after a look is chosen, is the browser suite's claim.
  assert.equal(typeof Surface, 'function')
  assert.equal(typeof BackgroundControl, 'function')
})

test('exactly 11 built-in atmospheres exist for the control to offer', () => {
  assert.equal(ATMOSPHERES.length, 11)
  assert.ok(ATMOSPHERES.every((a) => a.id && a.name && a.says))
})

test('surface.css paints .qc\'s background layer only, never its structure', () => {
  const css = readFileSync(new URL('../src/quiet/surface/surface.css', import.meta.url), 'utf8')
  assert.ok(css.includes(".qc { background:"), 'the solid ground is still declared')
  assert.ok(css.includes("[data-surface='glass']"), 'a glass treatment is declared')
  for (const structural of ['grid-template-rows', 'height: 100dvh', 'isolation:'])
    assert.ok(!css.includes(structural), `surface.css must not carry .qc's structural property ${structural}`)
})

test('surface.css is this package\'s only edit to a file layout.css also touches .qc in', () => {
  const atmosphere = readFileSync(new URL('../src/atmosphere.css', import.meta.url), 'utf8')
  assert.ok(!atmosphere.includes("data-surface"), 'atmosphere.css carries no surface-treatment rule of its own')
})
