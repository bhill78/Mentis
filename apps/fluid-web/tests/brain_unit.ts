/* MANAGE BRAIN IN QUIET CHAT, checked without a server or a browser: the
 * Ladder→plain-words table, the pill and the compact row words (an unknown
 * status is never said as Recorded), the browse read's address and paging,
 * the ONE detail normaliser against the server's real shapes, the words of a
 * record whose Kind keeps them outside `text`, the usage sentence (each
 * verdict by name, inconclusive included, never a score), the owner
 * decision's rules, and what Back says. `fetch` is answered here, as
 * `tests/fluid_workspaces_unit.ts` answers it. */
import assert from 'node:assert/strict'
import {
  BRAIN_PAGE, browseUrl, compactWords, countOf, dedupeById, fetchBrainPage, fetchBrainRecord, fieldWords, isVerdict,
  mapBrainDetail, mapBrainRow, normalizeOutcomes, plainStandingLabel, recordUrl, standingPillLabel, statusWord, verdictLabel, wordsOf,
} from '../src/quiet2/brain/data'
import { kindChoices } from '../src/quiet2/brain/author/model'
import { adoptRefusal, appendPage, backWords, compactStanding, declineRefusal, footWords, kindWords } from '../src/quiet2/brain/logic'
import {
  actWords, challengedFlagWords, countWords, dateOnly, standingDot, stripAt, sublineWords, tierWords, toggleFold, usageWords,
} from '../src/quiet2/brain/recordWords'
import { buildAdoptPayload, type LadderAdoptionRequest } from '../src/fluid/governance/ladderTypes'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }

/* -- fetch, answered here -------------------------------------------------- */
let routes: { match: string; body: unknown }[] = []
const asked: string[] = []
globalThis.fetch = (async (url: string) => {
  const u = String(url)
  asked.push(u)
  const r = routes.find((x) => u.includes(x.match))
  if (!r) throw new Error('unmocked fetch: ' + u)
  return new Response(JSON.stringify(r.body), { status: 200 })
}) as typeof fetch

/* ======================================================================= *
 * 1. The Ladder→plain-words table (DESIGN-r2.md), every row                *
 * ======================================================================= */
eq(plainStandingLabel('adopted', false), "In effect as knowledge — agents are told it when relevant; it doesn't bind them", 'adopted knowledge')
eq(plainStandingLabel('adopted', true), 'In effect — agents are given it as a rule', 'adopted governing')
eq(plainStandingLabel('adoption_requested', true, { by: 'Reviewer' }), 'Not in effect — proposed by Reviewer, waiting for your decision', 'requested, proposer known')
eq(plainStandingLabel('adoption_requested', true), 'Not in effect — proposed, waiting for your decision', 'requested, proposer unknown')
eq(plainStandingLabel('recorded', false), 'Recorded, not adopted (reaches agents only as labelled past experience)', 'recorded')
eq(plainStandingLabel('recorded', false, { kind: 'hypothesis' }), 'Not settled', 'a hypothesis merely recorded')
eq(plainStandingLabel('recorded', true, { kind: 'rule' }), 'Not in effect — recorded, not adopted; it governs nothing and reaches only runs that name it', 'a rule nobody adopted is not said to be in effect, or to reach agents as experience')
eq(plainStandingLabel('adopted', false, { kind: 'hypothesis' }), "In effect as knowledge — agents are told it when relevant; it doesn't bind them", 'an ADOPTED hypothesis is in effect, not "not settled"')
eq(plainStandingLabel('declined', false), 'Not in effect — declined', 'declined')
eq(plainStandingLabel('superseded', true), 'Not in effect — replaced by a later version', 'replaced, successor unknown')
eq(plainStandingLabel('superseded', true, { replacedBy: '“the second wording”' }), 'Not in effect — replaced by “the second wording”', 'replaced, successor named')
eq(plainStandingLabel('deleted', true), 'Not in effect — ended', 'deleted reads as ended')
eq(plainStandingLabel('something-new', true), 'Not in effect', 'an unknown status is the least claim')

