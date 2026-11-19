/* THE BRAIN RECORD EDITOR'S MODEL (`src/quiet2/brain/author/model.ts`),
 * checked without a server or a browser: what a draft of each of the seven
 * Kinds shows first and keeps behind "+ Add", what is still missing, and
 * exactly what is sent, in what order.
 *
 * THE FIXTURES are what `/api/governance/authoring` answers for a new Brain
 * (`mentis/web/governance_ui.py` over the Kinds' own definitions), written
 * out by hand: rule, decision and lesson through the generic door with a
 * basis offered (a lesson REQUIRES one); a persona through its own door; a
 * conversation instruction through the instruction door; a discipline and a
 * workflow with the forms they declare.
 *
 * THE RULE THAT MATTERS MOST: recording writes a proposal, through every
 * door, and nothing here can establish. That it is so on screen and in the
 * Brain is `tests/test_quiet_brain_author_browser.py`. */
import assert from 'node:assert/strict'
import type { ActivityRow, KindAuthoring } from '../src/surfaces/governance/r2Model'
import {
  KEY, KIND_ORDER, addedBasis, askOf, changedBody, changes, consequence, createSteps, diffWords, dirty, draftFrom,
  emptyDraft, firstFields, hasValue, kindChoices, kindTitle, nameOf, planOf, problem, reviseRequest, sentRows, summaryOf, withKeys,
  type Draft, type Ref,
} from '../src/quiet2/brain/author/model'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }

/* -- the seven Kinds, as the server describes them -------------------------- */

type Authoring = NonNullable<KindAuthoring['authoring']>
const kind = (name: string, fields: string[], authoring: Partial<Authoring> & Pick<Authoring, 'section' | 'door'>, more: Partial<KindAuthoring> = {}): KindAuthoring => ({
  kind: name, fields, meaning: '', standing_apt: true, expects_falsifier: null, requires_basis: null, form: null,
  authoring: { placeable: true, persona_placeable: false, basis: false, declared: false, placement_directs_work: true, standing_apt: true, expects_falsifier: null, ...authoring },
  ...more,
})
const rule = kind('rule', ['text', 'about'], { section: 'rules', door: 'entry', basis: true })
const decision = kind('decision', ['text', 'about'], { section: 'rules', door: 'entry', basis: true })
const lesson = kind('lesson', ['text', 'limits'], { section: 'rules', door: 'entry', basis: true, placement_directs_work: false }, { requires_basis: true })
const persona = kind('persona', ['name', 'behaviour', 'about'], { section: 'personas', door: 'persona', placeable: false })
const instruction = kind('conversation-instruction', ['text', 'about'], { section: 'instructions', door: 'instruction' })
const discipline = kind('discipline', ['name', 'about', 'text', 'tools', 'tool_use', 'requires', 'inputs', 'outputs', 'verification', 'limits'],
  { section: 'disciplines', door: 'entry', persona_placeable: true, declared: true }, {
    form: {
      name: { input: 'line', label: 'Name' },
      about: { input: 'line', label: 'When it applies', help: 'the kind of work this Discipline is for' },
      text: { input: 'text', label: 'Principles and procedure', rows: 12 },
      tools: { input: 'list', label: 'Tools it uses' },
      tool_use: { input: 'text', label: 'Tool use', rows: 6 },
      requires: { input: 'capabilities', label: 'Requires' },
      inputs: { input: 'text', label: 'What it takes', rows: 3 },
      outputs: { input: 'text', label: 'What it produces', rows: 3 },
      verification: { input: 'text', label: 'Verification', rows: 6 },
      limits: { input: 'text', label: 'Known limitations and dependencies', rows: 4 },
    },
  })
const workflow = kind('workflow', ['name', 'about', 'projects', 'text', 'activities', 'decisions', 'done_when', 'evidence', 'interrupted', 'carrier', 'persona', 'requires'],
  { section: 'workflows', door: 'entry', declared: true }, {
    form: {
      name: { input: 'line', label: 'Name' },
      about: { input: 'line', label: 'When it applies' },
      projects: { input: 'list', label: 'Projects it applies to' },
      text: { input: 'text', label: 'How the work proceeds', rows: 8 },
      activities: { input: 'activities', label: 'Activities' },
      decisions: { input: 'list', label: 'Decisions reserved to the owner' },
      done_when: { input: 'text', label: 'Done when', rows: 3 },
      evidence: { input: 'text', label: 'What supports completion', rows: 3 },
      interrupted: { input: 'text', label: 'If interrupted: what remains and how it continues', rows: 4 },
      carrier: { input: 'participant', label: 'Usually carried by' },
      persona: { input: 'persona', label: 'Carried as' },
      requires: { input: 'capabilities', label: 'Requires' },
    },
  })
const SEVEN = [rule, decision, lesson, persona, workflow, discipline, instruction]

const ME = 'ent-owner'
const NOTE: Ref = { ref: 'ent-aaaaaaaaaaaa', label: 'The deploy call was refused.', kind: 'Record' }
const POST: Ref = { ref: 'ent-bbbbbbbbbbbb', label: 'Nobody told me.', kind: 'Post' }
const draft = (more: Partial<Draft> = {}): Draft => ({ ...emptyDraft(), ...more })
const acts = (rows: Partial<ActivityRow>[]) => JSON.stringify(rows)
const SEED = acts([{ key: '', what: '' }])

