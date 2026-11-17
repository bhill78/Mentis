/* THE CONVERSATION FOLLOWING THE RECORD: the decisions, without React or a
 * browser (quiet2/real.ts, 2026-11-17).
 *
 * The defect: Quiet Chat Mark 2's conversation read itself when it was
 * opened, on the reader's own post and on a rename, and at no other time, so
 * an agent's post after a run was not drawn until something else made the
 * page read again. It now hears the pulse Fluid already beats. The things
 * that decide what that does are pure:
 *
 *   `flowMoved`   -- whether a pulse move can have changed this flow;
 *   `keepingEarlier` -- what a reread shows, so that reading the latest batch
 *                       again never takes words away from above the reader;
 *   `spacedAfter` -- when a read the pulse asked for runs (FLOW_SPACING);
 *   `readingAgain` -- whether a read of a thread is a reread of what is
 *                     already shown or the first read of a new root.
 *
 * The thread being read follows the record on the same terms (the correction
 * of ent-4964f2340ef8): the flow carries the latest batch of threads with
 * it, so a thread whose root is older than that batch was never reread, and
 * an agent's reply inside an entered older thread was not drawn until the
 * reader left and came back.
 *
 * The browser cases (an agent's post appearing in the owner's browser, the
 * draft, the place and the posts above kept, switching conversations, and an
 * entered older thread) are tests/test_quiet_refresh_browser.py. */
import assert from 'node:assert/strict'
import { FLOW_SPACING, flowMoved, keepingEarlier, readingAgain, spacedAfter } from '../src/quiet2/real'
import type { Post } from '../src/quiet2/sample'

let checks = 0
const ok = (what: string, fn: () => void) => { fn(); checks++; void what }

const C = 'ent-here'
const OTHER = 'ent-elsewhere'
const where = (o: Partial<{ conversations: string[]; executions: string[]; governed: boolean; people: boolean; loose: boolean }> = {}) =>
  ({ conversations: [], executions: [], governed: false, people: false, loose: false, ...o })

/* -- flowMoved ------------------------------------------------------------ */

ok('the record moving in this conversation is read again', () => {
  assert.equal(flowMoved('durable', where({ conversations: [C] }), C), true)
})

ok('the record moving in another conversation is not', () => {
  assert.equal(flowMoved('durable', where({ conversations: [OTHER] }), C), false)
})

ok('one of several conversations named is enough', () => {
  assert.equal(flowMoved('durable', where({ conversations: [OTHER, C] }), C), true)
})

ok('LIVE EXECUTION MOVING WROTE NOTHING: a run starting, working or merely '
  + 'ending is not a post, and the flow does not read for it. The final post '
  + 'after it finishes is a durable move of its own, which is read.', () => {
  assert.equal(flowMoved('live', null, C), false)
  assert.equal(flowMoved('live', where({ conversations: [C] }), C), false)
  assert.equal(flowMoved('durable', where({ conversations: [C], executions: ['inst-1'] }), C), true)
})

ok('NOTHING IS NARROWED THAT IS NOT CERTAIN: where the pulse could not say, '
  + 'and a loose move, are read exactly as every move was before', () => {
  assert.equal(flowMoved('durable', null, C), true)
  assert.equal(flowMoved('durable', where({ loose: true }), C), true)
  assert.equal(flowMoved('durable', where({ conversations: [OTHER], loose: true }), C), true)
})

ok('no conversation shown: nothing to read again', () => {
  assert.equal(flowMoved('durable', null, null), false)
  assert.equal(flowMoved('durable', where({ loose: true }), null), false)
})

ok('governed material or people alone moved: not this flow', () => {
  assert.equal(flowMoved('durable', where({ governed: true, people: true }), C), false)
})

ok('the spacing is a bound, stated', () => {
  assert.ok(FLOW_SPACING >= 1000 && FLOW_SPACING <= 5000, String(FLOW_SPACING))
})

/* -- spacedAfter: WHEN A READ THE PULSE ASKED FOR RUNS -------------------- */

ok('MOVES INSIDE THE WINDOW BECOME ONE READ AT ITS END: a move just after a '
  + 'read waits out the rest of the spacing, trailing, so nothing is dropped', () => {
  assert.equal(spacedAfter(10_000, 10_000), FLOW_SPACING)
  assert.equal(spacedAfter(10_000, 10_500), FLOW_SPACING - 500)
})

ok('a move after the window has passed is read at once', () => {
  assert.equal(spacedAfter(10_000, 10_000 + FLOW_SPACING), 0)
  assert.equal(spacedAfter(10_000, 99_000), 0)
  // nothing has been read yet: at once
  assert.equal(spacedAfter(0), 0)
})

/* -- readingAgain: ARRIVING IS NOT READING AGAIN -------------------------- */

ok('THE FIRST READ OF A ROOT IS NOT A REREAD: it says it is reading and owns '
  + 'its failure -- nothing of that thread is on screen yet', () => {
  assert.equal(readingAgain(null, 'p1', 0), false)
})

ok('A READ THE PULSE ASKED FOR IS: the same root, one move further on. What '
  + 'is already read stays, so no reply flickers out and back, and a reread '
  + 'that fails leaves the thread standing.', () => {
  assert.equal(readingAgain({ root: 'p1', advance: 0 }, 'p1', 1), true)
  assert.equal(readingAgain({ root: 'p1', advance: 7 }, 'p1', 8), true)
})

