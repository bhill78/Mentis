/* A HALF-MADE ANSWER IS ONLY FOR WHAT IT WAS MADE AGAINST, AND WHAT IS SHOWN
 * ABOUT A REQUEST IS ONLY ITS LATEST READ, checked without a browser:
 * a question re-asked with its options reordered or changed discards the
 * draft; a repeated adoption request, or a re-worded proposal, starts empty;
 * an older inspection answer arriving last is ignored; details being read
 * again are said to be; a failed read is never shown as current details; an
 * input's form is found by its exact post, part and name.
 * (Drafts are in memory only: nothing here stores anything.) */
import assert from 'node:assert/strict'
import { askSignature, drafts, draftsTold, dropNotAsked, madeAgainst, madeFor, signature, stillFor, type AskLike } from '../src/experimental/draftKeep'
import { createAdoptionDrafts } from '../src/quiet2/brain/adoptionDraft'
import { createAboutStore } from '../src/quiet2/needs/about'
import type { About } from '../src/quiet2/needs/inspect'
import { blockOf, pickBlock } from '../src/quiet2/needs/land'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }

ok(signature(['a', 'b']) !== signature(['b', 'a']), 'order is part of what a draft was made against')
eq(signature({ a: 1 }), signature({ a: 1 }), 'and the same thing signs the same')

/* -- a question's draft ---------------------------------------------------------- */
const ASK: AskLike = { id: 'opr-ask', expects: 'decision', form: 'opr-form', question: 'Apply it tonight?',
  options: [{ label: 'Apply it', consequence: 'links are stripped' }, { label: 'Hold the migration', consequence: 'nothing changes' }] }
{
  const pick = { kind: 'option', option: 1 } as const
  const made = madeAgainst(ASK, pick)
  eq(made, { sig: askSignature(ASK), label: 'Hold the migration' }, 'a choice is remembered by its label, with the question it was made against')
  ok(stillFor(made, ASK, pick), 'the same question: the draft stands')
  ok(stillFor(made, { ...ASK }, pick), 'read again and unchanged: it stands')
  /* RE-ASKED WITH THE OPTIONS REORDERED: option 1 now means something else */
  const reordered = { ...ASK, options: [ASK.options![1], ASK.options![0]] }
  ok(askSignature(reordered) !== askSignature(ASK), 'the order of the options is part of the question')
  ok(!stillFor(made, reordered, pick), 'the draft is not for the reordered question')
  /* CHANGED: its words, a label, a consequence, an option added or all removed, what is expected */
  for (const changed of [
    { ...ASK, question: 'Apply it tomorrow?' },
    { ...ASK, options: [ASK.options![0], { label: 'Hold', consequence: 'nothing changes' }] },
    { ...ASK, options: [{ label: 'Apply it', consequence: 'ALL links are stripped' }, ASK.options![1]] },
    { ...ASK, options: [...ASK.options!, { label: 'Cancel it' }] },
    { ...ASK, options: null },
    { ...ASK, expects: 'clarification' },
    { ...ASK, form: 'opr-other-form' },
  ] as AskLike[]) ok(!stillFor(made, changed, pick), `not for a changed question (${changed.question}, ${changed.options?.length}, ${changed.expects})`)
  /* own words and a withdrawal are for the question too */
  const own = madeAgainst(ASK, { kind: 'own' })
  eq(own.label, null, 'own words choose no option')
  ok(stillFor(own, ASK, { kind: 'own' }), 'own words stand for the same question')
  ok(!stillFor(own, { ...ASK, question: 'Something else?' }, { kind: 'own' }), 'and not for another')
  /* the label is checked even where the signature agrees */
  ok(!stillFor({ sig: askSignature(ASK), label: 'Apply it' }, ASK, pick), 'a choice whose place no longer has its label is not applied')
  ok(!stillFor({ sig: askSignature(ASK), label: 'Gone' }, ASK, { kind: 'option', option: 7 }), 'nor an option that is not there')
  ok(!stillFor(undefined, ASK, pick), 'nothing known of what it was made against: not applied')
}

