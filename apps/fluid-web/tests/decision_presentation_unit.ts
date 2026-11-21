/* WHAT A DECISION ASKS, AND WHAT THE RECORD DOES NOT SAY, checked without a
 * server or a browser (src/experimental/decisionPresentation.ts, and the reply
 * bodies in src/experimental/decisions.ts).
 *
 * The fixtures are the representative decisions the contract names
 * (ent-40166218c575 §6): the three Agent Presets scope questions and their
 * generated approval, the answered "merge and/or deploy" release approval, an
 * operation permission with no artifact, a free response with no source, and a
 * technical tradeoff whose second alternative has no recorded consequence.
 *
 * What it holds this code to:
 *   - NOTHING IS INVENTED. No primary source where none was recorded, no stage
 *     where none was recorded, no Yes/No where words were asked for, and the
 *     wording of a question never decides what kind of question it is.
 *   - WHAT IS MISSING IS NAMED, by its field, from record structure only.
 *   - AN OLDER DECISION IS SHOWN AS RECORDED, said to be an earlier format, and
 *     not claimed to have been reviewed or verified.
 *   - ANSWER SEMANTICS ARE UNTOUCHED: the same question id, option index and
 *     label; own words still close only their own question; a withdrawal
 *     offered as asking for a clearer question sends the same withdrawal. */
import assert from 'node:assert/strict'
import {
  APPLIES_WHEN_SAYS, EARLIER_FORMAT, OWN_WORDS_CLOSES, OWN_WORDS_NOT_A_CLARIFICATION,
  TYPE_WORDS, WITHDRAW_CLARIFY_LABEL, appliesWhen, gapsOf, letterOf, primaryOf, refOf,
  refOpens, refWords, scopeWords, stageWords, statusOf, supportingOf, unclear,
  withdrawSays, withoutConsequence,
  type Asked, type Asking, type Presentation,
} from '../src/experimental/decisionPresentation'
import { groupsOf, replyFor, type Ask, type PostHead, type Read } from '../src/experimental/decisions'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }

const NO_FORM: Asking = {}

/* -- the three Agent Presets scope questions (opr-4bfe6e0c950a) -------------
   Materially different alternatives, two of them conditional. They must stay
   four and two choices with their own consequences, never collapse into
   "Is this the design you want us to build? Yes/No". */
const PRESETS: Asking = { because: 'Agent Presets needs a first-release scope before anything is built.' }
const scope: Asked = {
  id: 'opr-5e0d5cab21c1', expects: 'decision', form: 'opr-4bfe6e0c950a',
  question: 'Which first-release implementation scope should Agent Presets have?',
  options: [
    { label: 'Full bounded presets', consequence: 'permission and authority defaults, Persona suggestions, fixed runtime/model/effort and bounded delegation reuse, with the stated safeguards' },
    { label: 'Permission-first', consequence: 'owner permission and authority presets with lifecycle safeguards; defers Persona associations, runtime presets and agent-side reads' },
    { label: 'Browser-local only', consequence: 'a reduced device-bound composer feature, without agent-side reuse' },
    { label: 'Isolation first', consequence: 'defers implementation until stronger isolation is designed and authorized' },
  ],
}
const storage: Asked = {
  id: 'opr-37be635ff2b6', expects: 'decision', form: 'opr-4bfe6e0c950a',
  question: 'If server presets proceed, where should they be stored?',
  options: [
    { label: 'Separate store', consequence: 'host-path preferences stay out of Brain backups and Exchange; Brain recovery does not restore presets automatically' },
    { label: 'Include in Brain backups', consequence: 'portable backups may contain local workspace paths' },
  ],
}
const scopeState = statusOf(scope, PRESETS)
eq(scopeState, { state: 'legacy', problems: [] }, 'a structurally sufficient older question is the earlier format, with nothing missing')
eq(unclear(scopeState), false, 'and it is not treated as a decision that cannot be read')
eq(gapsOf(scopeState, scope), [], 'so nothing is listed as missing from it')
eq(withoutConsequence(scope), [], 'every alternative it offered has its own recorded consequence')
eq(scope.options!.map((o) => o.label), ['Full bounded presets', 'Permission-first', 'Browser-local only', 'Isolation first'],
  'the four alternatives keep their submitted order and their own words')
