import assert from 'node:assert/strict'
import { test } from 'node:test'
import { page } from '../src/brainBinding'
import { answerHistory, derivedPerspectiveName, PerspectiveStore, STANDING_QUESTION, standingAnswerOp, standingOp } from '../src/quiet2/magnets/perspectives'
import { discussSelectedQuestion } from '../src/quiet2/magnets/InquiryPanel'
import { miniComposerDraft, removeContext, saveMiniComposer } from '../src/quiet2/magnets/conversation'
import { emptyDraft } from '../src/composer/draft'
import type { MagnetResource } from '../src/quiet2/magnets/contract'

page.saw('fixture@instance')
const held = new Map<string, string>()
Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: { getItem: (k: string) => held.get(k) ?? null, setItem: (k: string, v: string) => held.set(k, v), removeItem: (k: string) => held.delete(k) } })
const A = 'ent-topicA11111', B = 'ent-topicB11111'
let id = 0
function resource(): MagnetResource {
  let state: any = { tab: 'Perspectives', context: null, contextSuppressed: false }
  return { id: `fixture-${++id}`, brainKey: 'origin|fixture', saved: { id: `mag-unit${id}`, name: 'Inquiry', config: { sources: [] } }, snapshot: () => state, update: (v: any) => { state = { ...state, ...v } } } as unknown as MagnetResource
}
function detail(topic = A, text = 'Saved \u03b1\u{1f642}', revision = 'adm-revision111') {
  return { magnet: '', perspective: topic, selected: A, name: topic, retired: false, question: { ref: revision, digest: 'a'.repeat(64), size: 20, media_type: 'application/json' }, current_question: { text, revision }, events: 200 }
}
function fixture(r = resource()) {
  const store = new PerspectiveStore(r), calls: string[] = []
  let selected: string | null = A, words = 'Saved \u03b1\u{1f642}', revision = 'adm-current111'
  store.get = async (tail = '') => {
    calls.push(tail)
    if (tail.startsWith('?')) return { perspectives: [], selected, next: 'page2' }
    const topic = tail.split('/')[1]
    if (tail.includes('/history')) return { magnet: r.saved.id, perspective: topic, events: [], next: null }
    return { ...detail(topic, words, revision), magnet: r.saved.id, selected }
  }
  return { store, r, calls, selected: (v: string | null) => { selected = v }, edit: (v: string) => { words = v; revision += 'x' } }
}

test('ordinary context reads durable selection outside first page and current question, never history or evidence', async () => {
  const f = fixture()
  f.store.update({ selected: B, viewed: B, events: [{ data: { text: 'Old history' } } as any] })
  assert.deepEqual(await f.store.ordinaryContext(), { perspective: A, name: A, question: 'Saved \u03b1\u{1f642}', revision: 'adm-current111' })
  assert.ok(f.calls.every((p) => !/prepare|history|collection/.test(p)))
  f.edit('Edited elsewhere')
  assert.equal((await f.store.ordinaryContext())?.question, 'Edited elsewhere')
  f.selected(null)
  assert.equal(await f.store.ordinaryContext(), null)
})

test('list retains the selected Perspective even outside first page', async () => {
  const f = fixture(); await f.store.read()
  assert.equal(f.store.snapshot().rows[0].perspective, A)
  assert.equal(f.store.snapshot().selectedDetail?.current_question?.text, 'Saved \u03b1\u{1f642}')
})

test('ordinary context refuses late local or durable lens and revision changes', async () => {
  for (const change of ['local', 'durable', 'revision']) {
    const f = fixture(), get = f.store.get
    let calls = 0
    f.store.get = async (tail) => { const v = await get(tail); if (++calls === 2) { if (change === 'local') f.store.update({ selected: B }); if (change === 'durable') f.selected(B); if (change === 'revision') f.edit('New revision') }; return v }
    await assert.rejects(f.store.ordinaryContext(), /changed/)
  }
})

test('discussion uses selected saved wording rather than viewed history and keeps Composer choices', async () => {
  const f = fixture(); f.store.update({ selected: A, viewed: B })
  const draft = { ...emptyDraft(), action: 'ask-mentis' as const, coordinate: true }
  saveMiniComposer(f.r, draft)
  await discussSelectedQuestion(f.r, f.store)
  assert.equal(miniComposerDraft(f.r).text, 'Saved \u03b1\u{1f642}')
  assert.equal(miniComposerDraft(f.r).action, 'ask-mentis')
  assert.equal(f.r.snapshot().tab, 'Conversation')
  saveMiniComposer(f.r, { ...draft, text: 'Do not discard this draft' })
  await assert.rejects(discussSelectedQuestion(f.r, f.store), /different draft/)
  assert.equal(miniComposerDraft(f.r).text, 'Do not discard this draft')
})

