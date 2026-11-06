import { registerHooks } from 'node:module'
import { readFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import assert from 'node:assert/strict'
import test from 'node:test'
import ts from '../node_modules/typescript/lib/typescript.js'

/* The same TS loader as the other client unit suites, plus stylesheets:
 * ActivityPanel.tsx imports its own CSS, which node cannot read and which
 * this suite is not about (quiet_seam_unit.mjs's own pattern). RunRowView is
 * drawn with react-dom/server for the rendered-markup checks below, which
 * asks every external store for a server snapshot; fluid_magnet_frame_unit's
 * own shim stands the client snapshot in for it (useRunFeed has none). */
const SES = /import \{([^}]*)\buseSyncExternalStore\b([^}]*)\} from 'react'/
const ssr = (out) => SES.test(out)
  ? out.replace(SES, "import {$1useSyncExternalStore as __uSES$2} from 'react'") + '\nfunction useSyncExternalStore(s, g, h) { return __uSES(s, g, h ?? g) }\n'
  : out
registerHooks({
  resolve(specifier, context, next) {
    if (specifier.startsWith('.')) {
      if (/\.css$/.test(specifier)) {
        return { url: new URL(specifier, context.parentURL).href, shortCircuit: true }
      }
      for (const suffix of ['.ts', '.tsx', '/index.ts']) {
        const url = new URL(specifier + suffix, context.parentURL)
        if (existsSync(fileURLToPath(url))) return { url: url.href, shortCircuit: true }
      }
    }
    return next(specifier, context)
  },
  load(url, context, next) {
    if (/\.css$/.test(url)) return { format: 'module', shortCircuit: true, source: 'export {}' }
    if (/\.tsx?$/.test(url)) return {
      format: 'module', shortCircuit: true,
      source: ssr(ts.transpileModule(readFileSync(fileURLToPath(url), 'utf8'), {
        compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
      }).outputText),
    }
    return next(url, context)
  },
})

const { groupActivity, contextWindowFor, RunRowView } = await import('../src/quiet/activity/ActivityPanel.tsx')
const { postingBody } = await import('../src/quiet/model.ts')
const { createElement } = await import('react')
const { renderToStaticMarkup } = await import('react-dom/server')

const entryHere = {
  participant: 'ent-care', alias: 'Caretaker', has_live_execution: true,
  conversation: 'ent-c', conversations: ['ent-c'], scope: 'conversation',
  working_on: null, working_on_gap: null,
  runs: [{ run: 'ent-run-1', state: 'running', words: 'Working', held_here: true,
           activity: 'Reading AGENTS.md', stopping: false, permission: null, permissions: [],
           conversation: 'ent-c', turn: null, live: true, working_on: null }],
}
const entryFallback = {
  // no `conversation` of its own -- an older style of row -- but its one
  // run's `working_on.conversation` still says where it is.
  participant: 'ent-steward', alias: 'Steward', has_live_execution: true,
  conversation: null, conversations: [], scope: null,
  working_on: null, working_on_gap: null,
  runs: [{ run: 'ent-run-2', state: 'running', words: 'Working', held_here: true,
           activity: 'Writing', stopping: false, permission: null, permissions: [],
           conversation: null, turn: 'ent-t', live: true,
           working_on: { turn: 'ent-t', number: 4, conversation: 'ent-c', since: null } }],
}
const entryElsewhere = {
  participant: 'ent-builder', alias: 'Builder', has_live_execution: true,
  conversation: 'ent-other', conversations: ['ent-other'], scope: 'conversation',
  working_on: null, working_on_gap: null,
  runs: [{ run: 'ent-run-3', state: 'running', words: 'Working', held_here: true,
           activity: 'Running tests', stopping: true, permission: null, permissions: [],
           conversation: 'ent-other', turn: null, live: true, working_on: null }],
}

test('a run whose own conversation matches is grouped here, one row per run', () => {
  const { here, elsewhere } = groupActivity([entryHere, entryElsewhere], 'ent-c')
  assert.deepEqual(here.map((a) => a.run), ['ent-run-1'])
  assert.deepEqual(elsewhere.map((a) => a.run), ['ent-run-3'])
})

test('the working_on.conversation fallback is kept here, not dropped', () => {
  const { here, elsewhere } = groupActivity([entryFallback, entryElsewhere], 'ent-c')
  assert.deepEqual(here.map((a) => a.run), ['ent-run-2'])
  assert.equal(here[0].working_on.conversation, 'ent-c')
  assert.deepEqual(elsewhere.map((a) => a.run), ['ent-run-3'])
})

test('a null since on a run\'s working_on does not throw grouping off', () => {
  const { here } = groupActivity([entryFallback], 'ent-c')
  assert.equal(here[0].working_on.since, 0)
})

test('two runs of one participant in different conversations are two rows, placed separately', () => {
  const two = {
    ...entryHere,
    runs: [
      { ...entryHere.runs[0], run: 'ent-run-a', conversation: 'ent-c' },
      { ...entryHere.runs[0], run: 'ent-run-b', conversation: 'ent-other' },
    ],
  }
  const { here, elsewhere } = groupActivity([two], 'ent-c')
  assert.deepEqual(here.map((a) => a.run), ['ent-run-a'])
  assert.deepEqual(elsewhere.map((a) => a.run), ['ent-run-b'])
})