eq(statusOf(storage, PRESETS), { state: 'legacy', problems: [] }, 'the conditional question stands on its own, unanswered by the first')
ok(storage.question!.startsWith('If server presets proceed'), 'its condition stays in the question as recorded')
ok(APPLIES_WHEN_SAYS.includes('never answers'), 'a condition answers, withdraws or skips nothing by itself')
ok(EARLIER_FORMAT.includes('earlier format'), 'an older question is labelled as an earlier format')
ok(!/verified|reviewed|approved/i.test(EARLIER_FORMAT), 'and is not claimed to have been verified, reviewed or approved')

/* -- the generated approval over the same work (opr-fc67b303516b) ----------
   Faithful presentation can establish only its recorded question, its generic
   alternatives and the material it names. Its authorization boundary was never
   supplied, and that is said -- from the form's own recorded approval
   material, NEVER from the words "Approve this work?". */
const GENERATED: Asking = { because: 'the run claimed its work', approval_artifacts: ['ent-e89925cea328'] }
const generated: Asked = {
  id: 'opr-generated', expects: 'decision', form: 'opr-fc67b303516b',
  question: 'Approve this work?',
  options: [
    { label: 'Approve', consequence: 'the work continues' },
    { label: 'Revise', consequence: 'it is revised' },
  ],
}
const genState = statusOf(generated, GENERATED)
eq(genState, { state: 'legacy', problems: [{ path: 'approval.scope', code: 'required' }] },
  'a recorded generated approval with no authorization scope or stage is identified as missing it')
eq(unclear(genState), true, 'so the form offers the way out of a question that cannot be read')
ok(gapsOf(genState, generated)[0].includes('what approving it would permit cannot be read from the record'),
  'and says exactly what cannot be read')
eq(primaryOf(generated), { kind: 'unrecorded' }, 'no relationship to the scope questions, and no artifact, is invented for it')
eq(statusOf(generated, { because: 'the run claimed its work' }), { state: 'legacy', problems: [] },
  'the same wording on a form the record does NOT call a generated approval is not read as one: structure decides, not prose')

/* -- the answered release approval (ent-8d176472a180) -----------------------
   "merging and/or deploying". The recorded option alone does not say which,
   and this repair must not resolve that. */
const release: Asked = {
  id: 'opr-release', expects: 'decision', form: 'opr-releaseform',
  question: 'Approve merging and/or deploying Manage Brain Round 2?',
  because: 'Round 2 is ready to go out.',
  options: [
    { label: 'Approve', consequence: 'it proceeds' },
    { label: 'Revise', consequence: 'it comes back for revision' },
  ],
}
const relState = statusOf(release, NO_FORM)
eq(relState, { state: 'legacy', problems: [] }, 'an answered older approval stays a historical display')
eq(stageWords([]), '', 'and no stage is supplied for an approval that recorded none')
ok(!gapsOf(relState, release).some((g) => /merge|deploy/i.test(g)), 'the historical merge-or-deploy ambiguity is neither resolved nor restated as a defect')

/* -- an operation permission with no artifact (ent-d946f0a07248) ------------
   A system-produced permission form: no primary artifact is required, and its
   Allow once / Deny consequences are its own. */
const PERMISSION: Asking = { because: 'the task needs the local preview page', operation: { summary: 'Fetch the local preview with Invoke-WebRequest' } }
const permission: Asked = {
  id: 'opr-permission', expects: 'decision', form: 'opr-permissionform',
  question: 'Allow this run to fetch the local preview page?',
  options: [
    { label: 'Allow once', consequence: 'this one operation runs, and nothing else is allowed by it' },
    { label: 'Deny', consequence: 'it is refused and the run is told' },
  ],
}
eq(statusOf(permission, PERMISSION), { state: 'legacy', problems: [] },
  'a permission naming no artifact is complete as recorded: no artifact is required of it')