/* -- a question no longer asked keeps no draft --------------------------------------- */
{
  /* a form of two questions and a decision on its own post, each with a draft a keeping host remembered */
  drafts.set('opr-form|picks', { 'opr-q1': { kind: 'option', option: 0 }, 'opr-q2': { kind: 'own' } })
  drafts.set('opr-form|texts', { 'opr-q2': 'my words' })
  drafts.set('opr-own|picks', { 'opr-own': { kind: 'own' } })
  drafts.set('opr-own|texts', { 'opr-own': 'answered elsewhere meanwhile' })
  for (const k of ['opr-form|opr-q1', 'opr-form|opr-q2', 'opr-own|opr-own']) madeFor.set(k, { sig: 'x', label: null })
  /* and one a host that keeps nothing holds (legacy Fluid): never touched */
  drafts.set('opr-fluid|picks', { 'opr-fluid': { kind: 'own' } })
  let told = 0
  const hear = () => { told++ }
  draftsTold.add(hear)
  dropNotAsked(['opr-q1', 'opr-q2', 'opr-own'])
  eq(told, 0, 'everything still asked: nothing is dropped')
  dropNotAsked(['opr-q1'])                        // q2 and the own-post decision were answered or withdrawn elsewhere
  eq(drafts.get('opr-form|picks'), { 'opr-q1': { kind: 'option', option: 0 } }, 'the question still asked keeps its draft')
  eq(drafts.has('opr-form|texts'), false, 'the closed question\'s words are gone')
  eq(drafts.has('opr-own|picks') || drafts.has('opr-own|texts'), false, 'and the closed decision\'s draft')
  eq([...madeFor.keys()], ['opr-form|opr-q1'], 'with what they were made against')
  eq(drafts.get('opr-fluid|picks'), { 'opr-fluid': { kind: 'own' } }, 'a draft no keeping host remembered is left exactly as it was')
  eq(told, 1, 'and every form drawn is told once')
  draftsTold.delete(hear); drafts.clear(); madeFor.clear()
}

/* -- an adoption decision's draft -------------------------------------------------- */
const REQ = { request: 'ent-req1', kind: 'lesson', wording: { proposed: 'Strip dangling links.', proposed_body: { text: 'Strip dangling links.' } } }
{
  const a = createAdoptionDrafts()
  const k = a.keyOf('ent-rule', REQ)
  eq(a.read(k), a.NONE, 'nothing written: empty')
  a.write(k, { because: 'It held twice.' })
  a.write(k, { editedText: 'Strip dangling links first.', editOpen: true })
  eq(a.read(a.keyOf('ent-rule', REQ)), { ...a.NONE, because: 'It held twice.', editedText: 'Strip dangling links first.', editOpen: true },
    'left and come back to: what was written for this request is there')
  eq(a.read(a.keyOf('ent-other', REQ)), a.NONE, 'another record has its own')
  /* THE SAME RECORD, ASKED ABOUT AGAIN: another request */
  const again = { ...REQ, request: 'ent-req2' }
  eq(a.read(a.keyOf('ent-rule', again)), a.NONE, 'a repeated request for the same record starts empty')
  eq(a.read(k), a.NONE, 'and the earlier request\'s draft is gone: it cannot come back')
}
{
  /* THE SAME REQUEST, PROPOSING OTHER WORDS */
  const a = createAdoptionDrafts()
  a.write(a.keyOf('ent-rule', REQ), { editedText: 'my edit of the first wording', because: 'x' })
  const reworded = { ...REQ, wording: { proposed: 'Never migrate with dangling links.', proposed_body: { text: 'Never migrate with dangling links.' } } }
  eq(a.read(a.keyOf('ent-rule', reworded)), a.NONE, 'an edit of other wording is not offered for this wording')
  a.write(a.keyOf('ent-rule', reworded), { because: 'for the new wording' })
  eq(a.read(a.keyOf('ent-rule', REQ)), a.NONE, 'nor the other way round')
  /* decided: nothing is left; deciding another does not forget this one */
  const b = createAdoptionDrafts()
  b.write(b.keyOf('ent-rule', REQ), { because: 'x' })
  b.forget(b.keyOf('ent-rule', { ...REQ, request: 'ent-req9' }))
  eq(b.read(b.keyOf('ent-rule', REQ)).because, 'x', 'forgetting another request\'s draft leaves this one')
  b.forget(b.keyOf('ent-rule', REQ))
  eq(b.read(b.keyOf('ent-rule', REQ)), b.NONE, 'a decision made keeps no draft')
  /* a new page (a reload) holds nothing: drafts are in memory only */
  eq(createAdoptionDrafts().read(a.keyOf('ent-rule', reworded)), a.NONE, 'a reload starts empty')
}