test('uncertain edit survives remount and freezes original target, text and key after viewed lens changes', async () => {
  const f = fixture(); f.store.update({ selected: A, viewed: A })
  const sent: any[] = []
  f.store.write = async (...args) => { sent.push(args); throw new Error('response lost') }
  await assert.rejects(f.store.lifecycle('question', { text: 'Original text' }, 'original-key'), /lost/)
  f.store.update({ selected: B, viewed: B })
  await assert.rejects(f.store.lifecycle('question', { text: 'Changed' }, 'new-key'), /unknown outcome/)
  const reopened = fixture(f.r)
  reopened.store.update({ selected: B, viewed: B })
  reopened.store.write = async (...args) => { sent.push(args); return { perspective: A } }
  await reopened.store.retryPending()
  assert.deepEqual(sent, [[`/${A}/question`, { text: 'Original text' }, 'original-key'], [`/${A}/question`, { text: 'Original text' }, 'original-key']])
  assert.equal(reopened.store.snapshot().pending, undefined)
})

test('uncertain create retains original body and key, and acknowledged create only retries its frozen selection', async () => {
  const f = fixture(), sent: any[] = []
  f.store.write = async (...args) => { sent.push(args); throw new Error('create response lost') }
  await assert.rejects(f.store.lifecycle('create', { name: 'Original', question: 'Question' }, 'create-key'), /lost/)
  const second = fixture(f.r)
  second.store.write = async (...args) => { sent.push(args); if (args[0] === '/selected') throw new Error('selection response lost'); return { perspective: A } }
  await assert.rejects(second.store.retryPending(), /selection response lost/)
  const third = fixture(f.r)
  third.store.update({ viewed: B })
  third.store.write = async (...args) => { sent.push(args); return { selected: A } }
  await third.store.retryPending()
  assert.deepEqual(sent.map((x) => [x[0], x[2]]), [['', 'create-key'], ['', 'create-key'], ['/selected', 'create-key-select'], ['/selected', 'create-key-select']])
  assert.equal(sent[0][1].name, 'Original'); assert.deepEqual(sent[0], sent[1])
})

test('uncertain selection retries the original selection and key after remount', async () => {
  const f = fixture(), sent: any[] = []
  f.store.write = async (...args) => { sent.push(args); throw new Error('lost') }
  await assert.rejects(f.store.select(A, 'selection-key'))
  const second = fixture(f.r)
  second.store.update({ selected: B })
  second.store.write = async (...args) => { sent.push(args); return {} }
  await second.store.retryPending()
  assert.deepEqual(sent, [['/selected', { perspective: A }, 'selection-key'], ['/selected', { perspective: A }, 'selection-key']])
  // The chip the retry leaves says which saved question version it stands for,
  // taken from the durable read the card then shows (adm-394af815cdce §4).
  assert.deepEqual(f.r.snapshot().context, { ref: A, kind: 'perspective', label: A,
    version: 'adm-current111', digest: 'a'.repeat(64) })
  assert.equal(f.r.snapshot().contextSuppressed, false)
})

test('acknowledged save followed by failed refresh is saved, not an uncertain write', async () => {
  const f = fixture(); f.store.update({ viewed: A })
  f.store.write = async () => ({ perspective: A })
  f.store.get = async () => { throw new Error('read failed') }
  await f.store.lifecycle('question', { text: 'Saved' }, 'saved-key')
  assert.equal(f.store.snapshot().pending, undefined)
  assert.match(f.store.snapshot().error!, /saved. Refresh failed/)
})

test('late history response cannot replace another viewed lens or resurrect active qualification', async () => {
  const f = fixture(); let finish!: (v: any) => void
  f.store.update({ selected: A, viewed: A, active: {} as any, answer: {} })
  f.store.get = () => new Promise((resolve) => { finish = resolve })
  const pending = f.store.history()
  f.store.update({ selected: B, viewed: B })
  finish({ perspective: A, events: [{ post: 'old' }] }); await pending
  assert.deepEqual(f.store.snapshot().events, [])
  assert.equal(f.store.snapshot().active, undefined); assert.equal(f.store.snapshot().answer, undefined)
})

