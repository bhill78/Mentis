/* THE BRAIN BROWSER'S DATA LAYER (quiet2/brain/data.ts), checked without a
 * server: the Ladder→plain-words table, the verdict words, the dedup that
 * makes "All" never show a record twice, the detail endpoint's real shapes
 * (`outcomes` and `cited_by` as arrays, never the list endpoint's counts),
 * and each filter's actual read, with `fetch` answered here exactly as
 * `tests/fluid_workspaces_unit.ts` answers it -- no server, no subprocess. */
import assert from 'node:assert/strict'
import {
  countOf,
  dedupeById,
  fetchBrainList,
  fetchBrainRecord,
  mapBrainDetail,
  normalizeOutcomes,
  plainStandingLabel,
  standingPillLabel,
  verdictLabel,
} from '../src/quiet2/brain/data'
import { store } from '../src/fluid/store'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }

/* -- fetch, answered here (as fluid_workspaces_unit.ts) -------------------- */
type RouteEntry = { match: string; body: unknown }
let routes: RouteEntry[] = []
const route = (match: string, body: unknown) => { routes.push({ match, body }) }
const resetRoutes = () => { routes = [] }
globalThis.fetch = (async (url: string) => {
  const u = String(url)
  const r = routes.find((x) => u.includes(x.match))
  if (!r) throw new Error('unmocked fetch: ' + u)
  return new Response(JSON.stringify(r.body), { status: 200 })
}) as typeof fetch

/* ======================================================================= *
 * 1. plainStandingLabel -- the Ladder→plain-words table, every row         *
 * ======================================================================= */
eq(plainStandingLabel('adopted', false),
  "In effect as knowledge — agents are told it when relevant; it doesn't bind them",
  'adopted knowledge (that)')
eq(plainStandingLabel('adopted', true),
  'In effect — agents are given it as a rule',
  'adopted governing (how)')
eq(plainStandingLabel('adoption_requested', false),
  'Not in effect — proposed, waiting for your decision',
  'adoption_requested, no asker known to this pure function')
eq(plainStandingLabel('adoption_requested', true, { by: '@brian' }),
  'Not in effect — proposed by @brian, waiting for your decision',
  'adoption_requested, proposed by X')
eq(plainStandingLabel('recorded', false),
  'Recorded, not adopted (reaches agents only as labelled past experience)',
  'recorded')
eq(plainStandingLabel('recorded', false, { kind: 'hypothesis' }),
  'Not settled',
  'hypothesis, recorded is its own row of the table')
eq(plainStandingLabel('recorded', true, { kind: 'rule' }),
  'Recorded, not adopted (reaches agents only as labelled past experience)',
  'recorded, a non-hypothesis Kind, governing or not, gets the plain recorded sentence')
eq(plainStandingLabel('declined', false), 'Not in effect — declined', 'declined')
eq(plainStandingLabel('superseded', true), 'Not in effect — replaced by a later version', 'superseded')
eq(plainStandingLabel('ended', true), 'Not in effect — ended', 'ended')
eq(plainStandingLabel('retired', false), 'Not in effect — ended', 'retired is said as ended')
eq(plainStandingLabel('some-unheard-status', false), 'Not in effect', 'an unknown status never crashes; it is simply not in effect')

/* standingLabel: the short pill beside the plain-language line */
eq(standingPillLabel('adopted', 'lesson', false), 'Adopted · knowledge', 'pill for a working position')
eq(standingPillLabel('adoption_requested', 'rule', true), 'Adoption requested · rule', 'pill for governing material names the Kind')

/* ======================================================================= *
 * 2. verdictLabel -- worked/failed/inconclusive, and free text unharmed    *
 * ======================================================================= */
eq(verdictLabel('worked'), 'Helped', 'worked -> Helped')
eq(verdictLabel('failed'), "Didn't help", 'failed -> Didn’t help')
eq(verdictLabel('inconclusive'), 'Unclear', 'inconclusive -> Unclear')
eq(verdictLabel('partial'), 'partial', 'live free text (investigation.md §6.4) passes through unchanged')
eq(verdictLabel('Runnable hands-on preview delivery met'), 'Runnable hands-on preview delivery met', 'longer free text also passes through, never "undefined"')

/* ======================================================================= *
 * 3. dedupeById -- the 'All' filter's union, never a record twice          *
 * ======================================================================= */
eq(dedupeById([[{ id: '1' }, { id: '2' }], [{ id: '2' }, { id: '3' }]]).map((r) => r.id),
  ['1', '2', '3'], 'first occurrence wins; order is the lists’ own order')
eq(dedupeById<{ id: string }>([[], []]), [], 'nothing in either list dedupes to nothing')
eq(dedupeById([[{ id: 'x' }]]), [{ id: 'x' }], 'one list, nothing to dedupe against')

