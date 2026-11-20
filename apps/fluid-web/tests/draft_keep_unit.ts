/* WHAT IS KEPT ABOUT A DECISION IS KEPT FOR EXACTLY WHAT IT WAS MADE FOR
 * (independent review of "Needs You: inspect before deciding", 2026-11-20),
 * checked without a browser: two Brains behind one address sharing an id
 * never see each other's details or drafts; a question re-asked with its
 * options reordered or changed discards the draft; an ask answered elsewhere
 * drops its draft; a repeated adoption request does not resurrect the earlier
 * draft; a reload restores an adoption draft; a failed read is never shown as
 * current details; an input's form is found by its exact post, part and name. */
import assert from 'node:assert/strict'
import { askSignature, dropAnswer, keepAnswer, keptAnswer, keyOf, scopeOf, signature, sweep, type AskLike } from '../src/experimental/draftKeep'
import { createAdoptionDrafts } from '../src/quiet2/brain/adoptionDraft'
import { createAboutStore, OTHER_BRAIN } from '../src/quiet2/needs/about'
import type { About } from '../src/quiet2/needs/inspect'
import { blockOf, pickBlock } from '../src/quiet2/needs/land'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }

/** A tab's session storage: shared by every "page load" made over it. */
function storage() {
  const data = new Map<string, string>()
  return {
    data,
    getItem: (k: string) => (data.has(k) ? data.get(k)! : null),
    setItem: (k: string, v: string) => { data.set(k, String(v)) },
    removeItem: (k: string) => { data.delete(k) },
    get length() { return data.size },
    key: (i: number) => [...data.keys()][i] ?? null,
  }
}

/* -- which Brain ---------------------------------------------------------------- */
const LIVE = scopeOf({ corpus_id: 'corpus-1', corpus_path: 'C:\\brains\\live' })!
const COPY = scopeOf({ corpus_id: 'corpus-1', corpus_path: 'C:\\brains\\restored' })!
const OTHER = scopeOf({ corpus_id: 'corpus-2', corpus_path: 'C:\\brains\\live' })!
ok(LIVE && COPY && OTHER && new Set([LIVE, COPY, OTHER]).size === 3, 'a copy of a Brain somewhere else is another Brain, and so is another id in the same place')
eq(scopeOf({ corpus_id: '', corpus_path: 'x' }), null, 'no id: no Brain is known')
eq(scopeOf(null), null, 'nothing said: no Brain is known')
ok(signature(['a', 'b']) !== signature(['b', 'a']), 'order is part of what a draft was made against')
eq(signature({ a: 1 }), signature({ a: 1 }), 'and the same thing signs the same')