/* -- 1. "New" lists each Kind by name ---------------------------------------- */
{
  eq(KIND_ORDER, ['rule', 'decision', 'lesson', 'persona', 'workflow', 'discipline', 'conversation-instruction'], 'the order New lists them in')
  const answered = [instruction, discipline, lesson, workflow, persona, decision, rule]   // the server's order is not the menu's
  eq(kindChoices(answered).map((c) => c.kind), KIND_ORDER, 'the seven, in that order, whatever order they are answered in')
  eq(kindChoices(answered).map((c) => c.label), ['Rule', 'Decision', 'Lesson', 'Persona', 'Workflow', 'Discipline', 'Conversation instruction'], 'each by its own name')
  const later = [kind('zeta-note', ['text'], { section: 'x', door: 'entry' }), kind('house_style', ['text'], { section: 'x', door: 'entry' })]
  eq(kindChoices([...later, ...answered]).map((c) => c.label).slice(7), ['House style', 'Zeta note'], 'a Kind declared later follows the seven, in readable words')
  eq(kindChoices([...answered, { ...kind('finding', ['text'], { section: 'x', door: 'entry' }), authoring: null }]).length, 7, 'a Kind that is not authored is not offered')
  eq(kindChoices([lesson, { ...rule, authoring: null }]).map((c) => c.kind), ['lesson'], 'not even one of the seven, where this Brain does not offer it')
  eq(kindChoices([]), [], 'nothing declared, nothing offered')
  eq([kindTitle('conversation-instruction'), kindTitle('house_style')], ['conversation instruction', 'house style'], 'a Kind is named in words')
}

/* -- 2. what is shown first, and what waits behind "+ Add" -------------------- */
{
  const shape = (k: KindAuthoring, mode: 'create' | 'revise' = 'create') => {
    const p = planOf(k, mode)
    return { first: p.first, optional: p.optional, extras: p.extras, needsBasis: p.needsBasis, needsConversation: p.needsConversation }
  }
  eq(shape(rule), { first: ['text'], optional: ['about'], extras: ['basis', 'place'], needsBasis: false, needsConversation: false }, 'a rule: one field; its subject, basis and placement can be added')
  eq(shape(decision), { first: ['text'], optional: ['about'], extras: ['context', 'basis', 'place'], needsBasis: false, needsConversation: false }, 'a decision can also name the question it settles')
  eq(shape(lesson), { first: ['text'], optional: ['limits'], extras: ['place'], needsBasis: true, needsConversation: false }, 'a lesson shows its basis from the start, so it is not behind + Add')
  eq(shape(persona), { first: ['name', 'behaviour'], optional: ['about'], extras: [], needsBasis: false, needsConversation: false }, 'a persona: its name and behaviour; no basis, no placement')
  eq(shape(instruction), { first: ['text'], optional: ['about'], extras: [], needsBasis: false, needsConversation: true }, 'an instruction needs its conversation, and is never placed anywhere else')
  eq(shape(discipline), {
    first: ['name', 'text'], optional: ['about', 'tools', 'tool_use', 'requires', 'inputs', 'outputs', 'verification', 'limits'],
    extras: ['place'], needsBasis: false, needsConversation: false,
  }, 'a discipline: two questions, the eight other parts behind + Add, in the declared order')
  eq(shape(workflow), {
    first: ['name', 'activities'], optional: ['about', 'projects', 'text', 'decisions', 'done_when', 'evidence', 'interrupted', 'carrier', 'persona', 'requires'],
    extras: [], needsBasis: false, needsConversation: false,
  }, 'a workflow: its name and its activities; every other field reachable, and NO plain placement')
  ok(workflow.authoring!.placeable && !planOf(workflow).placeable, 'though the server reports a workflow placeable: it is placed only by reference')
  // the server's own word for it (`by_reference`) is believed where it is given, either way
  const byRef = (k: KindAuthoring, by_reference: boolean): KindAuthoring => ({ ...k, authoring: { ...k.authoring!, by_reference } })
  eq([planOf(byRef(workflow, true)).extras, planOf(byRef(rule, true)).extras], [[], ['basis']], 'a Kind the server says is placed only by reference is never offered a plain placement')
  ok(planOf(byRef(workflow, false)).placeable && planOf(byRef(discipline, false)).placeable, 'and one it says is not, is')
  eq([planOf(discipline).placeable, planOf(discipline).personaPlaceable], [true, true],'a discipline can be placed in a conversation or on a persona')
  eq([planOf(rule).placeable, planOf(rule).personaPlaceable], [true, false], 'a rule only in a conversation')
  ok(!planOf(instruction).placeable && !planOf(persona).placeable, 'an instruction and a persona are not offered a placement')

  // every declared field is somewhere: nothing a Kind has is unreachable
  for (const k of SEVEN) {
    const p = planOf(k)
    eq([...p.first, ...p.optional].sort(), [...k.fields].sort(), `every field of a ${k.kind} is in the first view or behind + Add`)
    eq(p.title, kindTitle(k.kind), `a ${k.kind} is titled by its name`)
  }

  // revising: no placement, no question context; a reason can be added
  eq(shape(rule, 'revise').extras, ['basis', 'because'], 'revising a rule offers its basis and a reason, not a placement')
  eq(shape(decision, 'revise').extras, ['basis', 'because'], 'revising a decision does not re-link its question')
  eq(shape(lesson, 'revise').extras, ['because'], 'a lesson\'s basis is still shown rather than offered')
  eq(shape(discipline, 'revise').extras, ['because'], 'a discipline is not placed by revising it')
  eq(shape(workflow, 'revise').extras, ['because'], 'nor is a workflow')
  ok(!planOf(instruction, 'revise').needsConversation, 'a revised instruction stays in its conversation: none is asked for')
  eq(shape(rule, 'revise').first, ['text'], 'the first view is the same one it was made in')

  // a Kind defined later: its first field, and the form it declares
  const later = kind('house-style', ['body', 'tone'], { section: 'styles', door: 'entry' }, { form: { tone: { input: 'list', label: 'Tone words' } } })
  eq([planOf(later).first, planOf(later).optional, planOf(later).title], [['body'], ['tone'], 'house style'], 'a Kind defined later starts with its first field')
  eq([askOf(planOf(later), 'body'), nameOf(planOf(later), 'tone')], ['Body', 'Tone words'], 'asked in its declared words, or its field name made readable')
  eq(planOf({ ...rule, form: 'not a form' }).form, {}, 'a malformed form declaration is no form, never a failure')

  // the words
  eq([askOf(planOf(rule), 'text'), askOf(planOf(decision), 'text'), askOf(planOf(lesson), 'text')], ['What should be done?', 'What was decided?', 'What was learned?'], 'each Kind is asked its own question')
  eq([nameOf(planOf(rule), 'about'), nameOf(planOf(lesson), 'limits'), nameOf(planOf(discipline), 'tools')], ['Subject', 'Where it stops being true', 'Tools it uses'], 'an optional part is named plainly, or as declared')
  eq(['basis', 'context', 'place', 'because'].map((x) => nameOf(planOf(rule), x)), ['What it is based on', 'The question it settles', 'Where it applies', 'Why it is changing'], 'and so are the parts that are not fields')
}

