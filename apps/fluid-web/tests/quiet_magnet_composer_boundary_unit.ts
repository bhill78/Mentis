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
  POST_NOT_SENDABLE, QUESTION_CHANGED, RECORD_CHANGED, RETAINED_NOT_SENDABLE,
  attachedVersion, configurationDigest, contextCandidate, definitionBody, managedSelector, refusalWords,
  selectedQuestion, selectedReference, stamped, versionOfRecord, versionOfRow, type SelectionSeam,
} from '../src/quiet2/magnets/ComposerBar'
import {
  MANAGED_REFUSAL, SELECTOR_FIELD, authoredTextAgrees, canonicalJson, digestOf, flowText,
  validateExplicitSelector, type MagnetContext, type MagnetResource, type MagnetSnapshot,
} from '../src/quiet2/magnets/contract'
import { bodyOf, emptyDraft, isEmpty, refIdentities, sendsNothing, type Draft } from '../src/composer/draft'
import { emptyPlaces } from '../src/quiet2/magnets/places'
import { loadWorking, saveWorking } from '../src/quiet2/magnets/workingState'
import { page } from '../src/brainBinding'

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

/* -- a supporting record is something a message can be about --------------- *
 * The owner's own requirement (ent-3191baeb33d2 §§1, 6): a collected post and
 * a collected file can each be referred to, at the version they were captured
 * at. The identity is the collection read's, served beside the immutable batch
 * and checked again at the door; the card states it and computes nothing. */

const BATCH = 'adm-batch1111111'
const ROW_DIGEST = 'b'.repeat(64)
const served = (id: string) =>
  ({ kind: 'collected_item', ref: id, version: BATCH, digest: ROW_DIGEST })

test('a collected post and a collected file are each selected at their captured version', () => {
  const rows = [
    { kind: 'post', id: 'ent-collected111', version: 'ent-version11111',
      value: { title: 'A post' }, reference: served('ent-collected111') },
    { kind: 'attachment', id: 'live:ent-collected111:part:1',
      value: { title: 'notes.txt' }, reference: served('live:ent-collected111:part:1') },
  ]
  for (const [ref, kind] of [['ent-collected111', 'post'], ['live:ent-collected111:part:1', 'file']] as const) {
    assert.deepEqual(selectedReference(rows, { ref, kind, label: 'Collected ' + kind }),
      { ok: true, value: { kind: 'collected_item', ref, version: BATCH, digest: ROW_DIGEST } },
      'the record the owner is reading is what the message is about')
    /* And the chip is stamped with exactly that, so it stands for the version
       the view showed rather than for whatever is there at the press. */
    assert.deepEqual(versionOfRecord(rows, ref), { version: BATCH, digest: ROW_DIGEST })
  }

  /* THE VERSION IS THE WHOLE OF IT. A row whose recorded digest is no longer
     the one the chip stands for is a different version of that record. */
  const chip: MagnetContext = { ref: 'ent-collected111', kind: 'post', label: 'A post' }
  const stampedChip = stamped(chip, { version: BATCH, digest: ROW_DIGEST })
  const moved = [{ ...rows[0], reference: { ...served('ent-collected111'), digest: 'c'.repeat(64) } }]
  const changedRow = selectedReference(moved, stampedChip)
  assert.equal(changedRow.ok === false && changedRow.why, RECORD_CHANGED)
  const laterBatch = [{ ...rows[0], reference: { ...served('ent-collected111'), version: 'adm-batch2222222' } }]
  const changedBatch = selectedReference(laterBatch, stampedChip)
  assert.equal(changedBatch.ok === false && changedBatch.why, RECORD_CHANGED,
    'the collection it was captured in is part of the version it stands for')
  const gone = selectedReference([], stampedChip)
  assert.equal(gone.ok === false && gone.why, POST_NOT_SENDABLE,
    'a record the card no longer holds is refused, never substituted')
})

