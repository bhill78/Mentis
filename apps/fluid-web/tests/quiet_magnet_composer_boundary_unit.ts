/* THE COMPOSER'S HALF OF THE MESSAGE BOUNDARY.
 *
 * Revised contract adm-c5c73679ac1e §§2-6, owner request ent-3191baeb33d2 §§5-6.
 * What is checked here is exactly what this part owns: the words that reach the
 * record are the words that were typed, nothing generated is written as if the
 * author had typed it, and what a message is ABOUT travels as the published
 * selector -- only ever what was actually selected.
 *
 * Nothing here opens a Brain, starts a server or reaches the network. The
 * canonical digests are the published implementation's (`magnets/contract.ts`,
 * which the golden vectors pin against Python), never a second reading of the
 * rules written out here.
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFileSync } from 'node:fs'
import {
  CONTEXT_WORDS, DROPPED_REF_NOT_SENDABLE, FILE_NOT_SENDABLE, MANAGED_REFUSAL_WORDS,
  POST_NOT_SENDABLE, QUESTION_CHANGED, RETAINED_NOT_SENDABLE,
  configurationDigest, contextCandidate, definitionBody, managedSelector, refusalWords,
  selectedQuestion, selectedReference, type SelectionSeam,
} from '../src/quiet2/magnets/ComposerBar'
import {
  MANAGED_REFUSAL, SELECTOR_FIELD, authoredTextAgrees, canonicalJson, digestOf, flowText,
  validateExplicitSelector, type MagnetContext, type MagnetResource, type MagnetSnapshot,
} from '../src/quiet2/magnets/contract'
import { bodyOf, emptyDraft, refIdentities, type Draft } from '../src/composer/draft'
import { emptyPlaces } from '../src/quiet2/magnets/places'

/* -- fixtures -------------------------------------------------------------- */

const ME = 'ent-ownerme11111'
const OWN = 'ent-ownconv11111'
const DIGEST = 'a'.repeat(64)
const QUESTION_DIGEST = 'b'.repeat(64)
const LENS = 'ent-lens11111111'
const QUESTION = 'adm-question1111'

const config = (over: Record<string, unknown> = {}) => ({
  id: 'mag-fixtureA',
  sources: [{ kind: 'conversation', conversation: 'ent-source111111' }],
  collection: { mode: 'one-time' },
  conversation: OWN,
  ...over,
})

const snapshotFor = (over: Partial<MagnetSnapshot> = {}): MagnetSnapshot => ({
  title: 'Fixture', loading: false, results: [],
  x: 0, y: 0, open: true, wide: false, tab: 'Conversation', overlay: null,
  places: emptyPlaces(), query: '', searchType: 'All', searchTarget: null, searchListScroll: 0,
  lens: null, returnRoute: null, settingsReturn: null,
  context: null, contextSuppressed: false, carried: null,
  ...over,
} as MagnetSnapshot)

function resourceFor(over: Partial<MagnetSnapshot> = {}, definition = config()): MagnetResource {
  let state = snapshotFor(over)
  return {
    id: 'mag-fixtureA', brainKey: 'https://fixture.invalid|dev|corpus-a',
    saved: { id: 'mag-fixtureA', name: 'Fixture', config: definition as never },
    snapshot: () => state,
    subscribe: () => () => {},
    update: (change: Partial<MagnetSnapshot>) => { state = { ...state, ...change } },
    read: async () => {}, cancel: () => {}, dispose: () => {},
  } as unknown as MagnetResource
}

const seamFor = (resource: MagnetResource, over: {
  ordinary?: { perspective: string; revision: string } | null
  rows?: { perspective: string; question: { ref: string; digest: string } | null }[]
} = {}): SelectionSeam => ({
  resource,
  inquiries: {
    ordinaryContext: async () => over.ordinary ?? null,
    snapshot: () => ({ rows: over.rows ?? [] }),
  },
})

const draftWith = (over: Partial<Draft> = {}): Draft => ({ ...emptyDraft(), ...over })

/* -- the words are the words that were typed ------------------------------- */

