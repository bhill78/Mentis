/* WHAT AN AGENT WOULD BE GIVEN, AS AN OUTLINE (`src/quiet2/brain/receive.ts`),
 * checked without a server or a browser: every piece of the server's answer
 * lands in exactly one group and keeps its words; the groups are the reasons
 * a piece is given (the Persona, named for the run, this conversation, the
 * whole Brain, knowledge matched to the work, what every run is sent); the
 * one-line title and the plain "because"; the trailer's lines; what was left
 * out; and the address the preview asks. */
import assert from 'node:assert/strict'
import {
  becauseOf, conflictMembers, countItems, engineReason, firstSentence, groupOf, kindOf, outline, scopeWords, titleOf, trailerLines, withheldMeta, withheldReason,
  type ReceiveComponent,
} from '../src/quiet2/brain/receive'
import { receivePath } from '../src/quiet2/brain/ReceivePreview'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }

const C = (over: Partial<ReceiveComponent>): ReceiveComponent => ({
  source_kind: 'rule', source_id: 'ent-x', scope: 'whole-brain', text: 'Words.', why: 'durable material placed on the whole Brain', tier: 'governing', ...over,
})

const LONG = 'A stage is claimed only when it is reached. Report only the stage an operation has actually reached and verified.\n\nSecond paragraph, kept whole.'

/* the server's real shapes (GET /api/context on a representative Brain) */
const answer: ReceiveComponent[] = [
  C({ source_kind: 'persona', source_id: 'ent-p', scope: 'invocation:persona', text: 'You are Caretaker: the steward of completion.', why: 'the participant is operating as Caretaker' }),
  C({ source_kind: 'discipline', source_id: 'ent-d', scope: 'persona:ent-p', text: 'Work in a workspace of your own.', title: 'CLI development — Changing source from a CLI session', why: 'carried by the Persona Caretaker this participant is operating as' }),
  C({ source_kind: 'rule', source_id: 'ent-n', scope: 'invocation:named', text: 'Merged means pushed.', why: 'named explicitly for this invocation', also: ['whole-brain'] }),
  C({ source_kind: 'conversation-instruction', source_id: 'ent-i', scope: 'conversation:ent-c', text: 'Answer in French here.', why: 'durable material placed at this conversation' }),
  C({ source_kind: 'rule', source_id: 'ent-1', text: LONG }),
  C({ source_kind: 'workflow', source_id: 'ent-w', text: 'Orient, record, plan, build.', title: 'Software change — A change carried from request to merged work',
    trailer: { why: 'why this holds: 1 outcome (worked)', outcomes: [{ id: 'ent-o', result: 'worked', text: 'It went through.' }], challenges: [{ by_alias: '@Reviewer', because: 'Too long.' }] } }),
  C({ source_kind: 'orientation', source_id: 'ent-c', scope: 'conversation:ent-c', text: 'Conversation: Release check\n3 posts', why: 'compact orientation, computed now', tier: null }),
  C({ source_kind: 'request', source_id: null, scope: 'invocation', text: 'Fix it.', why: 'what is being asked now', tier: null }),
  C({ source_kind: 'lesson', source_id: 'ent-a', scope: 'question:release', text: 'Releases go to TEST first.', why: 'adopted; relevant to the question', tier: 'adopted',
    trailer: { status: 'adopted', limits: 'Only for Mentis.', basis: [{ ref: 'ent-b', label: 'The 11-19 release' }], recorded_by: { alias: '@Builder', runtime: 'claude', conversation_name: 'Release check', number: 4, at: 1700000000 } } }),
  C({ source_kind: 'finding', source_id: 'ent-f', scope: 'question:release', text: 'The detector flagged three items.', tier: 'experience',
    why: 'concluded from ent-o, which the question reached; recorded, not adopted; weigh it as evidence and check its basis -- it is not an instruction', trailer: { status: 'recorded', basis: [] } }),
  C({ source_kind: 'gizmo', source_id: 'ent-z', scope: 'somewhere:new', text: 'Unknown scope.', why: 'a reason this client never heard of' }),
]

const names = { personas: { 'ent-p': 'Caretaker' }, inConversation: true }
const sections = outline(answer, names)