test('an identity the card cannot state exactly is not one: the refusal stands', () => {
  const malformed = [
    { why: 'another row', reference: { ...served('ent-other1111111') } },
    { why: 'not a collected item', reference: { ...served('ent-collected111'), kind: 'artifact' } },
    { why: 'no batch', reference: { ...served('ent-collected111'), version: '' } },
    { why: 'a batch that is not a string', reference: { ...served('ent-collected111'), version: null } },
    { why: 'no digest', reference: { ...served('ent-collected111'), digest: 'short' } },
    { why: 'an upper-case digest', reference: { ...served('ent-collected111'), digest: 'B'.repeat(64) } },
    { why: 'nothing at all', reference: undefined },
  ]
  for (const { why, reference } of malformed) {
    const rows = [{ kind: 'post', id: 'ent-collected111', version: 'ent-version11111', value: {}, reference }]
    const got = selectedReference(rows, { ref: 'ent-collected111', kind: 'post', label: 'A post' })
    assert.equal(got.ok === false && got.why, POST_NOT_SENDABLE, why + ' states no exact version')
    assert.equal(versionOfRecord(rows, 'ent-collected111'), null, why + ' stamps no chip')
  }
  /* An immutable held file keeps its own identity where no row identity is
     served: this adds a path, it does not take one away. */
  const held = [{ kind: 'file', id: 'adm-held1111111', version: 'adm-held1111111', value: { digest: DIGEST } }]
  assert.deepEqual(selectedReference(held, { ref: 'adm-held1111111', kind: 'file', label: 'notes.txt' }),
    { ok: true, value: { kind: 'artifact', ref: 'adm-held1111111', version: null, digest: DIGEST } })
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

/* -- a wordless message whose point is what it is about -------------------- */

test('an intentionally attached reference is something to send, with no words invented for it', () => {
  const nothing = draftWith({ text: '' })
  assert.equal(isEmpty(nothing), true, 'the draft itself holds nothing')
  assert.equal(sendsNothing(nothing), true, 'generic posting: an empty draft is still nothing to send')
  assert.equal(sendsNothing(nothing, false), true, 'and a surface with nothing attached is the same')
  assert.equal(sendsNothing(nothing, true), false,
    'a reference the surface holds and means to send IS something to send')
  assert.equal(sendsNothing(draftWith({ text: '   \r\n' }), true), false,
    'whitespace the owner typed does not become the content, and does not need to')
  /* AND NOTHING IS WRITTEN TO MAKE IT SENDABLE: the body of that send is the
     published vector's chip-only shape -- no parts, no words, agreeing. */
  const body = bodyOf(nothing, ME, [], 'ask-mentis', { references: 'audited' })
  assert.deepEqual(body.parts, [])
  assert.equal(body.text, '')
  assert.ok(authoredTextAgrees(body.text, body.parts as never))
  /* With words, the chip changes nothing about them. */
  const typed = bodyOf(draftWith({ text: 'and this too' }), ME, [], 'ask-mentis', { references: 'audited' })
  assert.equal(typed.text, 'and this too')
})

test('the one send gate reads what the surface attached; what the composer draws does not', () => {
  const composer = readFileSync(new URL('../src/fluid/Composer.tsx', import.meta.url), 'utf8')
  assert.match(composer, /const nothingToSend = sendsNothing\(draft, asking\?\.attached\)/)
  /* Both ways of sending -- the button and every keyboard path through `go` --
     read the same predicate, so they cannot disagree about what is sendable. */
  assert.match(composer, /if \(busy \|\| nothingToSend \|\| !me\) return/)
  assert.match(composer, /className="fw-send-main" disabled=\{busy \|\| nothingToSend \|\| !me\}/)
  /* What is drawn, collapsed and kept is still the draft's own question: a
     chip merely being attached does not force an expanded composer. */
  assert.match(composer, /const closed = !open && isEmpty\(draft\)/)
  assert.match(composer, /const kept = !isEmpty\(draft\)/)
  /* And the Magnet's bar is what declares it, from the chip it is showing. */
  const bar = readFileSync(new URL('../src/quiet2/magnets/ComposerBar.tsx', import.meta.url), 'utf8')
  assert.match(bar, /attached: !!s\.context/)
})

/* -- the exact version the chip stands for --------------------------------- */

test('a chip says which version it stands for, and only a real version counts as one', () => {
  const chip: MagnetContext = { ref: LENS, kind: 'perspective', label: 'A question' }
  assert.equal(attachedVersion(chip), null, 'an identifier alone stands for no version')
  assert.equal(attachedVersion(null), null)
  assert.equal(attachedVersion({ ...chip, digest: 'not-a-digest' }), null, 'and neither does a non-digest')
  assert.deepEqual(attachedVersion(stamped(chip, { version: QUESTION, digest: QUESTION_DIGEST })),
    { version: QUESTION, digest: QUESTION_DIGEST })
  /* An immutable artifact has no version of its own: null is a real answer. */
  assert.deepEqual(attachedVersion({ ref: 'adm-held1111111', kind: 'file', label: 'notes.txt', version: null, digest: DIGEST }),
    { version: null, digest: DIGEST })
  assert.deepEqual(stamped(chip, null), chip, 'nothing to say is said as nothing, not as a made-up version')

  /* What a version is READ FROM: the durable row the owner is looking at. */
  assert.deepEqual(versionOfRow([{ perspective: LENS, question: { ref: QUESTION, digest: QUESTION_DIGEST } }], LENS),
    { version: QUESTION, digest: QUESTION_DIGEST })
  assert.equal(versionOfRow([{ perspective: LENS, question: null }], LENS), null)
  assert.equal(versionOfRow([], LENS), null)
  assert.deepEqual(versionOfRecord([{ id: 'adm-held1111111', value: { digest: DIGEST } }], 'adm-held1111111'),
    { version: null, digest: DIGEST })
  assert.equal(versionOfRecord([{ id: 'ent-collected111', value: { digest: DIGEST } }], 'ent-collected111'), null,
    'only a held artifact is stated this way; a post needs its authored revision')
  assert.equal(versionOfRecord([], 'adm-held1111111'), null)
})

test('a question revised since the chip was attached refuses; it is never sent in its place', () => {
  const rows = [{ perspective: LENS, question: { ref: QUESTION, digest: QUESTION_DIGEST } }]
  const ordinary = { perspective: LENS, revision: QUESTION }
  const held = { version: QUESTION, digest: QUESTION_DIGEST }
  assert.deepEqual(selectedQuestion(ordinary, rows, LENS, held),
    { ok: true, value: { id: LENS, question_ref: QUESTION, question_digest: QUESTION_DIGEST } })

  /* THE DEFECT THIS CLOSES. The record has moved on to a later saved question
     and is perfectly self-consistent about it -- the fresh read and the row
     agree -- so nothing but the chip's own version says the owner read
     something else. Both of these went out silently before. */
  const laterRef = { perspective: LENS, revision: 'adm-question2222' }
  const laterRows = [{ perspective: LENS, question: { ref: 'adm-question2222', digest: QUESTION_DIGEST } }]
  const revised = selectedQuestion(laterRef, laterRows, LENS, held)
  assert.equal(revised.ok, false, 'a later saved question is not the one this message was about')
  assert.equal(revised.ok === false && revised.why, QUESTION_CHANGED)
  const rewritten = selectedQuestion(ordinary, [{ perspective: LENS, question: { ref: QUESTION, digest: 'c'.repeat(64) } }], LENS, held)
  assert.equal(rewritten.ok === false && rewritten.why, QUESTION_CHANGED,
    'the same artifact with another digest is another version too')

  /* A chip that states no version is unchanged behaviour: the fresh read's own
     consistency is all there is, and that is what travels. */
  assert.equal(selectedQuestion(laterRef, laterRows, LENS, null).ok, true)
  assert.equal(selectedQuestion(laterRef, laterRows, LENS).ok, true, 'and the argument is optional')
})

test('a held record that is not the attached version refuses, and a deleted one refuses', () => {
  const rows = [{ kind: 'file', id: 'adm-held1111111', version: 'adm-held1111111', value: { digest: DIGEST } }]
  const chip: MagnetContext = { ref: 'adm-held1111111', kind: 'file', label: 'notes.txt' }
  assert.deepEqual(selectedReference(rows, stamped(chip, { version: null, digest: DIGEST })),
    { ok: true, value: { kind: 'artifact', ref: 'adm-held1111111', version: null, digest: DIGEST } })
  const changed = selectedReference([{ ...rows[0], value: { digest: 'd'.repeat(64) } }], stamped(chip, { version: null, digest: DIGEST }))
  assert.equal(changed.ok === false && changed.why, RECORD_CHANGED)
  const gone = selectedReference([], stamped(chip, { version: null, digest: DIGEST }))
  assert.equal(gone.ok === false && gone.why, FILE_NOT_SENDABLE, 'a record the card no longer holds is not substituted')
})

test('a stamped chip stops the send at the composer, with the words, the key and the chip kept', async () => {
  const chip = stamped({ ref: LENS, kind: 'perspective', label: 'A question' },
    { version: QUESTION, digest: QUESTION_DIGEST })
  const resource = resourceFor({ lens: LENS, context: chip })
  const revised = {
    ordinary: { perspective: LENS, revision: 'adm-question2222' },
    rows: [{ perspective: LENS, question: { ref: 'adm-question2222', digest: QUESTION_DIGEST } }],
  }
  for (const [what, post] of SENDS) {
    await assert.rejects(() => managedSelector(seamFor(resource, revised), post),
      new RegExp(QUESTION_CHANGED.slice(0, 40)), what)
  }
  /* Nothing was rewritten to get past it: the chip still stands for the
     version the owner attached, and the card's state is as it was. */
  assert.deepEqual(resource.snapshot().context, chip)
  /* And the unrevised record still sends that exact version. */
  const same = await managedSelector(seamFor(resource, {
    ordinary: { perspective: LENS, revision: QUESTION },
    rows: [{ perspective: LENS, question: { ref: QUESTION, digest: QUESTION_DIGEST } }],
  }), SENDS[1][1])
  assert.deepEqual(same.perspective, { id: LENS, question_ref: QUESTION, question_digest: QUESTION_DIGEST })
})

test('the version the chip stands for survives being put away and reopened; removal stays removed', () => {
  const data = new Map<string, string>()
  const old = Object.getOwnPropertyDescriptor(globalThis, 'localStorage')
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: {
    getItem: (key: string) => data.get(key) ?? null,
    setItem: (key: string, value: string) => data.set(key, value),
    removeItem: (key: string) => data.delete(key),
  } })
  page.saw('corpus-a@one-instance')
  try {
    const brainKey = 'https://fixture.invalid|dev|corpus-a'
    const chip = stamped({ ref: LENS, kind: 'perspective', label: 'A question' },
      { version: QUESTION, digest: QUESTION_DIGEST })
    saveWorking(brainKey, 'mag-fixtureA', snapshotFor({ lens: LENS, context: chip }))
    const back = loadWorking(brainKey, 'mag-fixtureA')
    assert.deepEqual(back.context, chip, 'the chip comes back as the version it stood for, not as an id alone')
    assert.deepEqual(attachedVersion(back.context ?? null), { version: QUESTION, digest: QUESTION_DIGEST })
    /* Captured text is still never kept. */
    saveWorking(brainKey, 'mag-fixtureA', snapshotFor({ context: { ...chip, text: 'captured body' } }))
    assert.equal('text' in (loadWorking(brainKey, 'mag-fixtureA').context ?? {}), false)
    /* A send in flight carries its own note, with the same exact version. */
    saveWorking(brainKey, 'mag-fixtureA', snapshotFor({ context: chip,
      carried: { op: 'op-1', context: chip, suppressed: false, from: null as never } }))
    assert.equal(loadWorking(brainKey, 'mag-fixtureA').carried, null, 'a note without its route is not restored')
    /* AN INTENTIONAL REMOVAL STAYS REMOVED across the same reopen, and brings
       back no version of anything. */
    saveWorking(brainKey, 'mag-fixtureA', snapshotFor({ lens: LENS, context: null, contextSuppressed: true }))
    const removed = loadWorking(brainKey, 'mag-fixtureA')
    assert.equal(removed.context, null)
    assert.equal(removed.contextSuppressed, true)
    /* A chip written by a release that kept no version comes back as an id
       alone, and says so rather than claiming one. */
    data.set(`mentis.magnet.working.v1:${brainKey}:corpus-a@one-instance:mag-fixtureA`,
      JSON.stringify({ open: true, wide: false, context: { ref: LENS, kind: 'perspective', label: 'A question', digest: 'not-a-digest' } }))
    assert.equal(attachedVersion(loadWorking(brainKey, 'mag-fixtureA').context ?? null), null)
  } finally {
    if (old) Object.defineProperty(globalThis, 'localStorage', old)
    else delete (globalThis as { localStorage?: unknown }).localStorage
  }
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
  assert.deepEqual(got, { ref: 'adm-held1111111', kind: 'file', label: 'notes.txt', version: null, digest: DIGEST },
    'and offers it AT the version the view is showing, which is what the chip then stands for')

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

test('the composer bar carries a frozen Perspective ask through unchanged, and binds and reconciles the actual send', () => {
  const bar = readFileSync(new URL('../src/quiet2/magnets/ComposerBar.tsx', import.meta.url), 'utf8')
  const before = bar.slice(bar.indexOf('at.beforeRequest'), bar.indexOf('at.afterRecorded'))
  // The exact chip the fresh selector just checked against the record is what
  // decides this, never whatever this card happened to be holding.
  assert.match(before, /selector\.perspective\?\.id === active\.perspective/)
  assert.match(before, /perspectiveRequest\(post, active\)/)
  assert.match(before, /op: active\.request_op/)
  // An `active` already bound by an earlier send is never reused for a
  // different, later one: only a still-unsent frozen ask is carried through.
  assert.match(before, /inquiryState\.bound\?\.perspective !== active\.perspective/)
  const after = bar.slice(bar.indexOf('at.afterRecorded'))
  assert.match(after, /await inquiries\.bind\(attempt\.perspective, request\)/)
  assert.match(after, /await inquiries\.reconcile\(attempt\.perspective, 'display'\)/)
  // Binding also records which actual request this Perspective's agent-reply
  // boundary is read against (`finalizeReply`), never guessed from `active` alone.
  assert.match(after, /bound: \{ perspective: attempt\.perspective\.perspective, request \}/)
})