test('malformed detail identity or question revision refuses ordinary discussion', async () => {
  for (const change of [{ perspective: B }, { magnet: 'mag-other' }, { current_question: { text: 'Forged', revision: 'different' } }]) {
    const f = fixture(), get = f.store.get
    f.store.get = async (tail = '') => tail.startsWith('?') ? get(tail) : { ...await get(tail), ...change }
    await assert.rejects(f.store.ordinaryContext(), /did not match/)
  }
})

test('question-first creation sends the derived name with the question, and asks for no second field', async () => {
  const f = fixture(), sent: any[] = []
  f.store.write = async (...args) => { sent.push(args); if (args[0] === '/selected') f.selected(B); return { perspective: B } }
  const question = 'Does the calibration drift between the two retained batches, and by how much?'
  await f.store.lifecycle('create', { name: derivedPerspectiveName(question), question }, 'create-key')
  assert.equal(sent[0][0], '', 'creation uses the existing create route')
  assert.equal(sent[0][1].question, question)
  assert.equal(sent[0][1].name, 'Does the calibration drift between the two retain…')
  assert.ok(Array.from(sent[0][1].name).length <= 52, 'the derived name is within the approved bound')
  assert.equal(sent[1][0], '/selected', 'creation still selects the new Perspective durably')
  assert.equal(f.r.snapshot().context?.ref, B)
  assert.equal(f.r.snapshot().context?.kind, 'perspective')
  assert.equal(f.r.snapshot().contextSuppressed, false, 'explicit creation clears chip suppression')
  removeContext(f.r)
  assert.equal(f.r.snapshot().context, null, 'the composer chip can be removed')
  assert.equal(f.store.snapshot().selected, B, 'removing the chip does not change the active Perspective')
})

test('choosing ordinary Conversation removes a Perspective chip but preserves unrelated context', async () => {
  const f = fixture(), sent: any[] = []
  f.r.update({ context: { ref: A, kind: 'perspective', label: A }, contextSuppressed: true })
  f.store.write = async (...args) => { sent.push(args); f.selected(null); return { selected: null } }
  await f.store.select(null, 'ordinary-key')
  assert.equal(f.r.snapshot().context, null)
  assert.equal(f.r.snapshot().contextSuppressed, false)
  assert.deepEqual(sent[0], ['/selected', { perspective: null }, 'ordinary-key'])

  f.r.update({ context: { ref: 'adm-file111111', kind: 'file', label: 'Evidence' } })
  await f.store.select(null, 'ordinary-again')
  assert.equal(f.r.snapshot().context?.ref, 'adm-file111111', 'ordinary selection removes only a Perspective chip')
})

test('the durable rename uses H6 verb and changes the display name only', async () => {
  const f = fixture(), sent: any[] = []
  f.store.update({ selected: A, viewed: A })
  f.store.write = async (...args) => { sent.push(args); return { perspective: A, event: { event: 'rename' } } }
  await f.store.lifecycle('rename', { name: 'Calibration drift' }, 'rename-key')
  assert.deepEqual(sent[0], [`/${A}/rename`, { name: 'Calibration drift' }, 'rename-key'])
  assert.equal(sent.length, 1, 'a rename is one write: it never re-selects or re-questions')
  assert.equal(f.store.snapshot().selected, A, 'the durable selection is untouched')
  assert.equal(f.store.snapshot().viewedDetail?.current_question?.text, 'Saved α\u{1f642}', 'the saved question is untouched')
})

test('an uncertain rename keeps its original name, target and key for the unchanged retry', async () => {
  const f = fixture(), sent: any[] = []
  f.store.update({ selected: A, viewed: A })
  f.store.write = async (...args) => { sent.push(args); throw new Error('rename response lost') }
  await assert.rejects(f.store.lifecycle('rename', { name: 'Original name' }, 'rename-key'), /lost/)
  assert.equal(f.store.snapshot().pending?.kind, 'rename')
  const reopened = fixture(f.r)
  reopened.store.update({ selected: B, viewed: B })
  reopened.store.write = async (...args) => { sent.push(args); return { perspective: A } }
  await reopened.store.retryPending()
  assert.deepEqual(sent, [[`/${A}/rename`, { name: 'Original name' }, 'rename-key'], [`/${A}/rename`, { name: 'Original name' }, 'rename-key']])
  assert.equal(reopened.store.snapshot().pending, undefined)
})

