/* QUIET CHAT MARK 2 ON THE MODERNIZED BACKEND (WS-C and later rounds),
 * checked without a browser:
 *
 *  1. a run that ended is never completion: run state `ended` (and an older
 *     server's `completed`) is a closed run, worded "ended", inked neutral;
 *  2. a request with a reply and no claim is "replied", neutral, never met;
 *  3. a claim not recorded met reads in the server's words -- "Claimed met ·
 *     pending: <reason>", "Partly done · <summary>", "Not done · <summary>"
 *     -- from the work overview or from the acts on the reply, and is never
 *     completed; a claim reconciled met is met;
 *  4. verified only from the work overview's `verified` state; recorded met
 *     alone says nothing is independently verified;
 *  5. stopped for a consent change reads as stopped, needing attention;
 *  6. delegated and not started keeps the server's words and is never ended;
 *  7. inks: --ok only for recorded met and verified; replied, claimed, ended
 *     and recovered are neutral;
 *  8. a run's Permission/Execution lines and its enforcement (never said as
 *     enforced unless the server says so); runtime availability in its four
 *     states; a structured refusal said whole. */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { askState, attributionOf, claimLine, claimOfActs, statusOf, workByExpectation, type ExpectationFact, type PostAct, type WorkFact } from '../src/quiet2/status/status.ts'
import { availabilityLines, ENDED, isEnded, PLAIN_END, runModesOf, runStateWord } from '../src/quiet2/activity/records.ts'
import { refusalWords } from '../src/quiet2/refusal.ts'
import { Refused } from '../src/fluid/actions.ts'

let checks = 0
const ok = (cond: unknown, msg: string) => { assert.ok(cond, msg); checks++ }
const eq = <T,>(a: T, b: T, msg: string) => { assert.deepEqual(a, b, msg); checks++ }

const exp = (over: Partial<ExpectationFact> = {}): ExpectationFact => ({
  id: 'opr-1', expects: 'result', of: 'p-ada', of_alias: 'Ada', by: 'p-owner', by_alias: 'Owner',
  response_present: false, live_execution: false, satisfied_by: [], failures: [], delegations: [], ...over,
})
const facts = (e: ExpectationFact) => ({ addressees: [], expectations: [e] })
const work = (state: string, status_words: string, more: Partial<WorkFact> = {}) =>
  new Map<string, WorkFact>([['opr-1', { expectation: 'opr-1', state, status_words, ...more }]])

/* -- 1. ended is not completed --------------------------------------------- */
ok(ENDED.has('ended'), 'run state `ended` is a closed run')
ok(ENDED.has('completed'), 'an older server\'s `completed` stays a closed run')
ok(isEnded({ state: 'ended', ended_at: null }), 'an ended run is ended')
eq(runStateWord('completed'), 'ended', 'an older `completed` run is worded ended, never completed')
eq(runStateWord('ended'), 'ended', 'ended stays ended')
eq(runStateWord('recovered'), 'recovered', 'other states keep the server\'s word')
ok(PLAIN_END.has('ended') && !PLAIN_END.has('failed'), 'only a plain end drops its how-it-ended line')

/* -- 2. a reply is not completion ------------------------------------------ */
{
  const e = exp({ response_present: true })
  eq(askState(e), 'replied', 'a reply with no claim is replied')
  const s = statusOf(facts(e), [])!
  eq(s.state, 'replied', 'post: replied')
  ok(!/complete|met/i.test(s.label.replace('not marked complete', '')), 'a reply is never said met or complete: ' + s.label)
  ok(/no outcome is claimed/.test(s.parties[0].asks[0].words), 'its words say no outcome is claimed')
}