/* ======================================================================= *
 * 4. outcomes / cited_by: array (detail) vs {count,latest}/number (list)   *
 * ======================================================================= */
eq(normalizeOutcomes([{ id: 'o1', result: 'worked', attempted: true, text: 't', in_context: 'ent-x', recorded_at: 5 }]),
  [{ id: 'o1', result: 'worked', attempted: true, text: 't', in_context: 'ent-x', recorded_at: 5 }],
  'the detail endpoint’s real shape: a flat array, passed through coerced')
eq(normalizeOutcomes({ count: 1, latest: [{ id: 'o2', result: 'partial', attempted: false, text: null, in_context: null, recorded_at: null }] }),
  [{ id: 'o2', result: 'partial', attempted: false, text: '', in_context: '', recorded_at: 0 }],
  'the LIST endpoint’s {count,latest} shape is flattened, never mistaken for the detail array')
eq(normalizeOutcomes({ count: 1, all: [{ id: 'o3', result: 'failed', attempted: true, text: 't3', in_context: 'ent-y', recorded_at: 9 }] }),
  [{ id: 'o3', result: 'failed', attempted: true, text: 't3', in_context: 'ent-y', recorded_at: 9 }],
  '{all}, where a server sends it, is read over {latest}')
eq(normalizeOutcomes(null), [], 'null never crashes the mapping')
eq(normalizeOutcomes(undefined), [], 'undefined never crashes the mapping')
eq(normalizeOutcomes('garbage'), [], 'a string is not an outcomes shape and yields nothing, not a throw')

eq(countOf([1, 2, 3]), 3, 'cited_by as an array (detail endpoint): its length')
eq(countOf(4), 4, 'cited_by as a count (list endpoint): itself')
eq(countOf(null), 0, 'cited_by missing: zero, never a crash')
eq(countOf('x'), 0, 'cited_by of an unexpected shape: zero, never a crash')

/* ======================================================================= *
 * 5. mapBrainDetail -- the whole §6.2 shape, mapped                        *
 * ======================================================================= */
const rawDetail = {
  id: 'ent-item1', kind: 'rule', text: 'Always do X', status: 'adopted', challenged: 1, governs: true,
  recorded_by: { conversation: 'ent-conv', turn: 'ent-turn', number: 12 },
  basis: [{ ref: 'ent-basis1', relation: 'derived-from', kind: 'contribution', label: 'the turn', cite: null }],
  outcomes: [{ id: 'ent-o1', result: 'worked', attempted: true, text: 'it worked', in_context: 'ent-turn2', recorded_at: 42 }],
  cited_by: [{ entry: 'ent-cited1', kind: 'lesson', relation: 'derived-from', by: 'ent-p2', at: 5 }],
  challenges: [
    { link: 'ent-ch1', objection: 'ent-obj1', by: 'ent-p3', by_alias: '@X', because: 'too broad', at: 10, resolution: 'open', set_aside: null },
    { link: 'ent-ch2', objection: null, by: 'ent-p4', by_alias: '@Y', because: 'fixed', at: 11, set_aside: { link: 'ent-sa', by: 'ent-owner', by_alias: '@brian', because: 'ok', at: 12 } },
  ],
  lineage: { up: [{ id: 'ent-u1' }], down: [] },
  history: [{ at: 1, act: 'material-recorded', by: 'ent-p', by_alias: '@Caretaker', because: null }],
  originating: { conversation: 'ent-conv', conversation_name: 'Conv', turn: 'ent-turn', number: 12 },
  adoption: { requests: [], declines: [], adopted: { by: 'ent-owner', at: 20, because: 'good rule' } },
  usage: { delivered: 5, executions: 5, cited: 1, outcomes_after_delivery: { worked: 1, failed: 0, other: 0 } },
}
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const d = mapBrainDetail(rawDetail as any)
eq(d.id, 'ent-item1', 'detail carries the summary fields too')
eq(d.standingLabel, 'Adopted · rule', 'adopted + governing pill names the Kind')
eq(d.standingPlain, 'In effect — agents are given it as a rule', 'adopted + governing sentence')
eq(d.challenged, true, 'challenged > 0 -> true')
eq(d.outcomes, [{ id: 'ent-o1', result: 'worked', attempted: true, text: 'it worked', in_context: 'ent-turn2', recorded_at: 42 }],
  'the detail’s own array, not {count,latest}')
eq(d.challenges[0].resolution, 'open', 'no set_aside, no withdrawn -> open')
eq(d.challenges[1].resolution, 'set_aside', 'a set_aside answer resolves it')
eq(d.history[0].by_alias, '@Caretaker', 'by_alias, which HistoryRecord in ladderTypes.ts does not declare, is still read')
eq(d.usage, { delivered: 5, executions: 5, cited: 1, outcomes_after_delivery: { worked: 1, failed: 0, other: 0 } }, 'usage carried through as the server sent it')

