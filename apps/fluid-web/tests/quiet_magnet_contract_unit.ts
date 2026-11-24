/* The TypeScript half of the shared Magnet message-boundary contract check.
 *
 * Revised contract adm-c5c73679ac1e sections 2-5. The vectors in
 * tests/fixtures/magnet_boundary_vectors.json are the published contract; this
 * asserts the TS implementation reproduces them, and
 * tests/test_magnet_boundary_contract.py asserts Python reproduces the same
 * file from the same rules. Neither side may change a digest alone.
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFileSync } from 'node:fs'
import {
  AUTHORED_FLOW_PART_TYPES, CanonicalError, DIGEST_HEX_CHARS, HYDRATED_CONTEXT_MAX_BYTES,
  IDENTIFIER_MAX_CHARS, MANAGED_CONTEXT_VERSION, MANAGED_DELIVERY_STATES, MANAGED_REFUSAL,
  MANAGED_REQUEST_DOOR, RETAINED_GATE_CODE, SELECTOR_FIELD, SELECTOR_MAX_BYTES,
  SELECTOR_MAX_REFERENCES, authoredTextAgrees, canonicalJson, contextDigest, digestOf,
  emptySelectorV1, flowText, isBlankAuthoredText, isDigestHex, isIdentifier,
  materiallyRevised, submittedSelector, textDigest, validateExplicitSelector,
} from '../src/quiet2/magnets/contract'
import type {
  AuthoredPart, CanonicalValue, ManagedContextSnapshot, ManagedRefusalReason,
} from '../src/quiet2/magnets/contract'

interface Vectors {
  bounds: Record<string, number | string>
  canonical: { name: string; why: string; value: CanonicalValue; canonical: string; digest: string }[]
  text_digests: { name: string; text: string; digest: string }[]
  flow_text: { name: string; parts: AuthoredPart[]; text: string; agrees: boolean }[]
  selector_refusals: { name: string; selector: unknown; reason: ManagedRefusalReason }[]
  canonical_refusals: { name: string; value: CanonicalValue; reason: ManagedRefusalReason }[]
  distinct_digests: { why: string; left: string; right: string }[]
}
const vectors: Vectors = JSON.parse(
  readFileSync(new URL('./fixtures/magnet_boundary_vectors.json', import.meta.url), 'utf8'))

test('the published bounds are the ones this build enforces', () => {
  assert.deepEqual(vectors.bounds, {
    managed_context_version: MANAGED_CONTEXT_VERSION,
    selector_max_bytes: SELECTOR_MAX_BYTES,
    selector_max_references: SELECTOR_MAX_REFERENCES,
    hydrated_context_max_bytes: HYDRATED_CONTEXT_MAX_BYTES,
    identifier_max_chars: IDENTIFIER_MAX_CHARS,
    digest_hex_chars: DIGEST_HEX_CHARS,
    managed_request_door: MANAGED_REQUEST_DOOR,
    retained_gate_code: RETAINED_GATE_CODE,
  })
})

test('every canonical vector serialises and digests exactly as published', async () => {
  assert.ok(vectors.canonical.length >= 9)
  for (const v of vectors.canonical) {
    assert.equal(canonicalJson(v.value), v.canonical, v.name + ': canonical bytes')
    assert.equal(await digestOf(v.value), v.digest, v.name + ': digest')
    assert.ok(isDigestHex(v.digest), v.name + ': digest shape')
  }
})

/* Written out rather than read from the file: this is the one place the two
 * languages could silently diverge, because JS's default sort compares UTF-16
 * code units and would put the astral key before U+FFFD. */
test('object keys sort by Unicode scalar, not UTF-16 code unit', () => {
  assert.equal(canonicalJson({ a: 1, '\ufffd': 2, '\u{1f600}': 3, z: 4 }),
    '{"a":1,"z":4,"\ufffd":2,"\u{1f600}":3}')
  assert.notEqual(canonicalJson({ '\ufffd': 1, '\u{1f600}': 2 }),
    '{"\u{1f600}":2,"\ufffd":1}')
})

test('canonical form uses only the escaping JSON requires and normalises nothing', () => {
  assert.equal(canonicalJson({ s: 'a\u0301' }), '{"s":"a\u0301"}')
  assert.notEqual(canonicalJson({ s: '\u00e9' }), canonicalJson({ s: 'e\u0301' }))
  assert.equal(canonicalJson('\u007f'), '"\u007f"')
  assert.equal(canonicalJson('\u0001'), '"\\u0001"')
  assert.equal(canonicalJson('\n\t\r'), '"\\n\\t\\r"')
  assert.equal(canonicalJson([3, 1, 2]), '[3,1,2]')
})

test('exact authored text digests its own UTF-8 bytes, untrimmed', async () => {
  for (const v of vectors.text_digests) {
    assert.equal(await textDigest(v.text), v.digest, v.name)
  }
  for (const pair of vectors.distinct_digests) {
    assert.notEqual(await textDigest(pair.left), await textDigest(pair.right), pair.why)
  }
  assert.ok(isBlankAuthoredText('  \n '))
  assert.ok(!isBlankAuthoredText(' x '))
})

