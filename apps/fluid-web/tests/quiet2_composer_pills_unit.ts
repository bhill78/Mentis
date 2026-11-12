/* Quiet Chat Mark 2's composer pills (Workstream U): each addressee's pill
 * opens THAT participant's Operations; two addressees keep independent
 * settings, and removing one leaves the other's intact; non-default
 * Authority / Permission / Execution are said on the pill; the round-3
 * summary is gone and Alt+O keeps its rule; the Model pull-out says what local
 * discovery reported (state, tools, refused, a partial list) and still stores
 * the exact slug. */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { bodyOf, emptyDraft, type Addressee, type Draft } from '../src/composer/draft'
import { modelFacts, partialNotice } from '../src/composer/execution'
import { altTargetOf, withAddressee, withoutAddressee } from '../src/fluid/composer/choose'
import { pillWarnings } from '../src/fluid/composer/Operations'

const src = (p: string) => readFileSync(new URL('../src/' + p, import.meta.url), 'utf8')

const caretaker: Addressee = { participant: 'ent-care', alias: '@Caretaker', dispatch: true }
const builder: Addressee = { participant: 'ent-build', alias: '@Builder', dispatch: true }
const two: Draft = { ...emptyDraft(), text: 'hi @Caretaker @Builder', to: [caretaker, builder] }

/* -- independent per-participant settings -------------------------------- */
let d = withAddressee(two, { ...caretaker, runtime: 'claude', model: 'claude-opus-4-1', persona: 'ent-persona-a', coordinate: true,
  consent: { mode: 'task', workspaces: [] }, executionMode: 'sandboxed' })
d = withAddressee(d, { ...builder, runtime: 'codex', persona: 'none', consent: { mode: 'deny', workspaces: ['C:\\Work\\x'] } })
const [c1, b1] = d.to
assert.equal(c1.runtime, 'claude'); assert.equal(c1.model, 'claude-opus-4-1'); assert.equal(c1.persona, 'ent-persona-a')
assert.equal(c1.coordinate, true); assert.equal(c1.consent?.mode, 'task'); assert.equal(c1.executionMode, 'sandboxed')
assert.equal(b1.runtime, 'codex'); assert.equal(b1.model, undefined); assert.equal(b1.persona, 'none')
assert.equal(b1.coordinate, undefined); assert.equal(b1.consent?.mode, 'deny'); assert.equal(b1.executionMode, undefined)
assert.deepEqual(d.to.map((a) => a.participant), ['ent-care', 'ent-build'], 'order kept')
/* survives the draft's own persistence shape (drafts.ts stores JSON) */
assert.deepEqual(JSON.parse(JSON.stringify(d)).to, d.to)
/* and each goes to the server as its own dispatch spec */
const body = bodyOf(d, 'ent-me', d.topics, 'ask-mentis') as unknown as { dispatch?: Array<Record<string, unknown>> }
assert.ok(Array.isArray(body.dispatch) && body.dispatch.length === 2, 'two dispatch specs')
assert.equal(body.dispatch![0].runtime, 'claude'); assert.equal(body.dispatch![1].runtime, 'codex')

/* -- removing one leaves the other's settings intact ----------------------- */
const r = withoutAddressee(d, 'ent-care')
assert.deepEqual(r.to, [b1], 'only @Builder, exactly as it was')
assert.equal(r.text, d.text, 'the words are not edited by removing a pill')
assert.deepEqual(withoutAddressee(d, 'ent-build').to, [c1])

/* -- Alt+O's target: last opened, else first asked to work, else first ------ */
assert.equal(altTargetOf(d.to, 'ent-build')?.participant, 'ent-build')
assert.equal(altTargetOf(d.to, null)?.participant, 'ent-care')
assert.equal(altTargetOf([{ ...caretaker, dispatch: false }, builder], null)?.participant, 'ent-build')
assert.equal(altTargetOf([{ ...caretaker, dispatch: false }], 'gone')?.participant, 'ent-care')
assert.equal(altTargetOf([], null), undefined)