/* the pill: the Ladder word, and never "Recorded" for what is not known */
eq(standingPillLabel('adopted', 'lesson', false), 'Adopted · knowledge', 'pill: adopted knowledge')
eq(standingPillLabel('adoption_requested', 'rule', true), 'Adoption requested · rule', 'pill: requested rule')
eq(standingPillLabel('adopted', 'conversation-instruction', true), 'Adopted · conversation instruction', 'pill: a Kind with a hyphen is said in words')
eq(statusWord('declined'), 'Adoption declined', 'declined has its own word')
eq(statusWord('deleted'), 'Ended', 'deleted is Ended')
eq(statusWord('nobody-knows'), 'Unknown', 'an unknown status is Unknown, never Recorded (audit finding 4)')
eq(standingPillLabel('nobody-knows', 'rule', true), 'Unknown · rule', 'pill: unknown stays unknown')

/* the compact row */
eq(compactStanding({ status: 'adopted', kind: 'lesson' }), { status: 'Adopted', words: 'in effect', off: false }, 'row: adopted')
eq(compactStanding({ status: 'recorded', kind: 'hypothesis' }), { status: 'Recorded', words: 'not settled', off: false }, 'row: hypothesis recorded')
eq(compactStanding({ status: 'adopted', kind: 'hypothesis' }).words, 'in effect', 'row: an adopted hypothesis is in effect (audit finding 4)')
eq(compactStanding({ status: 'superseded', kind: 'hypothesis' }).words, 'replaced', 'row: a replaced hypothesis is replaced')
eq(compactStanding({ status: 'declined', kind: 'rule' }), { status: 'Adoption declined', words: 'declined', off: true }, 'row: declined is Declined, not Recorded')
eq(compactStanding({ status: 'mystery', kind: 'rule' }), { status: 'Unknown', words: 'not in effect', off: false }, 'row: unknown')
eq(compactWords('deleted', 'rule'), { words: 'ended', off: true }, 'row: deleted')
eq(kindWords('conversation-instruction'), 'Conversation instruction', 'Kind in words')

/* verdict words */
eq(verdictLabel('worked'), 'Helped', 'worked')
eq(verdictLabel('failed'), "Didn't help", 'failed')
eq(verdictLabel('inconclusive'), 'Unclear', 'inconclusive is said, by name')
eq(verdictLabel('Inconclusive '), 'Unclear', 'case and space do not hide a verdict')
eq(verdictLabel('partial'), 'partial', 'free text passes through')
eq(verdictLabel(null), '', 'nothing is nothing')
ok(isVerdict('failed') && isVerdict('inconclusive') && !isVerdict('partial') && !isVerdict(null), 'the three verdicts, and nothing else')

/* ======================================================================= *
 * 2. The list read                                                         *
 * ======================================================================= */
eq(browseUrl({ view: 'knowledge' }), `/api/ladder/browse?view=knowledge&limit=${BRAIN_PAGE}`, 'the plain page')
eq(browseUrl({ view: 'all', q: '  zebra  ', kind: 'note', status: 'declined', past: true, challenged: true, offset: 50 }),
  `/api/ladder/browse?view=all&limit=${BRAIN_PAGE}&offset=50&q=zebra&kind=note&status=declined&past=1&challenged=1`, 'every narrowing is sent, trimmed')
ok(!browseUrl({ view: 'governing', q: '   ' }).includes('q='), 'blank words are not sent')

const rawRow = {
  id: 'ent-aaa', kind: 'lesson', text: 'Wait for the test.', status: 'declined', governs: false, adoptable: true, challenged: 2, recorded_at: 100,
  recorded_by: { alias: '@Builder', conversation: 'ent-conv', conversation_name: 'Round 4', turn: 'ent-turn', number: 22 },
}
const row = mapBrainRow(rawRow)
eq([row.status, row.standingLabel, row.standingPlain], ['declined', 'Adoption declined · knowledge', 'Not in effect — declined'], 'a declined row is said as declined (audit finding 4)')
eq([row.challenged, row.by, row.conversation, row.turn, row.number], [2, '@Builder', 'ent-conv', 'ent-turn', 22], 'the row keeps who, where and its open challenges')
eq(mapBrainRow({ id: 'ent-b', kind: 'rule', status: 'adopted', governs: true }).text, '', 'a row with no words has none, without failing')

