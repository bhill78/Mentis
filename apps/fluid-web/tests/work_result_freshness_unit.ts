/* Press-time readability of a post / Brain-record / conversation result (P4).
 *
 * Every case drives the shipped `src/work/freshness.ts` against answers shaped
 * exactly as `mentis.operational.result_destinations.enrich` writes them (the
 * fixtures below are copied from a real probe of that reader). Nothing is
 * mocked inside the module: only the one read it makes, and the page state it
 * is told about when that read answers.
 */
import assert from 'node:assert/strict'
import test from 'node:test'

import { MOVED_WORDS } from '../src/brainBinding'
import { ResultsRefreshRequired } from '../src/api'
import {
  ANOTHER_WORK, COULD_NOT_CHECK, NOT_LISTED, NOT_THE_SAME, RESULTS_MOVED,
  atOf, checkResultOpen, freshGroupPath, isResultOpens, itemIn, verdict,
  type Answer, type Checked, type Now, type Pressed,
} from '../src/work/freshness'
import type { WorkDetail, WorkResult } from '../src/work/contract'

const WORK = 'opr-1111aaaa2222'
const GROUP = 'ent-group000001'
const POST = 'ent-post00000001'
const CONV = 'ent-conv00000001'
const REC = 'ent-rec000000001'

const NOW: Now = { brain: 'corpus-one@abcd0123', moved: false, moves: 7 }

const pressed = (over: Partial<Pressed> = {}): Pressed => ({
  expectation: WORK, group: GROUP, ref: POST, opens: 'post',
  brain: NOW.brain, moves: NOW.moves, ...over,
})

/* As `_Resolver._post` answers an open post. */
const livePost = (): WorkResult => ({
  ref: POST, kind: 'post', source: null, basis: [], association: 'referenced',
  actionable: true, reason: null, available: true,
  inspection: {
    id: POST, type: 'post', label: 'a post that stays', available: true,
    state: 'ok', why: null, opens: 'post', post: POST, conversation: CONV,
    conversation_name: 'Somewhere else', number: 2,
  } as WorkResult['inspection'],
})

/* As it answers one that has since been deleted. */
const deletedPost = (): WorkResult => ({
  ...livePost(), actionable: false, available: false,
  reason: 'This post was deleted.',
  inspection: {
    id: POST, state: 'deleted', label: null, available: false,
    why: 'This post was deleted.', opens: null, post: POST, conversation: CONV,
    conversation_name: 'Somewhere else', number: 1,
  },
})

const conversationItem = (): WorkResult => ({
  ref: CONV, kind: 'record', source: null, basis: [], association: 'referenced',
  actionable: true, reason: null, available: true,
  inspection: { id: CONV, state: 'ok', available: true, why: null,
                opens: 'conversation', conversation: CONV, label: 'Somewhere else' },
})

const recordItem = (): WorkResult => ({
  ref: REC, kind: 'record', source: null, basis: [], association: 'referenced',
  actionable: true, reason: null, available: true,
  inspection: { id: REC, state: 'ok', available: true, why: null,
                opens: 'record', label: 'a durable note' },
})

const missingItem = (ref: string): WorkResult => ({
  ref, kind: 'record', source: null, basis: [], association: 'referenced',
  actionable: false, reason: 'This Brain holds nothing with this id.',
  available: false,
  inspection: { id: ref, state: 'missing', label: null, available: false,
                why: 'This Brain holds nothing with this id.', opens: null },
})

const detail = (items: WorkResult[], over: Partial<WorkDetail> = {}): WorkDetail => ({
  expectation: WORK,
  result_groups: {
    groups: [{ id: GROUP, source: null, unplaced: false, items,
               total_items: items.length, omitted_items: 0, next_items_after: null }],
    total_groups: 1, omitted_groups: 0, omitted_group_items: 0,
    next_results_before: null,
    availability_checked_at: '2026-11-22T01:21:18.228413+00:00',
  },
  ...over,
} as WorkDetail)

const ok = (items: WorkResult[], over: Partial<WorkDetail> = {}): Answer =>
  ({ ok: true, detail: detail(items, over) })

const say = (c: Checked): string => (c.how === 'open' ? 'open' : c.how)

// ---------------------------------------------------------------- the path

test('the re-read is the existing result page, one group of it', () => {
  assert.equal(freshGroupPath(pressed(), 'ent-me0000000001'),
    `/api/work/${encodeURIComponent(WORK)}?viewer=ent-me0000000001&result_group=${GROUP}`)
  assert.equal(freshGroupPath(pressed(), null),
    `/api/work/${encodeURIComponent(WORK)}?result_group=${GROUP}`)
  // No cursor is sent: a group is named, never paged into.
  assert.ok(!freshGroupPath(pressed(), null).includes('items_after'))
  assert.ok(!freshGroupPath(pressed(), null).includes('results_before'))
})