/* -- 3. claims, from the work overview -------------------------------------- */
{
  const e = exp({ response_present: true })
  const pend = work('claim-pending', 'Claimed met · pending: its run has not ended yet',
    { claim: { act: 'opr-c', result: 'met', summary: 'fixed it', evidence: ['tests pass'], claimed_by: 'exe', participant: 'p-ada',
      participant_alias: '@Ada', via: 'reply', at: null, recorded: 'pending', reasons: ['its run has not ended yet', 'review required'] } })
  const s = statusOf(facts(e), [], { work: pend })!
  eq(s.state, 'claimed', 'a pending claim is claimed, not completed')
  eq(s.label, 'Claimed met · pending: its run has not ended yet', 'the server\'s words head it')
  eq(s.parties[0].state, 'claimed', 'party: claimed')
  eq(attributionOf(s.parties[0]), 'Claimed, not met: @Ada', 'attribution says claimed, not met')
  ok(/not recorded met/.test(s.parties[0].asks[0].words), 'its sentence says it is not recorded met')

  const partly = statusOf(facts(e), [], { work: work('claimed-partly', 'Partly done · two of three') })!
  eq([partly.state, partly.label], ['claimed', 'Partly done · two of three'], 'partly done')
  const notMet = statusOf(facts(e), [], { work: work('claimed-not-met', 'Not done · blocked') })!
  eq([notMet.state, notMet.label], ['claimed', 'Not done · blocked'], 'not done')
}

/* -- 3b. claims, from the acts on the reply (no work item) ------------------ */
{
  const claim: PostAct = { id: 'opr-c', act: 'outcome-claimed', at: 10, actor: 'p-ada', caused_by: 'opr-1',
    detail: { result: 'met', summary: 'did it', evidence: [] } }
  const pending: PostAct = { id: 'opr-p', act: 'outcome-pending', at: 11, actor: 'mentis', caused_by: 'opr-1',
    detail: { claim: 'opr-c', reasons: ['decision opr-9 is open'] } }
  const c1 = claimOfActs([claim, pending], 'opr-1')!
  eq(c1.recorded, 'pending', 'an outcome-pending names the claim: pending')
  eq(claimLine(c1), 'Claimed met · pending: decision opr-9 is open', 'pending words')
  eq(claimLine(claimOfActs([claim], 'opr-1')!), 'Claimed met · not recorded met yet', 'a claim not reconciled yet is not met')
  const partly: PostAct = { ...claim, detail: { result: 'partly', summary: 'half' } }
  eq(claimLine(claimOfActs([partly], 'opr-1')!), 'Partly done · half', 'partly from acts')
  const notMet: PostAct = { ...claim, detail: { result: 'not-met', summary: 'could not' } }
  eq(claimLine(claimOfActs([notMet], 'opr-1')!), 'Not done · could not', 'not met from acts')
  eq(claimOfActs([claim], 'opr-other'), null, 'a claim about another request is not this one\'s')
  const met: PostAct = { id: 'opr-m', act: 'expectation-met', at: 12, actor: 'p-ada', caused_by: 'opr-1', detail: { reconciled_from: 'opr-c' } }
  eq(claimOfActs([claim, met], 'opr-1')!.recorded, 'met', 'reconciled: met')

  const e = exp({ response_present: true })
  eq(statusOf(facts(e), [], { claimActs: [claim, pending] })!.state, 'claimed', 'post: claimed from the reply\'s acts')
  /* recorded met by reconciliation: satisfied_by is set, and it is met, not verified */
  const done = exp({ response_present: true, satisfied_by: ['opr-m'] })
  const s = statusOf(facts(done), [], { claimActs: [claim, met] })!
  eq(s.state, 'completed', 'a claim reconciled met is met')
}

/* -- 4. verified only from `verified` ---------------------------------------- */
{
  const done = exp({ response_present: true, satisfied_by: ['opr-m'] })
  eq(askState(done), 'completed', 'recorded met with no work item: met')
  const met = statusOf(facts(done), [], { work: work('claimed-met', 'Objective met · claimed by @Ada') })!
  eq(met.state, 'completed', 'claimed-met is met, never verified')
  eq(met.label, 'Objective met', 'met is said as objective met')
  ok(/Nothing records it as independently verified/.test(met.parties[0].asks[0].words), 'met alone denies verification')
  ok(!/verified ·|Verified/.test(met.label), 'no verification word without the state')
  const v = statusOf(facts(done), [], { work: work('verified', 'Verified · @Reviewer') })!
  eq(v.state, 'verified', 'only `verified` is verified')
  eq(v.label, 'Verified · @Reviewer', 'the server\'s words for it')
  eq(attributionOf(v.parties[0]), 'Met and verified: @Ada', 'attribution')
  /* a claim of met in the agent's own words is never verified */
  eq(askState(exp({ response_present: true }), work('claim-pending', 'x').get('opr-1')), 'claimed', 'claim of met: claimed, not verified')
  /* verified state without satisfied_by is not shown met */
  eq(askState(exp({ response_present: true }), work('verified', 'Verified · @R').get('opr-1')), 'replied', 'verified needs the record met too')
}

