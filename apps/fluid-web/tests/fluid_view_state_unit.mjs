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
    if (/\.tsx?$/.test(url)) return {
      format: 'module', shortCircuit: true,
      source: ts.transpileModule(readFileSync(fileURLToPath(url), 'utf8'), {
        compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
      }).outputText,
    }
    return next(url, context)
  },
})

class MemoryStorage {
  values = new Map()
  getItem(key) { return this.values.get(key) ?? null }
  setItem(key, value) { this.values.set(key, String(value)) }
  removeItem(key) { this.values.delete(key) }
}
globalThis.localStorage = new MemoryStorage()
globalThis.sessionStorage = new MemoryStorage()

const { workspace } = await import('../src/fluid/workspace/place.ts')
const { VIEW_RESOURCES, forgetSurface, setViewState, viewState } = await import('../src/fluid/surface/viewState.ts')

let checks = 0
function same(actual, expected, label) {
  checks++
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    throw new Error(`${label}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`)
  }
}

workspace.key = 'view-state-test'

// Present: the zone id is the surface identity, so docking or floating it
// leaves the current item and each resource's fold state under the same keys.
const present = { surface: 'surface-a', resource: 'present' }
const object = { surface: 'surface-a', resource: 'live:post-1:chart' }
setViewState(present, 'current', object.resource)
setViewState(object, 'fold', false)
same(viewState(present, 'current'), object.resource, 'Present current item survives placement change')
same(viewState(object, 'fold'), false, 'Present fold survives placement change')

// Grouped: a remounted component reads the four parts back from the store.
const grouped = { surface: 'surface-grouped', resource: 'grouped' }
setViewState(grouped, 'focus', 'post-1')
setViewState(grouped, 'open', 'post-2')
setViewState(grouped, 'cur', { 'post-2': 'live:post-2:table' })
setViewState(grouped, 'all', { 'post-2': true })
same(viewState(grouped, 'focus'), 'post-1', 'Grouped focus survives remount')
same(viewState(grouped, 'open'), 'post-2', 'Grouped open row survives remount')
same(viewState(grouped, 'cur'), { 'post-2': 'live:post-2:table' }, 'Grouped current objects survive remount')
same(viewState(grouped, 'all'), { 'post-2': true }, 'Grouped show-all survives remount')

// FormDialog: its draft resource is independent of the saved-form library.
const form = { surface: 'form-draft', resource: 'conversation-1:root' }
const fields = [{ id: 'field_1', label: 'Still here', type: 'text', options: '', required: true }]
setViewState(form, 'title', 'Half-built form')
setViewState(form, 'fields', fields)
same(viewState(form, 'title'), 'Half-built form', 'Form title survives remount')
same(viewState(form, 'fields'), fields, 'Form fields survive remount')

// Local Close does not touch the store. Remove from workspace is the one
// operation that calls forgetSurface and clears every resource on it.
same(viewState(object, 'fold'), false, 'local Close preserves view state')
forgetSurface('surface-a')
same(viewState(object, 'fold'), undefined, 'Remove forgets resource state')
same(viewState(present, 'current'), undefined, 'Remove forgets surface current state')

// A state update refreshes recency. The ninth distinct resource evicts the
// least-recently-used one, retaining exactly eight.
for (let i = 0; i < VIEW_RESOURCES; i++) setViewState({ surface: 'lru', resource: `r${i}` }, 'scroll', i)
setViewState({ surface: 'lru', resource: 'r0' }, 'scroll', 0)
setViewState({ surface: 'lru', resource: 'r8' }, 'scroll', 8)
same(viewState({ surface: 'lru', resource: 'r0' }, 'scroll'), 0, 'recent resource retained')
same(viewState({ surface: 'lru', resource: 'r1' }, 'scroll'), undefined, 'least-recent resource evicted')

// Each place has a separate sessionStorage mirror, restored when revisited.
const placeKey = { surface: 'shared-zone', resource: 'resource' }
setViewState(placeKey, 'tab', 'place-a')
workspace.key = 'other-place'
same(viewState(placeKey, 'tab'), undefined, 'other place starts separately')
setViewState(placeKey, 'tab', 'place-b')
workspace.key = 'view-state-test'
same(viewState(placeKey, 'tab'), 'place-a', 'first place restores its session state')

console.log(`fluid view state: ${checks} checks passed`)
