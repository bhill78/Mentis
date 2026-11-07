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

const { dispatchBody, draftBody } = await import('../src/quiet/composer/Composer.tsx')
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

/* -- ROUND 4: what the @ / # / / palettes land, and what the body then carries
 *
 * The palettes write `to`, `topics`, `marks` and `use` into the draft
 * (contract.ts), and `draftBody` is the one builder the composer sends. These
 * cases are the reference: Fluid's own `bodyOf` on the equivalent Fluid draft,
 * so a pick made in Quiet is the same recorded fact as the same pick in Fluid.
 */

test('an @ pick addresses the participant and asks them to work', () => {
  const to = { participant: 'ent-vera', alias: '@Vera', dispatch: true }
  const body = draftBody({ text: 'Hello @Vera', action: 'ask-mentis', op: 'o', to: [to] },
    'ent-owner', 'ent-c', null, null, 'op-to')
  assert.equal(body.action, 'ask-participant')
  assert.deepEqual(body.addressed_to, ['ent-vera'])
  assert.deepEqual(body.dispatch.map((d) => d.participant), ['ent-vera'])
})

test('a mention that was not marked for work addresses without dispatching', () => {
  // The two decisions stay apart (composer/draft.ts, `Addressee.dispatch`):
  // `@Vera` in a sentence costs no runtime unless the owner said so.
  const to = { participant: 'ent-vera', alias: '@Vera', dispatch: false }
  const body = draftBody({ text: 'Mentioning @Vera', action: 'ask-mentis', op: 'o', to: [to] },
    'ent-owner', 'ent-c', null, null, 'op-mention')
  assert.equal(body.action, 'ask-mentis')
  assert.deepEqual(body.addressed_to, ['ent-vera'])
  assert.deepEqual(body.dispatch, [])
})

test('a # pick files the post under the topic and marks the characters that name it', () => {
  const marks = [{ topic: 'ent-topic', text: '#Thermal', start: 6 }]
  const body = draftBody({ text: 'Under #Thermal drift', action: 'ask-mentis', op: 'o',
    topics: ['ent-topic'], marks }, 'ent-owner', 'ent-c', null, null, 'op-topic')
  assert.deepEqual(body.topics, ['ent-topic'])
  const want = bodyOf({ ...emptyDraft(), text: 'Under #Thermal drift', topics: ['ent-topic'], marks },
    'ent-owner', ['ent-topic'])
  assert.deepEqual(body.parts, want.parts)
  // The authored reference survives as its own part, carrying the identity.
  assert.ok(body.parts.some((p) => p.type === 'topic' && p.ref === 'ent-topic' && p.text === '#Thermal'),
    JSON.stringify(body.parts))
})

test('the topic being read is sent first, and a # pick of it is not sent twice', () => {
  const body = draftBody({ text: 'Filed', action: 'ask-mentis', op: 'o',
    topics: ['ent-read', 'ent-picked'] }, 'ent-owner', 'ent-c', 'ent-read', null, 'op-both')
  assert.deepEqual(body.topics, ['ent-read', 'ent-picked'])
})

test('a / pick names the Workflow as governed, wherever work is asked for', () => {
  const use = { governed: ['ent-workflow'], said: { 'ent-workflow': 'Software change' } }
  const asked = draftBody({ text: 'Do this', action: 'ask-mentis', op: 'o', use },
    'ent-owner', 'ent-c', null, null, 'op-use')
  assert.deepEqual(asked.governed, ['ent-workflow'])
  const to = { participant: 'ent-vera', alias: '@Vera', dispatch: true }
  const dispatched = draftBody({ text: 'Do this', action: 'ask-mentis', op: 'o', use, to: [to] },
    'ent-owner', 'ent-c', null, null, 'op-use-2')
  assert.deepEqual(dispatched.dispatch[0].governed, ['ent-workflow'])
  // Nothing is owed and nothing runs under record-only, so nothing governs it.
  const recorded = draftBody({ text: 'Just a note', action: 'record-only', op: 'o', use },
    'ent-owner', 'ent-c', null, null, 'op-use-3')
  assert.equal(recorded.governed, undefined)
  assert.deepEqual(recorded.dispatch, [])
})

test('a draft with nothing picked is postingBody\'s own body, field for field', () => {
  // The dropdown is gone and `draftBody` is now the only builder the composer
  // calls, so an ordinary Ask Mentis post has to be EXACTLY what it was.
  const plain = postingBody('Ordinary words', 'ask-mentis', 'ent-owner', 'ent-c', 'ent-topic', reply, 'op-x')
  const got = draftBody({ text: 'Ordinary words', action: 'ask-mentis', op: 'o' },
    'ent-owner', 'ent-c', 'ent-topic', reply, 'op-x')
  assert.deepEqual(got, plain)
})

test('dispatchBody is draftBody with one addressee -- the two cannot drift', () => {
  const to = { participant: 'ent-vera', alias: '@Vera', dispatch: true, runtime: 'claude' }
  assert.deepEqual(
    dispatchBody('Take this', to, 'ask-mentis', 'ent-owner', 'ent-c', 'ent-topic', reply, 'op-y'),
    draftBody({ text: 'Take this', action: 'ask-mentis', op: 'o', to: [to] },
      'ent-owner', 'ent-c', 'ent-topic', reply, 'op-y'))
})

console.log('quiet_composer_unit: ok')
