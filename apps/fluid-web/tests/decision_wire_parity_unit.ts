/* THE PAGE AGAINST THE BACKENDS' OWN PAYLOADS (ent-0fc483e17f76, B1-B3).
 *
 * `fixtures/needs_you_pinned_wire.json` is not a shape anybody retyped: it is
 * what Python 2f3c2210 answered on `/fluid/api/decisions`,
 * `/fluid/api/needs-you/about` and `/fluid/api/needs-you/items` for three
 * representative decisions recorded in a disposable Brain --
 *
 *   legacy_scope_form   the three Agent Presets scope questions, recorded
 *                       before the creation contract;
 *   generated_approval  the run-end "Approve this work?" whose form act
 *                       carries the material it was generated over;
 *   new_contract_form   two questions asked through the validated path, one
 *                       with a declared primary and supporting source, one
 *                       with an explicit `primary: null` and its reason.
 *
 * Rust 47796384 derives the same legacy codes and forwards everything else to
 * Python, so these are the integrated pair's words.
 *
 * What it holds this code to:
 *   - EVERY CODE ON THE WIRE READS AS WORDS. No field path and no code in
 *     front of the owner (§B2).
 *   - THE GENERATED APPROVAL SAYS ITS AUTHORISATION AND STAGE ARE MISSING --
 *     both when the server derives it and when this page has to (§B1).
 *   - WHAT THIS PAGE DERIVES IS WHAT THE BACKEND PROJECTED, problem for
 *     problem, so a page says the same thing whichever answered.
 *   - EACH QUESTION'S REFERENCES ARE ITS OWN, read from `question_references`
 *     keyed by its exact expectation id (§B3). */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import {
  asksAuthority, clarifyNeeded, gapsOf, statusOf, unclear,
  type Asked, type Asking, type PresentationStatus,
} from '../src/experimental/decisionPresentation'
import { questionsOf, type About } from '../src/quiet2/needs/inspect'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }

interface Case {
  decision_form: { form: string; because?: string | null; questions: (Asked & { expectation: string; presentation_status?: PresentationStatus })[] }
  about: About
  item_questions: { expectation: string; question?: string | null }[]
}
/** One question exactly as the pinned Python answered for it, for the three
 *  cases of review ent-be99511604d4 (R1-A, R1-B, R2). `expectation` is the
 *  `/fluid/api/decisions` projection of the question itself; for the
 *  standalone one, `expectation_keys` is every key that projection carried. */
interface Clarification {
  question?: Asked & { presentation_status: PresentationStatus }
  expectation: Asked & { presentation_status: PresentationStatus }
  expectation_keys?: string[]
}
const WIRE = JSON.parse(readFileSync(new URL('./fixtures/needs_you_pinned_wire.json', import.meta.url), 'utf8')) as
  { python: string; cases: Record<string, Case>; clarification_cases: Record<string, Clarification> }

const asked = (q: Case['decision_form']['questions'][number]): Asked => ({ ...q, id: q.expectation })
/* the form row as this page gets it: NO `approval_artifacts` -- `decision_form`
   does not project it, which is why that gate could never fire (§B1), and why
   the page's own derivation rests on the recorded question alone. What follows
   from that is that it may say what is MISSING from such a form, and may not
   say where the form came from (ent-9f0291944c9a). */
const formOf = (c: Case): Asking => ({ because: c.decision_form.because })

for (const [name, c] of Object.entries(WIRE.cases)) {
  for (const q of c.decision_form.questions) {
    const said = q.presentation_status!
    ok(said && typeof said.state === 'string', `${name}: the backend projected a state for every question`)
    /* WHAT THE SERVER SAID, IN WORDS */
    for (const words of gapsOf(said, asked(q))) {
      ok(!/\bpresentation\.|not_recorded|unavailable_or_uncertain|unsupported_|_required\b|\(.*\)/.test(words),
        `${name}: "${words}" shows no field path and no code`)
      ok(/[.!?]$/.test(words.trim()), `${name}: "${words}" is a sentence`)
    }
    /* WHAT THIS PAGE DERIVES WHERE THE SERVER SAYS NOTHING: the same thing */
    const mine = statusOf({ ...asked(q), presentation_status: undefined }, formOf(c))
    eq(mine, said, `${name}: this page derives what the backend projected for ${q.expectation}`)
  }
}