/* -- 3. what is still missing -------------------------------------------------- */
{
  const say = (k: KindAuthoring, d: Draft, mode: 'create' | 'revise' = 'create', start?: Draft) => problem(planOf(k, mode), k, d, mode, start)

  /* NO KIND IS GIVEN A REQUIRED FIELD ITS DEFINITION DOES NOT HAVE. The
     server records a rule with no words, so nothing here refuses one: only
     what the server refuses, and what an act that follows needs, is asked. */
  for (const k of [rule, decision, discipline]) eq(say(k, draft()), null, `an empty ${k.kind} is not refused here: its definition requires no field`)
  eq(say(workflow, draft({ fields: firstFields(planOf(workflow)) })), null, 'nor is a workflow nobody wrote in, starting activity and all')
  eq(say(lesson, draft())?.part, 'basis', 'an empty lesson is asked only for what the server requires of it: its basis')
  eq(say(rule, draft({ fields: { text: 'Say so first.' } })), null, 'a rule with its words is recorded')
  eq(say(discipline, draft({ fields: { text: 'Drive the real page.' } })), null, 'no Kind is given a required field its definition does not have')
  eq(say(workflow, draft({ fields: { ...firstFields(planOf(workflow)), name: 'Release to TEST' } })), null, 'a workflow with a name and an untouched starting activity can be recorded')

  // persona: name, then behaviour
  eq(say(persona, draft()), { message: 'Give the persona a name.', part: 'name' }, 'a persona needs its name first')
  eq(say(persona, draft({ fields: { behaviour: 'Reads the diff first.' } }))?.part, 'name', 'whatever else is written')
  eq(say(persona, draft({ fields: { name: 'Reviewer' } })), { message: 'Say how the persona should behave.', part: 'behaviour' }, 'then its behaviour')
  eq(say(persona, draft({ fields: { name: 'Reviewer', behaviour: 'Reads the diff first.' } })), null, 'and then nothing more')

  // instruction: text, then conversation
  eq(say(instruction, draft({ conversation: { id: 'ent-c1', name: 'Planning' } })), { message: 'Write the instruction first.', part: 'text' }, 'an instruction needs its words first')
  eq(say(instruction, draft({ fields: { about: 'tone' }, conversation: { id: 'ent-c1', name: 'Planning' } }))?.part, 'text', 'a subject is not the instruction')
  eq(say(instruction, draft({ fields: { text: 'Keep answers short.' } })), { message: 'Choose the conversation it is for.', part: 'conversation' }, 'then the conversation it is for')
  eq(say(instruction, draft({ fields: { text: 'Keep answers short.' }, conversation: { id: 'ent-c1', name: 'Planning' } })), null, 'and then it can be recorded')

  // basis
  const learned = { text: 'A hosted run cannot restart its host.' }
  eq(say(lesson, draft({ fields: learned })), { message: 'A lesson has to be based on something already held. Choose at least one.', part: 'basis' }, 'a lesson needs its basis')
  eq(say(lesson, draft({ fields: learned, basis: [NOTE] })), null, 'and is not asked how the evidence leads to it')
  eq(say(rule, draft({ fields: { text: 'Say so.' }, basis: [NOTE] })), { message: 'Say how what you chose leads to this.', part: 'basisReason' }, 'an optional basis is cited with a reason')
  eq(say(rule, draft({ fields: { text: 'Say so.' }, basis: [NOTE], basisReason: '  ' }))?.part, 'basisReason', 'which spaces are not')
  eq(say(rule, draft({ fields: { text: 'Say so.' }, basis: [NOTE], basisReason: 'It is what happened.' })), null, 'given, it can be recorded')

  // placement: where, then why
  const place = { to: 'conversation' as const, where: '', name: '', reason: '' }
  eq(say(rule, draft({ fields: { text: 'Say so.' }, place })), { message: 'Choose the conversation.', part: 'place' }, 'a placement needs its conversation')
  eq(say(discipline, draft({ fields: { text: 'Do it so.' }, place: { ...place, to: 'persona' } }))?.message, 'Choose the persona.', 'or its persona')
  eq(say(rule, draft({ fields: { text: 'Say so.' }, place: { ...place, where: 'ent-c1', name: 'Planning' } })), { message: 'Say why it belongs there.', part: 'placeReason' }, 'then its reason')
  eq(say(rule, draft({ fields: { text: 'Say so.' }, place: { ...place, where: 'ent-c1', name: 'Planning', reason: 'It was asked here.' } })), null, 'and then nothing more')
  eq(say(rule, draft({ fields: { text: 'Say so.' }, basis: [NOTE], place }))?.part, 'basisReason', 'one thing at a time: the evidence before the placement')

  // activities
  const wf = (rows: Partial<ActivityRow>[]) => draft({ fields: { name: 'Release to TEST', activities: acts(rows) } })
  eq(say(workflow, wf([{ key: '', what: 'Build' }, { key: '', what: 'Verify' }, { key: '', what: '' }])),
    { message: 'Activity 3 is empty. Write it or remove it.', part: 'activities', index: 2 }, 'an empty extra activity is named by its number, and pointed at')
  eq(say(workflow, wf([{ key: '', what: '' }, { key: '', what: 'Verify' }]))?.index, 0, 'whichever one it is')
  eq(say(workflow, wf([{ key: 'kept', what: '' }]))?.message, 'Activity 1 is empty. Write it or remove it.', 'a lone activity somebody named is an activity, and is empty')
  eq(say(workflow, wf([{ key: 'not a key', what: 'Build' }]))?.message,
    'Activity 1\'s short name can use letters, digits, _ . and -, up to 40, starting with a letter or digit.', 'a short name the server would refuse is said here')
  eq(say(workflow, wf([{ key: 'build', what: 'Build' }, { key: 'build', what: 'Build again' }])),
    { message: 'Two activities have the short name "build". Each needs its own.', part: 'activities', index: 1 }, 'and so are two with the same one')
  eq(say(workflow, wf([{ key: 'build', what: 'Build' }, { key: '', what: 'Build' }])), null, 'a new activity never collides with a kept one: its key is made unique')

  // revising
  const revise = (k: KindAuthoring, body: Record<string, unknown>, basis: Ref[], change: (d: Draft) => Draft) => {
    const start = draftFrom(planOf(k, 'revise'), body, basis)
    return say(k, change(start), 'revise', start)
  }
  eq(revise(rule, { text: 'Say so.', about: 'deploys' }, [], (d) => d), { message: 'Nothing has changed yet.', part: 'text' }, 'an unchanged revision is not recorded')
  eq(revise(rule, { text: 'Say so.' }, [], (d) => ({ ...d, because: 'It was unclear.' }))?.message, 'Nothing has changed yet.', 'a reason alone changes nothing')
  eq(revise(rule, { text: 'Say so.' }, [], (d) => ({ ...d, fields: { ...d.fields, text: 'Say so first.' } })), null, 'a reworded one is, with no reason asked')
  eq(revise(rule, { text: 'Say so.' }, [], (d) => ({ ...d, basis: [NOTE] })), { message: 'Say why this is being added.', part: 'because' }, 'evidence added to unchanged wording needs its reason')
  eq(revise(rule, { text: 'Say so.' }, [], (d) => ({ ...d, basis: [NOTE], because: 'It happened again.' })), null, 'and is recorded with one')
  const removal = revise(rule, { text: 'Say so.' }, [NOTE, POST], (d) => ({ ...d, basis: [NOTE], because: 'Not relevant.' }))
  ok(removal?.message.startsWith('What it is based on can be taken away only together with a change to its wording'), 'evidence cannot be taken from a record whose wording is unchanged')
  eq(revise(rule, { text: 'Say so.' }, [NOTE, POST], (d) => ({ ...d, basis: [NOTE], fields: { ...d.fields, text: 'Say so first.' } })), null, 'with a rewording it can: the new version carries its own evidence')
  eq(revise(lesson, learned, [NOTE], (d) => ({ ...d, basis: [], fields: { ...d.fields, text: 'A hosted run can never restart its host.' } }))?.part, 'basis', 'a lesson still cannot be left with none')
  eq(revise(lesson, learned, [NOTE], (d) => ({ ...d, basis: [NOTE, POST], because: 'Again.' })), null, 'a lesson\'s evidence can be added to')
  eq(say(rule, draft({ fields: { text: 'Say so.' }, basis: [NOTE] }), 'revise', draft({ fields: { text: 'Say so.' } }))?.part, 'because', 'revising never asks how the evidence leads to it: that is the create\'s question')
}