ok('ANOTHER THREAD IS ANOTHER READ: entering a different root reads afresh, '
  + 'however many moves have been heard', () => {
  assert.equal(readingAgain({ root: 'p1', advance: 3 }, 'p2', 3), false)
  assert.equal(readingAgain({ root: 'p1', advance: 3 }, 'p2', 4), false)
})

ok('the same root at the same move is the same read, not a reread (a view '
  + 'mounted twice reads as it always did)', () => {
  assert.equal(readingAgain({ root: 'p1', advance: 2 }, 'p1', 2), false)
})

/* -- keepingEarlier ------------------------------------------------------- */

const held = new Map<string, Post>()
const post = (id: string, o: Partial<Post> = {}): Post => {
  const p = { id, by: { id: 'p', name: '@p' }, at: '', weight: 'brief', topics: [], blocks: [], attachments: [], conversation: C, real: true, ...o } as unknown as Post
  held.set(id, p)
  return p
}
const of = (id: string) => held.get(id)

const read = (top: string[], o: Partial<{ older: number; first: number | null; topic: string | null; conversation: string | null; participants: { id: string; name: string }[] }> = {}) => ({
  name: 'Here', total: top.length, top, topics: [], participants: [], units: null,
  topic: null, conversation: C, older: 0, first: null, ...o,
})

ok('A FIRST READ STANDS AS IT IS: there is nothing above it yet', () => {
  const got = read(['a', 'b'])
  assert.equal(keepingEarlier(null, got, of), got)
})

ok('ANOTHER CONVERSATION OR TOPIC IS ANOTHER FLOW: it replaces, never merges '
  + '-- a switch must not leave the conversation left behind on screen', () => {
  const got = read(['x'])
  assert.equal(keepingEarlier(read(['a']), { ...got, conversation: OTHER }, of).top.join(), 'x')
  assert.equal(keepingEarlier(read(['a']), { ...got, topic: 'ent-topic' }, of).top.join(), 'x')
  assert.equal(keepingEarlier(read(['a'], { topic: 'ent-topic' }), got, of).top.join(), 'x')
})

ok('A NEW POST ARRIVES AT THE END and nothing else moves', () => {
  const r = keepingEarlier(read(['a', 'b']), read(['a', 'b', 'c']), of)
  assert.equal(r.top.join(), 'a,b,c')
})

ok('THE LATEST BATCH HAS DROPPED ITS OLDEST THREAD, and that thread is still '
  + 'on screen above the reader: it is kept, in front, in its own order. '
  + 'Replacing what is shown with the new batch would have taken words away '
  + 'from above somebody reading and moved the page under them.', () => {
  const shown = read(['a', 'b', 'c'], { older: 4, first: 12 })
  const got = read(['b', 'c', 'd'], { older: 5, first: 14 })
  const r = keepingEarlier(shown, got, of)
  assert.equal(r.top.join(), 'a,b,c,d')
  // and how much is still older stays as the earlier read left it
  assert.equal(r.older, 4)
  assert.equal(r.first, 12)
})

ok('EARLIER POSTS THE READER ASKED FOR ARE NOT UNDONE by a refresh', () => {
  const shown = read(['e1', 'e2', 'a', 'b'], { older: 2, first: 3 })
  const got = read(['a', 'b', 'c'], { older: 9, first: 30 })
  const r = keepingEarlier(shown, got, of)
  assert.equal(r.top.join(), 'e1,e2,a,b,c')
  assert.equal(r.older, 2)
  assert.equal(r.first, 3)
})

ok('NOTHING ABOVE: the new read says how much is older, as it always did', () => {
  const r = keepingEarlier(read(['a', 'b'], { older: 9, first: 30 }), read(['a', 'b', 'c'], { older: 9, first: 30 }), of)
  assert.equal(r.older, 9)
  assert.equal(r.first, 30)
})

ok('A KEPT POST THAT IS NOW A REPLY under a root in the new batch goes under '
  + 'it, not beside it -- as reading earlier posts does', () => {
  post('root')
  post('kid', { replyTo: 'root', root: 'root' })
  const r = keepingEarlier(read(['kid', 'a'], { older: 1, first: 5 }), read(['a', 'root'], { older: 2, first: 7 }), of)
  assert.equal(r.top.join(), 'a,root')
})

ok('a kept post whose root is NOT in the new batch stays where it is', () => {
  post('lone', { replyTo: 'gone', root: 'gone' })
  const r = keepingEarlier(read(['lone', 'a'], { older: 1, first: 5 }), read(['a', 'b'], { older: 2, first: 7 }), of)
  assert.equal(r.top.join(), 'lone,a,b')
})

ok('participants read in either are kept, once each', () => {
  const shown = read(['a'], { older: 1, first: 5, participants: [{ id: 'p1', name: '@one' }] })
  const got = read(['b'], { older: 2, first: 7, participants: [{ id: 'p1', name: '@one' }, { id: 'p2', name: '@two' }] })
  const r = keepingEarlier(shown, got, of)
  assert.equal(r.participants.map((p) => p.id).join(), 'p1,p2')
})

ok('THE NAME, COUNT AND TOPICS ARE THE NEW READ\'S: a renamed conversation, '
  + 'a new topic and the count of posts come from what was just read', () => {
  const got = { ...read(['a', 'b'], { older: 2, first: 7 }), name: 'Renamed', total: 99 }
  const r = keepingEarlier(read(['z', 'a'], { older: 1, first: 5 }), got, of)
  assert.equal(r.name, 'Renamed')
  assert.equal(r.total, 99)
})

console.log(`${checks} checks passed`)