eq(primaryOf(permission), { kind: 'unrecorded' }, 'and none is invented for it')

/* -- a free response with no source ---------------------------------------- */
const availability: Asked = {
  id: 'opr-window', expects: 'decision', form: 'opr-windowform',
  question: 'Which maintenance window can you attend?',
  because: 'We need to know when you are available before a schedule is proposed.',
  presentation: {
    version: 1, type: 'free_response',
    scope: 'Your answer is used to propose a schedule. It permits no deployment and no other operation.',
    stages: [], primary: null,
    primary_reason: 'This asks for your availability, not about a document or a candidate.',
  } as Presentation,
}
const freeState = statusOf(availability, NO_FORM)
eq(freeState, { state: 'complete', problems: [] }, 'a free response with no options, no stages and an explicit absent primary is complete')
eq(unclear(freeState), false, 'nothing about it needs clarifying')
eq(primaryOf(availability), { kind: 'none', because: 'This asks for your availability, not about a document or a candidate.' },
  'an explicit absent primary is shown with the recorded reason, not as an unrecorded role')
eq(scopeWords(availability), 'Your answer is used to propose a schedule. It permits no deployment and no other operation.',
  'what the answer is used for is the author’s own words, neither summarised nor shortened')
ok(!/approv/i.test(TYPE_WORDS.free_response), 'asking for the owner’s words is not framed as an approval')
eq(statusOf({ ...availability, options: [{ label: 'Yes', consequence: 'y' }, { label: 'No', consequence: 'n' }] }, NO_FORM).problems,
  [{ path: 'options', code: 'not-allowed-for-free-response' }],
  'offered choices on a free response are reported, never quietly accepted as Yes/No')

/* -- a technical tradeoff whose second alternative has no consequence ------- */
const tradeoff: Asked = {
  id: 'opr-capacity', expects: 'decision', form: 'opr-capacityform',
  question: 'Should MARS change capacity estimation, or should the runtime change what it reports?',
  because: 'MARS cannot reliably determine available workload.',
  options: [
    { label: 'Change capacity estimation', consequence: 'MARS estimates differently; the runtimes are untouched' },
    { label: 'Change the runtime’s reporting' },
  ],
  presentation: {
    version: 1, type: 'choice',
    scope: 'Chooses which of the two is built next. It authorizes no deployment.',
    stages: ['implementation'],
    primary: { kind: 'record', id: 'ent-6f6d22b5c962', label: 'the post explaining the issue' },
  } as Presentation,
}
const tradeState = statusOf(tradeoff, NO_FORM)
eq(tradeState, { state: 'incomplete', problems: [{ path: 'options[1].consequence', code: 'required' }] },
  'an offered alternative with no recorded consequence makes the question incomplete')
eq(withoutConsequence(tradeoff), [1], 'and it is identified by its index, so its own row says so')
eq(gapsOf(tradeState, tradeoff), ['Choice B “Change the runtime’s reporting”: what choosing it leads to was not recorded.'],
  'named by its letter and its own words, with no engineering alternative invented for it')
eq(unclear(tradeState), true, 'the owner is offered the way out of it')
eq(primaryOf(tradeoff), { kind: 'ref', ref: { kind: 'record', id: 'ent-6f6d22b5c962', label: 'the post explaining the issue' } },
  'its declared primary source is shown as declared')
eq(stageWords(['implementation']), 'building it', 'the stage it covers reads as what it is')

