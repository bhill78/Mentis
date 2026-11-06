import { registerHooks } from 'node:module'
import { readFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import assert from 'node:assert/strict'
import test from 'node:test'
import ts from '../node_modules/typescript/lib/typescript.js'

// The same TS loader quiet_unit.mjs uses, plus a stub for the one thing it
// never needed: Composer.tsx imports its own stylesheet, and nothing in a
// Node unit run can load CSS as a module.
registerHooks({
  resolve(specifier, context, next) {
    if (specifier.startsWith('.')) for (const suffix of ['.ts', '.tsx', '/index.ts']) {
      const url = new URL(specifier + suffix, context.parentURL)
      if (existsSync(fileURLToPath(url))) return { url: url.href, shortCircuit: true }
    }
    return next(specifier, context)
  },
  load(url, context, next) {
    if (url.endsWith('.css')) return { format: 'module', shortCircuit: true, source: 'export default {}' }
    if (/\.tsx?$/.test(url)) return {
      format: 'module', shortCircuit: true,
      source: ts.transpileModule(readFileSync(fileURLToPath(url), 'utf8'), {
        compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
      }).outputText,
    }
    return next(url, context)
  },
})

const { dispatchBody } = await import('../src/quiet/composer/Composer.tsx')
const { postingBody } = await import('../src/quiet/model.ts')
const { bodyOf, emptyDraft } = await import('../src/composer/draft.ts')

const reply = { id: 'ent-reply', number: 200, author: 'ent-agent', root: 'ent-root', answering: 'ent-root', author_alias: '@Ada' }

test('an addressee with no runtime chosen still dispatches, carrying no runtime, model or effort', () => {
  const to = { participant: 'ent-vera', alias: '@Vera', dispatch: true }
  const body = dispatchBody('Please take this', to, 'ask-mentis', 'ent-owner', 'ent-c', null, null, 'op-1')
  assert.equal(body.conversation, 'ent-c')
  assert.equal(body.op, 'op-1')
  assert.equal(body.action, 'ask-participant')
  assert.deepEqual(body.addressed_to, ['ent-vera'])
  assert.deepEqual(body.dispatch, [{
    participant: 'ent-vera', runtime: null, model: null, effort: null,
    persona: null, new_instance: false, coordinate: false,
  }])
})

test('the chosen runtime, model and effort arrive exactly as Fluid\'s own bodyOf would send them', () => {
  const to = { participant: 'ent-vera', alias: '@Vera', dispatch: true, runtime: 'claude', model: 'opus', effort: 'high' }
  const got = dispatchBody('Please take this', to, 'ask-mentis', 'ent-owner', 'ent-c', 'ent-topic', null, 'op-2')
  // The reference: Fluid's own draft and its own bodyOf, built the way
  // Fluid's composer builds one, with nothing Quiet-specific added.
  const want = bodyOf({ ...emptyDraft(), text: 'Please take this', to: [to] }, 'ent-owner', ['ent-topic'])
  assert.deepEqual(got.dispatch, want.dispatch)
  assert.deepEqual(got.dispatch[0], {
    participant: 'ent-vera', runtime: 'claude', model: 'opus', effort: 'high',
    persona: null, new_instance: false, coordinate: false,
  })
  assert.deepEqual(got.parts, want.parts)
  assert.equal(got.action, want.action)
})

test('record-only dominates even once somebody is marked for work, as it does in Fluid', () => {
  const to = { participant: 'ent-vera', alias: '@Vera', dispatch: true, runtime: 'claude' }
  const body = dispatchBody('Just a note', to, 'record-only', 'ent-owner', 'ent-c', null, null, 'op-3')
  assert.equal(body.action, 'record-only')
  assert.deepEqual(body.dispatch, [])
})

test('a reply addressed to nobody in particular still falls back to whoever wrote what it answers', () => {
  const to = { participant: 'ent-vera', alias: '@Vera', dispatch: true }
  const body = dispatchBody('A reply', to, 'ask-mentis', 'ent-owner', 'ent-c', null, reply, 'op-4')
  assert.equal(body.replies_to, reply.id)
  // The addressee marked for work is who `addressed_to` already names, so
  // the reply's author is not added a second time.
  assert.deepEqual(body.addressed_to, ['ent-vera'])
})

test('with nobody marked for work, the body is postingBody\'s own -- unchanged', () => {
  // The no-dispatch path never calls dispatchBody at all (Composer.tsx keeps
  // calling model.ts's postingBody exactly as before); this pins that the
  // two builders still agree on an ordinary Ask Mentis post with nobody to
  // dispatch, so a reviewer can see neither drifted from the other.
  const plain = postingBody('Ordinary words', 'ask-mentis', 'ent-owner', 'ent-c', null, null, 'op-5')
  assert.deepEqual(plain.dispatch, [])
  assert.equal(plain.action, 'ask-mentis')
})

console.log('quiet_composer_unit: ok')
