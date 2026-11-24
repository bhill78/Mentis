import assert from 'node:assert/strict'
import { test } from 'node:test'
import { page } from '../src/brainBinding'
import { derivedPerspectiveName, PerspectiveStore } from '../src/quiet2/magnets/perspectives'
import { discussSelectedQuestion } from '../src/quiet2/magnets/InquiryPanel'
import { miniComposerDraft, saveMiniComposer } from '../src/quiet2/magnets/conversation'
import { emptyDraft } from '../src/composer/draft'
import type { MagnetResource } from '../src/quiet2/magnets/contract'

page.saw('fixture@instance')
const held = new Map<string, string>()
Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: { getItem: (k: string) => held.get(k) ?? null, setItem: (k: string, v: string) => held.set(k, v), removeItem: (k: string) => held.delete(k) } })
const A = 'ent-topicA11111', B = 'ent-topicB11111'
let id = 0
function resource(): MagnetResource {
  let state: any = { tab: 'Perspectives' }
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
  f.store.write = async (...args) => { sent.push(args); return { perspective: B } }
  const question = 'Does the calibration drift between the two retained batches, and by how much?'
  await f.store.lifecycle('create', { name: derivedPerspectiveName(question), question }, 'create-key')
  assert.equal(sent[0][0], '', 'creation uses the existing create route')
  assert.equal(sent[0][1].question, question)
  assert.equal(sent[0][1].name, 'Does the calibration drift between the two retain…')
  assert.ok(Array.from(sent[0][1].name).length <= 52, 'the derived name is within the approved bound')
  assert.equal(sent[1][0], '/selected', 'creation still selects the new Perspective durably')
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