/* -- 4. activity keys ----------------------------------------------------------- */
{
  const keyed = withKeys([
    { key: 'build', what: 'Build the release' }, { key: '', what: 'Build the release' }, { key: '', what: 'Build the release' },
    { key: '', what: 'build' }, { key: '', what: '   ' }, { key: '', what: '!!! ???' }, { key: ' Kept As Is ', what: 'x' },
    { key: '', what: 'Verify it headlessly, then ask the owner who runs the deploy step before anything else happens' },
    { key: '', what: 'Über-prüfen: Größe' }, { key: '', what: 'verify' }, { key: 'verify', what: 'An older activity, later in the list' },
  ])
  const keys = keyed.map((r) => r.key)
  eq([keys[0], keys[6], keys[10]], ['build', ' Kept As Is ', 'verify'], 'a key an activity already has is kept verbatim, valid or not: delegated work is labelled by it')
  eq(keys.slice(1, 6), ['build-the-release', 'build-the-release-2', 'build-2', 'activity', 'activity-2'], 'a new key is made from its words, unique when words repeat or meet an existing key; no words, "activity"')
  eq(keys[9], 'verify-2', 'unique against a key that comes LATER in the list too')
  const made = keys.filter((_, i) => ![0, 6, 10].includes(i))
  ok(made.every((k) => KEY.test(k)), 'every key made here is one the server accepts: ' + made.join(' '))
  ok(made.every((k) => /^[A-Za-z0-9][A-Za-z0-9_.-]{0,39}$/.test(k)), 'which is letters, digits, _ . and -, at most 40, starting with a letter or digit')
  eq(new Set(keys).size, keys.length, 'and no two activities share one')
  eq(keyed.map((r) => r.what), ['Build the release', 'Build the release', 'Build the release', 'build', '   ', '!!! ???', 'x',
    'Verify it headlessly, then ask the owner who runs the deploy step before anything else happens', 'Über-prüfen: Größe', 'verify', 'An older activity, later in the list'], 'nothing else about an activity is touched')
  const many = withKeys(Array.from({ length: 30 }, () => ({ key: '', what: 'The very same words every single time, longer than a key may be' })))
  ok(new Set(many.map((r) => r.key)).size === 30 && many.every((r) => KEY.test(r.key)), 'thirty activities with the same long words still get thirty valid keys')
  eq(withKeys([]), [], 'no activities, no keys')
  const whoKept = withKeys([{ key: '', what: 'Ask', who: { role: 'a reviewer' }, default_tier: 'coding' }])[0]
  eq([whoKept.who, whoKept.default_tier], [{ role: 'a reviewer' }, 'coding'], 'an activity keeps who carries it and its settings when it is given a key')
}