routes = [{ match: '/api/ladder/browse', body: { items: [rawRow], total: 213, past: 4, kinds: [{ kind: 'lesson', count: 13, governs: false }] } }]
const page = await fetchBrainPage({ view: 'knowledge', q: 'wait', offset: 50 })
eq([page.items.length, page.total, page.past, page.kinds[0].kind], [1, 213, 4, 'lesson'], 'the page carries its total, what was left out, and the Kinds present')
ok(asked[asked.length - 1].includes('offset=50') && asked[asked.length - 1].includes('q=wait'), 'the next page is asked for by offset')
eq(footWords(50, 213, 'knowledge'), '50 of 213 records · newest first', 'a short page is not mistaken for a short record (audit finding 8)')
eq(footWords(7, 7, 'all'), '7 records · newest first', 'everything shown')
eq(footWords(1, 1, 'needs-you'), '1 record', 'Needs you is in its own order')
routes = [{ match: '/api/ladder/browse', body: { error: 'view is one of knowledge, governing, needs-you, all' } }]
await assert.rejects(() => fetchBrainPage({ view: 'all' }), /view is one of/, 'a refusal is an error, said in the words given'); checks++

eq(dedupeById([[{ id: 'a' }, { id: 'b' }], [{ id: 'b' }, { id: 'c' }]]).map((r) => r.id), ['a', 'b', 'c'], 'each record once')
eq(appendPage([{ id: 'a' }, { id: 'b' }], [{ id: 'b' }, { id: 'c' }]).map((r) => r.id), ['a', 'b', 'c'], 'the next page joins what is shown; a record that moved between reads is shown once')

/* what can be made, from the Brain's own declaration: "New" lists each Kind
   an owner writes BY NAME, in one fixed order whatever order the server
   answers in; a Kind declared later follows them; one that is not authored
   is not offered */
const kinds = [
  { kind: 'conversation-instruction', authoring: { section: 'instructions', door: 'instruction' } },
  { kind: 'lesson', authoring: { section: 'rules', door: 'entry' } },
  { kind: 'workflow', authoring: { section: 'workflows', door: 'entry' } },
  { kind: 'rule', authoring: { section: 'rules', door: 'entry' } },
  { kind: 'persona', authoring: { section: 'personas', door: 'persona' } },
  { kind: 'discipline', authoring: { section: 'disciplines', door: 'entry' } },
  { kind: 'decision', authoring: { section: 'rules', door: 'entry' } },
  { kind: 'finding', authoring: null },
] as never[]
eq(kindChoices(kinds).map((c) => c.kind), ['rule', 'decision', 'lesson', 'persona', 'workflow', 'discipline', 'conversation-instruction'],
  'the seven Kinds, in the order New lists them, none for a Kind that is not authored')
eq(kindChoices(kinds).map((c) => c.label), ['Rule', 'Decision', 'Lesson', 'Persona', 'Workflow', 'Discipline', 'Conversation instruction'],
  'each by its own name, never by a section')
eq(kindChoices([...kinds, { kind: 'house_style', authoring: { section: 'styles', door: 'entry' } } as never]).map((c) => c.label).slice(7), ['House style'],
  'a Kind declared later follows the seven, in readable words')
eq(kindChoices(kinds.slice(0, 2)).map((c) => c.kind), ['lesson', 'conversation-instruction'], 'only what this Brain declares is offered')
eq(kindChoices([]), [], 'nothing declared, nothing offered')

/* ======================================================================= *
 * 3. The one detail normaliser, against the server's real shapes           *
 * ======================================================================= */