/* -- §B1: THE GENERATED APPROVAL ------------------------------------------- */
const gen = WIRE.cases.generated_approval
const genQ = asked(gen.decision_form.questions[0])
ok(/^approve this work\?/i.test(genQ.question ?? ''), 'it is the real recorded question')
eq(gen.decision_form.questions[0].presentation_status!.problems.map((p) => `${p.path}:${p.code}`),
  ['because:unavailable_or_uncertain', 'presentation.scope:not_recorded', 'presentation.stages:not_recorded'],
  'the backend reports its context as uncertain and its authorisation and stage as not recorded')
for (const status of [gen.decision_form.questions[0].presentation_status!, statusOf({ ...genQ, presentation_status: undefined }, formOf(gen))]) {
  const words = gapsOf(status, genQ, formOf(gen))
  eq(status.state, 'incomplete', 'it is not shown as a complete earlier format')
  eq(unclear(status), true, 'so the owner is offered the way out of it')
  ok(words.some((w) => w.includes('what approving it would permit cannot be read from the record')),
    'and is told, in words, that what approving it would authorise is not in the record')
  ok(words.some((w) => w.includes('at which stage')), 'including at which stage')
  ok(words.some((w) => w.includes('the record does not say why you are being asked')),
    'and that why it is asked cannot be read from the record')
  /* WHAT THE WIRE ACTUALLY CARRIES is the question and the backend's codes --
     nothing that says a run produced this form. On that evidence the page says
     the boundary is missing and leaves the origin unknown (ent-9f0291944c9a). */
  ok(!words.some((w) => /recorded as a generated approval|was generated/.test(w)),
    'and, with no approval material on the wire, no origin is asserted for it')
  ok(words.some((w) => w.includes('The record does not say whether this question was written for this work')),
    'the origin is said to be exactly what it is: not in the record')
  /* AND WHERE A FORM ROW DOES CARRY THE APPROVAL MATERIAL, that provenance is
     kept: the record's own statement, not a reading of the question. */
  const recorded = gapsOf(status, genQ, { ...formOf(gen), approval_artifacts: ['ent-e89925cea328'] })
  ok(recorded.some((w) => w.startsWith('This was recorded as a generated approval.')),
    'a form act that records the approval material keeps its recorded provenance')
  eq(recorded.length, words.length, 'and says the same number of things either way')
}

/* -- §B2: no backend code reaches the owner -------------------------------- */
const seen = new Set<string>()
for (const c of Object.values(WIRE.cases)) {
  for (const q of c.decision_form.questions) for (const p of q.presentation_status!.problems) seen.add(`${p.path}:${p.code}`)
}
eq([...seen].sort(), ['because:unavailable_or_uncertain', 'presentation.scope:not_recorded', 'presentation.stages:not_recorded'],
  'these are the codes the representative records actually put on the wire')
ok(!/The record is missing/.test([...Object.values(WIRE.cases)].flatMap((c) =>
  c.decision_form.questions.flatMap((q) => gapsOf(q.presentation_status!, asked(q)))).join(' ')),
  'and none of them renders as "The record is missing <path> (<code>)."')

/* -- §B3: each question's references are its own --------------------------- */
const newForm = WIRE.cases.new_contract_form
const words = new Map(newForm.item_questions.map((q) => [q.expectation, q.question ?? null]))
const drawn = questionsOf(newForm.about, words)
eq(drawn.length, 2, 'both questions of the form are drawn separately')
eq(drawn.map((q) => q.id), newForm.decision_form.questions.map((q) => q.expectation),
  'each by its own expectation id, in the order asked')
eq(drawn[0].subject.map((r) => r.relation),
  ['the one source this question is about', 'further material this question names'],
  'the first question’s own primary and supporting material are its own')
eq(drawn[1].subject, [], 'and the question that recorded no source of its own is given none of the first’s')
eq(drawn.map((q) => q.question), newForm.item_questions.map((q) => q.question),
  'each group is named by that question’s own recorded wording')
eq(drawn[0].subject.map((r) => [r.state, r.why]), [['missing', 'This Brain holds nothing with this id.'], ['missing', 'This Brain holds nothing with this id.']],
  'a declared source that cannot be read is said to be, and the author’s label never stands in for it')

const legacy = WIRE.cases.legacy_scope_form
const legacyDrawn = questionsOf(legacy.about, new Map(legacy.item_questions.map((q) => [q.expectation, q.question ?? null])))
eq(legacyDrawn.length, 3, 'the three legacy questions are drawn separately too')
eq(legacyDrawn.flatMap((q) => q.subject), [], 'none of them declared a source, and none is invented')
eq(legacy.about.subject, [], 'and the form names no pooled item that could be read as theirs')
ok(legacyDrawn.every((q) => q.presentation_state === 'legacy'), 'each carries the state the backend derived for it')