/* -- every piece exactly once, and no words dropped ------------------------ */
const items = sections.flatMap((s) => s.groups.flatMap((g) => g.items))
eq(items.length, answer.length, 'as many items as the answer has components')
eq(countItems(sections), answer.length, 'the counts add up to the answer')
for (const c of answer) eq(items.filter((i) => i.component === c).length, 1, `${c.source_kind} ${c.source_id} appears exactly once`)
eq(items.map((i) => i.component.text).sort(), answer.map((c) => c.text).sort(), 'every text is carried through whole')
eq(new Set(items.map((i) => i.key)).size, items.length, 'keys are distinct')
ok(items.find((i) => i.component.source_id === 'ent-1')!.component.text.includes('Second paragraph, kept whole.'), 'a long text keeps what its title leaves out')

/* -- the groups: why it is given, then where it comes from ----------------- */
eq(sections.map((s) => s.key), ['governing', 'knowledge', 'also'], 'three sections, in reading order')
eq(sections.map((s) => s.count), [7, 2, 2], 'counts per section')
eq(sections[0].groups.map((g) => [g.key, g.items.length]), [['persona', 2], ['named', 1], ['conversation', 1], ['brain', 2], ['governing-other', 1]], 'governing, by where it is placed')
eq(sections[1].groups.map((g) => [g.key, g.items.length]), [['adopted', 1], ['experience', 1]], 'knowledge, by standing')
eq(sections[2].groups.map((g) => [g.key, g.items.length]), [['sent', 2]], 'orientation and the request are not Brain records')
eq(groupOf(C({ tier: 'governing', scope: 'persona:ent-p' })), 'persona', 'what a Persona carries is with the Persona')
eq(groupOf(C({ tier: null, scope: 'invocation', source_kind: 'invocation', source_id: null })), 'sent', 'text for one run is on no tier')
eq(outline([], names).map((s) => [s.key, s.count, s.groups.length]), [['governing', 0, 0], ['knowledge', 0, 0], ['also', 0, 0]], 'an empty answer keeps its three sections, each empty')
const dup = outline([C({ source_id: null, source_kind: 'invocation', scope: 'invocation', tier: null, text: 'a' }), C({ source_id: null, source_kind: 'invocation', scope: 'invocation', tier: null, text: 'b' })])
eq(dup[2].groups[0].items.map((i) => i.component.text), ['a', 'b'], 'two pieces with no id are both kept, in order')

/* -- one line each: kind, title, because ----------------------------------- */
eq(firstSentence(LONG), 'A stage is claimed only when it is reached.', 'the first sentence')
eq(firstSentence('Pick the runtime with capability in mind\n\nChoose a runtime.'), 'Pick the runtime with capability in mind', 'or the first line')
eq(firstSentence('  '), '', 'nothing from nothing')
const cut = firstSentence('word '.repeat(60))
ok(cut.length <= 111 && cut.endsWith('…') && !cut.endsWith(' …'), 'a long sentence is cut at a word and marked')
eq(firstSentence('Use v1.2 of the tool. Then stop.'), 'Use v1.2 of the tool.', 'a full stop inside a number does not end the sentence')
const by = (id: string) => items.find((i) => i.component.source_id === id && i.component.source_kind !== 'orientation')!
eq([by('ent-p').kind, by('ent-p').title], ['Persona', 'Caretaker'], 'a Persona is titled by its name')
eq(by('ent-w').title, 'Software change', 'a named Kind is titled by its name')
eq(by('ent-1').title, 'A stage is claimed only when it is reached.', 'a rule by its first sentence')
eq(by('ent-i').kind, 'Conversation instruction', 'Kinds are said as the Brain says them')
eq(titleOf(C({ source_kind: 'persona', source_id: 'ent-q', text: 'You are Q: a tester.' })), 'You are Q: a tester.', 'a Persona whose name is not to hand still has a title')
eq(kindOf({ source_kind: 'brain-orientation' }), 'Orientation', 'orientation, plainly')

