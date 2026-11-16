/* THE RECORD, READ (manage-brain round 2, Workstream B): checked without a
 * browser (DESIGN-r2.md "The record, at rest" and "Effectiveness, in plain
 * words").
 *
 *  - the Ladder→plain-words table, including the hypothesis exception
 *  - the standing pill's knowledge/rule suffix
 *  - "Helped" / "Didn't help" / "Unclear" verdicts, never a count or score
 *  - the subline: who adopted it and when, and its scope
 *  - a history act's words
 *  - the fold toggle a section's disclosure button uses
 */
import assert from 'node:assert/strict'
import { plainStandingLabel, standingPillLabel, verdictLabel } from '../src/quiet2/brain/data'
import {
  actWords,
  countWords,
  dateOnly,
  proposedSentence,
  standingDot,
  standingSentence,
  stripAt,
  sublineWords,
  toggleFold,
} from '../src/quiet2/brain/recordWords'

/* -- the Ladder→plain-words table (DESIGN-r2.md) -------------------------- */
assert.equal(
  plainStandingLabel('adopted', false),
  "In effect as knowledge — agents are told it when relevant; it doesn't bind them.",
)
assert.equal(plainStandingLabel('adopted', true), 'In effect — agents are given it as a rule.')
assert.equal(plainStandingLabel('adoption_requested', false), 'Not in effect — waiting for your decision.')
assert.equal(plainStandingLabel('adoption_requested', true), 'Not in effect — waiting for your decision.')
assert.equal(plainStandingLabel('recorded', false), 'Recorded, not adopted — reaches agents only as labelled past experience.')
assert.equal(plainStandingLabel('declined', false), 'Not in effect — declined.')
assert.equal(plainStandingLabel('superseded', false), 'Not in effect — replaced.')
assert.equal(plainStandingLabel('ended', false), 'Not in effect — ended.')
assert.equal(plainStandingLabel('retired', false), 'Not in effect — ended.')
/* an unknown status falls back to the Ladder's own word, never invented */
assert.equal(plainStandingLabel('made up', false), 'Recorded')

/* a hypothesis merely recorded is "Not settled" -- the one row the 2-arg
   table cannot say without the Kind */
assert.equal(standingSentence('hypothesis', 'recorded', false), 'Not settled.')
assert.equal(standingSentence('lesson', 'recorded', false), plainStandingLabel('recorded', false))
assert.equal(standingSentence('hypothesis', 'adopted', false), plainStandingLabel('adopted', false), 'an adopted hypothesis is settled: the ordinary mapping applies')

/* -- the standing pill: knowledge/rule only for adopted & asked ----------- */
assert.equal(standingPillLabel('adopted', false), 'Adopted · knowledge')
assert.equal(standingPillLabel('adopted', true), 'Adopted · rule')
assert.equal(standingPillLabel('adoption_requested', true), 'Adoption requested · rule')
assert.equal(standingPillLabel('recorded', false), 'Recorded', 'recorded material carries no knowledge/rule suffix')
assert.equal(standingPillLabel('declined', true), 'Adoption declined')

/* -- effectiveness, in plain words: no counts, no score ------------------- */
assert.equal(verdictLabel('worked'), 'Helped')
assert.equal(verdictLabel('failed'), "Didn't help")
assert.equal(verdictLabel('inconclusive'), 'Unclear')
assert.equal(verdictLabel('mixed'), 'mixed', 'free text until every outcome is a B7 verdict: passed through, never fabricated')

/* -- who asked, waiting on the owner -------------------------------------- */
assert.equal(proposedSentence('@Reviewer', null), 'Not in effect — proposed by Reviewer, waiting for your decision.')
assert.equal(proposedSentence(null, 'ent-abc'), 'Not in effect — proposed by ent-abc, waiting for your decision.')
assert.equal(proposedSentence(null, null), 'Not in effect — proposed by somebody, waiting for your decision.')

/* -- the subline: who adopted it and when, and its scope ------------------ */
const nov12 = new Date(2026, 10, 12, 11, 5).getTime() / 1000
assert.equal(
  sublineWords({ status: 'adopted', governs: false, adoptedBy: '@brian', adoptedAt: nov12, scopeLabel: 'whole Brain' }),
  'Adopted by brian, Nov 12 · whole Brain',
)
assert.equal(
  sublineWords({ status: 'adopted', governs: false, adoptedBy: '@brian', adoptedAt: nov12, scopeLabel: null }),
  'Adopted by brian, Nov 12',
)
assert.equal(
  sublineWords({ status: 'adoption_requested', governs: true }),
  'If adopted, agents are given it as a rule they must follow.',
)
assert.equal(
  sublineWords({ status: 'adoption_requested', governs: false }),
  "If adopted, agents are told it when relevant; it doesn't bind them.",
)
assert.equal(sublineWords({ status: 'declined', governs: false, recordedBy: '@brian', recordedAt: nov12 }), 'Declined by brian, Nov 12.')
assert.equal(sublineWords({ status: 'superseded', governs: false, recordedAt: nov12 }), 'Replaced, Nov 12.')
assert.equal(sublineWords({ status: 'ended', governs: false, recordedAt: nov12 }), 'Ended, Nov 12.')
assert.equal(sublineWords({ status: 'recorded', governs: false, recordedBy: '@Builder', recordedAt: nov12 }), 'Recorded by Builder, Nov 12')

/* -- a history act's words ------------------------------------------------- */
assert.equal(actWords('material-recorded'), 'Recorded')
assert.equal(actWords('material-adopted'), 'Adopted')
assert.equal(actWords('adoption-requested'), 'Adoption requested')
assert.equal(actWords('something-nobody-named-yet'), 'Something nobody named yet', 'an unknown act is said in its own words, not dropped')

/* -- helpers used throughout ------------------------------------------------ */
assert.equal(stripAt('@brian'), 'brian')
assert.equal(stripAt(null, 'somebody'), 'somebody')
assert.equal(dateOnly(nov12), 'Nov 12')
assert.equal(dateOnly(null), '')
assert.equal(standingDot('adopted'), '')
assert.equal(standingDot('adoption_requested'), 'ask')
assert.equal(standingDot('declined'), 'gone')
assert.equal(standingDot('recorded'), 'off')
assert.equal(countWords(0, 'source'), 'none')
assert.equal(countWords(1, 'source'), '1 source')
assert.equal(countWords(3, 'source'), '3 sources')
assert.equal(countWords(1, 'challenge'), '1 challenge')

/* -- the fold toggle: several sections may be open together --------------- */
let open = new Set<string>()
open = toggleFold(open, 'stands')
assert.deepEqual([...open], ['stands'])
open = toggleFold(open, 'gone')
assert.deepEqual([...open], ['stands', 'gone'])
open = toggleFold(open, 'stands')
assert.deepEqual([...open], ['gone'], 'toggling an open section closes only that one')

console.log('brain_record_unit: ok')
