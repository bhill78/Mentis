/* The run panel's feed (src/fluid/runs/feed.ts): entries merge by id in seq
 * order, and how a session ended is said as a session's end, never as the
 * work being done. */
import assert from 'node:assert/strict'
import { endedWords, merge, waitingPermissions, type Feed, type FeedEntry, type Permission } from '../src/fluid/runs/feed'

const e = (id: string, seq: number, extra: Partial<FeedEntry> = {}): FeedEntry => ({ id, seq, kind: 'tool', at: seq, ...extra })
let held = merge([], [e('message-1', 1, { kind: 'message', text: 'Hel' }), e('tool-a', 2, { status: 'in_progress' })])
held = merge(held, [e('message-1', 3, { kind: 'message', text: 'Hello' })])
assert.deepEqual(held.map((x) => x.id), ['tool-a', 'message-1'], 'a changed entry moves to its new place')
assert.equal(held[1].text, 'Hello', 'and replaces what was held')
assert.equal(merge(held, []), held, 'nothing new keeps the same list')

const feed = (outcome: Feed['outcome'], ended = 5): Feed => ({ run: 'r', held_here: true, ended_at: ended, outcome, events: [], next: 0 })
assert.equal(endedWords(feed({ stop_reason: 'cancelled', error_kind: null, error: null, stopped: true, session_ended: false })), 'Stopped: the session ended cleanly')
assert.equal(endedWords(feed({ stop_reason: null, error_kind: 'cancel_forced', error: null, stopped: true, session_ended: true })), 'Stopped: the session was ended by force')
assert.equal(endedWords(feed({ stop_reason: 'end_turn', error_kind: null, error: null, stopped: false, session_ended: false })), 'Session finished its turn')
assert.equal(endedWords(feed(null, 0)), null, 'a run still going has no end words')
for (const o of [true, false]) {
  const w = endedWords(feed({ stop_reason: 'end_turn', error_kind: null, error: null, stopped: o, session_ended: false }))!
  assert.ok(!/complete|done/i.test(w), 'never says the work is done: ' + w)
}

const permissions: Permission[] = Array.from({ length: 10 }, (_, i) => ({
  form: `form-${i}`, decision: `decision-${i}`, asked_at: i,
  conversation: 'conversation', post: 'post', title: `Tool ${i}`,
}))
const rapid = { ...feed(null, 0), permissions, permission: permissions[0] }
assert.deepEqual(waitingPermissions(rapid).map((p) => p.decision), permissions.map((p) => p.decision),
  'ten rapid permissions remain independently addressable in server order')
assert.deepEqual(waitingPermissions({ ...rapid, permissions: undefined }).map((p) => p.decision), ['decision-0'],
  'an older server still exposes its singular permission')
console.log('fluid runs: ok')
