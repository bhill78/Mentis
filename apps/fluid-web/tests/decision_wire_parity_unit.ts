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
import { gapsOf, statusOf, unclear, type Asked, type Asking, type PresentationStatus } from '../src/experimental/decisionPresentation'
import { questionsOf, type About } from '../src/quiet2/needs/inspect'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }

interface Case {
  decision_form: { form: string; because?: string | null; questions: (Asked & { expectation: string; presentation_status?: PresentationStatus })[] }
  about: About
  item_questions: { expectation: string; question?: string | null }[]
}
const WIRE = JSON.parse(readFileSync(new URL('./fixtures/needs_you_pinned_wire.json', import.meta.url), 'utf8')) as
  { python: string; cases: Record<string, Case> }

const asked = (q: Case['decision_form']['questions'][number]): Asked => ({ ...q, id: q.expectation })
/* the form row as this page gets it: NO `approval_artifacts` -- `decision_form`
   does not project it, which is why that gate could never fire (§B1) */
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
  const words = gapsOf(status, genQ)
  eq(status.state, 'incomplete', 'it is not shown as a complete earlier format')
  eq(unclear(status), true, 'so the owner is offered the way out of it')
  ok(words.some((w) => w.includes('what approving it would permit cannot be read from the record')),
    'and is told, in words, that what approving it would authorise is not in the record')
  ok(words.some((w) => w.includes('at which stage')), 'including at which stage')
  ok(words.some((w) => w.includes('the record does not say why you are being asked')),
    'and that the context recorded with it is not the asker’s own')
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

console.log(`decision wire parity (python ${WIRE.python.slice(0, 8)}): ${checks} checks ok`)