// ------------------------------------------------- still there: it opens

test('a post still readable opens at the conversation, post and number just read', () => {
  const c = verdict(pressed(), ok([livePost()]), NOW)
  assert.equal(say(c), 'open')
  assert.deepEqual(c.how === 'open' && c.at,
    { opens: 'post', conversation: CONV, post: POST, number: 2 })
})

test('a conversation and a record open at themselves', () => {
  const conv = verdict(pressed({ ref: CONV, opens: 'conversation' }),
    ok([conversationItem()]), NOW)
  assert.deepEqual(conv.how === 'open' && conv.at, { opens: 'conversation', conversation: CONV })
  const rec = verdict(pressed({ ref: REC, opens: 'record' }), ok([recordItem()]), NOW)
  assert.deepEqual(rec.how === 'open' && rec.at, { opens: 'record', entry: REC })
})

test('the row pressed is found among others, by its exact reference alone', () => {
  const page = detail([recordItem(), deletedPost(), conversationItem()]).result_groups
  assert.equal(itemIn(page, GROUP, POST)!.inspection!.state, 'deleted')
  assert.equal(itemIn(page, GROUP, 'ent-nothere00001'), null)
  assert.equal(itemIn(page, 'ent-other000001', POST), null)
})

// ------------------------------------------- gone: denied, deleted, unreadable

test('a post deleted since it was shown is refused in the server’s own words', () => {
  const c = verdict(pressed(), ok([deletedPost()]), NOW)
  assert.equal(say(c), 'gone')
  assert.equal(c.how === 'gone' && c.why, 'This post was deleted.')
})

test('a record or conversation the Brain no longer holds is refused in its own words', () => {
  for (const [ref, opens] of [[REC, 'record'], [CONV, 'conversation']] as const) {
    const c = verdict(pressed({ ref, opens }), ok([missingItem(ref)]), NOW)
    assert.equal(say(c), 'gone')
    assert.equal(c.how === 'gone' && c.why, 'This Brain holds nothing with this id.')
  }
})

test('available without opens, and opens without available, both refuse', () => {
  const noOpens = { ...livePost() }
  noOpens.inspection = { ...noOpens.inspection!, opens: null, why: 'It has no page of its own to open.' }
  assert.equal(say(verdict(pressed(), ok([noOpens]), NOW)), 'gone')

  const notAvailable = { ...livePost(), available: false }
  assert.equal(say(verdict(pressed(), ok([notAvailable]), NOW)), 'gone')

  // The row's own flag and the inspection's must BOTH say yes.
  const innerNo = { ...livePost() }
  innerNo.inspection = { ...innerNo.inspection!, available: false }
  assert.equal(say(verdict(pressed(), ok([innerNo]), NOW)), 'gone')
})

test('a post with no conversation to open it in is refused, never half-opened', () => {
  const homeless = { ...livePost() }
  homeless.inspection = { ...homeless.inspection!, conversation: null }
  assert.equal(atOf(homeless), null)
  assert.equal(say(verdict(pressed(), ok([homeless]), NOW)), 'gone')
})

test('a read that failed is an answer, not a move', () => {
  const c = verdict(pressed(), { ok: false, why: 'the record holds no such act' }, NOW)
  assert.equal(say(c), 'gone')
  assert.equal(c.how === 'gone' && c.why, 'the record holds no such act')
  // and one that said nothing still says something
  const quiet = verdict(pressed(), { ok: false }, NOW)
  assert.equal(quiet.how === 'gone' && quiet.why, COULD_NOT_CHECK)
})

test('an answer about other work never opens anything', () => {
  const c = verdict(pressed(), ok([livePost()], { expectation: 'opr-999999999999' }), NOW)
  assert.equal(c.how === 'gone' && c.why, ANOTHER_WORK)
})

test('an answer naming another reference in the row is not that reference', () => {
  const swapped = { ...livePost() }
  swapped.inspection = { ...swapped.inspection!, id: 'ent-somethingelse' }
  assert.equal(c_why(verdict(pressed(), ok([swapped]), NOW)), COULD_NOT_CHECK)
})

function c_why(c: Checked): string | null {
  return c.how === 'gone' || c.how === 'changed' ? c.why : null
}

// ------------------------------------------------ changed: not the same thing

test('a result no longer listed, or a group gone, says to read again', () => {
  assert.equal(c_why(verdict(pressed(), ok([recordItem()]), NOW)), NOT_LISTED)
  const noGroups = detail([], { result_groups: { groups: [], total_groups: 0,
    omitted_groups: 0, omitted_group_items: 0, next_results_before: null,
    availability_checked_at: 'x' } })
  assert.equal(c_why(verdict(pressed(), { ok: true, detail: noGroups }, NOW)), NOT_LISTED)
})