const raw = {
  id: 'ent-rec', kind: 'lesson', text: 'A background test dies with the run.', said: 'A background test dies with the run.',
  fields: { text: 'A background test dies with the run.', limits: 'dispatched runs only', falsifier: 'a test that survives' },
  limits: 'dispatched runs only', status: 'adopted', challenged: 1, governs: false, adoptable: true, recorded_at: 1000,
  recorded_by: { alias: '@Builder', runtime: 'codex', model: null, persona_name: 'Builder', conversation: 'ent-c', conversation_name: 'Round 2', turn: 'ent-t', number: 14 },
  basis: [
    { ref: 'ent-t', relation: 'extracted-from', kind: 'contribution', label: 'The run ended before the test reported', cite: null, where: { conversation: 'ent-c', conversation_name: 'Round 2', turn: 'ent-t', number: 14 } },
    { ref: 'ent-f', relation: 'derived-from', kind: 'finding', label: 'Background tests are not awaited', cite: null },
  ],
  outcomes: [
    { id: 'ent-o1', result: 'worked', attempted: true, text: 'named and followed', in_context: 'ent-t9', recorded_at: 2000, where: { conversation: 'ent-c4', conversation_name: 'Round 4', turn: 'ent-t9', number: 9 } },
    { id: 'ent-o2', result: 'inconclusive', attempted: false, text: 'relayed', in_context: null, recorded_at: 1900, where: null },
  ],
  challenges: [
    { link: 'ent-ch1', objection: 'ent-n1', by: 'ent-rev', by_alias: '@Reviewer', because: 'too broad', evidence: ['ent-e1'], at: 1500, resolution: 'open', withdrawn: null, set_aside: null },
    { link: 'ent-ch2', objection: 'ent-n2', by: 'ent-rev', by_alias: '@Reviewer', because: 'wrong', evidence: [], at: 1400, resolution: 'set_aside', withdrawn: null, set_aside: { link: 'ent-s', by: 'ent-own', by_alias: '@brian', because: 'checked', at: 1450 } },
  ],
  lineage: { up: [{ id: 'ent-t', kind: 'contribution', label: 'The run ended', relation: 'extracted-from', via: 'ent-rec', depth: 1, where: { conversation: 'ent-c', conversation_name: 'Round 2', turn: 'ent-t', number: 14 } }], down: [{ id: 'ent-o1', kind: 'outcome', label: 'named and followed', relation: 'outcome-of', via: 'ent-rec', depth: 1, result: 'worked' }] },
  delivered: [{ execution: 'exe-2', participant_alias: '@Checker', runtime: 'claude', conversation: 'ent-c4', at: 1800, tier: 'adopted' }],
  delivered_total: 1755,
  cited_by: [{ entry: 'ent-o1', kind: 'outcome', relation: 'outcome-of', by: 'ent-x', by_alias: '@Checker', at: 2000, label: 'named and followed' }],
  cited_total: 1,
  superseded_by: [],
  usage: { delivered: 1755, executions: 1700, cited: 1, outcomes_after_delivery: { worked: 1, failed: 0, other: 1, inconclusive: 1 } },
  history: [{ at: 1000, act: 'material-recorded', by: 'ent-b', by_alias: '@Builder', because: null }, { at: 1200, act: 'material-adopted', by: 'ent-own', by_alias: '@brian', because: 'it held twice' }],
  originating: { conversation: 'ent-c', conversation_name: 'Round 2', turn: 'ent-t', number: 14 },
  owner: 'ent-own',
  adoption: {
    requests: [{ request: 'ent-rq', ask: 'opr-1', by: 'ent-rev', by_alias: '@Reviewer', at: 1100, because: 'it held twice', scope: null, replaces: [], closed: true, closed_by: 'adopted' }],
    declines: [],
    adopted: { by: 'ent-own', by_alias: '@brian', at: 1200, because: 'it held twice', scope: { whole_brain: true }, scope_label: 'whole Brain' },
  },
}
const d = mapBrainDetail(raw)
eq([d.id, d.kind, d.status, d.governs, d.challenged], ['ent-rec', 'lesson', 'adopted', false, 1], 'what it is')
eq(d.text, 'A background test dies with the run.', 'its words')
eq(d.fields, [{ name: 'falsifier', value: 'a test that survives' }], 'every other declared field is kept (audit finding 5); the principal words and limits are not repeated')
eq(d.limits, 'dispatched runs only', 'limits')
eq(d.recordedBy, { alias: '@Builder', runtime: 'codex', model: null, personaName: 'Builder' }, 'who recorded it, on what, as whom')
eq(d.originating, { conversation: 'ent-c', conversation_name: 'Round 2', turn: 'ent-t', number: 14 }, 'where it was recorded')
eq(d.basis.map((b) => [b.kind, !!b.where]), [['contribution', true], ['finding', false]], 'a basis that is a post says where the post is')
eq(d.outcomes.map((o) => [o.result, o.attempted, o.where?.number ?? null]), [['worked', true, 9], ['inconclusive', false, null]], 'outcomes: verdict, attempted, and where observed (audit finding 3)')
eq(d.challenges.map((c) => [c.resolution, c.evidence.length, c.answer?.by_alias ?? null]), [['open', 1, null], ['set_aside', 0, '@brian']], 'challenges with their evidence and how they were answered')
eq(d.adoption.requests.map((r) => [r.by_alias, r.because, r.closed_by]), [['@Reviewer', 'it held twice', 'adopted']], 'the adoption request is kept, to be shown (investigation §3)')
eq(d.adoption.adopted, { by: 'ent-own', by_alias: '@brian', at: 1200, because: 'it held twice', scopeLabel: 'whole Brain' }, 'who adopted it, when, why, and its scope')
eq([d.delivered.length, d.deliveredTotal], [1, 1755], 'the delivery list is bounded; the total is still said')
eq(d.citedBy.map((c) => c.label), ['named and followed'], 'what cites it, in its own words')
eq(d.usage?.after, { worked: 1, failed: 0, inconclusive: 1, other: 0 }, 'inconclusive is counted once, under its own name')
eq(d.owner, 'ent-own', 'the owner, for owner-only acts')
eq(d.lineage.up[0].where?.number, 14, 'a lineage post can be gone to')

