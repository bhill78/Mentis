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
import { createBoundStore, createPageBrain } from '../src/quiet2/needs/about'
import type { NeedsItem } from '../src/needsItems'
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

/* -- the list and what each item is about: ONE ANSWER OF ONE BRAIN ----------------------- */
const ABOUT = (label: string, id = 'opr-ask'): About => ({ id, kind: 'adoption', form: null, says: label, asked_by_name: '@Coach', subject: [], evidence: [], context: [], referenced: [] } as unknown as About)
const ITEM = (key: string, asks = [key]) => ({ key, kind: 'decision', asks } as unknown as NeedsItem)
const ANSWER = (label: string, brain: unknown, keys = ['opr-ask']) => ({
  items: keys.map((k) => ITEM(k)), words: `${keys.length} decision`, brain: brain as never,
  about: keys.map((k) => ABOUT(`${label} ${k}`, k)),
})
const LIVE = { corpus_id: 'corpus-1', corpus_path: 'C:\\brains\\live' }
const COPY = { corpus_id: 'corpus-1', corpus_path: 'C:\\brains\\restored' }
{
  const s = createBoundStore()
  eq(s.shown(1), null, 'nothing is shown before an answer')
  const g1 = s.begin(1)
  ok(s.reading(1), 'a read is on its way')
  ok(s.took(1, g1, ANSWER('first', LIVE)), 'the latest read is taken')
  ok(!s.reading(1), 'and is over')
  eq(s.shown(1)?.items.map((i) => i.key), ['opr-ask'], 'the list is the answer\'s list')
  eq(s.shown(1)?.about.get('opr-ask')?.says, 'first opr-ask', 'with that same answer\'s details')
  eq(s.shown(1)?.asks, ['opr-ask'], 'and its asks')
  eq(s.shown(2), null, 'a later opening shows nothing before it has read')
  /* OUT OF ORDER: the first of two reads answers last */
  const old = s.begin(1), latest = s.begin(1)
  ok(s.reading(1), 'being read again')
  eq(s.shown(1)?.about.get('opr-ask')?.says, 'first opr-ask', 'meanwhile the last answer stays, whole: one Brain\'s list with its details')
  ok(s.took(1, latest, ANSWER('latest', LIVE)), 'the latest answer is taken')
  eq(s.took(1, old, ANSWER('older, arriving last', LIVE)), false, 'the older answer arriving last is ignored')
  eq(s.took(1, old, null, 'the older read failed late'), false, 'and so is an older failure')
  eq(s.shown(1)?.about.get('opr-ask')?.says, 'latest opr-ask', 'only the latest answer is shown')
  /* a failed read: nothing it said is shown, and it says why */
  const g3 = s.begin(1)
  s.took(1, g3, null, 'HTTP 500')
  eq(s.shown(1), null, 'a failed read shows no answer: the page falls back to the plain list without details')
  eq(s.why(1), 'HTTP 500', 'and says why')
  /* an answer that is not one (no list, or no details) is a failure, never half shown */
  const g4 = s.begin(1)
  s.took(1, g4, { items: [ITEM('opr-ask')], brain: LIVE } as never)
  eq(s.shown(1), null, 'a list without details is not shown')
  /* a later opening: the earlier opening's late answer is not its */
  const g5 = s.begin(2)
  eq(s.took(1, g4, ANSWER('from the closed opening', LIVE)), false, 'an answer for an opening that is over is ignored')
  s.took(2, g5, ANSWER('fresh', LIVE, ['opr-ask', 'opr-two']))
  eq(s.shown(2)?.items.length, 2, 'a good read is shown')
  eq(s.shown(1), null, 'and the closed opening shows nothing')
}
{
  /* NEEDS YOU IS BOUND TO THE BRAIN OF THE PAGE'S FIRST ANSWER */
  const page = createPageBrain()
  ok(page.saw('corpus-1@C:\\brains\\live'), 'the first Brain named binds the page')
  ok(page.saw(null), 'an answer naming no Brain decides nothing')
  ok(!page.changed(), 'nothing has changed')
  ok(page.saw('corpus-1@C:\\brains\\live'), 'the same Brain again is fine')
  eq(page.saw('corpus-1@C:\\brains\\restored'), false, 'another Brain is not')
  ok(page.changed(), 'and the page knows the server now serves another Brain')
  eq(page.saw('corpus-1@C:\\brains\\live'), false, 'and stays knowing it: only a reload binds it again')
}
{
  /* the same opening, another Brain answering with the same ids: nothing is shown as current */
  const page = createPageBrain()
  const s = createBoundStore(page)
  const g1 = s.begin(5)
  s.took(5, g1, ANSWER('live', LIVE, ['opr-ask', 'opr-b']))
  eq(s.shown(5)?.about.get('opr-ask')?.says, 'live opr-ask', 'Brain A is shown')
  const g2 = s.begin(5)
  s.took(5, g2, ANSWER('the copy', COPY, ['opr-ask', 'opr-b']))
  eq(s.shown(5), null, "B's answer is not shown: neither its list nor its details")
  ok((s.why(5) ?? '').includes('reload'), 'it asks for a reload')
  ok(page.changed(), 'the page knows')
  const g3 = s.begin(5)
  s.took(5, g3, ANSWER('live again', LIVE))
  eq(s.shown(5), null, 'nothing is shown as current again until a reload, whatever answers next')
}
{
  /* the FIRST answer binds the page whole: its list and its details are one Brain's by construction */
  const page = createPageBrain()
  const s = createBoundStore(page)
  const g = s.begin(7)
  s.took(7, g, ANSWER('b', COPY))
  eq(s.shown(7)?.about.get('opr-ask')?.says, 'b opr-ask', 'a page first answered by B shows B\'s list with B\'s details')
  ok(!page.changed(), 'and is bound to B')
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