/** A kept question's recorded answers, oldest first, as a history page returns them. */
const answered = (...texts: string[]) => texts.map((text, i) => ({
  seq: i + 1, post: `ent-answer${i}`, event: 'answer', perspective: A,
  snapshot: { ref: `adm-answer${i}`, digest: 'b'.repeat(64), size: 10, media_type: 'application/json' },
  data: { text, answer: { ref: `adm-recorded${i}` } },
}))

test('a kept question keeps every earlier answer and names only the newest as standing now', () => {
  assert.deepEqual(answerHistory([]), { current: null, superseded: [] })
  const events = [...answered('First understanding', 'Second understanding', 'Third understanding'),
    { seq: 9, post: 'ent-challenge1', event: 'challenge', perspective: A, snapshot: { ref: 'adm-c' }, data: { text: 'Doubt' } } as any]
  const h = answerHistory(events)
  assert.equal(h.current?.data.text, 'Third understanding')
  // Earlier answers are kept, newest first, and none of them is discarded.
  assert.deepEqual(h.superseded.map((e) => e.data.text), ['Second understanding', 'First understanding'])
  // A challenge is not an answer and never stands as one.
  assert.ok(![h.current, ...h.superseded].some((e) => e?.event === 'challenge'))
})

test('reading a kept question again reports a newer answer, reports no change, and refuses over an unknown write', async () => {
  const f = fixture()
  let events = answered('First understanding')
  const base = f.store.get
  f.store.get = async (tail = '') => tail.includes('/history')
    ? { magnet: f.r.saved.id, perspective: tail.split('/')[1], events, next: null } : base(tail)
  f.store.update({ selected: A, viewed: A })
  await f.store.view(A)
  assert.equal(answerHistory(f.store.snapshot().events).current?.data.text, 'First understanding')
  // Nothing new recorded: the read says so rather than claiming a change.
  assert.equal(await f.store.recheck(), 'unchanged')
  // A newer answer recorded since: the read finds it and the earlier one stays.
  events = answered('First understanding', 'Second understanding')
  assert.equal(await f.store.recheck(), 'changed')
  const after = answerHistory(f.store.snapshot().events)
  assert.equal(after.current?.data.text, 'Second understanding')
  assert.deepEqual(after.superseded.map((e) => e.data.text), ['First understanding'])
  // Reading again records nothing and starts nothing: every call was a read.
  assert.ok(f.calls.every((p) => !/prepare|reconcile|bind/.test(p)))
  // With no question in hand there is nothing to read again.
  f.store.update({ selected: null, viewed: null })
  assert.equal(await f.store.recheck(), 'none')
  // An action whose outcome is unknown is resolved before anything is re-read.
  f.store.update({ viewed: A, pending: { kind: 'question' } as any })
  await assert.rejects(f.store.recheck(), /unchanged question action/)
})

/* --- PART F: a question gets a real persisted answer ------------------------
   What these prove at the store level, against the plan's Part F done-when:
   asking writes one keyed, retryable answer; asking again SUPERSEDES rather
   than overwrites; the standing Perspective is created exactly once with a
   key derived from the Magnet; and one collection produces at most one
   evolving summary, keyed by its own batch. */

test('asking a question of the collection is one keyed write, and asking again supersedes', async () => {
  const f = fixture(), sent: any[] = []
  f.store.update({ selected: A, viewed: A })
  f.store.write = async (...args) => { sent.push(args); return { perspective: A, text: 'An answer' } }
  await f.store.ask('What do the records say about drift?', 'ask-key')
  assert.deepEqual(sent[0], [`/${A}/answer`, { text: 'What do the records say about drift?' }, 'ask-key'])
  assert.equal(sent.length, 1, 'asking is one write: it never selects or re-questions')
  // Asking the saved question again omits the text: the server re-answers the
  // question already saved, and appends rather than replacing.
  await f.store.ask(undefined, 'again-key')
  assert.deepEqual(sent[1], [`/${A}/answer`, {}, 'again-key'])
  await f.store.ask('   ', 'blank-key')
  assert.deepEqual(sent[2][1], {}, 'blank words are not a new question')
  // With no question open there is nothing to ask of the collection.
  f.store.update({ selected: null, viewed: null })
  await assert.rejects(f.store.ask('Anything'), /Open a question/)
})