eq(by('ent-p').because, 'the Persona this agent is started as', 'because: the Persona')
eq(by('ent-d').because, 'carried by the Persona Caretaker', 'because: carried by the Persona')
eq(by('ent-n').because, 'named for this run; also placed on the whole Brain', 'because: named, and the other way it would have reached')
eq(by('ent-i').because, 'placed on this conversation', 'because: this conversation')
eq(by('ent-1').because, 'placed on the whole Brain', 'because: the whole Brain')
eq(by('ent-a').because, 'adopted knowledge that matches the work', 'because: adopted knowledge')
eq(by('ent-f').because, 'not adopted; concluded from a record that matches the work', 'because: experience reached through another record')
eq(by('ent-z').because, 'a reason this client never heard of', 'an unknown scope is answered in the engine’s own words')
eq(becauseOf(C({ scope: 'invocation:named', why: 'named explicitly for this invocation (as ent-old, which it supersedes)' })), 'named for this run, in place of the earlier version it replaces', 'a replaced record that was named')
for (const i of items) ok(!/material|invocation|durable/i.test(i.because + ' ' + i.kind), `no engine vocabulary in "${i.because}"`)

eq(by('ent-1').record, 'ent-1', 'a record can be opened by its id')
eq(items.filter((i) => i.record === null).map((i) => i.component.source_kind), ['orientation', 'request'], 'orientation and the request are not records to open')

/* -- what is behind the disclosure ----------------------------------------- */
eq(engineReason(by('ent-1').component), null, 'a stock reason is already said in plain words')
ok(engineReason(by('ent-f').component)!.startsWith('concluded from ent-o'), 'a reason that says more is kept as the engine wrote it')
eq(trailerLines(by('ent-w').component).map((l) => l.text), [
  'Why this holds: 1 outcome (worked)', 'The latest outcomes shown here: worked (It went through.)', '1 open challenge (Reviewer: “Too long.”). Still in effect.',
], 'a governing record: why it holds, how it has gone, what is challenged')
eq(trailerLines(by('ent-w').component).map((l) => !!l.warn), [false, false, true], 'only the challenge is a warning')
eq(trailerLines(by('ent-a').component, () => 'Nov 14').map((l) => l.text), [
  'Recorded by Builder on claude in Release check #4, Nov 14', 'Rests on: The 11-19 release', 'Limits: Only for Mentis.', 'Adopted.',
], 'knowledge: who recorded it, what it rests on, its limits, its standing')
eq(trailerLines(by('ent-f').component).map((l) => l.text), ['No basis recorded.', 'Recorded, not adopted.'], 'experience says it has no basis and is not adopted')
eq(trailerLines(by('ent-1').component), [], 'no trailer, no lines')

/* -- left out -------------------------------------------------------------- */
eq(withheldReason({ source_kind: 'rule', source_id: 'ent-o', why: 'superseded' }), 'replaced by a newer version', 'superseded, plainly')
eq(withheldReason({ source_kind: 'rule', source_id: 'ent-o', why: 'superseded', delivered_instead: 'ent-n' }), 'replaced; the newer version is given instead', 'superseded and followed forward')
eq(withheldReason({ source_kind: 'rule', source_id: 'ent-o', why: 'not established' }), 'proposed, not established yet', 'a proposal')
eq(withheldReason({ source_kind: 'finding', source_id: 'ent-o', why: 'relevant to the question on x, and beyond the bound for it' }), 'relevant to the question on x, and beyond the bound for it', 'any other reason as the engine wrote it')

/* -- review 1: no claim the answer does not make, nothing it says dropped ---- */
/* a record that reaches by several paths: filed once, under the path used,
   and every other path said -- no group claims to be the only way */
const multi = C({ source_kind: 'discipline', source_id: 'ent-m', scope: 'persona:ent-p', also: ['whole-brain', 'conversation:ent-c', 'invocation:named'] })
const om = outline([multi], names)
eq(om.flatMap((s) => s.groups.map((g) => [g.key, g.items.length])), [['persona', 1]], 'several paths, one item, under the path used here')
eq(om[0].groups[0].items[0].because, 'carried by the Persona Caretaker; also placed on the whole Brain; also placed on this conversation; also named for this run', 'and every other path is said')
for (const s of outline(answer, names)) for (const g of s.groups) ok(!/\bonly\b/i.test(g.hint), `"${g.label}" does not claim to be the only way`)
ok(/outside any conversation/.test(sections[0].groups.find((g) => g.key === 'brain')!.hint), 'the whole Brain also reaches work outside any conversation')