/* a proposed record: who asked is in the sentence */
const proposed = mapBrainDetail({ ...raw, status: 'adoption_requested', adoption: { requests: [{ ...raw.adoption.requests[0], closed: false, closed_by: null }], declines: [], adopted: null } })
eq(proposed.standingPlain, 'Not in effect — proposed by Reviewer, waiting for your decision', 'the proposer is named')
/* a replaced record names what replaced it; a deleted one is ended */
eq(mapBrainDetail({ ...raw, status: 'superseded', superseded_by: [{ id: 'ent-new', kind: 'lesson', label: 'the second wording', deleted: false }] }).standingPlain,
  'Not in effect — replaced by “the second wording”', 'the successor is named')
eq(mapBrainDetail({ ...raw, status: 'deleted', superseded_by: [{ id: 'ent-del', kind: 'deletion', label: null, deleted: true }] }).standingPlain, 'Not in effect — ended', 'deleted is ended')
/* defensive about what may be missing */
const bare = mapBrainDetail({ id: 'ent-x', kind: 'note', status: 'recorded', governs: false })
eq([bare.text, bare.basis, bare.outcomes, bare.history, bare.usage, bare.adoption.adopted, bare.deliveredTotal, bare.citedTotal], ['', [], [], [], null, null, 0, 0], 'a bare record does not fail')
eq(mapBrainDetail({ ...raw, usage: { delivered: 2, executions: 2, outcomes_after_delivery: null }, cited_by: [{ entry: 'a' }, { entry: 'b' }], cited_total: undefined }).usage,
  { delivered: 2, executions: 2, cited: 2, after: null }, 'never delivered to an outcome: null, not zeros; cited falls back to the list')

