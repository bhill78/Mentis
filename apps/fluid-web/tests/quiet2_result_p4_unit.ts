/* P4 -- A POST, A BRAIN RECORD OR A CONVERSATION IS READ AGAIN AT THE PRESS,
 * against the real composition (`mount.ts` + `opener.ts` + `refNow.ts` +
 * `src/work/freshness.ts`), exactly as `quiet2_result_mount_unit.ts` runs the
 * artifact half.
 *
 * WHAT THIS FALSIFIES. Before this, `mount.ts`'s read adapter answered
 * `{how:'unchecked'}` for every target that was not an artifact, and the three
 * remaining routes moved the reader on the row in hand. A post deleted since
 * that row was drawn therefore took the reader out of where they were, and the
 * destination page -- not the press -- was what said it could not be read.
 *
 * The only thing injected is the ONE read `freshness.ts` makes
 * (`page.resultNow`). The route it asks for, the decision it makes on the
 * answer, the host adapters, the guard's three ends and the opener's identity
 * check are all this build's own. */
import assert from 'node:assert/strict'
import { centreGeneration, mountResults, placedResults, resetPlacedResults, type ResultPage } from '../src/quiet2/results/mount'
import { clearLaunches, beginOpening, holdLaunch, type LaunchContext, type LaunchPlace } from '../src/quiet2/results/launch'
import type { ResultDestination } from '../src/quiet2/results/targets'
import type { Opened } from '../src/quiet2/results/opener'
import type { CentreAt } from '../src/quiet2/address'
import type { WorkDetail, WorkResult } from '../src/work/contract'
import { heldItem } from '../src/quiet2/brain/logic'
import { closeViewer, maximised } from '../src/quiet2/viewer/viewers'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }

const BRAIN = 'fixture-corpus@instance-1'
const WORK = 'opr-work00000001'
const GROUP = 'ent-group0000001'
const CONV = 'ent-conversatn1'
const POST = 'ent-post00000001'
const REC = 'ent-record12345'
const HERE: LaunchPlace = { conversation: 'ent-origin', centre: null }

const launch = (): LaunchContext => holdLaunch({
  opening: beginOpening(), brainKey: BRAIN, place: HERE, thread: null,
  reading: null, reply: null, draft: null,
  focus: { control: null, fallback: { kind: 'conversation' } }, decision: null,
})

/* -- destinations as the result projection gives them ---------------------- */

const base = (over: Partial<ResultDestination>): ResultDestination => ({
  work: WORK, group: GROUP, target: { kind: 'post', conversation: CONV, post: POST },
  label: 'Generation 1 returned', source: null, basis: ['returned-by-run'],
  verified: true, availability: 'ok', available: true, opens: 'post', reason: null,
  ...over,
})
const postDest = () => base({})
const recordDest = () => base({ target: { kind: 'record', ref: REC }, opens: 'record' })
const convDest = () => base({ target: { kind: 'record', ref: CONV }, opens: 'conversation' })
/** the same post, as a destination the record placed in no Work at all */
const unplaced = () => base({ work: null, group: null })

/* -- the server's own answers, as `enrich` writes them ---------------------- */

const row = (ref: string, inspection: WorkResult['inspection'], available = true,
             reason: string | null = null): WorkResult => ({
  ref, kind: 'record', source: null, basis: [], association: 'referenced',
  actionable: available, reason, available, inspection,
})
const answer = (items: WorkResult[]): WorkDetail => ({
  expectation: WORK,
  result_groups: {
    groups: [{ id: GROUP, source: null, unplaced: false, items,
               total_items: items.length, omitted_items: 0, next_items_after: null }],
    total_groups: 1, omitted_groups: 0, omitted_group_items: 0,
    next_results_before: null, availability_checked_at: '2026-11-22T01:00:00Z',
  },
} as WorkDetail)

const livePost = (conversation = CONV) => row(POST, {
  id: POST, state: 'ok', available: true, why: null, opens: 'post',
  post: POST, conversation, number: 2, label: 'a post that stays',
})
const deletedPost = () => row(POST, {
  id: POST, state: 'deleted', available: false, why: 'This post was deleted.',
  opens: null, post: POST, conversation: CONV, number: 1,
}, false, 'This post was deleted.')
const liveRecord = () => row(REC, {
  id: REC, state: 'ok', available: true, why: null, opens: 'record', label: 'a durable note',
})
const missingRecord = () => row(REC, {
  id: REC, state: 'missing', available: false, opens: null,
  why: 'This Brain holds nothing with this id.',
}, false, 'This Brain holds nothing with this id.')
const liveConversation = () => row(CONV, {
  id: CONV, state: 'ok', available: true, why: null, opens: 'conversation',
  conversation: CONV, label: 'Somewhere else',
})
const erasedConversation = () => row(CONV, {
  id: CONV, state: 'erased', available: false, opens: null,
  why: 'This was permanently deleted with its conversation.',
}, false, 'This was permanently deleted with its conversation.')