/* a tier this client has never heard of: its own labelled section and group,
   the raw tier kept -- never filed under "not Brain records" */
const odd = C({ source_id: 'ent-t', tier: 'provisional', scope: 'whole-brain', text: 'A new standing.' })
const bare = C({ source_id: 'ent-u', tier: null, scope: 'conversation:ent-c', text: 'A record on no tier.' })
const ou = outline([...answer, odd, bare], names)
eq(ou.map((s) => s.key), ['governing', 'knowledge', 'also', 'unknown'], 'a fourth section, only when it is needed')
eq(ou[3].groups.map((g) => [g.key, g.label, g.items.map((i) => i.component.source_id)]), [['tier:provisional', 'Tier “provisional”', ['ent-t']], ['tier:none', 'No tier stated', ['ent-u']]], 'the raw tier is the group’s name')
eq(ou[2].count, 2, 'and "Also sent" still holds only what is not a record')
eq(ou[2].groups[0].items.every((i) => i.record === null), true, 'nothing with a record to open is called "not a Brain record"')
eq(ou[3].groups[0].items[0].record, 'ent-t', 'the unknown-tier record is still opened by its id')
eq(countItems(ou), answer.length + 2, 'and it is counted')
eq(groupOf(C({ tier: undefined, source_kind: 'request', source_id: null, scope: 'invocation' })), 'sent', 'the request is on no tier and is not a record')

/* an `also` scope this client does not know is said as the engine wrote it */
eq(becauseOf(C({ also: ['topic:ent-9', 'whole-brain'], scope: 'invocation:named', why: 'named explicitly for this invocation' })), 'named for this run; also “topic:ent-9”; also placed on the whole Brain', 'an unknown path is kept verbatim')
eq(becauseOf(C({ scope: 'somewhere:new', why: 'a new reason', also: ['topic:ent-9'] })), 'a new reason; also “topic:ent-9”', 'on an unknown scope too')
eq(scopeWords('topic:ent-9'), '“topic:ent-9”', 'an unknown scope, verbatim')

/* the trailer is a slice: a total is said only where the answer gives one,
   and the slice is never counted as if it were all */
const sliced = C({ source_id: 'ent-s', about: 'releases', trailer: {
  why: 'why this holds: 1 finding, 7 outcomes (worked, worked, failed)', supports: ['ent-e1', 'ent-e2'],
  basis: [{ ref: 'ent-b1', label: 'The owner’s post', relation: 'derived-from', kind: 'turn' }, { ref: 'adm-1', label: 'notes.pdf', relation: 'extracted-from' }],
  outcomes: [{ id: 'ent-o1', result: 'worked', attempted: true, in_context: 'ent-x1', recorded_at: 1700000000 }, { id: 'ent-o2', result: 'worked', text: 'Again.' }, { id: 'ent-o3', result: 'failed', attempted: false }] } })
const sl = trailerLines(sliced, () => 'Nov 14')
eq(sl.map((l) => l.text), [
  'Subject: releases', 'Why this holds: 1 finding, 7 outcomes (worked, worked, failed)', 'Supported by 2 records',
  'Rests on: The owner’s post (derived from); notes.pdf (extracted from)', 'The latest outcomes shown here: worked, attempted, Nov 14; worked (Again.); failed, not attempted',
], 'a governing record, as the server really gives it (no total): the outcomes shown are not counted')
ok(!/\d+ recorded outcome/.test(sl[4].text), 'so three shown can never contradict the seven its why-this-holds names')
eq(trailerLines(C({ tier: 'adopted', trailer: { basis: [{ ref: 'ent-b1', label: 'x' }], outcomes: [{ result: 'worked' }, { result: 'worked' }, { result: 'failed' }], outcomes_total: 7 } })).map((l) => l.text)[1],
  'Showing the latest 3 of 7 recorded outcomes: worked; worked; failed', 'knowledge carries its total: the slice is said as a slice of it')
