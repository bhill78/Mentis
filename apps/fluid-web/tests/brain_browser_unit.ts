/* MANAGE BRAIN, ROUND 2 — WORKSTREAM A (the rail's Brain icon and browser
 * card), checked without a browser:
 *
 *  - `plainStandingLabel` (brain/data.ts): the Ladder status + whether it
 *    governs, mapped to DESIGN-r2.md's "The record, at rest" sentences.
 *  - `compactStanding` (brain/BrainBrowser.tsx): a compact row's short
 *    "Kind · Ladder status · plain words" words (DESIGN-r2.md,
 *    "Navigation" §2), read from a record summary alone.
 */
import assert from 'node:assert/strict'
import { plainStandingLabel, type BrainRecordSummary } from '../src/quiet2/brain/data'
import { compactStanding } from '../src/quiet2/brain/BrainBrowser'

/* -- plainStandingLabel: adopted knowledge vs governing -------------------- */
assert.equal(
  plainStandingLabel('adopted', false),
  "In effect as knowledge — agents are told it when relevant; it doesn't bind them",
)
assert.equal(plainStandingLabel('adopted', true), 'In effect — agents are given it as a rule')

/* -- not in effect: requested, declined, superseded, ended ----------------- */
assert.equal(plainStandingLabel('adoption_requested', false), 'Not in effect — proposed, waiting for your decision')
assert.equal(plainStandingLabel('declined', false), 'Not in effect — declined')
assert.equal(plainStandingLabel('superseded', true), 'Not in effect — replaced')
assert.equal(plainStandingLabel('ended', false), 'Not in effect — ended')
assert.equal(plainStandingLabel('retired', false), 'Not in effect — ended')

/* -- recorded, not adopted; and a status nobody recognises reads the same,
      never a stronger claim than the Ladder made -------------------------- */
assert.equal(plainStandingLabel('recorded', false), 'Recorded, not adopted — reaches agents only as labelled past experience')
assert.equal(plainStandingLabel('something-new', true), plainStandingLabel('recorded', true), 'an unrecognised status reads as recorded does')

/* -- compactStanding: the mockup's own rows (1-brain-rail.html) ------------ */
const row = (over: Partial<BrainRecordSummary>): BrainRecordSummary => ({
  id: 'r', kind: 'lesson', text: 'words', standingPlain: '', standingLabel: 'Adopted', governs: false, challenged: false, ...over,
})

assert.deepEqual(compactStanding(row({ kind: 'lesson', standingLabel: 'Adopted · knowledge' })), { status: 'Adopted', words: 'in effect', off: false })
assert.deepEqual(compactStanding(row({ kind: 'finding', standingLabel: 'Recorded' })), { status: 'Recorded', words: 'not in effect', off: false })
assert.deepEqual(compactStanding(row({ kind: 'hypothesis', standingLabel: 'Recorded' })), { status: 'Recorded', words: 'not settled', off: false })
assert.deepEqual(compactStanding(row({ kind: 'lesson', standingLabel: 'Superseded' })), { status: 'Superseded', words: 'replaced', off: true })

console.log('ok')
