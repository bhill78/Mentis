/* Task Gravity, said the same way everywhere (runs/gravity.ts), the
 * addressee chip that always states it (composer/words.ts), a run's line
 * Participant · Persona · runtime · Task Gravity, the side-work findings'
 * words, and a governed item's other fields (a Persona's behaviour) that the
 * item page now draws (governance/model.ts restOf). Operating-model §6. */
import assert from 'node:assert/strict'
import { GRAVITY_TIP, followUpOf, foundWords, gravityWords, reconsiderWords, runLine } from '../src/fluid/runs/gravity'
import { tokenOf } from '../src/fluid/composer/words'
import { restOf } from '../src/fluid/governance/model'
import type { Gravity, GravityItem } from '../src/api'
import type { Addressee } from '../src/composer/draft'

// Mark IV's words, whole
assert.equal(GRAVITY_TIP, 'Ask afterward: it is recorded and put to you when this work is finished. '
  + 'A depth allows that many generations of independently pursued discovery; work necessary to this request does not count. '
  + 'Permission allows pursuit; it never starts anything by itself.')

// the three values, and the draft's value read as the record's
assert.equal(gravityWords('ask'), 'Asks before pursuing side work')
assert.equal(gravityWords(undefined), 'Asks before pursuing side work')
assert.equal(gravityWords({ depth: 1 }), 'May pursue side work 1 generation deep')
assert.equal(gravityWords({ depth: 3 }), 'May pursue side work 3 generations deep')
assert.equal(gravityWords('unrestricted'), 'May pursue side work freely')
// an unreadable value is never widened: it is "ask", as the server reads it
assert.equal(gravityWords({ depth: 0 }), 'Asks before pursuing side work')
assert.deepEqual(followUpOf(undefined), 'ask')
assert.deepEqual(followUpOf(2), { depth: 2 })
assert.deepEqual(followUpOf('unrestricted'), 'unrestricted')

// the chip says the setting for somebody asked to work, "ask" included
const who: Addressee = { participant: 'p1', alias: '@Quill', dispatch: true }
assert.equal(tokenOf({ ...who, runtime: 'codex' }, []), 'codex · asks before side work')
assert.equal(tokenOf({ ...who, runtime: 'codex', followUp: 2 }, []), 'codex · side work: 2 deep')
assert.equal(tokenOf({ ...who, followUp: 'unrestricted', persona: 'ent-r' }, [], () => 'Reviewer'),
  'any runtime · Reviewer · side work: free')
assert.equal(tokenOf({ ...who, dispatch: false }, []), 'addressed only')

// a run's line, in the contract's order; what the record does not say is left out
assert.equal(runLine({ participant_name: '@Quill', persona: 'ent-r', persona_name: 'Reviewer', runtime: 'claude', follow_up: { depth: 2 }, generation: 0 }),
  'Quill · Reviewer · claude · May pursue side work 2 generations deep')
assert.equal(runLine({ participant_name: 'Quill', persona: null, runtime: 'codex', follow_up: 'ask' }),
  'Quill · codex · Asks before pursuing side work')
assert.equal(runLine({ participant_name: 'Quill', persona: 'ent-x', runtime: 'codex', follow_up: 'unrestricted', generation: 2 }),
  'Quill · ent-x · codex · May pursue side work freely (this is generation 2)')

// deferred findings: who found it and its generation; due only when the trunk is finished
const item: GravityItem = { act: 'a1', by: '@Quill', because: 'a flaky test', about: ['e1'], at: 1, conversation: 'c', originating_turn: 't', depth_from_root: 1 }
assert.equal(foundWords(item), 'Quill · generation 1')
const trunk = (complete: boolean, due: boolean): Gravity => ({
  deferred: [item],
  reconsideration: { trunk: { originating_turn: 't', turn_number: 4, complete, outstanding_on_trunk: [] }, deferred: [item], due_for_reconsideration: due },
})
assert.equal(reconsiderWords(trunk(true, true)), 'The work is finished: these are due for reconsideration.')
assert.equal(reconsiderWords(trunk(false, false)), 'Put to you when this work is finished.')
assert.equal(reconsiderWords({ deferred: [item] }), null)

// a Persona leads with its name; its behaviour and about follow, in the Kind's order
assert.deepEqual(restOf(['name', 'behaviour', 'about'], { name: 'Reviewer', behaviour: 'Challenge the claim.', about: '' }, 'name'),
  [{ field: 'behaviour', text: 'Challenge the claim.' }])
assert.deepEqual(restOf(['text'], { text: 'A rule' }, 'text'), [])
assert.deepEqual(restOf(undefined, undefined, undefined), [])

console.log('fluid_gravity_unit: ok')
