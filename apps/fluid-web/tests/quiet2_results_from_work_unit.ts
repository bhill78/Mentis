/* THE INTEGRATOR'S OWN SEAM: the chooser's wire shape as the opener's
 * destination, and the record's post mapping as the lookup `Post.tsx` asks.
 *
 * HOST-INTEGRATION.md §3.3 left this conversion to whoever mounts the two
 * parts together (`src/quiet2/results/fromWork.ts`). These checks are its
 * falsifiers: each one undoes a rule the two parts' own reviews established
 * and watches it fail.
 */
import assert from 'node:assert/strict'
import { destinationOfResult, destinationOfTarget, lookupOf, resultsByPost } from '../src/quiet2/results/fromWork'
import { REFERENCED_ONLY, actionable, openable } from '../src/quiet2/results/targets'
import type { ResultGroup, ResultPage, WorkItem, WorkResult } from '../src/work/contract'

let n = 0
const eq = (a: unknown, b: unknown, m: string) => { n++; assert.deepEqual(a, b, m) }
const ok = (a: unknown, m: string) => { n++; assert.ok(a, m) }
const no = (a: unknown, m: string) => { n++; assert.ok(!a, m) }

const ADM = 'adm-0c40c5395a16'
const POST = 'ent-6c39bfc11d0d'
const CONV = 'ent-458c8860e63e'
const WORK = 'opr-a71d4f7a25fc'

function held(over: Partial<WorkResult> = {}): WorkResult {
  return {
    ref: ADM, kind: 'artifact', source: { turn: POST, number: 1, conversation: CONV, conversation_name: 'Quiet' },
    basis: [{ kind: 'returned-by-run', act: 'opr-1', work: WORK, turn: POST }],
    association: 'verified', actionable: true, reason: null,
    artifact: { ref: ADM, state: 'held', name: 'REVIEW.md', size: 22902, claimed_media_type: 'text/markdown' },
    ...over,
  }
}

/* ========================================================================== *
 * AN ARTIFACT DESCRIPTOR IS HELD BYTES, AND ITS OWN WORD IS ITS AVAILABILITY
 * ========================================================================== */
{
  const d = destinationOfResult(held(), { work: WORK, group: 'grp-1' })
  eq(d.target, { kind: 'artifact', ref: ADM }, 'a held Admission is an artifact target')
  eq(d.opens, 'file', 'and its route is the file viewer')
  eq(d.availability, 'ok', '`held` IS `ok` (availabilityOf), not an unknown word')
  ok(d.available, 'and it is available')
  eq(openable(d).can, true, 'so it opens')
  eq(d.label, 'REVIEW.md', 'the descriptor name is what a person reads')
  eq(d.work, WORK, 'the Work it was chosen from is carried')
  eq(d.group, 'grp-1', 'and so is the exact group, for the entry and the re-read')
  eq(d.source, { kind: 'post', conversation: CONV, post: POST }, 'the PRODUCING post is the source')
  ok(d.verified, 'a verified association is verified')
  eq(d.file?.state, 'held', 'the bytes are carried so the viewer needs no second read')
}
{
  /* a descriptor that is not held opens nothing, in the server's own words */
  const d = destinationOfResult(held({ artifact: { ref: ADM, state: 'purged', reason: 'Its contents were purged from this Brain.' } }))
  eq(d.availability, 'purged', 'the descriptor state is the availability')
  no(d.available, 'and it is not available')
  eq(openable(d), { can: false, why: 'Its contents were purged from this Brain.' }, 'the refusal is the server own reason')
}
{
  /* NOTHING IS CLAIMED WHERE THE SERVER SAID NOTHING: no inspection and no
     descriptor is `unknown`, which degrades to `unreadable` and refuses. */
  const d = destinationOfResult(held({ artifact: undefined }))
  eq(d.availability, 'unreadable', 'no answer is not an answer of available')
  eq(openable(d).can, false, 'and such a press is refused, not attempted')
}

/* ========================================================================== *
 * PROVENANCE IS CARRIED, NOT RESTATED (navigation review B2)
 * ========================================================================== */
{
  const claimOnly = destinationOfResult(held({
    association: 'referenced', actionable: false, reason: REFERENCED_ONLY,
    basis: [{ kind: 'authored-result-ref', act: 'opr-2', work: WORK, turn: POST }],
  }))
  eq(claimOnly.basis, ['authored-result-ref'], 'the record own basis kinds, exactly')
  no(actionable(claimOnly.basis), 'an authored claim alone is not an actionable deliverable')
  no(claimOnly.verified, 'and the association is not verified')
  eq(claimOnly.reason, REFERENCED_ONLY, 'said in the words the review settled on')
}
{
  /* THE SOURCE IS NEVER BORROWED. A result the record states no producing
     post for has none -- not the post the chooser happens to be drawn on. */
  const d = destinationOfResult(held({ source: null }))
  eq(d.source, null, 'no stated origin, no invented one')
}

