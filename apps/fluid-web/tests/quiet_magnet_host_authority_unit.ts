/** THE HOST'S AUTHORITY DECISION for a Magnet's own Conversation.
 *
 *  `Host.tsx` decides which write the Magnet's Composer, Conversation view and
 *  Perspectives panel are allowed to make, and it decides it with
 *  `magnetWriteGate` -- the function checked here, not a re-statement of it.
 *  The reported blocker (integrator report `ent-226f667e4111`) was that the
 *  gate asked `conversation(id)` about a Magnet with NO own Conversation, where
 *  the id does not exist yet: that answers "may I write into nothing", which is
 *  no, so a Magnet that was simply new was reported as one that cannot be
 *  written to, and the first send was unreachable.
 *
 *  WHAT IS CHECKED WHERE. The gate is here. That the send really works -- the
 *  own Conversation made and the message recorded, with no own Conversation and
 *  an empty collection to start from -- and that a scoped authority refuses it
 *  and writes nothing, are checked against a REAL server on a disposable
 *  fixture Brain in `tests/test_quiet_magnet_additions_boundary.py`. The real
 *  `fluid/Composer` is client-only, so what the card draws around it is driven
 *  by `tests/quiet_magnet_mini_browser.py`.
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { magnetWriteGate, type MagnetWrites } from '../src/quiet2/magnets/capabilities'
import { ComposerBarView } from '../src/quiet2/magnets/ComposerBar'
import { CANNOT_WRITE, NO_OWN_CONVERSATION, NO_OWN_CONVERSATION_HERE } from '../src/quiet2/magnets/conversation'

const OWN = 'ent-own111111'

/** An ordinary server: its ordinary UI authority answers every write. */
const ordinary: MagnetWrites = {
  conversation: () => true, ownConversation: () => true,
  arrangement: () => true, fixture: false,
}
/** The disposable fixture's scope: one named Conversation may be written into,
 *  and making a Magnet's own Conversation is not one of the two writes its
 *  proxy forwards (`tools/quiet-magnet-additions-preview.mjs`). */
const scoped = (named: string): MagnetWrites => ({
  conversation: (id) => id === named, ownConversation: () => false,
  arrangement: () => true, fixture: true,
})

test('a Magnet with no own Conversation and an empty collection may be written to on an ordinary server', () => {
  // The case that was blocked. No collection is consulted at all: the gate is
  // given only the own Conversation, so an empty collection cannot block it.
  const gate = magnetWriteGate(ordinary, null, NO_OWN_CONVERSATION_HERE)
  assert.equal(gate.mayWrite, true, 'the first send is reachable')
  for (const none of [null, undefined, '', 'not-an-entry-id']) {
    assert.equal(magnetWriteGate(ordinary, none, NO_OWN_CONVERSATION_HERE).mayWrite, true,
      `no own Conversation (${String(none)}) does not make the card unwritable`)
  }
})

test('the question asked is about the operation, not about an id that does not exist', () => {
  // What the gate must NOT do: ask whether a Conversation that is not there may
  // be written into. A capability that refuses every named Conversation but
  // permits making one still answers yes for a Magnet that has none.
  const makesOnly: MagnetWrites = { ...ordinary, conversation: () => false }
  assert.equal(magnetWriteGate(makesOnly, null, NO_OWN_CONVERSATION_HERE).mayWrite, true,
    'with none of its own, what matters is whether one may be made')
  // And the converse: a capability that permits writing into the one it has but
  // not making any still answers yes once it has one.
  const writesOnly: MagnetWrites = { ...ordinary, ownConversation: () => false }
  assert.equal(magnetWriteGate(writesOnly, OWN, NO_OWN_CONVERSATION_HERE).mayWrite, true)
  assert.equal(magnetWriteGate(writesOnly, null, NO_OWN_CONVERSATION_HERE).mayWrite, false)
})

test('an own Conversation that exists is still asked about by name', () => {
  const gate = magnetWriteGate(scoped(OWN), OWN, NO_OWN_CONVERSATION_HERE)
  assert.equal(gate.mayWrite, true, 'the Conversation the scope names is writable')
  assert.equal(gate.why, undefined, 'and there is nothing to explain')
  const other = magnetWriteGate(scoped(OWN), 'ent-other11111', NO_OWN_CONVERSATION_HERE)
  assert.equal(other.mayWrite, false, 'one the scope does not name is not')
  assert.equal(other.why, undefined,
    'and the reason is the card’s own: this Magnet is not writable here')
})

test('where making one is not authorised the gate refuses and says why, without widening anything', () => {
  const gate = magnetWriteGate(scoped(OWN), null, NO_OWN_CONVERSATION_HERE)
  assert.equal(gate.mayWrite, false,
    'the fixture is not widened: a send it would refuse is not offered')
  assert.equal(gate.why, NO_OWN_CONVERSATION_HERE, 'and the card is told the actual reason')
})

test('the refusal names the operation rather than reporting the Magnet as unwritable', () => {
  const bar = (over: Record<string, unknown>) => renderToStaticMarkup(createElement(ComposerBarView, {
    canWrite: false, chip: null, suppressed: false, onRemoveChip: () => {}, replyTo: null,
    onReplyToConversation: () => {}, mode: 'ordinary' as const, retainedWhy: null,
    onMode: () => {}, reads: false, onReads: () => {}, frozen: false, sending: false,
    creating: false, uncertain: false, canRetry: false, onRetry: () => {}, composer: null,
    ...over,
  } as never))
  const told = bar({ cannotWriteBecause: NO_OWN_CONVERSATION_HERE })
  assert.ok(told.includes('making one is not available here'),
    'it names what cannot be done')
  assert.ok(!told.includes(CANNOT_WRITE),
    'and does not report the Magnet itself as unwritable here')
  // Unchanged where the host supplies no reason: an ordinary read-only page.
  assert.ok(bar({}).includes(CANNOT_WRITE))
  assert.notEqual(NO_OWN_CONVERSATION_HERE, NO_OWN_CONVERSATION,
    'the offer to make one and the refusal to are different sentences')
})
