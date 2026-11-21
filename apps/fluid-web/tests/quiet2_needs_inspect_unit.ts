/* INSPECT BEFORE DECIDING, checked without a server or a browser
 * (src/quiet2/needs/inspect.ts): an id in a request's words is found exactly
 * and read out as the thing the server resolved FOR THAT ID; an id nobody
 * resolved is said to be unreadable, never given the nearest name; a `#12`
 * in prose is not a reference; what cannot be opened is said as what it is;
 * the subject is told apart from evidence and from what is merely named; and
 * a subject that cannot be opened is said before the decision. */
import assert from 'node:assert/strict'
import { gaps, goneWords, itemName, mentionsOf, openLabel, plain, questionsOf, refName, refsOf, segments, subjectHeading, subjectWords, typeWords, whereWords, type About, type Ref } from '../src/quiet2/needs/inspect'
import { UNCLEAR_SAYS, itemUnclear } from '../src/needsItems'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }

const ref = (more: Partial<Ref> & { id: string }): Ref => ({
  type: 'record', label: null, available: true, state: 'ok', why: null, opens: 'record', relation: 'named', ...more,
})
const RULE = ref({ id: 'ent-aaaaaaaaaaaa', kind: 'lesson', label: 'Strip dangling links before migrating a chart.' })
const TWIN = ref({ id: 'ent-bbbbbbbbbbbb', kind: 'lesson', label: 'Strip dangling links before migrating a chart.' })
const POST = ref({ id: 'ent-cccccccccccc', type: 'post', opens: 'post', label: 'Measured the old loader', number: 3, conversation: 'ent-conv2', conversation_name: 'Evidence room', post: 'ent-cccccccccccc' })
const GONE = ref({ id: 'ent-dddddddddddd', type: 'post', opens: null, available: false, state: 'deleted', why: 'This post was deleted.', number: 2, conversation_name: 'Evidence room' })
const NONE = ref({ id: 'ent-000000000000', type: 'unknown', opens: null, available: false, state: 'missing', why: 'This Brain holds nothing with this id.' })
const FINDING = ref({ id: 'opr-111111111111', type: 'finding', opens: 'post', label: 'Reconcile the base branch', number: 4, conversation: 'ent-conv1', post: 'ent-f1' })

const about = (more: Partial<About>): About => ({
  id: 'opr-ask', kind: 'form', form: 'opr-form', says: '@Coach asks you to decide: the question', asked_by_name: '@Coach',
  subject: [], evidence: [], context: [], referenced: [], ...more,
})

/* -- finding ids in words ------------------------------------------------------ */
eq(mentionsOf('Apply ent-aaaaaaaaaaaa, as in ent-cccccccccccc and (opr-111111111111). Again ent-aaaaaaaaaaaa.'),
  ['ent-aaaaaaaaaaaa', 'ent-cccccccccccc', 'opr-111111111111'], 'each id once, in the order written')
eq(mentionsOf('adm-f15046f4e90d at the start; see #2, #3 and commit 082a7a8211751bb84c05515ec2cbe4386d4daf1a'), ['adm-f15046f4e90d'],
  'a post number in prose and a commit hash are not references')
eq(mentionsOf('pre-ent-aaaaaaaaaaaa and student-abcdef are not ids; nor is ent-12'), [], 'an id is a whole word of its own shape')
eq(mentionsOf(null), [], 'no words, no ids')

/* -- reading them out: by the exact id, or not at all ---------------------------- */
const a1 = about({ referenced: [RULE, POST, GONE, NONE] })
const refs = refsOf(a1)
const cut = segments('Apply ent-aaaaaaaaaaaa as in ent-cccccccccccc?', refs)
eq(cut.map((s) => ('text' in s ? s.text : 'ref' in s ? '<' + s.ref.id + '>' : '?')),
  ['Apply ', '<ent-aaaaaaaaaaaa>', ' as in ', '<ent-cccccccccccc>', '?'], 'the words between ids are kept exactly')
eq(plain('Apply ent-aaaaaaaaaaaa?', refs), 'Apply lesson “Strip dangling links before migrating a chart.”?', 'an id reads as the thing it names')
/* THE TWIN HAS THE SAME WORDS AND A DIFFERENT ID: it is never what is shown */
const onlyTwin = refsOf(about({ referenced: [TWIN] }))
eq(segments('Apply ent-aaaaaaaaaaaa?', onlyTwin)[1], { unknown: 'ent-aaaaaaaaaaaa' }, 'an id the server did not resolve is unknown, not its look-alike')
eq(plain('Apply ent-aaaaaaaaaaaa?', onlyTwin), 'Apply a reference that could not be read?', 'and reads as unreadable, never as the similar record')
eq(plain('See #3 and ent-dddddddddddd', refs), 'See #3 and a deleted post (#2 in Evidence room)', 'a deleted post is said so; #3 is left as written')
eq(refsOf(about({ error: 'no', referenced: [RULE] })).size, 0, 'a request that could not be read names nothing')
eq(refsOf(null).size, 0, 'nothing read, nothing named')
/* the first role a reference was given is the one kept */
eq(refsOf(about({ subject: [{ ...RULE, relation: 'the record you would adopt' }], referenced: [{ ...RULE, relation: 'named' }] })).get(RULE.id)?.relation,
  'the record you would adopt', 'a subject also named in the words stays the subject')