/* -- warnings on the pill ----------------------------------------------------- */
assert.deepEqual(pillWarnings(caretaker), [], 'defaults say nothing')
assert.deepEqual(pillWarnings({ ...caretaker, runtime: 'codex', model: 'x', persona: 'p' }), [], 'runtime/model/Persona are not warnings')
assert.deepEqual(pillWarnings(c1), ['coordinates', 'routine', 'sandboxed'])
assert.deepEqual(pillWarnings({ ...builder, consent: { mode: 'all', workspaces: [] } }), ['allow all'])
assert.deepEqual(pillWarnings({ ...builder, coordinate: true, dispatch: false }), [], 'addressed only: nothing runs')
/* an unaccepted Unrestricted Host is not carried, so not said */
assert.deepEqual(pillWarnings({ ...builder, executionMode: 'unrestricted-host' }), [])

/* -- the composer: pills on the right open THAT participant's Operations ---- */
const composer = src('fluid/Composer.tsx')
assert.ok(!/fc-sum|operationsSummary/.test(composer), 'the round-3 summary is gone')
assert.match(composer, /className="fc-pills"/)
assert.match(composer, /onClick=\{\(\) => openOps\(a\.participant\)\}/, 'a pill opens its own participant')
assert.match(composer, /const who = opened \? draft\.to\.find\(\(a\) => a\.participant === opened\)/, 'Operations is for whoever was opened')
assert.match(composer, /<Operations key=\{who\.participant\} who=\{who\}/)
assert.match(composer, /aria-label=\{`remove \$\{a\.alias\}`\}[\s\S]{0,200}onClick=\{\(\) => unaddress\(a\.participant\)\}/, 'a separate remove target per pill')
assert.match(composer, /onClose=\{\(\) => closeOps\('escape'\)\}/, 'closing returns focus to the pill')
const css = src('fluid/composer/operations.css')
assert.match(css, /\.fx-composer \.fc-pills \{[^}]*margin-left: auto/, 'pills sit on the right of the line')
assert.ok(!/\.fc-sum\b/.test(css))

/* -- the Model pull-out: what discovery reported ------------------------------ */
assert.deepEqual(modelFacts({}), { notes: [], dim: false }, 'an older server says nothing')
assert.deepEqual(modelFacts({ state: 'unknown', tools: 'unknown', status: 'listed' }), { notes: [], dim: false })
assert.deepEqual(modelFacts({ state: 'loaded' }), { notes: ['loaded'], dim: false })
assert.deepEqual(modelFacts({ state: 'installed', tools: 'unsupported' }), { notes: ['installed', "can't use tools"], dim: false })
assert.deepEqual(modelFacts({ state: 'unavailable' }), { notes: ['unavailable'], dim: true })
assert.deepEqual(modelFacts({ status: 'refused', status_why: 'context window too small' }), { notes: ['refused: context window too small'], dim: true })
assert.deepEqual(modelFacts({ status: 'refused' }), { notes: ['refused'], dim: true })
assert.equal(partialNotice({}), null)
assert.equal(partialNotice({ models_partial_why: null }), null)
assert.equal(partialNotice({ models_partial_why: 'LM Studio not reachable' }), 'LM Studio not reachable — list may be incomplete')
assert.equal(partialNotice({ models_partial_why: 'list may be incomplete: Ollama timed out' }), 'list may be incomplete: Ollama timed out')
const ops = src('fluid/composer/Operations.tsx')
assert.match(ops, /pick: \(\) => choose\(\{ \.\.\.who, model: m\.slug, effort: undefined \}\)/, 'choosing stores the exact slug')
assert.match(ops, /key: m\.slug, name: m\.slug/, 'the exact id is the name shown')

console.log('quiet2 composer pills: ok')
