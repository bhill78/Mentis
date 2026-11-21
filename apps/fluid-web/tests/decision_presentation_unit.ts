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
  APPLIES_WHEN_SAYS, CONSTRUCTOR_BECAUSE, EARLIER_FORMAT, OWN_WORDS_CLOSES, OWN_WORDS_NOT_A_CLARIFICATION,
  TYPE_WORDS, WITHDRAW_CLARIFY_LABEL, appliesWhen, gapWords, gapsOf, letterOf, primaryOf, refOf,
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
eq(genState, { state: 'incomplete', problems: [
  { path: 'presentation.scope', code: 'not_recorded' }, { path: 'presentation.stages', code: 'not_recorded' }] },
  'a recorded generated approval with no authorization scope or stage is identified as missing it, '
  + 'in the paths and codes Python 2f3c2210 and Rust 47796384 emit for it')
eq(unclear(genState), true, 'so the form offers the way out of a question that cannot be read')
eq(gapsOf(genState, generated, GENERATED).length, 1, 'its two halves are one thing to a person, and are said once')
ok(gapsOf(genState, generated, GENERATED)[0].includes('what approving it would permit cannot be read from the record'),
  'and say exactly what cannot be read')
ok(!/presentation\.|not_recorded|\(/.test(gapsOf(genState, generated, GENERATED)[0]),
  'with no field path and no code in front of the owner (ent-0fc483e17f76 §B2)')
eq(primaryOf(generated), { kind: 'unrecorded' }, 'no relationship to the scope questions, and no artifact, is invented for it')
/* WHERE THE RECORD SAYS THE ORIGIN, THE ORIGIN IS SAID: the form act carries
   the material the approval was generated over, so calling it a generated
   approval is the record's own statement, not a reading of the question. */
ok(gapsOf(genState, generated, GENERATED)[0].startsWith('This was recorded as a generated approval.'),
  'a form the record says carries a generated approval keeps that provenance')
/* THE BACKENDS' OWN RULE, MIRRORED: both identify the missing boundary by the
   form's recorded approval material OR by the recorded question beginning with
   those words. Deriving the same thing here is what makes a page say what the
   server that projects it says, instead of nothing (§B1). */
eq(statusOf(generated, { because: 'the run claimed its work' }), genState,
  'a question recorded as "Approve this work?" reads the same whether or not the form row reached this page')
eq(statusOf({ ...generated, question: 'Approve the Round 2 candidate for deployment?' }, { because: 'b' }),
  { state: 'legacy', problems: [] },
  'and an older approval that says what it is about is not treated as the generated one')

/* -- THE SAME WORDS, WITH NOTHING IN THE RECORD BEHIND THEM -----------------
   No server projects `approval_artifacts` today, so this is what the real page
   has: the general approval question and nothing that says who asked it. What
   is missing is still named in full; where it came from is not asserted
   (ent-9f0291944c9a, owner: a question prefix alone cannot prove an approval
   was generated). */
const UNATTRIBUTED: Asking = { because: 'the run claimed its work' }
const unattributed = gapsOf(statusOf(generated, UNATTRIBUTED), generated, UNATTRIBUTED)
eq(unattributed.length, 1, 'the missing boundary is still one thing, said once')
ok(!/recorded as a generated approval|was generated|produced by a run\b/.test(unattributed[0]),
  'and the page does not claim the record says a run produced it')
ok(unattributed[0].includes('what approving it would permit cannot be read from the record'),
  'what cannot be read is said in full, exactly as before')
ok(unattributed[0].includes('at which stage'), 'including at which stage')
ok(unattributed[0].includes('The record does not say whether this question was written for this work'),
  'and the origin is left as what it is: not known from the record')
ok(!/presentation\.|not_recorded|\(/.test(unattributed[0]),
  'still with no field path and no code in front of the owner')
const trailing: Asked = { ...generated, question: 'approve this work? please — the candidate is ready' }
eq(gapsOf(statusOf(trailing, UNATTRIBUTED), trailing, UNATTRIBUTED), unattributed,
  'a question that merely begins with those words reads the same, whatever follows them')

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
  [{ path: 'options', code: 'omit_for_free_response' }],
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
eq(vagueState.problems, [{ path: 'presentation.primary', code: 'exact_artifact_required' }],
  'approving something specific with an explicitly absent primary is incomplete')
ok(gapsOf(vagueState, vague)[0].includes('does not name which thing'), 'and says the record names no thing to approve')

/* -- missing and null are different ---------------------------------------- */
const noKey = { version: 1, type: 'action_approval', scope: 'Permits one deployment of the approved candidate.', stages: ['deployment'] } as unknown as Presentation
eq(statusOf({ id: 'opr-k', form: 'f', question: 'q', because: 'b', presentation: noKey }, NO_FORM).problems,
  [{ path: 'presentation.primary', code: 'required' }], 'a primary key nobody supplied is missing, and is said to be')
eq(primaryOf({ presentation: noKey }), { kind: 'unrecorded' }, 'and is never read as an explicit "no primary source"')
const bentRef = { version: 1, type: 'choice', scope: 's', stages: [], primary: { kind: 'commit', repository: 'Mentis', label: 'the candidate' } } as unknown as Presentation
eq(statusOf({ id: 'opr-m', form: 'f', question: 'q', because: 'b', presentation: bentRef, options: [{ label: 'a', consequence: 'x' }, { label: 'b', consequence: 'y' }] }, NO_FORM).problems,
  [{ path: 'presentation.primary', code: 'reference_object' }], 'a commit with no hash is malformed, not half-read')
eq(statusOf({ id: 'opr-m2', form: 'f', question: 'q', because: 'b', presentation: { version: 1, type: 'choice', scope: 's', stages: [], primary: null, primary_reason: 'r' } as unknown as Presentation }, NO_FORM).problems,
  [{ path: 'options', code: 'choice_options_required' }],
  'a choice recorded with no alternatives to choose between is reported, as both backends report it')
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
eq(laterState.problems[0], { path: 'presentation.version', code: 'unsupported_version' }, 'and says so by its field')
eq(scopeWords(later), null, 'nothing is read out of it as an authorization')
eq(appliesWhen(later), null, 'nor as a condition')
eq(supportingOf(later), [], 'nor as further material')
ok(gapsOf(laterState, later)[0].includes('version 2'), 'the version it does hold is named')
ok(gapsOf(laterState, later)[0].includes('exactly as recorded'), 'and its question, choices and answers are said to be as recorded')
const unknownType = statusOf({ id: 'u', form: 'f', question: 'q', because: 'b', presentation: { version: 1, type: 'blessing', scope: 's', stages: [], primary: null, primary_reason: 'r' } as unknown as Presentation }, NO_FORM)
eq(unknownType, { state: 'incomplete', problems: [{ path: 'presentation.type', code: 'unsupported_type' }] },
  'a version 1 whose type this page does not know is incomplete, exactly as the backends classify it')
eq(unclear(unknownType), true, 'and the owner is offered the way out of it')
ok(gapsOf(unknownType, { id: 'u' })[0].includes('does not support'), 'said as something this page cannot read')

/* -- the server's word where it gave one ----------------------------------- */
eq(statusOf({ id: 's', form: 'f', question: 'q', presentation_status: { state: 'incomplete', problems: [{ path: 'presentation.scope', code: 'required' }] } }, NO_FORM),
  { state: 'incomplete', problems: [{ path: 'presentation.scope', code: 'required' }] }, 'the derived state the server read is the one used')
eq(statusOf({ id: 's', form: 'f', question: 'q', presentation_status: { state: 'brand-new' } as unknown as never }, NO_FORM).state,
  'unsupported', 'a state this page does not know is never read as complete')
const odd = gapsOf(statusOf({ id: 's', form: 'f', question: 'q', because: 'b', presentation_status: { state: 'complete', problems: [{ path: 'presentation.wobble', code: 'odd' }] } }, NO_FORM), { id: 's' })
eq(odd, ['Something this decision records could not be read, and this page has no words for what it was.'],
  'a problem this page has no words for is still said, and never as a field path and a code')
ok(!/presentation\.wobble|odd/.test(odd[0]), 'the internal path and code do not reach the owner')
eq(gapsOf({ state: 'incomplete', problems: [{ path: 'presentation.supporting[2].id', code: 'record_identity' }] }, { id: 's' }),
  ['One of the further things it names does not name a record by an id this Brain could look up.'],
  'a problem with no sentence of its own is said by what it is about and what is wrong with it')

/* -- an older server says nothing, and nothing is claimed ------------------- */
const bare = statusOf({ id: 'opr-bare', expects: 'decision', form: 'opr-bareform' }, NO_FORM)
eq(bare, { state: 'incomplete', problems: [{ path: 'question', code: 'required' }, { path: 'because', code: 'required' }] },
  'a question of a form with no words and no context has both named, as the backends name them')
eq(gapsOf(bare, { id: 'opr-bare', form: 'opr-bareform' }),
  ['No question of its own was recorded for this one: what is asked is the asking post.', 'Why this decision is needed was not recorded.'],
  'said as what is missing, in the order found')
const alone = statusOf({ id: 'opr-alone', expects: 'decision', because: 'why it is asked' }, NO_FORM)
eq(alone.problems, [{ path: 'question', code: 'required' }],
  'an ask asked as its own post records no question of its own, which both backends report')
ok(gapsOf(alone, { id: 'opr-alone' })[0].includes('what is asked is the post it was asked on'),
  'and is said as what it is, not as a defect in the question')

/* -- WHY IT IS ASKED, WHERE THE RECORD HOLDS ONLY THE CONSTRUCTOR'S WORDS ---
   Both backends report the form constructor's own fallback phrase as context
   that cannot be established (`unavailable_or_uncertain`, Python 2f3c2210 /
   Rust 47796384). The stored words are untouched; what is said is that they
   are not the asker's. */
const fallback = statusOf({ id: 'opr-f', expects: 'decision', form: 'f', question: 'Approve the Round 2 candidate?', because: CONSTRUCTOR_BECAUSE }, NO_FORM)
eq(fallback, { state: 'incomplete', problems: [{ path: 'because', code: 'unavailable_or_uncertain' }] },
  'the constructor’s fallback is reported as context that cannot be established')
ok(gapsOf(fallback, {}).join(' ').includes('the record does not say why you are being asked'),
  'and is said in words, never as "because (unavailable_or_uncertain)"')
ok(!/unavailable_or_uncertain/.test(gapsOf(fallback, {})[0]), 'the code itself does not reach the owner')
/* AND AN AUTHOR MAY HAVE WRITTEN EXACTLY THOSE WORDS. The record holds the
   same string either way, so the page says the origin cannot be told from it
   rather than that nobody wrote it (ent-9f0291944c9a, owner: the fallback
   phrase cannot prove it was not authored). */
const authored: Asked = {
  id: 'opr-authored', expects: 'decision', form: 'f',
  question: 'Approve the Round 2 candidate?',
  /* a person's own words, which happen to be the constructor's exactly */
  because: CONSTRUCTOR_BECAUSE,
  options: [{ label: 'Approve', consequence: 'it proceeds' }, { label: 'Revise', consequence: 'it is revised' }],
}
const authoredSaid = gapsOf(statusOf(authored, { because: 'the run claimed its work' }), authored, { because: 'the run claimed its work' })
eq(authoredSaid.length, 1, 'the identical phrase is reported once, whoever put it there')
ok(!/is not in the asker|not the asker’s own|nobody wrote|Mentis itself fills/.test(authoredSaid[0]),
  'and the page does not claim it was not authored — the record cannot show that')
ok(/cannot be read from the record|cannot be told from the record/.test(authoredSaid[0]),
  'what is said is that it cannot be read from the record')
ok(authoredSaid[0].includes('the record does not say why you are being asked'),
  'and the missing context is still explained in full')
eq(statusOf(authored, { because: 'b' }).problems, [{ path: 'because', code: 'unavailable_or_uncertain' }],
  'the backends’ own classification of the phrase is unchanged by this wording')

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
eq(statusOf({ ...asked, question: 'Approve this work?' }, group),
  { state: 'incomplete', problems: [{ path: 'presentation.scope', code: 'not_recorded' }, { path: 'presentation.stages', code: 'not_recorded' }] },
  'so the question on it is read as the generated approval the record says it is')

/* -- EVERY CODE EITHER BACKEND EMITS HAS WORDS HERE -------------------------
   Read from the pinned sources: Python `mentis/decision_presentation.py` at
   2f3c2210 (`validate_question`, `fields`) and Rust
   `crates/mentis-ops/src/decision_presentation.rs` at 47796384, whose own
   legacy branch emits the first six. None of them may reach the owner as a
   field path or a code (ent-0fc483e17f76 §B2, ent-622a8338cdb1). */
const BACKEND_PROBLEMS: { path: string; code: string }[] = [
  { path: 'question', code: 'required' },
  { path: 'because', code: 'required' },
  { path: 'because', code: 'unavailable_or_uncertain' },
  { path: 'options[0].consequence', code: 'required' },
  { path: 'presentation.scope', code: 'not_recorded' },
  { path: 'presentation.stages', code: 'not_recorded' },
  { path: 'presentation.version', code: 'unsupported_version' },
  { path: 'presentation', code: 'required' },
  { path: 'presentation', code: 'object' },
  { path: 'presentation.type', code: 'unsupported_type' },
  { path: 'presentation.scope', code: 'required' },
  { path: 'presentation.scope', code: 'nonblank_string' },
  { path: 'presentation.scope', code: 'max_length_2000' },
  { path: 'presentation.stages', code: 'stage_array' },
  { path: 'presentation.stages', code: 'approval_stage_required' },
  { path: 'presentation.primary', code: 'required' },
  { path: 'presentation.primary', code: 'exact_artifact_required' },
  { path: 'presentation.primary', code: 'reference_object' },
  { path: 'presentation.primary.kind', code: 'unsupported_reference_kind' },
  { path: 'presentation.primary.label', code: 'required' },
  { path: 'presentation.primary.label', code: 'max_length_160' },
  { path: 'presentation.primary.id', code: 'record_identity' },
  { path: 'presentation.primary.sha', code: 'full_commit_hash' },
  { path: 'presentation.primary.repository', code: 'required' },
  { path: 'presentation.primary.url', code: 'http_url' },
  { path: 'presentation.primary.extra', code: 'unknown_key' },
  { path: 'presentation.primary_reason', code: 'required' },
  { path: 'presentation.primary_reason', code: 'max_length_2000' },
  { path: 'presentation.supporting', code: 'reference_array_max_24' },
  { path: 'presentation.supporting[0]', code: 'reference_object' },
  { path: 'presentation.supporting[3].id', code: 'record_identity' },
  { path: 'presentation.supporting[3].url', code: 'http_url' },
  { path: 'presentation.applies_when', code: 'max_length_1000' },
  { path: 'presentation.wobble', code: 'unknown_key' },
  { path: 'options', code: 'at_least_two' },
  { path: 'options', code: 'omit_for_free_response' },
  { path: 'options', code: 'choice_options_required' },
  { path: 'options[1].label', code: 'duplicate_label' },
  { path: 'options[1].label', code: 'max_length_200' },
  { path: 'options[1].consequence', code: 'max_length_2000' },
  { path: 'question', code: 'specific_approval_question_required' },
  { path: 'question', code: 'max_length_1000' },
  { path: 'questions', code: 'array_length_1_to_20' },
  { path: 'questions', code: 'use_shorthand_or_batch' },
  { path: 'question', code: 'question_object' },
]
const sample: Asked = { id: 'opr-x', form: 'f', question: 'q', options: [{ label: 'Yes' }, { label: 'No' }] }
for (const p of BACKEND_PROBLEMS) {
  const words = gapWords(p, sample)
  ok(words && /[.!?]$/.test(words), `${p.path}:${p.code} is said as a sentence`)
  ok(!words.includes(p.code), `${p.path}:${p.code} does not show its code`)
  ok(!/presentation\.|\[\d|_[a-z]/.test(words.replace(/[“”].*?[“”]/g, '')),
    `${p.path}:${p.code} does not show a field path`)
}
/* the one sentence a page falls back to names neither */
ok(!/presentation|options|_/.test(gapWords({ path: 'something.new', code: 'brand_new' })),
  'and a code nobody has written words for yet is still not shown as a code')

console.log(`decision presentation: ${checks} checks ok`)