/* -- names: never an id -------------------------------------------------------- */
eq(refName(RULE), 'lesson “Strip dangling links before migrating a chart.”', 'a record by its Kind and words')
eq(refName(POST), 'post #3 “Measured the old loader”', 'a post by its number and first line')
eq(refName(FINDING), 'finding “Reconcile the base branch”', 'a finding by what it says')
eq(refName(ref({ id: 'ent-x1x1x1', type: 'record', kind: 'working-rule', label: null })), 'a working rule', 'no words: what it is')
eq(refName(ref({ id: 'ent-form', type: 'form', label: 'cutover', number: 7, opens: 'post' })), 'the form “cutover” in post #7', 'a form by its name and post')
eq(refName(GONE), 'a deleted post (#2 in Evidence room)', 'deleted is said, with where it was')
eq(refName(NONE), 'something this Brain does not hold', 'missing is said')
eq(goneWords(ref({ id: 'ent-e', state: 'erased', available: false, opens: null })), 'something permanently deleted', 'erased is said')
eq(goneWords(ref({ id: 'ent-u', state: 'unreadable', available: false, opens: null })), 'something that could not be read', 'unreadable is said')
for (const r of [RULE, POST, FINDING, GONE, NONE]) ok(!/(ent|opr|adm)-[0-9a-f]{6,}/.test(refName(r)), `no id in the name of ${r.id}`)
eq(typeWords(POST), 'post #3', 'a post says its number')
eq(whereWords(POST, 'ent-conv1'), 'in Evidence room', 'a post elsewhere says where')
eq(whereWords(POST, 'ent-conv2'), null, 'a post here does not')
eq(whereWords(FINDING, 'ent-conv1'), '#4', 'a finding says the post it is in')
eq(openLabel(RULE), 'Open the record: lesson “Strip dangling links before migrating a chart.”', 'the control says what it opens')
eq(openLabel(POST), 'Go to the post: post #3 “Measured the old loader”', 'a post is gone to')

/* -- subject, apart from evidence and from what is only named -------------------- */
const adoption = about({ kind: 'adoption', says: '@Coach asks you to adopt this lesson: “Strip…”', subject: [RULE], evidence: [POST], referenced: [NONE] })
eq(subjectHeading(adoption), 'You are deciding on', 'an adoption is a decision')
eq(subjectWords(adoption), null, 'its subject is the record, not words about it')
eq(subjectHeading(about({ kind: 'input' })), 'You are asked to fill in', 'an input is filled in')
eq(subjectHeading(about({ kind: 'request' })), 'You are asked for', 'a request is asked for')
eq(subjectWords(about({ kind: 'form' })), 'The questions as asked. The record names no other item for them.', 'no item named: said, not invented')
eq(subjectWords(about({ kind: 'permission', operation: { summary: 'Delete the old chart cache' } })), 'Delete the old chart cache', 'a permission is about its operation')

/* -- what would be decided unseen is said first --------------------------------- */
eq(gaps(adoption), [], 'a subject that opens leaves nothing to warn of')
eq(gaps(about({ kind: 'adoption', subject: [{ ...GONE, relation: 'the record you would adopt' }] })),
  ['A deleted post (#2 in Evidence room) is what you would be deciding on, and it cannot be opened: This post was deleted.'], 'an unavailable subject is said')
eq(gaps(about({ kind: 'adoption' })), ['This asks you to adopt a record, and the request does not name which one.'], 'an adoption naming no record is said')
eq(gaps(about({ kind: 'decision', referenced: [NONE] })), [], 'an unreadable mention is listed, and is not the subject')
ok(gaps(null, 'HTTP 500')[0].includes('could not be read (HTTP 500)'), 'a failed read is said')
ok(gaps(about({ error: 'not a request' }))[0].includes('not a request'), 'a refused read is said')
eq(gaps(about({ kind: 'permission', operation: {} })), ['This asks permission for an operation, and the run did not say what it is.'], 'an operation nobody described is said')

/* -- the item's line in the list ------------------------------------------------ */
eq(itemName(adoption, 'Adoption requested: this lesson would stand…'), adoption.says, 'a structured kind is named by what it asks')
eq(itemName(a1, 'Apply ent-aaaaaaaaaaaa?'), 'Apply lesson “Strip dangling links before migrating a chart.”?', 'a question is read out')
eq(itemName(about({ says: '@Coach asks you to decide 2 questions.' }), 'the second question'), '@Coach asks you to decide 2 questions.', 'several questions: none is the name')
eq(itemName(null, 'Apply ent-aaaaaaaaaaaa?'), 'Apply ent-aaaaaaaaaaaa?', 'nothing read yet: the words as written')