/* -- a page, as a shared host supplies one --------------------------------- */

interface Seen { picked: string[]; posts: string[]; said: string[]; centre: CentreAt[]; read: string[] }

function makePage(resultNow: (path: string) => Promise<WorkDetail>, asks = () => false) {
  const r: Seen = { picked: [], posts: [], said: [], centre: [], read: [] }
  let pending: { go: () => void; stay: () => void } | null = null
  let at: CentreAt = null
  const guarded = (go: () => void, stay?: () => void) => {
    if (asks()) { pending = { go, stay: stay ?? (() => {}) }; return }
    go()
  }
  const page: ResultPage = {
    brainKey: () => BRAIN,
    origin: () => 'https://fixture.invalid',
    conversation: () => HERE.conversation!,
    centreAt: () => at,
    enterCentre: (to) => { at = to },
    columns: () => [], freeColumn: () => null, choose: () => {},
    invoker: () => null, hasControl: () => false, focus: () => {},
    centreGo: (to) => { at = to; r.centre.push(to) },
    centreReplace: (to) => { at = to },
    backTo: (_p, then) => { then() },
    pickConversation: (k, then, stay) => { r.picked.push(k); guarded(() => then?.(), stay); return true },
    openPost: (c, p, done) => { r.posts.push(`${c}/${p}`); guarded(() => done('completed'), () => done({ how: 'cancelled' })) },
    record: (entry, go, stay) => { r.picked.push(`record:${entry}`); guarded(go, stay) },
    goToPost: () => {},
    heldItem: (ref, about) => heldItem(ref, about),
    putBack: () => {},
    say: (w) => { r.said.push(w) },
    resultNow: (path) => { r.read.push(path); return resultNow(path) },
  }
  return { page, r, answerGuard: (how: 'go' | 'stay') => { const q = pending!; pending = null; q[how]() }, waiting: () => !!pending }
}

const settle = () => new Promise<void>((done) => { setImmediate(done) })
function fresh() {
  for (const v of placedResults().all()) closeViewer(v.viewer)
  const max = maximised()
  if (max) closeViewer(max.id)
  clearLaunches()
  resetPlacedResults()
}

/* ========================================================================== *
 * THE PRESS READS FIRST, AND HAS MOVED NOBODY YET
 * ========================================================================== */
for (const [what, d, reply] of [
  ['post', postDest(), answer([livePost()])],
  ['record', recordDest(), answer([liveRecord()])],
  ['conversation', convDest(), answer([liveConversation()])],
] as [string, ResultDestination, WorkDetail][]) {
  fresh()
  const settled: Opened[] = []
  let release!: (d: WorkDetail) => void
  const host = makePage(() => new Promise<WorkDetail>((res) => { release = res }))
  const m = mountResults(host.page)
  const press = m.openResult(d, launch(), (o) => settled.push(o))
  eq(press, { what: 'leaving', how: what }, `P4: a ${what} press is READ FIRST and has not arrived`)
  eq(host.r.posts, [], `P4: no ${what} route was taken on the press itself`)
  eq(host.r.picked, [], 'P4: and no conversation or record page was entered')
  eq(host.r.read, [`/api/work/${WORK}?result_group=${GROUP}`],
    'P4: the read is the existing result page, for the one group the row is in')
  release(reply)
  await settle()
  eq(settled.map((o) => o.what), ['opened'], `P4: a ${what} still readable then opens`)
}

/* ========================================================================== *
 * WHAT IS NO LONGER READABLE IS REFUSED, IN THE RECORD'S OWN WORDS, AND
 * THE READER IS NOT MOVED
 * ========================================================================== */
for (const [what, d, reply, words] of [
  ['a deleted post', postDest(), answer([deletedPost()]), 'This post was deleted.'],
  ['a record this Brain no longer holds', recordDest(), answer([missingRecord()]), 'This Brain holds nothing with this id.'],
  ['a permanently deleted conversation', convDest(), answer([erasedConversation()]), 'This was permanently deleted with its conversation.'],
] as [string, ResultDestination, WorkDetail, string][]) {
  fresh()
  const settled: Opened[] = []
  const host = makePage(async () => reply)
  const m = mountResults(host.page)
  m.openResult(d, launch(), (o) => settled.push(o))
  await settle()
  eq(settled, [{ what: 'unavailable', why: words }], `P4: ${what} is unavailable, in the server's own words`)
  eq(host.r.said, [words], 'P4: and the reader is told exactly that')
  eq(host.r.posts, [], 'P4: the post route was never taken')
  eq(host.r.picked, [], 'P4: no conversation was opened and no record page entered')
  eq(host.r.centre, [], 'P4: and no history entry is owed')
}