/* -- approving something specific, with nothing specific named -------------- */
const vague: Asked = {
  id: 'opr-vague', expects: 'decision', form: 'opr-vagueform', question: 'Approve the candidate?', because: 'it is ready',
  options: [{ label: 'Approve', consequence: 'it proceeds' }, { label: 'Revise', consequence: 'it is revised' }],
  presentation: {
    version: 1, type: 'artifact_approval', scope: 'Approves the design only.', stages: ['design'],
    primary: null, primary_reason: 'no candidate was named',
  } as Presentation,
}
const vagueState = statusOf(vague, NO_FORM)
eq(vagueState.problems, [{ path: 'presentation.primary', code: 'required-for-artifact-approval' }],
  'approving something specific with an explicitly absent primary is incomplete')
ok(gapsOf(vagueState, vague)[0].includes('does not name which thing'), 'and says the record names no thing to approve')

/* -- missing and null are different ---------------------------------------- */
const noKey = { version: 1, type: 'action_approval', scope: 'Permits one deployment of the approved candidate.', stages: ['deployment'] } as unknown as Presentation
eq(statusOf({ id: 'opr-k', form: 'f', question: 'q', because: 'b', presentation: noKey }, NO_FORM).problems,
  [{ path: 'presentation.primary', code: 'required' }], 'a primary key nobody supplied is missing, and is said to be')
eq(primaryOf({ presentation: noKey }), { kind: 'unrecorded' }, 'and is never read as an explicit "no primary source"')
const bentRef = { version: 1, type: 'choice', scope: 's', stages: [], primary: { kind: 'commit', repository: 'Mentis', label: 'the candidate' } } as unknown as Presentation
eq(statusOf({ id: 'opr-m', form: 'f', question: 'q', because: 'b', presentation: bentRef }, NO_FORM).problems,
  [{ path: 'presentation.primary', code: 'malformed' }], 'a commit with no hash is malformed, not half-read')
eq(primaryOf({ presentation: bentRef }), { kind: 'unrecorded' }, 'and nothing is shown for it')

/* -- presentation data this page cannot read -------------------------------- */
const later: Asked = {
  id: 'opr-v2', expects: 'decision', form: 'f', question: 'Approve the candidate?', because: 'it is ready',
  options: [{ label: 'Approve', consequence: 'it proceeds' }],
  presentation: {
    version: 2, type: 'artifact_approval', scope: 'Approves deploying it.', stages: ['deployment'],
    primary: { kind: 'record', id: 'ent-aaaaaaaaaaaa', label: 'the candidate' },
    supporting: [{ kind: 'record', id: 'ent-bbbbbbbbbbbb', label: 'the review' }],
  } as unknown as Presentation,
}
const laterState = statusOf(later, NO_FORM)
eq(laterState.state, 'unsupported', 'a version this page does not support is unsupported, never silently version 1')
eq(laterState.problems[0], { path: 'presentation.version', code: 'unsupported-version' }, 'and says so by its field')
eq(scopeWords(later), null, 'nothing is read out of it as an authorization')
eq(appliesWhen(later), null, 'nor as a condition')
eq(supportingOf(later), [], 'nor as further material')
ok(gapsOf(laterState, later)[0].includes('version 2'), 'the version it does hold is named')
ok(gapsOf(laterState, later)[0].includes('exactly as recorded'), 'and its question, choices and answers are said to be as recorded')
const unknownType = statusOf({ id: 'u', form: 'f', question: 'q', because: 'b', presentation: { version: 1, type: 'blessing', scope: 's', stages: [], primary: null, primary_reason: 'r' } as unknown as Presentation }, NO_FORM)
eq(unknownType.state, 'unsupported', 'a type this page does not know is unsupported too')

/* -- the server's word where it gave one ----------------------------------- */
eq(statusOf({ id: 's', form: 'f', question: 'q', presentation_status: { state: 'incomplete', problems: [{ path: 'presentation.scope', code: 'required' }] } }, NO_FORM),
  { state: 'incomplete', problems: [{ path: 'presentation.scope', code: 'required' }] }, 'the derived state the server read is the one used')
eq(statusOf({ id: 's', form: 'f', question: 'q', presentation_status: { state: 'brand-new' } as unknown as never }, NO_FORM).state,
  'unsupported', 'a state this page does not know is never read as complete')