/* -- 5. what is sent when making a record ---------------------------------------- */
{
  const steps = (k: KindAuthoring, d: Draft) => createSteps(planOf(k), k, d, ME)
  const NEW = 'ent-new000000'
  const filled: [KindAuthoring, Draft][] = [
    [rule, draft({ fields: { text: 'Say so first.' } })],
    [decision, draft({ fields: { text: 'Releases go to TEST first.' } })],
    [lesson, draft({ fields: { text: 'A hosted run cannot restart its host.' }, basis: [NOTE] })],
    [persona, draft({ fields: { name: 'Reviewer', behaviour: 'Reads the diff first.' } })],
    [workflow, draft({ fields: { name: 'Release to TEST', activities: acts([{ key: '', what: 'Build' }]) } })],
    [discipline, draft({ fields: { name: 'Headless verification', text: 'Drive the real page.' } })],
    [instruction, draft({ fields: { text: 'Keep answers short.' }, conversation: { id: 'ent-c1', name: 'Planning' } })],
  ]
  for (const [k, d] of filled) {
    const s = steps(k, d)
    eq(s[0].name, 'record', `a ${k.kind} is recorded first`)
    eq(s[0].body.establish, false, `EVERY KIND: a new ${k.kind} says establish: false, whatever the server's default is`)
    eq(s[0].body.attributed_to, ME, `a ${k.kind} is attributed to the reader`)
    ok(s.every((x) => !x.path(NEW).includes('establish')), `nothing sent for a ${k.kind} is an establishment`)
    eq(s.length, 1, `a ${k.kind} with nothing added is one act`)
  }

  // the three doors
  eq(steps(rule, filled[0][1])[0].path(null), '/api/entries', 'a rule goes through the generic door')
  eq(steps(rule, filled[0][1])[0].body, { kind: 'rule', body: { text: 'Say so first.', about: '' }, attributed_to: ME, establish: false, falsifier: '', links: [] }, 'as exactly this')
  eq(steps(persona, filled[3][1])[0].path(null), '/api/personas', 'a persona through its own')
  eq(steps(persona, filled[3][1])[0].body, { name: 'Reviewer', behaviour: 'Reads the diff first.', about: '', attributed_to: ME, propose: true, establish: false }, 'saying propose: true AND establish: false')
  eq(steps(instruction, filled[6][1])[0].path(null), '/api/conversations/ent-c1/instructions', 'an instruction is written to the conversation chosen')
  eq(steps(instruction, filled[6][1])[0].body, { text: 'Keep answers short.', about: '', attributed_to: ME, establish: false }, 'as a proposal')
  eq(steps(instruction, draft({ fields: { text: 'x' }, conversation: { id: 'ent c/1', name: 'Odd' } }))[0].path(null), '/api/conversations/ent%20c%2F1/instructions', 'the conversation id is the one chosen, safely in the path')
  eq(steps(instruction, draft({ fields: { text: 'x' }, conversation: { id: 'ent-c2', name: 'Other' }, basis: [NOTE], place: { to: 'conversation', where: 'ent-c9', name: 'N', reason: 'r' } })).length, 1,
    'an instruction is one act: it is neither cited nor placed elsewhere')

  // a lesson's basis rides on the create
  const made = steps(lesson, draft({ fields: { text: 'It failed twice.', limits: 'hosted runs' }, basis: [NOTE, POST] }))
  eq(made.map((x) => x.name), ['record'], 'a lesson has no derive-from step: its basis would be linked twice')
  eq(made[0].body, { kind: 'lesson', body: { text: 'It failed twice.', limits: 'hosted runs' }, attributed_to: ME, establish: false, falsifier: '', links: [], basis: [NOTE.ref, POST.ref] }, 'it carries its basis in the create')

  // a rule with evidence and a placement: three acts, in this order
  const three = steps(rule, draft({ fields: { text: 'Say so.' }, basis: [NOTE, POST], basisReason: '  It is what happened. ',
    place: { to: 'conversation', where: 'ent-c1', name: 'Planning', reason: ' It was asked here. ' } }))
  eq(three.map((x) => x.name), ['record', 'evidence', 'placement'], 'the record, then what it is based on, then where it applies')
  eq(three.map((x) => x.path(NEW)), ['/api/entries', `/api/entries/${NEW}/derive-from`, `/api/entries/${NEW}/place`], 'the later acts are on the record the first one made')
  ok(!('basis' in three[0].body), 'a rule\'s create carries no basis')
  eq(three[1].body, { attributed_to: ME, from: [NOTE.ref, POST.ref], because: 'It is what happened.' }, 'the evidence is cited with its reason')
  eq(three[2].body, { attributed_to: ME, where: 'ent-c1', because: 'It was asked here.' }, 'and it is placed with its own')
  eq(steps(rule, draft({ fields: { text: 'Say so.' }, place: { to: 'conversation', where: 'ent-c1', name: 'P', reason: 'r' } })).map((x) => x.name), ['record', 'placement'], 'no evidence, no citation')
  eq(steps(lesson, draft({ fields: { text: 'L' }, basis: [NOTE], place: { to: 'conversation', where: 'ent-c1', name: 'P', reason: 'r' } })).map((x) => x.name), ['record', 'placement'], 'a placed lesson: its basis in the create, then its placement')
  eq(steps(discipline, draft({ fields: { text: 'D' }, place: { to: 'persona', where: 'ent-p1', name: 'Reviewer', reason: 'r' } }))[1].body.where, 'ent-p1', 'a discipline placed on a persona names the persona')

  // a decision's question
  eq(steps(decision, draft({ fields: { text: 'Yes.' }, context: POST }))[0].body.links, [{ relation: 'in-context', to: POST.ref }], 'a decision is linked to the question it settles')
  eq(steps(decision, draft({ fields: { text: 'Yes.' } }))[0].body.links, [], 'or to nothing')

  // fields as the server stores them
  const d = steps(discipline, draft({ fields: { name: 'Headless', text: 'Drive it.', tools: 'playwright\n\n pytest \n', requires: 'drive_browser\nbuild_ui' } }))[0].body.body as Record<string, unknown>
  eq([d.tools, d.requires, d.about], [['playwright', 'pytest'], ['drive_browser', 'build_ui'], ''], 'a list is sent as a list, one per line, blanks dropped; a line as text')
  const w = steps(workflow, draft({ fields: { name: 'Release', activities: acts([
    { key: '', what: 'Build the release', done_when: ' ' }, { key: 'verify', what: 'Verify it', who: { role: 'a reviewer', persona: '' }, default_tier: 'coding' },
    { key: '', what: 'Ask who deploys', coordinates: true, disciplines: ['ent-d1'] }]) } }))[0].body.body as Record<string, unknown>
  eq(w.activities, [
    { key: 'build-the-release', what: 'Build the release' }, { key: 'verify', what: 'Verify it', who: { role: 'a reviewer' }, default_tier: 'coding' },
    { key: 'ask-who-deploys', what: 'Ask who deploys', disciplines: ['ent-d1'], coordinates: true }], 'activities are sent with their keys, and empty parts left out')
  eq([w.projects, w.decisions, w.requires, w.carrier, w.persona], [[], [], [], '', ''], 'the rest as what they are: lists as lists, a participant and a persona as text')
  eq((steps(workflow, draft({ fields: { ...firstFields(planOf(workflow)), name: 'Release' } }))[0].body.body as Record<string, unknown>).activities, [], 'the untouched starting activity is not sent')
}