const rawDetailCitedFallback = { ...rawDetail, usage: { delivered: 2, executions: 2, outcomes_after_delivery: null }, cited_by: [{ entry: 'a' }, { entry: 'b' }, { entry: 'c' }] }
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const dCited = mapBrainDetail(rawDetailCitedFallback as any)
eq(dCited.usage?.cited, 3, 'usage.cited missing -> falls back to the real cited_by array’s length, never a crash')
eq(dCited.usage?.outcomes_after_delivery, null, 'never delivered to an outcome yet, said as null, not zeros')

const rawDetailNeverDelivered = { ...rawDetail, usage: null }
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const dNever = mapBrainDetail(rawDetailNeverDelivered as any)
eq(dNever.usage, null, 'usage null (never delivered, §6.2) stays null, not zeros')

/* ======================================================================= *
 * 6. fetchBrainList('knowledge') -- governs === false, items + adopted     *
 * ======================================================================= */
resetRoutes()
route('/api/ladder/items', {
  items: [
    { id: 'ent-k1', kind: 'lesson', text: 'K1', status: 'recorded', challenged: 0, governs: false, recorded_by: { conversation: 'ent-c1', turn: 'ent-t1', number: 1 } },
    { id: 'ent-k2', kind: 'rule', text: 'K2', status: 'recorded', challenged: 0, governs: true, recorded_by: { conversation: null, turn: null, number: null } },
  ],
  total: 2, counts: {},
})
route('/api/ladder/adopted', {
  items: [
    { id: 'ent-k3', kind: 'hypothesis', text: 'K3', status: 'adopted', challenged: 0, governs: false, recorded_by: { conversation: 'ent-c3', turn: null, number: null } },
  ],
})
const knowledge = await fetchBrainList('knowledge', '')
eq(knowledge.map((r) => r.id), ['ent-k1', 'ent-k3'], 'governing K2 excluded; items and adopted merged')
eq(knowledge[1].standingPlain, "In effect as knowledge — agents are told it when relevant; it doesn't bind them", 'K3 is adopted knowledge')

/* ======================================================================= *
 * 7. fetchBrainList('governing') -- /api/governed, kept to Kinds that      *
 *    direct work (not a hard-coded list, and not the register's           *
 *    lesson/hypothesis, which are knowledge Kinds the register also walks)*
 * ======================================================================= */
resetRoutes()
route('/api/governance/authoring', {
  kinds: [
    { kind: 'rule', authoring: { placement_directs_work: true } },
    { kind: 'lesson', authoring: { placement_directs_work: false } },
    { kind: 'persona', authoring: { placement_directs_work: true } },
  ],
})
const governedRow = (over: Record<string, unknown>) => ({
  entry: '', kind: '', state: null, group: 'recorded', summary: '', secondary: '',
  attributed_to: null, author_alias: null, at: 1, established_by: [], superseded_by: [],
  disputed_by: [], open_disputes: [], placed_at: [], proposed_by: [], ...over,
})
route('/api/governed', {
  groups: {
    standing: [governedRow({ entry: 'ent-g1', kind: 'rule', state: 'stands', group: 'standing', summary: 'Rule G1' })],
    proposed: [governedRow({
      entry: 'ent-g2', kind: 'rule', state: 'candidate', group: 'proposed', summary: 'Rule G2',
      open_disputes: ['ent-d1'],
      proposed_by: [{ act: 'opr-1', actor: 'ent-p', actor_alias: '@brian', conversation: 'ent-c2', conversation_name: 'Conv2', turn: 'ent-t2' }],
    })],
    recorded: [governedRow({ entry: 'ent-g3', kind: 'lesson', state: 'candidate', group: 'recorded', summary: 'Lesson G3' })],
    history: [governedRow({ entry: 'ent-g4', kind: 'persona', state: 'ended', group: 'history', summary: 'Persona G4', disputed_by: ['ent-d2'] })],
    unknown: [],
  },
})
const governing = await fetchBrainList('governing', '')
eq(governing.map((r) => r.id).sort(), ['ent-g1', 'ent-g2', 'ent-g4'], 'ent-g3 (lesson, a knowledge Kind) is excluded though the register lists it')
const g2 = governing.find((r) => r.id === 'ent-g2')!
ok(g2, 'the proposed rule is present')
eq(g2.standingPlain, 'Not in effect — proposed, waiting for your decision', 'candidate grouped as "proposed" by the register -> adoption_requested words')
eq(g2.challenged, true, 'open_disputes present -> challenged')
const g1 = governing.find((r) => r.id === 'ent-g1')!
eq(g1.standingPlain, 'In effect — agents are given it as a rule', 'stands -> adopted, and it governs')
const g4 = governing.find((r) => r.id === 'ent-g4')!
eq(g4.standingPlain, 'Not in effect — ended', 'ended register state')