test('authored text reaches the body exactly: whitespace, line endings and combining characters', () => {
  for (const text of [
    '  how do I configure a magnet?  ',
    'first\r\nsecond\n',
    '\n',
    'café \u{1f9f2}‍✨ ',
    '   ',
  ]) {
    const body = bodyOf(draftWith({ text }), ME, [])
    assert.equal(body.text, text, 'the stored words are the typed words, untrimmed')
    assert.ok(authoredTextAgrees(body.text, body.parts as never),
      'text is the exact projection of the parts the door validates against')
  }
})

test('a typed inline reference stays authored, and its characters stay in the words', () => {
  const text = ' ask #collection about this '
  const body = bodyOf(draftWith({
    text, marks: [{ kind: 'topic', topic: 'ent-topic111111', text: '#collection', start: 5 }],
  }), ME, [])
  const parts = body.parts as { type: string; text?: string; ref?: string }[]
  assert.deepEqual(parts.map((p) => p.type), ['text', 'topic', 'text'])
  assert.equal(parts[1].ref, 'ent-topic111111')
  assert.equal(parts[1].text, '#collection', 'the author typed these characters; they remain hers')
  assert.equal(body.text, text)
  assert.ok(authoredTextAgrees(body.text, body.parts as never))
})

test('an audited send writes no chip label and no separator; the identity goes beside the words', () => {
  const refs = [{ part: { type: 'turn' as const, ref: 'ent-apost111111', text: '#4' } }]
  const audited = bodyOf(draftWith({ text: 'look at this', refs }), ME, [], 'ask-mentis', { references: 'audited' })
  assert.deepEqual(audited.parts, [{ type: 'text', text: 'look at this' }])
  assert.equal(audited.text, 'look at this')
  assert.ok(authoredTextAgrees(audited.text, audited.parts as never))
  assert.deepEqual((audited as { references?: unknown[] }).references, [{ type: 'turn', ref: 'ent-apost111111' }],
    'what the reference NAMES is carried; the characters it was drawn with are not')
  assert.equal(flowText(audited.parts as never), 'look at this', 'nothing generated entered the projection')

  /* A chip alone: no parts at all, and empty words that still agree -- the
     published vector's `chip-only-has-no-authored-text`. */
  const alone = bodyOf(draftWith({ text: '', refs }), ME, [], 'ask-mentis', { references: 'audited' })
  assert.deepEqual(alone.parts, [])
  assert.equal(alone.text, '')
  assert.ok(authoredTextAgrees(alone.text, alone.parts as never))

  /* And generic posting is untouched: there the reference IS a content part. */
  const generic = bodyOf(draftWith({ text: 'look at this', refs }), ME, [])
  const genericParts = generic.parts as { type: string; text?: string }[]
  assert.deepEqual(genericParts.map((p) => p.type), ['text', 'text', 'turn'])
  assert.equal(genericParts[2].text, '#4')
})

test('attachments survive both seams, and a file-only message has no words to disagree with', () => {
  const attached = [{ id: 'f1', name: 'notes.txt', mime: 'text/plain', size: 3, ref: 'sha256:abc', state: 'held' as const }]
  for (const seam of [{}, { references: 'audited' as const }]) {
    const body = bodyOf(draftWith({ text: '', attached }), ME, [], 'ask-mentis', seam)
    const parts = body.parts as { type: string; ref?: string; alt?: string }[]
    assert.deepEqual(parts.map((p) => p.type), ['file'])
    assert.equal(parts[0].ref, 'sha256:abc')
    assert.equal(parts[0].alt, 'notes.txt')
    assert.equal(body.text, '')
    assert.ok(authoredTextAgrees(body.text, body.parts as never))
  }
})

test('refIdentities keeps every field of the part except the characters it was drawn with', () => {
  assert.deepEqual(refIdentities([{ part: { type: 'object', ref: 'ent-post111111', key: 'k1', version: 'ent-v1', text: 'the table' } }]),
    [{ type: 'object', ref: 'ent-post111111', key: 'k1', version: 'ent-v1' }])
  assert.deepEqual(refIdentities(), [])
})