/* -- a question's draft ---------------------------------------------------------- */
const ASK: AskLike = { id: 'opr-ask', expects: 'decision', form: 'opr-form', question: 'Apply it tonight?',
  options: [{ label: 'Apply it', consequence: 'links are stripped' }, { label: 'Hold the migration', consequence: 'nothing changes' }] }
{
  const st = storage()
  ok(keepAnswer(LIVE, ASK, { kind: 'option', option: 1 }, 'after reading', st), 'really stored')
  eq(keptAnswer(LIVE, ASK, st), { pick: { kind: 'option', option: 1 }, text: 'after reading' }, 'and back, for the same question in the same Brain')
  /* TWO BRAINS, ONE ADDRESS, THE SAME ASK ID */
  eq(keptAnswer(COPY, ASK, st), null, 'the restored copy holding the same ask id gets nothing')
  eq(keptAnswer(OTHER, ASK, st), null, 'nor does another Brain')
  eq(keptAnswer(null, ASK, st), null, 'nor a page that does not know which Brain it is')
  ok(keptAnswer(LIVE, ASK, st), 'and asking from elsewhere removed nothing of this Brain\'s')
  keepAnswer(COPY, ASK, { kind: 'own' }, 'the copy\'s own words', st)
  eq(keptAnswer(LIVE, ASK, st)?.text, 'after reading', 'each Brain keeps its own')
  eq(keptAnswer(COPY, ASK, st)?.text, 'the copy\'s own words', 'each Brain keeps its own (2)')
}
{
  /* RE-ASKED WITH THE OPTIONS REORDERED: option 1 now means something else */
  const st = storage()
  keepAnswer(LIVE, ASK, { kind: 'option', option: 1 }, 'hold', st)
  const reordered = { ...ASK, options: [ASK.options![1], ASK.options![0]] }
  ok(askSignature(reordered) !== askSignature(ASK), 'the order of the options is part of the question')
  eq(keptAnswer(LIVE, reordered, st), null, 'the draft is not applied to the reordered question')
  eq(st.data.size, 0, 'and is discarded, not left to come back')
  eq(keptAnswer(LIVE, ASK, st), null, 'even for the question as it was')
}
{
  /* CHANGED: a label, a consequence, the question's words, an option added */
  for (const changed of [
    { ...ASK, question: 'Apply it tomorrow?' },
    { ...ASK, options: [{ label: 'Apply it', consequence: 'links are stripped' }, { label: 'Hold', consequence: 'nothing changes' }] },
    { ...ASK, options: [{ label: 'Apply it', consequence: 'ALL links are stripped' }, ASK.options![1]] },
    { ...ASK, options: [...ASK.options!, { label: 'Cancel it' }] },
    { ...ASK, options: null },
    { ...ASK, expects: 'clarification' },
  ] as AskLike[]) {
    const st = storage()
    keepAnswer(LIVE, ASK, { kind: 'option', option: 0 }, 'yes', st)
    eq(keptAnswer(LIVE, changed, st), null, `not applied to a changed question (${changed.question}, ${changed.options?.length})`)
    eq(st.data.size, 0, 'discarded')
  }
}
{
  /* a stored pick whose place no longer has its label is never applied, whatever the signature says */
  const st = storage()
  st.setItem(keyOf(LIVE, 'ask', ASK.id), JSON.stringify({ sig: askSignature(ASK), draft: { pick: { kind: 'option', option: 1 }, label: 'Apply it', text: 'x' } }))
  eq(keptAnswer(LIVE, ASK, st), null, 'the label it was chosen under is not at that place')
  st.setItem(keyOf(LIVE, 'ask', ASK.id), JSON.stringify({ sig: askSignature(ASK), draft: { pick: { kind: 'option', option: 7 }, label: 'Gone', text: 'x' } }))
  eq(keptAnswer(LIVE, ASK, st), null, 'nor an option that is not there')
  st.setItem(keyOf(LIVE, 'ask', ASK.id), '{not json')
  eq(keptAnswer(LIVE, ASK, st), null, 'rubbish is not believed')
}
{
  /* ANSWERED OR WITHDRAWN ELSEWHERE: what is no longer asked keeps no draft */
  const st = storage()
  const other: AskLike = { ...ASK, id: 'opr-other' }
  keepAnswer(LIVE, ASK, { kind: 'own' }, 'mine', st)
  keepAnswer(LIVE, other, { kind: 'own' }, 'still open', st)
  keepAnswer(COPY, ASK, { kind: 'own' }, 'the copy\'s', st)
  sweep(LIVE, 'ask', ['opr-other'], st)                        // the list now asks only the other
  eq(keptAnswer(LIVE, ASK, st), null, 'its draft is gone')
  eq(keptAnswer(LIVE, other, st)?.text, 'still open', 'the one still asked keeps its own')
  eq(keptAnswer(COPY, ASK, st)?.text, 'the copy\'s', 'another Brain\'s drafts are not this list\'s to remove')
  dropAnswer(LIVE, 'opr-other', st)
  eq(keptAnswer(LIVE, other, st), null, 'a closed question drops its draft')
  keepAnswer(LIVE, other, undefined, '', st)
  eq(st.data.size, 1, 'nothing chosen and nothing typed keeps nothing')
}
{
  /* storage that will not store: said, and nothing is claimed */
  const broken = { getItem: () => { throw new Error('denied') }, setItem: () => { throw new Error('quota') }, removeItem: () => { throw new Error('denied') } }
  eq(keepAnswer(LIVE, ASK, { kind: 'own' }, 'x', broken), false, 'not stored is said')
  eq(keptAnswer(LIVE, ASK, broken), null, 'and nothing comes back')
  eq(keepAnswer(null, ASK, { kind: 'own' }, 'x', storage()), false, 'no Brain known: nothing is stored')
}

