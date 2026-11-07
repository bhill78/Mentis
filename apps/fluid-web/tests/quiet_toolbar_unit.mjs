/* TRACK D's unit suite, without a browser: what a DOM-less Node test can
 * actually exercise -- the modules import and export what the contract
 * says, the pinned-toolbar appearance field persists the way pinHeader and
 * pinMargins already do, and the stylesheets carry the rules this track's
 * claims depend on. Everything that needs a real DOM -- the strip's actual
 * order, the theme cycling and surviving reload, the pinned toolbar's
 * fixed position at 1440 and its absence at 390, search highlighting and
 * stepping -- is a live-browser claim, asserted in
 * tests/test_quiet_r4_toolbar_browser.py against a real page. */
import { registerHooks } from 'node:module'
import { readFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import assert from 'node:assert/strict'
import test from 'node:test'
import ts from '../node_modules/typescript/lib/typescript.js'

registerHooks({
  resolve(specifier, context, next) {
    if (specifier.startsWith('.')) {
      if (/\.css$/.test(specifier)) return { url: new URL(specifier, context.parentURL).href, shortCircuit: true }
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

const here = fileURLToPath(new URL('.', import.meta.url))

const { default: Toolbar } = await import('../src/quiet/chrome/Toolbar.tsx')
const { default: QuietSearch } = await import('../src/quiet/search/QuietSearch.tsx')
const { ENTRIES } = await import('../src/quiet/contract.ts')
const { setSurfaceAppearance, getSurfaceAppearance } = await import('../src/quiet/surface/Surface.tsx')

test('Toolbar and QuietSearch both import and export a component', () => {
  assert.equal(typeof Toolbar, 'function')
  assert.equal(typeof QuietSearch, 'function')
})

test('the contract lists this track\'s two new entry modules, owned by D', () => {
  const toolbar = ENTRIES.find((e) => e.path === './chrome/Toolbar.tsx')
  const search = ENTRIES.find((e) => e.path === './search/QuietSearch.tsx')
  assert.ok(toolbar && toolbar.package === 'D' && toolbar.exports.includes('default'))
  assert.ok(search && search.package === 'D' && search.exports.includes('default'))
})

test('pinning the toolbar persists under the same appearance key as pinHeader and pinMargins', () => {
  assert.equal(getSurfaceAppearance().pinToolbar, false)
  setSurfaceAppearance({ pinToolbar: true })
  assert.equal(getSurfaceAppearance().pinToolbar, true)
  assert.equal(JSON.parse(store.get('mentis:quiet-appearance')).pinToolbar, true)
  setSurfaceAppearance({ pinToolbar: false })
})

test('toolbar.css gives the three new icons a consistent 32px hit target, and pins the strip only from 900px up', () => {
  const css = readFileSync(here + '../src/quiet/chrome/toolbar.css', 'utf8')
  assert.ok(css.includes('width: 32px') && css.includes('height: 32px'))
  assert.ok(/@media \(min-width: 900px\)/.test(css), 'the pinned strip is fixed only at or above 900px')
  assert.ok(css.includes("[data-pin-toolbar='true']"), 'the pin is read off data-pin-toolbar, as the other pins are')
})

test('highlight.ts\'s block list -- what dims and what counts as a hit -- now includes .qc-post', () => {
  const ts_ = readFileSync(here + '../src/fluid/search-in/highlight.ts', 'utf8')
  const line = ts_.split('\n').find((l) => l.includes('const BLOCKS ='))
  assert.ok(line.includes('.qc-post'), 'highlight.ts:BLOCKS must include .qc-post for Quiet\'s posts to count')
  assert.ok(line.includes('.fx-post'), 'the edit must not drop Fluid\'s own existing block')
})

test('search.css dims a Quiet post left out of the match, scoped to #qc-stream', () => {
  const css = readFileSync(here + '../src/quiet/search/search.css', 'utf8')
  assert.ok(/#qc-stream\[data-fs-on\]\s+\.qc-post:not\(\[data-fs-hit\]\):not\(\[data-fs-near\]\)/.test(css))
})