/* -- what the message is about -------------------------------------------- */

test('the configuration digest covers the definition without its own-Conversation mirror', async () => {
  const definition = config()
  assert.equal('conversation' in (definitionBody(definition) as Record<string, unknown>), false)
  assert.equal(await configurationDigest(definition), await configurationDigest(config({ conversation: 'ent-elsewhere111' })),
    'the nonauthoritative mirror does not change the digest')
  assert.notEqual(await configurationDigest(definition), await configurationDigest(config({ collection: { mode: 'continuous' } })),
    'collection behaviour does')
  assert.notEqual(await configurationDigest(definition), await configurationDigest(config({ extras: { filter: 'x' } })),
    'and so does an extension field')
  /* The bytes are the published canonicalisation's, not a second rendering. */
  assert.equal(await configurationDigest(definition), await digestOf(JSON.parse(canonicalJson(definitionBody(definition)))))
})

test('the saved question is selected by its own version, and a changed one refuses', () => {
  const rows = [{ perspective: LENS, question: { ref: QUESTION, digest: QUESTION_DIGEST } }]
  const got = selectedQuestion({ perspective: LENS, revision: QUESTION }, rows, LENS)
  assert.deepEqual(got, { ok: true, value: { id: LENS, question_ref: QUESTION, question_digest: QUESTION_DIGEST } })

  for (const [why, call] of [
    ['no durable question at all', () => selectedQuestion(null, rows, LENS)],
    ['another Perspective is selected now', () => selectedQuestion({ perspective: 'ent-other1111111', revision: QUESTION }, rows, LENS)],
    ['the question was revised since', () => selectedQuestion({ perspective: LENS, revision: 'adm-question2222' }, rows, LENS)],
    ['its digest is not a digest', () => selectedQuestion({ perspective: LENS, revision: QUESTION },
      [{ perspective: LENS, question: { ref: QUESTION, digest: 'not-a-digest' } }], LENS)],
  ] as [string, () => ReturnType<typeof selectedQuestion>][]) {
    const refused = call()
    assert.equal(refused.ok, false, why)
    assert.equal(refused.ok === false && refused.why, QUESTION_CHANGED)
  }
})

test('an attached object is selected by exact identity, and what cannot be stated exactly refuses', () => {
  const rows = [
    { kind: 'file', id: 'adm-held1111111', version: 'adm-held1111111', value: { digest: DIGEST, path: 'notes.txt' } },
    { kind: 'file', id: 'adm-nodigest111', version: 'adm-nodigest111', value: { path: 'other.txt' } },
    { kind: 'post', id: 'ent-collected111', version: 'ent-version11111', value: { title: 'A post' } },
  ]
  assert.deepEqual(selectedReference(rows, { ref: 'adm-held1111111', kind: 'file', label: 'notes.txt' }),
    { ok: true, value: { kind: 'artifact', ref: 'adm-held1111111', version: null, digest: DIGEST } })

  const noDigest = selectedReference(rows, { ref: 'adm-nodigest111', kind: 'file', label: 'other.txt' })
  assert.equal(noDigest.ok === false && noDigest.why, FILE_NOT_SENDABLE,
    'no recorded digest means no selection: nothing is computed from captured text')
  const post = selectedReference(rows, { ref: 'ent-collected111', kind: 'post', label: 'A post' })
  assert.equal(post.ok === false && post.why, POST_NOT_SENDABLE)
  const batch = selectedReference(rows, { ref: 'adm-batch1111111', kind: 'batch', label: 'Collected information' })
  assert.equal(batch.ok === false && batch.why, RETAINED_NOT_SENDABLE,
    'the retained collection is not answer context while configured-source access is unenforced')
})

/* -- the selector every action carries ------------------------------------- */