eq(gapsOf(statusOf({ id: 's', form: 'f', question: 'q', because: 'b', presentation_status: { state: 'complete', problems: [{ path: 'presentation.wobble', code: 'odd' }] } }, NO_FORM), { id: 's' }),
  ['The record is missing presentation.wobble (odd).'], 'a problem this page has no words for is still shown, by its field')

/* -- an older server says nothing, and nothing is claimed ------------------- */
const bare = statusOf({ id: 'opr-bare', expects: 'decision', form: 'opr-bareform' }, NO_FORM)
eq(bare, { state: 'legacy', problems: [{ path: 'question', code: 'required' }, { path: 'because', code: 'required' }] },
  'a question of a form with no words and no context is the earlier format, with both named')
eq(gapsOf(bare, { id: 'opr-bare', form: 'opr-bareform' }),
  ['No question of its own was recorded for this one: what is asked is the asking post.', 'Why this decision is needed was not recorded.'],
  'said as what is missing, in the order found')
eq(statusOf({ id: 'opr-alone', expects: 'decision', because: 'why it is asked' }, NO_FORM), { state: 'legacy', problems: [] },
  'an ask asked as its own post is not missing a question: the post is the question')

/* -- references read as words, never as ids -------------------------------- */
eq(refWords({ kind: 'record', id: 'ent-e89925cea328', label: 'the Agent Presets proposal' }), 'the Agent Presets proposal', 'a record by its words')
eq(refWords({ kind: 'commit', repository: 'Mentis', sha: '71b064703ffe8094cc391555ac1695e0dca60996', label: 'the candidate' }),
  'the candidate (Mentis 71b064703ffe)', 'a commit by its words, repository and short hash')
ok(!/(ent|opr|adm)-[0-9a-f]{6,}/.test(refWords({ kind: 'record', id: 'ent-e89925cea328', label: 'the proposal' })), 'an id is never a reference’s name')
eq(refOpens({ kind: 'record', id: 'ent-a1a1a1a1a1a1', label: 'l' }), { record: 'ent-a1a1a1a1a1a1' }, 'a record is opened by its exact id')
eq(refOpens({ kind: 'url', url: 'https://example.invalid/preview', label: 'the preview' }), { url: 'https://example.invalid/preview' }, 'a URL is a link')
eq(refOpens({ kind: 'commit', repository: 'r', sha: 'a'.repeat(40), label: 'l' }), null, 'a commit is named here, and is not opened from here')
eq(refOf({ kind: 'record', id: 'ent-a', label: '  ' }), null, 'a reference with no words of its own is malformed')
eq(refOf({ kind: 'url', label: 'the preview' }), null, 'a URL reference needs its address')
eq(refOf('ent-aaaaaaaaaaaa'), null, 'a bare id is not a reference object')
eq(supportingOf({ presentation: { version: 1, type: 'choice', scope: 's', stages: [], primary: null, primary_reason: 'r', supporting: [{ kind: 'record', id: 'ent-c1', label: 'the review' }, { kind: 'record', id: 'ent-c2' }] } as unknown as Presentation }),
  [{ kind: 'record', id: 'ent-c1', label: 'the review' }], 'a malformed one among the further material is left out, not half-shown')

/* -- stages and letters ---------------------------------------------------- */
eq(stageWords(['design', 'implementation']), 'the design and building it', 'two stages read as two')
eq(stageWords(['design', 'implementation', 'deployment']), 'the design, building it and deploying it', 'three read as three')
eq(stageWords(['nonsense']), '', 'a stage this page does not know contributes no words')
eq(stageWords('design'), '', 'and neither does something that is not a list')
eq([letterOf(0), letterOf(3)], ['A', 'D'], 'choices are lettered as the form letters them')