/* -- SEVERAL QUESTIONS, SEVERAL SUBJECTS: never pooled ---------------------------
   One question's primary source must not appear to belong to another (contract
   ent-40166218c575 §3; ent-0fc483e17f76 §B3). The mapping is the server's own
   `question_references`, keyed by the exact expectation id -- the shape
   mentis/fluid/inspect.py projects, with each declared reference carrying how
   the record it names stands (`availability`). Where a server projects none,
   the item reads exactly as it did before. */
const WORDS = new Map([['opr-q1', 'Which scope?'], ['opr-q2', 'If it proceeds, where is it stored?']])
const twoQuestions = about({
  kind: 'form', says: '@Caretaker asks you to decide 2 questions.',
  subject: [RULE],
  question_references: [
    { expectation: 'opr-q1', presentation_status: { state: 'legacy', problems: [] },
      primary: { kind: 'record', id: POST.id, label: 'the proposal', availability: POST } },
    { expectation: 'opr-q2', presentation_status: { state: 'incomplete', problems: [] },
      primary: { kind: 'record', id: GONE.id, label: 'the storage note', availability: GONE },
      supporting: [{ kind: 'commit', repository: 'Mentis', sha: 'a'.repeat(40), label: 'the candidate' }] },
  ],
})
const drawn = questionsOf(twoQuestions, WORDS)
eq(drawn.map((q) => q.id), ['opr-q1', 'opr-q2'], 'each question is kept by its own expectation id')
eq(drawn.map((q) => q.question), ['Which scope?', 'If it proceeds, where is it stored?'], 'with its own recorded wording')
eq(drawn.map((q) => q.presentation_state), ['legacy', 'incomplete'], 'and the state the server derived for that question')
eq(drawn[0].subject.map((r) => [r.id, r.relation]), [[POST.id, 'the one source this question is about']],
  'a question’s declared primary is its own subject, resolved by its exact id')
eq(drawn[1].subject.map((r) => r.id), [GONE.id, 'commit:Mentis:' + 'a'.repeat(40)],
  'and so is each further thing it names, including a commit, which is named and not opened')
eq(questionsOf(twoQuestions), [{ ...drawn[0], question: null }, { ...drawn[1], question: null }],
  'without the questions’ wording, the mapping still holds and no wording is invented')
eq(questionsOf(about({ question_references: [{ expectation: 'opr-q1', primary: { kind: 'record', id: POST.id, label: 'p', availability: POST } }] })), [],
  'one question needs no separation: a union over one cannot mislead')
eq(questionsOf(about({ error: 'no' })), [], 'a request that could not be read declares no questions')
eq(questionsOf(adoption), [], 'and neither does one the server gave no mapping for')
eq(refsOf(twoQuestions).get(POST.id)?.relation, 'the one source this question is about',
  'a question’s own reference is resolved for its words, in the part the record gives it')
ok(refsOf(twoQuestions).has(GONE.id), 'including one that cannot be read')
eq(gaps(twoQuestions, null, WORDS), ['A deleted post (#2 in Evidence room) is what you would be deciding on in “If it proceeds, where is it stored?”, and it cannot be opened: This post was deleted.'],
  'a subject that cannot be opened is said under the question it belongs to, never under another')
eq(gaps(about({ question_references: [
  { expectation: 'a', primary: { kind: 'record', id: POST.id, label: 'p', availability: POST } },
  { expectation: 'b', primary: { kind: 'record', id: POST.id, label: 'p', availability: POST } }] })), [],
  'a subject that opens leaves nothing to warn of, question by question')
eq(gaps(about({ question_references: [
  { expectation: 'a', primary: { kind: 'url', url: 'https://example.invalid/p', label: 'the preview' } },
  { expectation: 'b', primary: { kind: 'commit', repository: 'Mentis', sha: 'b'.repeat(40), label: 'the candidate' } }] })), [],
  'a commit or an address is named with where it is, and its not opening here is not an omission')
/* nothing is read out of a question that declared nothing */
eq(questionsOf(about({ question_references: [{ expectation: 'opr-q1' }, { expectation: 'opr-q2' }] })).map((q) => q.subject.length),
  [0, 0], 'a question that declared no source of its own is given none')

/* -- what the list says before the form is unfolded ----------------------------- */
eq(itemUnclear({ presentation_state: 'incomplete' }), true, 'an incomplete decision is said to be missing something')
eq(itemUnclear({ presentation_state: 'unsupported' }), true, 'and so is one this page cannot read')
eq(itemUnclear({ presentation_state: 'legacy' }), false, 'an earlier format alone is not a missing field')
eq(itemUnclear({ presentation_state: 'complete' }), false, 'and a complete one is not')
eq(itemUnclear({}), false, 'a server that says nothing claims nothing')
ok(UNCLEAR_SAYS.includes('was not recorded with it'), 'it names the absence')
ok(!/wrong|bad|invalid|cannot be answered/i.test(UNCLEAR_SAYS), 'and does not judge the decision or block answering it')

console.log(`quiet2 needs inspect: ${checks} checks ok`)
