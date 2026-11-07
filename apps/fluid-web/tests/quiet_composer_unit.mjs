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

/* The participant filter's own record, which has to work without a browser:
   a tiny store for what `localStorage` would hold, so persistence is checked
   rather than assumed. Set before the module is loaded, as a page's is. */
const storage = new Map()
globalThis.localStorage = {
  getItem: (k) => (storage.has(k) ? storage.get(k) : null),
  setItem: (k, v) => storage.set(k, String(v)),
  removeItem: (k) => storage.delete(k),
}

const { dispatchBody, draftBody } = await import('../src/quiet/composer/Composer.tsx')
const { postingBody } = await import('../src/quiet/model.ts')
const { bodyOf, emptyDraft } = await import('../src/composer/draft.ts')
const { retexted } = await import('../src/fluid/composer/choose.ts')
const { dropToken } = await import('../src/fluid/composer/workflows.ts')
const { triggerAt } = await import('../src/composer/trigger.ts')
const { clearWhoFilters, filterTurns, setWhoFilter, whoFilter } = await import('../src/quiet/filter/who.ts')

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

test('dropping the / token moves an earlier reference mark with the characters', () => {
  // The review of ddca038 found this: the token went, the characters after it
  // moved left, and a mark left at its old offset no longer described them --
  // so the authored reference was posted as prose. `retexted` is the one rule
  // both composers now drop a token by (fluid/composer/choose.ts).
  const text = '/Independent and #Thermal drift '
  const out = dropToken(text, triggerAt(text, 12))
  assert.equal(out.text, 'and #Thermal drift ')
  const marks = [{ topic: 'ent-topic', text: '#Thermal drift', start: 17 }]
  const moved = retexted({ text, action: 'record-only', op: 'o', to: [], topics: ['ent-topic'], marks }, out.text)
  assert.deepEqual(moved.marks, [{ topic: 'ent-topic', text: '#Thermal drift', start: 4 }])
  const body = draftBody(moved, 'ent-owner', 'ent-c', null, null, 'op-slash')
  assert.deepEqual(body.parts, [
    { type: 'text', text: 'and ' },
    { type: 'topic', ref: 'ent-topic', text: '#Thermal drift' },
  ])
  assert.deepEqual(body.topics, ['ent-topic'])
  // Without the shift the mark describes nothing, and `partsOf` drops it: the
  // reference becomes plain text, which is exactly what was reported.
  const left = draftBody({ text: out.text, action: 'record-only', op: 'o', topics: ['ent-topic'], marks },
    'ent-owner', 'ent-c', null, null, 'op-slash-was')
  assert.deepEqual(left.parts, [{ type: 'text', text: 'and #Thermal drift' }])
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

/* -- THE PARTICIPANT FILTER'S READING (src/quiet/filter/who.ts) -------------
 *
 * The strip's own at-rest/expanded rule is measured in a browser
 * (tests/test_quiet_r4_composer_browser.py); what it MEANS -- who is left,
 * what "everyone" is, and what survives a reload -- is exact here, because it
 * is pure and needs no DOM to be right.
 */

const turns = [
  { id: 'ent-1', author: 'ent-brian' },
  { id: 'ent-2', author: 'ent-vera' },
  { id: 'ent-3', author: 'ent-brian' },
  { id: 'ent-4', author: 'ent-quill' },
]
const everyone = ['ent-brian', 'ent-vera', 'ent-quill']

test('an empty filter is no filter: the same list, not a copy of it', () => {
  // Identity, deliberately: "everyone" and "unfiltered" are not two readings,
  // so a reader must not be able to tell them apart.
  assert.equal(filterTurns(turns, []), turns)
})

test('a filter leaves the chosen authors\' posts and hides the rest', () => {
  assert.deepEqual(filterTurns(turns, ['ent-brian']).map((t) => t.id), ['ent-1', 'ent-3'])
  assert.deepEqual(filterTurns(turns, ['ent-vera', 'ent-quill']).map((t) => t.id), ['ent-2', 'ent-4'])
  // By the AUTHOR alone: nothing here reads a post's prose, addressees or topics.
  assert.deepEqual(filterTurns(turns, ['ent-nobody']), [])
})

test('choosing everybody there is reduces to the one way of saying "everyone"', () => {
  clearWhoFilters()
  setWhoFilter('ent-c1', everyone, everyone)
  assert.deepEqual(whoFilter('ent-c1'), [])
  // And so does choosing nobody.
  setWhoFilter('ent-c1', ['ent-vera'], everyone)
  setWhoFilter('ent-c1', [], everyone)
  assert.deepEqual(whoFilter('ent-c1'), [])
})

test('a filter is kept per conversation, and remembered for the next sitting', () => {
  clearWhoFilters()
  setWhoFilter('ent-c1', ['ent-vera'], everyone)
  setWhoFilter('ent-c2', ['ent-quill'], everyone)
  assert.deepEqual(whoFilter('ent-c1'), ['ent-vera'])
  assert.deepEqual(whoFilter('ent-c2'), ['ent-quill'])
  // What a reload sees: the store forgotten, the storage kept.
  assert.deepEqual(JSON.parse(storage.get('mentis:quiet:who:ent-c1')), ['ent-vera'])
  const fresh = new Map(storage)
  clearWhoFilters()
  for (const [k, v] of fresh) storage.set(k, v)
  assert.deepEqual(whoFilter('ent-c1'), ['ent-vera'])
  // Everyone is stored as nothing at all, never as a list of every name.
  setWhoFilter('ent-c1', [], everyone)
  assert.equal(storage.has('mentis:quiet:who:ent-c1'), false)
})

test('storage holding something that is not a list of names is ignored, not thrown', () => {
  clearWhoFilters()
  storage.set('mentis:quiet:who:ent-c9', '{"not":"a list"}')
  assert.deepEqual(whoFilter('ent-c9'), [])
  clearWhoFilters()
  storage.set('mentis:quiet:who:ent-c9', 'not json at all')
  assert.deepEqual(whoFilter('ent-c9'), [])
  clearWhoFilters()
})

console.log('quiet_composer_unit: ok')