/* -- 6. the starting activity ----------------------------------------------------- */
{
  eq(firstFields(planOf(workflow)), { activities: SEED }, 'a new workflow starts with one activity to write in')
  for (const k of [rule, decision, lesson, persona, discipline, instruction]) eq(firstFields(planOf(k)), {}, `a new ${k.kind} starts with nothing`)
  eq(sentRows(SEED), [], 'a lone activity nobody wrote in is the starting row, not an activity')
  eq(sentRows(''), [], 'nor is nothing')
  eq(sentRows('not json'), [], 'and text that is not rows is no rows, never a failure')
  eq(sentRows(acts([{ key: '', what: 'Build' }])).length, 1, 'written in, it is sent')
  eq(sentRows(acts([{ key: 'build', what: '' }])).length, 1, 'named, it is an activity (and is then said to be empty)')
  eq(sentRows(acts([{ key: '', what: '' }, { key: '', what: '' }])).length, 2, 'two empty ones were made by the reader: both are kept, to be asked about')
  ok(!hasValue(planOf(workflow), 'activities', SEED) && hasValue(planOf(workflow), 'activities', acts([{ key: '', what: 'Build' }])), 'the starting row is not a value; a written one is')
  ok(!hasValue(planOf(rule), 'text', '  ') && !hasValue(planOf(rule), 'text', undefined) && hasValue(planOf(rule), 'text', 'x'), 'spaces are not a value')
}

/* -- 7. what a revision sends ------------------------------------------------------- */
{
  const plan = planOf(rule, 'revise')
  const start = draftFrom(plan, { text: 'Ask who deploys.', about: 'deploys' }, [NOTE])
  const reworded = { ...start, fields: { ...start.fields, text: 'Ask who deploys, before building.' } }
  eq(changedBody(plan, start, start), {}, 'nothing changed, nothing sent')
  eq(changedBody(plan, start, reworded), { text: 'Ask who deploys, before building.' }, 'only the field that changed')
  eq(changedBody(plan, start, { ...reworded, fields: { ...reworded.fields, about: '' } }), { text: 'Ask who deploys, before building.', about: '' }, 'a field emptied is a change')
  eq(reviseRequest(plan, start, reworded, ME), { attributed_to: ME, body: { text: 'Ask who deploys, before building.' } }, 'the edit act: who, and what changed; no reason, no basis, where neither was given')
  eq(reviseRequest(plan, start, { ...reworded, because: '  It was read two ways. ' }, ME).because, 'It was read two ways.', 'a reason goes with it only when one was given')
  ok(!('because' in reviseRequest(plan, start, { ...reworded, because: '   ' }, ME)), 'spaces are not a reason')
  ok(!('basis' in reviseRequest(plan, start, { ...reworded, basis: [{ ...NOTE, label: 'the same record, read again' }] }, ME)), 'the basis is not sent where it was left alone: the new version rests on what this one rests on')
  eq(reviseRequest(plan, start, { ...reworded, basis: [NOTE, POST] }, ME).basis, [NOTE.ref, POST.ref], 'changed, it is sent whole')
  eq(reviseRequest(plan, start, { ...reworded, basis: [] }, ME).basis, [], 'and so is its removal')
  ok(!JSON.stringify(reviseRequest(plan, start, { ...reworded, basis: [POST], because: 'x' }, ME)).includes('establish'), 'a revision never says anything about standing')

  // lists and activities
  const dp = planOf(discipline, 'revise')
  const dstart = draftFrom(dp, { name: 'Headless', text: 'Drive it.', tools: ['playwright', 'pytest'], requires: ['drive_browser'] }, [])
  eq(changedBody(dp, dstart, { ...dstart, fields: { ...dstart.fields, tools: 'playwright\npytest\n' } }), {}, 'a trailing empty row is not a change to a list')
  eq(changedBody(dp, dstart, { ...dstart, fields: { ...dstart.fields, tools: 'playwright\npytest -q' } }), { tools: ['playwright', 'pytest -q'] }, 'a changed row sends the list as a list')
  eq(changedBody(dp, dstart, { ...dstart, fields: { ...dstart.fields, requires: '' } }), { requires: [] }, 'an unchecked capability sends the shorter list')

  const wp = planOf(workflow, 'revise')
  const stored = [{ key: 'build', what: 'Build the release', default_tier: 'coding' }, { key: 'verify', what: 'Verify it', who: { role: 'a reviewer' } }]
  const wstart = draftFrom(wp, { name: 'Release to TEST', activities: stored }, [])
  eq(changedBody(wp, wstart, wstart), {}, 'a workflow read back and not touched changes nothing')
  const grown = { ...wstart, fields: { ...wstart.fields, activities: acts([{ ...stored[0], what: 'Build the release from a clean checkout' }, stored[1], { key: '', what: 'Verify it' }]) } }
  const sentBody = changedBody(wp, wstart, grown)
  eq(Object.keys(sentBody), ['activities'], 'only its activities are sent')
  eq(sentBody.activities, [
    { key: 'build', what: 'Build the release from a clean checkout', default_tier: 'coding' }, { key: 'verify', what: 'Verify it', who: { role: 'a reviewer' } },
    { key: 'verify-it', what: 'Verify it' }], 'every activity keeps its key and its settings; the new one gets a key of its own')
  const moved = { ...wstart, fields: { ...wstart.fields, activities: acts([stored[1], stored[0]]) } }
  eq((changedBody(wp, wstart, moved).activities as ActivityRow[]).map((a) => a.key), ['verify', 'build'], 'reordered, each key travels with its activity')

  // evidence added with no rewording
  eq(addedBasis(plan, start, { ...start, basis: [NOTE, POST] }), [POST], 'evidence added to unchanged wording is what is cited: only the additions')
  eq(addedBasis(plan, start, start), null, 'nothing added, nothing to cite')
  eq(addedBasis(plan, start, { ...reworded, basis: [NOTE, POST] }), null, 'reworded, it is a new version instead')
  eq(addedBasis(plan, start, { ...start, basis: [POST] }), null, 'a replacement is not an addition')
  eq(addedBasis(plan, start, { ...start, basis: [] }), null, 'nor is a removal')

  // what changes, in words
  const shown = changes(plan, start, reworded)
  eq(shown.map((c) => [c.field, c.name]), [['text', 'What should be done?']], 'what changes is shown per changed field, under its question')
  eq(shown[0].pieces.filter((p) => p.op === 'add').map((p) => p.text.trim()), ['deploys, before building.'], 'as the words that are new')
  eq(changes(plan, start, start), [], 'nothing changed, nothing shown')
}