/* -- what a request is about: the opening's LATEST read, or nothing ---------------------- */
const ABOUT = (label: string, id = 'opr-ask'): About => ({ id, kind: 'adoption', form: null, says: label, asked_by_name: '@Coach', subject: [], evidence: [], context: [], referenced: [] })
const LIVE = { corpus_id: 'corpus-1', corpus_path: 'C:\\brains\\live' }
const COPY = { corpus_id: 'corpus-1', corpus_path: 'C:\\brains\\restored' }
{
  const s = createAboutStore()
  const g1 = s.begin(1)
  ok(s.reading(1), 'a read is on its way')
  ok(s.took(['opr-ask'], 1, g1, { about: [ABOUT('first')], brain: LIVE }), 'the latest read is taken')
  s.done(1, g1)
  ok(!s.reading(1), 'and is over')
  eq(s.of('opr-ask', 1)?.says, 'first', 'what this opening read')
  eq(s.of('opr-ask', 2), null, 'is not shown as current by a later opening, before that opening has read')
  /* OUT OF ORDER: a second read begins, and the FIRST one's answer arrives last */
  const old = s.begin(1), latest = s.begin(1)
  ok(s.reading(1), 'being read again: what is shown is not current')
  eq(s.of('opr-ask', 1)?.says, 'first', 'what was read stays drawn meanwhile, marked as being read again')
  ok(s.took(['opr-ask'], 1, latest, { about: [ABOUT('latest')], brain: LIVE }), 'the latest answer is taken')
  eq(s.took(['opr-ask'], 1, old, { about: [ABOUT('older, arriving last')], brain: LIVE }), false, 'the older answer arriving last is ignored')
  eq(s.of('opr-ask', 1)?.says, 'latest', 'and changes nothing shown')
  eq(s.took(['opr-ask'], 1, old, null, 'the older read failed late'), false, 'nor does an older failure')
  eq(s.errorOf('opr-ask', 1), null, 'no error is said for it')
  s.done(1, old)
  ok(s.reading(1), 'an older read ending does not end the latest')
  s.done(1, latest)
  ok(!s.reading(1), 'the latest ending does')
  /* a failed re-read: nothing older is shown, and it says so */
  const g3 = s.begin(1)
  s.took(['opr-ask'], 1, g3, null, 'HTTP 500')
  s.done(1, g3)
  eq(s.of('opr-ask', 1), null, 'a failed read shows no details')
  eq(s.errorOf('opr-ask', 1), 'HTTP 500', 'and says why')
  /* a later opening: the earlier opening's late answer is not its */
  const g4 = s.begin(2)
  eq(s.took(['opr-ask'], 1, g3, { about: [ABOUT('from the closed opening')], brain: LIVE }), false, 'an answer for an opening that is over is ignored')
  s.took(['opr-ask', 'opr-two'], 2, g4, { about: [ABOUT('fresh')], brain: LIVE })
  eq(s.of('opr-ask', 2)?.says, 'fresh', 'a good read is shown')
  eq(s.of('opr-two', 2), null, 'a request the server did not answer for shows nothing')
  ok(s.errorOf('opr-two', 2), 'and says so')
}
{
  /* the answer names another Brain than the opening's previous answer did */
  const s = createAboutStore()
  const g1 = s.begin(5)
  s.took(['opr-ask', 'opr-b'], 5, g1, { about: [ABOUT('live a'), ABOUT('live b', 'opr-b')], brain: LIVE })
  s.done(5, g1)
  const g2 = s.begin(5)
  s.took(['opr-ask'], 5, g2, { about: [ABOUT('the copy\'s a')], brain: COPY })
  eq(s.of('opr-ask', 5)?.says, 'the copy\'s a', 'the new answer is shown')
  eq(s.of('opr-b', 5), null, 'and what the earlier Brain said of another request is dropped')
}

/* -- an input's form: the exact post, part and name ------------------------------------- */
eq(blockOf('Turn ent-p1/@cutover:form'), { post: 'ent-p1', part: 0, name: 'cutover' }, 'a posted block, as Fluid keys it')
eq(blockOf('Turn ent-p1 part 2/@cutover:form'), { post: 'ent-p1', part: 2, name: 'cutover' }, 'and in a later part')
eq(blockOf('q2:ent-p1:0/@cutover:form'), { post: 'ent-p1', part: 0, name: 'cutover' }, 'and as Quiet Chat keys it')
eq(blockOf('Turn ent-p1/form#1'), null, 'an unnamed block names nothing')
eq(blockOf(null), null, 'nothing drawn: nothing found')
const TWO = ['q2:ent-p1:0/@rollback:form', 'q2:ent-p1:0/@cutover:form', 'q2:ent-p2:0/@cutover:form', 'q2:ent-p10:0/@cutover:form', 'q2:ent-p1:0/@cutover-old:form']
eq(pickBlock(TWO, 'ent-p1', 0, 'cutover'), 1, 'the named form of that post, not the other form on it')
eq(pickBlock(TWO, 'ent-p1', 0, 'rollback'), 0, 'and the other form by its own name')
eq(pickBlock(TWO, 'ent-p2', 0, 'cutover'), 2, 'the same name on another post is another form')
eq(pickBlock(TWO, 'ent-p1', 0, 'cut'), -1, 'a name that merely starts the same is not it')
eq(pickBlock(TWO, 'ent-p3', 0, 'cutover'), -1, 'a post that does not draw it: nothing')
const PARTS = ['Turn ent-p1/@cutover:form', 'Turn ent-p1 part 2/@cutover:form']
eq(pickBlock(PARTS, 'ent-p1', 2, 'cutover'), 1, 'the same name in two parts: the part its set names')
eq(pickBlock(PARTS, 'ent-p1', 0, 'cutover'), 0, 'the same name in two parts: the part its set names (2)')
eq(pickBlock(PARTS, 'ent-p1', 5, 'cutover'), -1, 'the same name in two parts and neither is the one named: nothing is marked')

console.log(`draft keep: ${checks} checks ok`)
