/* THE SEAM ITSELF, checked without a browser.
 *
 * P0 hands nine other packages a module each and freezes everything around
 * them. Two things have to stay true for that to mean anything:
 *
 *  - EVERY ENTRY EXISTS AND STILL EXPORTS WHAT IT DECLARES. contract.ts's
 *    ENTRIES is the list; a package that renames its component, drops a named
 *    export or moves its file fails here rather than at integration, when
 *    nine branches are already written against it.
 *  - api.ts DECLARES THE RUN SHAPE THE SERVER SENDS. The keys are compared
 *    against the response recorded in tests/quiet_activity_run.json, which
 *    tests/test_quiet_seam_browser.py re-checks against a live read -- so
 *    neither side can drift quietly.
 */
import { registerHooks } from 'node:module'
import { readFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import assert from 'node:assert/strict'
import test from 'node:test'
import ts from '../node_modules/typescript/lib/typescript.js'

/* The same TS loader as the other client unit suites, plus stylesheets: the
   entry modules import their own CSS, which node cannot read and which this
   suite is not about. */
registerHooks({
  resolve(specifier, context, next) {
    if (specifier.startsWith('.')) {
      if (/\.css$/.test(specifier)) {
        return { url: new URL(specifier, context.parentURL).href, shortCircuit: true }
      }
      for (const suffix of ['', '.ts', '.tsx', '/index.ts', '/index.tsx']) {
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

const here = fileURLToPath(new URL('.', import.meta.url))
const { ENTRIES } = await import('../src/quiet/contract.ts')

test('every package has an entry module, and nobody owns two of the same', () => {
  assert.ok(ENTRIES.length >= 13, 'the seam lists fewer modules than P0 mounts')
  const paths = ENTRIES.map((e) => e.path)
  assert.deepEqual(paths, [...new Set(paths)])
  // Each of the seven packages that mounts a component has at least one.
  for (const owner of ['A', 'B', 'C', 'D', 'E', 'F', 'G'])
    assert.ok(ENTRIES.some((e) => e.package === owner), `package ${owner} mounts nothing`)
})

test('each entry imports, and exports what the contract declares', async () => {
  for (const entry of ENTRIES) {
    const module = await import('../src/quiet/' + entry.path.replace(/^\.\//, ''))
    for (const name of entry.exports) {
      assert.equal(typeof module[name], 'function',
        `${entry.path} (package ${entry.package}) does not export ${name} as a function`)
    }
  }
})

/* -- the run shape api.ts declares, against the one recorded ---------------- */

/** The property names a TypeScript interface declares, read off the source --
 *  one level only, which is all this comparison is about. */
function keysOf(source, name) {
  const open = source.indexOf(`export interface ${name} {`)
  assert.notEqual(open, -1, `api.ts no longer declares ${name}`)
  let depth = 0
  let end = open
  for (let i = source.indexOf('{', open); i < source.length; i++) {
    if (source[i] === '{') depth++
    else if (source[i] === '}' && --depth === 0) { end = i; break }
  }
  const body = source.slice(source.indexOf('{', open) + 1, end)
  const keys = []
  let nested = 0
  for (const line of body.split('\n')) {
    const bare = line.replace(/\/\*.*?\*\//g, '').replace(/\/\/.*$/, '')
    const found = nested === 0 && bare.match(/^\s*([A-Za-z_]\w*)\??\s*:/)
    if (found) keys.push(found[1])
    nested += (bare.match(/[{(]/g) ?? []).length - (bare.match(/[})]/g) ?? []).length
  }
  return keys.sort()
}

test('api.ts declares exactly the run keys /api/activity was recorded sending', () => {
  const recorded = JSON.parse(readFileSync(here + '../../../tests/quiet_activity_run.json', 'utf8'))
  const declared = keysOf(readFileSync(here + '../src/api.ts', 'utf8'), 'ActivityRun')
  assert.deepEqual(declared, recorded.keys,
    'api.ts and the recorded /api/activity run rows disagree about the run shape')
})