/* -- 5. consent-stopped ------------------------------------------------------ */
{
  const e = exp({ response_present: false })
  const s = statusOf(facts(e), [], { work: work('consent-stopped', 'Stopped for a consent change · not restarted · yours to continue') })!
  eq(s.parties[0].state, 'stopped', 'party: stopped')
  eq(s.state, 'attention', 'post: attention, never ended or met')
  eq(s.label, 'Stopped for a consent change · not restarted · yours to continue', 'the server\'s words')
  eq(attributionOf(s.parties[0]), 'Stopped for a consent change: @Ada', 'attribution')
  /* a restarted run is running again */
  eq(askState(exp({ live_execution: true }), work('consent-stopped', 'x').get('opr-1')), 'running', 'a live run is running')
}

/* -- 6. delegated, not started ---------------------------------------------- */
{
  const e = exp()
  const s = statusOf(facts(e), [], { work: work('owed', 'Not started · Delegated · not started') })!
  eq(s.state, 'pending', 'owed: pending, never ended')
  ok(s.parties[0].asks[0].words.includes('Not started · Delegated · not started'), 'the server\'s words travel with it')
  ok(!/ended|complete/i.test(s.label), 'never said ended or complete')
}

/* -- the overview, keyed ---------------------------------------------------- */
eq([...workByExpectation({ items: [{ expectation: 'opr-a', state: 'running' } as never, { expectation: 'opr-b', state: 'returned' } as never] }).keys()],
  ['opr-a', 'opr-b'], 'items by expectation')