/* -- an adoption decision's draft -------------------------------------------------- */
const REQ = { request: 'ent-req1', kind: 'lesson', wording: { proposed: 'Strip dangling links.', proposed_body: { text: 'Strip dangling links.' } } }
{
  const st = storage()
  const page1 = createAdoptionDrafts(st)
  const k = page1.keyOf(LIVE, 'ent-rule', REQ)
  eq(page1.read(k), page1.NONE, 'nothing kept: empty')
  page1.write(k, { because: 'It held twice.', editedText: 'Strip dangling links first.', editOpen: true })
  ok(page1.stored(k), 'really in the tab\'s storage')
  /* A RELOAD: a new page over the same tab storage */
  const page2 = createAdoptionDrafts(st)
  eq(page2.read(page2.keyOf(LIVE, 'ent-rule', REQ)).because, 'It held twice.', 'a reload restores the reason')
  eq(page2.read(page2.keyOf(LIVE, 'ent-rule', REQ)).editedText, 'Strip dangling links first.', 'and the edited wording')
  /* THE SAME RECORD, ASKED ABOUT AGAIN: another request */
  const again = { ...REQ, request: 'ent-req2' }
  const page3 = createAdoptionDrafts(st)
  eq(page3.read(page3.keyOf(LIVE, 'ent-rule', again)), page3.NONE, 'a repeated request for the same record starts empty')
  eq([...st.data.keys()].filter((x) => x.includes('ent-req1')).length, 0, 'and the earlier request\'s draft is removed')
  eq(createAdoptionDrafts(st).read(page1.keyOf(LIVE, 'ent-rule', REQ)), page1.NONE, 'so it cannot come back even for the old request')
}
{
  /* THE SAME REQUEST, PROPOSING OTHER WORDS */
  const st = storage()
  const a = createAdoptionDrafts(st)
  a.write(a.keyOf(LIVE, 'ent-rule', REQ), { editedText: 'my edit of the first wording', because: 'x' })
  const reworded = { ...REQ, wording: { proposed: 'Never migrate with dangling links.', proposed_body: { text: 'Never migrate with dangling links.' } } }
  const b = createAdoptionDrafts(st)
  eq(b.read(b.keyOf(LIVE, 'ent-rule', reworded)), b.NONE, 'an edit of other wording is not offered for this wording')
  eq(st.data.size, 0, 'and is discarded')
  /* in one page too: the key carries what it was written against */
  eq(a.read(a.keyOf(LIVE, 'ent-rule', reworded)), a.NONE, 'the same page, the new wording: empty')
}
{
  /* TWO BRAINS, the same record and request ids */
  const st = storage()
  const a = createAdoptionDrafts(st)
  a.write(a.keyOf(LIVE, 'ent-rule', REQ), { because: 'live reason' })
  eq(a.read(a.keyOf(COPY, 'ent-rule', REQ)), a.NONE, 'the copy sees nothing of it, in the same page')
  eq(createAdoptionDrafts(st).read(a.keyOf(COPY, 'ent-rule', REQ)), a.NONE, 'nor after a reload')
  eq(createAdoptionDrafts(st).read(a.keyOf(LIVE, 'ent-rule', REQ)).because, 'live reason', 'and reading as the copy removed nothing of the live Brain\'s')
  /* decided: nothing is left */
  a.forget(a.keyOf(LIVE, 'ent-rule', REQ))
  eq(st.data.size, 0, 'a decision made keeps no draft')
  /* not stored is said, so the page can ask before leaving */
  const none = createAdoptionDrafts(null)
  const k = none.keyOf(LIVE, 'ent-rule', REQ)
  none.write(k, { because: 'x' })
  eq(none.stored(k), false, 'no storage: said')
  const unknown = createAdoptionDrafts(st)
  unknown.write(unknown.keyOf(null, 'ent-rule', REQ), { because: 'x' })
  eq(unknown.stored(unknown.keyOf(null, 'ent-rule', REQ)), false, 'no Brain known: said')
  eq(st.data.size, 0, 'and nothing was stored')
}

/* -- what a request is about: this Brain's, this opening's, or nothing ------------------ */
const ABOUT = (label: string): About => ({ id: 'opr-ask', kind: 'adoption', form: null, says: label, asked_by_name: '@Coach', subject: [], evidence: [], context: [], referenced: [] })
const brainOf = (scope: string) => { const [id, path] = scope.split('@'); return { corpus_id: id, corpus_path: path } }
{
  const s = createAboutStore()
  s.took(['opr-ask'], LIVE, 1, { about: [ABOUT('the live record')], brain: brainOf(LIVE) })
  eq(s.of('opr-ask', LIVE, 1)?.says, 'the live record', 'what this opening read from this Brain')
  eq(s.of('opr-ask', COPY, 1), null, 'is not shown for the copy holding the same ask id')
  eq(s.of('opr-ask', LIVE, 2), null, 'nor as current by a later opening, before that opening has read')
  /* the later opening's read FAILS: nothing older is shown, and it says so */
  s.took(['opr-ask'], LIVE, 2, null, 'HTTP 500')
  eq(s.of('opr-ask', LIVE, 2), null, 'a failed read shows no details')
  eq(s.errorOf('opr-ask', LIVE, 2), 'HTTP 500', 'and says why')
  eq(s.of('opr-ask', LIVE, 1), null, 'what was held before is gone, not kept as if current')
  /* ANOTHER BRAIN ANSWERS at the same address */
  s.took(['opr-ask'], LIVE, 3, { about: [ABOUT('the copy\'s record')], brain: brainOf(COPY) })
  eq(s.of('opr-ask', LIVE, 3), null, 'an answer from a different Brain is never shown')
  eq(s.errorOf('opr-ask', LIVE, 3), OTHER_BRAIN, 'and is said to be another Brain\'s')
  /* a good read replaces the failure */
  s.took(['opr-ask'], LIVE, 4, { about: [ABOUT('fresh')], brain: brainOf(LIVE) })
  eq(s.of('opr-ask', LIVE, 4)?.says, 'fresh', 'a good read is shown')
  eq(s.errorOf('opr-ask', LIVE, 4), null, 'with no error')
  /* a request the server did not answer for is not left showing something */
  s.took(['opr-ask', 'opr-two'], LIVE, 4, { about: [ABOUT('fresh')], brain: brainOf(LIVE) })
  eq(s.of('opr-two', LIVE, 4), null, 'unanswered: nothing shown')
  ok(s.errorOf('opr-two', LIVE, 4), 'and said')
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
