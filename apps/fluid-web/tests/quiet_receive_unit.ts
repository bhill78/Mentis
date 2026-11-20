/* WHAT AN AGENT WOULD BE GIVEN, AS AN OUTLINE (`src/quiet2/brain/receive.ts`),
 * checked without a server or a browser: every piece of the server's answer
 * lands in exactly one group and keeps its words; the groups are the reasons
 * a piece is given (the Persona, named for the run, this conversation, the
 * whole Brain, knowledge matched to the work, what every run is sent); the
 * one-line title and the plain "because"; the trailer's lines; what was left
 * out; and the address the preview asks. */
import assert from 'node:assert/strict'
import {
  becauseOf, countItems, engineReason, firstSentence, groupOf, kindOf, outline, titleOf, trailerLines, withheldReason,
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
  'Why this holds: 1 outcome (worked)', '1 recorded outcome: worked (It went through.)', '1 open challenge (Reviewer: “Too long.”). Still in effect.',
], 'a governing record: why it holds, how it has gone, what is challenged')
eq(trailerLines(by('ent-w').component).map((l) => !!l.warn), [false, false, true], 'only the challenge is a warning')
eq(trailerLines(by('ent-a').component, () => 'Nov 14').map((l) => l.text), [
  'Recorded by Builder on claude in Release check #4, Nov 14', 'Rests on: The 11-19 release', 'Limits: Only for Mentis.',
], 'knowledge: who recorded it, what it rests on, its limits')
eq(trailerLines(by('ent-f').component).map((l) => l.text), ['No basis recorded.', 'Recorded, not adopted.'], 'experience says it has no basis and is not adopted')
eq(trailerLines(by('ent-1').component), [], 'no trailer, no lines')

/* -- left out -------------------------------------------------------------- */
eq(withheldReason({ source_kind: 'rule', source_id: 'ent-o', why: 'superseded' }), 'replaced by a newer version', 'superseded, plainly')
eq(withheldReason({ source_kind: 'rule', source_id: 'ent-o', why: 'superseded', delivered_instead: 'ent-n' }), 'replaced; the newer version is given instead', 'superseded and followed forward')
eq(withheldReason({ source_kind: 'rule', source_id: 'ent-o', why: 'not established' }), 'proposed, not established yet', 'a proposal')
eq(withheldReason({ source_kind: 'finding', source_id: 'ent-o', why: 'relevant to the question on x, and beyond the bound for it' }), 'relevant to the question on x, and beyond the bound for it', 'any other reason as the engine wrote it')

/* -- the question asked ---------------------------------------------------- */
eq(receivePath({ conversation: null, participant: null, persona: null, named: [], work: '  ' }), null, 'nothing chosen, nothing asked')
eq(receivePath({ conversation: 'ent-c', participant: 'ent-me', persona: 'ent-p', named: ['ent-1', 'ent-2'], work: ' fix the tests ' }),
  '/api/context?conversation=ent-c&participant=ent-me&persona=ent-p&work=fix+the+tests&behavioural=ent-1&behavioural=ent-2', 'records added for the run go as the list the server reads, once each')

console.log(`quiet_receive_unit: ${checks} checks passed`)