/* words that are not in `text` */
eq(wordsOf({ text: '', said: 'Reviewer', fields: { name: 'Reviewer', behaviour: 'review carefully' } }), { words: 'Reviewer', field: 'name' }, 'a Persona has words (audit finding 5)')
const persona = mapBrainDetail({ id: 'ent-p', kind: 'persona', status: 'adopted', governs: true, text: '', said: 'Reviewer', fields: { name: 'Reviewer', behaviour: 'review carefully' } })
eq([persona.text, persona.fields], ['Reviewer', [{ name: 'behaviour', value: 'review carefully' }]], 'its other fields are shown as details')
eq(wordsOf({ text: null, said: null, fields: { steps: ['a', 'b'], title: 'Ship it' } }), { words: 'Ship it', field: 'title' }, 'the first stated field, where the server names none')
eq(wordsOf({ fields: {} }), { words: '', field: null }, 'only a record with no words has none')
eq(fieldWords(['a', 'b']), 'a\nb', 'a list, one per line')
eq(fieldWords({ k: 1 }), '{\n "k": 1\n}', 'anything else as the record holds it')

eq(normalizeOutcomes({ count: 5, latest: [{ id: 'o', result: 'failed' }] }).map((o) => o.result), ['failed'], 'the list shape is tolerated')
eq(normalizeOutcomes(undefined), [], 'no outcomes')
eq([countOf([1, 2]), countOf(4), countOf(null)], [2, 4, 0], 'a count or a list')

routes = [{ match: '/api/ladder/items/ent-rec', body: raw }]
eq((await fetchBrainRecord('ent-rec')).id, 'ent-rec', 'the record is read through the normaliser')
routes = [{ match: '/api/ladder/items/', body: { error: 'the record holds no such entry', entry: 'ent-zzz' } }]
await assert.rejects(() => fetchBrainRecord('ent-zzz'), /no such entry/, 'a missing record is an error'); checks++
eq(recordUrl('ent-rec', 'http://127.0.0.1:8780/quiet2'), 'http://127.0.0.1:8780/quiet2?record=ent-rec', 'Copy link copies an address that opens the record (audit finding 7)')

/* ======================================================================= *
 * 4. The record's words                                                    *
 * ======================================================================= */
eq(stripAt('@Reviewer'), 'Reviewer', 'an alias, plainly')
eq(stripAt(null, 'somebody'), 'somebody', 'nobody named')
eq(dateOnly(null), '', 'no date')
eq([standingDot('adopted'), standingDot('adoption_requested'), standingDot('deleted'), standingDot('superseded'), standingDot('recorded')], ['', 'ask', 'gone', 'gone', 'off'], 'the dot')
ok(sublineWords({ status: 'adopted', governs: false, adoptedBy: '@brian', adoptedAt: 1200, scopeLabel: 'whole Brain' }).startsWith('Adopted by brian'), 'who adopted it')
ok(sublineWords({ status: 'adopted', governs: false, adoptedBy: '@brian', adoptedAt: 1200, scopeLabel: 'whole Brain' }).endsWith('· whole Brain'), 'and its scope')
eq(sublineWords({ status: 'adoption_requested', governs: true }), 'If adopted, agents are given it as a rule they must follow.', 'what adopting a rule would do')
eq(sublineWords({ status: 'adoption_requested', governs: false }), "If adopted, agents are told it when relevant; it doesn't bind them.", 'what adopting knowledge would do')
ok(sublineWords({ status: 'recorded', governs: false, recordedBy: '@Builder', recordedAt: 0 }).startsWith('Recorded by Builder'), 'who recorded it')
ok(sublineWords({ status: 'deleted', governs: true }).startsWith('Ended'), 'deleted is ended')
eq([actWords('material-adopted'), actWords('adoption-requested'), actWords('material-frobnicated')], ['Adopted', 'Adoption requested', 'Frobnicated'], 'acts, in words; an unknown one is still said')
eq([countWords(0, 'source'), countWords(1, 'source'), countWords(3, 'outcome')], ['none', '1 source', '3 outcomes'], 'counts')
eq([challengedFlagWords(0), challengedFlagWords(1), challengedFlagWords(3)], [null, '1 open challenge', '3 open challenges'], 'challenged is a flag, not a status')
eq([...toggleFold(new Set(['a']), 'b')].sort(), ['a', 'b'], 'several sections can be open')
eq([...toggleFold(new Set(['a', 'b']), 'a')], ['b'], 'and closed again')
eq([tierWords('governing'), tierWords('adopted'), tierWords('experience'), tierWords(null)], ['as a rule', 'as adopted knowledge', 'as past experience', ''], 'how it was given')