const SENDS: [string, Record<string, unknown>][] = [
  ['a recorded note', { action: 'record-only', text: 'a note', parts: [{ type: 'text', text: 'a note' }] }],
  ['an Ask Mentis question', { action: 'ask-mentis', text: 'how do I configure a magnet?', parts: [{ type: 'text', text: 'how do I configure a magnet?' }] }],
  ['an addressed request', { action: 'ask-participant', text: 'please look', parts: [{ type: 'text', text: 'please look' }], dispatch: [{ participant: 'ent-agent111111' }] }],
]

test('every action carries a valid explicit selector, and with nothing attached it says so explicitly', async () => {
  for (const [what, post] of SENDS) {
    const selector = await managedSelector(seamFor(resourceFor()), post)
    assert.deepEqual(Object.keys(selector).sort(), ['configuration_digest', 'mode', 'perspective', 'references', 'version'], what)
    assert.equal(selector.version, 1)
    assert.equal(selector.mode, 'ordinary')
    assert.equal(selector.perspective, null, 'nothing is inferred on send')
    assert.deepEqual(selector.references, [])
    assert.equal(validateExplicitSelector(selector).ok, true, what)
    assert.equal(selector.configuration_digest, await configurationDigest(config()))
  }
})

test('a removed Perspective reaches nothing, however it was removed', async () => {
  const rows = [{ perspective: LENS, question: { ref: QUESTION, digest: QUESTION_DIGEST } }]
  const ordinary = { perspective: LENS, revision: QUESTION }

  /* Attached: the exact saved question travels, for every action. */
  for (const [, post] of SENDS) {
    const attached = resourceFor({ lens: LENS, context: { ref: LENS, kind: 'perspective', label: 'A question' } })
    const selector = await managedSelector(seamFor(attached, { ordinary, rows }), post)
    assert.deepEqual(selector.perspective, { id: LENS, question_ref: QUESTION, question_digest: QUESTION_DIGEST })
  }

  /* Taken off: the Perspective is still SELECTED in the card -- the owner only
     removed it from this message -- and the selector carries nothing. */
  const removed = resourceFor({ lens: LENS, context: null, contextSuppressed: true })
  const after = await managedSelector(seamFor(removed, { ordinary, rows }), SENDS[1][1])
  assert.equal(after.perspective, null, 'an intentional removal is respected, not overridden by the active lens')
  assert.deepEqual(after.references, [])

  /* And never attached at all, with a lens selected, is the same. */
  const never = resourceFor({ lens: LENS, context: null, contextSuppressed: false })
  assert.equal((await managedSelector(seamFor(never, { ordinary, rows }), SENDS[0][1])).perspective, null)
})

test('an attached file travels as one exact reference; a selection that cannot be stated stops the send', async () => {
  const rows = [{ kind: 'file', id: 'adm-held1111111', version: 'adm-held1111111', value: { digest: DIGEST } }]
  const withFile = resourceFor({ results: rows as never, context: { ref: 'adm-held1111111', kind: 'file', label: 'notes.txt' } })
  const selector = await managedSelector(seamFor(withFile), SENDS[0][1])
  assert.deepEqual(selector.references, [{ kind: 'artifact', ref: 'adm-held1111111', version: null, digest: DIGEST }])
  assert.equal(validateExplicitSelector(selector).ok, true)

  const withBatch = resourceFor({ results: rows as never, context: { ref: 'adm-batch1111111', kind: 'batch', label: 'Collected information' } })
  await assert.rejects(() => managedSelector(seamFor(withBatch), SENDS[1][1]), new RegExp(RETAINED_NOT_SENDABLE.slice(0, 40)))

  const dropped = { ...SENDS[0][1], references: [{ type: 'object', ref: 'ent-post111111', key: 'k' }] }
  await assert.rejects(() => managedSelector(seamFor(resourceFor()), dropped), new RegExp(DROPPED_REF_NOT_SENDABLE.slice(0, 40)))
})

test('a question the record no longer holds stops the send, and nothing else is substituted', async () => {
  const attached = resourceFor({ lens: LENS, context: { ref: LENS, kind: 'perspective', label: 'A question' } })
  await assert.rejects(() => managedSelector(seamFor(attached, { ordinary: null, rows: [] }), SENDS[1][1]),
    new RegExp(QUESTION_CHANGED.slice(0, 40)))
})