test('an uncertain ask keeps its original words and key for the unchanged retry', async () => {
  const f = fixture(), sent: any[] = []
  f.store.update({ selected: A, viewed: A })
  f.store.write = async (...args) => { sent.push(args); throw new Error('answer response lost') }
  await assert.rejects(f.store.ask('Original question', 'ask-key'), /lost/)
  assert.equal(f.store.snapshot().pending?.kind, 'answer')
  const reopened = fixture(f.r)
  reopened.store.update({ selected: B, viewed: B })
  reopened.store.write = async (...args) => { sent.push(args); return { perspective: A } }
  await reopened.store.retryPending()
  assert.deepEqual(sent, [[`/${A}/answer`, { text: 'Original question' }, 'ask-key'],
                          [`/${A}/answer`, { text: 'Original question' }, 'ask-key']])
  assert.equal(reopened.store.snapshot().pending, undefined)
})

test('the standing Perspective is created once, with a key derived from the Magnet', async () => {
  const f = fixture(), sent: any[] = []
  f.store.write = async (...args) => { sent.push(args); return { perspective: 'ent-standing1111' } }
  const topic = await f.store.ensureStanding()
  assert.equal(topic, 'ent-standing1111')
  assert.equal(sent[0][0], '', 'it is the ordinary create route')
  assert.equal(sent[0][1].standing, true, 'marked as the standing one')
  assert.equal(sent[0][1].question, STANDING_QUESTION)
  assert.equal(sent[0][2], standingOp(f.r.saved.id), 'with the key derived from the Magnet')
  assert.equal(sent.length, 1, 'creation never selects it: the active question is the owner’s')
  // Known already: no second write, however often it is asked for.
  assert.equal(await f.store.ensureStanding(), 'ent-standing1111')
  assert.equal(sent.length, 1)
})

test('one collection produces at most one evolving summary, keyed by that collection', async () => {
  const f = fixture(), sent: any[] = []
  const answers: any[] = []
  f.store.update({ standing: 'ent-standing1111' })
  f.store.write = async (...args) => { sent.push(args); return { perspective: 'ent-standing1111' } }
  const base = f.store.get
  f.store.get = async (tail = '') => tail.includes('/history')
    ? { magnet: f.r.saved.id, perspective: tail.split('/')[1], events: answers, next: null } : base(tail)
  answers.push({ seq: 1, post: 'ent-a1', event: 'answered', perspective: 'ent-standing1111',
    snapshot: { ref: 'adm-s1' }, data: { text: 'First state', basis: { batch: 'adm-batch111111' } } })
  const got = await f.store.summarise('adm-batch111111')
  assert.equal(sent[0][0], '/ent-standing1111/answer')
  assert.deepEqual(sent[0][1], {}, 'the standing question is re-answered, never revised')
  assert.equal(sent[0][2], standingAnswerOp(f.r.saved.id, 'adm-batch111111'),
    'keyed by the collection, so a replay records nothing further')
  assert.equal(got?.current?.data.text, 'First state')
  assert.equal(got?.batch, 'adm-batch111111')
  assert.deepEqual(got?.superseded, [])
  // A second collection: a new current answer, with the previous one kept.
  answers.push({ seq: 2, post: 'ent-a2', event: 'answered', perspective: 'ent-standing1111',
    snapshot: { ref: 'adm-s2' }, data: { text: 'Second state', basis: { batch: 'adm-batch222222' } } })
  const after = await f.store.summarise('adm-batch222222')
  assert.equal(sent[1][2], standingAnswerOp(f.r.saved.id, 'adm-batch222222'), 'a different collection, a different key')
  assert.equal(after?.current?.data.text, 'Second state')
  assert.deepEqual(after?.superseded.map((e) => e.data.text), ['First state'], 'the earlier answer is kept')
  // Reading the summary writes nothing at all.
  const before = sent.length
  await f.store.readSummary()
  assert.equal(sent.length, before, 'reading the evolving summary is a read')
})

test('wrong or missing Brain response is refused; pending action never migrates to a replacement Brain', async () => {
  const f = fixture(); f.store.update({ viewed: A }); f.store.write = async () => { throw new Error('lost') }
  await assert.rejects(f.store.lifecycle('question', { text: 'Original' }, 'brain-key'))
  const store = new PerspectiveStore(f.r), fetchBefore = globalThis.fetch
  try {
    globalThis.fetch = async () => new Response(JSON.stringify({ brain: 'other@instance' }))
    await assert.rejects(store.get(), /late Perspective/)
    globalThis.fetch = async () => new Response(JSON.stringify({ perspectives: [] }))
    await assert.rejects(store.get(), /late Perspective/)
    page.move()
    await assert.rejects(f.store.retryPending(), /another Brain/)
  } finally { globalThis.fetch = fetchBefore }
})