test('a reference that now opens something else is not what was pressed', () => {
  const nowAConversation = { ...livePost(), ref: POST }
  nowAConversation.inspection = { ...conversationItem().inspection!, id: POST, conversation: CONV }
  assert.equal(c_why(verdict(pressed(), ok([nowAConversation]), NOW)), NOT_THE_SAME)
})

test('a reference that now answers as an artifact is left to the opener’s own check', () => {
  const asArtifact: WorkResult = { ...livePost(), kind: 'artifact' }
  assert.equal(c_why(verdict(pressed(), ok([asArtifact]), NOW)), NOT_THE_SAME)
  const withDescriptor: WorkResult = { ...livePost(), artifact: { ref: POST, state: 'held' } }
  assert.equal(c_why(verdict(pressed(), ok([withDescriptor]), NOW)), NOT_THE_SAME)
})

test('results that moved under the read say so as the server’s own refusal', () => {
  const c = verdict(pressed(), { ok: false, why: 'Result group is absent; refresh results.', refresh: true }, NOW)
  assert.equal(say(c), 'changed')
  assert.equal(c_why(c), 'Result group is absent; refresh results.')
  assert.equal(c_why(verdict(pressed(), { ok: false, refresh: true }, NOW)), RESULTS_MOVED)
})

// -------------------------------------- a late answer never moves the reader

test('a reader who moved on while it was checked is neither told nor moved', () => {
  for (const answer of [ok([livePost()]), ok([deletedPost()]),
                        { ok: false as const, why: 'boom' }]) {
    const c = verdict(pressed(), answer, { ...NOW, moves: NOW.moves + 1 })
    assert.equal(c.how, 'dropped')
    assert.deepEqual(Object.keys(c), ['how'])  // nothing said, nothing to open
  }
})

test('the reader is checked before the answer is, so a late success cannot yank them', () => {
  const c = verdict(pressed(), ok([livePost()]), { brain: 'other@brain', moved: true, moves: NOW.moves + 2 })
  assert.equal(c.how, 'dropped')
})

test('a page that has moved to another Brain opens nothing on it', () => {
  assert.equal(c_why(verdict(pressed(), ok([livePost()]), { ...NOW, moved: true })), MOVED_WORDS)
  assert.equal(c_why(verdict(pressed(), ok([livePost()]), { ...NOW, brain: 'corpus-two@ffff' })), MOVED_WORDS)
})

test('unknown serving identity refuses', () => {
  assert.equal(say(verdict(pressed({ brain: null }), ok([livePost()]), NOW)), 'gone')
  assert.equal(say(verdict(pressed(), ok([livePost()]), { ...NOW, brain: null })), 'gone')
})

// ------------------------------------------------------ it can only refuse

test('nothing here can make an unavailable result openable', () => {
  // Every shape the server can answer that is not "available and opens":
  const refusals: WorkResult[] = [
    deletedPost(), missingItem(POST),
    { ...livePost(), available: false, actionable: true },
    { ...livePost(), inspection: undefined },
  ]
  for (const item of refusals) {
    assert.notEqual(verdict(pressed(), ok([item]), NOW).how, 'open')
  }
})

// ------------------------------------------------- the whole press, end to end

test('the press reads once, at the right path, and decides on what came back', async () => {
  const asked: string[] = []
  const c = await checkResultOpen(pressed(), {
    viewer: 'ent-me0000000001',
    now: () => NOW,
    read: async (path) => { asked.push(path); return detail([livePost()]) },
  })
  assert.deepEqual(asked, [freshGroupPath(pressed(), 'ent-me0000000001')])
  assert.equal(say(c), 'open')
})

test('the press checks the binding before and after the read', async () => {
  const order: string[] = []
  let moves = NOW.moves
  const c = await checkResultOpen(pressed(), {
    viewer: null,
    now: () => { order.push('now'); return { ...NOW, moves } },
    read: async () => { order.push('read'); moves += 1; return detail([livePost()]) },
  })
  assert.deepEqual(order, ['now', 'read', 'now'])
  assert.equal(c.how, 'dropped')
})