/* -- what closing it does, said exactly ------------------------------------ */
for (const says of [withdrawSays(true), withdrawSays(false)]) {
  ok(!/nothing runs/i.test(says), 'withdrawal no longer says that nothing runs')
  ok(says.includes('may resume under its existing rules'), 'it says the Work MAY resume under its existing rules')
  ok(says.includes('does not itself create a replacement question'), 'and that it creates no replacement question')
  ok(/unchanged/.test(says), 'and that the question and its choices stay in the record unchanged')
}
ok(withdrawSays(true).includes('every question in this form'), 'on a form, it is the form’s last question that may let the Work resume')
ok(withdrawSays(false).includes('the Work it belongs to'), 'on an ask of its own, it is the Work the ask belongs to')
ok(!/immediately|will resume|guarantee/i.test(withdrawSays(true)), 'nothing is promised')
eq(WITHDRAW_CLARIFY_LABEL, 'Withdraw with a clarification reason', 'the way out of an unreadable question is named for what it does')
ok(OWN_WORDS_CLOSES.includes('close this question'), 'own words are said to close the question before they are sent')
ok(OWN_WORDS_NOT_A_CLARIFICATION.includes('please clarify'), 'and “please clarify” is said not to ask for a clearer question')

/* -- ANSWER SEMANTICS ARE UNTOUCHED ---------------------------------------- */
const post: PostHead = { id: 'ent-post', number: 7, author: 'ent-caretaker', author_alias: '@Caretaker', topics: ['agent-presets'], conversation: 'ent-conv' }
const asked: Ask = {
  id: 'opr-5e0d5cab21c1', expects: 'decision', of: 'ent-owner', by: 'ent-caretaker', by_alias: '@Caretaker',
  response_present: false, form: 'opr-4bfe6e0c950a', index: 0, question: scope.question,
  options: scope.options as Ask['options'],
}
const presented: Ask = {
  ...asked,
  presentation: { version: 1, type: 'choice', scope: 'Chooses the first release’s scope.', stages: ['implementation'], primary: { kind: 'record', id: 'ent-e89925cea328', label: 'the proposal' } },
  presentation_status: { state: 'complete', problems: [] },
}
const chose = replyFor({ ask: asked, pick: { kind: 'option', option: 1 }, text: '', me: 'ent-owner', post })
eq(replyFor({ ask: presented, pick: { kind: 'option', option: 1 }, text: '', me: 'ent-owner', post }), chose,
  'presentation changes nothing a reply sends')
eq(chose.chose, { expectation: 'opr-5e0d5cab21c1', option: 1, label: 'Permission-first' },
  'a choice still records its question, the option’s index and its label')
eq(replyFor({ ask: asked, pick: { kind: 'withdraw' }, text: 'I cannot tell what Approve would authorize.', me: 'ent-owner', post }).chose,
  { expectation: 'opr-5e0d5cab21c1', withdraw: true },
  'a withdrawal offered as asking for a clearer question is the same withdrawal, with the owner’s reason')
eq(replyFor({ ask: asked, pick: { kind: 'own' }, text: 'Permission-first, for now.', me: 'ent-owner', post }).chose,
  { expectation: 'opr-5e0d5cab21c1' }, 'own words still close exactly their own question and no other')

/* -- what the form row carries, through to each question ------------------- */
const read: Read = {
  post, you: 'ent-owner', expectations: [asked],
  decision_forms: [{
    form: 'opr-4bfe6e0c950a', post: 'ent-post', pending: false, conversation: 'ent-conv', asked_by: 'ent-caretaker',
    because: 'the run claimed its work', questions: [{ expectation: 'opr-5e0d5cab21c1' }],
    approval_artifacts: ['ent-e89925cea328'], from_prose: false,
  }],
}
const [group] = groupsOf(read)
eq(group.approval_artifacts, ['ent-e89925cea328'], 'the material a generated approval was recorded over reaches the form')
eq(group.from_prose, false, 'and so does whether the form was produced from prose')
eq(statusOf(asked, group), { state: 'legacy', problems: [{ path: 'approval.scope', code: 'required' }] },
  'so the question on it is read as the generated approval the record says it is')

console.log(`decision presentation: ${checks} checks ok`)
