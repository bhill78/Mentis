/* Who is working, per conversation and per run (identity/activity.ts):
 * a conversation's indicators count only runs whose own conversation is
 * that one; two runs of one persona stay two entries; the switcher's row
 * says how many and whose. */
import assert from 'node:assert/strict'
import { concerns, live, workingIn, workKey, type Activity, type ActivityRun, type Where } from '../src/fluid/identity/activity'
import { workingLine } from '../src/fluid/conversation/working'
import { workersWords } from '../src/fluid/conversation/Switcher'

const run = (id: string, conversation: string, extra: Partial<ActivityRun> = {}): ActivityRun => ({
  run: id, state: 'running', held_here: true, live: true, conversation, turn: 't-' + id,
  working_on: { turn: 't-' + id, number: 1, conversation, since: 1 }, ...extra,
})
const row = (participant: string, alias: string, runs: ActivityRun[], extra: Partial<Activity> = {}): Activity => ({
  participant, alias, has_live_execution: runs.some((r) => r.live), conversation: null,
  conversations: ['A', 'B'], scope: null, working_on: null, runs, ...extra,
})

// @Caretaker: two runs in A, one in B; @Ada: one in B; @Idle: member of A, no run.
const all: Activity[] = [
  row('p-care', 'Caretaker', [run('r1', 'A'), run('r2', 'A'), run('r3', 'B')]),
  row('p-ada', 'Ada', [run('r4', 'B')]),
  row('p-idle', 'Idle', [run('r5', 'A', { live: false, held_here: false, state: 'unknown' })]),
]

const inA = workingIn(all, 'A')
assert.deepEqual(inA.map(workKey), ['r1', 'r2'], "A shows only A's runs, each its own entry")
assert.ok(inA.every((w) => w.runs!.length === 1 && w.conversation === 'A'), 'each entry is narrowed to its one run')
const inB = workingIn(all, 'B')
assert.deepEqual(inB.map(workKey).sort(), ['r3', 'r4'], "membership in B does not bring A's runs into B")
assert.equal(workingIn(all, 'C').length, 0, 'a conversation nobody runs in shows nobody, though they are members')
assert.equal(live(all).length, 4, 'an open run not held here is not somebody working')
assert.equal(new Set(live(all).map(workKey)).size, 4, 'every entry has its own key')

assert.equal(workingLine(inA), '@Caretaker ×2 are working', 'two runs of one persona are said as two')
assert.equal(workingLine([inA[0]]), '@Caretaker is working')
assert.equal(workingLine(inB.sort((a, b) => a.alias.localeCompare(b.alias))), '@Ada and @Caretaker are working')

// A live execution with no held run (fixture-style) is still somebody, where its execution is.
const exOnly = [row('p-x', 'X', [], { has_live_execution: true, conversation: 'A' })]
assert.deepEqual(workingIn(exOnly, 'A').map(workKey), ['p-x'])
assert.equal(workingIn(exOnly, 'B').length, 0, 'not in a conversation it is only a member of')

// The switcher row: how many, and whose.
assert.equal(workersWords({ working: 3, workers: [
  { run: 'r1', participant: 'p-care', alias: 'Caretaker' }, { run: 'r2', participant: 'p-care', alias: 'Caretaker' },
  { run: 'r4', participant: 'p-ada', alias: '@Ada' }] }), '3 working: @Caretaker ×2, @Ada')
assert.equal(workersWords({ working: 2 }), '2 working', 'a count alone is said as before')
console.log('fluid activity: ok')

// WHETHER A DURABLE MOVE CONCERNS A READER (concerns): only ever narrows what
// the pulse is certain of.
{
  const where = (w: Partial<Where>): Where => ({ conversations: [], executions: [], governed: false, people: false, loose: false, ...w })
  const activity = { executions: true, people: true }
  const notices = { conversations: true, governed: true, people: true }
  assert.equal(concerns(null, activity), true, 'no where: always reread')
  assert.equal(concerns(where({ loose: true }), notices), true, 'a loose move: always reread')
  assert.equal(concerns(where({ conversations: ['A'] }), activity), false, "a post nobody's run wrote: who is working has not moved")
  assert.equal(concerns(where({ conversations: ['A'], executions: ['x'] }), activity), true, "a run's act: reread")
  assert.equal(concerns(where({ people: true }), activity), true, 'a participant moved: reread')
  assert.equal(concerns(where({ executions: ['x'] }), notices), false, "only a run's own acts: no result or ask moved")
  assert.equal(concerns(where({ executions: ['x'], conversations: ['A'] }), notices), true, 'a Conversation moved: reread')
  assert.equal(concerns(where({ governed: true }), notices), true, 'governed material: reread')
  assert.equal(concerns(where({}), notices), false, 'nothing named: nothing to reread')
}