/* -- R1/R2: ESSENTIAL INFORMATION, ON THE SAME PINNED WIRE -------------------
   Review ent-be99511604d4 reproduced three decisions on the real pinned Python
   whose recorded choices were still offered and still sent. Their payloads are
   that server's own answers (`clarification_cases`, captured the same way as
   the three above), and what they hold this page to is that each of them now
   needs clarifying -- and that nothing else does. */
const CLARIFY = WIRE.clarification_cases
const askOf = (c: Clarification): Asked => ({ ...c.expectation, id: 'opr-wire' })

const consequence = CLARIFY.action_approval_missing_consequence
eq(consequence.expectation.presentation_status.problems, [{ path: 'options[0].consequence', code: 'required' }],
  'R1-A: the pinned server reports exactly one thing missing, and it is not an authority')
eq((consequence.expectation.presentation as { type: string }).type, 'action_approval', 'its scope and its stage ARE recorded')
eq(consequence.expectation.options![0].consequence, undefined, 'and its first alternative has no recorded consequence')
eq(clarifyNeeded(consequence.expectation.presentation_status, askOf(consequence), {}), true,
  'so Approve is not offered as an answer: what choosing it leads to is not in the record')
ok(gapsOf(consequence.expectation.presentation_status, askOf(consequence)).some((w) => w.includes('Choice A “Approve”')),
  'and the owner is told which alternative it is, by its letter and its own recorded words')
eq(statusOf({ ...askOf(consequence), presentation_status: undefined }, {}), consequence.expectation.presentation_status,
  'this page derives the same problem the server projected for it')

const material = CLARIFY.artifact_approval_unreadable_primary
eq(material.expectation.presentation_status.problems, [{ path: 'presentation.primary.id', code: 'record_identity' }],
  'R1-B: the pinned server reports the exact part of the reference that cannot be read')
eq((material.expectation.presentation as { type: string }).type, 'artifact_approval', 'on an approval of something specific')
eq(asksAuthority(askOf(material), {}), true, 'which the record itself declares')
eq(clarifyNeeded(material.expectation.presentation_status, askOf(material), {}), true,
  'so its choices are wording: approving material nobody can look up is not an approval anyone can read')
ok(gapsOf(material.expectation.presentation_status, askOf(material)).some((w) => w.includes('could look up')),
  'and what cannot be read is said in words, with no field path and no code')
eq(statusOf({ ...askOf(material), presentation_status: undefined }, {}), material.expectation.presentation_status,
  'and this page derives the same problem the server projected, so it does not depend on being told')

const standalone = CLARIFY.standalone_generic_approval
ok(!standalone.expectation_keys!.includes('question'),
  'R2: the pinned projection of an ask on its own post carries no question at all')
ok(!standalone.expectation_keys!.includes('presentation'), 'and no presentation object')
ok(standalone.expectation_keys!.includes('presentation_status'), 'what it does carry is the status')
eq(standalone.expectation.presentation_status.problems.map((p) => `${p.path}:${p.code}`),
  ['because:unavailable_or_uncertain', 'presentation.scope:not_recorded', 'presentation.stages:not_recorded'],
  'which reports the missing authorisation boundary of an approval')
eq(asksAuthority(askOf(standalone), {}), false,
  'nothing about the question reaches this page, so nothing about the question can say it may authorise')
eq(clarifyNeeded(standalone.expectation.presentation_status, askOf(standalone), {}), true,
  'and the server’s own problems say it: Approve is not a control, on Decide or on “+ continue”')
ok(gapsOf(standalone.expectation.presentation_status, askOf(standalone), {})
  .some((w) => w.includes('what approving it would permit cannot be read from the record')),
  'and it is said in the same words as on a form')
/* AND WHAT THE SAME WIRE SAYS ABOUT THE DECISIONS THAT ARE SUFFICIENT: the
   three Agent Presets scope questions and the two questions asked through the
   validated path keep every control they had, on the pinned server's own word. */
for (const name of ['legacy_scope_form', 'new_contract_form'] as const) {
  const c = WIRE.cases[name]
  for (const q of c.decision_form.questions) {
    eq(clarifyNeeded(q.presentation_status!, asked(q), formOf(c)), false,
      `${name}: ${q.expectation} is sufficient as recorded, and nothing is taken from it`)
  }
}
eq(clarifyNeeded(gen.decision_form.questions[0].presentation_status!, genQ, formOf(gen)), true,
  'and the generated approval, on the same wire, still needs clarifying')

console.log(`decision wire parity (python ${WIRE.python.slice(0, 8)}): ${checks} checks ok`)