eq(trailerLines(C({ tier: 'adopted', trailer: { basis: [{ ref: 'adm-1', label: '', artifact: { name: 'notes.pdf' }, relation: 'extracted-from', cite: 'p. 4', range: [10, 90], excerpt: 'Measure first.' }] } })).map((l) => l.text),
  ['Rests on: notes.pdf (extracted from; cited: p. 4; bytes 10–90) “Measure first.”'], 'a basis: the file, the place cited and the words cited')
eq(sl[2].refs!.map((r) => r.id), ['ent-e1', 'ent-e2'], 'each supporting record is opened by its id')
eq(sl[3].refs!.map((r) => r.id), ['ent-b1'], 'a basis that is a record is opened by its id; held bytes are named, not opened as a record')
eq(sl[4].refs!.map((r) => r.id), ['ent-o1', 'ent-o2', 'ent-o3', 'ent-x1'], 'each outcome shown is opened by its id, and where it happened')
eq(trailerLines(C({ trailer: { outcomes: [{ result: 'worked' }], outcomes_total: 1 } })).map((l) => l.text), ['1 recorded outcome: worked'], 'a whole list is not called a slice')
eq(trailerLines(C({ about: 'Where work is done', title: 'Own workspace — Where work is done' })), [], 'a subject the title already says is not said twice')
eq(trailerLines(C({ tier: 'adopted', trailer: { recorded_by: { alias: '@Builder', persona_name: 'Builder', runtime: 'claude', model: 'opus' }, basis: [] } }), () => '').map((l) => l.text),
  ['Recorded by Builder as Builder on claude (opus)', 'No basis recorded.'], 'who recorded it: the Persona worn and the model, where the answer says them')

/* the pieces that speak to one subject, each by name and by exact id */
eq(conflictMembers(['ent-1', 'ent-w', 'ent-gone', 'request'], answer, names), [
  { id: 'ent-1', kind: 'Rule', title: 'A stage is claimed only when it is reached.' }, { id: 'ent-w', kind: 'Workflow', title: 'Software change' },
  { id: 'ent-gone', kind: 'Record', title: 'A record' }, { id: null, kind: 'Request', title: '' },
], 'conflict members: named, and opened by the id the answer gave')

/* what else the answer says about something left out */
eq(withheldMeta({ source_kind: 'finding', source_id: 'ent-o', why: 'beyond the bound', tier: 'experience', rank: 6 }), { text: 'considered as relevant experience · ranked 6', refs: [] }, 'tier and rank')
eq(withheldMeta({ source_kind: 'rule', source_id: 'ent-o', why: 'superseded', scope: 'whole-brain' })!.text, 'would have reached this run as: placed on the whole Brain', 'how it would have reached')
eq(withheldMeta({ source_kind: 'discipline', source_id: 'ent-o', why: 'not established', scope: 'persona:ent-p' }, names)!.text, 'would have reached this run as: carried by the Persona Caretaker', 'what a Persona would have carried')
eq(withheldMeta({ source_kind: 'rule', source_id: 'ent-o', why: 'superseded', superseded_by: 'ent-n', delivered_instead: 'ent-n' })!.refs, [{ id: 'ent-n', label: 'the version given instead' }], 'the record given in its place, by id')
eq(withheldMeta({ source_kind: 'x', source_id: 'ent-o', why: 'cut', tier: 'provisional', scope: 'topic:ent-9' })!.text, 'considered on the tier “provisional” · would have reached this run as: “topic:ent-9”', 'unknown tier and scope, verbatim')
eq(withheldMeta({ source_kind: 'rule', source_id: 'ent-o', why: 'superseded' }), null, 'nothing more to say, nothing said')

/* -- the question asked ---------------------------------------------------- */
eq(receivePath({ conversation: null, participant: null, persona: null, named: [], work: '  ' }), null, 'nothing chosen, nothing asked')
eq(receivePath({ conversation: 'ent-c', participant: 'ent-me', persona: 'ent-p', named: ['ent-1', 'ent-2'], work: ' fix the tests ' }),
  '/api/context?conversation=ent-c&participant=ent-me&persona=ent-p&work=fix+the+tests&behavioural=ent-1&behavioural=ent-2', 'records added for the run go as the list the server reads, once each')

console.log(`quiet_receive_unit: ${checks} checks passed`)