test('nothing live anywhere groups to two empty lists, not an error', () => {
  assert.deepEqual(groupActivity(null, 'ent-c'), { here: [], elsewhere: [] })
  assert.deepEqual(groupActivity([], 'ent-c'), { here: [], elsewhere: [] })
})

const exec = {
  runtimes: [{ kind: 'claude', present: true, version: '1', capabilities: [], notes: [],
    models: [{ slug: 'claude-sonnet-5', name: 'Sonnet 5', efforts: [], default_effort: null,
               locality: 'hosted', provider: null, context_window: 200000, aliases: ['sonnet'] }] }],
}

/* -- the closed row's own markup and CSS: the narrow collision, the caret --
 *
 * ent-5983e32736b4 found a closed row's name running into its activity text
 * at narrow widths (the shared `.qc button` rule turns the disclosure
 * button into a flex row), and no visible cue that a closed row discloses.
 * Rendered through the real component, not asserted from the fix's own
 * description. */

const activityCss = readFileSync(new URL('../src/quiet/activity/activity.css', import.meta.url), 'utf8')

/** `live()`'s own output shape (fluid/identity/activity.ts): a flattened
 *  `run`, and `runs: [r]` -- what `RunRowView` actually reads. */
const liveRow = {
  participant: 'ent-care', alias: 'Caretaker', has_live_execution: true,
  conversation: 'ent-c', working_on: null, working_on_gap: null, run: 'ent-run-1',
  runs: [{ run: 'ent-run-1', state: 'running', words: 'Working', held_here: true,
           activity: 'Reading AGENTS.md', stopping: false, permission: null, permissions: [],
           conversation: 'ent-c', turn: null, live: true, working_on: null }],
}

const renderRow = () => renderToStaticMarkup(createElement(RunRowView, {
  a: liveRow, run: 'ent-run-1', working: undefined, contextWindow: null,
  conversation: 'ent-c', topic: null,
}))

test('the disclosure button sets its own flex-direction, so the shared narrow-screen button rule cannot collapse name and activity onto one flex line', () => {
  const start = activityCss.indexOf('.qc-run-disclosure {')
  const rule = activityCss.slice(start, activityCss.indexOf('}', start))
  assert.ok(/flex-direction:\s*column/.test(rule), '.qc-run-disclosure declares its own flex-direction: column')
})

test('a closed row renders the agent name and its activity as separate elements, not run together', () => {
  const html = renderRow()
  assert.ok(html.includes('<strong>Caretaker</strong>'), 'the alias renders in its own element')
  assert.ok(/<span class="qc-run-activity">Reading AGENTS\.md<\/span>/.test(html),
    'the activity renders in its own element, separate from the name')
  assert.ok(!html.includes('CaretakerReading AGENTS.md'), 'the name and the activity text never concatenate into one run')
})

test('the disclosure button carries a visible caret that reacts to aria-expanded', () => {
  const html = renderRow()
  assert.ok(html.includes('qc-run-caret'), 'a visible caret is rendered beside the name')
  assert.ok(html.includes('aria-expanded="false"'), 'the row starts closed')
  const start = activityCss.indexOf(".qc-run-disclosure[aria-expanded='true']")
  assert.ok(start >= 0, 'activity.css reacts to the open disclosure state')
  const rule = activityCss.slice(start, activityCss.indexOf('}', start))
  assert.ok(/transform:\s*rotate/.test(rule), 'the caret rotates once the row opens, so the cue itself changes with state')
})

test('Stop stays its own control, reachable whether the row is open or closed', () => {
  const html = renderRow()
  assert.ok(/qc-run-stop\b/.test(html), 'the Stop button renders')
  const buttonOpen = html.indexOf('<button')
  const disclosureClose = html.indexOf('</button>', html.indexOf('qc-run-disclosure'))
  assert.ok(html.indexOf('qc-run-stop') > disclosureClose, 'Stop is a sibling of the disclosure button, not nested inside it')
})

test('a requested model is matched by its slug', () => {
  assert.equal(contextWindowFor(exec, 'claude-sonnet-5'), 200000)
})
test('a requested model is matched by one of its aliases', () => {
  assert.equal(contextWindowFor(exec, 'sonnet'), 200000)
})
test('a model nothing present declares is a known absence, not a guess', () => {
  assert.equal(contextWindowFor(exec, 'nothing-like-this'), null)
  assert.equal(contextWindowFor(exec, null), null)
  assert.equal(contextWindowFor(null, 'sonnet'), null)
})

test('an answer to a decision is an ordinary post that carries chose, same as model.ts always has', () => {
  const body = postingBody('Pursue all five now', 'record-only', 'ent-owner', 'ent-c', null, null, 'op',
    { expectation: 'ent-ask', option: 0, label: 'Pursue all five now' })
  assert.deepEqual(body.chose, { expectation: 'ent-ask', option: 0, label: 'Pursue all five now' })
  assert.equal(body.action, 'record-only')
})