/* -- what the owner is told, and what the composer offers ------------------ */

test('every refusal the door can answer with has words that say what to do', () => {
  for (const reason of Object.keys(MANAGED_REFUSAL)) {
    const words = refusalWords(reason)
    assert.ok(words && words.length > 20, `${reason} has owner-facing words`)
    assert.doesNotMatch(words!, /selector|digest|422|409|schema|envelope/i, `${reason} says it without implementation vocabulary`)
  }
  assert.equal(Object.keys(MANAGED_REFUSAL_WORDS).length, Object.keys(MANAGED_REFUSAL).length)
  assert.equal(refusalWords('something-else'), null)
  assert.equal(refusalWords(undefined), null)
})

test('automatic attachment offers only what a message can actually carry', () => {
  const carriable = [{ kind: 'file', id: 'adm-held1111111', version: 'adm-held1111111', value: { digest: DIGEST, title: 'notes.txt' } }]
  const places = emptyPlaces()
  const inspecting = (results: unknown[], inspected: string) => resourceFor({
    results: results as never,
    places: { ...places, Conversation: { ...places.Conversation, inspected } },
  })
  const got = contextCandidate(inspecting(carriable, 'adm-held1111111'))
  assert.deepEqual(got, { ref: 'adm-held1111111', kind: 'file', label: 'notes.txt' })

  /* A collected record the card cannot state exactly is NOT attached by the
     act of typing: that would leave Send with nothing it could do. The owner
     may still attach it deliberately, and is then told why it cannot go. */
  const collected = [{ kind: 'post', id: 'ent-collected111', version: 'ent-version11111', value: { title: 'A post' } }]
  assert.equal(contextCandidate(inspecting(collected, 'ent-collected111')), null)
  const noDigest = [{ kind: 'file', id: 'adm-nodigest111', version: 'adm-nodigest111', value: {} }]
  assert.equal(contextCandidate(inspecting(noDigest, 'adm-nodigest111')), null)
})

test('the chip says what it is in ordinary words, and the identifier is not in the sentence', () => {
  assert.deepEqual(Object.keys(CONTEXT_WORDS).sort(), ['attachment', 'batch', 'file', 'image', 'perspective', 'post'])
  assert.equal(CONTEXT_WORDS.perspective, 'question')
  assert.equal(CONTEXT_WORDS.batch, 'collected information')
  for (const word of Object.values(CONTEXT_WORDS)) {
    assert.doesNotMatch(word, /evidence|retained|inspect|admission|perspective/i)
  }
  const kinds: MagnetContext['kind'][] = ['post', 'file', 'image', 'attachment', 'perspective', 'batch']
  assert.equal(kinds.every((k) => k in CONTEXT_WORDS), true)
})

/* -- the shape of this part, as source ------------------------------------- */

test('the composer bar builds no context prose and gates the selector on no action', () => {
  const bar = readFileSync(new URL('../src/quiet2/magnets/ComposerBar.tsx', import.meta.url), 'utf8')
  /* The hook is installed once, unconditionally, and has no branch on which
     action is being sent: a note cannot be the one send that carries less. */
  assert.match(bar, /at\.beforeRequest = async \(post, op\) =>/)
  const hook = bar.slice(bar.indexOf('at.beforeRequest'), bar.indexOf('at.afterRecorded'))
  assert.doesNotMatch(hook, /record-only|ask-mentis|ask-participant/)
  assert.match(hook, new RegExp(`\\[${SELECTOR_FIELD === 'magnet_context' ? 'SELECTOR_FIELD' : SELECTOR_FIELD}\\]`))
  /* No instruction, configuration or capability prose is assembled here. */
  assert.doesNotMatch(bar, /supported_sources|unsupported|grounded_perspective_execution/)
  assert.doesNotMatch(bar, /In reference to/)
  const draft = readFileSync(new URL('../src/composer/draft.ts', import.meta.url), 'utf8')
  assert.doesNotMatch(draft, /text: d\.text\.trim\(\)/, 'the stored words are never trimmed')
})