/* ======================================================================= *
 * 8. fetchBrainList('all') -- Knowledge ∪ Governing, never a record twice  *
 * ======================================================================= */
resetRoutes()
route('/api/ladder/items', { items: [
  { id: 'ent-shared', kind: 'note', text: 'Shared, as knowledge', status: 'recorded', challenged: 0, governs: false, recorded_by: { conversation: null, turn: null, number: null } },
], total: 1, counts: {} })
route('/api/ladder/adopted', { items: [] })
route('/api/governance/authoring', { kinds: [{ kind: 'rule', authoring: { placement_directs_work: true } }] })
route('/api/governed', { groups: { standing: [governedRow({ entry: 'ent-shared', kind: 'rule', state: 'stands', group: 'standing', summary: 'Shared, as a rule too' })] } })
const all = await fetchBrainList('all', '')
eq(all.length, 1, 'one id, read from both Knowledge and Governing, is one row')
eq(all[0].text, 'Shared, as knowledge', 'the first list in the union (Knowledge) wins the duplicate')

/* ======================================================================= *
 * 9. fetchBrainRecord -- GET /api/ladder/items/<id>                        *
 * ======================================================================= */
resetRoutes()
route('/api/ladder/items/ent-rec1', {
  id: 'ent-rec1', kind: 'decision', text: 'Decide Y', status: 'recorded', challenged: 0, governs: true,
  recorded_by: { conversation: 'ent-conv9', turn: 'ent-turn9', number: 3 },
  basis: [], outcomes: [], cited_by: [], challenges: [], lineage: { up: [], down: [] }, history: [],
  originating: { conversation: 'ent-conv9', conversation_name: 'Conv9', turn: 'ent-turn9', number: 3 },
  adoption: { requests: [], declines: [], adopted: null },
  usage: null,
})
const rec = await fetchBrainRecord('ent-rec1')
eq(rec.id, 'ent-rec1', 'fetchBrainRecord reads /api/ladder/items/<id>')
eq(rec.usage, null, 'never delivered')
eq(rec.standingLabel, 'Recorded · decision', 'recorded + governing pill names the Kind')

/* ======================================================================= *
 * 10. fetchBrainList('needs-you') -- the SAME data the dock/column reads:  *
 *     /api/ladder/adoption and /api/owed (resolved to the material it     *
 *     names through the Turn it hangs on, as askCoverage.ts's             *
 *     useAskCoverage does), never a second "needs you".                   *
 * ======================================================================= */
resetRoutes()
;(store as unknown as { loadMe: () => Promise<string> }).loadMe = async () => 'ent-me'
route('/api/ladder/adoption', {
  requests: [{
    request: 'ent-req1', ask: 'ent-ask1', entry: 'ent-n1', kind: 'rule', governs: true,
    wording: { proposed: 'Proposed wording', current: null },
    replaces: [], scope: null, limits: null, evidence: [], challenges: [],
    asked_by: { alias: '@brian' }, asked_at: 1,
    conversation: 'ent-convN', turn: 'ent-turnN', number: 9,
  }],
})
route('/api/owed', { owed: [{ expectation: 'ent-exp1', turn: 'ent-turnM' }] })
route('/api/turns/ent-turnM', { expectations: [{ id: 'ent-exp1', material: ['ent-n2'] }] })
route('/api/ladder/items/ent-n2', {
  id: 'ent-n2', kind: 'persona', text: 'A persona', status: 'recorded', challenged: 0, governs: true,
  recorded_by: { conversation: null, turn: null, number: null },
  basis: [], outcomes: [], cited_by: [], challenges: [], lineage: { up: [], down: [] }, history: [],
  originating: {}, adoption: { requests: [], declines: [], adopted: null }, usage: null,
})
const needsYou = await fetchBrainList('needs-you', '')
eq(needsYou.map((r) => r.id).sort(), ['ent-n1', 'ent-n2'], 'the adoption request and the owed-ask-named material, nothing invented')
const req = needsYou.find((r) => r.id === 'ent-n1')!
eq(req.standingPlain, 'Not in effect — proposed by @brian, waiting for your decision', 'the adoption request names who asked')
const named = needsYou.find((r) => r.id === 'ent-n2')!
eq(named.kind, 'persona', 'the named item is read through fetchBrainRecord, so it carries its real Kind and text')

console.log(`brain data unit ok (${checks} checks)`)