/* -- 7. inks ----------------------------------------------------------------- */
{
  const css = readFileSync(fileURLToPath(new URL('../src/quiet2/status/status.css', import.meta.url)), 'utf8')
  const ink = (sel: string) => new RegExp(`\\.q2 \\.q2-st-ear-${sel}, \\.q2-st-swatch\\.q2-st-ear-${sel} \\{ color: ([^;]+);`).exec(css)?.[1]
  ok(ink('replied') && ink('replied') !== 'var(--ok)', 'replied ear and swatch are neutral: ' + ink('replied'))
  ok(ink('claimed') && ink('claimed') !== 'var(--ok)', 'claimed ear is neutral: ' + ink('claimed'))
  eq(ink('completed'), 'var(--ok)', 'recorded met keeps --ok')
  eq(ink('verified'), 'var(--ok)', 'verified keeps --ok')
  const okRules = css.split('\n').filter((l) => l.includes('var(--ok)'))
  ok(okRules.every((l) => /completed|verified/.test(l)), '--ok only on met or verified: ' + okRules.join(' | '))
  ok(/\.q2-st-enforce \{ color: var\(--text-dim\)/.test(css), 'enforcement words are neutral')
  const dock = readFileSync(fileURLToPath(new URL('../src/quiet2/dock.css', import.meta.url)), 'utf8')
  ok(/\.q2-gdock-kicker\[data-state='ended'\], \.q2-gdock-kicker\[data-state='completed'\], \.q2-gdock-kicker\[data-state='recovered'\] \{ color: var\(--text-dim\); \}/.test(dock),
    'ended, completed and recovered run kickers are neutral')
  ok(!/data-state='(ended|completed|recovered)'\][^{]*\{[^}]*--ok/.test(dock), 'no run kicker is --ok')
}

/* -- 8. a run's modes, and enforcement -------------------------------------- */
{
  const m = runModesOf({
    run: 'opr-r', operations: [],
    consent: { mode: 'ask', label: 'Ask for permission', enforcement: { by: 'none', enforced: false, words: 'Not enforced here.' } } as never,
    execution: { mode: 'unrestricted-host', source: 'selected', mechanism: 'agent-full-access', isolation: 'host', permission_enforcement: null, acknowledged: null, applied_by_mars: true },
  })!
  eq(m.lines[0], 'Permission: Ask for permission', 'permission line, Fluid\'s words')
  eq(m.lines[1], 'Execution: Unrestricted Host (selected) · directly on this machine · agent-full-access', 'execution line, Fluid\'s executionLine')
  eq(m.enforcement?.enforced, false, 'not enforced is never enforced')
  const unreported = runModesOf({ run: 'r', operations: [], consent: { mode: 'ask', enforcement: { by: null, enforced: 'yes' } } as never })
  eq(unreported?.enforcement, null, 'an enforcement with no words is not shown')
  const truthy = runModesOf({ run: 'r', operations: [], consent: { mode: 'ask', enforcement: { by: 'x', enforced: 'true', words: 'w' } } as never })
  eq(truthy?.enforcement?.enforced, false, 'only a literal true is enforced')
  eq(runModesOf(null), null, 'an older server: nothing')
}

/* -- 8a. runtime availability, four states, nothing assumed ----------------- */
{
  const rt = (over: Record<string, unknown>) => ({ kind: 'codex', present: true, version: null, capabilities: [], notes: [], models: [], ...over }) as never
  const absent = availabilityLines(rt({ present: false }))
  eq(absent.unavailable, true, 'not installed: unavailable')
  ok(/Not installed/.test(absent.lines[0]), 'said as not installed')
  const st = (state: string, why: string | null = null) => ({ state, mechanism: null, permission_enforcement: '', why })
  const a = availabilityLines(rt({ execution_modes: { default: 'sandboxed', modes: {
    sandboxed: st('temporarily-unavailable', 'not signed in'), 'unrestricted-host': st('unverified'), container: st('unsupported') } } }))
  eq(a.unavailable, true, 'a temporarily unavailable mode marks the runtime')
  eq(a.lines[0], 'Execution: Sandboxed (default): temporarily unavailable: not signed in · Unrestricted Host: not verified on this runtime · Container: not available yet',
    'each mode in its own state, with the server\'s why')
  const b = availabilityLines(rt({ execution_modes: { default: 'unrestricted-host', modes: {
    sandboxed: st('unsupported', 'no sandbox'), 'unrestricted-host': st('supported') } } }))
  eq(b.unavailable, false, 'supported: available')
  eq(b.lines[0], 'Execution: Sandboxed: no sandbox · Unrestricted Host (default): supported · Container: not available yet', 'host-only runtime said as it is')
  eq(availabilityLines(rt({ execution_modes: { default: null, modes: {} } })).lines[0], 'Execution modes: not reported for this runtime', 'not reported: said so')
  eq(availabilityLines(undefined).lines, [], 'no catalogue row: nothing claimed')
}

/* -- 8b. a structured refusal, said whole ----------------------------------- */
{
  const body = { error: 'This needs a request.', kind: 'NotPermitted',
    refusal: { op: 'record_discovered_work', boundary: 'lineage', why: 'This needs a request', recovery: ['contribute(under=...)'], who: 'the owner' } }
  const w = refusalWords(new Refused(403, body))
  ok(w.startsWith('This needs a request.'), 'the server\'s words first')
  ok(w.includes('What you can do instead: contribute(under=...).'), 'recovery said')
  ok(w.includes('Who can lift this: the owner.'), 'who can lift it said')
  ok(w.includes('lineage boundary') && w.includes('record_discovered_work'), 'boundary and op said')
  ok(!/This needs a request\..*This needs a request\./.test(w), 'why already in the words is not repeated')
  eq(refusalWords(new Error('plain')), 'plain', 'a legacy refusal is its words alone')
  eq(refusalWords({ error: 'no', kind: 'X' }), 'no', 'an unstructured body: its words')
}

console.log(`quiet2 status: ${checks} checks passed`)