/* -- 8. has anything been written ---------------------------------------------------- */
{
  const rp = planOf(rule)
  const blank = draft()
  ok(!dirty(rp, blank, draft()), 'an untouched draft holds nothing')
  ok(!dirty(rp, blank, draft({ open: ['about', 'basis'] })), 'opening a part is not writing in it')
  ok(dirty(rp, blank, draft({ fields: { text: 'Half a rule' } })), 'typed words are held')
  ok(dirty(rp, blank, draft({ fields: { about: 'deploys' } })), 'in an optional part too')
  ok(dirty(rp, blank, draft({ basis: [NOTE] })), 'a chosen reference is held')
  ok(dirty(rp, blank, draft({ basisReason: 'because' })), 'and the reason beside it')
  ok(dirty(planOf(decision), blank, draft({ context: POST })), 'the question a decision settles is held')
  ok(dirty(rp, blank, draft({ place: { to: 'conversation', where: '', name: '', reason: '' } })), 'a placement begun is held, before anything is chosen in it')
  ok(dirty(rp, blank, draft({ because: 'why' })), 'a reason for a revision is held')
  ok(!dirty(rp, draft({ basis: [NOTE] }), draft({ basis: [{ ...NOTE, label: 'read again' }] })), 'the same reference under other words is not a change')

  const wp = planOf(workflow)
  const wstart = draft({ fields: firstFields(wp) })
  ok(!dirty(wp, wstart, draft({ fields: firstFields(wp) })), 'a new workflow\'s seeded activity is not something the reader wrote')
  ok(dirty(wp, wstart, draft({ fields: { activities: acts([{ key: '', what: '' }, { key: '', what: '' }]) } })), 'an activity added and still empty is structure the reader made')
  ok(dirty(wp, wstart, draft({ fields: { activities: acts([{ key: '', what: 'Build' }]) } })), 'words in the starting activity are held')
  ok(dirty(wp, wstart, draft({ fields: { ...firstFields(wp), carrier: 'ent-p1' } })), 'a chosen participant is held')

  const dp = planOf(discipline)
  ok(dirty(dp, blank, draft({ fields: { tools: '\n' } })), 'a list row added and still empty is held')
  ok(dirty(dp, blank, draft({ fields: { requires: 'drive_browser' } })), 'a ticked capability is held')

  const ip = planOf(instruction)
  const here = draft({ conversation: { id: 'ent-c1', name: 'Planning' } })
  ok(!dirty(ip, here, draft({ conversation: { id: 'ent-c1', name: 'Planning (renamed)' } })), 'the conversation the reader was already in is not a change')
  ok(dirty(ip, here, draft({ conversation: { id: 'ent-c2', name: 'Elsewhere' } })), 'choosing another is')

  // revising: against the record as it was read
  const rv = planOf(rule, 'revise')
  const start = draftFrom(rv, { text: 'Say so.', about: 'deploys' }, [NOTE])
  ok(!dirty(rv, start, draftFrom(rv, { text: 'Say so.', about: 'deploys' }, [NOTE])), 'a revision just opened holds nothing')
  ok(dirty(rv, start, { ...start, fields: { ...start.fields, text: 'Say so first.' } }), 'a changed word is held')
  ok(dirty(rv, start, { ...start, basis: [] }), 'and so is evidence taken away')
}