/* ========================================================================== *
 * AN INSPECTED REFERENCE TAKES THE SERVER'S ROUTE, AND ONLY IT
 * ========================================================================== */
{
  const post = destinationOfResult({
    ref: POST, kind: 'post', source: null, basis: [{ kind: 'attached-to-turn', act: 'opr-3', work: WORK, turn: POST }],
    association: 'verified', actionable: true, reason: null,
    inspection: { id: POST, state: 'ok', available: true, opens: 'post', why: null, post: POST, conversation: CONV, label: 'the request' },
  })
  eq(post.target, { kind: 'post', conversation: CONV, post: POST }, 'a post route needs the conversation the server named')
  eq(post.opens, 'post', 'and takes it')
  eq(openable(post).can, true, 'so it opens')
}
{
  /* a post route the server named WITHOUT a conversation opens nothing: it is
     said, never guessed at from whatever conversation is shown */
  const routeless = destinationOfResult({
    ref: POST, kind: 'post', source: null, basis: [], association: 'verified', actionable: true, reason: null,
    inspection: { id: POST, state: 'ok', available: true, opens: 'post', why: null },
  })
  eq(routeless.opens, null, 'no conversation, no post route')
  eq(openable(routeless).can, false, 'and it says so rather than offering a broken press')
}
{
  /* `state: ok` with `opens: null` is available AND nothing to open (M2.2) */
  const orphan = destinationOfResult({
    ref: 'ent-orphan00001', kind: 'record', source: null, basis: [], association: 'verified', actionable: true,
    reason: null, inspection: { id: 'ent-orphan00001', state: 'ok', available: true, opens: null, why: null },
  })
  ok(orphan.available, 'the Brain holds it')
  eq(openable(orphan).can, false, 'and there is still nothing here that opens it')
}

/* ========================================================================== *
 * A STORED ENTRY'S TARGET, BACK AS A DESTINATION (§3.2)
 * ========================================================================== */
{
  eq(destinationOfTarget({ kind: 'artifact', ref: ADM })?.target, { kind: 'artifact', ref: ADM }, 'an artifact entry points at its Admission')
  eq(destinationOfTarget({ kind: 'post', conversation: CONV, post: POST })?.target, { kind: 'post', conversation: CONV, post: POST }, 'a post entry at its post')
  eq(destinationOfTarget({ kind: 'record', ref: 'ent-record12345' })?.target, { kind: 'record', ref: 'ent-record12345' }, 'a record entry at its record')
  eq(destinationOfTarget({ kind: 'url', href: 'https://example.invalid/x' }), null, 'a URL has no viewer to restore, so no destination here')
  eq(destinationOfTarget({ kind: 'commit', sha: 'a'.repeat(40) }), null, 'and neither has a commit')
}

/* ========================================================================== *
 * WHICH POSTS CARRY WHICH WORK'S RESULTS: THE RECORD'S MAPPING, EXACTLY
 * ========================================================================== */
function group(items: WorkResult[]): ResultGroup {
  return {
    id: 'grp-1', source: { turn: POST, number: 1, conversation: CONV, conversation_name: 'Quiet' },
    unplaced: false, items, total_items: items.length, omitted_items: 0, next_items_after: null,
  }
}
function page(items: WorkResult[]): ResultPage {
  return {
    groups: [group(items)], total_groups: 1, omitted_groups: 0, omitted_group_items: 0,
    next_results_before: null, availability_checked_at: '2026-11-22T10:00:00Z',
  }
}
function item(over: Partial<WorkItem> = {}): WorkItem {
  return {
    expectation: WORK, title: 'Result-first navigation', group: 'in_flight', status_words: 'In flight',
    state: 'open', state_source: 'recorded', objective_met: null, met_at: null,
    origin: { turn: POST, number: 1, conversation: CONV, conversation_name: 'Quiet' },
    replies: 3, last_activity_at: null, why_unknown: null,
    update_turns: [{ turn: 'ent-update000001', number: 7, conversation: CONV, conversation_name: 'Quiet' }],
    result_summary: page([held()]),
    ...over,
  } as WorkItem
}

{
  const by = resultsByPost({ items: [item()] })
  eq([...by.keys()].sort(), ['ent-update000001', POST].sort(), 'the request Turn and each recorded update carry it')
  eq(by.get(POST)?.map((r) => r.mapping), ['request'], 'the origin Turn is the request')
  eq(by.get('ent-update000001')?.map((r) => r.mapping), ['update'], 'an update_turn is an update')
  eq(by.get(POST)?.[0].title, 'Result-first navigation', 'with the Work own title for the heading')
}
{
  /* A POST MAPPED TWICE keeps both, each said as what it is. */
  const both = resultsByPost({ items: [item({ update_turns: [{ turn: POST, number: 1, conversation: CONV, conversation_name: 'Quiet' }] })] })
  eq(both.get(POST)?.map((r) => r.mapping), ['request', 'update'], 'a request that was claimed on carries both')
}
{
  /* NOTHING IS INFERRED: a post the record does not map gets nothing, however
     much the Work says about it. */
  const by = resultsByPost({ items: [item()] })
  eq(by.get('ent-unmapped00001') ?? [], [], 'an unmapped post carries no chooser')
  eq(lookupOf({ items: [item()] })('ent-unmapped00001'), [], 'and the lookup answers empty, never undefined')
}
{
  /* AN EMPTY RESULT READ GETS NO CHOOSER: an empty section is noise. */
  eq(resultsByPost({ items: [item({ result_summary: page([]) })] }).size, 0, 'a Work whose result read is empty maps nothing')
  eq(resultsByPost({ items: [item({ result_summary: undefined })] }).size, 0, 'and so does one the server sent no results for')
  eq(resultsByPost(null).size, 0, 'no read at all is an ordinary state')
}

console.log(`quiet2 results from work: ${n} checks ok`)