test('flow_text is the exact authored projection, and a chip in parts breaks it', () => {
  for (const v of vectors.flow_text) {
    assert.equal(authoredTextAgrees(v.text, v.parts), v.agrees, v.name)
  }
  // Mirrors mentis.conversation.versions.flow_text: text parts and the
  // characters of inline references, in order. Nothing else contributes.
  assert.deepEqual([...AUTHORED_FLOW_PART_TYPES],
    ['text', 'topic', 'turn', 'conversation', 'acquired', 'object'])
  assert.equal(flowText([{ type: 'file', ref: 'adm-1', text: 'ignored' }]), '')
  assert.equal(flowText([{ type: 'text', text: ' a ' }, { type: 'topic', ref: 'ent-1', text: '#b' }]), ' a #b')
  assert.equal(flowText(null), '')
})

test('the explicit empty selection is the full object, and {} is not it', () => {
  const cfg = '3f'.repeat(32)
  const empty = emptySelectorV1(cfg)
  assert.deepEqual(empty, { version: 1, mode: 'ordinary', configuration_digest: cfg, perspective: null, references: [] })
  const ok = validateExplicitSelector(empty)
  assert.ok(ok.ok)
  const published = vectors.canonical.find((v) => v.name === 'empty-selector-v1')!
  assert.equal(canonicalJson(empty as unknown as CanonicalValue), published.canonical)
  assert.equal(validateExplicitSelector({}).ok, false)
})

test('omission, null and an explicit selector stay three distinct submitted identities', () => {
  assert.deepEqual(submittedSelector({ text: 'hi' }), { form: 'omitted' })
  assert.deepEqual(submittedSelector({ [SELECTOR_FIELD]: null }), { form: 'null' })
  assert.deepEqual(submittedSelector({ [SELECTOR_FIELD]: { version: 1 } }),
    { form: 'explicit', value: { version: 1 } })
})

test('every published refusal refuses, with the published reason and a real status', () => {
  for (const v of vectors.selector_refusals) {
    const got = validateExplicitSelector(v.selector)
    assert.equal(got.ok, false, v.name + ' must refuse')
    assert.equal(got.ok === false && got.reason, v.reason, v.name + ': reason')
    assert.ok(MANAGED_REFUSAL[v.reason] >= 400, v.name + ': status')
  }
  for (const v of vectors.canonical_refusals) {
    assert.throws(() => canonicalJson(v.value), (e: unknown) =>
      e instanceof CanonicalError && e.reason === v.reason, v.name)
  }
  // Every refusal reason answers with an existing convention, nothing invented.
  for (const status of Object.values(MANAGED_REFUSAL)) {
    assert.ok([401, 403, 409, 422].includes(status), 'status ' + status)
  }
})

test('a valid selector passes the shape gate without resolving or hydrating anything', () => {
  const full = vectors.canonical.find((v) => v.name === 'full-selector-v1')!.value
  const got = validateExplicitSelector(full)
  assert.ok(got.ok, got.ok === false ? got.error : '')
  assert.equal(got.ok && got.selector.references.length, 3)
  assert.ok(isIdentifier('ent-1a2b3c4d5e6f'))
  assert.ok(!isIdentifier('x'.repeat(IDENTIFIER_MAX_CHARS + 1)))
  assert.ok(!isIdentifier(''))
  assert.ok(!isDigestHex('3F'.repeat(32)))
})

test('the context digest covers the body except itself, and an edit is seen by digest', async () => {
  const body: Omit<ManagedContextSnapshot, 'context_digest'> = {
    managed_context_version: 1, policy_version: 'magnet-boundary-1',
    brain_instance: 'brain-1f2e3d4c', corpus: 'corpus-aa11', magnet: 'mag-55667788',
    definition_digest: '3f'.repeat(32), author: 'ent-owner', observed_writer: 'ent-owner',
    operation: 'op-1', action: 'ask-participant', route: MANAGED_REQUEST_DOOR,
    conversation: 'ent-conv', submitted_form: 'explicit', selections: null,
    asking: { turn: 'ent-t', revision: '1', parts_digest: 'a'.repeat(64), text_digest: 'b'.repeat(64) },
  }
  const digest = await contextDigest(body)
  // Adding the field back must not change what was digested.
  assert.equal(await digestOf({ ...body, context_digest: digest } as unknown as CanonicalValue) === digest, false)
  assert.equal(await contextDigest({ ...body }), digest)
  assert.notEqual(await contextDigest({ ...body, asking: { ...body.asking, revision: '2' } }), digest)

  const accepted = body.asking
  assert.ok(!materiallyRevised(accepted, { parts_digest: accepted.parts_digest, text_digest: accepted.text_digest }))
  assert.ok(materiallyRevised(accepted, { parts_digest: 'c'.repeat(64), text_digest: accepted.text_digest }))
  // Edit-then-revert: the text matches again, but the recorded parts moved on.
  assert.ok(materiallyRevised(accepted, { parts_digest: 'c'.repeat(64), text_digest: 'b'.repeat(64) }))
})

test('supplied is one state among four and is not the prepared one', () => {
  assert.deepEqual([...MANAGED_DELIVERY_STATES], ['prepared', 'supplied', 'refused', 'failed'])
})