/* usage: counts of records, each verdict by name, never a score */
eq(usageWords('lesson', null, 0), 'Not given to any run yet.', 'never given')
eq(usageWords('lesson', { delivered: 5, after: { worked: 2, failed: 0, inconclusive: 1, other: 0 } }, 3),
  "Given to 5 runs. Being given a lesson doesn't mean a run used it. Outcomes recorded since it was first given: 2 worked · 1 inconclusive. 3 later records cite it.", 'inconclusive is said by name (investigation §2.12)')
eq(usageWords('rule', { delivered: 1, after: { worked: 0, failed: 0, inconclusive: 0, other: 0 } }, 0),
  "Given to 1 run. Being given a rule doesn't mean a run used it. No outcome has been recorded since it was first given.", 'given, nothing recorded since')
ok(!/\d+\s*%|score|rating/i.test(usageWords('lesson', { delivered: 9, after: { worked: 4, failed: 3, inconclusive: 1, other: 1 } }, 2)), 'no score, no percentage')

/* ======================================================================= *
 * 5. The owner decision uses the authoritative payload                     *
 * ======================================================================= */
const req = {
  request: 'ent-rq', ask: 'opr-1', entry: 'ent-h', kind: 'hypothesis', governs: false, expects_falsifier: true,
  wording: { proposed: 'the cache is stale', current: null, proposed_body: { text: 'the cache is stale', limits: 'dev only', falsifier: 'a fresh read' } },
  replaces: [{ id: 'ent-old', text: 'old', since: 1 }], scope: null, limits: 'dev only', evidence: [], challenges: [],
  asked_by: {} as never, asked_at: 1, conversation: null, turn: null, number: null,
} as LadderAdoptionRequest
eq(adoptRefusal(req, ''), 'A hypothesis is adopted with a falsifier: say what would show it wrong.', 'a Kind that owes a falsifier is asked for one (audit finding 2)')
eq(adoptRefusal(req, 'a fresh read'), null, 'with one, it may be adopted')
eq(adoptRefusal({ ...req, expects_falsifier: false }, ''), null, 'a Kind that owes none is not asked')
eq(declineRefusal('  '), 'Say why first: a decline is recorded with its reason.', 'a decline needs its reason, and the form says so')
eq(declineRefusal('not yet'), null, 'with one, it may be declined')
const edited = buildAdoptPayload(req, { me: 'ent-own', because: 'ok', editedText: 'the cache is always stale', scope: 'when_named', falsifier: 'a fresh read' })
eq(edited.body, { text: 'the cache is always stale', limits: 'dev only', falsifier: 'a fresh read' }, 'edited wording keeps every other proposed field (audit finding 2)')
eq([edited.scope, edited.replaces, edited.falsifier], [{ whole_brain: false }, ['ent-old'], 'a fresh read'], 'scope, what it replaces and the falsifier travel with it')
ok(!('body' in buildAdoptPayload(req, { me: 'ent-own', because: 'ok', editedText: 'the cache is stale' })), 'unchanged wording sends no body')

/* ======================================================================= *
 * 6. Back says where it goes                                               *
 * ======================================================================= */
eq(backWords({ stack: [{ page: 'record', entry: 'ent-a' }], origin: { from: 'browser', label: 'Needs you' } }), 'Brain · Needs you', 'back to the browser, with its filter')
eq(backWords({ stack: [{ page: 'record', entry: 'ent-a' }], origin: { from: 'post', post: 'ent-p', label: 'Back to #22' } }), 'Back to #22', 'back to the exact post')
eq(backWords({ stack: [{ page: 'record', entry: 'ent-a' }, { page: 'record', entry: 'ent-b' }], origin: { from: 'browser', label: 'All' } }), 'Back to the record before', 'a record reached from a record goes back to it')
eq(backWords({ stack: [{ page: 'record', entry: 'ent-a' }], origin: { from: 'link' } }), 'Back to the conversation', 'opened by address')

console.log(`brain_unit: ${checks} checks passed`)
