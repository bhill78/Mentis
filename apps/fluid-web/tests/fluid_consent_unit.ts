/* Run consent in Fluid (docs/run-consent.md §1-3, §6): the dispatch spec
 * carries `consent` only when chosen, categories only when the owner added
 * optional ones; the chip and a run's line say it in few words, apart from
 * Task Gravity; a permission form's `operation` reaches its drawn group. */
import assert from 'node:assert/strict'
import { bodyOf, emptyDraft, type Addressee } from '../src/composer/draft'
import { tokenOf } from '../src/fluid/composer/words'
import { runLine } from '../src/fluid/runs/gravity'
import { consentLine, notAbsolute, workspacesOf } from '../src/fluid/runs/consent'
import { groupsOf, type Ask, type Read } from '../src/experimental/decisions'

const MARS = String.raw`C:\Work\MARS`
const WT = String.raw`C:\Work\MARS-wt`
const who: Addressee = { participant: 'p1', alias: '@Orbit', dispatch: true }
const spec = (a: Addressee) => bodyOf({ ...emptyDraft(), text: 'go', to: [a] }, 'p-me', []).dispatch[0] as Record<string, unknown>

// asking is the default and sends nothing
assert.equal('consent' in spec(who), false)
// routine work: the workspaces, no categories while only the routine ones are implied
assert.deepEqual(spec({ ...who, consent: { mode: 'task', workspaces: [MARS] } }).consent, { mode: 'task', workspaces: [MARS] })
// an optional category added: the whole list, in order
assert.deepEqual(spec({ ...who, consent: { mode: 'task', workspaces: [MARS], extra: ['install', 'delete'] } }).consent,
  { mode: 'task', workspaces: [MARS], categories: ['read', 'edit', 'test', 'build', 'run', 'git', 'delete', 'install'] })
// never wait: no categories to say
assert.deepEqual(spec({ ...who, consent: { mode: 'deny', workspaces: [], extra: ['network'] } }).consent, { mode: 'deny', workspaces: [] })
// Task Gravity is its own field, untouched by consent
assert.deepEqual(spec({ ...who, followUp: 1, consent: { mode: 'task', workspaces: [] } }).follow_up, { depth: 1 })
// record-only dispatches nothing, consent included
assert.deepEqual(bodyOf({ ...emptyDraft(), text: 'x', action: 'record-only', to: [{ ...who, consent: { mode: 'task', workspaces: [] } }] }, 'p-me', []).dispatch, [])

// the chip: said only when chosen, after side work
assert.equal(tokenOf({ ...who, runtime: 'claude' }, []), 'claude · asks before side work')
assert.equal(tokenOf({ ...who, runtime: 'claude', consent: { mode: 'task', workspaces: [] } }, []), 'claude · asks before side work · routine work proceeds')
assert.equal(tokenOf({ ...who, runtime: 'claude', consent: { mode: 'deny', workspaces: [] } }, []), 'claude · asks before side work · never waits')

// a run's line: consent last, nothing for ask or an older server
assert.equal(runLine({ participant_name: 'Orbit', runtime: 'codex', follow_up: 'ask', consent: { mode: 'task' } }),
  'Orbit · codex · Asks before pursuing side work · routine work proceeds')
assert.equal(runLine({ participant_name: 'Orbit', runtime: 'codex', follow_up: 'ask', consent: { mode: 'ask' } }), 'Orbit · codex · Asks before pursuing side work')
assert.equal(runLine({ participant_name: 'Orbit', runtime: 'codex', follow_up: 'ask' }), 'Orbit · codex · Asks before pursuing side work')

// the panel's line
assert.equal(consentLine({ mode: 'task', label: 'Routine work in the approved workspaces proceeds', workspaces: [MARS, WT] }),
  'Routine work in the approved workspaces proceeds · 2 workspaces')
assert.equal(consentLine({ mode: 'ask', workspaces: [MARS] }), 'Each operation is asked')

// workspaces as typed: one per line or comma-separated; only absolute directories pass
assert.deepEqual(workspacesOf(`${MARS}\n\n ${WT} , /c/x`), [MARS, WT, '/c/x'])
assert.deepEqual(notAbsolute([MARS, String.raw`Work\MARS`, '/c/x', 'd:/y']), [String.raw`Work\MARS`])

// a permission form's operation reaches the group; a form without one, and an ask on its own post, carry null
const ask = (id: string, form?: string): Ask => ({ id, expects: 'decision', of: 'p-me', by_alias: '@Orbit', response_present: false, form })
const operation = { summary: String.raw`Edit examples\run_turn.py with PowerShell`, category: 'edit', within: false, outside: ['writes outside the approved workspaces'], command: 'Set-Content ...' }
const r: Read = {
  post: { id: 't1', number: 4, author: 'p-orbit', author_alias: '@Orbit', topics: [], conversation: 'c1' },
  you: 'p-me',
  expectations: [ask('e1', 'f1'), ask('e2', 'f2'), ask('e3')],
  decision_forms: [
    { form: 'f1', post: 't1', pending: true, conversation: 'c1', asked_by: 'p-orbit', questions: [{ expectation: 'e1' }], operation },
    { form: 'f2', post: 't1', pending: true, conversation: 'c1', asked_by: 'p-orbit', questions: [{ expectation: 'e2' }] },
  ],
}
assert.deepEqual(groupsOf(r).map((x) => [x.key, x.operation]), [['e3', null], ['f1', operation], ['f2', null]])

console.log('fluid consent: ok')