/* -- 9. what recording will do, in one line -------------------------------------------- */
{
  eq(consequence('create', { standingApt: true }), 'Records a proposal. It is not in effect until you establish it.', 'making: a proposal, and it says so')
  eq(consequence('create', { standingApt: false }), 'Records it. Standing does not apply to this kind.', 'a Kind standing does not apply to is not called a proposal')
  eq(consequence('revise', { standingApt: true, editMode: 'proposed' }), 'Records a proposed new version. The current one stays in effect until you establish the new one.', 'revising what stands leaves it standing')
  eq(consequence('revise', { standingApt: true, editMode: 'candidate' }), 'Replaces this proposal with the new wording. It is still a proposal.', 'revising a proposal replaces it')
  eq(consequence('revise', { standingApt: true, editMode: 'candidate', placed: 2 }), 'Replaces this proposal with the new wording. It is still a proposal. It stays placed where this one is.', 'and a placed one is told its placement carries over')
  eq(consequence('revise', { standingApt: true, editMode: 'candidate', placed: 0 }), 'Replaces this proposal with the new wording. It is still a proposal.', 'one placed nowhere is not')
  ok(!consequence('revise', { standingApt: true, editMode: 'proposed', placed: 3 }).includes('stays placed'), 'the placement sentence belongs to the replaced proposal only')
  eq(consequence('revise', { standingApt: false, editMode: 'direct' }), 'Saves a new version. It replaces the current one now; the old one is kept.', 'a record standing does not apply to is saved as a new version')
  eq(consequence('revise', { standingApt: true, editMode: null }), 'Saves a new version. It replaces the current one now; the old one is kept.', 'and so is anything the server names no mode for')
  for (const mode of ['proposed', 'candidate', 'direct', null]) ok(!/\bestablish(es|ed)?\b this|in effect now/i.test(consequence('revise', { standingApt: true, editMode: mode, placed: 1 })), `revising (${mode}) never claims to put anything in effect`)
}

/* -- 10. what changes, word by word ------------------------------------------------------ */
{
  const was = 'Ask the owner who runs the deploy step.', now = 'Ask the owner who runs the deploy step, before building.'
  const pieces = diffWords(was, now)
  eq(pieces.filter((p) => p.op !== 'cut').map((p) => p.text).join(''), now, 'what is kept and what is added reads as the new wording')
  eq(pieces.filter((p) => p.op !== 'add').map((p) => p.text).join(''), was, 'what is kept and what is cut reads as the old one')
  eq(pieces.filter((p) => p.op === 'add').map((p) => p.text.trim()), ['step, before building.'], 'the added words, as words')
  eq(pieces.filter((p) => p.op === 'cut').map((p) => p.text.trim()), ['step.'], 'and the ones they take the place of')
  eq(pieces[0], { op: 'same', text: 'Ask the owner who runs the deploy ' }, 'unchanged words are one run, not one piece per word')
  eq(diffWords('The same words.', 'The same words.'), [{ op: 'same', text: 'The same words.' }], 'nothing changed is all the same')
  eq(diffWords('', 'New words.'), [{ op: 'add', text: 'New words.' }], 'written where there was nothing: all added')
  eq(diffWords('Old words.', ''), [{ op: 'cut', text: 'Old words.' }], 'emptied: all cut')
  eq(diffWords('', ''), [], 'nothing to nothing is nothing')
  const mid = diffWords('one two three', 'one 2 three')
  eq([mid.filter((p) => p.op === 'cut').map((p) => p.text), mid.filter((p) => p.op === 'add').map((p) => p.text)], [['two'], ['2']], 'a word changed in the middle is that word')
  const long = 'word '.repeat(700)
  eq(diffWords(long, long + 'more'), [{ op: 'cut', text: long }, { op: 'add', text: long + 'more' }], 'a very long wording is said whole rather than freezing the page')
}

/* -- 11. a draft from a record ------------------------------------------------------------ */
{
  const dp = planOf(discipline, 'revise')
  const from = draftFrom(dp, { name: 'Headless', text: 'Drive it.', about: 'verifying', tools: ['playwright', 'pytest'], requires: ['drive_browser'], limits: '', inputs: '   ' }, [NOTE])
  eq(from.open, ['about', 'tools', 'requires'], 'every optional field that already says something is on screen, in the Kind\'s order; an empty one is not')
  eq([from.fields.name, from.fields.tools, from.fields.requires, from.fields.outputs], ['Headless', 'playwright\npytest', 'drive_browser', ''], 'each value as its input edits it: a list one per line, a missing field empty')
  eq(from.basis, [NOTE], 'with the evidence it rests on')
  eq([from.because, from.place, from.context, from.conversation, from.basisReason], ['', null, null, null, ''], 'and nothing else begun')

  const wp = planOf(workflow, 'revise')
  const rows = [{ key: 'build', what: 'Build' }]
  const wf = draftFrom(wp, { name: 'Release', activities: rows, about: 'releases', done_when: 'TEST serves it', projects: ['mentis'], carrier: 'ent-p1', persona: 'ent-persona', requires: [] }, [])
  eq(wf.open, ['about', 'projects', 'done_when', 'carrier', 'persona'], 'a workflow opens what it has: its lists, its carrier and its persona included')
  eq(JSON.parse(wf.fields.activities), rows, 'its activities are read back as they are stored, keys and all')
  for (const [k, body] of [[rule, { text: 'R', about: 'a' }], [decision, { text: 'D', about: 'a' }], [lesson, { text: 'L', limits: 'x' }], [persona, { name: 'P', behaviour: 'B', about: 'a' }], [instruction, { text: 'I', about: 'a' }]] as [KindAuthoring, Record<string, unknown>][]) {
    const p = planOf(k, 'revise')
    eq(draftFrom(p, body, []).open, p.optional, `a ${k.kind}'s optional field is open when it has a value`)
    eq(draftFrom(p, Object.fromEntries(p.first.map((f) => [f, body[f]])), []).open, [], `and closed when it has none`)
  }
  eq(draftFrom(planOf(rule, 'revise'), {}, []).fields, { text: '', about: '' }, 'a record with no body reads as empty fields, never a failure')

  // a collapsed part, in one line
  eq(summaryOf(dp, 'tools', from.fields.tools), 'playwright, pytest', 'a list reads as its items')
  eq([summaryOf(wp, 'activities', wf.fields.activities), summaryOf(wp, 'activities', acts([rows[0], rows[0]]))], ['1 activity', '2 activities'], 'activities as how many')
  eq([summaryOf(wp, 'carrier', 'ent-p1', { 'ent-p1': '@Builder' }), summaryOf(wp, 'carrier', 'ent-p1'), summaryOf(wp, 'carrier', '')], ['@Builder', 'Chosen', ''], 'a participant by name, never by id')
}

console.log(`brain_author_unit: ${checks} checks passed`)
