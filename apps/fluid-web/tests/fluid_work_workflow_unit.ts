/* The Work drawer's Workflow section, as words (src/work/workflow.ts): how the
 * current Workflow came to govern the work, each history entry, the activity
 * progress, and the body the owner's change sends -- refused before sending
 * when it lacks a Workflow, a reason or evidence. */
import assert from 'node:assert/strict'
import { activityWords, changeBody, changePath, eventWords, evidenceWords, originWords, parseEvidence } from '../src/work/workflow'
import type { WorkflowView } from '../src/work/contract'

const R = { entry: 'ent-aaaaaaaaaaaa', name: 'Research' }
const B = { entry: 'ent-bbbbbbbbbbbb', name: 'Bug repair' }
const view = (over: Partial<WorkflowView>): WorkflowView => ({
  current: [R], origin: 'named', progress: [], progress_source: 'computed',
  history: [{ kind: 'asked', at: 1, by: 'p', by_alias: '@brian', workflows: [R], from: 'named', continues: null }],
  ...over,
})

// origin, in words
assert.equal(originWords(view({})), 'named when the work was asked')
assert.equal(originWords(view({ origin: 'continued' })), 'carried from the request this continues')
assert.equal(originWords(view({ origin: 'placed' })), 'placed where the work runs; not named for it')
assert.equal(originWords(view({ origin: 'none', current: [] })), 'no Workflow governs this work')
const changed = view({
  current: [B], origin: 'changed',
  history: [view({}).history[0], { kind: 'changed', act: 'opr-1', at: 2, by: 'p2', by_alias: 'Steward', role: 'carrier',
    because: 'a defect', from: [R], to: [B], evidence: [{ ref: 'ent-cccccccccccc', number: 12 }], runtime: 'claude', execution: 'x' }],
})
assert.equal(originWords(changed), 'changed by @Steward (carrier)')
assert.equal(originWords(view({ origin: 'unknown', why_unknown: 'unreadable' })), 'unreadable')

// history lines
assert.equal(eventWords(changed.history[0]), 'Asked with Research · named')
assert.equal(eventWords(changed.history[1]), 'Research → Bug repair · by @Steward (carrier)')
assert.equal(eventWords({ kind: 'asked', at: 1, by: null, by_alias: null, workflows: [], from: null, continues: null }),
  'Asked · asked with no Workflow named')
assert.equal(eventWords({ kind: 'asked', at: 1, by: null, by_alias: null, workflows: [R], from: 'continued', continues: 'opr-x' }),
  'Asked with Research · carried from the request it continues')
assert.equal(evidenceWords({ ref: 'ent-cccccccccccc', number: 12 }), '#12')
assert.equal(evidenceWords({ ref: 'opr-dddddddddddd', number: 3, act: 'result-returned' }), '#3 (result-returned)')
assert.equal(evidenceWords({ ref: 'opr-dddddddddddd', number: null }), 'opr-dddddddddddd')

// activity progress
assert.equal(activityWords([], 'nothing delegated for it'), 'nothing delegated for it')
assert.equal(activityWords([{ state: 'running' }, { state: 'returned' }, { state: 'returned' }], null), '1 running · 2 returned')

// evidence parsing and the body
assert.deepEqual(parseEvidence('#ent-cccccccccccc, opr-dddddddddddd ent-cccccccccccc'),
  { refs: ['ent-cccccccccccc', 'opr-dddddddddddd'], bad: [] })
assert.deepEqual(parseEvidence('see #12'), { refs: [], bad: ['see', '#12'] })
assert.deepEqual(changeBody('', 'x', 'ent-cccccccccccc', 'k'), { why: 'choose the Workflow to change to' })
assert.deepEqual(changeBody(B.entry, '  ', 'ent-cccccccccccc', 'k'), { why: 'say why the Workflow changes' })
assert.deepEqual(changeBody(B.entry, 'x', '', 'k'), { why: 'cite at least one finding, result, decision or post' })
assert.match((changeBody(B.entry, 'x', 'post 12', 'k') as { why: string }).why, /not a reference/)
assert.deepEqual(changeBody(B.entry, ' a defect ', 'ent-cccccccccccc', 'k'),
  { body: { workflow: B.entry, because: 'a defect', evidence: ['ent-cccccccccccc'], op: 'k' } })
assert.equal(changePath('opr-a/b'), '/fluid/api/work/opr-a%2Fb/workflow')
console.log('ok')