/* ========================================================================== *
 * A READ THAT COULD NOT BE MADE IS A REFUSAL, NOT A MOVE
 * ========================================================================== */
{
  fresh()
  const settled: Opened[] = []
  const host = makePage(() => Promise.reject(new Error('Failed to fetch')))
  const m = mountResults(host.page)
  m.openResult(postDest(), launch(), (o) => settled.push(o))
  await settle()
  eq(settled.map((o) => o.what), ['unavailable'], 'P4: a read that failed opens nothing')
  eq(host.r.posts, [], 'P4: and moves nobody')
}

/* ========================================================================== *
 * A FRESH ANSWER THAT NAMES SOMETHING ELSE IS NOT THIS PRESS'S ANSWER
 * ========================================================================== */
{
  fresh()
  const settled: Opened[] = []
  const host = makePage(async () => answer([livePost('ent-elsewhere01')]))
  const m = mountResults(host.page)
  m.openResult(postDest(), launch(), (o) => settled.push(o))
  await settle()
  eq(settled.map((o) => o.what), ['refused'],
    'P4: the same post in another conversation is refused by the opener’s own identity check')
  eq(host.r.posts, [], 'P4: and nothing was opened on it')
}

/* ========================================================================== *
 * THE OPEN IS ON THE FRESH FACTS, NEVER THE ROW IN HAND
 * ========================================================================== */
{
  fresh()
  /* the row says post #1 of this conversation; the fresh read says the same
     post, same conversation -- and the press goes to what the READ said */
  const host = makePage(async () => answer([livePost()]))
  const m = mountResults(host.page)
  m.openResult(postDest(), launch())
  await settle()
  eq(host.r.posts, [`${CONV}/${POST}`], 'P4: the post route is taken with the freshly read conversation and post')
}

/* ========================================================================== *
 * THE UNSAVED-WORK GUARD IS UNTOUCHED: STILL ASKED, AND STAY STILL KEEPS
 * ========================================================================== */
{
  fresh()
  const settled: Opened[] = []
  const host = makePage(async () => answer([liveRecord()]), () => true)
  const m = mountResults(host.page)
  m.openResult(recordDest(), launch(), (o) => settled.push(o))
  await settle()
  ok(host.waiting(), 'P4: the unsaved-work question is still asked, after the check and before the move')
  eq(settled, [], 'P4: and asking is not arriving')
  host.answerGuard('stay')
  eq(settled.map((o) => o.what), ['cancelled'], 'P4: Stay still keeps the reader where they were')
}
{
  fresh()
  const settled: Opened[] = []
  const host = makePage(async () => answer([liveRecord()]), () => true)
  const m = mountResults(host.page)
  m.openResult(recordDest(), launch(), (o) => settled.push(o))
  await settle()
  host.answerGuard('go')
  eq(settled.map((o) => o.what), ['opened'], 'P4: and Go still opens it')
}

/* ========================================================================== *
 * A READER WHO MOVED ON WHILE IT WAS CHECKED IS NEITHER TOLD NOR MOVED
 * ========================================================================== */
{
  fresh()
  const settled: Opened[] = []
  let release!: (d: WorkDetail) => void
  const host = makePage(() => new Promise<WorkDetail>((res) => { release = res }))
  const m = mountResults(host.page)
  m.openResult(postDest(), launch(), (o) => settled.push(o))
  const was = centreGeneration()
  /* the reader goes somewhere else: the centre moves, exactly as a Back does */
  m.applyCentre(null)
  ok(centreGeneration() !== was, 'the centre has moved while the check was in flight')
  release(answer([livePost()]))
  await settle()
  eq(settled, [], 'P4: a late answer tells a reader who moved on nothing')
  eq(host.r.posts, [], 'P4: and does not take them anywhere')
  eq(host.r.said, [], 'P4: and says nothing, because they asked for none of it')
}

/* ========================================================================== *
 * A DESTINATION THE RECORD PLACED IN NO WORK KEEPS EXACTLY ITS OLD BEHAVIOUR
 * ========================================================================== */
{
  fresh()
  const settled: Opened[] = []
  const host = makePage(async () => { throw new Error('nothing should be read') })
  const m = mountResults(host.page)
  const press = m.openResult(unplaced(), launch(), (o) => settled.push(o))
  eq(host.r.read, [], 'P4: a destination with no Work and no result group is not re-read')
  eq(press.what, 'opened', 'P4: and opens on the press, exactly as it did before')
  eq(host.r.posts, [`${CONV}/${POST}`], 'P4: by its own route, unchanged')
}

fresh()
console.log(`quiet2 result P4 readability: ${checks} checks ok`)