test('a read that throws never throws out of the press', async () => {
  const thrown = await checkResultOpen(pressed(), {
    viewer: null, now: () => NOW,
    read: async () => { throw new Error('Failed to fetch') },
  })
  assert.equal(thrown.how === 'gone' && thrown.why, 'Failed to fetch')

  const refused = await checkResultOpen(pressed(), {
    viewer: null, now: () => NOW,
    read: async () => { throw new ResultsRefreshRequired('Results changed or this cursor belongs elsewhere; refresh results.') },
  })
  assert.equal(refused.how, 'changed')
  assert.equal(c_why(refused), 'Results changed or this cursor belongs elsewhere; refresh results.')

  const odd = await checkResultOpen(pressed(), {
    viewer: null, now: () => NOW,
    read: async () => { throw 'not an error' },
  })
  assert.equal(odd.how === 'gone' && odd.why, COULD_NOT_CHECK)
})

test('the three checked words, and file is not one of them', () => {
  assert.ok(isResultOpens('post') && isResultOpens('record') && isResultOpens('conversation'))
  assert.ok(!isResultOpens('file') && !isResultOpens(null) && !isResultOpens(undefined))
})

test('continuation member is read with its opaque cursor; incomplete page never proves absence', async () => {
  const first = detail([recordItem()])
  const g = first.result_groups!.groups[0]
  g.next_items_after = 'opaque & cursor'
  g.omitted_items = 1
  assert.equal(verdict(pressed(), { ok: true, detail: first }, NOW).how, 'gone')
  const paths: string[] = []
  const c = await checkResultOpen(pressed(), { viewer: null, now: () => NOW,
    read: async (path) => { paths.push(path); return paths.length === 1 ? first : detail([livePost()]) } })
  assert.equal(c.how, 'open')
  assert.ok(paths[1].includes('items_after=opaque%20%26%20cursor'))
})

test('continuation refresh and repeated cursor fail truthfully without claiming absence', async () => {
  const first = detail([])
  first.result_groups!.groups[0].next_items_after = 'cursor'
  first.result_groups!.groups[0].omitted_items = 1
  let calls = 0
  const c = await checkResultOpen(pressed(), { viewer: null, now: () => NOW,
    read: async () => { if (++calls === 2) throw new ResultsRefreshRequired('Refresh this result page.'); return first } })
  assert.deepEqual(c, { how: 'changed', why: 'Refresh this result page.' })
  calls = 0
  const cycle = await checkResultOpen(pressed(), { viewer: null, now: () => NOW,
    read: async () => { calls++; return first } })
  assert.deepEqual(cycle, { how: 'gone', why: COULD_NOT_CHECK })
  assert.equal(calls, 2)
})

test('a continuation read stops silently after centre movement', async () => {
  const first = detail([])
  first.result_groups!.groups[0].next_items_after = 'cursor'
  first.result_groups!.groups[0].omitted_items = 1
  let moves = NOW.moves
  let calls = 0
  const c = await checkResultOpen(pressed(), { viewer: null, now: () => ({ ...NOW, moves }),
    read: async () => { calls++; moves++; return first } })
  assert.equal(c.how, 'dropped')
  assert.equal(calls, 1)
})

test('malformed nested success bodies never throw, and unknown states never open', async () => {
  for (const page of [null, { groups: [null] }, { groups: [{ id: GROUP, items: {} }] }]) {
    const c = await checkResultOpen(pressed(), { viewer: null, now: () => NOW,
      read: async () => ({ expectation: WORK, result_groups: page }) as unknown as WorkDetail })
    assert.deepEqual(c, { how: 'gone', why: COULD_NOT_CHECK })
  }
  const item = livePost()
  item.inspection!.state = 'future-unknown'
  assert.equal(verdict(pressed(), ok([item]), NOW).how, 'gone')
})

test('direct references read without inventing a Work; identity, state and binding are checked', async () => {
  const p = pressed({ expectation: null, group: null })
  const [corpus_id, instance] = p.brain!.split('@')
  const brain = { corpus_id, instance }
  const readRef = async (path: string) => {
    assert.equal(path, `/fluid/api/result-ref?ref=${encodeURIComponent(p.ref)}`)
    return { brain, inspection: livePost().inspection }
  }
  assert.equal((await checkResultOpen(p, { viewer: null, now: () => NOW, readRef })).how, 'open')
  for (const inspection of [undefined, { ...livePost().inspection!, id: 'ent-other' },
    { ...livePost().inspection!, state: 'future-unknown' }]) {
    assert.equal((await checkResultOpen(p, { viewer: null, now: () => NOW,
      readRef: async () => ({ brain, inspection }) })).how, 'gone')
  }
  assert.equal((await checkResultOpen(p, { viewer: null, now: () => NOW,
    readRef: async () => ({ brain: { corpus_id, instance: 'other' }, inspection: livePost().inspection }) })).how, 'gone')
  assert.deepEqual(await checkResultOpen(p, { viewer: null, now: () => NOW,
    readRef: async () => { throw new Error('Owner read refused.') } }), { how: 'gone', why: 'Owner read refused.' })
})
